# Battery Storage Valuation & Revenue Optimization Model

A Python tool that models a grid-scale battery's optimal dispatch and
computes stacked revenue across multiple market segments: energy
arbitrage, FCR/aFRR reserve provision, peak shaving, and congestion
management.

## Overview

Grid-scale batteries rarely earn from a single revenue source. This tool
formulates the charge/discharge scheduling problem as a Linear Program,
solves for the profit-maximising dispatch given a day-ahead price curve,
and combines that arbitrage result with simplified models of ancillary
service and capacity revenue to produce a full weekly PnL breakdown.

## How to run it

```bash
pip install -r requirements.txt

# Demo mode - synthetic prices, no API key needed
python3 main.py

# Real data mode - requires a free ENTSO-E token (transparency.entsoe.eu)
python3 main.py --entsoe YOUR_TOKEN --zone DE_LU --start 2026-07-06 --days 7
```

Running it produces:
- `dashboard_output.png` - a weekly dashboard (price curve, dispatch
  schedule, SoC trajectory, revenue breakdown, volatility scenarios)
- A console summary of the revenue stack

## Project structure

| File | Role |
|---|---|
| `config.py` | Battery specs (power, energy, efficiency, degradation cost) and market assumptions (FCR/aFRR prices, peak shaving value) |
| `data_fetcher.py` | ENTSO-E API integration for real day-ahead prices, plus a synthetic price generator for offline testing |
| `battery_model.py` | Physical battery model: SoC bounds, efficiency split, dispatch replay/validation, cycle counting |
| `optimizer.py` | Linear Program (PuLP/CBC) that finds the profit-maximising charge/discharge schedule under physical constraints |
| `revenue_stacking.py` | Combines arbitrage (from the optimizer) with FCR, aFRR, peak shaving and congestion revenue into a single PnL |
| `dashboard.py` | Builds the weekly PNG dashboard: price/dispatch chart, SoC trajectory, revenue breakdown, scenario stress test |
| `main.py` | CLI entry point, orchestrates the pipeline |

## Modelling approach

**Dispatch optimisation.** The charge/discharge schedule is solved as a
Linear Program: decision variables for charge and discharge power at
every hour, state-of-charge dynamics expressed as an equality recursion,
and an objective that maximises arbitrage revenue net of a degradation
cost (to avoid unrealistic micro-cycling on negligible price spreads). A
cyclic state-of-charge constraint ties the end of the window back to the
starting SoC, so the optimiser can't "free-ride" by ending the period
empty.

**Revenue stacking.** Power capacity reserved for FCR/aFRR is subtracted
from what's available for arbitrage before the optimiser runs, reflecting
the real trade-off between reserving capacity for grid services versus
using it for energy trading. Reserve revenue is currently modelled using
average capacity prices rather than historical auction-clearing data.

**Scenario analysis.** The dashboard's bull/base/bear scenarios scale the
price *spread* around its mean rather than the price level, since battery
revenue depends on the gap between cheap and expensive hours, not on the
absolute price level.

## Current limitations

- Day-ahead scheduling only; no intraday re-optimisation
- FCR/aFRR modelled as constant average capacity prices, not real
  auction-clearing data or activation volumes
- No weather-driven price forecasting (uses realised/historical prices)
- Degradation cost is a flat EUR/MWh assumption rather than a full
  electrochemical ageing model

## Possible extensions

- Pull real historical FCR/aFRR clearing prices (e.g. regelleistung.net)
- Add intraday re-dispatch on a rolling horizon
- Replace the flat degradation cost with a nonlinear ageing model
- Add a simple day-ahead price forecast module
