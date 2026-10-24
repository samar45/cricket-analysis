"""Dashboard smoke tests with Streamlit's AppTest, on the real DB (skipped when it is missing).

Every registered module is opened on the Explore page with its default params, then again with
competition=ipl and players filled in where a module has a player param. Zero exceptions, zero st.error.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cricket_analytics import registry

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
REAL = Path(__file__).parent.parent / "data" / "cricket_analytics.duckdb"
pytestmark = pytest.mark.skipif(not REAL.exists(), reason="real DB not built")

IDS = [m.id for m in registry.all_modules()]
PLAYERS = {"player": "V Kohli", "player2": "RG Sharma"}


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=120).run()


def open_module(at: AppTest, module_id: str) -> AppTest:
    at.sidebar.radio(key="page").set_value("Explore").run()
    at.radio(key="category").set_value(registry.get(module_id).category).run()
    return at.selectbox(key="module").set_value(module_id).run()


def assert_clean(at: AppTest, module_id: str = ""):
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert not [c for c in at.caption if "no chart yet" in c.value], f"{module_id} has no viz/<id>.py"


def test_overview_loads():
    at = new_app()
    assert_clean(at)
    assert len(at.markdown) >= 16 and len(at.dataframe) == 2          # one card per competition, two leader tables
    at.selectbox(key="ov_comp").set_value("t20i_women").run()      # leaders follow the chosen competition
    assert_clean(at)


@pytest.mark.parametrize("module_id", IDS)
def test_module_defaults(module_id):
    at = open_module(new_app(), module_id)
    for p in registry.get(module_id).params:   # required players have no "Any" option; matchup needs one of two
        if p.required or (module_id == "matchup" and p.name in PLAYERS):
            at.selectbox(key=f"p_{p.name}").set_value(PLAYERS[p.name]).run()
    assert_clean(at, module_id)
    assert at.selectbox(key="module").value == module_id


@pytest.mark.parametrize("module_id", IDS)
def test_module_ipl_with_players(module_id):
    mod = registry.get(module_id)
    at = open_module(new_app(), module_id)
    at.selectbox(key="p_competition").set_value("ipl").run()
    names = dict(PLAYERS, **({"player2": "JJ Bumrah"} if module_id == "matchup" else {}))
    for p in mod.params:
        if p.name in names:
            at.selectbox(key=f"p_{p.name}").set_value(names[p.name]).run()
    assert_clean(at, module_id)
    if module_id == "pace_vs_spin":
        assert at.warning, "experimental modules show a banner"
    if module_id == "batting":
        at.toggle(key="batting_include_super_overs").set_value(True).run()
        assert_clean(at, module_id)
        assert any(r.get("total_runs") == 9346 for r in at.dataframe[0].value.to_dict("records")), "Kohli IPL runs with super overs"
