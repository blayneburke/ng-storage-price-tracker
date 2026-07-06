import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
"""
test_pipeline_synthetic.py

Sanity-checks clean_align.py against synthetic data shaped like the real
EIA API v2 response (period, value columns), since live API access isn't
available in this environment. This is not a substitute for running the
real pull, it exists to confirm the parsing, deduplication, weekly
aggregation, and five-year reference logic behave as intended before
pointing them at real data.
"""

import numpy as np
import pandas as pd

import clean_align as ca


def make_synthetic_storage(n_years=6):
    """Weekly Friday dates, roughly seasonal storage curve with noise."""
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n_years * 52, freq="W-FRI")
    t = np.arange(len(dates))
    seasonal = 1500 + 1500 * np.sin((t / 52) * 2 * np.pi - np.pi / 2)
    trend = t * 0.5
    noise = np.random.normal(0, 20, len(dates))
    values = seasonal + trend + noise
    df = pd.DataFrame({"period": dates.strftime("%Y-%m-%d"), "value": values})
    # inject a duplicate week (simulating an EIA revision reissue) to test dedup
    dup_row = df.iloc[10].copy()
    dup_row["value"] = dup_row["value"] + 5
    df = pd.concat([df, pd.DataFrame([dup_row])], ignore_index=True)
    return df


def make_synthetic_price(n_years=6):
    """Daily business-day dates, noisy price series with a few gaps (holidays)."""
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n_years * 365, freq="B")
    price = 3 + np.cumsum(np.random.normal(0, 0.05, len(dates)))
    price = np.clip(price, 1.0, None)
    df = pd.DataFrame({"period": dates.strftime("%Y-%m-%d"), "value": price})
    # drop a handful of rows at random to simulate holiday gaps
    drop_idx = np.random.choice(df.index, size=15, replace=False)
    df = df.drop(index=drop_idx).reset_index(drop=True)
    return df


def run():
    np.random.seed(7)

    raw_storage = make_synthetic_storage()
    raw_price = make_synthetic_price()

    print("--- Testing clean_storage ---")
    storage = ca.clean_storage(raw_storage)
    assert storage["week_ending"].is_monotonic_increasing, "storage weeks not sorted"
    assert storage["week_ending"].duplicated().sum() == 0, "duplicate weeks not removed"
    assert storage["net_change_bcf"].isna().sum() == 1, "expected exactly one NaN net change (first row)"
    print(f"storage rows after cleaning: {len(storage)}")
    print(storage.head(3))
    print(storage.tail(3))

    print("\n--- Testing add_five_year_reference ---")
    storage_ref = ca.add_five_year_reference(storage)
    non_null_avg = storage_ref["five_yr_avg_bcf"].notna().sum()
    print(f"rows with a populated five-year average: {non_null_avg} / {len(storage_ref)}")
    assert non_null_avg > 0, "five year average never populated, alignment logic broken"
    # spot check: a row with five_yr_avg should have five_yr_min <= value <= or near average
    sample = storage_ref.dropna(subset=["five_yr_avg_bcf"]).iloc[-1]
    assert sample["five_yr_min_bcf"] <= sample["five_yr_avg_bcf"] <= sample["five_yr_max_bcf"], \
        "five year min/avg/max out of order"
    print(storage_ref.dropna(subset=["five_yr_avg_bcf"])[
        ["week_ending", "storage_bcf", "five_yr_avg_bcf", "five_yr_min_bcf",
         "five_yr_max_bcf", "vs_five_yr_avg_pct"]
    ].tail(5))

    print("\n--- Testing clean_price_daily ---")
    price_daily = ca.clean_price_daily(raw_price)
    assert price_daily["date"].is_monotonic_increasing, "price dates not sorted"
    print(f"price rows after cleaning: {len(price_daily)}")

    print("\n--- Testing aggregate_price_to_weekly ---")
    price_weekly = ca.aggregate_price_to_weekly(price_daily)
    assert (price_weekly["week_ending"].dt.weekday == 4).all(), "week_ending not all Fridays"
    print(f"weekly price rows: {len(price_weekly)}")
    print(price_weekly.head(3))
    non_friday_close = (~price_weekly["friday_was_trading_day"]).sum()
    print(f"weeks where Friday itself wasn't a trading day (holiday): {non_friday_close}")

    print("\n--- Testing build_combined_weekly ---")
    combined = ca.build_combined_weekly(storage_ref, price_weekly)
    assert len(combined) > 0, "combined weekly join produced zero rows"
    assert combined["week_ending"].is_monotonic_increasing
    print(f"combined weekly rows: {len(combined)}")
    print(combined.columns.tolist())
    print(combined.tail(3))

    print("\nAll synthetic pipeline checks passed.")


if __name__ == "__main__":
    run()
