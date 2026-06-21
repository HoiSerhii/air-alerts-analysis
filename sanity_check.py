"""End-to-end acceptance checks for the air-alerts pipeline.

Run with:  python sanity_check.py

Exits non-zero if any check fails, so it works as a gate: run it after the data
is (re)downloaded to confirm the structural invariants the pipeline relies on
still hold. The dataset updates daily and its recording granularity has shifted
over time, so "the data still looks the way the code assumes" is not a given.

Check groups:
  DI   data-shape invariants (raw file)
  CP   cleaning post-conditions (L1)
  TZ   timezone / DST correctness
  MID  midnight-crossing interval explosion
  UNI  oblast union
  RES  result marts
"""
from __future__ import annotations

import sys

import pandas as pd

from src.aggregate import build_l2, merge_intervals
from src.data import build_l1, load_raw
from src.timeutils import explode_interval, to_kyiv

PASSED = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    PASSED += bool(ok)
    FAILED += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def T(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def data_shape_checks(raw: pd.DataFrame) -> None:
    cols = ["oblast", "raion", "hromada", "level", "started_at", "finished_at", "source"]
    check("DI-1 schema", list(raw.columns) == cols, str(list(raw.columns)))
    check("DI-2 volume >= 271000 (grows over time)", len(raw) >= 271000, f"rows={len(raw)}")

    s = pd.to_datetime(raw["started_at"], utc=True, errors="coerce")
    f = pd.to_datetime(raw["finished_at"], utc=True, errors="coerce")
    check("DI-3 starts 2022-03-15", str(s.min().date()) == "2022-03-15", f"min={s.min()}")
    check("DI-4 no null timestamps", s.isna().sum() == 0 and f.isna().sum() == 0, "")
    check("DI-5 level domain",
          set(raw["level"].dropna().unique()) <= {"oblast", "raion", "hromada"}, "")

    by_year = raw.assign(_y=s.dt.year).groupby("_y")["level"]
    osh = by_year.apply(lambda x: (x == "oblast").mean())
    rsh = by_year.apply(lambda x: (x == "raion").mean())
    check("DI-6 granularity confound holds",
          osh.get(2022, 0) > 0.7 and osh.get(2025, 1) < 0.35 and rsh.get(2026, 0) > 0.8,
          f"oblast_share={osh.round(2).to_dict()}")

    check("DI-7 25 oblasts, Luhansk present, Crimea absent",
          raw["oblast"].nunique() == 25
          and raw["oblast"].str.contains("Luhan", case=False, na=False).any()
          and not raw["oblast"].str.contains("Crim|Krym", case=False, na=False).any(), "")

    dur = (f - s).dt.total_seconds() / 60
    check("DI-8 outliers present (end<=start and a permanent siren)",
          (dur <= 0).sum() > 0 and dur.max() / 1440 > 100,
          f"end<=start={(dur <= 0).sum()}, max={dur.max() / 1440:.0f} days")

    # DI-9: ~2x full-row duplication in historical years, fully removable.
    dup = raw.assign(_y=s.dt.year, _d=raw.duplicated(keep=False))
    dup_share_2023 = dup.loc[dup["_y"] == 2023, "_d"].mean()
    check("DI-9 ~2x historical duplication, removable",
          dup_share_2023 > 0.9 and raw.drop_duplicates().duplicated().sum() == 0,
          f"dup_share_2023={dup_share_2023:.2f}")


def cleaning_checks(l1: pd.DataFrame) -> None:
    check("CP no invalid remain (all end>start)", (l1["duration_min"] > 0).all(),
          f"min_dur={l1['duration_min'].min():.3f} min")
    check("CP permanent sirens flagged", int(l1["is_permanent"].sum()) >= 1,
          f"n_perm={int(l1['is_permanent'].sum())}")
    check("CP Kyiv columns present", {"start_kyiv", "end_kyiv"} <= set(l1.columns), "")


def time_checks() -> None:
    sk, wk = to_kyiv(T("2023-07-01 12:00")), to_kyiv(T("2023-01-01 12:00"))
    check("TZ-1 summer 12:00Z->15:00, winter->14:00", sk.hour == 15 and wk.hour == 14, "")
    check("TZ-2 offset is DST-live (not hardcoded)", sk.utcoffset() != wk.utcoffset(), "")

    b = explode_interval(T("2023-07-01 20:30"), T("2023-07-01 22:15"))  # 23:30->01:15 Kyiv
    got = {k.strftime("%H:%M"): round(v, 1) for k, v in sorted(b.items())}
    check("MID-1 midnight split + sums to duration",
          got == {"23:00": 30.0, "00:00": 60.0, "01:00": 15.0}
          and abs(sum(b.values()) - 105) < 1e-6, str(got))

    try:
        d = explode_interval(T("2023-10-29 00:00"), T("2023-10-29 03:00"))  # autumn fall-back
        check("MID-2 DST fall-back explode (no crash, sums right)",
              abs(sum(d.values()) - 180) < 1e-6, f"{sum(d.values()):.0f} min")
    except Exception as exc:  # noqa: BLE001
        check("MID-2 DST fall-back explode", False, f"raised: {exc}")


def union_checks(l1: pd.DataFrame, l2: dict) -> None:
    iv = [(T("2024-01-01 10:00"), T("2024-01-01 11:00")),
          (T("2024-01-01 10:30"), T("2024-01-01 12:00")),
          (T("2024-01-01 11:45"), T("2024-01-01 12:30"))]
    check("UNI-1 overlapping raion alerts -> single envelope",
          merge_intervals(iv) == [(T("2024-01-01 10:00"), T("2024-01-01 12:30"))], "")

    raw_year = l1.assign(_y=l1["start_kyiv"].dt.year).groupby("_y").size()
    merged_year = pd.Series(
        [to_kyiv(st).year for ivs in l2["union"].values() for st, _ in ivs]
    ).value_counts().sort_index()
    ratio = raw_year / merged_year
    check("UNI-2 union collapses raion-era inflation (ratio_2026 >> ratio_2023)",
          ratio.get(2026, 1) > 1.5 * ratio.get(2023, 1),
          f"ratio_2023={ratio.get(2023):.2f}, ratio_2026={ratio.get(2026):.2f}")


def result_checks(l2: dict) -> None:
    cov = l2["coverage"]
    check("RES coverage minutes positive", (cov["minutes"] > 0).all(), "")
    check("RES coverage spans all 24 hours", sorted(cov["hour"].unique()) == list(range(24)), "")
    check("RES night_share in (0,1) per year", l2["night_share"]["night_share"].between(0, 1).all(), "")


def main() -> None:
    print("Loading data and building marts ...")
    raw = load_raw()
    l1 = build_l1(raw, verbose=False)
    l2 = build_l2(l1)

    print("\n== data-shape (DI) ==");  data_shape_checks(raw)
    print("\n== cleaning (CP) ==");    cleaning_checks(l1)
    print("\n== time (TZ/MID) ==");    time_checks()
    print("\n== union (UNI) ==");      union_checks(l1, l2)
    print("\n== results (RES) ==");    result_checks(l2)

    print(f"\n=== {PASSED} passed, {FAILED} failed ===")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
