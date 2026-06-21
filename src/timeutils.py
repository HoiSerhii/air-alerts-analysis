"""Time handling: the single place where timezone conversion and interval
explosion happen.

This module is isolated on purpose. Time is the main source of silent bugs in
this dataset: timestamps are stored in UTC, but the question ("when during the
day do alerts happen?") is about Kyiv local time, alerts cross midnight, and
Ukraine observes daylight-saving time. Keeping all of that in one file means
there is exactly one place to audit when a result looks wrong.
"""
from __future__ import annotations

import pandas as pd

from .config import KYIV_TZ


def to_kyiv(ts):
    """Convert UTC, timezone-aware timestamps to Kyiv local time.

    Works on a single ``pd.Timestamp`` or a ``pd.Series`` of timestamps.
    Conversion goes through the IANA zone ``Europe/Kyiv``, so DST is handled
    automatically (summer = UTC+3, winter = UTC+2).
    """
    if isinstance(ts, pd.Series):
        return ts.dt.tz_convert(KYIV_TZ)
    return ts.tz_convert(KYIV_TZ)


def explode_interval(start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> dict:
    """Split one alert interval into minutes-per-Kyiv-clock-hour.

    Operates on UTC instants and labels each bucket by the Kyiv wall-clock hour
    it falls in. Returns ``{hour_bucket -> minutes}`` where ``hour_bucket`` is a
    tz-naive timestamp representing a Kyiv wall-clock hour (e.g. 2023-07-01 23:00).
    Intervals that cross midnight are handled correctly and the minutes always sum
    to the interval's duration.

    Why step in UTC and convert per step, instead of flooring a Kyiv timestamp:
    converting a UTC instant to a zone is always unambiguous, whereas flooring a
    tz-aware Kyiv time *raises* during the autumn fall-back hour (when 03:00 occurs
    twice). This makes the explosion DST-safe by construction.

    Known limitation: during the two yearly DST transitions, the repeated/skipped
    hour is attributed by wall-clock label, so a single hour per year may be
    counted slightly off. This is negligible once aggregated over the full period.
    """
    if end_utc <= start_utc:
        return {}
    buckets: dict = {}
    cur = start_utc
    while cur < end_utc:
        kyiv = cur.tz_convert(KYIV_TZ)
        mins_into_hour = kyiv.minute + kyiv.second / 60 + kyiv.microsecond / 6e7
        step = pd.Timedelta(minutes=60 - mins_into_hour)
        seg_end = min(cur + step, end_utc)
        bucket = pd.Timestamp(
            year=kyiv.year, month=kyiv.month, day=kyiv.day, hour=kyiv.hour
        )
        buckets[bucket] = buckets.get(bucket, 0.0) + (seg_end - cur).total_seconds() / 60.0
        cur = seg_end
    return buckets
