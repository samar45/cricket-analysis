"""Dashboard smoke tests with Streamlit's AppTest, on the real DB (skipped when it is missing).

Every registered module is opened on the Explore page with its default params, then again with
competition=ipl and players filled in where a module has a player param. Zero exceptions, zero st.error.
"""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cricket_analytics import registry
from cricket_analytics.viz import video
from tests.conftest import requires_real_db

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
pytestmark = requires_real_db

sys.path.insert(0, str(Path(APP).parent))  # the dashboard imports its siblings by bare name
import module_view  # noqa: E402

# trade / xi_odds are generic module views on the IPL market page; auction / scarcity have custom sections there;
# player_card / player_worth are shown by the Player page. Everything else is on Explore.
MARKET_TAB = {"trade": "Trade", "xi_odds": "XI win odds"}
CUSTOM = {"auction", "scarcity"} | module_view.ON_PLAYER_PAGE
IDS = [m.id for m in registry.all_modules() if m.id not in CUSTOM]
PLAYERS = {"player": "V Kohli", "player2": "RG Sharma"}


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=120).run()


def open_module(at: AppTest, module_id: str) -> AppTest:
    if module_id in MARKET_TAB:
        at.sidebar.radio(key="page").set_value("IPL market").run()
        return at.radio(key="market_tab").set_value(MARKET_TAB[module_id]).run()
    at.sidebar.radio(key="page").set_value("Explore").run()
    at.radio(key="category").set_value(registry.get(module_id).category).run()
    return at.selectbox(key="module").set_value(module_id).run()


def go(at: AppTest, scope: str) -> AppTest:
    """Click the Run button of a module / page (nothing computes before this)."""
    return at.button(key=f"run_{scope}").click().run()


def assert_clean(at: AppTest, module_id: str = ""):
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert not [c for c in at.caption if "no chart yet" in c.value], (
        f"{module_id} has no viz/<id>.py"
    )


def test_overview_loads():
    at = new_app()
    assert_clean(at)
    assert len(at.markdown) >= 16 and len(at.dataframe) == 0  # cards only; leaders wait for the button
    go(at, "overview")
    assert_clean(at)
    assert len(at.dataframe) == 2  # two leader tables
    at.selectbox(key="ov_comp").set_value("t20i_women").run()  # leaders follow the chosen competition once re-run
    go(at, "overview")
    assert_clean(at)


@pytest.mark.parametrize("module_id", IDS)
def test_module_defaults(module_id):
    at = open_module(new_app(), module_id)
    for p in registry.get(
        module_id
    ).params:  # required players have no "Any" option; matchup needs one of two
        if p.required or (module_id == "matchup" and p.name in PLAYERS):
            at.selectbox(key=f"p_{p.name}").set_value(PLAYERS[p.name]).run()
    go(at, module_id)
    assert_clean(at, module_id)
    if module_id not in MARKET_TAB:
        assert at.selectbox(key="module").value == module_id


@pytest.mark.parametrize("module_id", IDS)
def test_module_ipl_with_players(module_id):
    mod = registry.get(module_id)
    at = open_module(new_app(), module_id)
    if any(x.key == "p_competition" for x in at.selectbox):  # the IPL market tools have no competition selector
        at.selectbox(key="p_competition").set_value("ipl").run()
    names = dict(PLAYERS, **({"player2": "JJ Bumrah"} if module_id == "matchup" else {}))
    for p in mod.params:
        if p.name in names:
            at.selectbox(key=f"p_{p.name}").set_value(names[p.name]).run()
    go(at, module_id)
    assert_clean(at, module_id)
    assert bool(at.warning) == (mod.category == "experimental" and module_id not in module_view.LEAN), (  # these pages are numbers only
        "only experimental modules show the banner"
    )
    if module_id == "batting":
        at.toggle(key="batting_include_super_overs").set_value(True).run()
        go(at, "batting")
        assert_clean(at, module_id)
        assert any(r.get("total_runs") == 9346 for r in at.dataframe[0].value.to_dict("records")), (
            "Kohli IPL runs with super overs"
        )


def test_multi_and_season_controls():
    at = open_module(new_app(), "batting")
    at.selectbox(key="p_competition").set_value("ipl").run()
    at.selectbox(key="p_player").set_value("V Kohli").run()
    at.multiselect(key="p_venue").set_value(["M Chinnaswamy Stadium", "Wankhede Stadium"]).run()
    go(at, "batting")
    assert_clean(at, "batting")
    assert at.dataframe[0].value.total_runs.iloc[0] == 4139  # two venues, summed
    at.radio(key="p_season_mode").set_value("Last N seasons").run()
    at.number_input(key="p_last_n_years").set_value(5).run()
    at.multiselect(key="p_venue").set_value([]).run()
    go(at, "batting")
    assert_clean(at, "batting")
    assert at.dataframe[0].value.total_runs.iloc[0] == 3053  # IPL 2022..2026
    at.radio(key="p_season_mode").set_value("Year range").run()
    at.selectbox(key="p_season_from").set_value(2024).run()
    go(at, "batting")
    assert_clean(at, "batting")
    assert at.dataframe[0].value.total_runs.iloc[0] == 741 + 657 + 675
    at.selectbox(key="p_season_from").set_value(None).run()
    at.selectbox(key="batting_group_by").set_value("venue").run()
    go(at, "batting")
    assert_clean(at, "batting")


@pytest.mark.parametrize("module_id", IDS)
def test_video_tab(module_id):
    """Every module with a result gets Chart / Table / Video tabs; the aspect toggle and the focus box rerun cleanly."""
    at = open_module(new_app(), module_id)
    if any(x.key == "p_competition" for x in at.selectbox):  # the IPL market tools have no competition selector
        at.selectbox(key="p_competition").set_value("ipl").run()
    names = dict(PLAYERS, **({"player2": "JJ Bumrah"} if module_id == "matchup" else {}))
    for p in registry.get(module_id).params:
        if p.name in names:
            at.selectbox(key=f"p_{p.name}").set_value(names[p.name]).run()
    go(at, module_id)
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


def test_nothing_runs_before_run(monkeypatch):
    """Opening a module shows no result and never calls api.run; changing params afterwards shows the stale tag."""
    import streamlit as st
    from cricket_analytics import api

    st.cache_data.clear()

    calls = []
    real = api.run
    monkeypatch.setattr(api, "run", lambda *a, **k: calls.append(a) or real(*a, **k))
    at = open_module(new_app(), "batting")
    assert not calls and not at.dataframe and not at.tabs
    go(at, "batting")
    assert calls and at.dataframe
    n = len(calls)
    at.selectbox(key="p_competition").set_value("ipl").run()  # param change alone: no recompute, stale tag
    assert len(calls) == n and any("params changed" in c.value for c in at.caption)


def test_player_page():
    """Player page: default IPL 2023-26 for three different roles (bowler, keeper-batter, all-rounder), no errors, sections present."""
    at = new_app()
    at.sidebar.radio(key="page").set_value("Player").run()
    assert_clean(at)
    assert "WAR v3 by season" not in " ".join(m.value for m in at.markdown)  # waits for Run
    assert at.selectbox(key="pl_who").value is None and not at.text_input  # one search box, empty until chosen
    for name, role_word, tag in (("JJ Bumrah", "bowler", "Complete"), ("H Klaasen", "batter", "Two-phase"), ("HH Pandya", "all-rounder", "Middle-overs specialist")):
        at.selectbox(key="pl_who").set_value(name).run()
        go(at, "player")
        assert_clean(at)
        page = " ".join(m.value for m in at.markdown)
        assert name in page and role_word in page and "WAR v3 by season" in page and "Player worth" in page and "Phase profile" in page and tag in page, name
    assert at.selectbox(key="pl_comp").value == "ipl"


def test_every_module_is_reachable():
    """Explore lists everything not hidden; hidden ones are covered by a test above or by the market / Player page."""
    at = new_app()
    at.sidebar.radio(key="page").set_value("Explore").run()
    listed = set()
    for cat in at.radio(key="category").options:
        at.radio(key="category").set_value(cat.lower()).run()
        listed |= set(at.selectbox(key="module").options)  # option labels are the short titles
    short = {m.id: m.title.split(" (")[0] for m in registry.all_modules()}
    shown = {i for i, t in short.items() if t in listed}
    hidden = module_view.HIDDEN_FROM_EXPLORE
    assert shown | hidden == set(short) and not (shown & hidden)
    assert module_view.ON_MARKET_PAGE == set(MARKET_TAB) | {"auction", "scarcity"}


def test_ipl_market_tabs():
    at = new_app()
    at.sidebar.radio(key="page").set_value("IPL market").run()
    assert at.radio(key="market_tab").options == ["Trade", "XI win odds", "Squads", "Auction"]
    at.radio(key="market_tab").set_value("Squads").run()
    at = go(at, "trade_squad")
    assert_clean(at, "squads")
    at.radio(key="market_tab").set_value("Auction").run()
    for g in ("ar_needs", "ar_scarce", "ar_est", "ar_scout", "ar_market"):
        at = go(at, g)
    assert_clean(at, "auction")


def test_player_style_without_commentary(monkeypatch):
    """No commentary files (another machine): the Style section says so and nothing breaks."""
    from cricket_analytics.models import player_card as PC

    monkeypatch.setattr(PC, "_style_frame", lambda: None)
    assert PC.style("JJ Bumrah", 2023, None) == {"status": "unavailable"}
