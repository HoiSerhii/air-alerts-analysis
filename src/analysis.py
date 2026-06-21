"""Analysis layer: turn the L2 marts into the Phase-1 answer.

Question: when during the day do air-raid alerts happen, and has the nocturnal
pattern changed over the war? Two views answer it:

  * hour-of-day *share* per year -- normalised so each year sums to 1, which makes
    years with very different attack volumes comparable. Answers "what fraction of
    alert time fell in each clock hour".
  * night-coverage share per year vs a uniform baseline -- the evolution metric.

The uniform baseline is the honest reference. The night window (22:00-05:59) is
8 of 24 hours, so a process with no daily pattern would spend 8/24 = 0.333 of its
time there. A night share clearly above 0.333 is a real nocturnal skew; a value
near it is not. We compare against this baseline instead of claiming a trend the
data may not support.

Caveat handled by callers: the current (latest) year is usually partial, so its
single yearly number is not directly comparable to full years.
"""
from __future__ import annotations

import pandas as pd

# 8-hour night window as a fraction of the day: the "no daily pattern" reference.
UNIFORM_NIGHT_BASELINE = 8 / 24


def hour_share_by_year(l2: dict) -> pd.DataFrame:
    """Year x hour-of-day table of shares (each row/year sums to 1)."""
    heat = l2["heat"].copy()
    year_totals = heat.groupby("year")["minutes"].transform("sum")
    heat["share"] = heat["minutes"] / year_totals
    return heat.pivot(index="year", columns="hour", values="share").fillna(0.0)


def night_share_trend(l2: dict) -> pd.DataFrame:
    """Night-coverage share per year, with the uniform baseline alongside.

    ``above_baseline`` > 0 means alert time is skewed toward night hours.
    """
    out = l2["night_share"].copy()
    out["uniform_baseline"] = UNIFORM_NIGHT_BASELINE
    out["above_baseline"] = out["night_share"] - UNIFORM_NIGHT_BASELINE
    return out


def sanity_plot(l2: dict, path: str) -> str:
    """Save a two-panel sanity PNG: hour-of-day heatmap + night-share trend.

    This is a static check that the result is sensible; the interactive dashboard
    is built separately. matplotlib is imported lazily so the core pipeline does
    not depend on it.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    share = hour_share_by_year(l2)
    trend = night_share_trend(l2)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.2))

    im = ax1.imshow(share.values, aspect="auto", cmap="magma", origin="lower")
    ax1.set_xticks(range(0, 24, 2))
    ax1.set_xticklabels(range(0, 24, 2))
    ax1.set_yticks(range(len(share.index)))
    ax1.set_yticklabels(share.index)
    ax1.set_xlabel("hour of day (Kyiv)")
    ax1.set_ylabel("year")
    ax1.set_title("Share of alert time by hour of day")
    fig.colorbar(im, ax=ax1, label="share of year's alert minutes")

    ax2.plot(trend["year"], trend["night_share"], marker="o", label="night share")
    ax2.axhline(UNIFORM_NIGHT_BASELINE, ls="--", color="gray",
                label=f"uniform baseline ({UNIFORM_NIGHT_BASELINE:.2f})")
    ax2.set_xlabel("year")
    ax2.set_ylabel("night coverage share (22:00-05:59)")
    ax2.set_title("Night share vs uniform baseline")
    ax2.set_ylim(0.30, 0.55)
    ax2.legend()

    fig.suptitle("Ukraine air-raid alerts: when during the day (oblast-union coverage)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
