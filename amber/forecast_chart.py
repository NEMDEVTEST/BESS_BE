"""Forecast dashboard — 24h actuals + forward forecasts for price, solar, load."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .chart import THEMES

# Battery capacity
BATTERY_KWH = 42.0


def _simulate_soc(
    solar: pd.Series,
    load: pd.Series,
    start_soc_pct: float,
    capacity_kwh: float = BATTERY_KWH,
) -> pd.Series:
    """Simulate SoC forward from start_soc_pct using solar - load at each step.

    Both solar and load should be in kW, indexed by datetime at regular intervals.
    Returns SoC as percentage (0-100).
    """
    # Align and fill gaps
    combined = pd.DataFrame({"solar": solar, "load": load}).sort_index()
    combined = combined.ffill().fillna(0)

    # Interval in hours (detect from index)
    if len(combined) < 2:
        return pd.Series(dtype=float)
    dt_hours = (combined.index[1] - combined.index[0]).total_seconds() / 3600

    soc_kwh = start_soc_pct / 100 * capacity_kwh
    soc_vals = []

    for _, row in combined.iterrows():
        net_kwh = (row["solar"] - row["load"]) * dt_hours
        soc_kwh = max(0, min(capacity_kwh, soc_kwh + net_kwh))
        soc_vals.append(soc_kwh / capacity_kwh * 100)

    return pd.Series(soc_vals, index=combined.index, name="soc_forecast")


def build_forecast_dashboard(
    actuals: pd.DataFrame,
    price_forecast: pd.DataFrame,
    solar_forecast: pd.DataFrame,
    output_path: str | Path = "docs/forecast.html",
    theme: str = "sharp",
) -> Path:
    """Build a forecast dashboard showing 24h actuals + forward forecasts.

    Parameters
    ----------
    actuals        : energy table rows for the last 24h (dt, price, solar, home_load, ...)
    price_forecast : Amber forecast (dt, price_forecast, price_low, price_high)
    solar_forecast : Solcast forecast (dt, pv_estimate, pv_estimate10, pv_estimate90)
    output_path    : HTML output path
    theme          : colour theme name
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    t = THEMES.get(theme, THEMES["sharp"])

    # ------------------------------------------------------------------
    # Prepare actuals (last 24h)
    # ------------------------------------------------------------------
    act = actuals.set_index("dt").sort_index()

    # ------------------------------------------------------------------
    # Load forecast = repeat last 24h of actuals, shifted forward
    # ------------------------------------------------------------------
    load_actual = act["home_load"].dropna()
    if not load_actual.empty:
        cutoff = load_actual.index.max() - pd.Timedelta(hours=24)
        last_24h = load_actual.loc[cutoff:]
        shift = pd.Timedelta(hours=24)
        load_forecast = last_24h.copy()
        load_forecast.index = load_forecast.index + shift
    else:
        load_forecast = pd.Series(dtype=float)

    # ------------------------------------------------------------------
    # SoC forecast: simulate from current level using forecast solar/load
    # ------------------------------------------------------------------
    soc_actual = act["soc"].dropna() if "soc" in act.columns else pd.Series(dtype=float)
    current_soc = soc_actual.iloc[-1] if not soc_actual.empty else 50.0

    soc_forecast = pd.Series(dtype=float)
    if not solar_forecast.empty and not load_forecast.empty:
        sf_idx = solar_forecast.set_index("dt")["pv_estimate"]
        soc_forecast = _simulate_soc(sf_idx, load_forecast, current_soc)

    # ------------------------------------------------------------------
    # Build figure — 4 rows: SoC, Price, Solar, Load
    # ------------------------------------------------------------------
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.25, 0.25, 0.25, 0.25],
        subplot_titles=("Battery SoC (%)", "Price (c/kWh)", "Solar (kW)", "Load (kW)"),
    )

    now_line_color = "#FFFFFF"
    soc_color = "#06D6A0"

    # ==== Row 1: SoC ====
    if not soc_actual.empty:
        fig.add_trace(
            go.Scatter(
                x=soc_actual.index, y=soc_actual.values,
                name="SoC (actual)", mode="lines",
                line=dict(color=soc_color, width=1.5),
                hovertemplate="<b>SoC</b><br>%{x|%H:%M %d %b}<br>%{y:.0f}%<extra></extra>",
            ),
            row=1, col=1,
        )

    if not soc_forecast.empty:
        fig.add_trace(
            go.Scatter(
                x=soc_forecast.index, y=soc_forecast.values,
                name="SoC (forecast)", mode="lines",
                line=dict(color=soc_color, width=1.5, dash="dot"),
                hovertemplate="<b>SoC forecast</b><br>%{x|%H:%M %d %b}<br>%{y:.0f}%<extra></extra>",
            ),
            row=1, col=1,
        )

    # ==== Row 2: Price ====
    if "price" in act.columns:
        price_act = act["price"].dropna()
        fig.add_trace(
            go.Scatter(
                x=price_act.index, y=price_act.values,
                name="Price (actual)", mode="lines",
                line=dict(color=t["price"], width=1.5),
                hovertemplate="<b>Price</b><br>%{x|%H:%M %d %b}<br>%{y:.1f} c/kWh<extra></extra>",
            ),
            row=2, col=1,
        )

    if not price_forecast.empty:
        pf = price_forecast.set_index("dt").sort_index()
        fig.add_trace(
            go.Scatter(
                x=pf.index, y=pf["price_high"].values,
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=pf.index, y=pf["price_low"].values,
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(199, 125, 255, 0.15)",
                name="Price range",
                hoverinfo="skip",
            ),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=pf.index, y=pf["price_forecast"].values,
                name="Price (forecast)", mode="lines",
                line=dict(color=t["price"], width=1.5, dash="dot"),
                hovertemplate="<b>Price forecast</b><br>%{x|%H:%M %d %b}<br>%{y:.1f} c/kWh<extra></extra>",
            ),
            row=2, col=1,
        )

    # ==== Row 3: Solar ====
    if "solar" in act.columns:
        solar_act = act["solar"].dropna()
        fig.add_trace(
            go.Scatter(
                x=solar_act.index, y=solar_act.values,
                name="Solar (actual)", mode="lines",
                line=dict(color=t["solar"], width=1.5),
                hovertemplate="<b>Solar</b><br>%{x|%H:%M %d %b}<br>%{y:.2f} kW<extra></extra>",
            ),
            row=3, col=1,
        )

    if not solar_forecast.empty:
        sf = solar_forecast.set_index("dt").sort_index()
        fig.add_trace(
            go.Scatter(
                x=sf.index, y=sf["pv_estimate90"].values,
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=sf.index, y=sf["pv_estimate10"].values,
                mode="lines", line=dict(width=0),
                fill="tonexty", fillcolor="rgba(255, 214, 10, 0.15)",
                name="Solar range",
                hoverinfo="skip",
            ),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=sf.index, y=sf["pv_estimate"].values,
                name="Solar (forecast)", mode="lines",
                line=dict(color=t["solar"], width=1.5, dash="dot"),
                hovertemplate="<b>Solar forecast</b><br>%{x|%H:%M %d %b}<br>%{y:.2f} kW<extra></extra>",
            ),
            row=3, col=1,
        )

    # ==== Row 4: Load ====
    if "home_load" in act.columns:
        load_act = act["home_load"].dropna()
        fig.add_trace(
            go.Scatter(
                x=load_act.index, y=load_act.values,
                name="Load (actual)", mode="lines",
                line=dict(color=t["load"], width=1.5),
                hovertemplate="<b>Load</b><br>%{x|%H:%M %d %b}<br>%{y:.2f} kW<extra></extra>",
            ),
            row=4, col=1,
        )

    if not load_forecast.empty:
        fig.add_trace(
            go.Scatter(
                x=load_forecast.index, y=load_forecast.values,
                name="Load (forecast)", mode="lines",
                line=dict(color=t["load"], width=1.5, dash="dot"),
                opacity=0.7,
                hovertemplate="<b>Load forecast</b><br>%{x|%H:%M %d %b}<br>%{y:.2f} kW<extra></extra>",
            ),
            row=4, col=1,
        )

    # ------------------------------------------------------------------
    # "Now" vertical line on all subplots
    # ------------------------------------------------------------------
    now = pd.Timestamp.now().floor("min")
    for row in range(1, 5):
        fig.add_vline(
            x=now, line_width=1, line_dash="dash",
            line_color=now_line_color, opacity=0.5,
            row=row, col=1,
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    axis_common = dict(gridcolor=t["grid"], linecolor=t["zero"], zerolinecolor=t["zero"])

    fig.update_layout(
        title=dict(
            text="<b>BESS Forecast Dashboard</b>",
            x=0.02,
            font=dict(size=18),
        ),
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
        xaxis=dict(gridcolor=t["grid"], showgrid=True, linecolor=t["zero"]),
        xaxis2=dict(gridcolor=t["grid"], showgrid=True, linecolor=t["zero"]),
        xaxis3=dict(gridcolor=t["grid"], showgrid=True, linecolor=t["zero"]),
        xaxis4=dict(
            title="Time (AEST/AEDT)",
            gridcolor=t["grid"], showgrid=True, linecolor=t["zero"],
        ),
        yaxis=dict(title="%", range=[0, 100], **axis_common),
        yaxis2=dict(title="c/kWh", **axis_common),
        yaxis3=dict(title="kW", **axis_common),
        yaxis4=dict(title="kW", **axis_common),
        margin=dict(t=100, b=60, l=70, r=40),
        height=1100,
    )

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
    print(f"  [{THEMES.get(theme, THEMES['sharp'])['name']}] forecast saved: {output_path.resolve()}")
    return output_path
