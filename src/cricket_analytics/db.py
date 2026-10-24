"""Database layer — DuckDB schema creation and connection management."""

import duckdb
from pathlib import Path

from src.cricket_analytics.config import get_db_path

_SCHEMA_SQL = """
-- Matches: one row per match
CREATE TABLE IF NOT EXISTS matches (
    match_id     VARCHAR PRIMARY KEY,
    date         DATE,
    format       VARCHAR,        -- legacy label: T20 (T20I + IPL), BBL, PSL, ... Use competition + gender instead
    tournament   VARCHAR,        -- event name, or a fallback label when Cricsheet has none
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
    source       VARCHAR,        -- cricsheet
    ingested_at  TIMESTAMP DEFAULT current_timestamp,
    competition  VARCHAR,        -- ipl, t20i, bbl, psl, cpl, sa20, hundred, blast
    gender       VARCHAR,        -- male, female
    team_type    VARCHAR,        -- club, international
    match_type   VARCHAR,        -- Cricsheet info.match_type (T20, IT20)
    event        VARCHAR,        -- Cricsheet info.event, NULL when absent
    balls_per_over INTEGER       -- 6, or 5 for The Hundred
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
    extra_type    VARCHAR,       -- wides, noballs, byes, legbyes, penalty
    wicket_type   VARCHAR,       -- bowled, caught, lbw, run out, etc.
    player_out    VARCHAR,
    fielder       VARCHAR,       -- = Cricsheet fielder_1
    source        VARCHAR,
    batting_team  VARCHAR,
    bowling_team  VARCHAR,
    wides         INTEGER,
    noballs       INTEGER,
    byes          INTEGER,
    legbyes       INTEGER,
    penalty       INTEGER,
    other_wicket_type VARCHAR,
    other_player_out  VARCHAR,
    fielder_2     VARCHAR,
    fielder_3     VARCHAR,
    ball_seq      INTEGER,       -- 1.. running ball order within an innings (extras do not collide)
    PRIMARY KEY (match_id, innings, ball_seq)
);

-- Players: from the Cricsheet people registry
CREATE TABLE IF NOT EXISTS players (
    player_id     VARCHAR PRIMARY KEY,
    name          VARCHAR
);

-- Indexes on columns that exist in every DB version (the slim DB has no new columns)
CREATE INDEX IF NOT EXISTS idx_deliveries_match ON deliveries(match_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_batter ON deliveries(batter);
CREATE INDEX IF NOT EXISTS idx_deliveries_bowler ON deliveries(bowler);
CREATE INDEX IF NOT EXISTS idx_matches_format ON matches(format);
CREATE INDEX IF NOT EXISTS idx_matches_season ON matches(season);
CREATE INDEX IF NOT EXISTS idx_matches_tournament ON matches(tournament);
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
    con = get_connection(db_path, read_only=True)
    try:
        if params:
            result = con.execute(sql, params).fetchdf()
        else:
            result = con.execute(sql).fetchdf()
        return result
    finally:
        con.close()
