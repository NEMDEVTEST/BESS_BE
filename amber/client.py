"""Amber Electric API client."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd
import requests

import cache as _cache

BASE_URL = "https://api.amber.com.au/v1"


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

    def get_usage(
        self,
        site_id: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """
        Fetch usage for every channel between *start* and *end* (inclusive).
        Past days are served from the local parquet cache; only missing or
        today's data is fetched from the API.

        Returns a DataFrame with columns:
            time            datetime64[ns, Australia/Sydney]
            channel_type    'general' | 'feedIn'
            channel_id      'E1' | 'B1'
            kwh             float
            spot_per_kwh    float   (c/kWh, wholesale spot)
            per_kwh         float   (c/kWh, Amber all-in tariff)
            cost            float   (cents)
            descriptor      str
        """
        today = date.today()
        frames: list[pd.DataFrame] = []
        cursor = start

        while cursor <= end:
            cached = _cache.load("amber", cursor)
            if cached is not None and cursor < today:
                print(f"  Amber {cursor} ... cached ({len(cached)} rows)")
                frames.append(cached)
            else:
                print(f"  Amber {cursor} ... fetching", end=" ")
                raw = self._get(
                    f"/sites/{site_id}/usage",
                    params={"startDate": str(cursor), "endDate": str(cursor)},
                )
                df = self._parse_usage(raw)
                print(f"({len(df)} rows)")
                if cursor < today:
                    _cache.save("amber", cursor, df)
                frames.append(df)
                time.sleep(0.2)

            cursor += timedelta(days=1)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> list:
        url = BASE_URL + path
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _parse_usage(records: list[dict]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame()

        rows = []
        for r in records:
            rows.append(
                {
                    "time": r["nemTime"],
                    "channel_type": r["channelType"],
                    "channel_id": r["channelIdentifier"],
                    "kwh": float(r["kwh"]),
                    "spot_per_kwh": float(r.get("spotPerKwh", 0)),
                    "per_kwh": float(r.get("perKwh", 0)),
                    "cost": float(r.get("cost", 0)),
                    "descriptor": r.get("descriptor", ""),
                }
            )

        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert(
            "Australia/Sydney"
        )
        df = df.sort_values("time").reset_index(drop=True)
        return df
