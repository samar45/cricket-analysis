"""Update safety checks, golden numbers, health command and run log. Offline: fixture DB + fake recently-added zip."""
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import duckdb
import pytest

import cricket_analytics.ingest.update as u
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.ingest.update import run_golden, run_health, run_update

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
GOOD = [{"name": "one match", "sql": "SELECT count(*) FROM matches", "expected": 1},
        {"name": "at least one", "sql": "SELECT count(*) FROM matches", "expected": 1, "op": "ge"}]
KEYS = {"schema", "run_id", "kind", "started", "finished", "ok", "error", "db_path", "args", "steps", "checks",
        "new_by_competition", "skipped_events", "changed_matches", "freshness_before", "freshness_after",
        "fingerprint_before", "fingerprint_after", "golden", "swapped", "backup"}
STEPS = ["lock_check", "download", "classify", "load_to_copy", "checks", "golden", "swap", "copy_raw"]


def _text(sub, name):
    return (FIX / sub / name).read_text(encoding="utf-8")


def _clone(new_id, **info_edits):
    info = _text("ipl", "1082591_info.csv").replace("1082591", new_id)
    for old, new in info_edits.items():
        assert old in info
        info = info.replace(old, new)
    return {f"{new_id}.csv": _text("ipl", "1082591.csv").replace("1082591", new_id), f"{new_id}_info.csv": info}


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for n, t in files.items():
            zf.writestr(n, t)
    return path


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=db)
    files = {n: _text("ipl", n) for n in ("1082591.csv", "1082591_info.csv")}           # already in DB
    files |= {n: _text("hundred", n) for n in ("1252666.csv", "1252666_info.csv")}      # new
    files |= _clone("9000002", **{"info,match_type,T20": "info,match_type,ODI"})        # untracked
    z = _zip(tmp_path / "recently_added_30_male_csv2.zip", files)
    kw = dict(db_path=db, download=False, zip_paths=[z], raw_root=tmp_path / "raw", updates_root=tmp_path / "upd", golden=[])
    return db, tmp_path, kw


def _ids(db):
    c = duckdb.connect(str(db), read_only=True)
    try:
        return {r[0] for r in c.execute("SELECT match_id FROM matches").fetchall()}
    finally:
        c.close()


def _log(r):
    return json.loads(Path(r["log_path"]).read_text(encoding="utf-8"))


def _check(log, name):
    return next(c for c in log["checks"] if c["name"] == name)


def test_log_schema_and_steps(env):
    db, tmp, kw = env
    r = run_update(**{**kw, "golden": [{"name": "two", "sql": "SELECT count(*) FROM matches", "expected": 2}]})
    d = _log(r)
    assert set(d) == KEYS and d["schema"] == 1 and d["kind"] == "update" and re.fullmatch(r"\d{8}-\d{6}", d["run_id"])
    assert d["ok"] and d["swapped"] is True and d["backup"] == r["backup"] and d["error"] is None
    assert [s["name"] for s in d["steps"]] == STEPS and all(s["status"] in ("pass", "skip") for s in d["steps"])
    assert all(set(c) == {"name", "status", "expected", "actual", "message"} for c in d["checks"])
    assert d["new_by_competition"] == {"hundred": {"matches": 1, "earliest": "2021-07-22", "latest": "2021-07-22"}}
    assert d["golden"] == [{"name": "two", "expected": 2, "actual": 2, "status": "pass"}]
    assert d["skipped_events"] == [{"event": "Indian Premier League", "match_type": "ODI", "gender": "male", "count": 1}]
    assert d["freshness_after"]["hundred"]["matches"] == 1 and d["fingerprint_before"] == d["fingerprint_after"]
    assert (db.parent / "runs" / f"{d['run_id']}.json").exists()


def test_dry_run_is_logged(env):
    _, _, kw = env
    d = _log(run_update(dry_run=True, **kw))
    assert d["kind"] == "dry_run" and d["ok"] and d["new_by_competition"]["hundred"]["matches"] == 1


def test_old_data_unchanged_passes(env):
    c = _check(_log(run_update(**env[2])), "old_data_unchanged")
    assert c["status"] == "pass" and c["expected"] == c["actual"]


def test_old_data_changed_during_load_fails_and_does_not_swap(env, monkeypatch):
    db, tmp, kw = env
    real = u.load_to_db

    def bad_loader(*a, **k):      # a buggy loader that also alters an old ball
        real(*a, **k)
        con = duckdb.connect(str(k["db_path"]))
        con.execute("UPDATE deliveries SET runs_total = runs_total + 1 WHERE match_id = '1082591' AND ball_seq = 1")
        con.close()

    monkeypatch.setattr(u, "load_to_db", bad_loader)
    r = run_update(**kw)
    d = _log(r)
    assert r["ok"] is False and not r["swapped"] and d["ok"] is False and d["swapped"] is False
    assert _check(d, "old_data_unchanged")["status"] == "fail" and "1082591" in _check(d, "old_data_unchanged")["message"]
    assert next(s for s in d["steps"] if s["name"] == "swap")["status"] == "skip"
    assert _ids(db) == {"1082591"} and not list(tmp.glob("*.updating.*")) and not list(tmp.glob("*_prev_*"))


def test_replace_changed_only_warns(env):
    db, tmp, kw = env
    ball = _text("ipl", "1082591.csv").splitlines()
    z = _zip(tmp / "recently_added_7_male_csv2.zip", {"1082591.csv": "\n".join(ball[:-1]) + "\n",
                                                      "1082591_info.csv": _text("ipl", "1082591_info.csv")})
    r = run_update(**{**kw, "zip_paths": [z], "replace_changed": True})
    d = _log(r)
    assert r["swapped"] and _check(d, "old_data_unchanged")["status"] == "warn"
    assert d["changed_matches"][0]["match_id"] == 1082591


def test_golden_values(env):
    db, _, _ = env
    out = run_golden(db, GOOD + [{"name": "wrong", "sql": "SELECT count(*) FROM matches", "expected": 5},
                                 {"name": "too low", "sql": "SELECT count(*) FROM matches", "expected": 5, "op": "ge"},
                                 {"name": "module", "module": "batting", "params": {"competition": "ipl"},
                                  "column": "total_runs", "expected": -1},
                                 {"name": "broken", "sql": "SELECT nope FROM matches", "expected": 1}])
    assert [g["status"] for g in out] == ["pass", "pass", "fail", "fail", "fail", "fail"]
    assert out[3]["expected"] == ">= 5" and str(out[5]["actual"]).startswith("error")


def test_golden_mismatch_blocks_swap(env):
    db, tmp, kw = env
    r = run_update(**{**kw, "golden": [{"name": "bad", "sql": "SELECT count(*) FROM matches", "expected": 99}]})
    d = _log(r)
    assert not r["ok"] and not r["swapped"] and d["ok"] is False and "bad" in d["error"]
    assert d["golden"][0]["status"] == "fail" and _ids(db) == {"1082591"}


def test_real_golden_file_is_valid_json():
    g = json.loads(u.GOLDEN.read_text(encoding="utf-8"))
    assert len(g) >= 8 and all({"name", "expected"} <= set(x) and ("sql" in x or {"module", "column"} <= set(x)) for x in g)


def test_lookalike_event_warns(env):
    db, tmp, kw = env
    files = _clone("9000003", **{"info,event,Indian Premier League": "info,event,IPL Super Cup"})
    files |= {n: _text("hundred", n) for n in ("1252666.csv", "1252666_info.csv")}
    z = _zip(tmp / "recently_added_7_male_csv2.zip", files)
    d = _log(run_update(**{**kw, "zip_paths": [z]}))
    c = _check(d, "skipped_events")
    assert c["status"] == "warn" and c["actual"][0]["event"] == "IPL Super Cup" and d["ok"]
    assert {"event": "IPL Super Cup", "match_type": "T20", "gender": "male", "count": 1} in d["skipped_events"]


def test_clean_skips_pass(env):
    assert _check(_log(run_update(**env[2])), "skipped_events")["status"] == "pass"


def test_balls_per_match_sane(env):
    assert _check(_log(run_update(**env[2])), "balls_per_match_sane")["status"] == "pass"


def test_balls_per_match_outside_range_warns(env, monkeypatch):
    monkeypatch.setattr(u, "_BALLS_RANGE", {"hundred": (1000, 2000)})
    r = run_update(**env[2])
    c = _check(_log(r), "balls_per_match_sane")
    assert c["status"] == "warn" and c["actual"][0][0] == "1252666" and r["swapped"]   # a warning does not block


def test_locked_db_fails_early(env):
    db, tmp, kw = env
    code = "import duckdb,time,sys;c=duckdb.connect(sys.argv[1],read_only=True);print('ready',flush=True);time.sleep(60)"
    p = subprocess.Popen([sys.executable, "-c", code, str(db)], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="stop the dashboard"):
            run_update(**kw)
    finally:
        p.kill()
        p.wait()
    d = json.loads(next((tmp / "runs").glob("*.json")).read_text(encoding="utf-8"))
    assert d["ok"] is False and "dashboard" in d["error"] and d["steps"][0]["name"] == "lock_check"
    assert d["steps"][0]["status"] == "fail" and _ids(db) == {"1082591"}


def test_health_ok_and_logged(env):
    db, tmp, _ = env
    r = run_health(db, golden=GOOD)
    d = json.loads(Path(r["log_path"]).read_text(encoding="utf-8"))
    assert r["ok"] and d["kind"] == "health" and set(d) == KEYS and d["ok"]
    assert [s["name"] for s in d["steps"]] == ["fingerprint", "integrity", "golden"]
    assert d["fingerprint_after"]["ipl"]["matches"] == 1 and d["fingerprint_after"]["ipl"]["balls"] > 0
    assert {c["name"] for c in d["checks"]} == {"no_duplicate_keys", "every_match_has_deliveries", "no_orphan_deliveries"}


def test_health_detects_problems(env):
    db, tmp, _ = env
    con = duckdb.connect(str(db))
    con.execute("INSERT INTO matches (match_id, date, competition, gender) VALUES ('777', DATE '2020-01-01', 'ipl', 'male')")
    con.close()
    r = run_health(db, golden=[{"name": "bad", "sql": "SELECT 1", "expected": 2}])
    assert not r["ok"] and set(r["failed"]) == {"every_match_has_deliveries", "bad"}
