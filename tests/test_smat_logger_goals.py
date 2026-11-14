"""Goal tests for the S26 live logger (frozen): over-6/10/15 end states, append-only writer, required keys, no cross-match metrics."""
import json
import re
from pathlib import Path

from cricket_analytics.live import smat_logger as L

FIX = Path(__file__).parent / "fixtures" / "smat_live_comm1.json"
LIVE_DIR = Path(L.__file__).parent


def test_checkpoints_from_over_summaries():
    cp = L.checkpoints(json.loads(FIX.read_text()))
    got = {o: (c["runs"], c["wickets"], c["balls"]) for o, c in cp.items()}
    # real Cricbuzz over-summary lines of Karnataka's innings (saved SMAT 2025 payload): ends of over 6, 10, 15
    assert got == {6: (55, 2, 36), 10: (82, 2, 60), 15: (106, 6, 90)}


def test_checkpoints_ignore_unfinished_overs():
    d = json.loads(FIX.read_text())
    d["commentary"][0]["commentaryList"] = [x for x in d["commentary"][0]["commentaryList"] if (x.get("overSeparator") or {}).get("overNum", 99) < 9.6]
    assert set(L.checkpoints(d)) == {6}


def test_writer_append_only_and_dedup(tmp_path):
    f = tmp_path / "p.jsonl"
    w = L.Writer(f)
    a = {"match_id": "1", "innings": 1, "checkpoint": "over6", "kind": "inplay", "x": 1}
    assert w.write(a) is True
    assert w.write({**a, "x": 2}) is False  # same key: not written again
    assert w.write({**a, "innings": 2}) is True
    w2 = L.Writer(f)  # restart: still de-duplicated
    assert w2.write(a) is False
    rows = [json.loads(x) for x in f.read_text().splitlines()]
    assert [r["x"] for r in rows] == [1, 1] and rows[0] == a


def test_line_has_required_keys():
    m = dict(id="1", series="Syed Mushtaq Ali Trophy Elite 2026", team_a="A", team_b="B", venue="V")
    r = L.line("inplay", m, "over6", 1, dict(runs=1, wickets=0, balls=36, target=None), {"p": 0.5}, "http://x", flags=["unknown_venue"])
    assert L.REQUIRED_KEYS <= set(r)
    assert r["flags"] == ["unknown_venue"]


def test_no_cross_match_metrics_in_code():
    bad = re.compile(r"\b(mae|brier|log_loss|logloss|pinball|bootstrap|cov80|accuracy|calibration|np\.mean|statistics)\b", re.I)
    for f in LIVE_DIR.glob("*.py"):
        assert not bad.search(f.read_text(encoding="utf-8")), f.name
