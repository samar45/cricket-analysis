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

## 2026-10-24 Phase 3.5a-d done (7ec128b, 92be42b, f278737, a8492ed)
- 3.5a multi/range filters; 3.5b player attributes; 3.5c pace_vs_spin on reviewed types (IPL coverage 83%, stays experimental), death-overs charts, player_profile chart, Video tab; 3.5d reel charts.
- Samar hit a ConversionException: the dashboard server was started before 3.5a, so old package code ran with the new UI. Restarted; multi-season picker works. Lesson: restart Streamlit after any `src/` change.
- Error messages now plain-language (warning for bad input, "couldn't run" + technical details expander, empty-result message lists the chosen filters).
- 288 tests pass. Next: 3.5e (dynamic tags as percentages, grow reviewed list), needs Samar's yes on the list expansion and kaleido.

## 2026-10-24 3.5e done (c523d65), reviewed list 940 (3264647), handshake v1
- Player profile shows filter-aware mixes ("usually No.5–6 (52%)"); keeper/type/hand only from the reviewed list.
- Reviewed list 350 → 940; IPL bowl-type coverage 94.9% → pace_vs_spin now advanced. 291 tests pass.
- `docs/HANDSHAKE_video.md` v1: how Edit Pipeline calls this app (CLI + JSON + video PNGs), what works today vs planned (`cricket facts`, `cricket chart`).
- Running: online check of a 10% sample of the list + fill top-50 IPL gaps by web search (→ `docs/VERIFY_player_list.md`).
- Open: famous keepers (Dhoni, Buttler, Pant, de Kock) are in original rows without a keeper flag; fill after the verifier finishes. Samar: tokens short, conserve.

## 2026-10-25 Feature engineering done (4bd537d, ec8b994, 1cfb910), list checks (b6bca2c, 3cadb6f)
- New modules: dismissal_profile, chase_vs_set, pressure (per-ball match state, exact on 17,688 innings), home_away (481 venues → country, 190 team homes). 18 modules total.
- Reviewed list: 10% sample checked online (bowl_type 2.6% wrong, hands 11.7% wrong, all fixed); 48 IPL bowlers added by web search (IPL coverage 98.05%); 13 keepers flagged; 197 doubtful hands re-checked (24 fixed). 172 medium/low hands still unchecked (web-search cap) — resume list in docs/VERIFY_player_list.md.
- 323 tests pass. Dashboard restarted.
- Next: Phase 5 (`cricket facts`, `cricket chart`), Phase 4 (`cricket update` + CI), Phase 6 (NLQ).

## 2026-10-25 Phases 4 and 5 done (73cdca2, latest)
- `cricket update`: recently-added zips → new matches only → 5 checks on a temp copy → swap with backup. Round trip proven on a copy (61 matches); live DB already current. CI workflow written, untested (nothing pushed).
- `cricket facts` (reel JSON with tokens) and `cricket chart` (reel PNG); handshake v2. Lead checked Bumrah facts (187 wkts, 7.34, 5/10) and the unknown-name path.
- 338 tests pass. CLAUDE.md map refreshed.
- Next: Phase 6 NLQ (Ollama), finish 172 hand checks, Edit Pipeline side (own session), push to GitHub (needs Samar's OK).

## 2026-10-25 Phase 6 (NLQ) first version done
- `cricket ask "..."` + dashboard Ask page; local Ollama nemotron-3.5-bolt picks the module, Python resolves names (alias map), seasons/phase from the question text, numbers only from data.
- Eval (50 questions, `evals/`): module 80%, params 85% per param / 64% all-correct, clarification recall 100% but 7 false clarifications, 7 s per question warm (37 s cold load).
- Lead checked: "Buttler IPL 2022 runs" → 863 in 8 s. Branch pushed to GitHub (origin/overhaul); CI result not checked (gh not logged in).
- Next options: drop invented competitions, venue resolver, try a smaller tools model (needs OK to pull), finish 172 hand checks.

## 2026-10-25 Data health, logs, CI hardening done (839c3ab, 6808702, 5e5fa3d, 2c29683, 0fb907b, b3642e7)
- Safe update: lock check, old_data_unchanged, 8 golden numbers, look-alike skipped events, ball-count sanity; every run logged in data/runs/; `cricket health`, `cricket runs`; Data health dashboard page; docs/RUNBOOK.md.
- Logs: logs/errors.log with error ids shown in the UI; logs/ask.jsonl with 👍/👎 feedback; `cricket ask-log`.
- innings_list module (debut / last N / best); ask maps "debut" and "last N matches" in Python.
- CI: ci.yml with ruff lint + format (blocking), DB-free tests (277 pass / 111 skip), pip-audit (pillow 12.3 advisories ignored with TODO: streamlit 1.55 pins pillow<13), gitleaks; SHA-pinned actions; dependabot; pre-commit config. Lint 74 → 0.
- Pushed. First green CI run pending at time of writing.

## 2026-10-25 New rule: Samar pushes, no Claude attribution
- Samar saw "claude" listed as a contributor on GitHub (from Co-Authored-By trailers). From now on: commit locally without any Claude trailer; Claude never runs `git push`. Rule added to CLAUDE.md (Git safety) and to memory.
- 58 commits on `overhaul` (already pushed to origin) carry the trailer. Removing it means rewriting those commits and a force-push of `overhaul` — Samar's decision (see options in the chat / JOURNEY).
- Next for Samar: open the GitHub "Compare & pull request" for overhaul → main, check CI, merge.

## 2026-10-25 Option B done locally: Claude trailers stripped from overhaul
- `git filter-branch --msg-filter` removed "Co-Authored-By: Claude" and "Generated with Claude Code" lines from all 59 commits on `overhaul` (origin/main..overhaul). Files identical to before (empty diff). Backup branch: `backup/overhaul-before-trailer-strip`.
- Samar must force-push once: `git push --force-with-lease origin overhaul`.
- Note: 12 older commits already on `main` (from ~7 months ago) also carry the trailer, so GitHub may still list "claude" until those are rewritten too (needs a force-push of main — Samar's call).

## 2026-10-25 Overhaul merged into main (3983247, squash, no Claude attribution)
- Samar squash-merged PR #1 on GitHub; CI green. Local main reset to origin/main (old unpushed local commit kept as backup/old-local-main).
- Full suite on merged main: 388 passed (one earlier run had 1 failure that didn't repeat — likely a timing flake in a live test; watch for it).
- Dependabot opened 3 PRs (gitleaks-action 3.0.0, duckdb 1.5.6, pip-audit 2.10.1) — review before merging; duckdb change must be tested against the real DB.
- New work happens on branch `dev`; Claude commits locally, Samar pushes.

## 2026-10-25 Phase 7 done + ask agent v2 (dev: 052df05, 34c94cb, e3a835a..f9e53fa)
- fielding module (Dhoni IPL 158 ct / 47 st / 53 RO; all 9,720 IPL caught dismissals accounted for; Cricsheet lacks fielder on ~15% of run-outs).
- stories module (ranked reel hooks from other modules, sample guards, sources) + underrated finder (experimental heuristic, transparent components); facts.json v2 with `stories`; handshake v3. Lead checked Kohli pace/spin hook = module output.
- Ask v2: eval (64 questions incl. 8 out-of-scope) 76.5% → 98% module accuracy, 0 false clarifications, 8/8 out-of-scope.
- **Lead's held-out check (5 NEW questions not in the eval): only 2/5 handled well** (Kohli Test average → out-of-scope ✅; Rashid "at the death" → batting instead of bowling; "Pant vs left-arm spin" and "KL Rahul at Chinnaswamy" → model asked a question instead of calling a module; "most catches IPL 2024" → player_profile instead of fielding). The 98% is tuned on the eval itself — real accuracy is lower. Next: a held-out question set written separately, a fallback when the model returns no tool, routing for fielding/role words.
- Tests 423 pass; DB-free 293 pass / 130 skip; ruff clean. All commits local, no Claude lines; Samar to push dev.

## 2026-11-06 Advanced value (paused: out of tokens)
- Step 1 run expectancy + runs_added, step 2 win probability + wpa, IPL contracts file: verified by lead, committed (ecf635a + this commit).
- Impact-era WP test: isolation did not help (chase Brier +0.003 worse); pooled kept. IPL chase win rate swings 45-63% by season (2026: 63%).
- Steps 3 (WAR) and 4 (matchup predictor) stopped mid-way; partial files on branch wip/value-step3-4, untested. Resume from docs/JOURNEY.md section 6 item 0.

## 2026-11-06 Advanced value steps 3-5 done
- WAR/pWAR (runs per win 99 for IPL 2023+, 3 methods agree; Bumrah 2024 = 311 balls/20 wkts after shortened matches came back; Kohli 2016 973). Out of sample: batter pWAR r 0.06 (no skill), bowler 0.32; team win share ~ coin-flip spread.
- Matchup predictor: beats league average by ~1% log loss on 33,303 IPL 2025-26 balls; P(out) calibrated within 0.7 pts. Kohli v Bumrah middle overs 1.31 runs/ball, 3.5% out (WagonLens PDF: 1.35, 4.5%).
- Trade tool (option A, recent value): Pant/Kuldeep -> LSG +0.45 (likely better), DC -0.54 (likely worse). Lead found + fixed a bug: `team` param was swallowed by Filters (always MI); regression test added. Verdict labels overlapped on the card: wrapped.
- Tests: value tests pass (trade 23); worker full run 518.
