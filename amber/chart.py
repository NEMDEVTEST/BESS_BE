"""Plotly interactive dashboard — Amber Electric + Fox ESS."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ------------------------------------------------------------------
# Colour themes
# Each theme: bg, plot_bg, grid, zero, and trace colours
# ------------------------------------------------------------------
THEMES: dict[str, dict] = {
    "sharp": {
        "name": "Sharp Dark",
        "bg":       "#08090F",
        "plot_bg":  "#0C0E18",
        "grid":     "#181C2E",
        "zero":     "#2A2D3E",
        "import":   "#FF4D6D",   # vivid coral-red
        "export":   "#00E5FF",   # electric cyan
        "load":     "#FFFFFF",   # pure white
        "solar":    "#FFD60A",   # sharp gold
        "price":    "#C77DFF",   # vivid purple
        "revenue":  "#00FF87",   # bright green
        "active":   "#00E5FF",
    },
    "synthwave": {
        "name": "Synthwave",
        "bg":       "#0A0018",
        "plot_bg":  "#0E0022",
        "grid":     "#1A0033",
        "zero":     "#2D0050",
        "import":   "#FF0F80",   # neon magenta
        "export":   "#01FFA3",   # neon mint
        "load":     "#E8E8FF",   # pale lavender white
        "solar":    "#FF8C00",   # vivid orange
        "price":    "#9D4EDD",   # deep purple
        "revenue":  "#FFE066",   # warm yellow
        "active":   "#01FFA3",
    },
    "glacier": {
        "name": "Glacier",
        "bg":       "#030D14",
        "plot_bg":  "#051220",
        "grid":     "#0C2030",
        "zero":     "#183045",
        "import":   "#FF6B81",   # rose pink
        "export":   "#00BFFF",   # deep sky blue
        "load":     "#F0FFFF",   # azure white
        "solar":    "#FFA040",   # warm amber
        "price":    "#00FA9A",   # spring green
        "revenue":  "#7BFF7B",   # lime green
        "active":   "#00BFFF",
    },
    "inferno": {
        "name": "Inferno",
        "bg":       "#0A0A08",
        "plot_bg":  "#0F0F0C",
        "grid":     "#1C1C18",
        "zero":     "#2E2E28",
        "import":   "#4895EF",   # steel blue
        "export":   "#FF4500",   # orange-red
        "load":     "#FFF5E0",   # warm white
        "solar":    "#FFD700",   # gold
        "price":    "#DA70D6",   # orchid
        "revenue":  "#FFD700",   # gold
        "active":   "#FF4500",
    },
}


def build_dashboard(
    df: pd.DataFrame,
    output_path: str | Path = "output/dashboard.html",
    theme: str = "sharp",
) -> Path:
    """
    Build and save an interactive Plotly dashboard.

    Parameters
    ----------
    df          : Unified DataFrame with columns:
                  dt, grid_export, grid_import, price, home_load, solar, soc
    output_path : Destination for the self-contained HTML file.
    theme       : One of 'sharp', 'synthwave', 'glacier', 'inferno'.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    t = THEMES.get(theme, THEMES["sharp"])

    # ------------------------------------------------------------------
    # Amber traces — grid import/export and price
    # ------------------------------------------------------------------
    amber = df[["dt", "grid_export", "grid_import", "price"]].dropna(
        subset=["grid_export", "grid_import", "price"], how="all"
    ).set_index("dt").sort_index()

    price_series = amber["price"]
    export_kw    = amber["grid_export"]           # positive
    import_kw    = -amber["grid_import"]           # negative (for chart)
    import_abs   = amber["grid_import"]            # positive (for hover)

    # ------------------------------------------------------------------
    # Fox ESS traces — home load, solar, SoC; resample to 5-min
    # ------------------------------------------------------------------
    fox = df[["dt", "home_load", "solar", "soc"]].dropna(
        subset=["home_load", "solar", "soc"], how="all"
    ).set_index("dt").sort_index()
    fox_5min = fox.resample("5min").mean()

    load_kw  = fox_5min["home_load"]
    solar_kw = fox_5min["solar"]
    soc      = fox_5min["soc"]

    # ------------------------------------------------------------------
    # Revenue series (5-min intervals → divide kW by 12 to get kWh)
    # ------------------------------------------------------------------
    revenue = (amber["grid_export"] - amber["grid_import"]) / 12 * amber["price"]
    cumulative_revenue = revenue.cumsum()

    # ------------------------------------------------------------------
    # Figure — 3 rows: main (2/4), revenue (1/4), cumulative (1/4)
    # ------------------------------------------------------------------
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.5, 0.25, 0.25],
        specs=[
            [{"secondary_y": True}],
            [{"secondary_y": False}],
            [{"secondary_y": False}],
        ],
    )

    # Grid Export (positive, cyan/theme)
    fig.add_trace(
        go.Bar(
            x=export_kw.index,
            y=export_kw.values,
            name="Grid Export",
            marker_color=t["export"],
            marker_line_width=0,
            opacity=0.45,
            hovertemplate=(
                "<b>Grid Export</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{y:.2f} kW<extra></extra>"
            ),
        ),
        row=1, col=1, secondary_y=False,
    )

    # Grid Import (negative, red/theme)
    fig.add_trace(
        go.Bar(
            x=import_kw.index,
            y=import_kw.values,
            name="Grid Import",
            marker_color=t["import"],
            marker_line_width=0,
            opacity=0.45,
            hovertemplate=(
                "<b>Grid Import</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{customdata:.2f} kW<extra></extra>"
            ),
            customdata=import_abs.values,
        ),
        row=1, col=1, secondary_y=False,
    )

    # Home Load line
    fig.add_trace(
        go.Scatter(
            x=load_kw.index,
            y=load_kw.values,
            name="Home Load",
            mode="lines",
            line=dict(color=t["load"], width=1.2),
            opacity=0.9,
            hovertemplate=(
                "<b>Home Load</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{y:.2f} kW<extra></extra>"
            ),
        ),
        row=1, col=1, secondary_y=False,
    )

    # Gen Load / AC Solar line
    fig.add_trace(
        go.Scatter(
            x=solar_kw.index,
            y=solar_kw.values,
            name="Solar",
            mode="lines",
            line=dict(color=t["solar"], width=1.2),
            opacity=0.9,
            hovertemplate=(
                "<b>Gen Load (AC Solar)</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{y:.2f} kW<extra></extra>"
            ),
        ),
        row=1, col=1, secondary_y=False,
    )

    # Spot Price (secondary axis)
    fig.add_trace(
        go.Scatter(
            x=price_series.index,
            y=price_series.values,
            name="Price",
            mode="lines",
            line=dict(color=t["price"], width=1.2),
            opacity=0.9,
            hovertemplate=(
                "<b>Spot Price</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{y:.2f} c/kWh<extra></extra>"
            ),
        ),
        row=1, col=1, secondary_y=True,
    )

    # SoC (third axis — hidden by default, toggle via legend)
    fig.add_trace(
        go.Scatter(
            x=soc.index,
            y=soc.values,
            name="SoC",
            mode="lines",
            line=dict(color="#06D6A0", width=1.5, dash="dot"),
            opacity=0.9,
            visible="legendonly",
            hovertemplate=(
                "<b>SoC</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{y:.0f}%<extra></extra>"
            ),
            yaxis="y5",
        ),
    )

    # ------------------------------------------------------------------
    # Row 2: Revenue per interval
    # ------------------------------------------------------------------
    fig.add_trace(
        go.Bar(
            x=revenue.index,
            y=revenue.values,
            name="Revenue",
            marker_color=t["revenue"],
            marker_line_width=0,
            opacity=0.7,
            hovertemplate=(
                "<b>Revenue</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "%{y:.2f} cents<extra></extra>"
            ),
        ),
        row=2, col=1,
    )

    # ------------------------------------------------------------------
    # Row 3: Cumulative revenue
    # ------------------------------------------------------------------
    fig.add_trace(
        go.Scatter(
            x=cumulative_revenue.index,
            y=cumulative_revenue.values / 100,
            name="Cumulative Revenue",
            mode="lines",
            line=dict(color=t["revenue"], width=1.5),
            fill="tozeroy",
            fillcolor="rgba(0, 255, 135, 0.1)",
            hovertemplate=(
                "<b>Cumulative Revenue</b><br>"
                "%{x|%d %b %Y %H:%M}<br>"
                "$%{y:.2f}<extra></extra>"
            ),
        ),
        row=3, col=1,
    )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    t_min = df["dt"].min().strftime("%d %b %Y")
    t_max = df["dt"].max().strftime("%d %b %Y")

    axis_common = dict(gridcolor=t["grid"], linecolor=t["zero"], zerolinecolor=t["zero"])

    fig.update_layout(
        title=dict(
            text=(
                f"<b>BESS Dashboard</b>  [{t['name']}]  ·  {t_min} to {t_max}<br>"
                "<sup style='color:#666'>"
            ),
            x=0.02,
            font=dict(size=18),
        ),
        barmode="overlay",
        bargap=0,
        plot_bgcolor=t["plot_bg"],
        paper_bgcolor=t["bg"],
        font=dict(color="#E8EAF6", family="'SF Mono', 'Fira Code', 'Consolas', monospace"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0.6)",
            bordercolor=t["zero"],
            borderwidth=1,
        ),
        hovermode="x unified",
        # Row 1 x-axis (top chart)
        xaxis=dict(
            gridcolor=t["grid"],
            showgrid=True,
            linecolor=t["zero"],
            rangeselector=dict(
                buttons=[
                    dict(count=1,  label="1d",  step="day", stepmode="backward"),
                    dict(count=7,  label="7d",  step="day", stepmode="backward"),
                    dict(count=14, label="14d", step="day", stepmode="backward"),
                    dict(step="all", label="30d"),
                ],
                bgcolor=t["bg"],
                activecolor=t["active"],
                bordercolor=t["zero"],
                font=dict(color="#E8EAF6"),
                x=0,
                y=1.08,
            ),
        ),
        # Row 2 x-axis
        xaxis2=dict(
            gridcolor=t["grid"],
            showgrid=True,
            linecolor=t["zero"],
        ),
        # Row 3 x-axis (bottom chart — gets the range slider + label)
        xaxis3=dict(
            title="Time (AEST/AEDT)",
            gridcolor=t["grid"],
            showgrid=True,
            linecolor=t["zero"],
            rangeslider=dict(visible=True, thickness=0.08, bgcolor=t["bg"]),
        ),
        # Row 1 primary y-axis
        yaxis=dict(
            title="Power (kW)  [Export + / Import -]",
            zerolinewidth=2,
            **axis_common,
        ),
        # Row 1 secondary y-axis (price)
        yaxis2=dict(
            title="Price (c/kWh)",
            range=[-80, 80],
            gridcolor="rgba(0,0,0,0)",
            zerolinecolor=t["zero"],
            zerolinewidth=1,
            linecolor=t["zero"],
        ),
        # Row 2 y-axis (revenue per interval)
        yaxis3=dict(
            title="Revenue (cents)",
            zerolinewidth=1,
            **axis_common,
        ),
        # Row 3 y-axis (cumulative revenue)
        yaxis4=dict(
            title="Cumulative ($)",
            zerolinewidth=1,
            **axis_common,
        ),
        # SoC overlay on row 1
        yaxis5=dict(
            title=dict(text="SoC (%)", font=dict(color="#06D6A0")),
            range=[0, 100],
            overlaying="y",
            side="right",
            anchor="free",
            position=1.0,
            gridcolor="rgba(0,0,0,0)",
            zerolinecolor="rgba(0,0,0,0)",
            tickfont=dict(color="#06D6A0"),
            linecolor=t["zero"],
        ),
        margin=dict(t=120, b=60, l=70, r=110),
        height=1000,
    )

    fig.add_hline(y=0, line_width=1, line_color=t["zero"], row=1, col=1, secondary_y=False)
    fig.add_hline(y=0, line_width=1, line_color=t["zero"], row=2, col=1)

    # ------------------------------------------------------------------
    # Write HTML
    # ------------------------------------------------------------------
    fig.write_html(
        str(output_path),
        include_plotlyjs="cdn",
        full_html=True,
        config={
            "scrollZoom": True,
            "displayModeBar": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )
    print(f"  [{t['name']}] saved: {output_path.resolve()}")
    return output_path
