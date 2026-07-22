"""
data_loader.py

Loads and validates the phase 2 analysis output for use by the dashboard.
Kept separate from streamlit_app.py so it can be tested without a running
Streamlit session.
"""

import pandas as pd

REQUIRED_COLUMNS = [
    "week_ending", "storage_bcf", "net_change_bcf",
    "five_yr_avg_bcf", "five_yr_min_bcf", "five_yr_max_bcf",
    "vs_five_yr_avg_bcf", "vs_five_yr_avg_pct",
    "expected_net_change_bcf", "storage_surprise_bcf", "storage_regime",
    "release_date", "price_change_1d", "price_change_1d_pct",
    "price_change_2d", "price_change_2d_pct",
]


def load_analysis_data(path: str) -> pd.DataFrame:
    """
    Loads analysis_weekly.csv and parses date columns. Raises a clear
    error if expected columns are missing, so a schema mismatch surfaces
    immediately in the dashboard rather than as a confusing downstream
    KeyError inside a chart function.
    """
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"analysis_weekly.csv is missing expected columns: {missing}. "
            "Check that analysis.py ran successfully and produced the "
            "expected schema."
        )

    for col in ["week_ending", "release_date"]:
        df[col] = pd.to_datetime(df[col])

    df["year"] = df["week_ending"].dt.year
    df["week_of_year"] = df["week_ending"].dt.isocalendar().week

    return df.sort_values("week_ending").reset_index(drop=True)


def available_years(df: pd.DataFrame) -> list:
    return sorted(df["year"].unique().tolist())