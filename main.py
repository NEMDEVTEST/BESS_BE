"""
BESS Dashboard
--------------
Fetches the last 30 days of data from Amber Electric and Fox ESS,
then renders an interactive Plotly dashboard as a standalone HTML file.

Usage:
    python main.py [--days N] [--out PATH]

Environment (set in .env):
    AMBER_API_TOKEN   Amber Electric personal access key
    FOXESS_API_KEY    Fox ESS Cloud API key
"""

from __future__ import annotations

import argparse
import os
import webbrowser
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from amber import AmberClient, build_dashboard
from foxess import FoxESSClient


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="BESS interactive dashboard")
    parser.add_argument("--days", type=int, default=30, help="Number of days to fetch (default: 30)")
    parser.add_argument("--out", type=str, default="output/dashboard.html", help="Output HTML path")
    args = parser.parse_args()

    amber_token = os.environ.get("AMBER_API_TOKEN")
    foxess_key = os.environ.get("FOXESS_API_KEY")

    if not amber_token:
        raise SystemExit("AMBER_API_TOKEN not set in .env")
    if not foxess_key:
        raise SystemExit("FOXESS_API_KEY not set in .env")

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days - 1)

    print()
    print("BESS Dashboard")
    print("-" * 40)
    print(f"Period : {start_date} to {end_date}  ({args.days} days)")
    print(f"Output : {args.out}")
    print()

    # ------------------------------------------------------------------
    # Amber Electric — price + grid import/export
    # ------------------------------------------------------------------
    print(">> Amber: getting site info ...")
    amber = AmberClient(api_token=amber_token)
    site_id = amber.get_site_id()

    print(f"\n>> Amber: fetching {args.days} days of usage ...")
    amber_df = amber.get_usage(site_id, start=start_date, end=end_date)

    print(f"\n  {len(amber_df) // 2:,} intervals  |  "
          f"import {amber_df[amber_df.channel_type == 'general']['kwh'].sum():.1f} kWh  |  "
          f"export {amber_df[amber_df.channel_type == 'feedIn']['kwh'].sum():.1f} kWh  |  "
          f"avg spot {amber_df[amber_df.channel_type == 'general']['spot_per_kwh'].mean():.2f} c/kWh")

    # ------------------------------------------------------------------
    # Fox ESS — home load, solar, battery, SoC
    # ------------------------------------------------------------------
    print(f"\n>> Fox ESS: getting device info ...")
    fox = FoxESSClient(api_key=foxess_key)
    sn = fox.get_device_sn()

    print(f"\n>> Fox ESS: fetching {args.days} days of history ...")
    print("   (1 request/day, ~1 s apart — this takes about a minute for 30 days)")
    fox_df = fox.get_history(sn, start=start_date, end=end_date)

    print(f"\n  {len(fox_df):,} readings  |  "
          f"avg load {fox_df['loadsPower'].mean():.2f} kW  |  "
          f"avg gen load {fox_df['meterPower2'].mean():.2f} kW  |  "
          f"avg SoC {fox_df['SoC'].mean():.1f}%")

    # ------------------------------------------------------------------
    # Build dashboard
    # ------------------------------------------------------------------
    print("\n>> Building dashboard ...")
    out_path = build_dashboard(amber_df, fox_df, output_path=args.out, theme="sharp")

    print("\n>> Opening in browser ...")
    webbrowser.open(out_path.resolve().as_uri())
    print("\nDone.\n")


if __name__ == "__main__":
    main()
