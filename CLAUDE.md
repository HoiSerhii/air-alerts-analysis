# CLAUDE.md — guardrails for working on this project

Read `spec.md` first; it is the contract and explains the *why* behind every
decision below. This file is the standing set of rules — follow it on every
session.

## What this is
A small, finished Phase-1 analysis of Ukraine air-raid alert timing
(when during the day, and how the nocturnal pattern changed). The analytical core
(`src/`, `pipeline.py`, `sanity_check.py`) is already built and verified. Your
main remaining job is the dashboard — see "Phase B" below.

## First step on a fresh machine (do this before anything else)
```
pip install -r requirements.txt
python pipeline.py        # downloads fresh data, builds + persists marts
python sanity_check.py    # must print "N passed, 0 failed" and exit 0
```
The dataset updates daily. Row-count growth and a later max date are expected.
But if any **DI** (data-shape) check fails — schema change, a new permanent
siren, a shift in the level mix — **stop and reconcile with `spec.md`**. Do not
silently adapt the code to drifted data; update the spec/invariants deliberately.

## Hard rules (do not violate)
1. **Timezone**: convert via IANA `Europe/Kyiv` only (it is in `config.py`).
   Never hardcode a +02:00/+03:00 offset — it breaks at the DST switch.
2. **Dedup is mandatory**: the raw file is ~2x duplicated for 2022–2025.
   Removing the dedup step would inflate history ~2x and fake a current-year
   drop. Keep `drop_duplicates()` in `build_l1`.
3. **Oblast union is mandatory** for any comparison over time: recording
   granularity shifted to raion in 2025–26, so raw per-year counts are not
   comparable. Always analyse on the merged oblast timeline.
4. **Permanent sirens**: exclude via the duration threshold in `config.py`
   (region-agnostic). Do not hardcode region names.
5. **The latest year is partial**: never present its single yearly number as a
   trend point without the partial-year caveat.

## Scope discipline (stay lean)
- No Docker, CI, database, or test framework. `sanity_check.py` is the gate.
- Phase 1 = alerts + time-of-day only. **Defer** attack-volume, ACLED, and weather
  data, and the per-oblast map, to later phases. The schema is built to join
  attack volume by day later without rework — but do not add it now.
- Prefer the smallest change that works over a more general abstraction.

## Phase B — your job here: the dashboard (`app.py`)
Build a simple Streamlit app that reads the persisted marts (do **not** recompute
the pipeline on every view):
- `data/processed/heat.csv`        — year × hour-of-day coverage minutes
- `data/processed/night_share.csv` — night share per year + the 0.333 baseline

Two views:
1. Hour-of-day heatmap. Normalise each year to a *share* (year sums to 1) so years
   with very different attack volumes are comparable.
2. Night-share trend vs the dashed 0.333 uniform baseline.

Label hours as Kyiv local time. Iterate on UX live. Keep it to one file.

## File map
```
src/config.py     constants (source URL, paths, Europe/Kyiv, thresholds)
src/timeutils.py  tz conversion + DST-safe interval explosion
src/data.py       L0 -> L1 (load/cache, dedup, clean, flag)
src/aggregate.py  L1 -> L2 (oblast union + coverage marts)
src/analysis.py   L2 -> answer (hour-share, night-share, sanity plot)
pipeline.py       orchestrate + persist marts
sanity_check.py   acceptance gate (DI/CP/TZ/MID/UNI/RES)
sample/           tiny committed CSV fixture for offline tests
spec.md           the contract + rationale
```

## Data attribution
Source: Vadimkin/ukrainian-air-raid-sirens-dataset (official data; volunteer data
via the eTryvoga channel). Keep the attribution in the README.
