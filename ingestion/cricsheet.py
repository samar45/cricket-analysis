"""Cricsheet.org data ingestion — download and load ball-by-ball CSVs into DuckDB.

Cricsheet CSV2 format (per match):
  {match_id}.csv       — ball-by-ball data, match_id already in column 1
  {match_id}_info.csv  — match metadata, variable column count (2–5 fields)
League zips also hold all_matches.csv (every ball of every match); it is skipped.
"""

import csv
import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

from src.cricket_analytics.config import load_config, get_path
from src.cricket_analytics.db import get_connection, init_schema
from preprocessing.teams import normalise_team
from preprocessing.venues import normalise_venue

logger = logging.getLogger(__name__)

from src.cricket_analytics.leagues import (
    CRICSHEET_URLS      as _FORMAT_URLS,
    CRICSHEET_FORMAT_LABELS  as _FORMAT_LABELS,
    CRICSHEET_TOURNAMENT_LABELS as _TOURNAMENT_LABELS,
    COMPETITION_CODES   as _COMPETITION_CODES,
)


# ── Output DB ─────────────────────────────────────────────────────────────────

def default_db_path() -> Path:
    """data/cricket_analytics.duckdb (never the slim deployment DB)."""
    return get_path("raw").parent / "cricket_analytics.duckdb"


def _check_db_path(db_path: Path) -> Path:
    db_path = Path(db_path)
    if "slim" in db_path.name.lower():
        raise ValueError(f"Refusing to write into {db_path.name}: build a new DB next to it instead.")
    return db_path


# ── Download ──────────────────────────────────────────────────────────────────

def download_cricsheet(format_key: str) -> Path:
    """Download and extract a Cricsheet CSV2 zip for one format."""
    cfg = load_config()
    dest = get_path("raw") / "cricsheet" / format_key
    dest.mkdir(parents=True, exist_ok=True)

    url = _FORMAT_URLS.get(format_key)
    if not url:
        raise ValueError(f"Unknown format: {format_key}. Choose from: {list(_FORMAT_URLS)}")

    ua = cfg.get("scraping", {}).get("user_agent", "CricketAnalytics/0.1")
    logger.info(f"Downloading {format_key} from {url} ...")
    resp = requests.get(url, headers={"User-Agent": ua}, timeout=180)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(dest)

    csv_count = len(list(dest.glob("*.csv")))
    logger.info(f"Extracted {csv_count} files to {dest}")
    return dest


# ── Info CSV parser ───────────────────────────────────────────────────────────

def _parse_info(info_path: Path) -> dict:
    """Parse a Cricsheet _info.csv file into a flat metadata dict.

    Info rows have variable column counts:
      info,key,value                (3 fields)
      info,player,Team,Name         (4 fields)
      info,registry,people,Name,id  (5 fields) -> meta["people"] = {name: id}
      version,2.1.0                 (2 fields — skip)
    """
    meta = {"teams": [], "players": {}, "people": {}}
    if not info_path.exists():
        return meta

    with open(info_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0] != "info" or len(row) < 3:
                continue
            key = row[1].strip()
            val = row[2].strip() if len(row) > 2 else ""

            if key == "team":
                meta["teams"].append(val)
            elif key == "player" and len(row) >= 4:
                team = val
                player = row[3].strip()
                meta["players"].setdefault(team, []).append(player)
            elif key == "registry":
                if val == "people" and len(row) >= 5:
                    meta["people"][row[3].strip()] = row[4].strip()
            else:
                # For duplicate keys (e.g. umpire), keep the first value
                if key not in meta:
                    meta[key] = val

    return meta


# ── Ball-by-ball CSV -> deliveries frame ──────────────────────────────────────

_BALL_COLS = [
    "match_id", "innings", "ball", "batting_team", "bowling_team", "striker", "non_striker", "bowler",
    "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes", "penalty",
    "wicket_type", "player_dismissed", "other_wicket_type", "other_player_dismissed",
    "fielder_1", "fielder_2", "fielder_3",
]
_EXTRA_COLS = ["wides", "noballs", "byes", "legbyes", "penalty"]
_INT_COLS = ["innings", "runs_off_bat", "extras", *_EXTRA_COLS]


def _deliveries_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Map one match's raw CSV2 rows to the deliveries table columns."""
    raw = df.reindex(columns=_BALL_COLS)
    raw[_INT_COLS] = raw[_INT_COLS].fillna(0).astype(int)
    for c in ("batting_team", "bowling_team"):
        raw[c] = raw[c].map(normalise_team)

    # "ball" is "over.delivery"; it is read as text so "4.10" is not collapsed to 4.1
    over_ball = raw["ball"].astype(str).str.split(".", n=1, expand=True)
    d = pd.DataFrame({
        "match_id":    raw["match_id"].astype(str),
        "innings":     raw["innings"],
        "over_num":    over_ball[0].astype(int),
        "ball_num":    over_ball[1].astype(int),
        "batter":      raw["striker"],
        "bowler":      raw["bowler"],
        "non_striker": raw["non_striker"],
        "runs_batter": raw["runs_off_bat"],
        "runs_extras": raw["extras"],
    })
    d["runs_total"] = d["runs_batter"] + d["runs_extras"]
    # first non-zero extra column wins (same order as the old loader)
    d["extra_type"] = None
    for c in reversed(_EXTRA_COLS):
        d.loc[raw[c] > 0, "extra_type"] = c
    d["wicket_type"] = raw["wicket_type"]
    d["player_out"]  = raw["player_dismissed"]
    d["fielder"]     = raw["fielder_1"]
    d["source"]      = "cricsheet"
    d["batting_team"] = raw["batting_team"]
    d["bowling_team"] = raw["bowling_team"]
    for c in _EXTRA_COLS:
        d[c] = raw[c]
    d["other_wicket_type"] = raw["other_wicket_type"]
    d["other_player_out"]  = raw["other_player_dismissed"]
    d["fielder_2"] = raw["fielder_2"]
    d["fielder_3"] = raw["fielder_3"]
    d["ball_seq"]  = d.groupby("innings").cumcount() + 1
    return d


# ── Load to DB ────────────────────────────────────────────────────────────────

def load_to_db(format_key: str, data_dir: Path | None = None, db_path: Path | None = None) -> int:
    """Load extracted Cricsheet CSVs into DuckDB. Returns total delivery rows loaded.

    Re-loading a match replaces its old rows. Never writes to a *slim* DB file.
    """
    raw_dir = data_dir or get_path("raw") / "cricsheet" / format_key
    if not raw_dir.exists():
        raise FileNotFoundError(f"No data at {raw_dir}. Run download_cricsheet('{format_key}') first.")
    db_path = _check_db_path(db_path or default_db_path())

    # Ball-by-ball CSVs (exclude _info files). League zips also contain all_matches.csv
    # (every ball of every match); only numeric stems are matches.
    match_csvs = sorted(f for f in raw_dir.glob("*.csv") if f.stem.isdigit())
    if not match_csvs:
        logger.warning(f"No match CSVs found in {raw_dir}")
        return 0

    format_label     = _FORMAT_LABELS[format_key]
    tournament_label = _TOURNAMENT_LABELS[format_key]
    competition      = _COMPETITION_CODES[format_key]

    all_deliveries = []
    match_rows = []
    people: dict[str, str] = {}   # player_id -> name
    skipped = 0

    for i, csv_path in enumerate(match_csvs, 1):
        match_id = csv_path.stem
        try:
            df = pd.read_csv(csv_path, low_memory=False,
                             dtype={"match_id": str, "ball": str, "season": str, "start_date": str})
            if df.empty:
                continue

            d = _deliveries_frame(df)

            meta = _parse_info(raw_dir / f"{match_id}_info.csv")
            people.update({pid: name for name, pid in meta["people"].items()})
            teams = [normalise_team(t) for t in meta["teams"]]
            first_row = df.iloc[0]

            result_margin = None
            result_type = None
            if meta.get("winner_wickets"):
                result_type = "wickets"
                result_margin = int(meta["winner_wickets"])
            elif meta.get("winner_runs"):
                result_type = "runs"
                result_margin = int(meta["winner_runs"])
            elif meta.get("outcome") in ("tie", "no result", "draw"):
                result_type = meta["outcome"]

            raw_venue = str(first_row.get("venue", meta.get("venue", "")))
            match_rows.append({
                "match_id":        match_id,
                "date":            str(first_row.get("start_date", "")),
                "format":          format_label,
                "tournament":      meta.get("event", tournament_label),
                "season":          str(first_row.get("season", meta.get("season", ""))),
                "venue":           normalise_venue(raw_venue),
                "city":            meta.get("city", ""),
                "team1":           teams[0] if len(teams) > 0 else normalise_team(str(first_row.get("batting_team", ""))),
                "team2":           teams[1] if len(teams) > 1 else normalise_team(str(first_row.get("bowling_team", ""))),
                "toss_winner":     normalise_team(meta.get("toss_winner")),
                "toss_decision":   meta.get("toss_decision"),
                "winner":          normalise_team(meta.get("winner")),
                "result":          result_type,
                "result_margin":   result_margin,
                "player_of_match": meta.get("player_of_match"),
                "source":          "cricsheet",
                "competition":     competition,
                "gender":          meta.get("gender"),
                "team_type":       meta.get("team_type"),
                "match_type":      meta.get("match_type"),
                "event":           meta.get("event"),
                "balls_per_over":  int(meta.get("balls_per_over") or 6),
            })
            all_deliveries.append(d)  # appended after the match row, so a failure never leaves an orphan
        except Exception as e:
            logger.warning(f"Skipping {match_id}: {e}")
            skipped += 1
            continue
        if i % 500 == 0:
            logger.info(f"{format_key}: parsed {i}/{len(match_csvs)} files")

    if not all_deliveries:
        logger.warning(f"No deliveries parsed for {format_key} ({skipped} skipped)")
        return 0

    init_schema(db_path)
    con = get_connection(db_path)
    try:
        matches_df = pd.DataFrame(match_rows)
        deliveries_df = pd.concat(all_deliveries, ignore_index=True)
        players_df = pd.DataFrame({"player_id": list(people), "name": list(people.values())})
        con.register("_matches_staging", matches_df)
        con.register("_deliveries_staging", deliveries_df)
        con.register("_players_staging", players_df)

        # Replace previously loaded copies of these matches (Cricsheet corrects files)
        con.execute("DELETE FROM deliveries WHERE match_id IN (SELECT match_id FROM _matches_staging)")
        con.execute("DELETE FROM matches WHERE match_id IN (SELECT match_id FROM _matches_staging)")

        con.execute("""
            INSERT INTO matches
                (match_id, date, format, tournament, season, venue, city,
                 team1, team2, toss_winner, toss_decision, winner, result,
                 result_margin, player_of_match, source,
                 competition, gender, team_type, match_type, event, balls_per_over)
            SELECT match_id, CAST(date AS DATE), format, tournament, season, venue, city,
                   team1, team2, toss_winner, toss_decision, winner, result,
                   result_margin, player_of_match, source,
                   competition, gender, team_type, match_type, event, balls_per_over
            FROM _matches_staging
        """)
        con.execute("""
            INSERT INTO deliveries
                (match_id, innings, over_num, ball_num, batter, bowler, non_striker,
                 runs_batter, runs_extras, runs_total, extra_type,
                 wicket_type, player_out, fielder, source,
                 batting_team, bowling_team, wides, noballs, byes, legbyes, penalty,
                 other_wicket_type, other_player_out, fielder_2, fielder_3, ball_seq)
            SELECT match_id, innings, over_num, ball_num, batter, bowler, non_striker,
                   runs_batter, runs_extras, runs_total, extra_type,
                   wicket_type, player_out, fielder, source,
                   batting_team, bowling_team, wides, noballs, byes, legbyes, penalty,
                   other_wicket_type, other_player_out, fielder_2, fielder_3, ball_seq
            FROM _deliveries_staging
        """)
        con.execute("INSERT OR IGNORE INTO players (player_id, name) SELECT player_id, name FROM _players_staging")
    finally:
        con.close()

    total = len(deliveries_df)
    logger.info(f"Loaded {total:,} deliveries, {len(matches_df)} matches for {format_key} "
                f"({len(match_csvs) - skipped}/{len(match_csvs)} files ok, {skipped} skipped)")
    return total


# ── Public API ────────────────────────────────────────────────────────────────

def ingest(formats: list[str] | None = None, download: bool = True, db_path: Path | None = None) -> dict[str, int]:
    """Full pipeline: download + load for the given formats into db_path.

    Args:
        formats: list of format keys. Defaults to all configured formats.
        download: whether to download missing data (skips if the raw folder already has CSVs).
        db_path: output DuckDB file. Defaults to data/cricket_analytics.duckdb (never the slim DB).
    Returns:
        dict of {format_key: rows_loaded}
    """
    cfg = load_config()
    formats = formats or cfg["sources"]["cricsheet"]["formats"]
    db_path = _check_db_path(db_path or default_db_path())
    results = {}

    for fmt in formats:
        logger.info(f"=== {fmt.upper()} ===")
        raw_dir = get_path("raw") / "cricsheet" / fmt
        if download and (not raw_dir.exists() or not any(raw_dir.glob("*.csv"))):
            download_cricsheet(fmt)
        elif download:
            logger.info(f"Data already exists at {raw_dir}, skipping download. Use --redownload to force.")
        results[fmt] = load_to_db(fmt, db_path=db_path)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = ingest()
    for fmt, rows in results.items():
        print(f"{fmt}: {rows:,} deliveries loaded")
