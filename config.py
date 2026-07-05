"""
config.py

Central place for EIA API configuration and series identifiers used across
the natural gas storage and price tracker project.

Data sources
------------
1. Weekly Lower 48 natural gas storage (EIA Weekly Natural Gas Storage Report)
   - EIA API v2 route: natural-gas/stor/wkly
   - Legacy (v1) series id for the headline Lower 48 number: NW2_EPG0_SWO_R48_BCF
   - Released every Thursday at 10:30am ET for the storage week ending the
     prior Friday.

2. Henry Hub natural gas spot price, daily
   - EIA API v2 route: natural-gas/pri/fut
   - Legacy (v1) series id: RNGWHHD
   - Units: dollars per million Btu

Both routes are documented at https://www.eia.gov/opendata/browser/natural-gas
An API key is required and is free to obtain at https://www.eia.gov/opendata/register.php

Note on API key handling: never hardcode the key in this file. Set it as an
environment variable (EIA_API_KEY) and read it at runtime. This keeps the key
out of version control if this project is pushed to GitHub for a portfolio.
"""
from dotenv import load_dotenv 
import os

load_dotenv()  # reads .env and loads its variables into the environment

EIA_API_KEY = os.environ.get("EIA_API_KEY")

if not EIA_API_KEY:
    raise EnvironmentError(
        "EIA_API_KEY not found. Copy .env.example to .env and add your key, "
        "or export EIA_API_KEY as an environment variable."
    )

EIA_API_BASE_URL = "https://api.eia.gov/v2"

# Read the API key from the environment. Raise a clear error early if it is
# missing rather than letting requests fail later with a confusing message.
EIA_API_KEY = os.environ.get("EIA_API_KEY")

# --- Storage series -------------------------------------------------------
# duoarea=NW2 is the Lower 48 states aggregate used in the EIA Weekly Natural
# Gas Storage Report. product=EPG0 is natural gas. process=SWO is the storage
# withdrawals/injections process code used for "working gas in storage".
STORAGE_ROUTE = f"{EIA_API_BASE_URL}/natural-gas/stor/wkly/data/"
STORAGE_FACETS = {
    "duoarea": ["R48"],  # Lower 48 states. Change to regional codes for
                          # East, Midwest, Mountain, Pacific, South Central
                          # if regional detail is added later.
    "product": ["EPG0"],
    "process": ["SWO"],
}

# --- Henry Hub spot price series ------------------------------------------
# duoarea=RGC is the Henry Hub reporting area used for the daily spot price
# series within natural-gas/pri/fut.
PRICE_ROUTE = f"{EIA_API_BASE_URL}/natural-gas/pri/fut/data/"
PRICE_FACETS = {
    "series": ["RNGWHHD"],
}

# --- Pull parameters --------------------------------------------------------
# Rolling window: default pull is 5 years. Widen this to 10 years later if
# more price regimes (e.g. the 2020 demand collapse, the 2022 price spike)
# are wanted for the analysis. No code changes are needed elsewhere, this is
# the single place that controls history length.
YEARS_OF_HISTORY = 5

# Number of years to use for the rolling five-year average / range
# comparison in phase 2. Kept separate from YEARS_OF_HISTORY so the pull
# window and the comparison window can be tuned independently.
ROLLING_AVG_YEARS = 5

RAW_DATA_DIR = "artifacts/raw"
PROCESSED_DATA_DIR = "artifacts/processed"
