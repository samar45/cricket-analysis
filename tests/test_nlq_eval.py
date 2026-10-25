"""The NLQ eval set is valid (params exist, golden numbers reproduce) and the scorer works."""
import importlib.util
from pathlib import Path

import pytest

from tests.conftest import requires_real_db

from cricket_analytics import api, registry
from cricket_analytics.db import current_db_path

EVALS = Path(__file__).parent.parent / "evals"
spec = importlib.util.spec_from_file_location("run_nlq_eval", EVALS / "run_nlq_eval.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
CASES = ev.load_questions()


def _specs(module):
    return {p.name: p for p in registry.get(module).params}


def _check_params(module, params):
    specs = _specs(module)
    assert set(params) <= set(specs), f"{module}: unknown {set(params) - set(specs)}"
    for k, v in params.items():
        api._coerce(specs[k], v)


def test_file_shape():
    assert len(CASES) == 50
    assert len({c["id"] for c in CASES}) == 50
    assert sum(c["expect_clarification"] for c in CASES) == 5
    assert all(c["question"] and c["expected_module"] is None for c in CASES if c["expect_clarification"])


def test_expected_modules_and_params_validate():
    for c in CASES:
        if c["expect_clarification"]:
            continue
        for m, p in [(c["expected_module"], c["expected_params"])] + [
                (a["module"], a.get("params", {})) for a in c.get("acceptable_alternatives", [])]:
            registry.get(m)
            _check_params(m, p)
        req = {p.name for p in registry.get(c["expected_module"]).params if p.required}
        assert req <= set(c["expected_params"]), f"{c['id']} missing required {req}"


@requires_real_db
def test_golden_numbers_reproduce():
    n = 0
    for c in CASES:
        g = c.get("golden")
        if not g:
            continue
        df = api.run(c["expected_module"], **c["expected_params"]).data
        for k, v in (g["where"] or {}).items():
            df = df[df[k] == v]
        assert float(df.iloc[0][g["column"]]) == pytest.approx(g["value"]), c["id"]
        n += 1
    assert n >= 20


def test_scorer_on_fake_outputs():
    by = {c["id"]: c for c in CASES}
    q1, q2, clar = by["q01"], by["q02"], by["q46"]
    good = {"status": "ok", "tool_call": {"name": "batting", "arguments": {"player": "Kohli", "competition": "ipl"}},
            "resolved_params": {"player": "V Kohli", "competition": "ipl"}, "answer": "Kohli has 9,336 IPL runs."}
    bad = {"status": "ok", "tool_call": {"name": "bowling", "arguments": {}}, "resolved_params": {"player": "RG Sharma"},
           "answer": "Sharma took 15."}
    ask_back = {"status": "clarify", "tool_call": {"name": "batting", "arguments": {"player": "Sharma"}}, "clarify": ["Which Sharma?"], "answer": ""}
    s = [ev.score_one(q1, good), ev.score_one(q2, bad), ev.score_one(clar, ask_back)]
    assert s[0]["module_ok"] and s[0]["params_ok"] and s[0]["golden_ok"]
    assert not s[1]["module_ok"] and not s[1]["params_ok"]
    assert s[2]["clar_pred"] and s[2]["clar_expected"]
    m = ev.summarize(s, [1.0, 3.0, 2.0])
    assert m["module_accuracy"] == 0.5 and m["param_accuracy_all_correct"] == 0.5
    assert m["clarification_precision"] == 1.0 and m["clarification_recall"] == 1.0
    assert m["seconds_max"] == 3.0 and m["golden_present"] == 0.5


def test_normalisation():
    assert ev._norm(["2024"]) == ev._norm(2024) == 2024.0
    assert ev._norm("IPL ") == "ipl"
    assert ev.golden_hit(7.32, "economy 7.2") is False and ev.golden_hit(7.32, "economy 7.32")
