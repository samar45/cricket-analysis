"""State leagues page goals (AppTest). Frozen: do not edit to make them pass."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cricket_analytics.scouting import profile as P
from tests.conftest import requires_real_db

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
pytestmark = [requires_real_db, pytest.mark.skipif(not P.available(), reason="Cricbuzz scouting data not present")]


def open_page() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=300).run()
    return at.sidebar.radio(key="page").set_value("State leagues").run()


def search(name: str) -> AppTest:
    at = open_page()
    at.text_input(key="sl_player").set_value(name).run()
    return at


def test_page_loads_and_board_has_rows():
    at = open_page()
    assert not at.exception and not at.error, [e.value for e in at.exception + at.error]
    assert len(at.dataframe[0].value) > 50


def test_default_board_is_uncapped_only():
    df = open_page().dataframe[0].value
    assert set(df["ipl_capped"]) == {"no"}
    assert "ipl_link" in df.columns


def test_player_naman_dhir_sher_e_punjab_2026():
    at = search("Naman Dhir")
    assert not at.exception and not at.error, [e.value for e in at.exception + at.error]
    df = at.dataframe[1].value
    row = df[(df["competition"] == "Sher-e-Punjab T20 League") & (df["season"] == "2026")]
    assert len(row) == 1 and int(row.iloc[0]["runs"]) == 655


def test_sahaj_dhawan_has_no_ipl_rows_by_default():
    at = search("Sahaj Dhawan")
    assert not at.exception and not at.error, [e.value for e in at.exception + at.error]
    df = at.dataframe[1].value
    assert len(df) > 0 and "IPL" not in set(df["competition"])
