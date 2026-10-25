"""Database layer — DuckDB schema creation and connection management."""

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import duckdb

from .config import get_db_path

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
    outcome_method VARCHAR,      -- 'super over' / 'bowl out' (tie settled; winner = tie-break winner), D/L, Awarded, ...
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


def get_connection(
    db_path: Path | None = None, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection. Creates the file if it doesn't exist."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def init_schema(db_path: Path | None = None) -> None:
    """Create all tables and indexes if they don't exist."""
    con = get_connection(db_path)
    con.execute(_SCHEMA_SQL)
    con.execute(
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS outcome_method VARCHAR"
    )  # DBs built before it existed
    con.close()


_DB_OVERRIDE: ContextVar[Path | None] = ContextVar("db_override", default=None)


@contextmanager
def use_db(db_path: Path | None):
    """Point query() at another DB file inside a `with` block (tests, `api.run(db_path=...)`)."""
    token = _DB_OVERRIDE.set(Path(db_path) if db_path else None)
    try:
        yield
    finally:
        _DB_OVERRIDE.reset(token)


def current_db_path(db_path: Path | None = None) -> Path:
    return Path(db_path or _DB_OVERRIDE.get() or get_db_path())


_READERS: dict[str, duckdb.DuckDBPyConnection] = {}
_LOCK = threading.Lock()


def _reader(db_path: Path | None) -> duckdb.DuckDBPyConnection:
    """One cached read-only connection per DB file (opened on first use)."""
    path = str(current_db_path(db_path).resolve())
    with _LOCK:
        if path not in _READERS:
            if not Path(path).exists():
                raise FileNotFoundError(f"Database not found: {path}. Run `cricket ingest` first.")
            _READERS[path] = duckdb.connect(path, read_only=True)
        return _READERS[path]


def close_readers() -> None:
    """Close cached connections (call before writing to a DB file from this process)."""
    with _LOCK:
        for con in _READERS.values():
            con.close()
        _READERS.clear()


def query(sql: str, params: list | None = None, db_path: Path | None = None):
    """Run a read-only query and return a pandas DataFrame. Errors raise; they are never hidden."""
    cur = _reader(db_path).cursor()  # cursor = own state, safe across Streamlit threads
    try:
        return cur.execute(sql, params or []).fetchdf()
    finally:
        cur.close()
