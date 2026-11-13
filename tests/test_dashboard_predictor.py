"""Match predictor page (AppTest): loads, nothing computes before Run, Run produces output. Skipped without the local ML files."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cricket_analytics.ml import predict as P
from cricket_analytics.ml.dataset import OUT_DIR
from tests.conftest import requires_real_db

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
pytestmark = [requires_real_db, pytest.mark.skipif(not (P.V2_DIR / "final_score_q50.txt").exists() or not (OUT_DIR / "balls.parquet").exists(), reason="ML files not built")]


def open_page() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=180).run()
    return at.sidebar.radio(key="page").set_value("Match predictor").run()


def test_loads_and_waits_for_run():
    at = open_page()
    assert not at.exception and not at.error
    assert at.title[0].value == "Match predictor" and len(at.tabs) == 3
    assert not at.metric and not at.dataframe


def test_live_run_and_chase():
    at = open_page()
    at.button(key="run_mp_live").click().run()
    assert not at.exception and not at.error, [e.value for e in at.exception + at.error]
    assert len(at.metric) == 3 and len(at.dataframe) == 1  # score, two win probabilities, breakdown table
    at.radio(key="mp_innings").set_value(2).run()
    at.number_input(key="mp_target").set_value(209).run()
    at.button(key="run_mp_live").click().run()
    assert not at.exception and not at.error
    assert "chasing 209" in " ".join(c.value for c in at.caption)


def test_replay_run():
    at = open_page()
    at.selectbox(key="mp_rseason").set_value(2024).run()
    at.selectbox(key="mp_rmatch").set_value("1426280").run()
    at.button(key="run_mp_replay").click().run()
    assert not at.exception and not at.error, [e.value for e in at.exception + at.error]
    assert any("Punjab Kings 262" in m.value for m in at.markdown)
