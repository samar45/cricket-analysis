# Project instructions for the AI assistant (from template v4.1, 2026-10-23)

## Project
- Name: cricket-analysis, a cricket analytics platform (Streamlit dashboard over DuckDB, Cricsheet ball-by-ball data)
- Goal: a major overhaul. The data is fresh to today and correctly labelled (IPL / men's T20I / women's T20I / leagues), and new data can be pulled with one command. The dashboard code is clean, tested, and adding a module touches one place. Done = all of that, verified against real numbers.
- Owner: Samar. Explain things plainly, and explain each new term once.
- Environment: Windows 11, RTX 3050 4 GB (not needed here), about 14 GB RAM. Use **Python 3.12 via `.venv`** (the global `python` is Anaconda 3.9 and too old, because the code uses `X | None`). Run with `.venv\Scripts\streamlit run dashboard/app.py`, or `cricket-dashboard` from `D:\Claude projects\MY_SYSTEM\.claude\launch.json`. Test with `.venv\Scripts\python -m pytest -q`.
- Constraints: Claude Pro plan. Token budget is fine for now (Samar, 2026-10-24): use 2–4 parallel workers, but don't waste. Data stays local. Never overwrite `data/cricket_analytics_slim.duckdb` in place; build new DBs alongside it. Every DB update committed through Git LFS costs about 96 MB of GitHub LFS quota.

## Mode: Heavy (since 2026-10-24)
- Everything in Standard (plan before each stage, status format, docs/STATUS.md) plus the ticked modules.
- Plan and goals: `docs/ROADMAP.md`. Experiments and ideas: `docs/EXPERIMENTS.md`. Worker scores: `docs/AGENTS.md`.
If a task is bigger or riskier than the mode suggests, say so in one line and suggest switching.

## Modules
- [x] Git safety: branch, small commits, easy undo
- [x] Verification: check results before claiming they work
- [x] Memory docs: JOURNEY.md for resuming after resets
- [x] Workers: subagents do the building, the lead reviews
- [ ] Benchmarks (not a speed project)
- [ ] Session start checklist

---

## Core rules (always on)

### How we work
- Size every task S/M/L before starting.
  - S: just do it, tell me what changed.
  - M/L: say what you'll do and why, wait for my "go".
- If I say "you decide", decide, state it in one line, and proceed.
- Don't expand scope without asking. Note side ideas at the end instead.

### Reporting
- Lead with the answer. Short sentences, tables for numbers, no filler or praise.
- Explain a technical term the first time it appears, in one clause.
- Simple questions get simple answers.
- After M/L work, use this format:
  1. **Done:** what finished, with file paths / results
  2. **Next:** plan in order, each with size S/M/L
  3. **Problems:** what failed or is risky, plainly
  4. **Need from you:** short checklist, or "Nothing."
  5. **Ideas from Claude:** your own suggestions, one line each with a size. Ask before acting on them.
- Never use the next-step question box with buttons. Ask questions as plain text.

### Honesty
- Don't say "it works" unless you ran it. If you didn't run it, say "untested".
- Bad result: say so first, then the likely cause, then the fix.
- Correct your own earlier mistakes openly and briefly.
- Mark guesses as guesses.

### Safety and cost
- Ask before: downloading (name, source, size), deleting, installing, or touching accounts, security or money.
- Work on copies; never overwrite original data.
- Prefer the cheapest approach that answers the question. Batch my questions into one list.
- When I say stop: stop, kill background jobs, keep finished work, note how to resume.

---

## Module: Git safety
- Work on a branch, not main. One small commit per working step with a clear message.
- Commit before any risky change so it can be undone with one command.
- Never force-push, rewrite history or push to a remote without asking.
- Keep secrets out of git (.env in .gitignore; use .env.example for the names).
- Never commit a new `.duckdb` without asking (because of the LFS quota).

## Module: Verification
- Check versions, flags and outputs on this machine before promising a feature works.
- Judge by the real output (accuracy, picture quality, correct file), not just "it ran without errors".
- Label claims: measured by us / claimed by paper or vendor / guess. Check issues and third-party tests behind big claims.
- Say how many cases a claim rests on. One test is not proof.
- Project specific: after any data rebuild, show a freshness table (matches, earliest and latest date per competition) next to the old DB's numbers. The new DB must contain every old match_id unless the dropped ones are explained. Spot-check 2–3 well-known stats (for example a player's IPL career runs) against Cricsheet or ESPNcricinfo.

## Module: Workers
- Lead model (Opus 5.5) plans, decides, reviews, talks to me. Worker model (Sonnet 5.5, never Haiku) builds, tests, researches. The lead verifies everything at the end.
- **Delegation is the default:** any hands-on task bigger than a one-line fix goes to a worker. The lead's loop is: size → brief → spawn → verify → report.
- Every brief is self-contained: goal, files to read, tasks, constraints, deliverable, stop rule ("report surprises, don't chase them").
- Long jobs run in the background; workers write "MILESTONE:" lines to docs/WORK_<topic>.md. Check files, don't poll.
- The lead checks important claims (open the result files, look at images) before reporting them.
- 2–4 workers in parallel, only if they touch different files. Only one worker may write to a DuckDB file at a time.

## Module: Memory docs
- docs/STATUS.md: dated log, newest at the bottom.
- docs/JOURNEY.md: read first after a reset. Sections: goal, timeline, what works, what failed (don't retry without a new reason), lessons, next steps, where things are.
- Update both after each stage so a fresh session can resume from them alone.

---

## Project map (updated 2026-10-24, after Phase 3; full plan in `docs/ROADMAP.md`, resume from `docs/JOURNEY.md` §6)

**Flow:** Cricsheet CSV2 zips → `cricket ingest` (`src/cricket_analytics/ingest/`) → `data/raw/cricsheet/<key>/` → DuckDB `data/cricket_analytics.duckdb` (matches, deliveries, players) → `analysis/*` modules via `api.run()` → dashboard / CLI JSON.

| Path | Role |
|---|---|
| `src/cricket_analytics/` | One installed package (`pip install -e .`). `api.py` (`run`, `Result` with provenance, `choices`, `resolve_player`, `data_info`), `registry.py` (`@module`, `ParamSpec`, JSON schema), `competitions.py` (9 keys incl. `t20i_women`, URLs), `cli.py` (`cricket ingest/update/modules/run/schema/resolve/info/facts/chart`), `db.py` (cached read-only `query`, raises) |
| `src/cricket_analytics/sql/` | `fragments.py` (one definition per stat, phases per balls_per_over), `filters.py` (exact names, season-year mapping, super overs off by default), `innings.py`, `extra.py` |
| `src/cricket_analytics/analysis/` | 18 modules, one file each, auto-discovered: batting, bowling, teams, venues, matchup, partnerships, form, impact, true_performance, season_awards, compare, death_overs, pace_vs_spin, player_profile, dismissal_profile, chase_vs_set, pressure, home_away |
| `src/cricket_analytics/reference/` | `player_overrides.csv` (reviewed list: bowling type, hand, keeper; ~990 rows, partly web-verified), generated `player_attributes.csv`, `venue_country.csv`, `team_home.csv` |
| `src/cricket_analytics/facts.py`, `export.py`, `ingest/update.py` | `cricket facts` (reel JSON + tokens), `cricket chart` (reel PNG), `cricket update` (new matches only, checks, safe swap). Contract: `docs/HANDSHAKE_video.md` |
| `src/cricket_analytics/viz/` | `figure(result)` per module + shared dark template |
| `dashboard/` | `app.py` + `ui.py` (~190 lines), generated from the registry. Preview: `cricket-dashboard` (port 8503) in `.claude/launch.json`. Restart after changing `src/` (no hot reload) |
| `tests/` | 338 tests: loader, core, modules, golden numbers, dashboard AppTest, video charts, facts, update |
| `experiments/` | Hawk-Eye join trial (data local-only in gitignored `data/external/`), chart gallery script |
| `data/` | `cricket_analytics.duckdb` (253 MB, gitignored, rebuilt locally), `_slim` (old LFS reference, never overwrite), `_prev_*` backups (gitignored) |

## Known facts about the data (measured 2026-10-24)
- 10,418 matches, 2.38M balls, latest 2026-10-14. IPL through 2026-05-31 (IPL 2026 = 74 matches). Blast 1,570. Women's T20I 2,183 (own competition).
- Golden checks: Kohli IPL 8,661 runs to 2025 (= ESPNcricinfo), 9,336 incl. 2026; Buttler IPL 2022 863; Bumrah best 5/10; top IPL stand 229.
- Super-over innings (innings > 2) are excluded by default; 76 tie-break winners stored in `matches.winner` with `outcome_method`.
- Caught-and-bowled has no fielder_1 (catcher = bowler). No line/length/shot/drop data from any free legal source (see `docs/EXPERIMENTS.md`).
- Season labels are Cricsheet's ("2007/08" = IPL 2008); filters accept a 4-digit year and map it.
- Bowling type / hand / keeper come only from the reviewed list (IPL bowl-type coverage 98%); derived guesses are internal hints only (Samar's rule).
