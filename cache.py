"""PostgreSQL cache — single 'energy' table in home_db."""

from __future__ import annotations

import os
from datetime import date, datetime

import pandas as pd
from sqlalchemy import create_engine, text

# Source → columns each source owns
_SOURCE_COLS: dict[str, list[str]] = {
    "amber":  ["grid_export", "grid_import", "price"],
    "foxess": ["home_load", "solar", "soc"],
}

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        url = os.environ["DATABASE_URL"]
        _engine = create_engine(url)
        _ensure_table(_engine)
    return _engine


def _ensure_table(engine) -> None:
    ddl = text("""
        CREATE TABLE IF NOT EXISTS energy (
            dt              TIMESTAMP PRIMARY KEY,
            grid_export     DOUBLE PRECISION,
            grid_import     DOUBLE PRECISION,
            price           DOUBLE PRECISION,
            home_load       DOUBLE PRECISION,
            solar           DOUBLE PRECISION,
            soc             DOUBLE PRECISION,
            uploaded_at     TIMESTAMP DEFAULT NOW()
        )
    """)
    with engine.begin() as conn:
        conn.execute(ddl)


def load(start: date, end: date) -> pd.DataFrame:
    """Return all energy rows between start midnight and end 23:59:59."""
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, 999999)

    query = text(
        "SELECT dt, grid_export, grid_import, price, home_load, solar, soc "
        "FROM energy WHERE dt BETWEEN :start AND :end ORDER BY dt"
    )
    df = pd.read_sql(query, _get_engine(), params={"start": start_dt, "end": end_dt})
    if not df.empty:
        df["dt"] = pd.to_datetime(df["dt"])
    return df


def save_bulk(source: str, df: pd.DataFrame) -> None:
    """Upsert an entire DataFrame for *source*. Only touches source's own columns."""
    if df.empty:
        return

    cols = _SOURCE_COLS[source]
    # Keep only dt + source columns that exist in the DataFrame
    keep = ["dt"] + [c for c in cols if c in df.columns]
    insert_df = df[keep].copy()

    # Build the parameterised upsert SQL
    col_names = [c for c in cols if c in insert_df.columns]
    placeholders = ", ".join(f":{c}" for c in ["dt"] + col_names)
    col_list = ", ".join(["dt"] + col_names)
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in col_names)

    sql = text(
        f"INSERT INTO energy ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT (dt) DO UPDATE SET {set_clause}"
    )

    # Build list of param dicts for executemany
    rows = []
    for _, row in insert_df.iterrows():
        params = {"dt": row["dt"]}
        for c in col_names:
            val = row[c]
            params[c] = None if pd.isna(val) else float(val)
        rows.append(params)

    with _get_engine().begin() as conn:
        conn.execute(sql, rows)


def latest_dt(source: str) -> datetime | None:
    """Return the latest timestamp that has non-NULL data for *source*."""
    cols = _SOURCE_COLS[source]
    where = " OR ".join(f"{c} IS NOT NULL" for c in cols)
    sql = text(f"SELECT MAX(dt) AS latest FROM energy WHERE {where}")
    with _get_engine().connect() as conn:
        result = conn.execute(sql).fetchone()
    if result and result[0] is not None:
        val = result[0]
        if isinstance(val, str):
            return datetime.fromisoformat(val)
        return val
    return None
