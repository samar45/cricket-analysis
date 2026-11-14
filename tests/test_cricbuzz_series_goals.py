"""Goal tests for the Cricbuzz SMAT 2025 parser, on two saved raw matches (data/external, gitignored). Frozen."""
import pandas as pd
import pytest

from cricket_analytics.ingest import cricbuzz_series as cb

MATCHES = ["127830", "128787"]  # a group game (no ball-by-ball) and the final (full ball-by-ball)


@pytest.fixture(scope="module")
def parsed():
    if not all((cb.ROOT / m / "scorecard.html.gz").exists() for m in MATCHES):
        pytest.skip("raw Cricbuzz sample not saved locally")
    return {m: cb.parse_match(m, dict(desc="x"), {}) for m in MATCHES}


@pytest.mark.parametrize("m", MATCHES)
def test_batting_plus_extras_is_innings_total(parsed, m):
    r = parsed[m]
    bat = pd.DataFrame(r["batting"]).groupby("innings").runs.sum()
    for i in r["innings"]:
        assert bat[i["innings"]] + i["extras"] == i["runs"]


@pytest.mark.parametrize("m", MATCHES)
def test_wickets_at_most_ten(parsed, m):
    r = parsed[m]
    bowl = pd.DataFrame(r["bowling"]).groupby("innings").wickets.sum()
    assert (bowl <= 10).all()
    assert all(i["wickets"] <= 10 for i in r["innings"])


def test_deliveries_match_scorecard_when_present(parsed):
    r = parsed["128787"]
    d = pd.DataFrame(r["deliveries"])
    assert len(d) > 0
    for i in r["innings"]:
        assert d[d.innings == i["innings"]].runs_total.sum() == i["runs"]
    assert (d.runs_total == d.runs_batter + d.runs_extras).all()
    assert d.over_num.min() == 0 and d.over_num.max() == 19


def test_no_ball_by_ball_leaves_no_deliveries(parsed):
    assert parsed["127830"]["deliveries"] == []


def test_no_s26_matches_listed():
    assert all(m["date"] < cb.S26_FROM for m in cb.all_matches())
