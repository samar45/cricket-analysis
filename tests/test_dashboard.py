"""Dashboard smoke tests with Streamlit's AppTest, on the real DB (skipped when it is missing).

Every registered module is opened on the Explore page with its default params, then again with
competition=ipl and players filled in where a module has a player param. Zero exceptions, zero st.error.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cricket_analytics import registry
from cricket_analytics.viz import video
from tests.conftest import requires_real_db

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
pytestmark = requires_real_db

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
    assert not [c for c in at.caption if "no chart yet" in c.value], (
        f"{module_id} has no viz/<id>.py"
    )


def test_overview_loads():
    at = new_app()
    assert_clean(at)
    assert (
        len(at.markdown) >= 16 and len(at.dataframe) == 2
    )  # one card per competition, two leader tables
    at.selectbox(key="ov_comp").set_value(
        "t20i_women"
    ).run()  # leaders follow the chosen competition
    assert_clean(at)


@pytest.mark.parametrize("module_id", IDS)
def test_module_defaults(module_id):
    at = open_module(new_app(), module_id)
    for p in registry.get(
        module_id
    ).params:  # required players have no "Any" option; matchup needs one of two
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
    assert bool(at.warning) == (mod.category == "experimental"), (
        "only experimental modules show the banner"
    )
    if module_id == "batting":
        at.toggle(key="batting_include_super_overs").set_value(True).run()
        assert_clean(at, module_id)
        assert any(r.get("total_runs") == 9346 for r in at.dataframe[0].value.to_dict("records")), (
            "Kohli IPL runs with super overs"
        )


def test_multi_and_season_controls():
    at = open_module(new_app(), "batting")
    at.selectbox(key="p_competition").set_value("ipl").run()
    at.selectbox(key="p_player").set_value("V Kohli").run()
    at.multiselect(key="p_venue").set_value(["M Chinnaswamy Stadium", "Wankhede Stadium"]).run()
    assert_clean(at, "batting")
    assert at.dataframe[0].value.total_runs.iloc[0] == 4139  # two venues, summed
    at.radio(key="p_season_mode").set_value("Last N seasons").run()
    at.number_input(key="p_last_n_years").set_value(5).run()
    at.multiselect(key="p_venue").set_value([]).run()
    assert_clean(at, "batting")
    assert at.dataframe[0].value.total_runs.iloc[0] == 3053  # IPL 2022..2026
    at.radio(key="p_season_mode").set_value("Year range").run()
    at.selectbox(key="p_season_from").set_value(2024).run()
    assert_clean(at, "batting")
    assert at.dataframe[0].value.total_runs.iloc[0] == 741 + 657 + 675
    at.selectbox(key="p_season_from").set_value(None).run()
    at.selectbox(key="batting_group_by").set_value("venue").run()
    assert_clean(at, "batting")


@pytest.mark.parametrize("module_id", IDS)
def test_video_tab(module_id):
    """Every module with a result gets Chart / Table / Video tabs; the aspect toggle and the focus box rerun cleanly."""
    at = open_module(new_app(), module_id)
    at.selectbox(key="p_competition").set_value("ipl").run()
    names = dict(PLAYERS, **({"player2": "JJ Bumrah"} if module_id == "matchup" else {}))
    for p in registry.get(module_id).params:
        if p.name in names:
            at.selectbox(key=f"p_{p.name}").set_value(names[p.name]).run()
    assert_clean(at, module_id)
    assert at.tabs, (
        f"{module_id} returned no rows for Kohli in the IPL, so its tabs cannot be checked"
    )
    assert [t.label for t in at.tabs] == ["Chart", "Table", "Video"]
    assert module_id in video.module_ids()
    assert at.radio(key="video_aspect").value == "9:16"
    html = [e for e in at.get("download_button") if e.proto.label == "Download HTML"]
    assert len(html) == 1
    at.radio(key="video_aspect").set_value("1:1").run()
    assert_clean(at, module_id)
    assert at.radio(key="video_aspect").value == "1:1"
    assert at.text_input(key=f"video_focus_{module_id}").value == ""
    at.radio(key="video_aspect").set_value("9:16").run()
