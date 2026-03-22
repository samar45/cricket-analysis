"""Cricsheet.org data ingestion — download and load ball-by-ball CSVs into DuckDB.

Cricsheet CSV2 format (per match):
  {match_id}.csv       — ball-by-ball data, match_id already in column 1
  {match_id}_info.csv  — match metadata, variable column count (2–5 fields)
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

logger = logging.getLogger(__name__)

_FORMAT_URLS = {
    "ipl":   "https://cricsheet.org/downloads/ipl_csv2.zip",
    "t20s":  "https://cricsheet.org/downloads/t20s_csv2.zip",
    "odis":  "https://cricsheet.org/downloads/odis_csv2.zip",
    "tests": "https://cricsheet.org/downloads/tests_csv2.zip",
}

_FORMAT_LABELS = {
    "ipl":   "IPL",   # IPL is its own format — not mixed with T20
    "t20s":  "T20",
    "odis":  "ODI",
    "tests": "Test",
}

_TOURNAMENT_LABELS = {
    "ipl":   "IPL",
    "t20s":  "T20I",
    "odis":  "ODI",
    "tests": "Test",
}


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
      info,key,value          (3 fields)
      info,player,Team,Name   (4 fields)
      info,registry,type,Name,hash  (5 fields)
      version,2.1.0           (2 fields — skip)
    """
    meta = {"teams": [], "players": {}}
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
                pass  # skip registry/people hashes
            elif key == "outcome":
                pass  # outcome details handled via winner/winner_runs/winner_wickets
            else:
                # For duplicate keys (e.g. umpire), keep the first value
                if key not in meta:
                    meta[key] = val

    return meta


# ── Load to DB ────────────────────────────────────────────────────────────────

def load_to_db(format_key: str, data_dir: Path | None = None) -> int:
    """Load extracted Cricsheet CSVs into DuckDB. Returns total delivery rows loaded."""
    raw_dir = data_dir or get_path("raw") / "cricsheet" / format_key
    if not raw_dir.exists():
        raise FileNotFoundError(f"No data at {raw_dir}. Run download_cricsheet('{format_key}') first.")

    init_schema()
    con = get_connection()

    # Ball-by-ball CSVs (exclude _info files)
    match_csvs = sorted(f for f in raw_dir.glob("*.csv") if not f.stem.endswith("_info"))
    if not match_csvs:
        logger.warning(f"No match CSVs found in {raw_dir}")
        con.close()
        return 0

    format_label     = _FORMAT_LABELS[format_key]
    tournament_label = _TOURNAMENT_LABELS[format_key]

    # Cricsheet CSV2 ball-by-ball columns:
    # match_id, season, start_date, venue, innings, ball,
    # batting_team, bowling_team, striker, non_striker, bowler,
    # runs_off_bat, extras, wides, noballs, byes, legbyes, penalty,
    # wicket_type, player_dismissed, other_wicket_type, other_player_dismissed

    all_deliveries = []
    match_rows = []
    skipped = 0

    for csv_path in match_csvs:
        match_id = csv_path.stem
        info_path = raw_dir / f"{match_id}_info.csv"

        try:
            df = pd.read_csv(csv_path, low_memory=False)
            if df.empty:
                continue

            # ── Deliveries ────────────────────────────────────────────────
            d = pd.DataFrame()
            d["match_id"]    = df["match_id"].astype(str)
            d["innings"]     = df["innings"].fillna(0).astype(int)

            # ball column is "over.delivery" e.g. 0.1, 4.6
            ball_str = df["ball"].astype(str)
            d["over_num"]  = ball_str.str.split(".").str[0].astype(int)
            d["ball_num"]  = ball_str.str.split(".").str[1].astype(int)

            d["batter"]      = df.get("striker",     df.get("batter"))
            d["bowler"]      = df["bowler"]
            d["non_striker"] = df.get("non_striker")
            d["runs_batter"] = df.get("runs_off_bat", 0).fillna(0).astype(int)
            d["runs_extras"] = df.get("extras",       0).fillna(0).astype(int)
            d["runs_total"]  = d["runs_batter"] + d["runs_extras"]

            # Determine extra type from whichever extra column is non-zero
            def _extra_type(row):
                for col in ("wides", "noballs", "byes", "legbyes", "penalty"):
                    if col in df.columns:
                        v = row.get(col)
                        if pd.notna(v) and v > 0:
                            return col
                return None

            extra_cols_present = [c for c in ("wides", "noballs", "byes", "legbyes", "penalty") if c in df.columns]
            if extra_cols_present:
                d["extra_type"] = df[extra_cols_present].apply(
                    lambda row: next((c for c in extra_cols_present if pd.notna(row[c]) and row[c] > 0), None),
                    axis=1
                )
            else:
                d["extra_type"] = None

            d["wicket_type"] = df.get("wicket_type")
            d["player_out"]  = df.get("player_dismissed")
            d["fielder"]     = df.get("fielder", df.get("fielders"))
            d["source"]      = "cricsheet"

            all_deliveries.append(d)

            # ── Match metadata ─────────────────────────────────────────────
            meta = _parse_info(info_path)
            teams = meta.get("teams", [])
            first_row = df.iloc[0]

            winner = meta.get("winner")
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

            match_rows.append({
                "match_id":        match_id,
                "date":            str(first_row.get("start_date", "")),
                "format":          format_label,
                "tournament":      meta.get("event", tournament_label),
                "season":          str(first_row.get("season", meta.get("season", ""))),
                "venue":           str(first_row.get("venue",  meta.get("venue",  ""))),
                "city":            meta.get("city", ""),
                "team1":           teams[0] if len(teams) > 0 else str(first_row.get("batting_team", "")),
                "team2":           teams[1] if len(teams) > 1 else str(first_row.get("bowling_team", "")),
                "toss_winner":     meta.get("toss_winner"),
                "toss_decision":   meta.get("toss_decision"),
                "winner":          winner,
                "result":          result_type,
                "result_margin":   result_margin,
                "player_of_match": meta.get("player_of_match"),
                "source":          "cricsheet",
            })

        except Exception as e:
            logger.warning(f"Skipping {match_id}: {e}")
            skipped += 1
            continue

    if not all_deliveries:
        logger.warning(f"No deliveries parsed for {format_key} ({skipped} skipped)")
        con.close()
        return 0

    # ── Bulk insert matches ────────────────────────────────────────────────
    matches_df = pd.DataFrame(match_rows)
    con.register("_matches_staging", matches_df)
    con.execute("""
        INSERT OR IGNORE INTO matches
            (match_id, date, format, tournament, season, venue, city,
             team1, team2, toss_winner, toss_decision, winner, result,
             result_margin, player_of_match, source)
        SELECT match_id, date, format, tournament, season, venue, city,
               team1, team2, toss_winner, toss_decision, winner, result,
               result_margin, player_of_match, source
        FROM _matches_staging
    """)
    con.unregister("_matches_staging")
    logger.info(f"Inserted {len(matches_df)} match records for {format_key}")

    # ── Bulk insert deliveries ─────────────────────────────────────────────
    deliveries_df = pd.concat(all_deliveries, ignore_index=True)

    # Remove any already-loaded match_ids to stay idempotent
    loaded_ids = tuple(deliveries_df["match_id"].unique())
    if loaded_ids:
        placeholders = ", ".join("?" for _ in loaded_ids)
        con.execute(f"DELETE FROM deliveries WHERE match_id IN ({placeholders})", list(loaded_ids))

    con.register("_deliveries_staging", deliveries_df)
    con.execute("""
        INSERT INTO deliveries
            (match_id, innings, over_num, ball_num, batter, bowler, non_striker,
             runs_batter, runs_extras, runs_total, extra_type,
             wicket_type, player_out, fielder, source)
        SELECT match_id, innings, over_num, ball_num, batter, bowler, non_striker,
               runs_batter, runs_extras, runs_total, extra_type,
               wicket_type, player_out, fielder, source
        FROM _deliveries_staging
    """)
    con.unregister("_deliveries_staging")
    con.close()

    total = len(deliveries_df)
    logger.info(f"Loaded {total:,} deliveries for {format_key} ({len(match_csvs) - skipped}/{len(match_csvs)} matches, {skipped} skipped)")
    return total


# ── Public API ────────────────────────────────────────────────────────────────

def ingest(formats: list[str] | None = None, download: bool = True) -> dict[str, int]:
    """Full pipeline: download + load for the given formats.

    Args:
        formats: list of format keys. Defaults to all configured formats.
        download: whether to re-download (skips if data already exists).
    Returns:
        dict of {format_key: rows_loaded}
    """
    cfg = load_config()
    formats = formats or cfg["sources"]["cricsheet"]["formats"]
    results = {}

    for fmt in formats:
        logger.info(f"=== {fmt.upper()} ===")
        raw_dir = get_path("raw") / "cricsheet" / fmt
        if download and (not raw_dir.exists() or not any(raw_dir.glob("*.csv"))):
            download_cricsheet(fmt)
        elif download:
            logger.info(f"Data already exists at {raw_dir}, skipping download. Use --redownload to force.")
        results[fmt] = load_to_db(fmt)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = ingest()
    for fmt, rows in results.items():
        print(f"{fmt}: {rows:,} deliveries loaded")
