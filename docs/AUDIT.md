# Code audit: cricket-analysis (2026-10-24, branch `overhaul`, read-only)

Label key: **measured** = I ran it or queried the DB; **read** = from reading the code; **guess** = not verified.

## 1. Summary

- Real module count is **15**, not 16 (B1-B6, I1-I4, A1-A5). The dashboard shows 15 pages + Overview = 16 nav entries.
- 5,725 Python lines. About half of every module file is Plotly chart code, so analysis cannot be called without importing the UI library.
- The same SQL (phase buckets, wicket kinds, legal balls, runs conceded, strike rate) is copy-pasted ~35 times with small differences, so the same stat gives different numbers in different modules.
- Root-cause schema gap: `deliveries` has no `batting_team` / `bowling_team`, so modules guess the batting side from `team1`/`team2` (wrong; see F1). No gender or competition column either.
- Tests: **6 passed**, but they only check the schema and the registry. No module SQL is executed anywhere, and ingestion, CLI, dashboard and filters have zero tests.

## 2. Module inventory

Lines = file length. "Params" = fields of `ModuleParams` actually used, plus `extra` keys. All modules also accept `format` (really a competition label) and `season`. All 15 build a `ModuleParams` -> SQL -> DataFrame, and all except B3 have a Plotly `plot()`.

| ID | File (lines) | Computes | Params | Overlap / duplication |
|---|---|---|---|---|
| B1 | basic/batting.py (189) | Per-batter career: innings, NOs, runs, HS, avg, SR, 50s/100s, ducks, 4s/6s, dot%, boundary% | player, team, venue, phase | Batting avg/SR re-derived in B5, B6, I1, I3, A1, A4. B1 counts `was_out` per match (any dismissal), B5/B6 count `player_out = batter` per ball. |
| B2 | basic/bowling.py (200) | Per-bowler: wickets, runs conceded, avg, econ, SR, dot%, boundary%, wides/no-balls | player, team, venue, phase | Economy/wicket logic repeated in B5, B6, I1, I3, I4, A1, A3, A4, A5. `dot_ball_pct` divides by all balls incl. wides; I1/B5-economy divide by legal balls. |
| B3 | basic/team_performance.py (67) | Team W/L/NR, win%, toss wins, wins after toss win | team, venue | Win% also computed in B6 `_team_records` and in app.py `_overview_data`. Three different denominators (all matches vs decisive only). |
| B4 | basic/head_to_head.py (211) | Batter-vs-bowler: balls, runs, dismissals, SR, dot%, boundary%, economy | player (batter), player2 (bowler), venue, phase | Subset of A2 (batter vs pace/spin) and A4 (compare). Top 50 pairs with >= 6 balls only. |
| B5 | basic/leaderboards.py (146) | Four leaderboards per season: orange (runs), purple (wkts), SR, economy | season, extra.cap | Four near-identical SQL blocks. Overlaps B1/B2 grouped by season. Chart title says "min 10 overs", SQL uses >= 60 balls (same, but not shared). |
| B6 | basic/venue.py (310) | Venue summary (avg 1st/2nd innings, bat-first win%), plus 5 sub-tabs: top batters, bowlers, death bowlers, PP bowlers, team records | venue, team, season | Sub-tabs repeat B1/B2/I1 SQL with a venue filter; B2/B1 already accept `venue`. |
| I1 | intermediate/phase_analysis.py (269) | PP/Middle/Death split for batting or bowling | player, team, venue, extra.role | Phase CASE repeated 6x in this file alone. Same idea as A1, A3, A4, A5. I1 bowling economy uses `SUM(runs_total)` (includes byes/leg-byes), unlike B2. |
| I2 | intermediate/partnerships.py (86) | Top batting pairs by runs together, SR, 4s/6s | player, team | Not true partnerships: it groups all balls where (batter, non-striker) pair appears across matches. No wicket/stand boundaries. Unique logic. |
| I3 | intermediate/impact_score.py (190) | Weighted bat + bowl "impact" per player | player, team | Reimplements batting and bowling aggregates (B1+B2). Weights hard-coded; `config.yaml: impact_score_weights` is unused. |
| I4 | intermediate/form_tracker.py (264) | Rolling avg runs/SR (batter) or wkts/economy (bowler) per match | player, extra.role, extra.window | Per-match SQL repeats B1/B2. Window default 5 in code vs `rolling_window: 10` in config (config unused). |
| A1 | advanced/true_performance.py (421) | Phase-adjusted "true SR" and "true economy" vs league baseline | player, team, extra.role | Largest file. Phase CASE 8x. Baseline uses only the format/season filter. |
| A2 | advanced/pace_vs_spin.py (343) | Guesses pace/spin from over distribution, then batter or team vs type | player, team, venue, extra.mode | Heuristic classifier (see F6). Team mode assumes innings 1 = team1 (F1). Superset of B4 ideas. |
| A3 | advanced/season_awards.py (317) | Top 5 per season per phase (bat/bowl), best debutants | season, venue, extra.award | Duplicates I1 phase SQL, with `?` over-bounds instead of the `BETWEEN` constants. |
| A4 | advanced/player_comparison.py (337) | Two batters or two bowlers side by side + radar | player, player2, extra.role | Runs one SQL per player in a loop; duplicates B1/B2 + I1. Only one that uses numpy. |
| A5 | advanced/clutch_performance.py (306) | "Clutch index" = SR in pressure situations / overall SR | player, team, extra.role | The "pressure" filter is just `over_num >= 15` (F5), so it duplicates the death-overs phase from I1/A3. |

Overlap in one line: batting stats are computed 7 ways (B1, B5, B6, I1, I3, A1, A4), bowling stats 9 ways, team win% 3 ways, phase splits 6 ways.

## 3. Findings (worst first)

| # | Sev | Where | Problem | Fix idea |
|---|---|---|---|---|
| F1 | High | `ingestion/cricsheet.py` (no `batting_team` col); `modules/advanced/pace_vs_spin.py:169`; `modules/basic/venue.py:82-83, 130-131` | The schema drops Cricsheet's `batting_team`/`bowling_team`. Modules then assume `innings 1 = team1` (A2) and `team1 = toss winner` (B6). **Measured:** `toss_winner = team1` in only 3,299 of 7,935 matches (42%). B6 bat-first wins = 3,943 by its formula vs 3,829 by the correct rule (toss winner + decision), out of 7,714 decided matches. A2 team mode is probably also wrong (**guess**: same assumption, not re-computed). | Store `batting_team`, `bowling_team` per delivery (and `innings_batting_first` per match) at ingest; compute bat-first from those. |
| F2 | High | `modules/base.py:110-119`, and ~35 literals in A1, A2, A4, A5, B6, I1, base (**measured:** 36 hits of `BETWEEN 0 AND 5` / `6 AND 14` / `15 AND 19`: I1 12, A1 8, A2 7, A4 4, base 3, B6 2) | Phase = fixed over ranges for a 20-over game. **Measured:** The Hundred has `over_num` 0-19 (100 balls grouped in 5s), so its "powerplay" is wrong (**guess**: real PP is first 25 balls = overs 0-4). `* 6.0` economy and `* 24` in B2 assume 6-ball overs and 4-over spells. | One `phases(format)` table in the SQL layer (balls-per-over, innings length, phase bounds); modules ask for `phase_sql("d")`. |
| F3 | High | `dashboard/app.py:50-85, 292-526` (`MODULE_NAV`, `MODULE_DESC`, `FILTER_FNS`, 15 `_filters_XX` fns) | Adding a module touches 4 places (module file + nav list + desc dict + a 15-40 line filter function + `FILTER_FNS` entry). `BaseModule.supported_filters` exists on every module but **nothing reads it** (**measured** by grep). `_filters_B1` and `_filters_B2` are identical; I2 and I3 identical. | Each module declares typed `ParamSpec`s (name, widget, choices source, depends_on); the dashboard renders widgets generically; nav/description come from the registry. |
| F4 | High | `dashboard/app.py:108,123,139,152,166,179` | `except Exception: return []` hides every DB error. Worse, 6 loaders build `{w} AND ...` where `w` is `""` when the filter is `1=1` (lines 100,104,120,135,149,176): that is a SQL syntax error that is silently swallowed (**read**, latent: all 8 real competitions have a filter, so it only fires for an unknown label). `_overview_data` (245) returns an `err` key that `_render_overview` never shows. | Let errors raise to one `st.error` boundary; build `WHERE` via one helper that always starts with `1=1`. |
| F5 | High | `modules/advanced/clutch_performance.py:69-79, 156` | Docstring promises "close chases, 5+ wickets down, RR > 9". The code is `(innings = 2 AND over >= 15) OR over >= 15`, which collapses to `over >= 15` (death overs, any innings). The "Clutch Index" is just death SR / overall SR. The label is misleading. | Either implement the pressure state (needs wickets-down and target from ball data) or rename it "Death-overs index". |
| F6 | High | `modules/advanced/pace_vs_spin.py:59-64, 93-100, 153-160` | Pace/spin is **guessed** from over distribution (>50% in overs 7-15 and <20% at death = spin). Cricsheet CSV2 has no bowling style. The result is presented as fact in the UI. Any bowler with < 120 balls defaults to "Pace". | Add a small `bowler_style` lookup (manual CSV, or Cricsheet people registry if usable), or label the module "experimental"/remove. |
| F7 | High | `ingestion/cricsheet.py:97-103`, `config.yaml:paths.database` | `ingest` writes into whatever `paths.database` is, which is the **slim deployment DB** (the same file the project rules say never to overwrite in place). Nothing in the repo builds the slim DB (known). `INSERT OR IGNORE` on matches but delete+insert on deliveries: re-ingest after a Cricsheet edit leaves stale match rows. Row-wise `apply(axis=1)` per match (line ~170) is slow. | `ingest --out <new.duckdb>`; build to a temp file, then swap. Vectorise `extra_type`. |
| F8 | Med | `src/cricket_analytics/cli.py:62, 87` | CLI imports only `modules.basic`. `cricket modules` lists B1-B6 only and `cricket run I1` / `A1` raises `KeyError`. README claims they work. | Registry auto-discovery (one import of the `modules` package). |
| F9 | Med | `modules/base.py:68-108` and all `ILIKE ?` with `%name%` (e.g. `batting.py:29`) | Player filter is a substring `ILIKE '%name%'`. The dashboard passes exact names but matching is still fuzzy: "Khan" or "Z Khan" also matches "AZ Khan". `_` / `%` are not escaped. `team` filters on the *match* (team1 OR team2), so "B1 team = MI" includes opposition batters. `opposition`, `date_range` params exist but no module or UI uses them. | Exact match (`=`) on resolved names; add a `resolve_player()` helper for fuzzy input; filter by the batting/bowling team column (F1). |
| F10 | Med | `modules/intermediate/phase_analysis.py:145` vs `modules/basic/bowling.py:226` | Runs conceded defined 4 ways: `runs_total` (I1, B6 death at venue.py:220), `runs_total - byes/legbyes` (B2, A1, A3, A4, A5), `CASE ... NOT IN (byes, legbyes)` (B5, B6, I3, I4), `runs_batter` only (B4). Same bowler gets different economy in different tabs. | One SQL fragment constant. |
| F11 | Med | grep over `modules/`, `dashboard/` | Wicket-kind exclusion list written 24+ times in 4 variants: 16x `(run out, retired hurt, retired out, obstructing the field)`, 4x without `obstructing`, 2x without `retired out` (app.py overview), 1x with spaces. Batter-dismissal lists differ from bowler lists (correct in principle, but not named). | Constants `BOWLER_WICKETS`, `BATTER_DISMISSALS`. |
| F12 | Med | `dashboard/app.py:606,615,631,643,673,708,719,727` | 8x deprecated `use_container_width` (Streamlit 1.55 pins; uses `width="stretch"`). | Replace, or let the generic renderer do it once. |
| F13 | Med | `dashboard/app.py:686-689` | `mod.run()` is re-executed on **every** Streamlit rerun (any widget click, even the CSV download), with no `st.cache_data` on module results. `db.query` opens a new DB connection per call (10+ per Overview). | Cache by `(module_id, params)`; reuse one read-only connection. |
| F14 | Med | `modules/*` (`plot()` in 14 of 15) | Analysis and presentation are mixed: ~45% of module lines are Plotly. A video pipeline or LLM tool would import plotly + build figures it never uses. Hard-coded hex colours everywhere. | Move all figure code to `viz/`; modules return data only. |
| F15 | Med | `pyproject.toml:[project.scripts], packages.find`, `conftest.py`, `dashboard/app.py:13` | Package is imported as `src.cricket_analytics` (a `src.` prefix), plus top-level `modules`, `ingestion`, `preprocessing`. `packages.find.include` omits `preprocessing*`, so `pip install -e .` would break `cricket setup` (**guess**, not tried: no installs allowed). Needs `sys.path` hacks in `conftest.py` and `app.py`. | One real package `cricket/` under `src/`; drop path hacks. |
| F16 | Med | `preprocessing/teams.py` | `normalise_team` / `migrate_teams` are **never called** (`rg` finds no caller; ingest only normalises venues). Team aliases (e.g. Delhi Daredevils -> Capitals) are therefore not applied at load. Still writes to DB in place when run. | Call at ingest; do not migrate in place. |
| F17 | Med | `modules/intermediate/impact_score.py:93,101,107` | `NULLIF(legal_balls, 1)` is almost certainly a typo for `NULLIF(legal_balls, 0)` (**guess**); economy for 1-ball bowlers becomes NULL. Weights are hard-coded; config weights ignored. | Fix and read weights from one place. |
| F18 | Low | `modules/basic/bowling.py:167,171` | Single-bowler pie estimates dots as `dot% * innings * 24 / 100` (assumes 4 overs per innings). A made-up number shown as a stat. | Return real counts from SQL. |
| F19 | Low | `modules/basic/team_performance.py:62` | Title shows "None" when `format` is None (and `params.format` is a competition label, not a format). | `params.format or "All"`. |
| F20 | Low | dead code: `ingestion/cricsheet.py:153` (`_extra_type` nested fn never called), `phase_analysis.py:38` (`phase_innings` CTE, unused), `pace_vs_spin.py:80` (`all_values` overwritten at :87), `bowling.py:36` (`overs` column unused), `app.py:29,32` (`pd`, `list_modules` unused), `db.py:133` (`pd` unused) | Dead lines. | Delete. |
| F21 | Low | `modules/base.py:78`, `ModuleParams.format` | `format` overloaded: holds a competition label ("IPL", "T20 International"), a raw format ("T20"), or "All T20". `ModuleParams.season` typed `int | list[int]` but DB seasons are strings like "2007/08". `output="report"` not implemented. | Rename to `competition`; seasons as `str`. |
| F22 | Low | `.claude/launch.json` | Uses bare `streamlit` / `python`, which on PATH is Anaconda 3.9 (code needs 3.12 for `X | None`). Whole-project `requires-python = ">=3.10"` also does not match 3.12 usage. | Point at `.venv\Scripts\...`. |
| F23 | Low | `requirements.txt`, `pyproject.toml` | `beautifulsoup4` (both) and `matplotlib`, `seaborn` (pyproject) are never imported. `numpy` is imported (A4) but not declared. Optional groups `ml`, `nlp`, `scraping` have no code. | See section 7. |
| F24 | Low | `config.yaml` | Only `paths.raw`, `paths.database`, `sources.cricsheet.formats`, `scraping.user_agent` are read. Everything else (`project`, `defaults`, `modules.*`, `dashboard.*`, `kaggle`, `paths.clean/gold`, `scraping.rate_limit/max_retries/cache_dir`, `base_url`, `file_type`) is unused. Download URLs live in `leagues.py`, not config. | Trim. |
| F25 | Low | SQL injection | **Measured/read:** all user values are bound with `?`. Only f-string interpolations of data are `app.py:233` (`m.season = '{latest}'`, value comes from the DB, so low risk) and `{window - 1}` (cast to `int` in I4). No real injection path today. | Bind `latest`; keep the pattern in the new filter layer. |
| F26 | Low | `README.md` | Stale: lists I5, A6-A8, "Pressure Index", ODI/Test formats, "A1 Win Probability" etc. that do not exist (modules there have different IDs/names than the code). | Regenerate module table from the registry. |
| F27 | Info | **Surprise** | CLAUDE.md lists "garbled tournament names (Men?s)". **Measured:** 0 rows with U+FFFD in the slim DB `tournament` column; names print correctly through Python. The garbling is probably Windows console encoding only (**guess**). Not a data bug in this DB. | Recheck on the rebuilt DB. |

## 4. Tests

Command: `.venv/Scripts/python -m pytest -q`

```
......                                                                   [100%]
6 passed in 3.11s
```

- `tests/test_db.py` (2): schema creates tables; schema is idempotent. Only touches a temp DB.
- `tests/test_modules.py` (4): `ModuleParams` defaults; B1/B2/B3 present in registry; `get_module("B1")` name; unknown ID raises `KeyError`.
- Coverage % **not measured**: `pytest-cov` is not installed in `.venv` and I was told not to install (`--cov` was rejected).
- **Modules with no test (14 of 15 have no direct test; B1 only has a name-lookup test):** B1-B6, I1-I4, A1-A5. **No module's `run()` or `plot()` is ever executed by tests.**
- Also untested: `ingestion/cricsheet.py` (`_parse_info`, `load_to_db`, `ingest`), `preprocessing/*` (aliases, `normalise_venue`), `leagues.get_sql_filter`, `ModuleParams` -> `_build_where_clauses` (the most important shared function), `cli.py`, `config.py`, `dashboard/app.py`.
- Note: `test_register_and_list_modules` imports only `modules.basic`, which is the same blind spot as F8.

## 5. Schema (slim DB, opened read-only: `data/cricket_analytics_slim.duckdb`)

Only 2 tables exist. The `players`, `venues`, `seasons`, `player_match` tables in `db.py` `_SCHEMA_SQL` are absent from the slim DB and not queried by any code.

**matches**: 7,935 rows, 7,935 distinct `match_id` (unique in practice, but **no PRIMARY KEY** in the file)

| column | type | notes |
|---|---|---|
| match_id | VARCHAR | |
| date | TIMESTAMP | schema says DATE |
| format | VARCHAR | values: T20 6,255 / BBL 662 / CPL 407 / PSL 314 / Hundred 167 / SA20 130. **No 'IPL' value**; IPL (1,169 matches, tournament "Indian Premier League") sits inside 'T20' |
| tournament | VARCHAR | e.g. Indian Premier League 1,169; Big Bash League 662; ICC Men's T20 World Cup 173; ICC Women's T20 World Cup 89 ... |
| season | VARCHAR | mixed styles: "2004/05", "2005", "2005/06" ... |
| venue, city, team1, team2 | VARCHAR | 163 distinct team names |
| toss_winner, toss_decision, winner, result | VARCHAR | |
| result_margin | INTEGER | |
| player_of_match, source | VARCHAR | |
| ingested_at | TIMESTAMP | |

Date range: 2005-02-17 to 2026-03-20. No gender column (4,856 matches have a `team1` that also appears in a "Women" tournament; **guess**: roughly women's and mixed teams, not a clean count).

**deliveries**: 1,812,213 rows (no PK, no FK in the file)

| column | type | notes |
|---|---|---|
| match_id | VARCHAR | every delivery has a match; every match has deliveries (0 orphans either way, **measured**) |
| innings, over_num, ball_num | INTEGER | `over_num` max = 19 in every format, including The Hundred |
| batter, bowler, non_striker | VARCHAR | names like "V Kohli" |
| runs_batter, runs_extras, runs_total | INTEGER | |
| extra_type | VARCHAR | wides 73,528; noballs 9,537; legbyes 24,410; byes 6,848; penalty 16; NULL 1,697,874 |
| wicket_type, player_out | VARCHAR | |
| fielder | **INTEGER** | 100% NULL (type is wrong too; should be VARCHAR if ever filled) |
| source | VARCHAR | |

Missing but needed: `batting_team`, `bowling_team`, gender/competition on matches, `balls_per_over`/innings length, `is_legal` ball flag, `target`/wickets-down for pressure stats.

Quirk: 1,134 `(match_id, innings, over_num, ball_num)` combos appear more than once (**measured**; probably extras re-using a ball number, not duplicates, **guess**).

## 6. Recommended architecture (<= 25 lines)

```
src/cricket/                  (one installable package; no "src." imports, no sys.path hacks)
  config.py   db.py           one read-only connection helper + cached query(); raises on error
  ingest/     cricsheet.py    download -> parse -> load into a NEW .duckdb (temp file, then swap)
              competitions.py 8 competitions: url, gender, balls_per_over, innings_len, phase bounds
  sql/        filters.py      Filters dataclass -> (where_sql, params); exact-match players, batting_team aware
              fragments.py    ONE definition each: LEGAL_BALL, RUNS_CONCEDED, BOWLER_WICKET, BATTER_OUT, phase_sql(fmt)
  analysis/   batting.py bowling.py matchups.py teams.py venues.py partnerships.py ...
                              plain functions returning DataFrames, NO plotly, built from sql/fragments
  registry.py                 @module(id="B1", title=..., params=[ParamSpec("player", kind="player"),...])
                              ParamSpec = name, type, choices source, depends_on, default
  api.py                      run(module_id, **params) -> Result(df, meta); list_modules(); schema(); resolve_player()
  cli.py                      cricket run B1 --player "V Kohli" --json | cricket schema --json | cricket ingest --out new.duckdb
  viz/                        figure builders keyed by module id (only the dashboard imports these)
dashboard/app.py              ~150 lines: nav from registry; widgets generated from ParamSpec; st.cache_data on api.run
tests/                        one golden test per module against a tiny fixture DB + 2-3 known real stats
```

- **Adding a module = one new file** in `analysis/` with the `@module(...)` decorator. Nav, description, filters, CLI, JSON schema and API all come from the registry; `app.py` and `README` are not touched.
- **Fix data first (F1, F2):** ingest `batting_team`, `bowling_team`, `gender`, `competition`, `balls_per_over`; phases come from a per-format table, not literals.
- **External callers (video pipeline now, LLM agent later):** `from cricket.api import run, resolve_player`; `run("B1", player="V Kohli", competition="IPL", season="2024")` returns `Result.to_records()` plus `meta` (module, params used, data-through date, DB version). `cricket schema --json` emits one JSON Schema per module, which can be pasted straight in as LLM tool definitions. `cricket run ... --json` is the same call over a CLI for non-Python callers. Always return raw numbers and column names, never figures.
- Stat definitions in `sql/fragments.py` so "Kohli's IPL strike rate" is the same number everywhere (check against Cricsheet/ESPNcricinfo in the golden tests).
- Not recommended now: an HTTP server, ORM, plugin system, or async. Add FastAPI later only if a non-Python caller needs it (`api.run` is already the function it would wrap).

## 7. What to delete (safe to remove) and why

| Item | Why safe |
|---|---|
| `requirements-ml.txt`, `requirements-nlp.txt`, and `pyproject` extras `ml`, `nlp`, `scraping`, `all` | No code imports scikit-learn, xgboost, lightgbm, statsmodels, spacy, nltk, scrapy or playwright. Re-add when a module needs them. |
| `beautifulsoup4` (requirements.txt, pyproject); `matplotlib`, `seaborn` (pyproject) | Never imported. |
| `config.yaml` keys: `project`, `defaults`, `modules.*`, `dashboard.*`, `sources.kaggle`, `sources.cricsheet.base_url/file_type`, `paths.clean/gold`, `scraping.rate_limit_seconds/max_retries/cache_dir` | Not read by any code (F24). Keep `paths.raw`, `paths.database`, `sources.cricsheet.formats`, `scraping.user_agent`. |
| Schema tables `players`, `venues`, `seasons`, `player_match` + 1 index in `db.py` | Not in the slim DB; no query reads them; ingest never fills them. |
| `ingestion/cricsheet.py:153` `_extra_type` nested function | Never called (the `apply` below it does the work). |
| `phase_analysis.py:38` `phase_innings` CTE; `pace_vs_spin.py:80` first `all_values`; `bowling.py:36` `overs` column; `app.py` `pd`, `list_modules` imports; `db.py:133` `import pandas` | Dead / unused (F20). |
| `BaseModule.supported_filters` (as now written), `ModuleParams.opposition`, `date_range`, `output="report"` | Never read or used. (Replace `supported_filters` with `ParamSpec`.) |
| `dashboard/app.py` six copies of `_xxx_for(comp)` loaders and 15 `_filters_XX` functions (~230 lines) | Collapse into one generic loader + ParamSpec renderer. |
| `conftest.py` `sys.path` hack and `sys.path.insert` in `app.py` | Not needed once the package is properly installable. |
| `README.md` module tables / "Adding a New Module" steps | Wrong IDs and stale steps; regenerate from the registry. |
| Plotly code inside `modules/*` (~half the lines) | Move to `viz/`, not delete, but removes ~1,200 lines from the analysis layer. |

Do **not** delete `preprocessing/teams.py` (F16): it is dead only because nobody calls it. Wire it into ingest.

## Open questions / not verified

- Pace/spin and `team_vs_type` correctness (F1/F6) need the batting team column to verify.
- Hundred phase correctness (F2) is a guess from `over_num` range, not checked against a scorecard.
- Packaging (F15) not tested (no installs allowed).
- Test coverage % not measured (pytest-cov missing).
