"""
Optimizer - Linear Programming battery arbitrage scheduler
==============================================================

Formulates the "optimal charge/discharge scheduling" problem as a Linear
Program and solves it with PuLP (CBC solver, open-source).

Decision variables (per time step t):
    c_t  >= 0   power charged   (MW)
    d_t  >= 0   power discharged (MW)
    soc_t       state of charge (MWh)

Objective (maximise):
    sum_t [ price_t * d_t * dt        <- revenue from discharging/selling
          - price_t * c_t * dt        <- cost of charging/buying
          - degradation_cost * (c_t + d_t) * dt   <- wear cost, discourages
                                                       micro-cycling on noise
          ]

Subject to:
    0 <= c_t <= P_max_charge          (charge power limit, net of reserved capacity)
    0 <= d_t <= P_max_discharge       (discharge power limit, net of reserved capacity)
    soc_{t+1} = soc_t + c_t * eta_charge * dt - d_t / eta_discharge * dt
    soc_min <= soc_t <= soc_max
    soc_0 = soc_start
    (optional) soc_end = soc_start    (cyclic constraint, so the battery
                                        doesn't "borrow" energy at the end
                                        of the optimisation window)

This is a standard formulation used in practice for day-ahead battery
scheduling (the real-world nuance - degradation cost, reserved capacity for
ancillary services, cyclic SoC constraint - is what separates a toy model
from something that resembles an actual trading desk tool).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pulp

from battery_model import BatteryModel
from config import BatterySpec


def optimize_arbitrage_schedule(
    prices: pd.Series,
    battery: BatteryModel,
    dt_hours: float = 1.0,
    reserved_power_share: float = 0.0,
    enforce_cyclic_soc: bool = True,
) -> pd.DataFrame:
    """Solve the optimal charge/discharge schedule that maximises arbitrage
    profit given a day-ahead price forecast/series.

    Parameters
    ----------
    prices : pd.Series
        Hourly (or `dt_hours`-spaced) day-ahead prices in EUR/MWh, indexed
        0..n-1.
    battery : BatteryModel
    dt_hours : float
        Length of each time step in hours.
    reserved_power_share : float
        Fraction of the battery's power capacity held back for ancillary
        services (FCR/aFRR) and therefore NOT available for arbitrage.
        This is how the model captures the real trade-off a trading desk
        faces: capacity used for reserves cannot simultaneously arbitrage.
    enforce_cyclic_soc : bool
        If True, force the SoC at the end of the window to equal the SoC
        at the start (avoids the optimiser "spending down" the battery for
        free at the edge of the optimisation horizon).

    Returns
    -------
    pd.DataFrame with columns ['price_eur_mwh', 'charge_mw', 'discharge_mw',
    'soc_mwh', 'soc_pct', 'net_position_mw']
    """
    n = len(prices)
    spec = battery.spec

    p_max = spec.power_mw * (1 - reserved_power_share)
    soc_min, soc_max = battery.soc_min_mwh, battery.soc_max_mwh
    soc_start = battery.soc_start_mwh
    deg_cost = spec.degradation_cost_eur_per_mwh_throughput

    prob = pulp.LpProblem("battery_arbitrage", pulp.LpMaximize)

    charge = pulp.LpVariable.dicts("charge", range(n), lowBound=0, upBound=p_max)
    discharge = pulp.LpVariable.dicts("discharge", range(n), lowBound=0, upBound=p_max)
    soc = pulp.LpVariable.dicts("soc", range(n + 1), lowBound=soc_min, upBound=soc_max)

    # Objective: arbitrage revenue net of degradation wear cost
    prob += pulp.lpSum(
        prices.iloc[t] * discharge[t] * dt_hours
        - prices.iloc[t] * charge[t] * dt_hours
        - deg_cost * (charge[t] + discharge[t]) * dt_hours
        for t in range(n)
    )

    # SoC dynamics
    prob += soc[0] == soc_start
    for t in range(n):
        prob += (
            soc[t + 1]
            == soc[t]
            + charge[t] * spec.charge_efficiency * dt_hours
            - discharge[t] / spec.discharge_efficiency * dt_hours
        )

    if enforce_cyclic_soc:
        prob += soc[n] == soc_start

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if pulp.LpStatus[prob.status] != "Optimal":
        raise RuntimeError(f"Optimizer did not converge: status={pulp.LpStatus[prob.status]}")

    charge_arr = np.array([charge[t].value() for t in range(n)])
    discharge_arr = np.array([discharge[t].value() for t in range(n)])
    soc_arr = np.array([soc[t + 1].value() for t in range(n)])

    result = pd.DataFrame(
        {
            "price_eur_mwh": prices.values,
            "charge_mw": charge_arr,
            "discharge_mw": discharge_arr,
            "soc_mwh": soc_arr,
            "soc_pct": soc_arr / spec.energy_mwh,
            "net_position_mw": discharge_arr - charge_arr,
        }
    )
    return result


def arbitrage_pnl(schedule: pd.DataFrame, dt_hours: float = 1.0) -> float:
    """Gross arbitrage PnL (revenue from discharge minus cost of charge)."""
    revenue = (schedule["price_eur_mwh"] * schedule["discharge_mw"] * dt_hours).sum()
    cost = (schedule["price_eur_mwh"] * schedule["charge_mw"] * dt_hours).sum()
    return float(revenue - cost)


if __name__ == "__main__":
    import datetime as datetime_module

    from data_fetcher import generate_synthetic_day_ahead_prices

    battery = BatteryModel(BatterySpec())
    prices_df = generate_synthetic_day_ahead_prices(
        datetime_module.datetime(2026, 7, 6), n_days=1, negative_price_frequency=0.3
    )
    schedule = optimize_arbitrage_schedule(prices_df["price_eur_mwh"], battery)
    print(schedule.round(2))
    print(f"\nGross arbitrage PnL (1 day): EUR {arbitrage_pnl(schedule):.2f}")
