# Cricket Analytics Platform

A modular, reusable cricket analytics pipeline covering IPL, T20I, ODI, and Test cricket.

Built on free, open-source data (Cricsheet, Kaggle). Runs fully locally. Designed to be extended with advanced ML and NLP modules over time.

---

## Quick Start

### 1. Clone & enter the project

```bash
cd cricket-analytics
```

### 2. Create and activate the virtual environment

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Mac / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install the project package

```bash
pip install -e .
```

### 5. Initialise the database

```bash
cricket setup
```

### 6. Download and load cricket data

```bash
# Download all formats (IPL, T20I, ODI, Test)
cricket ingest

# Or a specific format only
cricket ingest --format ipl
cricket ingest --format t20s
cricket ingest --format odis
cricket ingest --format tests
```

> Data comes from [Cricsheet.org](https://cricsheet.org) — ball-by-ball CSV files, free and open source.

### 7. Run the dashboard

```bash
streamlit run dashboard/app.py
```

Open your browser at `http://localhost:8501`

---

## CLI Usage

```bash
# List all available analysis modules
cricket modules

# Run a module (basic example)
cricket run B1                              # All batting stats (T20)
cricket run B1 --player "Kohli"            # Filter by player
cricket run B1 --format T20 --season 2023  # Filter by season
cricket run B2 --player "Bumrah" --format T20
cricket run B3 --team "Mumbai Indians"

# Show a plot instead of a table
cricket run B1 --output plot

# Filter by match phase
cricket run B2 --phase powerplay
cricket run B2 --phase death
```

---

## Analysis Modules

### Basic (Phase 1)

| ID  | Module                         | Description                                      |
|-----|--------------------------------|--------------------------------------------------|
| B1  | Batting Scorecard & Career Stats | Runs, average, SR, 50s, 100s per player        |
| B2  | Bowling Scorecard & Career Stats | Wickets, economy, SR, dot ball % per bowler    |
| B3  | Team Performance Summary       | Win/loss record, toss impact per team            |
| B4  | Head-to-Head Comparisons       | Batter vs bowler, team vs team records           |
| B5  | Tournament Leaderboards        | Orange Cap, Purple Cap, most sixes/fours         |
| B6  | Venue & Pitch Analysis         | Avg scores, batting/bowling-friendly venues      |

### Intermediate (Phase 2)

| ID  | Module                   | Description                                      |
|-----|--------------------------|--------------------------------------------------|
| I1  | Phase-Wise Breakdown     | Powerplay / middle / death run rates             |
| I2  | Partnership Analysis     | Best partnerships, wicket fall patterns          |
| I3  | Impact Player Scoring    | Custom impact score combining bat + bowl         |
| I4  | Pressure Index           | RRR vs CRR, win probability over time            |
| I5  | Form & Consistency       | Rolling averages, in-form / out-of-form detection |

### Advanced — ML (Phase 3+)

| ID  | Module                     | Description                                      |
|-----|----------------------------|--------------------------------------------------|
| A1  | Win Probability Model      | Real-time ball-by-ball win probability           |
| A2  | Score Prediction           | First/second innings score prediction            |
| A3  | Player Performance Forecast | Next-match batting/bowling prediction           |
| A4  | Player Archetypes          | K-Means clustering into role types               |
| A5  | Auction Value Estimator    | IPL fair value vs actual price                   |
| A6  | Player Network Graph       | Partnership & dismissal relationship graph       |
| A7  | Anomaly Detection          | Outlier performance flagging                     |
| A8  | Commentary NLP             | Sentiment analysis on match commentary           |

---

## Project Structure

```
cricket-analytics/
├── config.yaml              # All parameters — seasons, formats, data paths
├── requirements.txt         # Core dependencies
├── requirements-dev.txt     # Dev & testing dependencies
├── requirements-ml.txt      # ML dependencies (Phase 3+)
├── requirements-nlp.txt     # NLP dependencies (Phase 4+)
├── pyproject.toml           # Package config & CLI entry point
│
├── data/
│   ├── raw/                 # Downloaded CSVs / JSONs (never manually edited)
│   ├── clean/               # Normalised Silver layer
│   └── gold/                # Analysis-ready aggregates
│
├── ingestion/
│   └── cricsheet.py         # Cricsheet downloader + parser + loader
│
├── modules/
│   ├── base.py              # BaseModule interface + registry
│   ├── basic/               # B1–B6 modules
│   ├── intermediate/        # I1–I5 modules (Phase 2)
│   └── advanced/            # A1–A8 modules (Phase 3+)
│
├── src/cricket_analytics/
│   ├── config.py            # Config loader
│   ├── db.py                # DuckDB schema + connection helpers
│   └── cli.py               # Click CLI
│
├── dashboard/
│   └── app.py               # Streamlit dashboard
│
├── notebooks/               # Jupyter exploration notebooks
└── tests/                   # Unit tests
```

---

## Data Sources

| Source         | Type             | Coverage                          | Priority |
|----------------|------------------|-----------------------------------|----------|
| Cricsheet.org  | Free download    | IPL, T20I, ODI, Test — ball-by-ball | HIGH   |
| Kaggle         | Free download    | IPL 2008–2024 datasets            | HIGH     |
| ESPNcricinfo   | Web scrape       | All formats, all eras             | MED      |
| CricAPI        | REST API (free)  | Live scores, fixtures             | MED      |

---

## Adding a New Module

1. Create a file under `modules/basic/`, `modules/intermediate/`, or `modules/advanced/`.
2. Inherit from `BaseModule` and decorate with `@register_module`:

```python
from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query

@register_module
class MyNewModule(BaseModule):
    module_id = "B4"
    module_name = "Head-to-Head Comparisons"
    category = "basic"

    def run(self, params: ModuleParams):
        # Build your SQL using self._build_where_clauses(params, "m")
        where, values = self._build_where_clauses(params, "m")
        return query(f"SELECT ... FROM matches m WHERE {where}", values)
```

3. Import it in the package `__init__.py` so it self-registers.

That's it — the module is now available via CLI, dashboard, and notebooks.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
pytest tests/ --cov=src --cov=modules
```

---

## Delivery Phases

| Phase | Scope                              | Status      |
|-------|------------------------------------|-------------|
| 0     | Foundation, schema, Cricsheet ingestion | Done   |
| 1     | Basic modules B1–B6, CLI, tests    | In progress |
| 2     | Intermediate I1–I5, Streamlit dashboard | Planned |
| 3     | Advanced ML modules A1–A5          | Planned     |
| 4     | NLP & Network Analysis A6–A8       | Planned     |
| 5     | Polish, deploy, API wrapper        | Planned     |
