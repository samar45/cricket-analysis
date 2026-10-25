"""Incremental update, offline: a fake recently-added zip built from the ingest fixtures."""
import zipfile
from pathlib import Path

import duckdb
import pytest

from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.ingest.update import classify, run_update

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
WOMEN, ODI = "9000001", "9000002"


def _clone(sub, src_id, new_id, **info_edits):
    """(name -> text) for a fixture match copied under a new id with some info lines replaced."""
    ball = (FIX / sub / f"{src_id}.csv").read_text(encoding="utf-8").replace(src_id, new_id)
    info = (FIX / sub / f"{src_id}_info.csv").read_text(encoding="utf-8").replace(src_id, new_id)
    for old, new in info_edits.items():
        assert old in info
        info = info.replace(old, new)
    return {f"{new_id}.csv": ball, f"{new_id}_info.csv": info}


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=db)
    files = {p.name: p.read_text(encoding="utf-8") for p in (FIX / "ipl").glob("1082591*.csv")}  # already in DB
    files |= {p.name: p.read_text(encoding="utf-8") for p in (FIX / "hundred").glob("1252666*.csv")}  # new
    files |= _clone("ipl", "1082591", WOMEN, **{"info,team_type,club": "info,team_type,international",
                                                "info,gender,male": "info,gender,female"})
    files |= _clone("ipl", "1082591", ODI, **{"info,match_type,T20": "info,match_type,ODI"})
    files["README.txt"] = "ignore me"
    files["all_matches.csv"] = "junk"
    z = tmp_path / "recently_added_30_male_csv2.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for n, t in files.items():
            zf.writestr(n, t)
    kw = dict(db_path=db, download=False, zip_paths=[z], raw_root=tmp_path / "raw", updates_root=tmp_path / "upd", golden=[])
    return db, tmp_path, kw


def _ids(db):
    c = duckdb.connect(str(db), read_only=True)
    try:
        return {r[0] for r in c.execute("SELECT match_id FROM matches").fetchall()}
    finally:
        c.close()


def test_classify():
    assert classify({"match_type": "T20", "gender": "male", "team_type": "club", "event": "Indian Premier League"}) == "ipl"
    assert classify({"match_type": "T20", "gender": "female", "team_type": "international"}) == "t20i_women"
    assert classify({"match_type": "T20", "gender": "female", "team_type": "club", "event": "Big Bash"}) is None
    assert classify({"match_type": "ODI", "gender": "male", "team_type": "international"}) is None


def test_dry_run_changes_nothing(env):
    db, _, kw = env
    r = run_update(dry_run=True, **kw)
    assert {k: len(v) for k, v in r["new_by_competition"].items()} == {"hundred": 1, "t20i_women": 1}
    assert (r["already_in_db"], r["skipped_not_tracked"], r["changed"]) == (1, 1, [])
    assert _ids(db) == {"1082591"}


def test_real_update_swaps_and_keeps_backup(env):
    db, tmp, kw = env
    r = run_update(**kw)
    assert r["ok"] and r["swapped"] and all(c["ok"] for c in r["checks"].values())
    assert _ids(db) == {"1082591", "1252666", WOMEN}
    assert (tmp / r["backup"]).exists() and _ids(tmp / r["backup"]) == {"1082591"}
    assert (tmp / "raw" / "hundred" / "1252666.csv").exists() and (tmp / "raw" / "t20s" / f"{WOMEN}.csv").exists()
    assert not list(tmp.glob("*.updating.*"))
    assert run_update(**kw)["new_by_competition"] == {}      # second run: nothing new


def test_failed_check_leaves_db_untouched(env, monkeypatch):
    db, tmp, kw = env
    import cricket_analytics.ingest.update as u
    monkeypatch.setattr(u, "_checks", lambda *a: {"x": {"ok": False, "detail": "forced"}})
    r = run_update(**kw)
    assert r["ok"] is False and not r["swapped"]
    assert _ids(db) == {"1082591"} and not list(tmp.glob("*.updating.*"))


def test_changed_file_reported_not_replaced(env):
    db, tmp, kw = env
    ball = (FIX / "ipl" / "1082591.csv").read_text(encoding="utf-8").splitlines()
    z2 = tmp / "recently_added_7_male_csv2.zip"
    with zipfile.ZipFile(z2, "w") as zf:      # same match with the last ball dropped
        zf.writestr("1082591.csv", "\n".join(ball[:-1]) + "\n")
        zf.writestr("1082591_info.csv", (FIX / "ipl" / "1082591_info.csv").read_text(encoding="utf-8"))
    r = run_update(**{**kw, "zip_paths": [z2]})
    assert r["changed"] == ["1082591"] and r["new_by_competition"] == {} and not r["swapped"]
