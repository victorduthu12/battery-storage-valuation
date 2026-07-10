"""
Battery Model - Physical representation of the storage asset
================================================================

Wraps the BatterySpec into a small set of helper methods used by the
optimizer to build its constraints, and by the dashboard to sanity-check
a proposed dispatch schedule (i.e. replay it and verify SoC never breaches
its bounds - a common bug source in these models).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import BatterySpec


class BatteryModel:
    def __init__(self, spec: BatterySpec):
        self.spec = spec

    @property
    def soc_min_mwh(self) -> float:
        return self.spec.soc_min_pct * self.spec.energy_mwh

    @property
    def soc_max_mwh(self) -> float:
        return self.spec.soc_max_pct * self.spec.energy_mwh

    @property
    def soc_start_mwh(self) -> float:
        return self.spec.soc_start_pct * self.spec.energy_mwh

    @property
    def usable_energy_mwh(self) -> float:
        """Energy actually usable given the DoD reserve (soc_max - soc_min)."""
        return self.soc_max_mwh - self.soc_min_mwh

    def replay_dispatch(self, charge_mw: np.ndarray, discharge_mw: np.ndarray, dt_hours: float = 1.0) -> pd.DataFrame:
        """Simulate the SoC trajectory resulting from a charge/discharge schedule.

        Used as a post-optimisation sanity check: re-derive SoC from the
        decision variables and confirm the physical constraints hold. This
        catches modelling bugs (e.g. a sign error) before they show up as a
        silently wrong PnL number.
        """
        n = len(charge_mw)
        soc = np.zeros(n + 1)
        soc[0] = self.soc_start_mwh

        for t in range(n):
            energy_in = charge_mw[t] * self.spec.charge_efficiency * dt_hours
            energy_out = discharge_mw[t] / self.spec.discharge_efficiency * dt_hours
            soc[t + 1] = soc[t] + energy_in - energy_out

        soc_series = soc[1:]  # SoC at the END of each interval

        violations = (
            (soc_series < self.soc_min_mwh - 1e-6).sum()
            + (soc_series > self.soc_max_mwh + 1e-6).sum()
        )
        if violations > 0:
            raise ValueError(
                f"SoC constraint violated in {violations} interval(s) - "
                "check the optimizer's SoC bounds."
            )

        return pd.DataFrame(
            {
                "charge_mw": charge_mw,
                "discharge_mw": discharge_mw,
                "soc_mwh": soc_series,
                "soc_pct": soc_series / self.spec.energy_mwh,
            }
        )

    def throughput_mwh(self, charge_mw: np.ndarray, discharge_mw: np.ndarray, dt_hours: float = 1.0) -> float:
        """Total energy cycled through the battery (used for degradation cost)."""
        return float((charge_mw.sum() + discharge_mw.sum()) * dt_hours)

    def equivalent_full_cycles(self, charge_mw: np.ndarray, dt_hours: float = 1.0) -> float:
        """Number of equivalent full charge cycles over the period - a key
        metric to sanity-check against the battery's rated cycle life
        (e.g. LFP cells: ~3,000-6,000 cycles to 80% capacity)."""
        energy_charged = charge_mw.sum() * dt_hours
        return energy_charged / self.spec.energy_mwh


if __name__ == "__main__":
    spec = BatterySpec()
    model = BatteryModel(spec)
    print(f"Usable energy: {model.usable_energy_mwh:.1f} MWh")
    print(f"C-rate: {spec.c_rate:.2f}")
    print(f"Charge / discharge efficiency: {spec.charge_efficiency:.3f} / {spec.discharge_efficiency:.3f}")
