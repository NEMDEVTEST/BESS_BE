"""Solcast API client — rooftop PV forecasts."""

from __future__ import annotations

import pandas as pd
import requests


BASE_URL = "https://api.solcast.com.au"


class SolcastClient:
    """Thin wrapper around the Solcast rooftop API (free tier)."""

    def __init__(self, api_key: str, resource_id: str) -> None:
        self.resource_id = resource_id
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def fetch_forecasts(self, hours: int = 48) -> pd.DataFrame:
        """Fetch PV power forecasts.

        Returns DataFrame with columns (naive Brisbane time):
            dt, pv_estimate, pv_estimate10, pv_estimate90
        All values in kW.
        """
        url = f"{BASE_URL}/rooftop_sites/{self.resource_id}/forecasts"
        resp = self.session.get(url, params={"format": "json", "hours": hours}, timeout=30)
        resp.raise_for_status()
        data = resp.json()["forecasts"]
        return _parse_forecasts(data)

    def fetch_estimated_actuals(self, hours: int = 48) -> pd.DataFrame:
        """Fetch estimated actuals (recent past).

        Returns DataFrame with columns (naive Brisbane time):
            dt, pv_estimate, pv_estimate10, pv_estimate90
        """
        url = f"{BASE_URL}/rooftop_sites/{self.resource_id}/estimated_actuals"
        resp = self.session.get(url, params={"format": "json", "hours": hours}, timeout=30)
        resp.raise_for_status()
        data = resp.json()["estimated_actuals"]
        return _parse_forecasts(data)


def _parse_forecasts(records: list[dict]) -> pd.DataFrame:
    """Parse Solcast forecast/estimated_actuals into a DataFrame."""
    from zoneinfo import ZoneInfo
    brisbane = ZoneInfo("Australia/Brisbane")

    rows = []
    for r in records:
        dt = pd.Timestamp(r["period_end"], tz="UTC").tz_convert(brisbane).tz_localize(None)
        rows.append({
            "dt": dt,
            "pv_estimate": r["pv_estimate"],
            "pv_estimate10": r["pv_estimate10"],
            "pv_estimate90": r["pv_estimate90"],
        })

    df = pd.DataFrame(rows)
    return df.sort_values("dt").reset_index(drop=True)
