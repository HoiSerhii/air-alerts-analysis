# Spec — Ukraine Air-Raid Alerts: Time-of-Day Analysis (Phase 1)

A small, finished analysis that answers one question honestly, with a reproducible
pipeline and a simple dashboard. This file is the contract: it records not just
*what* was decided but *why*, so the decisions survive being handed to another
environment (e.g. Claude Code) without being silently undone.

## 1. Question (intent)

**When during the day do air-raid alerts happen, and has the nocturnal pattern
changed over the course of the war?**

Framing: separate the part of the alert regime that is *structured* (and therefore
useful for civilian preparedness) from the part that is irreducibly unpredictable.
We do **not** try to forecast attacks — the timing is partly adversarial, so a
forecast would be both unsound and inappropriate. We characterise the stable
structure (hour-of-day, year-over-year) and are honest about uncertainty.

## 2. Non-goals (Phase 1)

- No forecasting / prediction of attacks.
- No additional data sources yet (attack volume, ACLED, weather) — these are
  later phases and the schema is designed to join them by day without rework.
- No map / per-oblast view yet (a later iteration; raion/hromada columns are
  retained in L1 for it).
- No Docker, CI, database, or test framework. The acceptance gate is one script.

## 3. Data source

- Vadimkin/ukrainian-air-raid-sirens-dataset, file `official_data_en.csv`
  (transliterated region names keep the project English-only).
- Interval data: one row per alert with `started_at` / `finished_at` in **UTC**.
- The full dataset is **never committed** (gitignored, ~28 MB, updates daily).
  A small `sample/` fixture is committed so logic can be tested offline; the real
  run downloads a fresh copy.

## 4. Data contract (L1)

`build_l1()` produces the canonical event table every downstream step reads:

| column | meaning |
|---|---|
| `oblast`, `raion`, `hromada` | region; sub-oblast fields blank for oblast-level rows |
| `level` | `oblast` / `raion` / `hromada` — the recording granularity of the row |
| `source` | always `official` |
| `start_utc`, `end_utc` | parsed UTC timestamps |
| `start_kyiv`, `end_kyiv` | Kyiv local time (IANA `Europe/Kyiv`, DST-aware) |
| `duration_min` | minutes |
| `is_permanent` | flagged stuck/permanent siren (excluded from analysis) |
| `is_naive_30` | exact-30-min row (rare in official data; flagged, not dropped) |

## 5. Key decisions & rationale

These are the load-bearing decisions. **Do not undo them without re-reading why.**

### 5.1 Oblast union (mandatory)
The recording granularity shifted from oblast to raion over time, so raw row
counts are **not** comparable across years. Verified level share by year:

| year | oblast | raion | hromada |
|---|---|---|---|
| 2022 | 0.78 | 0.05 | 0.17 |
| 2023 | 0.94 | 0.00 | 0.06 |
| 2024 | 0.83 | 0.00 | 0.17 |
| 2025 | 0.29 | 0.56 | 0.15 |
| 2026 | 0.01 | 0.92 | 0.07 |

Fix: collapse every sub-oblast alert into one "oblast under alert" timeline
(merge overlapping intervals per oblast). The unit of analysis becomes
oblast-time-under-alert, invariant to recording granularity. Effect (raw deduped
rows vs merged oblast intervals): the ratio rises from ~1.06 (2023, oblast era)
to ~5.0 (2026, raion era) — i.e. ~5 raw rows collapse into 1 oblast envelope.

### 5.2 Exact-duplicate removal (mandatory)
The raw file contains ~2 identical copies of almost every record for 2022–2025
(duplicate share ≈ 1.0 by year), while the current year is only partly doubled.
Two alerts for the same region with identical start *and* end timestamps are not
physically meaningful, so dropping exact full-row duplicates is safe. **Leaving
them in would inflate historical counts ~2x and create a fake current-year drop.**

### 5.3 Permanent / stuck sirens (excluded by threshold)
Some records never receive an end signal and run for hundreds of days (observed
in Dnipropetrovska and Kharkivska oblasts; ~600-day max). Detected by a duration
threshold (`PERMANENT_THRESHOLD_DAYS = 7`), **not** by hardcoding regions, so it
generalises. The longest genuine mass attacks run ~30 h.

### 5.4 Coverage (primary) vs starts (secondary)
"Coverage" = time spent under alert per Kyiv clock hour (intervals exploded
hour-by-hour) is the primary metric: it answers "when am I most likely to be under
alert" and is robust to the union. Alert *starts* are a valid secondary view but
weight a 10-min and a 6-h alert equally, and are more polluted by sub-oblast
granularity, so the evolution claim leans on coverage.

### 5.5 Timezone (Europe/Kyiv, DST-safe)
Timestamps are UTC; the question is about Kyiv local time. Conversion always goes
through IANA `Europe/Kyiv` (never a hardcoded offset), and interval explosion
steps in UTC and converts per step, which is DST-safe (flooring a tz-aware Kyiv
time raises during the autumn fall-back hour).

### 5.6 Night baseline = 0.333
The night window (22:00–05:59) is 8/24 of the day, so a process with no daily
pattern would put 0.333 of its time there. Night share is always reported against
this baseline; only values clearly above 0.333 indicate a real nocturnal skew.

## 6. Acceptance checks

`python sanity_check.py` runs the full gate (groups DI / CP / TZ / MID / UNI /
RES) and exits non-zero on any failure. Re-run it after a fresh download: the
dataset updates daily, so structural drift (schema change, new permanent siren,
level-mix shift) must be caught and reconciled with this spec rather than silently
absorbed. Row-count growth and a later max date are expected and fine.

## 7. Results so far

Peak alert hours by year shift from a mixed day/night profile to a clearly
nocturnal one:

- 2022: peaks at 22:00 and 13:00–14:00 (mixed; early-war daytime strikes).
- 2023–2025: peaks at 00:00–03:00; night share +0.11 to +0.13 over the 0.333
  baseline (a real nocturnal skew, consistent with night drone campaigns).
- 2026: flatter and near baseline — **partial year (Jan–Jun)**, so its single
  yearly number is not compared directly to full years.

Caveat: the current/latest year is always partial; never read its yearly value as
a trend point without this caveat.

## 8. Architecture

`L0 raw -> L1 canonical events -> L2 marts` (a lightweight medallion pattern).
All cleaning and time conversion live in L1; everything downstream reads the
contract table.

```
src/config.py     constants: source URL, paths, Europe/Kyiv, thresholds, night window
src/timeutils.py  timezone conversion + DST-safe interval explosion (the danger zone)
src/data.py       L0 -> L1: load/cache, dedup, clean, flag
src/aggregate.py  L1 -> L2: oblast union + hourly coverage marts
src/analysis.py   L2 -> answer: hour-share, night-share vs baseline, sanity plot
pipeline.py       orchestrate + persist marts to data/processed/
sanity_check.py   end-to-end acceptance gate
app.py            Streamlit dashboard (skeleton provided; polished in Claude Code)
```

Commands: `python pipeline.py` (build), `python sanity_check.py` (verify),
`streamlit run app.py` (dashboard).
