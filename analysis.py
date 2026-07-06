"""
analysis.py

Phase 2: turns the phase 1 cleaned/aligned data into the actual analysis
the project is built around.

1. Storage surprise
   The "surprise" is the difference between the actual weekly net change in
   storage and what would be typical for that week of year, since the
   market has already priced in the seasonally typical draw or build.
   It's the deviation from that seasonal expectation that tends to move
   price, not the absolute storage level itself.

   expected_net_change_bcf: rolling five year average net change for the
   same ISO calendar week (mirrors the five_yr_avg_bcf logic already built
   in clean_align.py for storage levels, applied here to net_change_bcf
   instead).

   storage_surprise_bcf = net_change_bcf - expected_net_change_bcf
   A negative surprise means a bigger draw (or smaller build) than typical,
   generally read as bullish. A positive surprise means a smaller draw (or
   bigger build) than typical, generally read as bearish. The sign
   convention is documented here explicitly since it's easy to get
   backwards when eyeballing the numbers later.

2. Price reaction window
   For each Thursday release, the reaction is measured as the change in
   Henry Hub spot price from the last trading day before the release to
   the release day itself (1-day reaction) and to the trading day after
   that (2-day reaction). Reports are assumed released the Thursday
   immediately following the storage week's Friday end date (week_ending
   + 6 days). If that Thursday isn't a trading day (a market holiday), the
   next available trading day is used as the release-day reaction point.

3. Surprise vs. reaction relationship
   Correlates storage_surprise_bcf against the price reaction, both signed
   (does a bigger draw-than-expected push price up) and in absolute value
   (does a bigger surprise, regardless of direction, produce a bigger
   price move), and reports both overall and split by whether storage was
   running above or below its five year average at the time of the report,
   which is the specific comparison the project's core question asks for.
"""

import numpy as np
import pandas as pd


def add_expected_net_change(storage: pd.DataFrame, lookback_years: int = 5) -> pd.DataFrame:
    """
    Adds expected_net_change_bcf and storage_surprise_bcf to a cleaned
    weekly storage DataFrame (the output of clean_align.clean_storage,
    before or after add_five_year_reference has been applied, both work
    since this only touches net_change_bcf).
    """
    df = storage.copy()
    df["iso_week"] = df["week_ending"].dt.isocalendar().week
    df["year"] = df["week_ending"].dt.year

    expected = []
    for _, row in df.iterrows():
        window_years = range(row["year"] - lookback_years, row["year"])
        history = df[(df["iso_week"] == row["iso_week"]) &
                      (df["year"].isin(window_years))]
        expected.append(history["net_change_bcf"].mean() if len(history) else pd.NA)

    df["expected_net_change_bcf"] = expected
    df["storage_surprise_bcf"] = df["net_change_bcf"] - df["expected_net_change_bcf"]

    return df.drop(columns=["iso_week", "year"])


def classify_storage_regime(storage: pd.DataFrame) -> pd.DataFrame:
    """
    Labels each week as 'above_avg', 'below_avg', based on whether
    storage_bcf was above or below five_yr_avg_bcf that week. Weeks
    without a five_yr_avg_bcf value yet (early history) are labeled
    'insufficient_history' and excluded from regime-split comparisons.
    """
    df = storage.copy()

    def label(row):
        if pd.isna(row.get("five_yr_avg_bcf")):
            return "insufficient_history"
        return "above_avg" if row["storage_bcf"] >= row["five_yr_avg_bcf"] else "below_avg"

    df["storage_regime"] = df.apply(label, axis=1)
    return df


def compute_price_reaction(storage: pd.DataFrame, daily_price: pd.DataFrame,
                            release_lag_days: int = 6) -> pd.DataFrame:
    """
    For each storage report week, finds the release date (week_ending +
    release_lag_days, i.e. the following Thursday), and measures the price
    change from the last trading day before release to the release day
    itself (1-day reaction) and to the following trading day (2-day
    reaction).
    """
    prices = daily_price.sort_values("date").reset_index(drop=True)
    dates = prices["date"].values
    closes = prices["price_usd_mmbtu"].values

    rows = []
    for _, row in storage.iterrows():
        release_date = row["week_ending"] + pd.Timedelta(days=release_lag_days)

        # last trading day strictly before release_date
        pre_idx = np.searchsorted(dates, np.datetime64(release_date), side="left") - 1
        # first trading day on/after release_date
        post1_idx = np.searchsorted(dates, np.datetime64(release_date), side="left")
        post2_idx = post1_idx + 1

        if pre_idx < 0 or post2_idx >= len(dates):
            # not enough surrounding data (edge of the pulled history)
            rows.append({
                "week_ending": row["week_ending"],
                "release_date": release_date,
                "pre_release_date": pd.NaT,
                "pre_release_price": np.nan,
                "release_day_date": pd.NaT,
                "release_day_price": np.nan,
                "day2_date": pd.NaT,
                "day2_price": np.nan,
                "price_change_1d": np.nan,
                "price_change_1d_pct": np.nan,
                "price_change_2d": np.nan,
                "price_change_2d_pct": np.nan,
            })
            continue

        pre_price = closes[pre_idx]
        post1_price = closes[post1_idx]
        post2_price = closes[post2_idx]

        rows.append({
            "week_ending": row["week_ending"],
            "release_date": release_date,
            "pre_release_date": pd.Timestamp(dates[pre_idx]),
            "pre_release_price": pre_price,
            "release_day_date": pd.Timestamp(dates[post1_idx]),
            "release_day_price": post1_price,
            "day2_date": pd.Timestamp(dates[post2_idx]),
            "day2_price": post2_price,
            "price_change_1d": post1_price - pre_price,
            "price_change_1d_pct": (post1_price - pre_price) / pre_price * 100,
            "price_change_2d": post2_price - pre_price,
            "price_change_2d_pct": (post2_price - pre_price) / pre_price * 100,
        })

    return pd.DataFrame(rows)


def build_analysis_table(storage_with_surprise: pd.DataFrame,
                          reaction: pd.DataFrame) -> pd.DataFrame:
    return pd.merge(storage_with_surprise, reaction, on="week_ending", how="inner") \
             .sort_values("week_ending").reset_index(drop=True)


def summarize_correlation(analysis: pd.DataFrame) -> dict:
    """
    Returns a dict of correlation statistics answering the project's core
    question: does surprise size relate to price reaction size, and does
    that relationship differ depending on whether storage was running
    above or below its five year average.

    Rows with missing surprise or reaction values (edges of history) are
    dropped before correlating.
    """
    df = analysis.dropna(subset=["storage_surprise_bcf", "price_change_1d", "price_change_2d"])

    results = {
        "n_observations": len(df),
        "corr_surprise_vs_1d_reaction": df["storage_surprise_bcf"].corr(df["price_change_1d"]),
        "corr_surprise_vs_2d_reaction": df["storage_surprise_bcf"].corr(df["price_change_2d"]),
        "corr_abs_surprise_vs_abs_1d_reaction": df["storage_surprise_bcf"].abs().corr(df["price_change_1d"].abs()),
        "corr_abs_surprise_vs_abs_2d_reaction": df["storage_surprise_bcf"].abs().corr(df["price_change_2d"].abs()),
    }

    if "storage_regime" in df.columns:
        for regime in ["above_avg", "below_avg"]:
            subset = df[df["storage_regime"] == regime]
            if len(subset) >= 5:  # avoid reporting a correlation on a tiny sample
                results[f"n_{regime}"] = len(subset)
                results[f"mean_abs_1d_reaction_{regime}"] = subset["price_change_1d"].abs().mean()
                results[f"mean_abs_2d_reaction_{regime}"] = subset["price_change_2d"].abs().mean()
                results[f"corr_surprise_vs_1d_reaction_{regime}"] = \
                    subset["storage_surprise_bcf"].corr(subset["price_change_1d"])
            else:
                results[f"n_{regime}"] = len(subset)
                results[f"note_{regime}"] = "sample too small for a meaningful correlation"

    return results


def main():
    import os
    import config
    from clean_align import load_raw_storage, load_raw_price, clean_storage, \
        clean_price_daily, add_five_year_reference

    raw_storage = load_raw_storage()
    storage = clean_storage(raw_storage)
    storage = add_five_year_reference(storage)
    storage = add_expected_net_change(storage)
    storage = classify_storage_regime(storage)

    raw_price = load_raw_price()
    price_daily = clean_price_daily(raw_price)

    reaction = compute_price_reaction(storage, price_daily)
    analysis = build_analysis_table(storage, reaction)

    os.makedirs(config.PROCESSED_DATA_DIR, exist_ok=True)
    out_path = os.path.join(config.PROCESSED_DATA_DIR, "analysis_weekly.csv")
    analysis.to_csv(out_path, index=False)
    print(f"Saved {len(analysis)} rows to {out_path}")

    stats = summarize_correlation(analysis)
    print("\nCorrelation summary:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
