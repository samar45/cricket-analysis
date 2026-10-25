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
| 2026-10-24 | Phase 2 core rewrite (1994dec, c850027) | 15 old modules → 13 plot-free modules in `src/cricket_analytics/analysis/` + `viz/`; 126 tests; numbers now match official records |
| 2026-10-24 | Phase 3 dashboard + cleanup (09467b8, f31492c, latest viz commit) | Dashboard 753 → 190 lines, built from the registry; old code deleted; super-over winners stored; charts polished; Hawk-Eye trial done (local only) |

## 3. What works
- `data/cricket_analytics.duckdb` (253 MB, gitignored) built by `cricket ingest --db data/cricket_analytics.duckdb --no-download`.
  Has competition, gender, batting/bowling team, fielders, balls_per_over, primary keys, players table.
- Verified: 0 old match_ids missing; balls/runs/wickets identical for all 7,935 old matches; Kohli IPL 9,346 (8,671 to 2025 + 675 in 2026);
  per-season Kohli runs match known figures for 2016/2023/2024/2025 (lead's memory, not re-checked online).
- 156 tests pass (loader, core, 13 modules, golden numbers, dashboard AppTest for every module). Dashboard AppTest: 0 exceptions on the new DB.

## 4. What failed (don't retry without a new reason)
- First build doubled deliveries (all_matches.csv). Fixed.
- "Switch to JSON to get catches": not needed, CSV2 has fielder_1..3.
- Line/length/shot/drops from free sources: none found (see EXPERIMENTS.md); deeper research running.

## 5. Lessons
- Streamlit does not reload package code: after changing `src/`, restart the dashboard or users see old/new code mixed (caused a crash report on 2026-10-24).
- "Ran without errors" ≠ correct. The doubling only showed up in the Kohli spot-check.
- Check the raw file before trusting a "the format doesn't have it" fact. Our CLAUDE.md was wrong about fielders.

## 6. Next (resume here)
0. **Phase 6 NLQ v1 done (2026-10-25)**: `cricket ask`, eval 80% module accuracy. Next: improve NLQ (see STATUS), Edit Pipeline side, 172 hand checks.
   Earlier: **Phases 4 + 5 done (2026-10-25)**: `cricket update`, `cricket facts`, `cricket chart`. Next: Phase 6 NLQ.
   Earlier: **Phase 3.5 + feature engineering done (2026-10-25)**: 18 modules incl. dismissal_profile, chase_vs_set, pressure, home_away; reviewed list 940+ players, partly web-verified. Next: Phase 5 facts/chart CLI, Phase 4 update+CI, Phase 6 NLQ. Unchecked hands: docs/VERIFY_player_list.md.
   Older: **Phase 3.5a-d done.** Next 3.5e (ROADMAP bottom): dynamic tags as filter-aware percentages; keeper + bowling type only from the reviewed list; grow it to ~1,000 bowlers.
   Old note: **Phase 3.5 first** (Samar's dashboard feedback, see ROADMAP bottom): multi/range filters, player attributes (role, hand, bowling type), rebuild pace_vs_spin + death_overs, video-style charts.
1. Phase 4: `cricket update` (pull Cricsheet "recently added" zip, load only new matches, run checks, swap DB safely while the dashboard may hold it open) + GitHub Actions running tests on a fixture DB.
2. Phase 5 video bridge (`cricket facts`), Phase 6 NLQ, Phase 7 advanced stats (see ROADMAP).
3. Known: Streamlit doesn't hot-reload package code; restart the server after changing `src/`. DB backups `data/cricket_analytics_prev_*.duckdb` are gitignored.

## 7. Where things are
- Branch `overhaul`, nothing pushed. Dashboard: preview `cricket-dashboard` (port 8503) in this repo's `.claude/launch.json`. `main` also has 1 unpushed commit (39e474c).
- `config.yaml` → `data/cricket_analytics.duckdb`. Old `data/cricket_analytics_slim.duckdb` untouched (reference only).
- Raw data: `data/raw/cricsheet/<key>/`, zips of 2026-10-24 in `data/raw/_zips_2026-10-24/`.
- Docs: ROADMAP, STATUS, EXPERIMENTS, AGENTS, AUDIT, AUDIT_video, RESEARCH_data_nlq, WORK_data-refresh.
- Dashboard launch: `cricket-dashboard` in `D:\Claude projects\MY_SYSTEM\.claude\launch.json` (uses the absolute `.venv` streamlit.exe, fine). The repo's own `.claude/launch.json` uses bare `streamlit`/`python`, which resolve to Anaconda 3.9; fix pending.
