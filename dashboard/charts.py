"""
charts.py

Builds the plotly figures used by the dashboard. Kept separate from
app.py so these can be unit tested against synthetic data without needing
a running Streamlit session.
"""

import pandas as pd
import plotly.graph_objects as go


def build_storage_levels_figure(df: pd.DataFrame, selected_year: int,
                                 compare_years: list = None) -> go.Figure:
    """
    Plots the selected year's storage level against its own five year
    range band (min to max), both indexed by week of year so the
    comparison lines up regardless of which calendar year is selected.
    Optionally overlays additional prior years as thin reference lines.
    """
    year_df = df[df["year"] == selected_year].sort_values("week_of_year")

    fig = go.Figure()

    # five year range band, drawn first so it sits behind everything else
    band_df = year_df.dropna(subset=["five_yr_min_bcf", "five_yr_max_bcf"])
    if len(band_df) > 0:
        fig.add_trace(go.Scatter(
            x=band_df["week_of_year"], y=band_df["five_yr_max_bcf"],
            line=dict(width=0), showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=band_df["week_of_year"], y=band_df["five_yr_min_bcf"],
            line=dict(width=0), fill="tonexty", fillcolor="rgba(150,150,150,0.25)",
            name="5-year range", hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=band_df["week_of_year"], y=band_df["five_yr_avg_bcf"],
            line=dict(color="gray", dash="dash", width=1.5),
            name="5-year average",
        ))

    if compare_years:
        for cy in compare_years:
            cy_df = df[df["year"] == cy].sort_values("week_of_year")
            fig.add_trace(go.Scatter(
                x=cy_df["week_of_year"], y=cy_df["storage_bcf"],
                line=dict(width=1, dash="dot"), opacity=0.5,
                name=f"{cy} storage",
            ))

    fig.add_trace(go.Scatter(
        x=year_df["week_of_year"], y=year_df["storage_bcf"],
        line=dict(color="#1f77b4", width=3),
        name=f"{selected_year} storage",
    ))

    fig.update_layout(
        title=f"Lower 48 Working Gas in Storage, {selected_year} vs. 5-Year Range",
        xaxis_title="Week of year",
        yaxis_title="Storage (Bcf)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def build_price_reaction_figure(df: pd.DataFrame, reaction_col: str = "price_change_1d",
                                 regime_filter: str = "all") -> go.Figure:
    """
    Scatter plot of price reaction on the y-axis against release date on
    the x-axis, with marker color and size mapped to storage surprise
    magnitude and direction. A diverging color scale is used so a bigger
    draw than expected (negative surprise) and a bigger build than
    expected (positive surprise) read as visually distinct.
    """
    plot_df = df.dropna(subset=["storage_surprise_bcf", reaction_col]).copy()

    if regime_filter != "all":
        plot_df = plot_df[plot_df["storage_regime"] == regime_filter]

    max_abs_surprise = plot_df["storage_surprise_bcf"].abs().max() or 1
    sizes = 8 + 22 * (plot_df["storage_surprise_bcf"].abs() / max_abs_surprise)

    fig = go.Figure()
    fig.add_hline(y=0, line_dash="dot", line_color="lightgray")
    fig.add_trace(go.Scatter(
        x=plot_df["release_date"],
        y=plot_df[reaction_col],
        mode="markers",
        marker=dict(
            size=sizes,
            color=plot_df["storage_surprise_bcf"],
            colorscale="RdBu_r",
            cmid=0,
            colorbar=dict(title="Storage surprise (Bcf)<br>negative = bigger draw"),
            line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
        ),
        customdata=plot_df[["storage_surprise_bcf", "storage_regime"]],
        hovertemplate=(
            "Release date: %{x|%Y-%m-%d}<br>"
            "Price reaction: %{y:.2f} $/MMBtu<br>"
            "Storage surprise: %{customdata[0]:.1f} Bcf<br>"
            "Regime: %{customdata[1]}<extra></extra>"
        ),
    ))

    label = "1-Day" if reaction_col == "price_change_1d" else "2-Day"
    fig.update_layout(
        title=f"Henry Hub {label} Price Reaction to Storage Reports, Sized/Colored by Surprise",
        xaxis_title="Report release date",
        yaxis_title=f"{label} price change ($/MMBtu)",
    )
    return fig


def regime_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Small summary table comparing mean absolute price reaction between
    above-average and below-average storage regimes, the specific
    comparison the project's core question asks for.
    """
    rows = []
    for regime in ["above_avg", "below_avg"]:
        subset = df[df["storage_regime"] == regime].dropna(
            subset=["price_change_1d", "price_change_2d", "storage_surprise_bcf"]
        )
        if len(subset) == 0:
            continue
        rows.append({
            "Storage regime": "Above 5-yr average" if regime == "above_avg" else "Below 5-yr average",
            "Weeks": len(subset),
            "Mean |1-day reaction| ($/MMBtu)": round(subset["price_change_1d"].abs().mean(), 3),
            "Mean |2-day reaction| ($/MMBtu)": round(subset["price_change_2d"].abs().mean(), 3),
            "Corr(surprise, 1-day reaction)": round(subset["storage_surprise_bcf"].corr(subset["price_change_1d"]), 3),
        })
    return pd.DataFrame(rows)
