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
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

PROCESSED_DIR = Path("data/processed")
HEAT_PATH = PROCESSED_DIR / "heat.csv"
NIGHT_PATH = PROCESSED_DIR / "night_share.csv"
UNIFORM_NIGHT_BASELINE = 8 / 24  # night window 22:00-05:59 = 8/24 of the day


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


def heatmap_fig(share: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 2.5 + 0.5 * len(share)))
    im = ax.imshow(share.values, aspect="auto", cmap="magma", origin="lower")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels(range(0, 24, 2))
    ax.set_yticks(range(len(share.index)))
    ax.set_yticklabels(share.index)
    ax.set_xlabel("hour of day (Kyiv)")
    ax.set_ylabel("year")
    fig.colorbar(im, ax=ax, label="share of year's alert time")
    fig.tight_layout()
    return fig


def night_fig(night: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(night["year"], night["night_share"], marker="o", label="night share")
    ax.axhline(UNIFORM_NIGHT_BASELINE, ls="--", color="gray",
               label=f"uniform baseline ({UNIFORM_NIGHT_BASELINE:.2f})")
    ax.set_xlabel("year")
    ax.set_ylabel("night share (22:00-05:59)")
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

    selected = st.multiselect("Years", years, default=years)
    if not selected:
        st.warning("Select at least one year.")
        st.stop()
    heat_sel = heat[heat["year"].isin(selected)]
    night_sel = night[night["year"].isin(selected)]

    st.subheader("Share of alert time by hour of day")
    st.pyplot(heatmap_fig(hour_share_by_year(heat_sel)))

    st.subheader("Night share vs uniform baseline")
    st.pyplot(night_fig(night_sel))

    st.info(
        f"Baseline 0.333: the night window (22:00–05:59) is 8/24 of the day, so a "
        f"process with no daily pattern would sit there. Values clearly above it "
        f"indicate a real nocturnal skew. Note: {latest} is a partial year — its "
        f"single value is not a trend point."
    )


if __name__ == "__main__":
    render()
