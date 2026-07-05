# Natural Gas Storage and Price Tracker

Portfolio project analyzing the relationship between the EIA's weekly natural
gas storage report and Henry Hub spot prices. Built as a companion piece to
the ERCOT Day Ahead Price Forecasting Dashboard, covering the gas side of the
power and gas market rather than the electricity side.

**Core question:** How closely does the weekly natural gas storage report
relate to Henry Hub spot prices, and does the market react more strongly when
storage levels are above or below the five year average?



## Data sources

| Dataset | Source | Frequency | Access |
|---|---|---|---|
| Lower 48 working gas in underground storage | EIA Weekly Natural Gas Storage Report | Weekly (Thursday release, week ending Friday) | EIA API v2, route `natural-gas/stor/wkly` |
| Henry Hub natural gas spot price | EIA | Daily | EIA API v2, route `natural-gas/pri/fut`, series `RNGWHHD` |

Both require a free EIA API key: https://www.eia.gov/opendata/register.php

## Repository structure (for own use while work in progress)

```
ng_storage_price_tracker/
  artifacts/
    raw/            # untouched API pulls, written by fetch_data.py
    processed/      # cleaned, aligned outputs, written by clean_align.py
  config.py       # API routes, facets, pull window settings
  fetch_data.py   # pulls raw storage and price data from EIA
  clean_align.py  # cleans, aligns, and computes the five year reference
  tests/
    test_pipeline_synthetic.py   # validates cleaning logic against synthetic data
  requirements.txt
  README.md
```
## Project status (for own use while work in progress)

- [x] Phase 1: Data collection and cleaning
- [ ] Phase 2: Analysis (storage surprise, five year range comparison, price reaction)
- [ ] Phase 3: Streamlit dashboard

## How to run phase 1

```bash
pip install -r requirements.txt
export EIA_API_KEY="your_key_here"
python fetch_data.py
python clean_align.py
```

This produces four files in `data/processed/`:

- `storage_weekly_clean.csv`: weekly Lower 48 storage level, week over week
  net change, and the rolling five year average, min, and max for that same
  week of year.
- `henryhub_daily_clean.csv`: cleaned daily Henry Hub spot price, kept at
  daily granularity for the phase 2 event study.
- `henryhub_weekly.csv`: daily prices aggregated to the storage report's
  Friday week-ending convention (weekly average and Friday close).
- `combined_weekly.csv`: storage and weekly price data joined on
  `week_ending`, the table the phase 3 dashboard will read for the levels
  and price view.

## Key methodology decisions

**Week definition.** All weekly alignment uses the storage report's own
convention, a week ending on Friday. This avoids introducing a second,
competing definition of "week" alongside EIA's.

**Five year average and range.** Calculated as a rolling five year lookback
matched by ISO calendar week number, not a fixed calendar window (e.g. a
static 2021-2026 band). The rolling approach means the comparison stays
accurate and non-arbitrary as more weeks of data are collected, matching how
the industry itself continuously rolls its five year comparison forward.
It also means the earliest weeks of pulled history will have a partial or
empty five year average, since there is not yet five full years of prior
data to compare against. With a 5 year pull window, this affects the first
stretch of the dataset before the lookback fills in. This is expected and
documented in the data rather than a bug, but it does mean a wider initial
pull (for example 8-10 years) is recommended if a fully populated five year
reference is wanted across the entire analysis window from day one. The
default pull window can be widened with a single constant change in
`config.py` (`YEARS_OF_HISTORY`).

**Daily prices retained separately from weekly aggregates.** The core
question requires measuring how much price moves in the one to two days
following each Thursday storage release, a signal that would be lost if only
weekly average prices were kept. `henryhub_daily_clean.csv` preserves full
daily granularity specifically for that phase 2 event study.

**Holiday handling.** When the Friday marking a week's end is not a trading
day (a market holiday), the closing price for that week uses the most recent
prior trading day and is flagged via the `friday_was_trading_day` column in
`henryhub_weekly.csv`, so downstream analysis can filter or footnote those
weeks if needed.

## Known limitations

- EIA occasionally revises the prior week's storage figure when it reissues
  data. The cleaning step keeps the most recently reported value for a given
  week rather than the originally published one, which means the pulled
  data reflects EIA's latest revision, not necessarily the number the market
  reacted to in real time. This is a meaningful nuance for the phase 2 price
  reaction analysis and will be called out again there.
- The Henry Hub spot price series reflects trading day closes and does not
  capture intraday price action around the exact 10:30am ET release time.
  The phase 2 event study will therefore measure the reaction over full
  trading days following the release, not a tight intraday window.
- Storage data availability by API begins in the mid-1990s; five to ten
  years of history is more than sufficient to capture multiple seasonal
  cycles and at least one major price dislocation, but very long lookback
  windows (multi-decade) are not the design target here.
