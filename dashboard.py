"""
Dashboard - Weekly PnL drivers, risk exposure, forward curve scenarios
=========================================================================

Produces a single-page PNG dashboard (matplotlib) summarising:
  1. Price curve + optimal dispatch schedule (charge/discharge/SoC)
  2. Revenue stack breakdown (bar chart, by stream)
  3. Scenario comparison: revenue under bull / base / bear forward-curve
     assumptions (i.e. a simple stress test on price volatility)
  4. Key risk/performance metrics (equivalent cycles, EUR/MW/day, capture
     spread realised vs theoretical max)
"""

from __future__ import annotations

import datetime as datetime_module

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from battery_model import BatteryModel
from config import BatterySpec, MarketAssumptions
from data_fetcher import generate_synthetic_day_ahead_prices
from revenue_stacking import build_weekly_revenue_stack

plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["axes.facecolor"] = "white"


def run_scenario(prices: pd.Series, battery_spec: BatterySpec, market: MarketAssumptions, price_scale: float) -> dict:
    """Re-run the full revenue stack with prices scaled by `price_scale`,
    as a simple proxy for a bull/bear forward-curve volatility scenario.
    Scaling around the mean (not from zero) preserves the price *shape*
    while amplifying/dampening the spread available to arbitrage - which
    is what actually drives battery revenue, more than the price level
    itself.
    """
    mean_price = prices.mean()
    scaled_prices = mean_price + (prices - mean_price) * price_scale
    return build_weekly_revenue_stack(scaled_prices, battery_spec, market)


def build_dashboard(
    prices_df: pd.DataFrame,
    battery_spec: BatterySpec,
    market: MarketAssumptions,
    output_path: str,
    week_label: str = "",
) -> dict:
    result = build_weekly_revenue_stack(prices_df["price_eur_mwh"], battery_spec, market)
    schedule = result["schedule"]
    schedule["timestamp"] = prices_df["timestamp"].values

    # Scenarios: bear (low volatility / compressed spreads), base, bull (high volatility)
    scenarios = {
        "Bear (-40% spread)": run_scenario(prices_df["price_eur_mwh"], battery_spec, market, 0.6),
        "Base": result,
        "Bull (+40% spread)": run_scenario(prices_df["price_eur_mwh"], battery_spec, market, 1.4),
    }

    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(3, 2, height_ratios=[1.2, 1, 1], hspace=0.45, wspace=0.28)

    # --- Panel 1: price + dispatch schedule (spans full width) ---
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(schedule["timestamp"], schedule["price_eur_mwh"], color="#2b3a55", lw=1.3, label="Day-ahead price (EUR/MWh)")
    ax1.axhline(0, color="grey", lw=0.6, ls=":")
    ax1.set_ylabel("EUR/MWh")
    ax1.set_title(f"Price curve & optimal dispatch{' - ' + week_label if week_label else ''}", fontsize=12, fontweight="bold")

    ax1b = ax1.twinx()
    ax1b.fill_between(schedule["timestamp"], 0, schedule["charge_mw"], color="#c0392b", alpha=0.35, step="mid", label="Charge (MW)")
    ax1b.fill_between(schedule["timestamp"], 0, -schedule["discharge_mw"], color="#27ae60", alpha=0.35, step="mid", label="Discharge (MW)")
    ax1b.set_ylabel("MW (charge +/discharge -)")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1b.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8, ncol=3)

    # --- Panel 2: SoC trajectory ---
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.plot(schedule["timestamp"], schedule["soc_pct"] * 100, color="#8e44ad", lw=1.5)
    ax2.fill_between(schedule["timestamp"], 0, schedule["soc_pct"] * 100, color="#8e44ad", alpha=0.15)
    ax2.axhline(battery_spec.soc_min_pct * 100, color="grey", lw=0.7, ls="--")
    ax2.axhline(battery_spec.soc_max_pct * 100, color="grey", lw=0.7, ls="--")
    ax2.set_ylabel("State of charge (%)")
    ax2.set_title("SoC trajectory", fontsize=11, fontweight="bold")
    ax2.set_ylim(0, 100)
    ax2.tick_params(axis="x", labelrotation=45, labelsize=7)

    # --- Panel 3: revenue stack breakdown ---
    ax3 = fig.add_subplot(gs[1, 1])
    streams = ["Arbitrage", "FCR", "aFRR", "Peak\nshaving", "Congestion"]
    values = [result["arbitrage_eur"], result["fcr_eur"], result["afrr_eur"], result["peak_shaving_eur"], result["congestion_eur"]]
    colors = ["#2980b9", "#16a085", "#f39c12", "#8e44ad", "#c0392b"]
    bars = ax3.bar(streams, values, color=colors)
    ax3.set_ylabel("EUR")
    ax3.set_title("Revenue stack breakdown (base case)", fontsize=11, fontweight="bold")
    for bar, v in zip(bars, values):
        ax3.text(bar.get_x() + bar.get_width() / 2, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
    ax3.tick_params(axis="x", labelsize=8)

    # --- Panel 4: scenario comparison ---
    ax4 = fig.add_subplot(gs[2, 0])
    scenario_names = list(scenarios.keys())
    scenario_totals = [scenarios[s]["total_revenue_eur"] for s in scenario_names]
    bar_colors = ["#e67e22", "#2c3e50", "#27ae60"]
    bars4 = ax4.bar(scenario_names, scenario_totals, color=bar_colors)
    ax4.set_ylabel("Total revenue (EUR)")
    ax4.set_title("Forward-curve volatility scenarios", fontsize=11, fontweight="bold")
    for bar, v in zip(bars4, scenario_totals):
        ax4.text(bar.get_x() + bar.get_width() / 2, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=8)
    ax4.tick_params(axis="x", labelsize=8)

    # --- Panel 5: key metrics text box ---
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.axis("off")
    capture_spread = schedule.loc[schedule["discharge_mw"] > 0.01, "price_eur_mwh"].mean() - \
        schedule.loc[schedule["charge_mw"] > 0.01, "price_eur_mwh"].mean()
    theoretical_max_spread = schedule["price_eur_mwh"].max() - schedule["price_eur_mwh"].min()

    metrics_text = (
        f"KEY METRICS\n"
        f"{'-'*32}\n"
        f"Battery: {battery_spec.power_mw:.0f} MW / {battery_spec.energy_mwh:.0f} MWh "
        f"({battery_spec.energy_mwh/battery_spec.power_mw:.1f}h duration)\n"
        f"Round-trip efficiency: {battery_spec.round_trip_efficiency:.0%}\n\n"
        f"Total revenue (base case): EUR {result['total_revenue_eur']:,.0f}\n"
        f"EUR / MW / day: EUR {result['eur_per_mw_per_day']:.1f}\n"
        f"Equivalent full cycles: {result['equivalent_full_cycles']:.2f}\n\n"
        f"Avg realised capture spread: EUR {capture_spread:.1f}/MWh\n"
        f"Theoretical max spread (week): EUR {theoretical_max_spread:.1f}/MWh\n"
        f"Capture efficiency: {capture_spread/theoretical_max_spread:.0%} of single best spread\n\n"
        f"Bear -> Base -> Bull revenue swing: "
        f"EUR {scenarios['Bear (-40% spread)']['total_revenue_eur']:,.0f} -> "
        f"EUR {scenarios['Base']['total_revenue_eur']:,.0f} -> "
        f"EUR {scenarios['Bull (+40% spread)']['total_revenue_eur']:,.0f}"
    )
    ax5.text(0.02, 0.98, metrics_text, transform=ax5.transAxes, fontsize=9.5,
              verticalalignment="top", fontfamily="monospace",
              bbox=dict(boxstyle="round", facecolor="#f5f5f5", edgecolor="#cccccc"))

    fig.suptitle("Battery Storage Valuation & Revenue Optimization - Weekly Dashboard",
                 fontsize=14, fontweight="bold", y=0.995)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return {"result": result, "scenarios": scenarios}


if __name__ == "__main__":
    prices_df = generate_synthetic_day_ahead_prices(
        datetime_module.datetime(2026, 7, 6), n_days=7, negative_price_frequency=0.12
    )
    out = build_dashboard(
        prices_df, BatterySpec(), MarketAssumptions(),
        output_path="dashboard_demo.png", week_label="Week of 2026-07-06 (synthetic DE_LU-like prices)",
    )
    print("Dashboard saved.")
    print(f"Total weekly revenue (base case): EUR {out['result']['total_revenue_eur']:,.2f}")
