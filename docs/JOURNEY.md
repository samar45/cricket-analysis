# cricket-analysis - journey (read first after a reset)

## 1. Goal
A major overhaul. First step: refresh the data to today (Cricsheet). Then fix the labels/schema, then the app code. The full plan is in CLAUDE.md and the 2026-10-23 STATUS entry.

## 2. Timeline
| Date | Step | Outcome |
|---|---|---|
| 2026-10-22 | Cloned, venv (py 3.12), dashboard runs on the slim DB | Works; 6/6 tests after a stale-test fix (39e474c, on main) |
| 2026-10-23 | Project mapped, CLAUDE.md written (de8525a) | Data stale: latest match 2026-03-20, IPL 2025-06-03, Blast 0 |
| 2026-10-23 | Data refresh on branch `overhaul` | Download done; ingest bug fixed (59e917b); **the rebuild was stopped partway by Samar (sleep), so it is unverified** |

## 3. What works
- All 8 Cricsheet zips are downloaded and unpacked in `data/raw/cricsheet/<key>/` (about 540 MB unpacked, ~21k files), so **there's no need to download again**.
- A first build took 285 s, with 0 skipped matches. Blast now loads (1,571 matches).
- The fix in `59e917b`: the league zips contain `all_matches.csv`, which ingest treated as one more match, doubling the league deliveries (Kohli IPL runs 18,692 vs 8,671). The filter now keeps only numeric-stem files.

## 4. What failed (don't retry without a new reason)
- The first build was wrong (doubled deliveries). It was moved to the old worker's scratchpad; ignore it.

## 5. Lessons
- "Ran without errors" ≠ correct. The doubling only showed up in the Kohli spot-check.

## 6. Next (resume here)
1. `data/cricket_analytics.duckdb` (about 220 MB, last written 00:33) is **probably incomplete**, because the rebuild was killed. Delete it and rebuild from the raw files (~5 min, no download): init schema → migrate venues → ingest all 8 with **no download** (`--no-download`) → migrate teams.
2. Then do the verification in the old worker brief: the old-vs-new freshness table, every old match_id present, 0 duplicate ids, no matches without deliveries, Kohli IPL runs ≥ 8,671 (with 2026 added), IPL 2026 present, date type TIMESTAMP vs DATE, pytest, AppTest, 3 modules returning rows.
3. Only if all of that passes: set `config.yaml` → `paths.database: "data/cricket_analytics.duckdb"` and commit. Never commit the .duckdb.
4. After that: ask Samar the 4 open questions in STATUS (competitions, women's, DB-on-GitHub, separate session), then run phase 1 (labels/schema).

## 7. Where things are
- Branch `overhaul` (2 commits ahead of `main`); nothing is pushed.
- `config.yaml` still points at `data/cricket_analytics_slim.duckdb` (the old, working DB, untouched).
- Dashboard launch: `cricket-dashboard` in `D:\Claude projects\MY_SYSTEM\.claude\launch.json`.
- Work log: `docs/WORK_data-refresh.md`.
