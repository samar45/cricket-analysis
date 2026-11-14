"""Goal test: Cricsheet withholds every Afghanistan match on purpose, so verify must say so (not unmapped, not waiting). Frozen."""
import pandas as pd

from cricket_analytics.ingest import cricbuzz_sync as sy


def _row(t1, t2):
    m = dict(match_id="172731", date=pd.Timestamp("2026-11-01").date(), team1=t1, team2=t2, winner=t1)
    return sy.verify_one(m, pd.DataFrame(), pd.DataFrame(), None, "t20i", {}, {}, {"Zimbabwe"})


def test_afghanistan_match_is_cricsheet_withheld():
    for a, b in (("Afghanistan", "Zimbabwe"), ("Zimbabwe", "Afghanistan")):
        r = _row(a, b)
        assert r["status"] == "cricsheet_withheld"


def test_withheld_has_its_own_summary_line():
    res = pd.DataFrame([dict(_row("Afghanistan", "Zimbabwe"), comp="t20i")])
    import tempfile
    from pathlib import Path

    p = Path(tempfile.mkdtemp()) / "v.md"
    sy.write_doc(res, [], p)
    assert "withheld by Cricsheet | 1 |" in p.read_text(encoding="utf-8")
