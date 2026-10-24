# cricket-analysis - status (newest at the bottom)

## 2026-10-23 00:35 Data refresh paused
- Branch `overhaul`: CLAUDE.md (de8525a), ingest fix for `all_matches.csv` doubling (59e917b).
- All 8 Cricsheet zips are downloaded (~42 MB). A rebuild with the fix was in progress and got stopped, so the new DB is unverified. The app still uses the old slim DB.
- Resume: see JOURNEY.md section 6.
- Open questions for Samar:
  1. Competitions: men's T20 only, or add ODI and Test?
  2. Women's T20I: keep as its own competition, or drop?
  3. Stop committing the DB to GitHub LFS (~96 MB per update) and rebuild locally?
  4. Run the overhaul in its own session in this folder?

## 2026-10-24 Overhaul planned, Phase 0 done, Phase 1 started
- Samar's answers: Sonnet workers only (2-4 in parallel), Opus verifies at the end; tokens fine for now; download fresh data; clean the code first, then features; NLQ with Ollama; link to the Edit Pipeline (Reels) project. No question pop-up boxes; add Claude's own ideas to reports.
- Defaults (Samar didn't object): all T20 now, ODI/Test later; women's T20I as its own competition; stop committing the DB via LFS; updates run on the laptop.
- 3 read-only audits committed (47320d9): `docs/AUDIT.md`, `docs/AUDIT_video.md`, `docs/RESEARCH_data_nlq.md`. Plan: `docs/ROADMAP.md` (9 phases).
- Big correction: CSV2 already has batting_team, bowling_team, fielder_1..3, gender, balls_per_over. Our loader dropped them. No JSON switch needed.
- Phase 0: CLAUDE.md → Heavy mode + corrected facts; new `docs/EXPERIMENTS.md`, `docs/AGENTS.md`.
- Phase 1 running: builder worker (loader + schema + fresh download + new DB + verification), test worker (`tests/test_ingest.py`).

## 2026-10-24 Phase 1 done (318db73)
- New DB `data/cricket_analytics.duckdb`: 10,418 matches (old 7,935), 2.38M balls, data through 2026-10-14. IPL 2026 (74 matches) and Blast (1,570) now in.
- Verified by the lead: 0 old matches missing, identical balls/runs/wickets for all old matches, Kohli IPL 9,346, 0 wrong batting teams. 16/16 tests, dashboard 0 errors.
- `config.yaml` switched to the new DB. The .duckdb is not committed.
- Samar asked for deeper research on line/length/catch data (official sites, vendors, how analysts do it). Worker running → `docs/RESEARCH_ball_tracking.md`.

## 2026-10-24 Phase 2 done (1994dec, c850027)
- New package `cricket_analytics`: `sql/fragments.py` (one definition per stat), `sql/filters.py` (exact names, season-year mapping, super overs off by default), registry + JSON schema, `api.run` with provenance, CLI `cricket run/schema/resolve/info/modules`.
- 13 modules replace the old 15 (phase analysis and leaderboards folded into batting/bowling `group_by`; clutch renamed death_overs; pace_vs_spin marked experimental).
- Verified by the lead: 126/126 tests; Kohli IPL 8,661 to 2025 (= ESPNcricinfo), 2024 741 @ 61.75, 2025 657 @ 54.75; Buttler 2022 863; Bumrah best 5/10; top IPL stand 229.
- Old bugs found and fixed: super overs counted, non-striker run outs as not out, legal-ball and runs-conceded definitions, team side guessed, compare's per-phase highest score, impact NaN, true_performance sign flip.
- setuptools installed in .venv (Samar OK); `cricket` CLI works anywhere.
- Delete list for Phase 3 (needs Samar's yes): `modules/` (old 15, ~3,800 lines), `leagues.py`, empty `ingestion/` `preprocessing/` `notebooks/`, root `cricket_analytics.egg-info`, `requirements-ml.txt`, `requirements-nlp.txt`, unused pyproject extras/deps, unused config.yaml keys, sys.path hacks, `tests/test_modules.py`, stale README module tables.

## 2026-10-24 Phase 3 started
- Samar: go for Phase 3, delete list approved, HawkeyeStats approved as an experiment (local only, never committed or published).
- Workers: 3A dashboard rebuild + registry kinds + deletions; 3B super-over winners at ingest + competition config in one place, rebuilt into `data/cricket_analytics_new.duckdb`; 3C Hawk-Eye join trial → `docs/EXPERIMENT_hawkeye.md`.

## 2026-10-24 Phase 3 done
- Dashboard rebuilt on the registry (app.py 753 → 111 lines + ui.py 79): Overview + Explore, filters generated from module params, CSV/JSON download, provenance panel, experimental banner. Charts restyled (shared dark template, stacked panels, top-N).
- Deleted (Samar approved): old `modules/`, `leagues.py`, unused deps/extras/config keys, empty folders, old tests. All recoverable from git.
- Loader stores super-over/bowl-out winners (76 matches) + `outcome_method`; DB rebuilt and swapped in, previous kept as `data/cricket_analytics_prev_2026-10-24.duckdb`.
- Registry: bool/float params, experimental category, `include_super_overs` toggle; `api.choices` for dropdowns.
- Hawk-Eye trial: 627/628 IPL matches join, 2012–2021 only, no licence → local-only experiment.
- Lead verified: 156/156 tests, dashboard checked in the browser (Overview, Explore batting chart), new DB vs old (76 winners added, 0 other changes).

## 2026-10-24 Paused after Phase 3 (Samar: save everything, save tokens)
- All work committed on `overhaul` (not pushed). CLAUDE.md project map and data facts refreshed for the new layout.
- Dashboard preview stopped. Nothing running in the background.
- Resume: read `docs/JOURNEY.md` §6 → Phase 4 (`cricket update` + CI) waits for Samar's "go".

## 2026-10-24 Samar's dashboard feedback recorded
- Wants: glance-friendly video charts (bar/pie/donut, keep the current ones), better pace_vs_spin and death_overs, real bowler types and player roles via feature engineering, multi-select / last-N-years filters for every module.
- Planned as Phase 3.5a-d in `docs/ROADMAP.md`; feature ideas in `docs/EXPERIMENTS.md`. Work starts when Samar says go (token budget).

## 2026-10-24 Phase 3.5 started (Samar: go, run until tokens run out, resume after)
- Running in parallel: 3.5a multi/range filters (filters, registry, api, cli, batting/bowling group_by, dashboard); 3.5b player attributes (new `reference/` CSVs + `player_profile` module, Wikidata coverage check with tiny queries only); 3.5d video chart set (`viz/video/`, gallery).
- 3.5c (pace_vs_spin + death_overs rebuild) starts after 3.5b. Work log: `docs/WORK_phase3_5.md`.
- If the session stops mid-way: uncommitted worker files may be in the tree; check `git status`, run `pytest -q`, and read `docs/WORK_phase3_5.md` MILESTONE lines before continuing.
