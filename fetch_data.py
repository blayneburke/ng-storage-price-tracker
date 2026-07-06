"""
fetch_data.py

Pulls two raw datasets from the EIA API v2:

1. Weekly Lower 48 natural gas storage levels (EIA Weekly Natural Gas
   Storage Report).
2. Daily Henry Hub natural gas spot prices.

Both are written to artifacts/raw/ as untouched CSVs. No cleaning, aggregation,
or derived columns happen in this module. Keeping the raw pull separate
from cleaning (see clean_align.py) makes it easy to re-run the pull on a
schedule without re-deriving logic, and gives the project a clear,
defensible "raw versus processed" data lineage for the write up.

Usage
-----
    export EIA_API_KEY="your_key_here"
    python src/fetch_data.py

Requirements
------------
    pip install requests pandas
"""

import os
import sys
import time
from datetime import date

import pandas as pd
import requests

import config


def _check_api_key() -> str:
    if not config.EIA_API_KEY:
        raise EnvironmentError(
            "EIA_API_KEY environment variable is not set. Register for a "
            "free key at https://www.eia.gov/opendata/register.php and run "
            "`export EIA_API_KEY=your_key_here` before calling this script."
        )
    return config.EIA_API_KEY


def _paginated_get(route: str, facets: dict, frequency: str,
                    start: str, api_key: str) -> pd.DataFrame:
    """
    Handle EIA API v2 pagination. The API caps each response at 5000 rows,
    which is more than enough for a single facet request over 5-10 years of
    weekly or daily data, but pagination is included defensively in case
    the pull window is widened later (e.g. to 10+ years of daily data,
    which can exceed 5000 rows).
    """
    all_rows = []
    offset = 0
    length = 5000

    while True:
        params = {
            "api_key": api_key,
            "frequency": frequency,
            "data[0]": "value",
            "start": start,
            "sort[0][column]": "period",
            "sort[0][direction]": "asc",
            "offset": offset,
            "length": length,
        }
        for facet_key, facet_values in facets.items():
            for i, val in enumerate(facet_values):
                params[f"facets[{facet_key}][{i}]"] = val

        resp = requests.get(route, params=params, timeout=30)

        if resp.status_code != 200:
            raise RuntimeError(
                f"EIA API request failed with status {resp.status_code}: "
                f"{resp.text[:500]}"
            )

        payload = resp.json()
        rows = payload.get("response", {}).get("data", [])
        all_rows.extend(rows)

        if len(rows) < length:
            break
        offset += length
        time.sleep(0.2)  # be polite to the API, avoid hammering it

    if not all_rows:
        raise ValueError(
            f"No data returned for route {route} with facets {facets}. "
            "Check that the facet codes are still valid, EIA occasionally "
            "revises its taxonomy."
        )

    return pd.DataFrame(all_rows)


def fetch_storage_data(api_key: str, years_of_history: int = None) -> pd.DataFrame:
    """
    Pull the weekly Lower 48 working gas in storage series.

    Returns a DataFrame with (at minimum) columns: period, value, duoarea,
    product, process, units. The `period` column is a weekly date string
    (the storage report's week-ending Friday).
    """
    years = years_of_history or config.YEARS_OF_HISTORY
    start_year = date.today().year - years
    start = f"{start_year}-01-01"

    df = _paginated_get(
        route=config.STORAGE_ROUTE,
        facets=config.STORAGE_FACETS,
        frequency="weekly",
        start=start,
        api_key=api_key,
    )
    return df


def fetch_henryhub_daily(api_key: str, years_of_history: int = None) -> pd.DataFrame:
    """
    Pull the daily Henry Hub spot price series.

    Returns a DataFrame with (at minimum) columns: period, value, series,
    units. The `period` column is a daily date string.
    """
    years = years_of_history or config.YEARS_OF_HISTORY
    start_year = date.today().year - years
    start = f"{start_year}-01-01"

    df = _paginated_get(
        route=config.PRICE_ROUTE,
        facets=config.PRICE_FACETS,
        frequency="daily",
        start=start,
        api_key=api_key,
    )
    return df


def main():
    api_key = _check_api_key()
    os.makedirs(config.RAW_DATA_DIR, exist_ok=True)

    print(f"Pulling {config.YEARS_OF_HISTORY} years of weekly storage data...")
    storage_df = fetch_storage_data(api_key)
    storage_path = os.path.join(config.RAW_DATA_DIR, "eia_storage_weekly.csv")
    storage_df.to_csv(storage_path, index=False)
    print(f"Saved {len(storage_df)} rows to {storage_path}")

    print(f"Pulling {config.YEARS_OF_HISTORY} years of daily Henry Hub prices...")
    price_df = fetch_henryhub_daily(api_key)
    price_path = os.path.join(config.RAW_DATA_DIR, "eia_henryhub_daily.csv")
    price_df.to_csv(price_path, index=False)
    print(f"Saved {len(price_df)} rows to {price_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
