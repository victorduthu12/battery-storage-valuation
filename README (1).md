# Battery Storage Valuation & Revenue Optimization Model

A Python tool that models a grid-scale battery's optimal dispatch and
computes stacked revenue across multiple market segments (energy arbitrage,
FCR/aFRR reserve provision, peak shaving, congestion management).

## How to run it

```bash
pip install pandas numpy scipy matplotlib pulp requests

# Demo mode (synthetic prices, no API key needed)
python3 main.py

# Real data mode (requires a free ENTSO-E token: https://transparency.entsoe.eu)
python3 main.py --entsoe YOUR_TOKEN --zone DE_LU --start 2026-07-06 --days 7
```

Outputs a `dashboard_output.png` (weekly PnL dashboard) and prints the
revenue-stack summary to the console.

## Project structure

| File | Role |
|---|---|
| `config.py` | Battery specs (power, energy, efficiency, degradation cost) and market assumptions (FCR/aFRR prices, peak shaving value) |
| `data_fetcher.py` | Real ENTSO-E API integration (day-ahead prices, XML parsing) + synthetic price generator for offline testing |
| `battery_model.py` | Physical battery model: SoC bounds, efficiency split, dispatch replay/validation, cycle counting |
| `optimizer.py` | Linear Program (PuLP/CBC) that finds the profit-maximising charge/discharge schedule under physical constraints |
| `revenue_stacking.py` | Combines arbitrage (from optimizer) with FCR, aFRR, peak shaving and congestion revenue into one PnL |
| `dashboard.py` | Builds the weekly PNG dashboard: price/dispatch chart, SoC trajectory, revenue breakdown, scenario stress test |
| `main.py` | CLI entry point, orchestrates the pipeline |

---

## How this maps to your CV bullets (read this before the interview)

**"Built Python tool for battery arbitrage analysis: day-ahead/intraday
spread capture, optimal charging/discharging scheduling, revenue stacking
across market segments"**
-> This is `optimizer.py` + `revenue_stacking.py`. The optimizer is a real
Linear Program, not a heuristic: it has decision variables for charge/
discharge power at every hour, SoC dynamics as constraints, and maximises
arbitrage profit net of a degradation cost. Be ready to explain **why LP**:
because battery scheduling with linear efficiency/cost terms is a convex
problem, so LP finds the *global* optimum quickly (CBC solves a week of
hourly data in well under a second) - no need for a heuristic or a more
expensive MILP unless you add binary constraints (e.g. "can't charge and
discharge in the same hour", which this simple version doesn't need because
the LP naturally never does both at once when efficiency < 100%, since that
would burn money on round-trip losses for no reason - a nice point to make
if asked "why no binary charge/discharge exclusivity constraint?").

**"Integrated real-time power price data (EPEX Spot, intraday), weather
forecasts, and market fundamentals (supply/demand balance, CO2 prices,
grid congestion)"**
-> Be honest and precise here: `data_fetcher.py` has a **real, working
integration with ENTSO-E** (the official EU transparency platform that
publishes EPEX Spot day-ahead auction results), including real XML parsing
of their Publication_MarketDocument format. This is genuinely EPEX Spot
day-ahead data (ENTSO-E republishes it). Intraday, live weather feeds and a
full fundamentals model (supply/demand stack, CO2) are **not implemented
in this version** - `config.py` has a `co2_price_eur_per_t` parameter as a
placeholder for that layer. If asked directly: say clearly "the day-ahead
price integration is real and tested; intraday and weather are architected
as extension points I haven't built out yet" - this is a much stronger
answer than pretending it's all done, and it shows you know the difference
between day-ahead and intraday markets (which we covered: day-ahead is the
single auction for tomorrow, intraday is continuous trading closer to
real-time for last-minute adjustments).

**"Modelled cashflows across multiple revenue streams: energy arbitrage,
reserve provision (FCR, aFRR), congestion management, peak shaving"**
-> This is exactly `revenue_stacking.py`. Know the key modelling choice:
power capacity **reserved for FCR/aFRR is subtracted from what's available
for arbitrage** before the optimizer runs (`reserved_power_share` argument).
This reflects the real trade-off a trading desk faces - capacity used for
one purpose can't simultaneously be used for another. Be ready to say that
FCR/aFRR revenue here is modelled as an **average capacity price** (EUR/MW/h),
not real historical auction-clearing data - real clearing prices would come
from regelleistung.net (Germany) or the equivalent per-country TSO platform,
and are a natural next step.

**"Produced weekly dashboards summarising portfolio PnL drivers, risk
exposure, and forward curve scenarios under different market conditions"**
-> `dashboard.py`. The scenario analysis scales the price *spread* around
its mean (not the price level) to simulate higher/lower volatility -
explain why: **battery revenue depends on the spread between cheap and
expensive hours, not on the absolute price level**, so a volatility
stress test should preserve the average price and stretch/compress the
swings around it. This is a good technical point to make proactively.

---

## Things to genuinely understand before the interview (not just recite)

1. **Why the SoC constraint is written as an equality recursion**
   (`soc[t+1] == soc[t] + charge*eff - discharge/eff`) rather than an
   inequality - it's what makes this a *state-space* optimisation, and it's
   the mechanism that prevents the optimizer from "inventing" energy.

2. **Why efficiency is split as `sqrt(round_trip_efficiency)` on each leg**
   (charge and discharge) - a modelling simplification; real systems often
   have asymmetric losses (inverter losses differ from battery internal
   resistance losses), which is a legitimate limitation to acknowledge.

3. **Why a degradation cost term is in the objective function at all** -
   without it, the LP would happily cycle the battery for a 1 EUR/MWh
   spread, which is unrealistic (real wear cost from cycling would exceed
   that). This is what stops the "toy model" behaviour of trading on noise.

4. **The cyclic SoC constraint** (`soc[n] == soc_start`) - without it, the
   optimizer could end the week with an empty battery, effectively
   "monetising" stored energy for free at the edge of the time window
   rather than actually round-tripping it - a classic bug in naive versions
   of this model.

5. **Run the code yourself, change a parameter, and see what happens** -
   e.g. increase `degradation_cost_eur_per_mwh_throughput` in `config.py`
   and re-run `main.py`: you should see fewer, larger cycles (the optimizer
   becomes pickier about which spreads are worth the wear cost). Doing this
   once before the interview will make your answers sound like real
   experience, not a memorised script.

## Known limitations (say these proactively if asked "what would you improve")

- No intraday re-optimisation (day-ahead schedule only, no re-dispatch as
  new information arrives closer to real time)
- FCR/aFRR modelled as constant average prices, not real auction data or
  activation volumes
- No weather-driven price forecasting (uses realised/historical prices,
  not a forecast model)
- Degradation cost is a flat EUR/MWh assumption, not a full electrochemical
  ageing model (see the cycle-life / calendar-life discussion - a more
  advanced version would use a nonlinear stress function like the one used
  in academic battery degradation models)
