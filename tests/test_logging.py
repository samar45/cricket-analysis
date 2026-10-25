"""Error log, ask log, feedback, and the Ask-page chart regression."""

import json
import re
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner
from streamlit.testing.v1 import AppTest

from cricket_analytics import api, applog
from cricket_analytics import ask as A
from cricket_analytics.cli import cli
from tests.conftest import requires_real_db

APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
sys.path.insert(0, str(Path(APP).parent))   # the app does `import health`


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    monkeypatch.setenv("CRICKET_LOG_DIR", str(tmp_path))
    return tmp_path


def canned(name, **args):
    return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}}


def test_error_log_has_id_traceback_and_rotation(logdir):
    try:
        1 / 0
    except ZeroDivisionError as e:
        eid = applog.log_error("test", e, module="batting", params={"player": "x"})
    assert re.fullmatch(r"E-\d{8}-\d{4}-[0-9a-f]{4}", eid)
    text = (logdir / "errors.log").read_text(encoding="utf-8")
    assert eid in text and "ZeroDivisionError" in text and "Traceback" in text and "batting" in text
    h = applog._logger.handlers[0]
    assert (h.maxBytes, h.backupCount) == (1_000_000, 4)


def test_api_run_failure_is_logged_with_id(logdir):
    with pytest.raises(ValueError) as ei:
        api.run("batting", nonsense=1)
    assert ei.value.error_id in (logdir / "errors.log").read_text(encoding="utf-8")


def test_ask_line_schema_and_no_tool_error_id(logdir, monkeypatch):
    monkeypatch.setattr(A, "_chat", lambda q, m, timeout=180: {"message": {"content": "x" * 5000}})
    out = A.ask("what is cricket?")
    line = json.loads((logdir / "ask.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert {"type", "ts", "id", "question", "model", "raw", "tool_call", "resolved_params", "status", "clarify", "notes",
            "row_count", "answer", "timings", "error_id"} <= line.keys()
    assert line["id"] == out["id"] and line["status"] == "no_tool" and len(line["raw"]) < 2100
    assert line["error_id"] in (logdir / "errors.log").read_text(encoding="utf-8")


def test_ollama_down_is_logged(logdir, monkeypatch):
    def boom(q, m, timeout=180):
        raise A.AskError("no ollama")
    monkeypatch.setattr(A, "_chat", boom)
    with pytest.raises(A.AskError) as ei:
        A.ask("hi")
    assert ei.value.error_id in (logdir / "errors.log").read_text(encoding="utf-8")


def test_feedback_merge_and_eval_export(logdir, monkeypatch):
    monkeypatch.setattr(A, "_chat", lambda q, m, timeout=180: canned("teams"))
    monkeypatch.setattr(A, "execute", lambda q, t, **k: {"question": q, "tool_call": t, "resolved_params": {"a": 1}, "clarify": [],
                        "notes": [], "result": None, "answer": "ans", "status": "ok", "timings": {}})
    out = A.ask("best team?")
    applog.log_feedback(out["id"], "down", "wrong module", "venues")
    fb = json.loads((logdir / "ask.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert fb == {**fb, "type": "feedback", "ask_id": out["id"], "rating": "down", "comment": "wrong module", "expected_module": "venues"}
    assert applog.read_asks(bad_only=True)[0]["expected_module"] == "venues"
    r = CliRunner()
    assert "best team?" in r.invoke(cli, ["ask-log", "--bad"]).output
    f = logdir / "draft.jsonl"
    assert "Wrote 1" in r.invoke(cli, ["ask-log", "--to-eval", str(f)]).output
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d["question"] == "best team?" and d["expected_module"] == "venues" and d["expected_params"] == {"a": 1}


def test_cli_failure_is_logged(logdir, monkeypatch):
    import cricket_analytics.api as capi
    monkeypatch.setattr(capi, "list_modules", lambda: 1 / 0)
    res = CliRunner().invoke(cli, ["modules"])
    eid = re.search(r"error id (E-[\w-]+)", res.output).group(1)
    assert res.exit_code != 0 and eid in (logdir / "errors.log").read_text(encoding="utf-8")


def _ask_app(monkeypatch_target=None):
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.radio(key="page").set_value("Ask").run()
    return at


def test_guarded_error_id_in_ui_and_log(logdir, monkeypatch):
    monkeypatch.setattr(A, "ollama_up", lambda: True)
    monkeypatch.setattr(applog, "read_asks", lambda *a, **k: 1 / 0)   # the Ask page blows up
    at = _ask_app()
    eid = re.search(r"error id (E-[\w-]+)", at.error[0].value).group(1)
    assert eid in (logdir / "errors.log").read_text(encoding="utf-8") and "dashboard:ask_page" in (logdir / "errors.log").read_text(encoding="utf-8")


@requires_real_db
def test_ask_page_renders_chart_and_table_and_feedback(logdir, monkeypatch):
    """Regression: 'naman dhir total runs in ipl' showed 'This filter combination couldn't be run' in the Chart tab
    (a one-line `st.plotly_chart(...) if fig else st.caption(...)` statement made Streamlit try to print its value)."""
    monkeypatch.setattr(A, "_chat", lambda q, m, timeout=180: canned("batting", player="Naman Dhir", competition="ipl"))
    monkeypatch.setattr(A, "ollama_up", lambda: True)
    at = _ask_app()
    at.text_input(key="ask_q").set_value("naman dhir total runs in ipl").run()
    at.button[0].click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert len(at.tabs) == 2 and len(at.dataframe) >= 2   # result table + ask log table
    at.button(key=[b.key for b in at.button if b.key and b.key.startswith("fb_up_")][0]).click().run()
    assert applog.read_asks()[-1]["rating"] == "up"
