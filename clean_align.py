"""
clean_align.py

Takes the raw CSVs produced by fetch_data.py and produces analysis-ready
outputs:

  1. storage_weekly_clean.csv
     One row per storage report week (week ending Friday). Columns:
     week_ending, storage_bcf, net_change_bcf, five_yr_avg_bcf,
     five_yr_min_bcf, five_yr_max_bcf, vs_five_yr_avg_bcf,
     vs_five_yr_avg_pct.

  2. henryhub_daily_clean.csv
     Cleaned daily Henry Hub spot price series, deduplicated and sorted,
     kept at daily granularity for the phase 2 event study around each
     Thursday storage release.

  3. henryhub_weekly.csv
     Daily prices aggregated to the same week-ending Friday convention
     used by the storage report, with both a weekly average price and a
     Friday closing price, so the storage levels view and the price view
     can be joined on a single weekly key.

  4. combined_weekly.csv
     storage_weekly_clean and henryhub_weekly joined on week_ending, the
     single table the phase 3 dashboard reads for the levels-and-price
     view.

Key design decisions (documented here so they can be cited directly in the
project write up):

  - Week definition: the storage report's own convention, a week ending on
    Friday. This is EIA's native week-ending date and keeps the storage
    numbers exactly as EIA defines them rather than introducing a second,
    competing week definition.

  - Five year average and range: calculated as a ROLLING five year
    lookback (the trailing 5 years' worth of same-ISO-week observations,
    not a fixed 2021-2026 calendar window). This means the comparison
    stays accurate and non-arbitrary as more weekly data is added in the
    future, matching how the industry itself continuously rolls its
    5-year comparison window forward. Weeks are matched by ISO calendar
    week number (1-52/53) rather than exact calendar date, since the
    Friday week-ending date drifts by a few days year to year.

  - Daily prices are kept in a separate file at daily granularity
    specifically so phase 2 can measure the 1-2 trading day price
    reaction after each Thursday release without having that signal
    smoothed away by weekly averaging.
"""

import os

import pandas as pd

import config


def load_raw_storage(path: str = None) -> pd.DataFrame:
    path = path or os.path.join(config.RAW_DATA_DIR, "eia_storage_weekly.csv")
    df = pd.read_csv(path)
    return df


def load_raw_price(path: str = None) -> pd.DataFrame:
    path = path or os.path.join(config.RAW_DATA_DIR, "eia_henryhub_daily.csv")
    df = pd.read_csv(path)
    return df


def clean_storage(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Parse dates, sort chronologically, drop duplicate weeks (EIA
    occasionally revises the prior week's figure and reissues it, keep the
    most recent value for a given week), and compute the week over week
    net change in storage.
    """
    df = raw.copy()
    df["week_ending"] = pd.to_datetime(df["period"])
    df["storage_bcf"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["storage_bcf"])
    df = df.sort_values("week_ending")
    df = df.drop_duplicates(subset="week_ending", keep="last")

    df["net_change_bcf"] = df["storage_bcf"].diff()

    return df[["week_ending", "storage_bcf", "net_change_bcf"]].reset_index(drop=True)


def add_five_year_reference(df: pd.DataFrame,
                             lookback_years: int = None) -> pd.DataFrame:
    """
    For each week, compute the rolling five-year average, min, and max of
    storage_bcf using the same ISO calendar week number from the trailing
    N years (excluding the current row's own year). This reproduces the
    "5-year range" band that shows up on every industry storage chart,
    but computed directly from the pulled history rather than scraped from
    a published chart, so it stays reproducible and moves forward
    automatically as new weeks are added.
    """
    lookback_years = lookback_years or config.ROLLING_AVG_YEARS
    df = df.copy()
    df["iso_week"] = df["week_ending"].dt.isocalendar().week
    df["year"] = df["week_ending"].dt.year

    avg_list, min_list, max_list = [], [], []

    for _, row in df.iterrows():
        window_years = range(row["year"] - lookback_years, row["year"])
        history = df[(df["iso_week"] == row["iso_week"]) &
                      (df["year"].isin(window_years))]

        if len(history) == 0:
            avg_list.append(pd.NA)
            min_list.append(pd.NA)
            max_list.append(pd.NA)
        else:
            avg_list.append(history["storage_bcf"].mean())
            min_list.append(history["storage_bcf"].min())
            max_list.append(history["storage_bcf"].max())

    df["five_yr_avg_bcf"] = avg_list
    df["five_yr_min_bcf"] = min_list
    df["five_yr_max_bcf"] = max_list

    df["vs_five_yr_avg_bcf"] = df["storage_bcf"] - df["five_yr_avg_bcf"]
    df["vs_five_yr_avg_pct"] = (df["vs_five_yr_avg_bcf"] / df["five_yr_avg_bcf"]) * 100

    return df.drop(columns=["iso_week", "year"])


def clean_price_daily(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Parse dates, sort chronologically, drop duplicates and any non-trading
    day nulls that occasionally show up in the raw feed around holidays.
    """
    df = raw.copy()
    df["date"] = pd.to_datetime(df["period"])
    df["price_usd_mmbtu"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["price_usd_mmbtu"])
    df = df.sort_values("date")
    df = df.drop_duplicates(subset="date", keep="last")

    return df[["date", "price_usd_mmbtu"]].reset_index(drop=True)


def aggregate_price_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily prices onto the storage report's Friday week-ending
    convention. Produces both a weekly average price (smooths out
    intra-week noise, useful for the levels-over-time view) and the
    Friday closing price (useful as a clean "price as of the report week"
    reference point). If a given Friday is not a trading day (holiday),
    the most recent prior trading day's price is used as the week's
    closing price and flagged in a boolean column.
    """
    df = daily.copy()
    # Anchor each date to the Friday ending its trading week.
    df["week_ending"] = df["date"] + pd.to_timedelta(
        (4 - df["date"].dt.weekday) % 7, unit="D"
    )

    weekly_avg = df.groupby("week_ending")["price_usd_mmbtu"].mean().rename(
        "avg_price_usd_mmbtu"
    )

    # Closing price: last available trading day in each week-ending bucket.
    closing = df.groupby("week_ending").apply(
        lambda g: g.sort_values("date").iloc[-1]
    )
    closing = closing[["date", "price_usd_mmbtu"]].rename(
        columns={"date": "close_date", "price_usd_mmbtu": "close_price_usd_mmbtu"}
    )
    closing["friday_was_trading_day"] = closing["close_date"].dt.weekday == 4

    result = pd.concat([weekly_avg, closing], axis=1).reset_index()
    return result


def build_combined_weekly(storage: pd.DataFrame, price_weekly: pd.DataFrame) -> pd.DataFrame:
    combined = pd.merge(storage, price_weekly, on="week_ending", how="inner")
    return combined.sort_values("week_ending").reset_index(drop=True)


def main():
    os.makedirs(config.PROCESSED_DATA_DIR, exist_ok=True)

    raw_storage = load_raw_storage()
    storage = clean_storage(raw_storage)
    storage = add_five_year_reference(storage)
    storage_path = os.path.join(config.PROCESSED_DATA_DIR, "storage_weekly_clean.csv")
    storage.to_csv(storage_path, index=False)
    print(f"Saved {len(storage)} rows to {storage_path}")

    raw_price = load_raw_price()
    price_daily = clean_price_daily(raw_price)
    price_daily_path = os.path.join(config.PROCESSED_DATA_DIR, "henryhub_daily_clean.csv")
    price_daily.to_csv(price_daily_path, index=False)
    print(f"Saved {len(price_daily)} rows to {price_daily_path}")

    price_weekly = aggregate_price_to_weekly(price_daily)
    price_weekly_path = os.path.join(config.PROCESSED_DATA_DIR, "henryhub_weekly.csv")
    price_weekly.to_csv(price_weekly_path, index=False)
    print(f"Saved {len(price_weekly)} rows to {price_weekly_path}")

    combined = build_combined_weekly(storage, price_weekly)
    combined_path = os.path.join(config.PROCESSED_DATA_DIR, "combined_weekly.csv")
    combined.to_csv(combined_path, index=False)
    print(f"Saved {len(combined)} rows to {combined_path}")


if __name__ == "__main__":
    main()
