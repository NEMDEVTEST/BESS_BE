"""Amber Electric API client."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd
import requests

BASE_URL = "https://api.amber.com.au/v1"

# Amber kWh per 5-min → kW
_AMBER_FACTOR = 12.0


class AmberClient:
    """Thin wrapper around the Amber Electric REST API."""

    def __init__(self, api_token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_token}"})

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_site_id(self) -> str:
        """Return the first active site ID on the account."""
        sites = self._get("/sites")
        active = [s for s in sites if s.get("status") == "active"]
        if not active:
            raise RuntimeError("No active sites found on this Amber account.")
        site = active[0]
        print(f"  Site: NMI {site['nmi']} | Network: {site['network']} | ID: {site['id']}")
        return site["id"]

    def fetch(
        self,
        site_id: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """
        Fetch usage for every channel between *start* and *end* (inclusive).
        Loops day-by-day (API limitation). No cache logic — pure API fetch.

        Returns a DataFrame with columns (naive Brisbane time):
            dt              datetime64[ns]  (Brisbane UTC+10, no tz)
            grid_export     float  kW
            grid_import     float  kW
            price           float  c/kWh (spot)
        """
        frames: list[pd.DataFrame] = []
        cursor = start

        while cursor <= end:
            print(f"  Amber {cursor} ... fetching", end=" ")
            raw = self._get(
                f"/sites/{site_id}/usage",
                params={"startDate": str(cursor), "endDate": str(cursor)},
            )
            df = _parse_and_pivot(raw)
            print(f"({len(df)} rows)")
            frames.append(df)
            time.sleep(0.2)
            cursor += timedelta(days=1)

        # Drop empty frames to avoid FutureWarning on concat with all-NA columns
        frames = [f for f in frames if not f.empty]
        if not frames:
            return pd.DataFrame(columns=["dt", "grid_export", "grid_import", "price"])
        result = pd.concat(frames, ignore_index=True)
        result["dt"] = pd.to_datetime(result["dt"])
        result = result.sort_values("dt").reset_index(drop=True)
        return result

    def fetch_price_forecast(self, site_id: str, next_intervals: int = 48) -> pd.DataFrame:
        """Fetch current + forecast price intervals.

        Returns DataFrame with columns (naive Brisbane time):
            dt, price_forecast, price_low, price_high, channel_type, descriptor, renewables
        """
        raw = self._get(
            f"/sites/{site_id}/prices/current",
            params={"resolution": "30", "next": next_intervals},
        )
        return _parse_price_forecast(raw)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> list:
        url = BASE_URL + path
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()


def _parse_and_pivot(records: list[dict]) -> pd.DataFrame:
    """Parse raw Amber usage records, pivot channels into columns.

    Returns: dt, grid_export (kW), grid_import (kW), price (c/kWh spot).
    All timestamps are naive Brisbane (UTC+10).
    """
    if not records:
        return pd.DataFrame(columns=["dt", "grid_export", "grid_import", "price"])

    from zoneinfo import ZoneInfo
    brisbane = ZoneInfo("Australia/Brisbane")

    rows = []
    for r in records:
        rows.append({
            "time": r["nemTime"],
            "channel_type": r["channelType"],
            "kwh": float(r["kwh"]),
            "spot_per_kwh": float(r.get("spotPerKwh", 0)),
        })

    raw = pd.DataFrame(rows)
    raw["time"] = pd.to_datetime(raw["time"], utc=True).dt.tz_convert(brisbane).dt.tz_localize(None)

    general = raw[raw["channel_type"] == "general"].set_index("time")
    feedin = raw[raw["channel_type"] == "feedIn"].set_index("time")

    pivot = pd.DataFrame({
        "grid_import": general["kwh"] * _AMBER_FACTOR,
        "price": general["spot_per_kwh"],
    })

    if not feedin.empty:
        pivot["grid_export"] = feedin["kwh"] * _AMBER_FACTOR
    else:
        pivot["grid_export"] = float("nan")

    pivot = pivot.reset_index().rename(columns={"time": "dt"})
    pivot = pivot[["dt", "grid_export", "grid_import", "price"]]
    return pivot.sort_values("dt").reset_index(drop=True)


def _parse_price_forecast(records: list[dict]) -> pd.DataFrame:
    """Parse Amber current + forecast price intervals."""
    from zoneinfo import ZoneInfo
    brisbane = ZoneInfo("Australia/Brisbane")

    rows = []
    for r in records:
        if r.get("channelType") != "general":
            continue
        dt = pd.Timestamp(r["nemTime"]).tz_convert(brisbane).tz_localize(None)
        adv = r.get("advancedPrice", {})
        rows.append({
            "dt": dt,
            "type": r["type"],
            "price_forecast": float(r.get("spotPerKwh", 0)),
            "price_low": float(adv.get("low", r.get("spotPerKwh", 0))),
            "price_high": float(adv.get("high", r.get("spotPerKwh", 0))),
            "descriptor": r.get("descriptor", ""),
            "renewables": float(r.get("renewables", 0)),
        })

    df = pd.DataFrame(rows)
    return df.sort_values("dt").reset_index(drop=True)
