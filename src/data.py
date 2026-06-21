"""L0 -> L1: load the raw alert CSV (cached) and build the canonical event table.

L1 is the single "contract" table the rest of the project reads from. All
cleaning, deduplication, flagging and timezone conversion happen here and only
here, so downstream code never touches raw data and there is one auditable place
for data-quality decisions.
"""
from __future__ import annotations

import urllib.request

import pandas as pd

from . import config
from .timeutils import to_kyiv

# Columns kept in the L1 contract table. raion/hromada are retained for a future
# map view; the Phase-1 question (timing) only needs oblast + level.
L1_COLUMNS = [
    "oblast", "raion", "hromada", "level", "source",
    "start_utc", "end_utc", "start_kyiv", "end_kyiv",
    "duration_min", "is_permanent", "is_naive_30",
]


def load_raw(force: bool = False) -> pd.DataFrame:
    """Return the raw dataset, downloading and caching it on first use.

    The full dataset is never committed (gitignored, updates daily), so a fresh
    copy is fetched from the source when the local cache is missing or ``force``
    is set.
    """
    if force or not config.RAW_PATH.exists():
        config.RAW_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(config.RAW_URL, config.RAW_PATH)
    return pd.read_csv(config.RAW_PATH)


def build_l1(raw: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Transform raw rows into the canonical L1 event table.

    Steps (row counts are logged at every stage for reconciliation, check CP-1):
      1. parse timestamps as UTC
      2. drop exact-duplicate rows
      3. compute duration and quality flags
      4. drop invalid rows where end <= start          (check CP-2)
      5. flag permanent / stuck sirens                 (check CP-3) — kept, marked
      6. count exact-30-min "naive" rows               (check CP-4) — kept, marked
      7. add Kyiv local-time columns
    """
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    n0 = len(raw)
    log(f"[L1] raw rows: {n0}")

    df = raw.copy()
    df["start_utc"] = pd.to_datetime(df["started_at"], utc=True)
    df["end_utc"] = pd.to_datetime(df["finished_at"], utc=True)

    # 2. exact-duplicate removal.
    # IMPORTANT: this is essential, not cosmetic. The source systematically
    # contains ~2 copies of almost every record from 2022-2025, while the
    # current year is only partly doubled. Leaving duplicates in would inflate
    # all historical counts and coverage by ~2x and produce a *fake* halving in
    # the current year. Two distinct alerts for the same region with identical
    # start AND end timestamps are not physically meaningful, so dropping exact
    # full-row duplicates is safe. Do not remove this step.
    df = df.drop_duplicates()
    log(f"[L1] after dedup: {len(df)}  (removed {n0 - len(df)})")

    # 3. duration + quality flags
    df["duration_min"] = (df["end_utc"] - df["start_utc"]).dt.total_seconds() / 60.0
    is_invalid = df["duration_min"] <= 0
    df["is_permanent"] = (
        df["duration_min"] > config.PERMANENT_THRESHOLD_DAYS * 24 * 60
    )
    df["is_naive_30"] = df["duration_min"] == 30.0  # CP-4: report, do not drop

    log(f"[L1] exact-30-min 'naive' rows: {int(df['is_naive_30'].sum())} "
        f"(flagged, not dropped)")

    # 4. drop invalid (end <= start)
    n_invalid = int(is_invalid.sum())
    df = df[~is_invalid].copy()
    log(f"[L1] dropped end<=start: {n_invalid}  -> {len(df)}")

    # 5. flag permanent / stuck sirens (kept; excluded later by aggregation)
    n_perm = int(df["is_permanent"].sum())
    perm_oblasts = sorted(df.loc[df["is_permanent"], "oblast"].unique().tolist())
    log(f"[L1] permanent/stuck sirens flagged: {n_perm}  oblasts={perm_oblasts}")

    # 7. Kyiv local time
    df["start_kyiv"] = to_kyiv(df["start_utc"])
    df["end_kyiv"] = to_kyiv(df["end_utc"])

    out = df[L1_COLUMNS].reset_index(drop=True)
    log(f"[L1] final L1 rows: {len(out)}")
    return out
