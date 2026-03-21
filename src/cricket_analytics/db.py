"""Database layer — DuckDB schema creation and connection management."""

import duckdb
from pathlib import Path

from src.cricket_analytics.config import get_db_path

_SCHEMA_SQL = """
-- Matches: one row per match
CREATE TABLE IF NOT EXISTS matches (
    match_id     VARCHAR PRIMARY KEY,
    date         DATE,
    format       VARCHAR,        -- T20, ODI, Test
    tournament   VARCHAR,        -- IPL, T20I, ODI World Cup, etc.
    season       VARCHAR,
    venue        VARCHAR,
    city         VARCHAR,
    team1        VARCHAR,
    team2        VARCHAR,
    toss_winner  VARCHAR,
    toss_decision VARCHAR,
    winner       VARCHAR,
    result       VARCHAR,        -- runs, wickets, tie, no result
    result_margin INTEGER,
    player_of_match VARCHAR,
    source       VARCHAR,        -- cricsheet, kaggle, espn
    ingested_at  TIMESTAMP DEFAULT current_timestamp
);

-- Deliveries: one row per ball (ball-by-ball)
CREATE TABLE IF NOT EXISTS deliveries (
    match_id      VARCHAR,
    innings       INTEGER,
    over_num      INTEGER,
    ball_num      INTEGER,
    batter        VARCHAR,
    bowler        VARCHAR,
    non_striker   VARCHAR,
    runs_batter   INTEGER,
    runs_extras   INTEGER,
    runs_total    INTEGER,
    extra_type    VARCHAR,       -- wide, noball, bye, legbye, penalty
    wicket_type   VARCHAR,       -- bowled, caught, lbw, run out, etc.
    player_out    VARCHAR,
    fielder       VARCHAR,
    source        VARCHAR,
    FOREIGN KEY (match_id) REFERENCES matches(match_id)
);

-- Players: dimension table
CREATE TABLE IF NOT EXISTS players (
    player_id     VARCHAR PRIMARY KEY,
    name          VARCHAR,
    country       VARCHAR,
    dob           DATE,
    batting_style VARCHAR,
    bowling_style VARCHAR,
    role          VARCHAR,       -- batter, bowler, allrounder, keeper
    source        VARCHAR,
    updated_at    TIMESTAMP DEFAULT current_timestamp
);

-- Player match stats: aggregated per player per match
CREATE TABLE IF NOT EXISTS player_match (
    player_id   VARCHAR,
    match_id    VARCHAR,
    team        VARCHAR,
    runs        INTEGER,
    balls_faced INTEGER,
    fours       INTEGER,
    sixes       INTEGER,
    strike_rate DOUBLE,
    overs_bowled DOUBLE,
    runs_conceded INTEGER,
    wickets     INTEGER,
    economy     DOUBLE,
    catches     INTEGER,
    run_outs    INTEGER,
    stumpings   INTEGER,
    source      VARCHAR,
    PRIMARY KEY (player_id, match_id)
);

-- Venues: dimension table
CREATE TABLE IF NOT EXISTS venues (
    venue_id    VARCHAR PRIMARY KEY,
    name        VARCHAR,
    city        VARCHAR,
    country     VARCHAR,
    capacity    INTEGER,
    source      VARCHAR
);

-- Seasons: tournament season summary
CREATE TABLE IF NOT EXISTS seasons (
    season      VARCHAR PRIMARY KEY,
    tournament  VARCHAR,
    year        INTEGER,
    winner      VARCHAR,
    runner_up   VARCHAR,
    mvp         VARCHAR,
    total_matches INTEGER,
    source      VARCHAR
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_deliveries_match ON deliveries(match_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_batter ON deliveries(batter);
CREATE INDEX IF NOT EXISTS idx_deliveries_bowler ON deliveries(bowler);
CREATE INDEX IF NOT EXISTS idx_matches_format ON matches(format);
CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season);
CREATE INDEX IF NOT EXISTS idx_matches_tournament ON matches(tournament);
CREATE INDEX IF NOT EXISTS idx_player_match_player ON player_match(player_id);
"""


def get_connection(db_path: Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Creates the file if it doesn't exist."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def init_schema(db_path: Path | None = None) -> None:
    """Create all tables and indexes if they don't exist."""
    con = get_connection(db_path)
    con.execute(_SCHEMA_SQL)
    con.close()


def query(sql: str, params: list | None = None, db_path: Path | None = None):
    """Run a query and return results as a pandas DataFrame."""
    import pandas as pd
    con = get_connection(db_path, read_only=True)
    try:
        if params:
            result = con.execute(sql, params).fetchdf()
        else:
            result = con.execute(sql).fetchdf()
        return result
    finally:
        con.close()
