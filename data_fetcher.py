"""
Data Fetcher - Day-Ahead / Intraday Power Prices
==================================================

Two data sources are supported:

1. REAL DATA: ENTSO-E Transparency Platform (free, official EU source for
   day-ahead prices across all European bidding zones, including EPEX Spot
   auction results for DE/FR/ES/IT). Requires a free API token from
   https://transparency.entsoe.eu (register -> "Web API Security Token").

2. SYNTHETIC DATA: a realistic price-shape generator, used when no API token
   is available (e.g. for testing/demoing this tool offline). It reproduces
   the typical daily/weekly shape seen on EPEX Spot (morning + evening peaks,
   midday solar dip, occasional negative-price hours on windy/sunny days),
   calibrated loosely on 2026 Iberian/German price patterns.

Both paths return the same pandas DataFrame schema so the rest of the
pipeline (optimizer, revenue stacking, dashboard) never needs to know which
source was used.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests

from config import ENTSOE_DOMAIN_CODES

ENTSOE_BASE_URL = "https://web-api.tp.entsoe.eu/api"


def fetch_day_ahead_prices_entsoe(
    start: dt.datetime,
    end: dt.datetime,
    api_token: str,
    bidding_zone: str = "DE_LU",
) -> pd.DataFrame:
    """Fetch real day-ahead auction prices from the ENTSO-E Transparency Platform.

    Parameters
    ----------
    start, end : datetime
        UTC period to fetch. ENTSO-E expects periodStart/periodEnd as
        'YYYYMMDDHHMM'.
    api_token : str
        Personal ENTSO-E security token (free registration).
    bidding_zone : str
        Key into ENTSOE_DOMAIN_CODES (e.g. "DE_LU", "FR", "ES", "IT_NORD").

    Returns
    -------
    pd.DataFrame with columns ['timestamp', 'price_eur_mwh']

    Notes
    -----
    This function performs a real HTTP call to ENTSO-E and parses the
    official XML response (document type A44 = Day-ahead prices). It will
    raise if the token is invalid/missing or if ENTSO-E returns no data for
    the requested window (e.g. weekends/holidays with sparse coverage).
    """
    domain = ENTSOE_DOMAIN_CODES[bidding_zone]
    params = {
        "documentType": "A44",              # Day-ahead prices
        "in_Domain": domain,
        "out_Domain": domain,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
        "securityToken": api_token,
    }

    resp = requests.get(ENTSOE_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()

    return _parse_entsoe_price_xml(resp.text)


def _parse_entsoe_price_xml(xml_text: str) -> pd.DataFrame:
    """Parse ENTSO-E's Publication_MarketDocument XML into a flat price series."""
    ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
    root = ET.fromstring(xml_text)

    rows = []
    for ts in root.findall(".//ns:TimeSeries", ns):
        period = ts.find(".//ns:Period", ns)
        start_str = period.find("./ns:timeInterval/ns:start", ns).text
        resolution = period.find("./ns:resolution", ns).text
        step_minutes = 60 if resolution == "PT60M" else 15

        period_start = dt.datetime.strptime(start_str, "%Y-%m-%dT%H:%MZ")

        for point in period.findall("./ns:Point", ns):
            position = int(point.find("./ns:position", ns).text)
            price = float(point.find("./ns:price.amount", ns).text)
            timestamp = period_start + dt.timedelta(minutes=step_minutes * (position - 1))
            rows.append({"timestamp": timestamp, "price_eur_mwh": price})

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return df


def generate_synthetic_day_ahead_prices(
    start: dt.datetime,
    n_days: int = 7,
    base_price: float = 75.0,
    volatility_scale: float = 1.0,
    negative_price_frequency: float = 0.05,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Generate a realistic synthetic hourly day-ahead price series.

    The shape combines:
      - a smooth daily profile (morning + evening peaks, midday solar dip)
      - day-of-week effects (lower prices on weekends)
      - random noise scaled by `volatility_scale`
      - occasional negative-price hours around midday, at a frequency
        controlled by `negative_price_frequency` (mimics high solar/wind
        oversupply events, as seen increasingly in Spain/Germany in 2026)

    This is NOT real market data - it exists purely so the rest of the
    pipeline can be run, tested and demoed end-to-end without requiring a
    live ENTSO-E token.
    """
    rng = np.random.default_rng(seed)
    n_hours = n_days * 24
    timestamps = [start + dt.timedelta(hours=h) for h in range(n_hours)]

    prices = np.zeros(n_hours)
    for h, ts in enumerate(timestamps):
        hour_of_day = ts.hour
        is_weekend = ts.weekday() >= 5

        # Base daily shape: two peaks (08-10h, 18-21h), a solar-driven midday dip
        morning_peak = 18 * np.exp(-((hour_of_day - 8.5) ** 2) / (2 * 2.0 ** 2))
        evening_peak = 25 * np.exp(-((hour_of_day - 19.5) ** 2) / (2 * 2.2 ** 2))
        solar_dip = -22 * np.exp(-((hour_of_day - 13.0) ** 2) / (2 * 3.0 ** 2))
        night_floor = -8 if 1 <= hour_of_day <= 5 else 0

        weekend_discount = -12 if is_weekend else 0

        seasonal_noise = rng.normal(0, 6 * volatility_scale)

        price = (
            base_price
            + morning_peak
            + evening_peak
            + solar_dip
            + night_floor
            + weekend_discount
            + seasonal_noise
        )

        # Occasional deep negative-price event (oversupply hours, typically
        # midday on sunny/windy days) - mirrors the Iberian 2026 pattern
        if 11 <= hour_of_day <= 15 and rng.random() < negative_price_frequency:
            price = rng.uniform(-40, -5)

        prices[h] = price

    df = pd.DataFrame({"timestamp": timestamps, "price_eur_mwh": prices})
    return df


if __name__ == "__main__":
    # Quick smoke test of the synthetic generator
    df = generate_synthetic_day_ahead_prices(dt.datetime(2026, 7, 6), n_days=7)
    print(df.describe())
    print(f"Negative-price hours: {(df['price_eur_mwh'] < 0).sum()} / {len(df)}")
