"""Fox ESS Cloud API client."""

from __future__ import annotations

import hashlib
import time as time_module
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

BASE_URL = "https://www.foxesscloud.com"

# Variables to fetch from Fox ESS history endpoint
HISTORY_VARIABLES = [
    "loadsPower",        # home load (kW)
    "meterPower2",       # AC-coupled solar / Gen Load (kW) — CT meter 2
    "batChargePower",    # battery charging (kW)
    "batDischargePower", # battery discharging (kW)
    "gridConsumptionPower",  # grid import (kW)
    "feedinPower",       # grid export (kW)
    "SoC",               # battery state of charge (%)
]


class FoxESSClient:
    """Client for the Fox ESS Cloud Open API (v0)."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BESS-Dashboard/1.0",
        })

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_device_sn(self) -> str:
        """Return the serial number of the first inverter on the account."""
        payload = {"currentPage": 1, "pageSize": 10}
        data = self._post("/op/v0/device/list", payload)
        # Result can be a list directly, or a dict with a devices/deviceList key
        if isinstance(data, list):
            devices = data
        elif isinstance(data, dict):
            devices = (
                data.get("devices")
                or data.get("deviceList")
                or data.get("data")
                or data.get("list")
                or []
            )
        else:
            devices = []
        if not devices:
            raise RuntimeError(
                f"No devices found on Fox ESS account. Raw response: {data}"
            )
        sn = devices[0]["deviceSN"]
        model = devices[0].get("deviceType", "unknown")
        print(f"  Fox ESS device: {model}  SN: {sn}")
        return sn

    def fetch(
        self,
        sn: str,
        start: date,
        end: date,
        variables: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Fetch historical data for *sn* between *start* and *end* (inclusive).
        Loops day-by-day (API rate limit). No cache logic — pure API fetch.

        Returns a DataFrame with columns (naive Brisbane time):
            dt          datetime64[ns]  (Brisbane UTC+10, no tz)
            home_load   float  kW
            solar       float  kW
            soc         float  %
        """
        if variables is None:
            variables = HISTORY_VARIABLES

        all_frames: list[pd.DataFrame] = []
        cursor = start
        while cursor <= end:
            print(f"  Fox ESS {cursor} ...", end=" ")
            begin_ms = _day_start_ms(cursor)
            end_ms = _day_end_ms(cursor)
            payload = {
                "sn": sn,
                "variables": variables,
                "begin": begin_ms,
                "end": end_ms,
            }
            try:
                data = self._post("/op/v0/device/history/query", payload)
                df = _parse_history(data, variables)
                df = _to_brisbane_naive(df)
                print(f"{len(df)} rows")
                if not df.empty:
                    all_frames.append(df)
            except Exception as exc:
                print(f"ERROR: {exc}")
            time_module.sleep(1.1)  # stay within 1 req/s limit
            cursor += timedelta(days=1)

        if not all_frames:
            return pd.DataFrame(columns=["dt", "home_load", "solar", "soc"])

        result = pd.concat(all_frames, ignore_index=True)
        result["dt"] = pd.to_datetime(result["dt"])
        result = result.sort_values("dt").reset_index(drop=True)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _headers(self, path: str) -> dict:
        timestamp = str(int(time_module.time() * 1000))
        # Signature uses literal \r\n (4 chars), not actual CRLF — raw f-string required
        raw = fr"{path}\r\n{self.api_key}\r\n{timestamp}"
        signature = hashlib.md5(raw.encode("UTF-8")).hexdigest()
        return {
            "Token": self.api_key,
            "Lang": "en",
            "Timestamp": timestamp,
            "Signature": signature,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        url = BASE_URL + path
        resp = self.session.post(
            url,
            json=payload,
            headers=self._headers(path),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        errno = body.get("errno", -1)
        if errno != 0:
            raise RuntimeError(
                f"Fox ESS API error {errno}: {body.get('msg', body)}"
            )
        return body.get("result", body)


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------

def _day_start_ms(d: date) -> int:
    """Midnight AEST/AEDT for the given date, as ms UTC timestamp."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Australia/Sydney")
    dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    return int(dt.timestamp() * 1000)


def _day_end_ms(d: date) -> int:
    """23:59:59 AEST/AEDT for the given date, as ms UTC timestamp."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Australia/Sydney")
    dt = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=tz)
    return int(dt.timestamp() * 1000)


# Column rename mapping: Fox ESS API name → database name
_RENAME = {
    "time": "dt",
    "loadsPower": "home_load",
    "meterPower2": "solar",
    "SoC": "soc",
}


def _to_brisbane_naive(df: pd.DataFrame) -> pd.DataFrame:
    """Convert tz-aware 'dt' column to naive Brisbane (UTC+10) time, rename cols."""
    if df.empty:
        return df

    # Rename columns
    df = df.rename(columns=_RENAME)

    # Keep only the columns we care about
    keep = [c for c in ["dt", "home_load", "solar", "soc"] if c in df.columns]
    df = df[keep].copy()

    # Convert to Brisbane (fixed UTC+10, no DST) then strip tz
    from zoneinfo import ZoneInfo
    brisbane = ZoneInfo("Australia/Brisbane")
    df["dt"] = pd.to_datetime(df["dt"], utc=True).dt.tz_convert(brisbane).dt.tz_localize(None)
    return df


def _parse_history(data: dict | list, variables: list[str]) -> pd.DataFrame:
    """
    Convert the raw Fox ESS history response into a tidy wide DataFrame.

    Response shape: result is a list with one item containing a 'datas' list.
    Each datas entry has: variable, unit, data=[{time: str, value: float}].
    Times are strings like '2026-02-23 00:02:38 AEDT+1100'.
    """
    import re

    # Unwrap outer list → dict with 'datas'
    if isinstance(data, list):
        if not data:
            return pd.DataFrame()
        data = data[0]

    series_list = data.get("datas", []) if isinstance(data, dict) else []
    if not series_list:
        return pd.DataFrame()

    frames: dict[str, pd.Series] = {}
    for series in series_list:
        var = series.get("variable", "")
        points = series.get("data", [])
        if not var or not points:
            continue

        times = [_parse_fox_time(p["time"]) for p in points]
        values = [p.get("value", float("nan")) for p in points]
        frames[var] = pd.Series(values, index=times, name=var)

    if not frames:
        return pd.DataFrame()

    df = pd.DataFrame(frames)
    df.index.name = "time"
    df = df.reset_index()
    # Ensure all requested variables are present (fill missing with NaN)
    for v in variables:
        if v not in df.columns:
            df[v] = float("nan")

    return df


def _parse_fox_time(s: str):
    """
    Parse Fox ESS time strings like '2026-02-23 00:02:38 AEDT+1100'.
    Strips the timezone abbreviation (AEDT/AEST) and uses the numeric offset.
    """
    import re
    # Remove timezone abbreviation before the +/- offset: 'AEDT+1100' -> '+1100'
    clean = re.sub(r"\s+[A-Z]{2,5}(?=[+-])", " ", s)
    return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S %z")
