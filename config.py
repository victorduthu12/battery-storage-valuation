"""
Configuration - Battery Storage Valuation & Revenue Optimization Model
=======================================================================

All physical and market parameters used across the project are centralised
here so that a scenario can be changed in one place.
"""

from dataclasses import dataclass


@dataclass
class BatterySpec:
    """Physical specification of the battery asset (front-of-meter, grid-scale)."""

    power_mw: float = 10.0          # Max charge/discharge power (MW)
    energy_mwh: float = 20.0        # Nominal energy capacity (MWh) -> 2h duration
    round_trip_efficiency: float = 0.90   # AC-AC round-trip efficiency
    soc_min_pct: float = 0.10       # Min state of charge (protects battery, DoD reserve)
    soc_max_pct: float = 0.95       # Max state of charge
    soc_start_pct: float = 0.50     # SoC at the start of the optimisation window
    degradation_cost_eur_per_mwh_throughput: float = 4.0
    # ^ Approximate marginal cost of cycling (capex amortised over cycle life).
    #   Used to avoid the optimiser "cycling for pennies" on tiny spreads.

    @property
    def c_rate(self) -> float:
        return self.power_mw / self.energy_mwh

    @property
    def charge_efficiency(self) -> float:
        # Split round-trip efficiency symmetrically between charge and discharge legs
        return self.round_trip_efficiency ** 0.5

    @property
    def discharge_efficiency(self) -> float:
        return self.round_trip_efficiency ** 0.5


@dataclass
class MarketAssumptions:
    """Simplified market parameters for the reserve/ancillary revenue streams.

    Real FCR/aFRR clearing prices come from TenderRegister / regelleistung.net
    (Germany) or the relevant TSO auction platform per country. Here they are
    modelled as user-editable average price bands so the tool is usable even
    without a live auction-data feed, and can be swapped for real historical
    clearing prices later.
    """

    fcr_price_eur_per_mw_h: float = 12.0     # average FCR capacity price
    afrr_price_eur_per_mw_h: float = 6.0     # average aFRR capacity price
    reserved_power_share_fcr: float = 0.15   # share of power capacity reserved for FCR
    reserved_power_share_afrr: float = 0.15  # share of power capacity reserved for aFRR
    congestion_event_price_eur_per_mwh: float = 40.0  # extra premium during congestion hours
    peak_shaving_avoided_cost_eur_per_mw_month: float = 3500.0  # avoided grid demand charge

    co2_price_eur_per_t: float = 75.0        # EU ETS reference, used in fundamentals view


ENTSOE_DOMAIN_CODES = {
    # ENTSO-E Transparency Platform bidding zone EIC codes (subset, most-used)
    "DE_LU": "10Y1001A1001A82H",
    "FR": "10YFR-RTE------C",
    "ES": "10YES-REE------0",
    "IT_NORD": "10Y1001A1001A73I",
}
