# Project instructions for the AI assistant (from template v4.1, 2026-10-23)

## Project
- Name: cricket-analysis, a cricket analytics platform (Streamlit dashboard over DuckDB, Cricsheet ball-by-ball data)
- Goal: a major overhaul. The data is fresh to today and correctly labelled (IPL / men's T20I / women's T20I / leagues), and new data can be pulled with one command. The dashboard code is clean, tested, and adding a module touches one place. Done = all of that, verified against real numbers.
- Owner: Samar. Explain things plainly, and explain each new term once.
- Environment: Windows 11, RTX 3050 4 GB (not needed here), about 14 GB RAM. Use **Python 3.12 via `.venv`** (the global `python` is Anaconda 3.9 and too old, because the code uses `X | None`). Run with `.venv\Scripts\streamlit run dashboard/app.py`, or `cricket-dashboard` from `D:\Claude projects\MY_SYSTEM\.claude\launch.json`. Test with `.venv\Scripts\python -m pytest -q`.
- Constraints: Claude Pro plan, so keep Claude usage low. Data stays local. Never overwrite `data/cricket_analytics_slim.duckdb` in place; build new DBs alongside it. Every DB update committed through Git LFS costs about 96 MB of GitHub LFS quota.

## Mode: Standard
- Plan before each stage, use the status format, and keep docs/STATUS.md.
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
- Lead model (Opus 5.5) plans, decides, reviews, talks to me. Worker model (Sonnet 5.5) builds, tests, researches.
- **Delegation is the default:** any hands-on task bigger than a one-line fix goes to a worker. The lead's loop is: size → brief → spawn → verify → report.
- Every brief is self-contained: goal, files to read, tasks, constraints, deliverable, stop rule ("report surprises, don't chase them").
- Long jobs run in the background; workers write "MILESTONE:" lines to docs/WORK_<topic>.md. Check files, don't poll.
- The lead checks important claims (open the result files, look at images) before reporting them.
- Parallel workers only if they touch different files. Only one worker may write to a DuckDB file at a time.

## Module: Memory docs
- docs/STATUS.md: dated log, newest at the bottom.
- docs/JOURNEY.md: read first after a reset. Sections: goal, timeline, what works, what failed (don't retry without a new reason), lessons, next steps, where things are.
- Update both after each stage so a fresh session can resume from them alone.

---

## Project map (checked 2026-10-23)

**Flow:** Cricsheet CSV2 zips → `ingestion/cricsheet.py` → `data/raw/cricsheet/<key>/` → DuckDB `matches` + `deliveries` → `modules/*` (SQL via `db.query`, read-only) → `dashboard/app.py`.

| Path | Role |
|---|---|
| `src/cricket_analytics/` | `cli.py` (`cricket setup / ingest / modules / run`), `config.py` (paths from `config.yaml`, absolute, so it doesn't depend on the working directory), `db.py` (6-table schema, `query()`), `leagues.py` (8 competitions, Cricsheet URLs, SQL filters) |
| `ingestion/cricsheet.py` | Downloads the zips and loads the CSVs. Skips the download if the raw folder isn't empty. `INSERT OR IGNORE` on match_id |
| `preprocessing/` | Team and venue alias maps. Only venues get normalised at ingest |
| `modules/` | 16 analysis modules: basic B1–B6, intermediate I1–I4, advanced A1–A5. Each is a `BaseModule` subclass registered with `@register_module`. Params are in `modules/base.py` (`format=None` means no filter) |
| `dashboard/app.py` | 753 lines. Adding a module means touching `MODULE_NAV`, `MODULE_DESC` and a `_filters_XX` function |
| `data/cricket_analytics_slim.duckdb` | 96 MB, Git LFS. Only `matches` (7,935) + `deliveries` (1.8M), **with no primary key**. Nothing in the repo builds it |

## Known facts about the data (measured 2026-10-23)
- Latest match: **2026-03-20**. IPL ends at **2025-06-03**. BBL / SA20 end at 2026-01-25, CPL at 2025-09-21, PSL at 2025-05-25, Hundred at 2025-08-31.
- **T20 Blast has 0 matches** even though it's configured.
- IPL is stored as `format='T20'`. The "T20 International" filter therefore also returns IPL, 1,844 women's matches, and associate-nation series. There is no gender column.
- `deliveries.fielder` is NULL in all 1.8M rows. CSV2 has no fielder field (the JSON format does).
- Phase SQL (overs 0–5 / 6–14 / 15–19) is copy-pasted in about 8 modules and assumes 20 overs, so The Hundred is probably wrong.
- A full Cricsheet refresh is about **42 MB** (8 zips, Last-Modified 2026-10-07 to 10-14). `recently_added_30_male_csv2.zip` is about 1 MB, for incremental updates.
- Open bugs: `modules/basic/team_performance.py:62` title shows "None"; 8× deprecated `use_container_width` in `app.py`; `except Exception: return []` hides DB errors (`app.py:108–179`); tournament names are garbled ("Men�s").
