"""Goal tests for `cricket cricbuzz sync` (no network; saved fixtures; DB read-only). Frozen.

Fixtures (tests/fixtures/cricbuzz_sync): the Cricbuzz schedule page reduced to its series/match links, the match list of
the Sri Lanka tour of Pakistan 2026, and the trimmed scorecard of its 1st T20I (Cricbuzz 170687, 2026-10-09), which Cricsheet
also has. (Cricsheet has no SMAT after 2024-12-15 and no Cricbuzz SMAT 2024-25 copy is saved, so a T20I is the shared match.)
"""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from cricket_analytics.ingest import cricbuzz_series as cb
from cricket_analytics.ingest import cricbuzz_sync as sy

F = Path(__file__).parent / "fixtures" / "cricbuzz_sync"
DB = Path(__file__).resolve().parent.parent / "data" / "cricket_analytics.duckdb"


def _page():
    return (F / "series_all.html").read_text(encoding="utf-8")


def test_series_filter_keeps_mens_tracked_t20_and_drops_the_rest():
    kept, cands, unmapped = sy.discover(_page())
    assert {s["comp"] for s in kept} == {"smat"}
    assert {s["id"] for s in kept} == {12420, 12431}
    names = [s["name"] for s in kept + cands]
    assert not any(re.search(r"women|wbbl|wpl|u19|u-19|under", n, re.I) for n in names)
    assert not any(re.search(r"\bTest\b|ODI|Sheffield|Ranji|Ford Trophy", n, re.I) for n in names)
    assert all(s["comp"] != "t20i" for s in kept)  # t20i is only decided from the series' own match list
    assert {"Nepal Premier League 2026", "Abu Dhabi T10 League 2026"} <= set(unmapped)  # T20 but not tracked: logged, skipped


def test_international_series_kept_only_with_t20i_matches():
    ms = sy.series_matches((F / "series_13037.html").read_text(encoding="utf-8"), 13037)
    assert any(sy.is_t20i(m) for m in ms)
    tests_only = [m for m in ms if m["matchFormat"] == "TEST"]
    assert tests_only and not any(sy.is_t20i(m) for m in tests_only)
    got = sy.wanted(ms, "t20i")
    assert [m["matchDesc"] for m in got] == ["1st T20I", "2nd T20I", "3rd T20I"]  # no warm-up, no Test
    assert all(m["state"] == "Complete" for m in got)


def test_saved_matches_are_not_fetched_again(tmp_path):
    ms = [dict(matchId=i, seriesId=1, state="Complete", matchFormat="T20", matchDesc="x") for i in (1, 2, 3)]
    ms.append(dict(matchId=4, seriesId=1, state="Upcoming", matchFormat="T20", matchDesc="x"))
    d = sy.match_dir("ipl", 1, 2, tmp_path)
    d.mkdir(parents=True)
    (d / "scorecard.html.gz").write_bytes(b"x")
    todo = sy.to_fetch(ms, "ipl", tmp_path)
    assert [m["matchId"] for m in todo] == [1, 3]  # 2 saved, 4 not finished
    calls = []
    sy.scrape_match(todo[0], "ipl", tmp_path, fetch=lambda mid, root: (calls.append(mid), (root / mid).mkdir(parents=True, exist_ok=True)))
    assert calls == ["1"]


def test_two_syncs_never_overlap(tmp_path):
    lock = tmp_path / ".sync.lock"
    sy.acquire(lock)
    with pytest.raises(sy.Locked):
        sy.acquire(lock)
    sy.release(lock)
    sy.acquire(lock)  # free again


@pytest.fixture(scope="module")
def shared():
    if not DB.exists():
        pytest.skip("main DB not built locally")
    import duckdb

    r = cb.parse_match("170687", dict(desc="1st T20I"), {}, root=F)
    con = duckdb.connect(str(DB), read_only=True)
    cs_names = {x[0] for x in con.execute("select team1 from matches where competition='t20i'").fetchall()}
    tp = sy._team_players(con, "t20i")
    yield r, con, cs_names, tp
    con.close()


def _verify(r, con, cs_names, tp, innings=None):
    ii = pd.DataFrame(r["innings"]) if innings is None else innings
    return sy.verify_one(r["match"], ii, pd.DataFrame(r["batting"]), con, "t20i", {}, tp, cs_names)


def test_verify_pairs_cricbuzz_match_with_cricsheet_and_totals_equal(shared):
    r, con, cs_names, tp = shared
    row = _verify(r, con, cs_names, tp)
    assert row["cricsheet_match_id"] == "1550708"
    assert row["status"] == "equal", row["diffs"]
    assert row["batters_compared"] >= 10  # per-batter runs checked where names map


def test_altered_total_is_reported_as_mismatch(shared):
    r, con, cs_names, tp = shared
    ii = pd.DataFrame(r["innings"])
    ii.loc[0, "runs"] += 1
    row = _verify(r, con, cs_names, tp, ii)
    assert row["status"] == "different"
    assert "inn1 runs" in row["diffs"]


def test_unmatched_team_is_logged_not_guessed(shared):
    r, con, cs_names, tp = shared
    m = dict(r["match"], team1="Atlantis XI")
    row = sy.verify_one(m, pd.DataFrame(r["innings"]), pd.DataFrame(r["batting"]), con, "t20i", {}, tp, cs_names)
    assert row["status"] == "unmapped_team" and "Atlantis XI" in row["diffs"]
