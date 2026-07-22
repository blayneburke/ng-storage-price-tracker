"""
Streamlit dashboard for the Natural Gas Storage and Price Tracker.

Run with:
    streamlit run dashboard/streamlit_app.py

Reads artifacts/processed/analysis_weekly.csv, produced by src/analysis.py.
If that file doesn't exist yet, run src/fetch_data.py, src/clean_align.py,
and src/analysis.py first (in that order).
"""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/

import config
from data_loader import load_analysis_data, available_years
from charts import build_storage_levels_figure, build_price_reaction_figure, regime_summary_table


st.set_page_config(
    page_title="Natural Gas Storage and Price Tracker",
    layout="wide",
)


@st.cache_data
def get_data(path: str, mtime: float):
    # mtime is included as a cache key so the cache invalidates whenever
    # the underlying CSV is regenerated (e.g. after re-running analysis.py)
    return load_analysis_data(path)


def main():
    st.title("Natural Gas Storage and Price Tracker")
    st.caption(
        "How closely does the weekly EIA natural gas storage report relate to "
        "Henry Hub spot prices, and does the market react more strongly when "
        "storage is above or below its five year average?"
    )

    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        config.PROCESSED_DATA_DIR, "analysis_weekly.csv"
    )

    if not os.path.exists(data_path):
        st.error(
            f"Couldn't find {data_path}. Run src/fetch_data.py, "
            "src/clean_align.py, and src/analysis.py first, in that order."
        )
        st.stop()

    try:
        df = get_data(data_path, os.path.getmtime(data_path))
    except ValueError as e:
        st.error(str(e))
        st.stop()

    tab1, tab2, tab3 = st.tabs(["Storage Levels", "Price Reaction", "Summary & Methodology"])

    # --- Tab 1: Storage levels vs. five year range ---------------------
    with tab1:
        years = available_years(df)
        col1, col2 = st.columns([1, 2])
        with col1:
            selected_year = st.selectbox("Year", years, index=len(years) - 1)
            other_years = [y for y in years if y != selected_year]
            compare_years = st.multiselect(
                "Compare against prior years (optional)", other_years, default=[]
            )
        with col2:
            st.plotly_chart(
                build_storage_levels_figure(df, selected_year, compare_years),
                use_container_width=True,
            )

        latest = df[df["year"] == selected_year].dropna(subset=["five_yr_avg_bcf"])
        if len(latest) > 0:
            last_row = latest.iloc[-1]
            st.metric(
                label=f"Most recent week ({last_row['week_ending'].date()}) vs. 5-yr average",
                value=f"{last_row['storage_bcf']:.0f} Bcf",
                delta=f"{last_row['vs_five_yr_avg_bcf']:+.0f} Bcf ({last_row['vs_five_yr_avg_pct']:+.1f}%)",
            )

    # --- Tab 2: Price reaction around each report -----------------------
    with tab2:
        col1, col2 = st.columns([1, 1])
        with col1:
            reaction_window = st.radio(
                "Reaction window", ["1-day", "2-day"], horizontal=True
            )
        with col2:
            regime_filter = st.selectbox(
                "Storage regime filter",
                ["all", "above_avg", "below_avg"],
                format_func=lambda x: {
                    "all": "All weeks",
                    "above_avg": "Above 5-yr average only",
                    "below_avg": "Below 5-yr average only",
                }[x],
            )

        reaction_col = "price_change_1d" if reaction_window == "1-day" else "price_change_2d"
        st.plotly_chart(
            build_price_reaction_figure(df, reaction_col, regime_filter),
            use_container_width=True,
        )
        st.caption(
            "Marker color and size reflect the size of that week's storage surprise "
            "(actual net change minus the seasonally typical net change for that week). "
            "Blue markers are bigger-than-typical builds, red markers are bigger-than-typical draws."
        )

    # --- Tab 3: Summary stats and methodology ---------------------------
    with tab3:
        st.subheader("Does the market react more strongly above or below the 5-year average?")
        summary_df = regime_summary_table(df)
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        valid = df.dropna(subset=["storage_surprise_bcf", "price_change_1d", "price_change_2d"])
        overall_corr_1d = valid["storage_surprise_bcf"].corr(valid["price_change_1d"])
        overall_corr_2d = valid["storage_surprise_bcf"].corr(valid["price_change_2d"])

        c1, c2, c3 = st.columns(3)
        c1.metric("Weeks analyzed", len(valid))
        c2.metric("Corr(surprise, 1-day reaction)", f"{overall_corr_1d:.3f}")
        c3.metric("Corr(surprise, 2-day reaction)", f"{overall_corr_2d:.3f}")

        with st.expander("Data sources and access method"):
            st.markdown(
                "- **Storage**: EIA Weekly Natural Gas Storage Report, Lower 48 States, "
                "EIA API v2 route `natural-gas/stor/wkly` (`duoarea=R48`, `product=EPG0`, `process=SWO`)\n"
                "- **Price**: Henry Hub daily spot price, EIA API v2 route `natural-gas/pri/fut`, "
                "series `RNGWHHD`\n"
                f"- Pulled history: {config.YEARS_OF_HISTORY} years, rolling 5-year lookback for "
                "the seasonal average and range comparison"
            )

        with st.expander("Data dictionary"):
            st.markdown(
                "- **storage_bcf**: Lower 48 working gas in storage, billion cubic feet\n"
                "- **net_change_bcf**: week-over-week change in storage_bcf\n"
                "- **five_yr_avg_bcf / min / max**: rolling 5-year average, min, and max for the "
                "same ISO calendar week\n"
                "- **storage_surprise_bcf**: net_change_bcf minus the 5-year average net change "
                "for that week (the seasonally 'typical' move); negative means a bigger draw than "
                "typical, positive means a smaller draw or bigger build than typical\n"
                "- **storage_regime**: whether storage_bcf was above or below its own 5-year "
                "average that week\n"
                "- **price_change_1d / 2d**: change in Henry Hub spot price from the last trading "
                "day before the report's release to the release day itself (1-day) or the "
                "following trading day (2-day)"
            )

        with st.expander("Known limitations"):
            st.markdown(
                "- The storage surprise is a rolling 5-year seasonal average, not the actual "
                "analyst consensus estimate the market was positioned around ahead of each "
                "release (consensus data is typically paywalled). This is a reasonable public-data "
                "proxy, not the same thing.\n"
                "- EIA occasionally revises the prior week's storage figure. This dataset reflects "
                "the latest revision, not necessarily the number the market reacted to in real time.\n"
                "- Price reaction uses daily closes, not intraday data, so it will understate the "
                "immediate reaction relative to an intraday tick chart around the 10:30am ET release.\n"
                "- Release dates account for known EIA holiday-adjusted releases from January 2025 "
                "onward. No verified holiday schedule was available for 2021-2024, so a small "
                "number of holiday weeks in that earlier stretch may use a slightly incorrect "
                "release date."
            )


if __name__ == "__main__":
    main()
