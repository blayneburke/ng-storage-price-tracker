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

Confirmed facet values for the storage route (verified directly against the
API, since the legacy v1 area code does not carry over cleanly to v2):
`duoarea=R48` (Lower 48 states), `product=EPG0` (Natural Gas),
`process=SWO` (Underground Storage, Working Gas).

## Repository structure

```
ng_storage_price_tracker/
  artifacts/
    raw/            # untouched API pulls, written by fetch_data.py
    processed/      # cleaned, aligned, and analysis outputs
    
    config.py       # API routes, facets, pull window settings
    fetch_data.py   # pulls raw storage and price data from EIA
    clean_align.py  # cleans, aligns, and computes the five year reference
    analysis.py      # phase 2: storage surprise, price reaction, correlation
    dashboard/
      app.py         # Streamlit entry point
      data_loader.py # loads and validates analysis_weekly.csv
      charts.py      # plotly figure-building, kept separate from Streamlit UI for testability
  tests/
    test_pipeline_synthetic.py    # validates phase 1 cleaning logic
    test_analysis_synthetic.py    # validates phase 2 analysis logic
    test_dashboard_synthetic.py   # validates phase 3 chart logic
  requirements.txt
  README.md
```

## How to run phase 1

```bash
pip install -r requirements.txt
export EIA_API_KEY="your_key_here"
python src/fetch_data.py
python src/clean_align.py
```

This produces four files in `artifacts/processed/`:

- `storage_weekly_clean.csv`: weekly Lower 48 storage level, week over week
  net change, and the rolling five year average, min, and max for that same
  week of year.
- `henryhub_daily_clean.csv`: cleaned daily Henry Hub spot price, kept at
  daily granularity for the phase 2 event study.
- `henryhub_weekly.csv`: daily prices aggregated to the storage report's
  Friday week-ending convention (weekly average and Friday close).
- `combined_weekly.csv`: storage and weekly price data joined on
  `week_ending`, the table phase 2 and the phase 3 dashboard both build on.

## How to run phase 2

```bash
python src/analysis.py
```

This produces `artifacts/processed/analysis_weekly.csv` and prints a
correlation summary to the console. The output table adds the following
columns on top of the phase 1 combined weekly data:

- `expected_net_change_bcf`: rolling five year average net change in
  storage for that same week of year, the seasonally "typical" move.
- `storage_surprise_bcf`: actual net change minus expected net change. A
  negative value means a bigger draw (or smaller build) than typical,
  generally read as bullish. A positive value means a smaller draw (or
  bigger build) than typical, generally read as bearish.
- `storage_regime`: whether that week's storage level was running
  `above_avg` or `below_avg` relative to its own five year average, or
  `insufficient_history` for weeks too early in the dataset to have a five
  year lookback populated.
- `price_change_1d` / `price_change_1d_pct`: change in Henry Hub spot price
  from the last trading day before the Thursday release to the release day
  itself.
- `price_change_2d` / `price_change_2d_pct`: same, extended to the trading
  day after the release day.

The printed correlation summary reports the relationship between surprise
size and price reaction both overall and split by storage regime
(`above_avg` vs `below_avg`), which is the specific comparison the
project's core question asks for. Read the actual sign and magnitude of
these numbers directly from your own real-data run; the synthetic test in
`tests/test_analysis_synthetic.py` only confirms the pipeline correctly
recovers a known relationship on fake data, it says nothing about what the
real market has actually done.

## How to run phase 3

```bash
streamlit run src/dashboard/app.py
```

This opens a browser tab with three views:

- **Storage Levels**: the selected year's storage level plotted against
  its own rolling five year range (shaded band) and average (dashed line),
  indexed by week of year so different years line up for comparison. Prior
  years can be optionally overlaid as thin reference lines.
- **Price Reaction**: a scatter of Henry Hub price reaction (1-day or
  2-day, toggleable) against each report's release date, with marker color
  and size mapped to that week's storage surprise. A diverging color scale
  distinguishes bigger-than-typical draws from bigger-than-typical builds.
  Can be filtered to only above-average or only below-average storage
  weeks.
- **Summary & Methodology**: the regime comparison table (mean absolute
  price reaction and surprise correlation, split by above/below average
  storage), overall correlation metrics, and expandable sections for data
  sources, a full data dictionary, and known limitations, so the
  presentation layer carries the same documented judgment calls as this
  README rather than just showing charts without context.

The dashboard reads `artifacts/processed/analysis_weekly.csv` directly, so
phase 2 (`python src/analysis.py`) must be run first. The chart-building
logic in `charts.py` and the schema validation in `data_loader.py` are kept
separate from the Streamlit UI code in `app.py` specifically so they can be
unit tested against synthetic data without needing a running Streamlit
session, see `tests/test_dashboard_synthetic.py`.

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

**Storage surprise definition.** Built the same way as the five year
average for storage levels, but applied to the weekly net change rather
than the level itself: the expected net change for a given week is the
rolling five year average net change for that same ISO week. The surprise
is the actual net change minus that expectation. This is a proxy for what
the market itself watches (analyst consensus surveys ahead of each release,
which are not public data) rather than the true consensus figure itself,
and that distinction is worth stating explicitly in any written summary of
this project.

**Price reaction window.** Measured from the last trading day before the
Thursday release to the release day itself (1-day) and the following
trading day (2-day), using daily close prices rather than intraday data,
since intraday Henry Hub data around the exact 10:30am ET release time is
not available through this data source. Release dates use a verified
holiday-adjusted lookup table sourced directly from EIA's published release
schedule (https://ir.eia.gov/ngs/schedule.html) for weeks where an
exception is confirmed, falling back to the standard rule (week_ending + 6
days, the following Thursday) otherwise. EIA's published schedule only
lists confirmed exceptions from January 2025 onward; no equivalent verified
list was found for 2021-2024, so holiday-shifted release dates in that
earlier stretch of history are not corrected for and may introduce some
noise into the price reaction measured for those specific weeks. This is a
known, explicitly documented gap rather than an oversight.

**Daily prices retained separately from weekly aggregates.** The core
question requires measuring how much price moves in the one to two days
following each Thursday storage release, a signal that would be lost if only
weekly average prices were kept. `henryhub_daily_clean.csv` preserves full
daily granularity specifically for that phase 2 event study.

**Holiday handling.** When the Friday marking a week's end is not a trading
day (a market holiday), the closing price for that week uses the most recent
prior trading day and is flagged via the `friday_was_trading_day` column in
`henryhub_weekly.csv`, so downstream analysis can filter or footnote those
weeks if needed. This was confirmed working correctly against real data
around Juneteenth 2026.

## Known limitations

- EIA occasionally revises the prior week's storage figure when it reissues
  data. The cleaning step keeps the most recently reported value for a given
  week rather than the originally published one, which means the pulled
  data reflects EIA's latest revision, not necessarily the number the market
  reacted to in real time. This is a meaningful nuance for the phase 2 price
  reaction analysis, since the market traded on the originally published
  figure, not the later-revised one used here.
- The release date logic now corrects for known EIA holiday-adjusted
  releases from January 2025 onward (Veterans Day, Thanksgiving, Christmas,
  New Year's Day, Juneteenth, and one ad hoc exception, the January 2025
  National Day of Mourning), verified directly against EIA's published
  schedule. No equivalent verified schedule was available for 2021-2024, so
  the price reaction measured for holiday weeks in that earlier stretch of
  history uses the standard +6 day assumption and may be measuring a
  slightly wrong pair of trading days for those specific weeks. This
  affects a small number of weeks out of the full pulled history (a
  handful of federal holidays per year), not the dataset broadly.
- The storage surprise calculated here is a rolling five year seasonal
  average, not the actual analyst consensus estimate the market was
  positioned around ahead of each release. Real market reactions are driven
  by deviation from consensus, which is typically only available through
  paid data services (e.g. Bloomberg, Reuters polls). This project's
  surprise metric is a reasonable public-data proxy for that, but it is not
  the same thing, and this project's write up should be explicit about that
  distinction.
- The Henry Hub spot price series reflects trading day closes and does not
  capture intraday price action around the exact 10:30am ET release time.
  The phase 2 event study therefore measures the reaction over full trading
  days following the release, not a tight intraday window, and will likely
  understate the true immediate market reaction relative to what an
  intraday futures tick chart would show.
- Storage data availability by API begins in the mid-1990s; five to ten
  years of history is more than sufficient to capture multiple seasonal
  cycles and at least one major price dislocation, but very long lookback
  windows (multi-decade) are not the design target here.
