"""Incremental update: pull Cricsheet's "recently added" zips and load only the matches the DB does not have yet.

Safety: everything is loaded into a temp copy of the DB, checked, and only then swapped in. The old file is kept as
`<name>_prev_<date>.duckdb`. A locked DB (dashboard open) fails early with a clear message and nothing is changed.
Every run writes data/runs/<run_id>.json (see runlog.py). Downloaded files are treated as data: only `<digits>.csv` / `<digits>_info.csv` members are extracted, flat.
"""

import json
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
from ..runlog import RunLog
from .cricsheet import _check_db_path, _parse_info, load_to_db

logger = logging.getLogger(__name__)

_URL = "https://cricsheet.org/downloads/recently_added_{days}_{sex}_csv2.zip"
_MEMBER = re.compile(r"^(\d+)(_info)?\.csv$")
# event-name fragment (lowercase) -> competition key, for men's club T20 only (women's leagues are not tracked)
_CLUB_EVENTS = [
    ("indian premier league", "ipl"),
    ("big bash", "bbl"),
    ("pakistan super league", "psl"),
    ("caribbean premier league", "cpl"),
    ("sa20", "sa20"),
    ("the hundred", "hundred"),
    ("blast", "blast"),
]


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
                if _MEMBER.match(name):  # no paths, no all_matches.csv, no README
                    (dest / name).write_bytes(zf.read(name))
    return dest


GOLDEN = Path(__file__).parent.parent / "reference" / "golden.json"
# event names that look like a tracked competition: if one is NOT mapped, Cricsheet may have renamed it
_LOOKS_LIKE = (
    "ipl",
    "indian premier",
    "big bash",
    "pakistan super",
    "caribbean",
    "sa20",
    "hundred",
    "blast",
    "t20 international",
)
_BALLS_RANGE = {"hundred": (80, 220)}  # deliveries per match; everything else (T20): 100-300
_LOCK_MSG = (
    "{n} is in use by another process - stop the dashboard (Streamlit) first, then run again."
)


def _key(comp: str, gender: str) -> str:
    return "t20i_women" if comp == "t20i" and gender == "female" else comp


def _snapshot(db: Path) -> dict:
    """match_id -> (competition key, date, balls, runs, wickets), read-only."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            "SELECT m.match_id, m.competition, m.gender, m.date::VARCHAR, count(d.match_id), "
            "coalesce(sum(d.runs_total), 0), count(d.wicket_type) "
            "FROM matches m LEFT JOIN deliveries d USING (match_id) GROUP BY ALL"
        ).fetchall()
    finally:
        con.close()
    return {m: (_key(c, g), d, int(n), int(r), int(w)) for m, c, g, d, n, r, w in rows}


def _freshness(snap: dict) -> dict:
    out: dict = {}
    for k, d, *_ in snap.values():
        o = out.setdefault(k, {"matches": 0, "latest": d})
        o["matches"] += 1
        o["latest"] = max(o["latest"], d)
    return out


def _fingerprint(snap: dict, ids=None) -> dict:
    out: dict = {}
    for m, (k, _, n, r, w) in snap.items():
        if ids is None or m in ids:
            o = out.setdefault(k, {"matches": 0, "balls": 0, "runs": 0, "wickets": 0})
            o["matches"] += 1
            o["balls"] += n
            o["runs"] += r
            o["wickets"] += w
    return out


def run_golden(db: Path, entries: list | None = None) -> list[dict]:
    """Evaluate reference/golden.json (or `entries`) on db. Each -> {name, expected, actual, status}."""
    from .. import api
    from ..db import close_readers, query

    entries = json.loads(GOLDEN.read_text(encoding="utf-8")) if entries is None else entries
    out = []
    try:
        for g in entries:
            try:
                if "sql" in g:
                    v = query(g["sql"], db_path=db).iloc[0, 0]
                else:
                    v = (
                        api.run(g["module"], db_path=db, **g.get("params", {}))
                        .data[g["column"]]
                        .iloc[0]
                    )
                actual = v.item() if hasattr(v, "item") else v
                ok = actual >= g["expected"] if g.get("op") == "ge" else actual == g["expected"]
            except Exception as e:
                actual, ok = f"error: {e}", False
            exp = f">= {g['expected']}" if g.get("op") == "ge" else g["expected"]
            out.append(
                {
                    "name": g["name"],
                    "expected": exp,
                    "actual": actual,
                    "status": "pass" if ok else "fail",
                }
            )
    finally:
        close_readers()  # release the cached file handle (needed before the file is swapped)
    return out


def _integrity(db: Path) -> dict:
    """Whole-DB sanity: duplicate keys, matches without balls, balls without a match."""
    con = duckdb.connect(str(db), read_only=True)
    try:

        def q(s):
            return con.execute(s).fetchone()[0]

        dup_m = q("SELECT count(*) - count(DISTINCT match_id) FROM matches")
        dup_d = q("SELECT count(*) - count(DISTINCT (match_id, innings, ball_seq)) FROM deliveries")
        none = q(
            "SELECT count(*) FROM matches m WHERE NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.match_id = m.match_id)"
        )
        orphan = q(
            "SELECT count(DISTINCT match_id) FROM deliveries WHERE match_id NOT IN (SELECT match_id FROM matches)"
        )
    finally:
        con.close()
    return {
        "no_duplicate_keys": {
            "ok": dup_m == 0 and dup_d == 0,
            "detail": f"duplicate matches {dup_m}, balls {dup_d}",
            "expected": 0,
            "actual": dup_m + dup_d,
        },
        "every_match_has_deliveries": {
            "ok": none == 0,
            "detail": f"{none} matches without deliveries",
            "expected": 0,
            "actual": none,
        },
        "no_orphan_deliveries": {
            "ok": orphan == 0,
            "detail": f"{orphan} matches in deliveries but not in matches",
            "expected": 0,
            "actual": orphan,
        },
    }


def _extra_checks(
    before: dict, after: dict, new_ids: list, todo: dict, replace_changed: bool
) -> dict:
    """Checks that compare the DB before and after loading. before/after = per-match snapshots of the old and temp DB."""
    c: dict = {}
    old = set(before)
    diff = sorted(m for m in old if after.get(m, (None,) * 5)[2:] != before[m][2:])
    fb, fa = _fingerprint(before), _fingerprint(after, old)
    if not diff:
        c["old_data_unchanged"] = {
            "ok": True,
            "detail": f"{len(old)} existing matches identical (balls, runs, wickets)",
            "expected": fb,
            "actual": fa,
        }
    elif replace_changed and set(diff) <= {m for m in todo if m in old}:
        c["old_data_unchanged"] = {
            "ok": True,
            "status": "warn",
            "expected": fb,
            "actual": fa,
            "detail": f"{len(diff)} existing matches changed because of --replace-changed: {diff[:10]}",
        }
    else:
        c["old_data_unchanged"] = {
            "ok": False,
            "expected": fb,
            "actual": fa,
            "detail": f"{len(diff)} existing matches differ after the load: {diff[:10]}",
        }
    odd = []
    for m in new_ids:
        k, _, n, *_ = after.get(m, (todo[m][0], None, 0))
        lo, hi = _BALLS_RANGE.get(k, (100, 300))
        if not lo <= n <= hi:
            odd.append((m, n))
    c["balls_per_match_sane"] = {
        "ok": True,
        "status": "warn" if odd else "pass",
        "expected": "100-300 (Hundred 80-220)",
        "actual": odd[:10],
        "detail": f"{len(odd)} new matches outside the range"
        + (f" (rain-shortened games are normal): {odd[:5]}" if odd else ""),
    }
    return c


def _checks(db: Path, src: Path, todo: dict) -> dict:
    """Each check -> {ok, detail}. Run on the temp DB before it is swapped in."""
    con = duckdb.connect(str(db), read_only=True)
    ids = list(todo)
    con.register("ids", pd.DataFrame({"match_id": ids}))
    c: dict = {}
    try:
        loaded = con.execute(
            "SELECT match_id, competition, gender, date::VARCHAR FROM matches "
            "WHERE match_id IN (SELECT match_id FROM ids)"
        ).fetchall()
        c["all_loaded"] = {
            "ok": len(loaded) == len(ids),
            "detail": f"{len(loaded)} of {len(ids)} matches loaded",
        }
        per: dict = {}
        for mid, comp, gender, d in loaded:
            key = todo[mid][0]
            lo, hi, n = per.get(key, (d, d, 0))
            per[key] = (min(lo, d), max(hi, d), n + 1)
        c["dates_per_competition"] = {
            "ok": True,
            "detail": {
                k: {"n": n, "first": lo, "last": hi} for k, (lo, hi, n) in sorted(per.items())
            },
        }
        dup_m = con.execute("SELECT count(*) - count(DISTINCT match_id) FROM matches").fetchone()[0]
        dup_d = con.execute(
            "SELECT count(*) - count(DISTINCT (match_id, innings, ball_seq)) FROM deliveries"
        ).fetchone()[0]
        c["no_duplicate_keys"] = {
            "ok": dup_m == 0 and dup_d == 0,
            "detail": f"duplicate matches {dup_m}, balls {dup_d}",
        }
        none = con.execute(
            "SELECT count(*) FROM matches m WHERE match_id IN (SELECT match_id FROM ids) AND NOT EXISTS "
            "(SELECT 1 FROM deliveries d WHERE d.match_id = m.match_id)"
        ).fetchone()[0]
        c["every_match_has_deliveries"] = {
            "ok": none == 0,
            "detail": f"{none} new matches without deliveries",
        }
        got = {
            (m, int(i)): int(r)
            for m, i, r in con.execute(
                "SELECT match_id, innings, sum(runs_total) FROM deliveries WHERE match_id IN (SELECT match_id FROM ids) "
                "GROUP BY 1, 2"
            ).fetchall()
        }
        bad = []
        for m in ids:
            df = pd.read_csv(src / f"{m}.csv", usecols=["innings", "runs_off_bat", "extras"])
            want = (df.runs_off_bat + df.extras).groupby(df.innings).sum().to_dict()
            if {k: int(v) for k, v in want.items()} != {
                i: r for (mm, i), r in got.items() if mm == m
            }:
                bad.append(m)
        odd = [(m, i, r) for (m, i), r in got.items() if not 0 <= r <= 400]
        c["innings_runs_match_files"] = {
            "ok": not bad and not odd,
            "detail": f"{len(bad)} matches differ from CSV totals, {len(odd)} innings outside 0-400 runs"
            + (f": {bad[:5]} {odd[:5]}" if bad or odd else ""),
        }
    finally:
        con.close()
    return c


def _as_checks(raw: dict) -> list[dict]:
    out = []
    for n, c in raw.items():
        det = c["detail"]
        out.append(
            {
                "name": n,
                "status": c.get("status") or ("pass" if c["ok"] else "fail"),
                "expected": c.get("expected"),
                "actual": c["actual"] if "actual" in c else (None if isinstance(det, str) else det),
                "message": det if isinstance(det, str) else json.dumps(det, default=str),
            }
        )
    return out


def run_update(
    db_path: Path | None = None,
    days: int = 30,
    include_female: bool = True,
    dry_run: bool = False,
    download: bool = True,
    replace_changed: bool = False,
    zip_paths: list[Path] | None = None,
    raw_root: Path | None = None,
    updates_root: Path | None = None,
    golden: list | None = None,
) -> dict:
    """Add new matches from Cricsheet's recently-added zips to db_path. Returns a report dict; also writes the run log.

    download=False uses `zip_paths` (or zips already in today's updates folder). dry_run only classifies and counts.
    golden overrides reference/golden.json (tests).
    """
    from .cricsheet import default_db_path

    db_path = _check_db_path(db_path or default_db_path())
    args = {
        "days": days,
        "include_female": include_female,
        "dry_run": dry_run,
        "download": download,
        "replace_changed": replace_changed,
        "zip_paths": [str(p) for p in zip_paths or []],
    }
    log = RunLog("dry_run" if dry_run else "update", db_path, args)
    report = {
        "zips": [],
        "files_seen": 0,
        "skipped_not_tracked": 0,
        "skipped_unreadable": 0,
        "already_in_db": 0,
        "changed": [],
        "new_by_competition": {},
        "replaced": [],
        "checks": {},
        "ok": None,
        "swapped": False,
        "backup": None,
        "latest_before": {},
        "latest_after": None,
        "dry_run": dry_run,
    }
    try:
        _update(
            log,
            report,
            db_path,
            days,
            include_female,
            dry_run,
            download,
            replace_changed,
            zip_paths,
            raw_root,
            updates_root,
            golden,
        )
    except Exception as e:
        log.finish(False, f"{type(e).__name__}: {e}")
        raise
    failed = [n for n, c in report["checks"].items() if not c["ok"]] + [
        g["name"] for g in log.doc["golden"] if g["status"] == "fail"
    ]
    log.doc.update(swapped=report["swapped"], backup=report["backup"])
    report["log_path"] = str(
        log.finish(not failed, f"checks failed (DB not swapped): {failed}" if failed else None)
    )
    report["run_id"] = log.doc["run_id"]
    return _finish(report)


def _update(
    log,
    report,
    db_path,
    days,
    include_female,
    dry_run,
    download,
    replace_changed,
    zip_paths,
    raw_root,
    updates_root,
    golden,
):
    raw_root = Path(raw_root) if raw_root else get_path("raw") / "cricsheet"
    updates_dir = Path(updates_root) if updates_root else get_path("raw") / "_updates"
    work = updates_dir / date.today().isoformat()
    doc = log.doc

    if dry_run:
        log.skip("lock_check", "dry run only reads")
    else:  # fail fast: a read-write open fails while the dashboard (or anyone) holds the file
        with log.step("lock_check"):
            try:
                duckdb.connect(str(db_path)).close()
            except duckdb.IOException as e:
                raise RuntimeError(
                    _LOCK_MSG.format(n=db_path.name) + f" Nothing was changed. ({e})"
                ) from e

    with log.step("download") as s:
        if zip_paths:
            zips = [Path(p) for p in zip_paths]
            s.skip("zips given")
        elif download:
            zips = _download(days, include_female, work)
            s.details["bytes"] = {p.name: p.stat().st_size for p in zips}
        else:
            zips = sorted(work.glob("recently_added_*.zip"))
            s.skip("using zips already in today's folder")
        if not zips:
            raise FileNotFoundError(f"No recently-added zips (download={download}, folder {work}).")
        s.details["zips"] = [p.name for p in zips]
    report["zips"] = [p.name for p in zips]

    with log.step("classify") as s:
        src = _extract(zips, work / "extracted")
        before = _snapshot(db_path)
        existing = {m: v[2:4] for m, v in before.items()}
        doc["freshness_before"], doc["fingerprint_before"] = (
            _freshness(before),
            _fingerprint(before),
        )
        report["latest_before"] = {k: v["latest"] for k, v in doc["freshness_before"].items()}
        todo: dict[str, tuple[str, str]] = {}  # match_id -> (competition key, folder)
        meta_dates: dict[str, str] = {}
        skipped: dict = {}
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
                k = (
                    meta.get("event") or "(no event)",
                    meta.get("match_type") or "?",
                    meta.get("gender") or "?",
                )
                skipped[k] = skipped.get(k, 0) + 1
                continue
            meta_dates[mid] = (meta.get("date") or "").replace("/", "-")
            if mid in existing:
                report["already_in_db"] += 1
                if existing[mid] != (len(df), int((df.runs_off_bat + df.extras).sum())):
                    report["changed"].append(mid)
                    doc["changed_matches"].append(
                        {
                            "match_id": int(mid),
                            "reason": "numbers differ from the file at Cricsheet"
                            + (" (replaced)" if replace_changed else " (kept as is)"),
                        }
                    )
                    if replace_changed:
                        todo[mid] = (key, COMPETITIONS[key].folder)
                continue
            todo[mid] = (key, COMPETITIONS[key].folder)
        doc["skipped_events"] = [
            {"event": e, "match_type": t, "gender": g, "count": n}
            for (e, t, g), n in sorted(skipped.items(), key=lambda kv: -kv[1])
        ]
        s.details.update(
            files_seen=report["files_seen"],
            not_tracked=report["skipped_not_tracked"],
            unreadable=report["skipped_unreadable"],
            already_in_db=report["already_in_db"],
            changed=len(report["changed"]),
            to_load=len(todo),
        )
    # women's club events are known-untracked; only men's look-alikes can mean a rename
    odd_names = [
        x
        for x in doc["skipped_events"]
        if x["gender"] != "female"
        and x["match_type"] in ("T20", "IT20")
        and any(f in x["event"].lower() for f in _LOOKS_LIKE)
    ]
    if odd_names:
        log.check(
            "skipped_events",
            "warn",
            "no look-alike event left unmapped",
            odd_names[:10],
            f"{len(odd_names)} untracked event name(s) look like ours - possible Cricsheet rename",
        )
    else:
        log.check(
            "skipped_events",
            "pass",
            "no look-alike event left unmapped",
            [],
            f"{len(doc['skipped_events'])} untracked event name(s), none look like ours",
        )

    new_ids = [m for m in todo if m not in existing]
    report["replaced"] = [m for m in todo if m in existing]
    for m in new_ids:
        report["new_by_competition"].setdefault(todo[m][0], []).append(m)

    def new_summary(snap):
        out: dict = {}
        for k, ms in report["new_by_competition"].items():
            ds = sorted(snap[m][1] if m in snap else meta_dates[m] for m in ms)
            out[k] = {"matches": len(ms), "earliest": ds[0], "latest": ds[-1]}
        return out

    if dry_run:
        doc["new_by_competition"] = new_summary({})
        report["ok"] = True if not todo else None
        for k in ("load_to_copy", "checks", "golden", "swap", "copy_raw"):
            log.skip(k, "dry run")
        return
    doc["freshness_after"], doc["fingerprint_after"] = (
        doc["freshness_before"],
        doc["fingerprint_before"],
    )
    if not todo:
        report["ok"] = True
        for k in ("load_to_copy", "checks"):
            log.skip(k, "nothing new")
        with log.step("golden") as s:  # nothing to load: still verify the live DB, read-only
            doc["golden"] = run_golden(db_path, golden)
            if any(g["status"] == "fail" for g in doc["golden"]):
                s.fail("golden mismatch")
        for k in ("swap", "copy_raw"):
            log.skip(k, "nothing new")
        return

    tmp = db_path.with_name(db_path.stem + ".updating.duckdb")
    tmp.unlink(missing_ok=True)
    try:
        with log.step("load_to_copy") as s:
            stage = work / "stage"
            shutil.rmtree(stage, ignore_errors=True)
            for m, (_, folder) in todo.items():
                (stage / folder).mkdir(parents=True, exist_ok=True)
                for f in (f"{m}.csv", f"{m}_info.csv"):
                    shutil.copy2(src / f, stage / folder / f)
            shutil.copy2(db_path, tmp)
            for folder in sorted({f for _, f in todo.values()}):
                load_to_db(folder, data_dir=stage / folder, db_path=tmp)
            after = _snapshot(tmp)
            s.details.update(new=len(new_ids), replaced=len(report["replaced"]))
        doc["freshness_after"] = _freshness(after)
        doc["fingerprint_after"] = _fingerprint(
            after, set(before)
        )  # old matches only, so it compares 1:1 with before
        doc["new_by_competition"] = new_summary(after)
        report["latest_after"] = {k: v["latest"] for k, v in doc["freshness_after"].items()}

        with log.step("checks") as s:
            report["checks"] = _checks(tmp, src, todo)
            report["checks"].update(_extra_checks(before, after, new_ids, todo, replace_changed))
            doc["checks"] += _as_checks(report["checks"])
            s.details.update({c["name"]: c["status"] for c in doc["checks"]})
            if any(c["status"] == "fail" for c in doc["checks"]):
                s.fail("a check failed")
        with log.step("golden") as s:
            doc["golden"] = run_golden(tmp, golden)
            s.details.update({g["name"]: g["status"] for g in doc["golden"]})
            if any(g["status"] == "fail" for g in doc["golden"]):
                s.fail("golden mismatch")
        report["ok"] = all(c["ok"] for c in report["checks"].values()) and all(
            g["status"] == "pass" for g in doc["golden"]
        )
        if not report["ok"]:
            log.skip("swap", "checks or golden failed; live DB untouched")
            log.skip("copy_raw", "checks or golden failed")
            return
        with log.step("swap") as s:
            stamp = date.today().isoformat()
            prev = db_path.with_name(f"{db_path.stem}_prev_{stamp}.duckdb")
            if prev.exists():
                prev = db_path.with_name(
                    f"{db_path.stem}_prev_{stamp}_{pd.Timestamp.now():%H%M%S}.duckdb"
                )
            try:
                os.replace(db_path, prev)
            except PermissionError as e:
                raise RuntimeError(
                    _LOCK_MSG.format(n=db_path.name) + " Nothing was changed."
                ) from e
            os.replace(tmp, db_path)
            report.update(swapped=True, backup=prev.name)
            s.details["backup"] = prev.name
        with log.step("copy_raw"):  # keep data/raw reproducible
            for m, (_, folder) in todo.items():
                (raw_root / folder).mkdir(parents=True, exist_ok=True)
                for f in (f"{m}.csv", f"{m}_info.csv"):
                    shutil.copy2(stage / folder / f, raw_root / folder / f)
    finally:
        tmp.unlink(missing_ok=True)
        tmp.with_name(tmp.name + ".wal").unlink(missing_ok=True)


def run_health(db_path: Path | None = None, golden: list | None = None) -> dict:
    """Read-only audit of a DB: fingerprint + freshness, integrity, golden numbers. Logged as kind=health."""
    from .cricsheet import default_db_path

    db_path = Path(db_path or default_db_path())
    log = RunLog("health", db_path, {"golden": "custom" if golden is not None else GOLDEN.name})
    doc = log.doc
    try:
        with log.step("fingerprint") as s:
            snap = _snapshot(db_path)
            doc["freshness_before"] = doc["freshness_after"] = _freshness(snap)
            doc["fingerprint_before"] = doc["fingerprint_after"] = _fingerprint(snap)
            s.details["matches"] = len(snap)
        with log.step("integrity") as s:
            doc["checks"] += _as_checks(_integrity(db_path))
            if any(c["status"] == "fail" for c in doc["checks"]):
                s.fail("integrity check failed")
        with log.step("golden") as s:
            doc["golden"] = run_golden(db_path, golden)
            if any(g["status"] == "fail" for g in doc["golden"]):
                s.fail("golden mismatch")
    except Exception as e:
        log.finish(False, f"{type(e).__name__}: {e}")
        raise
    bad = [c["name"] for c in doc["checks"] if c["status"] == "fail"] + [
        g["name"] for g in doc["golden"] if g["status"] == "fail"
    ]
    path = log.finish(not bad, f"failed: {bad}" if bad else None)
    lines = [f"Health of {db_path.name}: {len(snap)} matches"]
    lines += [
        f"  {k}: {v['matches']} matches, latest {v['latest']}"
        for k, v in sorted(doc["freshness_after"].items())
    ]
    lines += [f"  [{c['status']}] {c['name']}: {c['message']}" for c in doc["checks"]]
    lines += [
        f"  [{g['status']}] golden {g['name']}: expected {g['expected']}, got {g['actual']}"
        for g in doc["golden"]
    ]
    lines.append(f"  result: ok={not bad}  log={path}")
    print("\n".join(lines))
    return {"ok": not bad, "run_id": doc["run_id"], "log_path": str(path), "failed": bad}


def _finish(report: dict) -> dict:
    n_new = sum(len(v) for v in report["new_by_competition"].values())
    lines = [
        f"Update ({'dry run' if report['dry_run'] else 'real'}): zips {report['zips']}",
        f"  files {report['files_seen']}, not tracked {report['skipped_not_tracked']}, unreadable "
        f"{report['skipped_unreadable']}, already in DB {report['already_in_db']} "
        f"(changed {len(report['changed'])}: {report['changed'][:10]}), new {n_new}",
    ]
    for k, v in sorted(report["new_by_competition"].items()):
        lines.append(f"  new {k}: {len(v)}")
    for name, ch in report["checks"].items():
        lines.append(
            f"  [{ch.get('status') or ('ok' if ch['ok'] else 'FAIL')}] {name}: {ch['detail']}"
        )
    if report["latest_after"]:
        for k in sorted(set(report["latest_before"]) | set(report["latest_after"])):
            lines.append(
                f"  latest {k}: {report['latest_before'].get(k)} -> {report['latest_after'].get(k)}"
            )
    lines.append(
        f"  result: ok={report['ok']} swapped={report['swapped']} backup={report['backup']}"
    )
    lines.append(f"  log: {report['log_path']}")
    report["text"] = "\n".join(lines)
    print(report["text"])
    return report
