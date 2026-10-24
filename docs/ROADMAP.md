# cricket-analysis - roadmap (drafted 2026-10-24, approved by Samar the same day)

Inputs: `docs/AUDIT.md` (code), `docs/AUDIT_video.md` (Edit Pipeline link), `docs/RESEARCH_data_nlq.md` (data + Ollama).
Key facts below were spot-checked by the lead on 2026-10-24 (marked ✔).

## Goals
- **Long term:** one local pipeline from Cricsheet ball-by-ball data to correct, sourced numbers that the Reels pipeline
  (`D:\Claude projects\Edit Pipeline`) and an "ask your cricket data" agent (Ollama) can use without a human typing stats.
- **Short term (Phases 0-3):** correct data, clean modular code, a modern dashboard. Adding a module = one new file.

## What we have (measured)
- 15 analysis modules (not 16), 5,700 lines, 6 tests that only check imports and the schema. ✔ 6 passed.
- Data is wrong in ways that come from our loader, not from Cricsheet:
  - ✔ The raw CSV2 files contain `batting_team`, `bowling_team` and `fielder_1..3`, plus `gender`, `team_type`, `event`
    and `balls_per_over` in the info file. Our loader drops them or reads the wrong column name (`cricsheet.py:172`).
  - So modules guess the batting side from `team1`/`team2` (✔ that's right in only 42% of matches),
    catches are unknown, IPL is mixed into T20I, and The Hundred is treated as 6-ball overs.
- The CLI only loads the basic modules (✔ `cli.py:62`, `:87`). About half of every module file is chart code.
- The Edit Pipeline types every stat by hand from Wikipedia. Its `PLAN.md` lists "stats from the cricket app" as "Waiting".
- Not available anywhere free and legal: length, line, shot type, wagon wheel, dropped catches (research §2).
  ESPNcricinfo terms ban scraping. **Catches are available** (fielder_1 is filled for ~100% of caught rows).

## Phases
| # | Phase | What "done" means | Size | Workers |
|---|---|---|---|---|
| 0 | Setup | Heavy mode, ROADMAP / EXPERIMENTS / AGENTS docs, wrong CLAUDE.md facts fixed, audits committed | S | lead |
| 1 | Data foundation | New loader keeps every useful CSV2 field; schema with primary keys and `competition`, `gender`, `batting_team`, `bowling_team`, `fielder`, `balls_per_over`; fresh download; new DB built alongside slim; verified (freshness table, all old match_ids, 3 known stats) | L | 1 builder (only one DB writer) + 1 test writer |
| 2 | Core rewrite | One package: `sql/fragments.py` (one definition per stat), `filters.py`, plot-free `analysis/`, registry with typed params, `api.run()`, `cricket run X --json`, `cricket schema --json`; redundant modules merged; a golden test per module | L | 3 (fragments+filters, analysis batch A, analysis batch B), then 1 reviewer |
| 3 | Dashboard rebuild | Modern multipage app generated from the registry, charts in `viz/`, ~150-line app file, all known UI bugs gone | L | 2 (app shell, viz) |
| 4 | Updates + CI | `cricket update`: pull `recently_added_7`/`30` zip (≈0.3-1.2 MB), load only new matches, run the checks, print a report; Windows scheduled job; GitHub Actions runs lint + tests on push (tiny fixture DB, no real DB in GitHub) | M | 2 (update cmd, CI) |
| 5 | Video bridge | `cricket facts --player X --out facts.json` with a provenance block (source, data-through date, DB version, caveats) and a versioned schema. Edit Pipeline side (tokens in `build.py`) runs in its own session | M | 1 here + 1 session there |
| 6 | Ask your data (NLQ) | Ollama tool-calling over the registry; name resolver in Python (fuzzy match, ask when ambiguous); no LLM-written SQL; 50-question eval at ≥90% right tool | L | 2 (agent, eval set) |
| 7 | Advanced analysis | Fielding (catches, run-outs, stumpings per fielder), correct Hundred phases, true batting-team stats, matchups, underrated-player finder for reels | L | 2-3 |
| 8 | Wider data (optional) | ODI / Test, DRS + replacements from JSON if wanted | M | 1 |

Line / length / shot / drops stay **blocked** until a legal source exists. Ideas go to `docs/EXPERIMENTS.md`.

## Order and why
- Phase 1 comes before the cleanup because most module bugs come from missing columns; clean code over wrong data is still wrong.
- Phases 2-3 are the "make it corporate-level" step you asked for first; no new features until they pass.
- Phase 5 before 6: the video side has a real waiting user; the NLQ agent reuses the same `api.run()` and schema.

## Rules for the multi-agent setup
- Opus (lead) plans, writes briefs, verifies every claim at the end. Sonnet 5.5 workers build. 2-4 in parallel.
- Parallel workers touch different files. Only one worker writes to a .duckdb at a time.
- Each phase ends with: lead review, pytest, real-number checks, a commit, STATUS + JOURNEY updated.
- Deletions follow `docs/AUDIT.md` §7 and are shown to Samar before they happen.

## Samar's feedback after checking the dashboard (2026-10-24) → new Phase 3.5, before Phase 4
Keep every existing chart; only add. Order decided by the lead (Samar can change it):

| # | Work | What "done" means | Size |
|---|---|---|---|
| 3.5a | **Multi-value and range filters everywhere** | `season` accepts a range or "last N years"; `venue`, `opposition`, `team` accept several values; dashboard uses multiselects; JSON schema uses arrays (NLQ-ready). "One year tells a story, five years show a pattern." | M |
| 3.5b | **Player attributes table** | `players` gets role (batter / bowler / all-rounder / keeper), batting hand, bowling type (right-arm fast, medium, off spin, leg spin, left-arm orthodox, left-arm wrist spin). Sources: features derived from our own data first, then a legal open source for styles (Wikidata is CC0, needs checking), hand-fixed CSV for gaps | M/L |
| 3.5c | **Rebuild pace_vs_spin and death_overs** | pace_vs_spin on real bowling types (split by type, not just pace/spin) and leaves "experimental"; new, simpler death-overs charts | M |
| 3.5d | **Video charts ("understand at a glance")** | A second chart set per module: one message per chart, big numbers, bar / donut / pie / single-stat card, 1080×1920 and 1080×1080 friendly, transparent background, exportable (PNG needs `kaleido`, ask before installing). Different chart type per feature, not one style for all | M |

Then Phase 4 (update + CI), 5 (video bridge, reuses 3.5d), 6 (NLQ, reuses 3.5a arrays), 7 (advanced).
