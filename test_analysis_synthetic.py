import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

"""
test_analysis_synthetic.py

Validates analysis.py by constructing synthetic storage and price data with
a KNOWN built-in relationship: bigger-than-expected draws (negative
surprise) are engineered to push price up, and the price reaction is
scaled directly off the surprise size. If the pipeline is implemented
correctly, summarize_correlation() should recover a clear negative
correlation between storage_surprise_bcf and price_change_1d (bigger draw
than expected -> price goes up -> negative surprise paired with positive
price change), and a stronger relationship should show up in whichever
regime the noise is set to favor.

This is a logic check, not a claim about how the real market behaves. Real
results depend on real data and phase 2's actual findings should be read
from analysis_weekly.csv once run against the live pull.
"""

import numpy as np
import pandas as pd

import analysis as an
from clean_align import add_five_year_reference


def make_synthetic_storage_with_surprise(n_years=8, seed=11):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n_years * 52, freq="W-FRI")
    t = np.arange(len(dates))

    seasonal_level = 1800 + 1600 * np.sin((t / 52) * 2 * np.pi - np.pi / 2)
    surprise = rng.normal(0, 15, len(dates))  # the "unexpected" component
    storage_bcf = seasonal_level + np.cumsum(rng.normal(0, 3, len(dates))) * 0.1

    df = pd.DataFrame({
        "week_ending": dates,
        "storage_bcf": storage_bcf,
    })
    df["net_change_bcf"] = df["storage_bcf"].diff()
    # inject the surprise directly into net_change so expected vs actual
    # diverge in a way we can trace
    df.loc[1:, "net_change_bcf"] = df.loc[1:, "net_change_bcf"] + surprise[1:]
    df["_true_surprise"] = 0.0
    df.loc[1:, "_true_surprise"] = surprise[1:]

    return df


def make_synthetic_price_reacting_to_surprise(storage_df, seed=11, sensitivity=-0.03):
    """
    Builds a daily price series that drifts randomly, then gets a jump on
    each release day proportional to -sensitivity * true_surprise (bigger
    draw than expected, i.e. more negative surprise, pushes price up when
    sensitivity is negative).
    """
    rng = np.random.default_rng(seed + 1)
    start = storage_df["week_ending"].min() - pd.Timedelta(days=14)
    end = storage_df["week_ending"].max() + pd.Timedelta(days=14)
    dates = pd.date_range(start=start, end=end, freq="B")

    price = 3.0 + np.cumsum(rng.normal(0, 0.02, len(dates)))
    price_series = pd.Series(price, index=dates)

    for _, row in storage_df.iterrows():
        release_date = row["week_ending"] + pd.Timedelta(days=6)
        # find nearest trading day on/after release_date
        candidates = price_series.index[price_series.index >= release_date]
        if len(candidates) == 0:
            continue
        release_day = candidates[0]
        jump = sensitivity * row["_true_surprise"] + rng.normal(0, 0.02)
        # apply the jump from release_day onward (a level shift, like a
        # real price reaction that persists rather than mean-reverting
        # instantly)
        price_series.loc[price_series.index >= release_day] += jump

    price_series = price_series.clip(lower=0.5)
    return pd.DataFrame({"date": price_series.index, "price_usd_mmbtu": price_series.values})


def run():
    storage = make_synthetic_storage_with_surprise()
    price_daily = make_synthetic_price_reacting_to_surprise(storage)

    print("--- Testing add_expected_net_change ---")
    storage_ref = add_five_year_reference(storage)
    storage_surprise = an.add_expected_net_change(storage_ref)
    populated = storage_surprise["storage_surprise_bcf"].notna().sum()
    print(f"rows with a computed surprise: {populated} / {len(storage_surprise)}")
    assert populated > 0, "surprise never computed, expected-value alignment broken"

    print("\n--- Testing classify_storage_regime ---")
    storage_regime = an.classify_storage_regime(storage_surprise)
    print(storage_regime["storage_regime"].value_counts())
    assert set(storage_regime["storage_regime"].unique()) <= \
        {"above_avg", "below_avg", "insufficient_history"}

    print("\n--- Testing compute_price_reaction ---")
    reaction = an.compute_price_reaction(storage_regime, price_daily)
    valid_reactions = reaction["price_change_1d"].notna().sum()
    print(f"rows with a computed 1-day price reaction: {valid_reactions} / {len(reaction)}")
    assert valid_reactions > 0, "price reaction never computed"

    print("\n--- Testing build_analysis_table + summarize_correlation ---")
    analysis_table = an.build_analysis_table(storage_regime, reaction)
    stats = an.summarize_correlation(analysis_table)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # the synthetic price was built with sensitivity = -0.03, meaning a
    # more negative surprise (bigger draw than expected) should map to a
    # positive price move, i.e. the overall correlation between surprise
    # and 1-day price reaction should come back negative.
    assert stats["corr_surprise_vs_1d_reaction"] < 0, (
        "expected a negative correlation given the synthetic sensitivity "
        "was set negative, pipeline did not recover the known relationship"
    )
    print("\nRecovered the known negative surprise-to-price relationship correctly.")
    print("All synthetic phase 2 checks passed.")


if __name__ == "__main__":
    run()
