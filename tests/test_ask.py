"""ask.py: everything except the live model, using the real DB and canned Ollama replies (live test skips without Ollama)."""


import pytest

from cricket_analytics import ask as A
from cricket_analytics import registry

from tests.conftest import requires_real_db
from tests.conftest import REAL_DB as DB
needs_db = requires_real_db


def canned(name, **args):
    return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}}


def fake(monkeypatch, resp):
    monkeypatch.setattr(A, "_chat", lambda q, model, timeout=180: resp)


def test_tools_cover_every_module_and_stay_small():
    ts = A.tools()
    assert {t["function"]["name"] for t in ts} == {m.id for m in registry.all_modules()}
    comp = next(t for t in ts if t["function"]["name"] == "batting")["function"]["parameters"]["properties"]
    assert "t20i_women" in comp["competition"]["enum"] and "venue" not in comp
    assert len(str(ts)) < 30_000   # a small model has to read all of it on every question


@needs_db
def test_kohli_strike_rate_2024(monkeypatch):
    fake(monkeypatch, canned("batting", player="Kohli", competition="ipl", season="2024"))
    out = A.ask("Kohli's IPL strike rate in 2024", db_path=DB)
    assert out["status"] == "ok" and out["resolved_params"] == {"player": "V Kohli", "competition": "ipl", "season": 2024}
    row = out["result"]["rows"][0]
    assert row["total_runs"] == 741
    assert "741" in out["answer"] and str(row["strike_rate"]).rstrip("0") in out["answer"]
    assert out["timings"]["total_s"] >= 0


@needs_db
def test_full_name_and_team_alias(monkeypatch):
    fake(monkeypatch, canned("home_away", team="CSK", competition="ipl"))
    out = A.ask("CSK home vs away", db_path=DB)
    assert out["resolved_params"]["team"] == "Chennai Super Kings" and len(out["result"]["rows"]) == 3
    assert A.pick_player("Virat Kohli", "ipl")[0] == "V Kohli"
    assert A.pick_player("Rohit Sharma", "ipl")[0] == "RG Sharma"


@needs_db
def test_ambiguous_player_asks_instead_of_guessing(monkeypatch):
    fake(monkeypatch, canned("batting", player="Sharma", competition="ipl"))
    out = A.ask("Sharma's runs", db_path=DB)
    assert out["status"] == "clarify" and out["result"] is None
    assert out["clarify"][0]["param"] == "player" and len(out["clarify"][0]["candidates"]) >= 2
    # the user picks one: re-run without the model
    out2 = A.execute("Sharma's runs", out["tool_call"], picks={"player": out["clarify"][0]["candidates"][0]}, db_path=DB)
    assert out2["status"] == "ok" and out2["result"]["rows"]


@needs_db
def test_junk_params_are_dropped_and_noted(monkeypatch):
    fake(monkeypatch, canned("batting", player="Buttler", competition="IPL!", season="last year", colour="red", phase=""))
    out = A.ask("Buttler", db_path=DB)
    assert out["status"] == "ok" and out["resolved_params"] == {"player": "JC Buttler"}
    assert len(out["notes"]) == 3


@needs_db
def test_missing_required_param_is_a_plain_error(monkeypatch):
    fake(monkeypatch, canned("form"))
    out = A.ask("form?", db_path=DB)
    assert out["status"] == "error" and "player" in out["answer"]


def test_no_tool_and_unknown_tool(monkeypatch):
    fake(monkeypatch, {"message": {"content": "Cricket is a sport."}})
    assert A.ask("what is cricket?")["status"] == "no_tool"
    fake(monkeypatch, canned("drop_tables"))
    assert A.ask("x")["status"] == "no_tool"


def test_ollama_down_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(A, "OLLAMA_URL", "http://127.0.0.1:9")
    with pytest.raises(A.AskError, match="ollama serve"):
        A.ask("hi")


@pytest.mark.skipif(not A.ollama_up(), reason="Ollama not running")
@needs_db
def test_live_model_kohli():
    out = A.ask("Kohli's IPL strike rate in 2024", db_path=DB)
    assert out["tool_call"]["name"] == "batting" and out["resolved_params"].get("player") == "V Kohli"


def test_innings_list_wording_rules():
    qf = A.question_filters
    assert qf("naman dhir last 5 matches") == {"order": "last", "n": 5}
    assert qf("his last match") == {"order": "last", "n": 1}
    assert qf("naman dhir debut match score ipl") == {"order": "first", "n": 1}
    assert qf("first three innings") == {"order": "first", "n": 3}
    assert qf("best innings of kohli") == {"order": "best"} and qf("best bowling figures")["role"] == "bowling"
    assert qf("last 3 seasons") == {"last_n_years": 3}   # seasons stay a season filter
    assert "n" in A._KEEP_INTS


@needs_db
def test_last_matches_drops_models_last_n_years(monkeypatch):
    fake(monkeypatch, canned("innings_list", player="Naman Dhir", last_n_years=5))
    out = A.ask("naman dhir last 5 matches", db_path=DB)
    assert out["resolved_params"]["order"] == "last" and out["resolved_params"]["n"] == 5
    assert "last_n_years" not in out["resolved_params"]
