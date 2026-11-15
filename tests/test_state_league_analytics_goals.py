"""Per-league state analytics goals. Frozen: do not edit to make them pass."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cricket_analytics.scouting import leagues as L
from cricket_analytics.scouting import profile as P

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
pytestmark = pytest.mark.skipif(not P.available(), reason="Cricbuzz scouting data not present")


def _runs(key, seasons, name):
    t = L.league_batting(key, seasons)
    return t[t["name"] == name].iloc[0]["runs"]


def test_spl_2026_top_scorer_naman_dhir():
    t = L.league_batting("state_spl", [2026])
    assert t.iloc[0]["name"] == "Naman Dhir" and int(t.iloc[0]["runs"]) == 655


def test_maharaja_karun_nair_1429():
    t = L.league_batting("state_maharaja", None)
    assert int(t[t["name"] == "Karun Nair"].iloc[0]["runs"]) == 1429


def test_tnpl_tushar_raheja_1429():
    assert int(_runs("state_tnpl", None, "Tushar Raheja")) == 1429


def test_leagues_lists_spl_and_upt20():
    names = {k: n for k, n, _ in L.leagues()}
    assert "Sher-e-Punjab" in names["state_spl"] and "UP T20" in names["state_upt20"]
    seasons = {k: s for k, _, s in L.leagues()}
    assert seasons["state_tnpl"] == [2023, 2024, 2025, 2026]


def test_bowling_table_columns_and_order():
    t = L.league_bowling("state_upt20", [2025])
    assert len(t) > 20 and {"wkts", "econ", "overs", "best"} <= set(t.columns)
    assert t["wkts"].is_monotonic_decreasing


def test_teams_played_is_twice_matches():
    for key in ("state_spl", "state_tnpl", "state_dpl"):
        t = L.league_teams(key, None)
        s = L.league_summary(key, None)
        assert t["played"].sum() == 2 * s["matches"]
        assert (t["won"] + t["lost"] + t["nr"] == t["played"]).all()


def test_summary_spl():
    s = L.league_summary("state_spl", [2026])
    assert s["matches"] == 27 and s["top_scorer"].startswith("Naman Dhir") and s["total_runs"] > 5000


def _open():
    at = AppTest.from_file(APP, default_timeout=300).run()
    return at.sidebar.radio(key="page").set_value("State leagues").run()


def test_page_overview_default_league():
    at = _open()
    assert not at.exception and not at.error
    assert "Sher-e-Punjab" in at.selectbox(key="sl_league").value
    assert [t.label for t in at.tabs][:3] == ["Overview", "Batting", "Bowling"]


def test_page_choose_up_t20_shows_batting_rows():
    at = _open()
    up = [o for o in at.selectbox(key="sl_league").options if "UP T20" in o][0]
    at = at.selectbox(key="sl_league").set_value(up).run()
    assert not at.exception and not at.error
    tables = at.get("table")
    assert len(tables) >= 2 and all(len(t.value) > 0 for t in tables)
    assert "Karan Sharma" in tables[1].value["name"].tolist()
