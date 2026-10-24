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
