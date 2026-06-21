"""Streamlit dashboard: Ukraine air-raid alerts — time of day.

Run:  streamlit run app.py

Reads the marts built by pipeline.py (data/processed/*.csv); it never recomputes
the pipeline. Two views:
  1. hour-of-day heatmap, each year normalised to a share so years with very
     different attack volumes are comparable;
  2. night-share-per-year vs the 0.333 "no daily pattern" baseline.

Structure note: the data/figure helpers are plain functions with no Streamlit
calls, so they can be imported and tested headless. The Streamlit UI lives in
render(), which only runs under `streamlit run app.py`.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

PROCESSED_DIR = Path("data/processed")
HEAT_PATH = PROCESSED_DIR / "heat.csv"
NIGHT_PATH = PROCESSED_DIR / "night_share.csv"
UNIFORM_NIGHT_BASELINE = 8 / 24  # night window 22:00-05:59 = 8/24 of the day

# Night window: hours 22–23 and 0–5 (8 hours total)
NIGHT_HOURS_LATE = (22, 23)   # end of day
NIGHT_HOURS_EARLY = (0, 5)    # start of day


# --------------------------- data / figure layer ---------------------------
# (pure functions, no Streamlit calls — safe to import and test)

def load_marts() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the persisted marts. Returns (heat, night)."""
    return pd.read_csv(HEAT_PATH), pd.read_csv(NIGHT_PATH)


def hour_share_by_year(heat: pd.DataFrame) -> pd.DataFrame:
    """Year x hour-of-day table of shares (each year sums to 1)."""
    totals = heat.groupby("year")["minutes"].transform("sum")
    shared = heat.assign(share=heat["minutes"] / totals)
    return shared.pivot(index="year", columns="hour", values="share").fillna(0.0)


def heatmap_fig(share: pd.DataFrame, latest_year: int):
    fig, ax = plt.subplots(figsize=(11, 2.5 + 0.5 * len(share)))
    im = ax.imshow(share.values, aspect="auto", cmap="magma", origin="lower")

    # Shade night window (22:00-05:59): two bands — late and early
    night_color = "steelblue"
    alpha = 0.15
    # Early morning: hours 0–5 → columns 0–5
    ax.axvspan(-0.5, 5.5, color=night_color, alpha=alpha, zorder=2)
    # Late night: hours 22–23 → columns 22–23
    ax.axvspan(21.5, 23.5, color=night_color, alpha=alpha, zorder=2)

    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7)
    ax.set_yticks(range(len(share.index)))
    yticklabels = [
        f"{y}*" if y == latest_year else str(y) for y in share.index
    ]
    ax.set_yticklabels(yticklabels)
    ax.set_xlabel("hour of day (Kyiv local time)")
    ax.set_ylabel("year  (* = partial)")
    fig.colorbar(im, ax=ax, label="share of year's alert time")

    night_patch = mpatches.Patch(color=night_color, alpha=0.4, label="night window (22:00–05:59)")
    ax.legend(handles=[night_patch], loc="upper right", fontsize=8,
              framealpha=0.7)
    fig.tight_layout()
    return fig


def night_fig(night: pd.DataFrame, latest_year: int):
    fig, ax = plt.subplots(figsize=(8, 4))

    full = night[night["year"] != latest_year]
    partial = night[night["year"] == latest_year]

    ax.plot(full["year"], full["night_share"], marker="o",
            color="tab:blue", label="night share (full year)")
    if not partial.empty:
        ax.plot(partial["year"], partial["night_share"], marker="o",
                markerfacecolor="white", markeredgecolor="tab:blue",
                markeredgewidth=2, color="tab:blue", ls="--",
                label=f"{latest_year} (partial year)")

    # value labels
    for _, row in night.iterrows():
        ax.annotate(f"{row['night_share']:.3f}",
                    xy=(row["year"], row["night_share"]),
                    xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=8)

    ax.axhline(UNIFORM_NIGHT_BASELINE, ls="--", color="gray",
               label=f"uniform baseline ({UNIFORM_NIGHT_BASELINE:.3f})")
    ax.set_xlabel("year")
    ax.set_ylabel("night share (22:00–05:59)")
    ax.set_ylim(0.30, 0.55)
    ax.legend()
    fig.tight_layout()
    return fig


# --------------------------------- UI --------------------------------------
# (runs only under `streamlit run app.py`)

def render() -> None:
    st.set_page_config(page_title="Ukraine Air-Raid Alerts — Time of Day",
                       layout="wide")
    st.title("Ukraine Air-Raid Alerts — Time of Day")
    st.caption(
        "When during the day do alerts happen, and how has the nocturnal pattern "
        "changed? 'Coverage' is time spent under alert, collapsed to one timeline "
        "per oblast. All hours are Kyiv local time."
    )

    if not HEAT_PATH.exists() or not NIGHT_PATH.exists():
        st.error("Marts not found. Run `python pipeline.py` first to build "
                 "data/processed/heat.csv and night_share.csv.")
        st.stop()

    heat, night = load_marts()
    years = sorted(heat["year"].unique())
    latest = max(years)

    with st.sidebar:
        st.header("Filters")
        selected = st.multiselect("Years", years, default=years)
        st.markdown("---")
        st.markdown(
            "**Night window**: 22:00–05:59 Kyiv (8/24 of the day).\n\n"
            "**Baseline 0.333**: a process with no daily pattern "
            "would put exactly 1/3 of its time in this window.\n\n"
            f"**{latest}\\***: partial year — its single value is "
            "not a trend point."
        )
        st.markdown("---")
        st.caption("Source: Vadimkin/ukrainian-air-raid-sirens-dataset")

    if not selected:
        st.warning("Select at least one year.")
        st.stop()
    heat_sel = heat[heat["year"].isin(selected)]
    night_sel = night[night["year"].isin(selected)]

    st.subheader("Share of alert time by hour of day")
    st.pyplot(heatmap_fig(hour_share_by_year(heat_sel), latest))

    st.subheader("Night share vs uniform baseline")
    st.pyplot(night_fig(night_sel, latest))

    st.info(
        f"2023–2025 night share is +0.11 to +0.13 above the 0.333 baseline — "
        f"consistent with systematic night drone campaigns. Peaks at 00:00–03:00 Kyiv. "
        f"Note: {latest} is a partial year."
    )


if __name__ == "__main__":
    render()
