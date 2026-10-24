# cricket-analysis - journey (read first after a reset)

## 1. Goal
A major overhaul: correct fresh data → clean modular code → modern dashboard → incremental updates + CI →
a stats bridge to the Reels pipeline (`D:\Claude projects\Edit Pipeline`) → "ask your cricket data" (Ollama) → advanced stats.
The full plan and goals are in `docs/ROADMAP.md`. Mode: Heavy, Opus leads, 2-4 Sonnet workers build.

## 2. Timeline
| Date | Step | Outcome |
|---|---|---|
| 2026-10-22 | Cloned, venv (py 3.12), dashboard runs on the slim DB | Works; 6/6 tests after a stale-test fix (39e474c, on main) |
| 2026-10-23 | Project mapped, CLAUDE.md written (de8525a) | Data stale: latest match 2026-03-20, IPL 2025-06-03, Blast 0 |
| 2026-10-23 | First rebuild | Doubled league deliveries (all_matches.csv); fixed in 59e917b; rebuild stopped (sleep) |
| 2026-10-24 | 3 audits + roadmap (47320d9), Phase 0 docs (62b4e98) | CSV2 already has batting team, fielders, gender: our loader dropped them |
| 2026-10-24 | Phase 1 data foundation (318db73) | New DB: 10,418 matches through 2026-10-14, all 7,935 old matches identical, app switched |

## 3. What works
- `data/cricket_analytics.duckdb` (253 MB, gitignored) built by `cricket ingest --db data/cricket_analytics.duckdb --no-download`.
  Has competition, gender, batting/bowling team, fielders, balls_per_over, primary keys, players table.
- Verified: 0 old match_ids missing; balls/runs/wickets identical for all 7,935 old matches; Kohli IPL 9,346 (8,671 to 2025 + 675 in 2026);
  per-season Kohli runs match known figures for 2016/2023/2024/2025 (lead's memory, not re-checked online).
- 16 tests pass (10 new loader tests on a 2-match fixture). Dashboard AppTest: 0 exceptions on the new DB.

## 4. What failed (don't retry without a new reason)
- First build doubled deliveries (all_matches.csv). Fixed.
- "Switch to JSON to get catches": not needed, CSV2 has fielder_1..3.
- Line/length/shot/drops from free sources: none found (see EXPERIMENTS.md); deeper research running.

## 5. Lessons
- "Ran without errors" ≠ correct. The doubling only showed up in the Kohli spot-check.
- Check the raw file before trusting a "the format doesn't have it" fact. Our CLAUDE.md was wrong about fielders.

## 6. Next (resume here)
1. Phase 2 core rewrite (see ROADMAP): sql/fragments + filters, plot-free analysis layer, registry, `api.run`, CLI JSON, golden tests.
   Show Samar the delete list (AUDIT.md §7) before removing anything.
2. Known data notes for Phase 2: IPL season labels are Cricsheet's ("2007/08", "2009/10", "2020/21"), add a `year`; caught-and-bowled has no fielder_1 (catcher = bowler);
   5 matches have NULL result; Hundred phase SQL still assumes 6-ball overs; slim DB date is TIMESTAMP, new is DATE.
3. Ball-tracking research: `docs/RESEARCH_ball_tracking.md` (worker running 2026-10-24).

## 7. Where things are
- Branch `overhaul`, nothing pushed. `main` also has 1 unpushed commit (39e474c).
- `config.yaml` → `data/cricket_analytics.duckdb`. Old `data/cricket_analytics_slim.duckdb` untouched (reference only).
- Raw data: `data/raw/cricsheet/<key>/`, zips of 2026-10-24 in `data/raw/_zips_2026-10-24/`.
- Docs: ROADMAP, STATUS, EXPERIMENTS, AGENTS, AUDIT, AUDIT_video, RESEARCH_data_nlq, WORK_data-refresh.
- Dashboard launch: `cricket-dashboard` in `D:\Claude projects\MY_SYSTEM\.claude\launch.json` (it uses bare `python`/`streamlit`, which resolve to Anaconda 3.9; fix pending).
