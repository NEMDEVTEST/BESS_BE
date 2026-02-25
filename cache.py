"""Simple file-based parquet cache — one file per source per day."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

CACHE_DIR = Path("cache")


def load(source: str, day: date) -> pd.DataFrame | None:
    """Return cached DataFrame for *source* on *day*, or None if not cached."""
    p = _path(source, day)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        p.unlink(missing_ok=True)   # corrupt file — delete and re-fetch
        return None


def save(source: str, day: date, df: pd.DataFrame) -> None:
    """Persist *df* to the cache. No-ops on empty DataFrames."""
    if df.empty:
        return
    p = _path(source, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)


def is_cached(source: str, day: date) -> bool:
    return _path(source, day).exists()


def _path(source: str, day: date) -> Path:
    return CACHE_DIR / source / f"{day}.parquet"
