"""Cricsheet.org data ingestion — download and load ball-by-ball CSVs into DuckDB.

Cricsheet is the primary data source (Tier 1, HIGH priority).
Provides ball-by-ball data for IPL, T20I, ODI, Tests.
"""

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

from src.cricket_analytics.config import load_config, get_path
from src.cricket_analytics.db import get_connection, init_schema

logger = logging.getLogger(__name__)

# Cricsheet CSV zip URLs by format key
_FORMAT_URLS = {
    "ipl": "https://cricsheet.org/downloads/ipl_csv2.zip",
    "t20s": "https://cricsheet.org/downloads/t20s_csv2.zip",
    "odis": "https://cricsheet.org/downloads/odis_csv2.zip",
    "tests": "https://cricsheet.org/downloads/tests_csv2.zip",
}

_FORMAT_LABELS = {
    "ipl": "T20",
    "t20s": "T20",
    "odis": "ODI",
    "tests": "Test",
}

_TOURNAMENT_LABELS = {
    "ipl": "IPL",
    "t20s": "T20I",
    "odis": "ODI",
    "tests": "Test",
}


def download_cricsheet(format_key: str, dest_dir: Path | None = None) -> Path:
    """Download a Cricsheet CSV zip and extract to dest_dir/cricsheet/{format_key}/."""
    cfg = load_config()
    dest = dest_dir or get_path("raw")
    extract_to = dest / "cricsheet" / format_key
    extract_to.mkdir(parents=True, exist_ok=True)

    url = _FORMAT_URLS.get(format_key)
    if not url:
        raise ValueError(f"Unknown format key: {format_key}. Choose from: {list(_FORMAT_URLS)}")

    rate_limit = cfg.get("scraping", {}).get("rate_limit_seconds", 2)
    user_agent = cfg.get("scraping", {}).get("user_agent", "CricketAnalytics/0.1")

    logger.info(f"Downloading {format_key} data from {url}")
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(extract_to)

    logger.info(f"Extracted {format_key} data to {extract_to}")
    return extract_to


def _parse_info_csv(info_path: Path) -> dict:
    """Parse the _info.csv companion file for match metadata."""
    metadata = {}
    if not info_path.exists():
        return metadata
    df = pd.read_csv(info_path, header=None, names=["category", "key", "value"])
    for _, row in df.iterrows():
        key = str(row["key"]).strip() if pd.notna(row["key"]) else ""
        val = str(row["value"]).strip() if pd.notna(row["value"]) else ""
        if key in ("team", ):
            metadata.setdefault("teams", []).append(val)
        elif key == "date":
            metadata.setdefault("dates", []).append(val)
        else:
            metadata[key] = val
    return metadata


def load_cricsheet_to_db(format_key: str, data_dir: Path | None = None) -> int:
    """Load extracted Cricsheet CSV files into DuckDB. Returns row count inserted."""
    cfg = load_config()
    raw_dir = data_dir or get_path("raw") / "cricsheet" / format_key

    if not raw_dir.exists():
        raise FileNotFoundError(f"No data at {raw_dir}. Run download_cricsheet('{format_key}') first.")

    init_schema()
    con = get_connection()

    # Cricsheet CSV2 format: one CSV per match, named {match_id}.csv
    csv_files = sorted(raw_dir.glob("*.csv"))
    # Filter out info files
    match_csvs = [f for f in csv_files if not f.stem.endswith("_info")]

    total_rows = 0
    format_label = _FORMAT_LABELS.get(format_key, "T20")
    tournament_label = _TOURNAMENT_LABELS.get(format_key, format_key.upper())

    for csv_path in match_csvs:
        match_id = csv_path.stem
        info_path = csv_path.parent / f"{match_id}_info.csv"

        try:
            # Read ball-by-ball data
            df = pd.read_csv(csv_path, low_memory=False)
            if df.empty:
                continue

            # Parse match info
            meta = _parse_info_csv(info_path)
            teams = meta.get("teams", [])
            dates = meta.get("dates", [])

            # Insert match record
            match_date = dates[0] if dates else None
            team1 = teams[0] if len(teams) > 0 else None
            team2 = teams[1] if len(teams) > 1 else None

            con.execute("""
                INSERT OR IGNORE INTO matches (match_id, date, format, tournament, season,
                    venue, city, team1, team2, toss_winner, toss_decision,
                    winner, result, player_of_match, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                match_id, match_date, format_label, tournament_label,
                meta.get("season"), meta.get("venue"), meta.get("city"),
                team1, team2,
                meta.get("toss_winner"), meta.get("toss_decision"),
                meta.get("winner"), meta.get("outcome"),
                meta.get("player_of_match"), "cricsheet"
            ])

            # Normalise delivery columns to our schema
            col_map = {
                "match_id": "match_id",
                "innings": "innings",
                "ball": "ball_num",
                "batting_team": "_batting_team",
                "striker": "batter",
                "bowler": "bowler",
                "non_striker": "non_striker",
                "runs_off_bat": "runs_batter",
                "extras": "runs_extras",
                "wides": "_wides",
                "noballs": "_noballs",
                "byes": "_byes",
                "legbyes": "_legbyes",
                "penalty": "_penalty",
                "wicket_type": "wicket_type",
                "player_dismissed": "player_out",
            }

            deliveries = pd.DataFrame()
            deliveries["match_id"] = match_id
            deliveries["innings"] = df.get("innings", pd.Series(dtype="int"))

            # Parse over.ball notation
            if "ball" in df.columns:
                deliveries["over_num"] = df["ball"].astype(str).str.split(".").str[0].astype(int)
                deliveries["ball_num"] = df["ball"].astype(str).str.split(".").str[1].astype(int)
            else:
                deliveries["over_num"] = 0
                deliveries["ball_num"] = 0

            deliveries["batter"] = df.get("striker", df.get("batter"))
            deliveries["bowler"] = df.get("bowler")
            deliveries["non_striker"] = df.get("non_striker")
            deliveries["runs_batter"] = df.get("runs_off_bat", 0)
            deliveries["runs_extras"] = df.get("extras", 0)
            deliveries["runs_total"] = deliveries["runs_batter"].fillna(0).astype(int) + deliveries["runs_extras"].fillna(0).astype(int)

            # Extra type
            extra_cols = ["wides", "noballs", "byes", "legbyes", "penalty"]
            def _get_extra_type(row):
                for col in extra_cols:
                    if col in df.columns and pd.notna(row.get(col)) and row.get(col, 0) > 0:
                        return col
                return None
            if any(c in df.columns for c in extra_cols):
                deliveries["extra_type"] = df.apply(_get_extra_type, axis=1)
            else:
                deliveries["extra_type"] = None

            deliveries["wicket_type"] = df.get("wicket_type")
            deliveries["player_out"] = df.get("player_dismissed")
            deliveries["fielder"] = df.get("fielders", df.get("fielder"))
            deliveries["source"] = "cricsheet"

            # Insert deliveries
            con.execute("""
                INSERT INTO deliveries
                SELECT * FROM deliveries_df
            """)
            # Use register + insert instead
            con.register("_tmp_deliveries", deliveries)
            con.execute("DELETE FROM deliveries WHERE match_id = ?", [match_id])
            con.execute("""
                INSERT INTO deliveries
                SELECT match_id, innings, over_num, ball_num, batter, bowler, non_striker,
                       runs_batter, runs_extras, runs_total, extra_type,
                       wicket_type, player_out, fielder, source
                FROM _tmp_deliveries
            """)
            con.unregister("_tmp_deliveries")

            total_rows += len(deliveries)

        except Exception as e:
            logger.warning(f"Skipping {match_id}: {e}")
            continue

    con.close()
    logger.info(f"Loaded {total_rows} deliveries for {format_key} ({len(match_csvs)} matches)")
    return total_rows


def ingest(formats: list[str] | None = None, download: bool = True) -> dict[str, int]:
    """Full ingestion pipeline: download + load for specified formats.

    Returns dict of {format_key: rows_loaded}.
    """
    cfg = load_config()
    formats = formats or cfg["sources"]["cricsheet"]["formats"]
    results = {}

    for fmt in formats:
        logger.info(f"--- Ingesting {fmt} ---")
        if download:
            download_cricsheet(fmt)
        rows = load_cricsheet_to_db(fmt)
        results[fmt] = rows

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = ingest()
    for fmt, rows in results.items():
        print(f"{fmt}: {rows:,} deliveries loaded")
