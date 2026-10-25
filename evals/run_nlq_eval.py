"""Run the natural-language question set through cricket_analytics.ask.ask() and score it.

    .venv/Scripts/python evals/run_nlq_eval.py [--model M] [--limit N] [--ids q01,q02]

Scores (exact match in Python, no LLM judge): module accuracy, param accuracy (per param and all-correct),
clarification precision/recall, golden-number presence in the answer, seconds per question.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_MODEL = "nemotron-3.5-bolt:e4b-q4_K_M"


def load_questions(path=HERE / "nlq_questions.jsonl"):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(v):
    """Make 2024 / "2024" / ["2024"] / "Ipl " comparable."""
    if isinstance(v, (list, tuple)):
        v = [_norm(x) for x in v]
        return v[0] if len(v) == 1 else sorted(map(str, v))
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"-?\d+(\.0+)?", v.strip())):
        return float(v)
    return str(v).strip().casefold()


def _call(out):
    tc = out.get("tool_call") or {}
    return tc.get("module") or tc.get("name"), tc.get("params") or tc.get("arguments") or {}


def predicted_clarification(out):
    # ask() status: ok | clarify (ambiguous name) | no_tool (model found no module: it declined) | error
    return out.get("status") in ("clarify", "no_tool") or bool(out.get("clarify"))


def numbers_in(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))]


def golden_hit(value, answer):
    tol = 0 if float(value).is_integer() else 0.05
    return any(abs(n - value) <= tol for n in numbers_in(answer))


def score_one(case, out):
    """One question -> dict of booleans/counts. `out` is what ask() returned (or {} on error)."""
    clar_pred, clar_exp = predicted_clarification(out), case["expect_clarification"]
    s = {"id": case["id"], "clar_pred": clar_pred, "clar_expected": clar_exp}
    if clar_exp:
        return s
    mod, tool_params = _call(out)
    params = out.get("resolved_params") or tool_params
    cands = [(case["expected_module"], case["expected_params"])] + [
        (a["module"], a.get("params", {})) for a in case.get("acceptable_alternatives", [])]
    match = next(((m, p) for m, p in cands if m == mod), None)
    s["module_ok"] = match is not None
    exp = (match or cands[0])[1]
    s["param_hits"] = {k: (k in params and _norm(params[k]) == _norm(v)) for k, v in exp.items()}
    s["params_ok"] = s["module_ok"] and all(s["param_hits"].values())
    if "golden" in case:
        s["golden_ok"] = golden_hit(case["golden"]["value"], out.get("answer", ""))
    return s


def summarize(scores, seconds):
    ex = [s for s in scores if not s["clar_expected"]]
    ph = [h for s in ex for h in s.get("param_hits", {}).values()]
    gold = [s["golden_ok"] for s in ex if "golden_ok" in s]
    tp = sum(s["clar_pred"] and s["clar_expected"] for s in scores)
    pred, exp = sum(s["clar_pred"] for s in scores), sum(s["clar_expected"] for s in scores)
    # a question that should NOT trigger a clarification but did counts as a miss for module accuracy
    r = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {
        "n": len(scores), "n_answerable": len(ex),
        "module_accuracy": r(sum(s["module_ok"] for s in ex), len(ex)),
        "param_accuracy_per_param": r(sum(ph), len(ph)),
        "param_accuracy_all_correct": r(sum(s["params_ok"] for s in ex), len(ex)),
        "clarification_precision": r(tp, pred), "clarification_recall": r(tp, exp),
        "false_clarifications": sum(s["clar_pred"] and not s["clar_expected"] for s in scores),
        "golden_present": r(sum(gold), len(gold)), "golden_n": len(gold),
        "seconds_mean": round(sum(seconds) / len(seconds), 2) if seconds else None,
        "seconds_max": round(max(seconds), 2) if seconds else None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", help="comma-separated question ids, e.g. q01,q07")
    a = ap.parse_args(argv)
    try:
        from cricket_analytics.ask import ask  # lazy: the module is built separately
    except ImportError as e:
        sys.exit(f"cricket_analytics.ask is not available yet ({e}). Build src/cricket_analytics/ask.py first.")
    cases = load_questions()
    if a.ids:
        want = set(a.ids.split(","))
        cases = [c for c in cases if c["id"] in want]
    cases = cases[: a.limit] if a.limit else cases
    scores, secs, rows = [], [], []
    for c in cases:
        t0 = time.perf_counter()
        try:
            out, err = ask(c["question"], model=a.model), None
        except Exception as e:  # keep going; an error is a miss
            out, err = {}, f"{type(e).__name__}: {e}"
        dt_s = time.perf_counter() - t0
        s = score_one(c, out)
        scores.append(s)
        secs.append(dt_s)
        rows.append({**s, "question": c["question"], "seconds": round(dt_s, 2), "error": err,
                     "tool_call": out.get("tool_call"), "resolved_params": out.get("resolved_params"),
                     "answer": out.get("answer"), "status": out.get("status")})
        flag = "ok " if (s.get("params_ok") or (s["clar_expected"] and s["clar_pred"])) else "BAD"
        print(f"{flag} {c['id']} {dt_s:5.1f}s  {c['question'][:60]}")
    summ = summarize(scores, secs)
    res = HERE / "results"
    res.mkdir(exist_ok=True)
    f = res / f"{dt.date.today()}_{re.sub(r'[^A-Za-z0-9._-]', '_', a.model)}.json"
    f.write_text(json.dumps({"model": a.model, "summary": summ, "questions": rows}, indent=1, default=str), encoding="utf-8")
    print("\n" + "\n".join(f"{k:30} {v}" for k, v in summ.items()) + f"\n\nwritten: {f}")


if __name__ == "__main__":
    main()
