"""L1 -> L2: collapse to a level-invariant oblast timeline and build the marts
that answer the Phase-1 question.

The key operation is the **oblast union**. The dataset mixes oblast-, raion- and
hromada-level alerts, and the granularity shifted hard toward raion in 2025-2026
(see the confound table in spec.md). Counting raw rows over time would therefore
measure a recording change, not a behavioural one. To neutralise that, every
sub-oblast alert is folded into a single "this oblast was under alert" timeline:
overlapping intervals within an oblast are merged, so it does not matter whether
one raion or the whole oblast fired. The unit of analysis becomes
"oblast-time under alert", which is invariant to how finely alerts are recorded.

Union is done in UTC (absolute time, no DST ambiguity when merging). Merged
intervals are then converted to Kyiv local time and split into clock-hour buckets
for the timing analysis.
"""
from __future__ import annotations

import pandas as pd

from .config import NIGHT_HOURS
from .timeutils import explode_interval


def merge_intervals(intervals: list[tuple]) -> list[tuple]:
    """Merge a list of (start, end) intervals into non-overlapping, sorted ones.

    Touching or overlapping intervals are combined. Inputs must have end > start.
    This is the core of the oblast union: three overlapping raion alerts become a
    single envelope.
    """
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:           # overlaps or touches the current run
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def union_to_oblast(l1: pd.DataFrame) -> dict[str, list[tuple]]:
    """Collapse L1 rows to one merged "under alert" timeline per oblast.

    Permanent / stuck sirens are excluded first (they would otherwise swallow the
    whole timeline). Returns {oblast -> [(start_utc, end_utc), ...]}.
    """
    active = l1[~l1["is_permanent"]]
    timelines: dict[str, list[tuple]] = {}
    for oblast, group in active.groupby("oblast"):
        intervals = list(zip(group["start_utc"], group["end_utc"]))
        timelines[oblast] = merge_intervals(intervals)
    return timelines


def hourly_coverage(timelines: dict[str, list[tuple]]) -> pd.DataFrame:
    """Explode merged oblast intervals into minutes-under-alert per clock hour.

    Returns long-form rows: (oblast, hour_bucket [Kyiv wall-clock, tz-naive],
    minutes). Intervals are passed in UTC; explode_interval handles the Kyiv
    conversion in a DST-safe way.
    """
    records = []
    for oblast, intervals in timelines.items():
        for start_utc, end_utc in intervals:
            for hour_bucket, minutes in explode_interval(start_utc, end_utc).items():
                records.append((oblast, hour_bucket, minutes))
    return pd.DataFrame(records, columns=["oblast", "hour_bucket", "minutes"])


def build_l2(l1: pd.DataFrame) -> dict:
    """Build the L2 marts used by the dashboard.

    Returns a dict with:
      - "union"       : {oblast -> merged intervals}
      - "coverage"    : long-form hourly coverage (oblast, hour_bucket, minutes, ...)
      - "heat"        : year x hour-of-day total coverage minutes (heatmap source)
      - "night_share" : night-coverage fraction per year (the evolution metric)
    Coverage (time under alert) is the primary metric; it is the honest answer to
    "when am I most likely to be under alert", and it is robust to the union step.
    """
    timelines = union_to_oblast(l1)
    cov = hourly_coverage(timelines)
    cov["hour"] = cov["hour_bucket"].dt.hour
    cov["year"] = cov["hour_bucket"].dt.year
    cov["is_night"] = cov["hour"].isin(NIGHT_HOURS)

    heat = (
        cov.groupby(["year", "hour"])["minutes"].sum().reset_index(name="minutes")
    )

    def night_fraction(group: pd.DataFrame) -> float:
        total = group["minutes"].sum()
        return group.loc[group["is_night"], "minutes"].sum() / total if total else 0.0

    night_share = (
        cov.groupby("year").apply(night_fraction, include_groups=False)
        .rename("night_share").reset_index()
    )

    return {"union": timelines, "coverage": cov, "heat": heat, "night_share": night_share}
