"""Incremental update: pull Cricsheet's "recently added" zips and load only the matches the DB does not have yet.

Safety: everything is loaded into a temp copy of the DB, checked, and only then swapped in. The old file is kept as
`<name>_prev_<date>.duckdb`. A locked DB (dashboard open) fails early with a clear message and nothing is changed.
Downloaded files are treated as data: only `<digits>.csv` / `<digits>_info.csv` members are extracted, flat.
"""

import logging
import os
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import requests

from ..competitions import COMPETITIONS
from ..config import get_path, load_config
from .cricsheet import _check_db_path, _parse_info, load_to_db

logger = logging.getLogger(__name__)

_URL = "https://cricsheet.org/downloads/recently_added_{days}_{sex}_csv2.zip"
_MEMBER = re.compile(r"^(\d+)(_info)?\.csv$")
# event-name fragment (lowercase) -> competition key, for men's club T20 only (women's leagues are not tracked)
_CLUB_EVENTS = [("indian premier league", "ipl"), ("big bash", "bbl"), ("pakistan super league", "psl"),
                ("caribbean premier league", "cpl"), ("sa20", "sa20"), ("the hundred", "hundred"), ("blast", "blast")]


def classify(meta: dict) -> str | None:
    """Competition key (as in competitions.py) for a parsed _info.csv, or None if we do not track it."""
    if meta.get("match_type") not in ("T20", "IT20"):
        return None
    gender, ttype = meta.get("gender"), meta.get("team_type")
    if ttype == "international":
        return {"male": "t20i", "female": "t20i_women"}.get(gender)
    event = (meta.get("event") or "").lower()
    if ttype == "club" and gender == "male":
        return next((k for frag, k in _CLUB_EVENTS if frag in event), None)
    return None


def _download(days: int, include_female: bool, dest: Path) -> list[Path]:
    ua = load_config().get("scraping", {}).get("user_agent", "CricketAnalytics/0.1")
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for sex in ("male", "female") if include_female else ("male",):
        url = _URL.format(days=days, sex=sex)
        r = requests.get(url, headers={"User-Agent": ua}, timeout=120)
        r.raise_for_status()
        p = dest / url.rsplit("/", 1)[1]
        p.write_bytes(r.content)
        logger.info(f"Downloaded {p.name}: {len(r.content):,} bytes")
        out.append(p)
    return out


def _extract(zips: list[Path], dest: Path) -> Path:
    """Flat-extract safe members of all zips into dest (later zips overwrite same names)."""
    dest.mkdir(parents=True, exist_ok=True)
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                if _MEMBER.match(name):          # no paths, no all_matches.csv, no README
                    (dest / name).write_bytes(zf.read(name))
    return dest


def _latest(con) -> dict:
    rows = con.execute("SELECT competition, gender, max(date)::VARCHAR FROM matches GROUP BY ALL").fetchall()
    return {(c if c != "t20i" or g == "male" else "t20i_women"): d for c, g, d in rows}


def _db_ids_and_totals(db_path: Path) -> tuple[dict, dict]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tot = {m: (int(n), int(r)) for m, n, r in con.execute(
            "SELECT match_id, count(*), sum(runs_total) FROM deliveries GROUP BY 1").fetchall()}
        ids = {m for (m,) in con.execute("SELECT match_id FROM matches").fetchall()}
        return {i: tot.get(i, (0, 0)) for i in ids}, _latest(con)
    finally:
        con.close()


def run_update(db_path: Path | None = None, days: int = 30, include_female: bool = True, dry_run: bool = False,
               download: bool = True, replace_changed: bool = False, zip_paths: list[Path] | None = None,
               raw_root: Path | None = None, updates_root: Path | None = None) -> dict:
    """Add new matches from Cricsheet's recently-added zips to db_path. Returns a report dict (see keys below).

    download=False uses `zip_paths` (or zips already in today's updates folder). dry_run only classifies and counts.
    """
    from .cricsheet import default_db_path
    db_path = _check_db_path(db_path or default_db_path())
    raw_root = Path(raw_root) if raw_root else get_path("raw") / "cricsheet"
    updates_dir = Path(updates_root) if updates_root else get_path("raw") / "_updates"
    work = updates_dir / date.today().isoformat()

    if not dry_run:  # fail fast: a read-write open fails while the dashboard (or anyone) holds the file
        try:
            duckdb.connect(str(db_path)).close()
        except duckdb.IOException as e:
            raise RuntimeError(f"{db_path.name} is in use by another process. Stop the dashboard "
                               f"(Streamlit) first, then run the update again. ({e})") from e

    zips = [Path(p) for p in zip_paths] if zip_paths else (
        _download(days, include_female, work) if download else sorted(work.glob("recently_added_*.zip")))
    if not zips:
        raise FileNotFoundError(f"No recently-added zips (download={download}, folder {work}).")
    src = _extract(zips, work / "extracted")

    existing, latest_before = _db_ids_and_totals(db_path)
    report = {"zips": [p.name for p in zips], "files_seen": 0, "skipped_not_tracked": 0, "skipped_unreadable": 0,
              "already_in_db": 0, "changed": [], "new_by_competition": {}, "replaced": [], "checks": {}, "ok": None,
              "swapped": False, "backup": None, "latest_before": latest_before, "latest_after": None,
              "dry_run": dry_run}

    todo: dict[str, tuple[str, str]] = {}      # match_id -> (competition key, folder)
    for csv in sorted(src.glob("*.csv")):
        if not csv.stem.isdigit():
            continue
        report["files_seen"] += 1
        mid = csv.stem
        try:
            meta = _parse_info(src / f"{mid}_info.csv")
            key = classify(meta)
            df = pd.read_csv(csv, usecols=["runs_off_bat", "extras"])
        except Exception as e:
            logger.warning(f"{mid}: unreadable ({e})")
            report["skipped_unreadable"] += 1
            continue
        if key is None:
            report["skipped_not_tracked"] += 1
            continue
        if mid in existing:
            report["already_in_db"] += 1
            if existing[mid] != (len(df), int((df.runs_off_bat + df.extras).sum())):
                report["changed"].append(mid)
                if replace_changed:
                    todo[mid] = (key, COMPETITIONS[key].folder)
            continue
        todo[mid] = (key, COMPETITIONS[key].folder)

    new_ids = [m for m in todo if m not in existing]
    report["replaced"] = [m for m in todo if m in existing]
    for m in new_ids:
        report["new_by_competition"].setdefault(todo[m][0], []).append(m)
    if dry_run or not todo:
        report["ok"] = True if not todo else None
        return _finish(report)

    # stage per folder, load into a temp copy of the DB
    stage = work / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    for m, (_, folder) in todo.items():
        (stage / folder).mkdir(parents=True, exist_ok=True)
        for f in (f"{m}.csv", f"{m}_info.csv"):
            shutil.copy2(src / f, stage / folder / f)

    tmp = db_path.with_name(db_path.stem + ".updating.duckdb")
    tmp.unlink(missing_ok=True)
    shutil.copy2(db_path, tmp)
    try:
        for folder in sorted({f for _, f in todo.values()}):
            load_to_db(folder, data_dir=stage / folder, db_path=tmp)
        report["checks"] = _checks(tmp, src, todo)
        report["latest_after"] = _latest_of(tmp)
        report["ok"] = all(c["ok"] for c in report["checks"].values())
        if report["ok"]:
            stamp = date.today().isoformat()
            prev = db_path.with_name(f"{db_path.stem}_prev_{stamp}.duckdb")
            if prev.exists():
                prev = db_path.with_name(f"{db_path.stem}_prev_{stamp}_{pd.Timestamp.now():%H%M%S}.duckdb")
            try:
                os.replace(db_path, prev)
            except PermissionError as e:
                raise RuntimeError(f"{db_path.name} is in use by another process. Stop the dashboard first, then "
                                   f"run the update again. Nothing was changed.") from e
            os.replace(tmp, db_path)
            report.update(swapped=True, backup=prev.name)
            for m, (_, folder) in todo.items():   # keep data/raw reproducible
                (raw_root / folder).mkdir(parents=True, exist_ok=True)
                for f in (f"{m}.csv", f"{m}_info.csv"):
                    shutil.copy2(stage / folder / f, raw_root / folder / f)
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_name(tmp.name + ".wal").unlink(missing_ok=True)
    return _finish(report)


def _latest_of(db: Path) -> dict:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return _latest(con)
    finally:
        con.close()


def _checks(db: Path, src: Path, todo: dict) -> dict:
    """Each check -> {ok, detail}. Run on the temp DB before it is swapped in."""
    con = duckdb.connect(str(db), read_only=True)
    ids = list(todo)
    con.register("ids", pd.DataFrame({"match_id": ids}))
    c: dict = {}
    try:
        loaded = con.execute("SELECT match_id, competition, gender, date::VARCHAR FROM matches "
                             "WHERE match_id IN (SELECT match_id FROM ids)").fetchall()
        c["all_loaded"] = {"ok": len(loaded) == len(ids), "detail": f"{len(loaded)} of {len(ids)} matches loaded"}
        per: dict = {}
        for mid, comp, gender, d in loaded:
            key = todo[mid][0]
            lo, hi, n = per.get(key, (d, d, 0))
            per[key] = (min(lo, d), max(hi, d), n + 1)
        c["dates_per_competition"] = {"ok": True, "detail": {k: {"n": n, "first": lo, "last": hi}
                                                             for k, (lo, hi, n) in sorted(per.items())}}
        dup_m = con.execute("SELECT count(*) - count(DISTINCT match_id) FROM matches").fetchone()[0]
        dup_d = con.execute("SELECT count(*) - count(DISTINCT (match_id, innings, ball_seq)) FROM deliveries").fetchone()[0]
        c["no_duplicate_keys"] = {"ok": dup_m == 0 and dup_d == 0, "detail": f"duplicate matches {dup_m}, balls {dup_d}"}
        none = con.execute("SELECT count(*) FROM matches m WHERE match_id IN (SELECT match_id FROM ids) AND NOT EXISTS "
                           "(SELECT 1 FROM deliveries d WHERE d.match_id = m.match_id)").fetchone()[0]
        c["every_match_has_deliveries"] = {"ok": none == 0, "detail": f"{none} new matches without deliveries"}
        got = {(m, int(i)): int(r) for m, i, r in con.execute(
            "SELECT match_id, innings, sum(runs_total) FROM deliveries WHERE match_id IN (SELECT match_id FROM ids) "
            "GROUP BY 1, 2").fetchall()}
        bad = []
        for m in ids:
            df = pd.read_csv(src / f"{m}.csv", usecols=["innings", "runs_off_bat", "extras"])
            want = (df.runs_off_bat + df.extras).groupby(df.innings).sum().to_dict()
            if {k: int(v) for k, v in want.items()} != {i: r for (mm, i), r in got.items() if mm == m}:
                bad.append(m)
        odd = [(m, i, r) for (m, i), r in got.items() if not 0 <= r <= 400]
        c["innings_runs_match_files"] = {"ok": not bad and not odd,
                                         "detail": f"{len(bad)} matches differ from CSV totals, {len(odd)} innings outside 0-400 runs"
                                                   + (f": {bad[:5]} {odd[:5]}" if bad or odd else "")}
    finally:
        con.close()
    return c


def _finish(report: dict) -> dict:
    n_new = sum(len(v) for v in report["new_by_competition"].values())
    lines = [f"Update ({'dry run' if report['dry_run'] else 'real'}): zips {report['zips']}",
             f"  files {report['files_seen']}, not tracked {report['skipped_not_tracked']}, unreadable "
             f"{report['skipped_unreadable']}, already in DB {report['already_in_db']} "
             f"(changed {len(report['changed'])}: {report['changed'][:10]}), new {n_new}"]
    for k, v in sorted(report["new_by_competition"].items()):
        lines.append(f"  new {k}: {len(v)}")
    for name, ch in report["checks"].items():
        lines.append(f"  [{'ok' if ch['ok'] else 'FAIL'}] {name}: {ch['detail']}")
    if report["latest_after"]:
        for k in sorted(set(report["latest_before"]) | set(report["latest_after"])):
            lines.append(f"  latest {k}: {report['latest_before'].get(k)} -> {report['latest_after'].get(k)}")
    lines.append(f"  result: ok={report['ok']} swapped={report['swapped']} backup={report['backup']}")
    report["text"] = "\n".join(lines)
    print(report["text"])
    return report
