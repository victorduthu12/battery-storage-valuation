"""
Revenue Stacking - combine arbitrage, reserve provision, peak shaving and
congestion management into a single weekly PnL breakdown
=============================================================================

This module reflects the real trade-off a battery portfolio manager faces:
power capacity reserved for FCR/aFRR cannot simultaneously be used for
arbitrage. The optimizer is therefore run on the REMAINING (non-reserved)
power capacity, and the reserve revenue is added on top as a separate,
largely price-independent revenue stream (capacity payment, not energy
payment).

Revenue streams modelled:
  1. Energy arbitrage        -> from optimizer.py (day-ahead spread capture)
  2. FCR capacity reservation -> EUR/MW/h * reserved MW * hours
  3. aFRR capacity reservation -> EUR/MW/h * reserved MW * hours
  4. Peak shaving              -> avoided monthly demand charge (EUR/MW/month),
                                   pro-rated to the analysis window
  5. Congestion management     -> extra premium captured during flagged
                                   congestion hours (on top of arbitrage)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from battery_model import BatteryModel
from config import BatterySpec, MarketAssumptions
from optimizer import arbitrage_pnl, optimize_arbitrage_schedule


def compute_reserve_revenue(
    battery: BatteryModel,
    market: MarketAssumptions,
    n_hours: int,
) -> dict:
    """FCR + aFRR capacity revenue over the analysis window."""
    p = battery.spec.power_mw

    fcr_mw = p * market.reserved_power_share_fcr
    afrr_mw = p * market.reserved_power_share_afrr

    fcr_revenue = fcr_mw * market.fcr_price_eur_per_mw_h * n_hours
    afrr_revenue = afrr_mw * market.afrr_price_eur_per_mw_h * n_hours

    return {
        "fcr_reserved_mw": fcr_mw,
        "afrr_reserved_mw": afrr_mw,
        "fcr_revenue_eur": fcr_revenue,
        "afrr_revenue_eur": afrr_revenue,
    }


def compute_peak_shaving_revenue(
    battery: BatteryModel,
    market: MarketAssumptions,
    n_hours: int,
    peak_shaving_power_share: float = 0.20,
) -> float:
    """Avoided demand-charge value, pro-rated to the length of the window.

    A share of the battery's power capacity is assumed reserved to shave
    the site/portfolio's monthly peak demand, avoiding a capacity-based
    grid tariff charge. This is common for co-located BESS + industrial
    load setups.
    """
    reserved_mw = battery.spec.power_mw * peak_shaving_power_share
    months_fraction = n_hours / (24 * 30)
    return reserved_mw * market.peak_shaving_avoided_cost_eur_per_mw_month * months_fraction


def compute_congestion_revenue(
    schedule: pd.DataFrame,
    market: MarketAssumptions,
    congestion_hours_mask: np.ndarray,
    dt_hours: float = 1.0,
) -> float:
    """Extra premium earned for discharging specifically during flagged
    grid-congestion hours (on top of the normal arbitrage revenue already
    counted for those hours).
    """
    discharge_in_congestion = schedule.loc[congestion_hours_mask, "discharge_mw"].sum() * dt_hours
    return float(discharge_in_congestion * market.congestion_event_price_eur_per_mwh)


def build_weekly_revenue_stack(
    prices: pd.Series,
    battery_spec: BatterySpec,
    market: MarketAssumptions,
    congestion_hours_mask: np.ndarray | None = None,
    dt_hours: float = 1.0,
) -> dict:
    """Run the full pipeline and return a structured revenue-stack summary
    for a given price series (typically one week of hourly prices).
    """
    battery = BatteryModel(battery_spec)
    n_hours = len(prices)

    reserved_share = market.reserved_power_share_fcr + market.reserved_power_share_afrr

    schedule = optimize_arbitrage_schedule(
        prices, battery, dt_hours=dt_hours, reserved_power_share=reserved_share
    )

    arb_pnl = arbitrage_pnl(schedule, dt_hours=dt_hours)
    reserves = compute_reserve_revenue(battery, market, n_hours)
    peak_shaving = compute_peak_shaving_revenue(battery, market, n_hours)

    if congestion_hours_mask is None:
        congestion_hours_mask = np.zeros(n_hours, dtype=bool)
    congestion_revenue = compute_congestion_revenue(schedule, market, congestion_hours_mask, dt_hours)

    total_revenue = (
        arb_pnl
        + reserves["fcr_revenue_eur"]
        + reserves["afrr_revenue_eur"]
        + peak_shaving
        + congestion_revenue
    )

    equivalent_cycles = battery.equivalent_full_cycles(schedule["charge_mw"].values, dt_hours)

    return {
        "schedule": schedule,
        "arbitrage_eur": arb_pnl,
        "fcr_eur": reserves["fcr_revenue_eur"],
        "afrr_eur": reserves["afrr_revenue_eur"],
        "peak_shaving_eur": peak_shaving,
        "congestion_eur": congestion_revenue,
        "total_revenue_eur": total_revenue,
        "equivalent_full_cycles": equivalent_cycles,
        "eur_per_mw_per_day": total_revenue / battery_spec.power_mw / (n_hours / 24),
    }


if __name__ == "__main__":
    import datetime as datetime_module

    from data_fetcher import generate_synthetic_day_ahead_prices

    prices_df = generate_synthetic_day_ahead_prices(
        datetime_module.datetime(2026, 7, 6), n_days=7, negative_price_frequency=0.12
    )
    result = build_weekly_revenue_stack(
        prices_df["price_eur_mwh"], BatterySpec(), MarketAssumptions()
    )

    print("=== Weekly Revenue Stack ===")
    for key in ["arbitrage_eur", "fcr_eur", "afrr_eur", "peak_shaving_eur", "congestion_eur", "total_revenue_eur"]:
        print(f"{key:22s}: EUR {result[key]:>10,.2f}")
    print(f"{'equivalent cycles':22s}: {result['equivalent_full_cycles']:.2f}")
    print(f"{'EUR / MW / day':22s}: EUR {result['eur_per_mw_per_day']:.2f}")
