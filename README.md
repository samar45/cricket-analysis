# Cricket Analytics

Ball-by-ball cricket analytics on free [Cricsheet](https://cricsheet.org) data (ODC-BY licence). Runs locally:
Cricsheet CSV zips -> DuckDB -> analysis modules -> CLI, JSON API and a Streamlit dashboard.

Competitions: IPL, men's and women's T20 internationals, BBL, PSL, CPL, SA20, The Hundred, T20 Blast.

## Setup (Python 3.12, Windows)

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pip install -e .
```

## Get the data

```
.venv\Scripts\cricket ingest                 # download all Cricsheet zips and build data/cricket_analytics.duckdb
.venv\Scripts\cricket ingest --format ipl    # one competition only
.venv\Scripts\cricket info                   # matches and latest date per competition
```

Raw files go to `data/raw/` and are not re-downloaded unless you pass `--redownload`. Database files are never
committed by hand (Git LFS quota).

## Use it

```
.venv\Scripts\cricket modules                # list analysis modules
.venv\Scripts\cricket schema                 # every module's parameters
.venv\Scripts\cricket resolve kohli          # find the exact player name
.venv\Scripts\cricket run batting --player "V Kohli" --competition ipl --group_by season
.venv\Scripts\cricket run bowling --competition ipl --season 2024 --json    # JSON with a meta block (source, data-through date, caveats)
```

From Python: `from cricket_analytics.api import run; run("batting", player="V Kohli", competition="ipl").data`.

## Dashboard

```
.venv\Scripts\streamlit run dashboard/app.py
```

Overview shows what is in the database and the leaders for a competition and season. Explore lists every module,
builds its filter widgets from the module's parameters, and offers CSV and JSON downloads.

## Tests

```
.venv\Scripts\python -m pytest -q
```

## Add a module = one file

Create `src/cricket_analytics/analysis/<name>.py` with a function decorated by `@module(...)` (copy `batting.py`).
It then appears in the CLI, the JSON schema (usable as LLM tool definitions) and the dashboard with no other edit.
Optional chart: `src/cricket_analytics/viz/<module_id>.py` with `figure(result)` returning a Plotly figure.
The contract is in `docs/WORK_phase2.md`.

## Layout

- `src/cricket_analytics/` - `registry.py`, `api.py`, `cli.py`, `competitions.py`, `db.py`, `sql/` (shared SQL rules), `analysis/`, `viz/`, `ingest/`
- `dashboard/` - `app.py` and `ui.py`
- `docs/` - roadmap, audits, status, journey
- `tests/` - unit tests on a two-match fixture plus checks against the real database
