"""
Main - Battery Storage Valuation & Revenue Optimization Model
==================================================================

Entry point. Two modes:

  python3 main.py                       -> demo mode, synthetic prices
  python3 main.py --entsoe TOKEN --zone DE_LU --start 2026-07-06

Outputs a weekly dashboard PNG and prints the revenue-stack summary to
the console.
"""

from __future__ import annotations

import argparse
import datetime as dt

from config import BatterySpec, MarketAssumptions
from dashboard import build_dashboard
from data_fetcher import fetch_day_ahead_prices_entsoe, generate_synthetic_day_ahead_prices


def parse_args():
    parser = argparse.ArgumentParser(description="Battery Storage Valuation & Revenue Optimization")
    parser.add_argument("--entsoe", type=str, default=None, help="ENTSO-E API security token (real data mode)")
    parser.add_argument("--zone", type=str, default="DE_LU", choices=["DE_LU", "FR", "ES", "IT_NORD"])
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD (defaults to 7 days ago)")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--power-mw", type=float, default=10.0)
    parser.add_argument("--energy-mwh", type=float, default=20.0)
    parser.add_argument("--output", type=str, default="dashboard_output.png")
    return parser.parse_args()


def main():
    args = parse_args()

    start = (
        dt.datetime.strptime(args.start, "%Y-%m-%d")
        if args.start
        else dt.datetime.utcnow() - dt.timedelta(days=args.days)
    )

    if args.entsoe:
        print(f"[main] Fetching REAL day-ahead prices from ENTSO-E for zone={args.zone} ...")
        end = start + dt.timedelta(days=args.days)
        prices_df = fetch_day_ahead_prices_entsoe(start, end, args.entsoe, bidding_zone=args.zone)
        week_label = f"{args.zone} - {start:%Y-%m-%d} to {end:%Y-%m-%d} (ENTSO-E real data)"
    else:
        print("[main] No ENTSO-E token provided -> using SYNTHETIC demo prices.")
        print("[main] Get a free token at https://transparency.entsoe.eu to run on real data.")
        prices_df = generate_synthetic_day_ahead_prices(start, n_days=args.days, negative_price_frequency=0.12)
        week_label = f"Synthetic demo prices - week of {start:%Y-%m-%d}"

    battery_spec = BatterySpec(power_mw=args.power_mw, energy_mwh=args.energy_mwh)
    market = MarketAssumptions()

    output = build_dashboard(prices_df, battery_spec, market, output_path=args.output, week_label=week_label)
    result = output["result"]

    print("\n=== WEEKLY REVENUE STACK SUMMARY ===")
    print(f"Battery: {battery_spec.power_mw:.0f} MW / {battery_spec.energy_mwh:.0f} MWh")
    print(f"  Arbitrage revenue     : EUR {result['arbitrage_eur']:>10,.2f}")
    print(f"  FCR revenue           : EUR {result['fcr_eur']:>10,.2f}")
    print(f"  aFRR revenue          : EUR {result['afrr_eur']:>10,.2f}")
    print(f"  Peak shaving          : EUR {result['peak_shaving_eur']:>10,.2f}")
    print(f"  Congestion management : EUR {result['congestion_eur']:>10,.2f}")
    print(f"  {'-'*40}")
    print(f"  TOTAL                 : EUR {result['total_revenue_eur']:>10,.2f}")
    print(f"  EUR/MW/day            : EUR {result['eur_per_mw_per_day']:>10,.2f}")
    print(f"  Equivalent cycles     : {result['equivalent_full_cycles']:.2f}")
    print(f"\nDashboard saved to: {args.output}")


if __name__ == "__main__":
    main()
