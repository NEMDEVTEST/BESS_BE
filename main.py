"""
BESS Dashboard
--------------
Fetches data from Amber Electric and Fox ESS, caches in PostgreSQL,
and renders an interactive Plotly dashboard as a standalone HTML file.

Usage:
    python main.py [--start DATE] [--end DATE] [--update] [--no-open] [--out PATH]

Examples:
    python main.py --update                              # update DB, dashboard last 30d
    python main.py --start 2026-02-01 --end 2026-02-15   # query range from DB only
    python main.py --update --start 2026-02-01            # update then show from Feb 1
    python main.py                                        # DB-only, last 30 days

Environment (set in .env):
    AMBER_API_TOKEN      Amber Electric personal access key
    FOXESS_API_KEY       Fox ESS Cloud API key
    DATABASE_URL         PostgreSQL connection string
    SOLCAST_API_KEY      Solcast rooftop API key
    SOLCAST_RESOURCE_ID  Solcast site resource ID
"""

from __future__ import annotations

import argparse
import os
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

import cache
from amber import AmberClient, build_dashboard, build_forecast_dashboard
from foxess import FoxESSClient
from solcast import SolcastClient


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="BESS interactive dashboard")
    parser.add_argument("--start", type=date.fromisoformat, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=date.fromisoformat, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--update", action="store_true", help="Fetch latest data from APIs before querying")
    parser.add_argument("--no-open", action="store_true", help="Skip opening browser (for headless/scheduled runs)")
    parser.add_argument("--out", type=str, default="docs/index.html", help="Output HTML path")
    args = parser.parse_args()

    amber_token = os.environ.get("AMBER_API_TOKEN")
    foxess_key = os.environ.get("FOXESS_API_KEY")
    solcast_key = os.environ.get("SOLCAST_API_KEY")
    solcast_rid = os.environ.get("SOLCAST_RESOURCE_ID")

    if not amber_token:
        raise SystemExit("AMBER_API_TOKEN not set in .env")
    if not foxess_key:
        raise SystemExit("FOXESS_API_KEY not set in .env")

    today = date.today()
    start_date = args.start if args.start else today - timedelta(days=29)
    end_date = args.end if args.end else today
    days = (end_date - start_date).days + 1

    print()
    print("BESS Dashboard")
    print("-" * 40)
    print(f"Period : {start_date} to {end_date}  ({days} days)")
    print(f"Update : {'yes' if args.update else 'no (DB only)'}")
    print(f"Output : {args.out}")
    print()

    amber = AmberClient(api_token=amber_token)
    site_id = None

    # ------------------------------------------------------------------
    # Update: fetch missing data from APIs and write to DB
    # ------------------------------------------------------------------
    if args.update:
        # --- Amber ---
        print(">> Amber: getting site info ...")
        site_id = amber.get_site_id()

        latest = cache.latest_dt("amber")
        fetch_start = latest.date() if latest else start_date
        print(f"\n>> Amber: fetching {fetch_start} to {today} ...")
        amber_df = amber.fetch(site_id, start=fetch_start, end=today)
        cache.save_bulk("amber", amber_df)
        print(f"  Saved {len(amber_df)} rows to DB")

        # --- Fox ESS ---
        print(f"\n>> Fox ESS: getting device info ...")
        fox = FoxESSClient(api_key=foxess_key)
        sn = fox.get_device_sn()

        latest = cache.latest_dt("foxess")
        fetch_start = latest.date() if latest else start_date
        print(f"\n>> Fox ESS: fetching {fetch_start} to {today} ...")
        print("   (1 request/day, ~1 s apart — this may take a while)")
        fox_df = fox.fetch(sn, start=fetch_start, end=today)
        cache.save_bulk("foxess", fox_df)
        print(f"  Saved {len(fox_df)} rows to DB")

        # --- Amber price forecast ---
        print("\n>> Amber: fetching price forecast ...")
        if site_id is None:
            site_id = amber.get_site_id()
        price_fc = amber.fetch_price_forecast(site_id)
        cache.save_forecast("amber", price_fc)
        print(f"  Saved {len(price_fc)} forecast intervals")

        # --- Solcast solar forecast ---
        if solcast_key and solcast_rid:
            print("\n>> Solcast: fetching solar forecast ...")
            solcast = SolcastClient(api_key=solcast_key, resource_id=solcast_rid)
            solar_fc = solcast.fetch_forecasts(hours=48)
            cache.save_forecast("solcast", solar_fc)
            print(f"  Saved {len(solar_fc)} forecast intervals")
        else:
            print("\n>> Solcast: skipped (SOLCAST_API_KEY / SOLCAST_RESOURCE_ID not set)")

    # ------------------------------------------------------------------
    # Query: load full range from DB
    # ------------------------------------------------------------------
    print(f"\n>> Loading {start_date} to {end_date} from DB ...")
    df = cache.load(start_date, end_date)
    print(f"  {len(df)} rows loaded")

    if df.empty:
        raise SystemExit(
            "No data in DB for this range. Run with --update to fetch from APIs first."
        )

    # ------------------------------------------------------------------
    # Build main dashboard
    # ------------------------------------------------------------------
    print("\n>> Building dashboard ...")
    out_path = build_dashboard(df, output_path=args.out, theme="sharp")

    # ------------------------------------------------------------------
    # Build forecast dashboard
    # ------------------------------------------------------------------
    print("\n>> Building forecast dashboard ...")
    yesterday = datetime.now() - timedelta(hours=24)
    actuals_24h = cache.load(yesterday.date(), today)

    price_fc = cache.load_latest_forecast("amber")
    solar_fc = cache.load_latest_forecast("solcast")

    forecast_path = build_forecast_dashboard(
        actuals=actuals_24h,
        price_forecast=price_fc,
        solar_forecast=solar_fc,
        output_path="docs/forecast.html",
        theme="sharp",
    )

    if not args.no_open:
        print("\n>> Opening in browser ...")
        webbrowser.open(out_path.resolve().as_uri())
    print("\nDone.\n")


if __name__ == "__main__":
    main()
