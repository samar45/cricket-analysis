"""Ask the data in plain English, with a LOCAL Ollama model.

    from cricket_analytics.ask import ask
    out = ask("Kohli's IPL strike rate in 2024")   # dict, see ask()

The model only picks ONE module and fills its params (tool calling). It never writes SQL and never supplies
numbers: names are resolved to exact data names in Python (ambiguous -> candidates, no guess), the module runs
through api.run, and the answer sentence is built from the result rows.
"""

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

from . import api, applog, competitions, registry
from .db import use_db

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "nemotron-3.5-bolt:e4b-q4_K_M"
_KEEP_KINDS = {"player", "player2", "team", "opposition", "competition", "phase", "choice"}
_KEEP_INTS = {"last_n_years", "season_from", "season_to", "top", "min_balls", "n"}
_KEEP_FALLBACK_NAMES = {"season"}   # the one multi/season param, flattened to a plain string for the model
_ABBREV = {"csk": "Chennai Super Kings", "mi": "Mumbai Indians", "rcb": "Royal Challengers Bengaluru",
           "kkr": "Kolkata Knight Riders", "srh": "Sunrisers Hyderabad", "dc": "Delhi Capitals",
           "pbks": "Punjab Kings", "kxip": "Punjab Kings", "rr": "Rajasthan Royals",
           "lsg": "Lucknow Super Giants", "gt": "Gujarat Titans"}
_PLAYER_ALIAS = {"sky": "SA Yadav", "suryakumar": "SA Yadav", "suryakumar yadav": "SA Yadav", "rohit": "RG Sharma",
                 "rohit sharma": "RG Sharma", "hardik": "HH Pandya", "hardik pandya": "HH Pandya", "kohli": "V Kohli",
                 "virat": "V Kohli", "virat kohli": "V Kohli", "bumrah": "JJ Bumrah", "jasprit bumrah": "JJ Bumrah",
                 "msd": "MS Dhoni", "dhoni": "MS Dhoni", "ms dhoni": "MS Dhoni", "abd": "AB de Villiers",
                 "de villiers": "AB de Villiers", "jadeja": "RA Jadeja", "ravindra jadeja": "RA Jadeja"}
SYSTEM = (
    "You answer cricket data questions by calling exactly one tool. Pick the tool whose description fits best. "
    "Copy player and team names as the user wrote them. Fill only what the user said; leave everything else out. "
    "competition: ipl = IPL, t20i = men's T20 internationals, t20i_women = women's T20 internationals; "
    "leave it out for all leagues. A single year like 2024 goes in season; 'last 3 seasons' means last_n_years=3. "
    "'best/top/most' questions are lists: do not give a player. 'X vs Y' or 'X against Y' for a batter and a bowler "
    "is matchup (player = batter, player2 = bowler); compare is only for 'compare X and Y'. If no tool fits, answer in words without a tool call.")


class AskError(RuntimeError):
    """Ollama unreachable or the model gave nothing usable."""


# ---------------------------------------------------------------- tools
def _short(text: str, n: int = 120) -> str:
    first = re.split(r"(?<=[.!?])\s", text.strip())[0]
    return first if len(first) <= n else first[: n - 1].rstrip(" ,;") + "…"


def tools() -> list[dict]:
    """Trimmed Ollama tool definitions, one per module (the full schemas stay in api.schema())."""
    out = []
    for m in registry.all_modules():
        props = {}
        for p in m.params:
            if p.kind in _KEEP_KINDS or p.name in _KEEP_INTS or p.name in _KEEP_FALLBACK_NAMES:
                full = registry.json_schema(m.id)["properties"][p.name]
                t = full["items"] if full.get("type") == "array" else full
                prop = {"type": "integer" if p.name in _KEEP_INTS else "string"}
                if "enum" in t:
                    prop["enum"] = t["enum"]
                if p.kind in ("player", "player2"):
                    prop["description"] = "player name" if p.kind == "player" else "second player (the bowler in a duel)"
                elif p.name == "season":
                    prop["description"] = "year, e.g. 2024"
                props[p.name] = prop
        out.append({"type": "function", "function": {
            "name": m.id, "description": f"{m.title}. {_short(m.description)}",
            "parameters": {"type": "object", "properties": props,
                           "required": [p.name for p in m.params if p.required and p.name in props]}}})
    return out


def _chat(question: str, model: str, timeout: int = 180) -> dict:
    body = {"model": model, "stream": False, "think": False, "keep_alive": "10m",
            "options": {"temperature": 0, "num_ctx": 6144},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
            "tools": tools()}
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise AskError(f"Could not reach Ollama at {OLLAMA_URL} ({type(e).__name__}). "
                       "Start it with `ollama serve` and check `ollama list`.") from e
    return r.json()


def ollama_up() -> bool:
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).ok
    except requests.RequestException:
        return False


_TEXT_CALL = re.compile(r"(\w+)\s*[{(](.*?)[})]\s*(?:<\|?tool_call\|?>)?\s*$", re.S)
_TEXT_ARG = re.compile(r'(\w+)\s*[:=]\s*(?:<\|"\|>(.*?)<\|"\|>|"([^"]*)"|\'([^\']*)\'|([^,})]+))')


def _text_call(text: str) -> dict | None:
    """The model sometimes prints its call as text (`name{k:<|"|>v<|"|>}<tool_call|>` or `name(k="v")`) and Ollama does not parse it."""
    m = _TEXT_CALL.search(text.strip())
    if not m or m.group(1) not in {x.id for x in registry.all_modules()}:
        return None
    return {"name": m.group(1), "arguments": {k: (a or b or c or d).strip() for k, a, b, c, d in _TEXT_ARG.findall(m.group(2))}}


def _tool_call(resp: dict) -> dict | None:
    calls = (resp.get("message") or {}).get("tool_calls") or []
    if not calls:
        return _text_call((resp.get("message") or {}).get("content") or "")
    fn = calls[0]["function"]
    args = fn.get("arguments") or {}
    if isinstance(args, str):
        import json
        args = json.loads(args)
    return {"name": fn["name"], "arguments": dict(args)}


# ---------------------------------------------------------------- name resolution
def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z]+", s.lower())


def pick_player(name: str, competition: str | None) -> tuple[str | None, list[dict]]:
    """(exact data name, []) when sure; (None, candidates) when ambiguous or unknown.

    Data names are initials + surname ('V Kohli'), so 'Virat Kohli' and 'kohli' both mean: same surname, matching
    first initial. Several such players: take the busiest if he has 3x the matches of the next, else ask.
    """
    alias = _PLAYER_ALIAS.get(name.strip().lower())
    if alias and api.resolve_player(alias, competition, limit=1)[0]["score"] >= 0.99:
        return alias, []
    cands = api.resolve_player(name, competition, limit=5)
    if cands and cands[0]["score"] >= 0.99:
        return cands[0]["name"], []
    q = _tokens(name)
    if q:
        pool = api.resolve_player(q[-1], competition, limit=15)
        hits = [c for c in pool if _tokens(c["name"])[-1:] == q[-1:]
                and (len(q) == 1 or _tokens(c["name"])[0][0] == q[0][0])]
        hits.sort(key=lambda c: -c["matches"])
        if len(hits) == 1 or (len(hits) > 1 and hits[0]["matches"] >= 3 * hits[1]["matches"]):
            return hits[0]["name"], []
        if hits:
            return None, hits
    if len(cands) == 1 or (cands and cands[0]["score"] >= 0.85 and cands[0]["score"] - cands[1]["score"] >= 0.05):
        return cands[0]["name"], []
    return None, cands


def pick_team(name: str, competition: str | None) -> tuple[str | None, list[dict]]:
    name = _ABBREV.get(name.strip().lower(), name)
    cands = api.resolve_team(name, competition, limit=4)
    if cands and cands[0]["score"] >= 0.8 and (len(cands) < 2 or cands[0]["score"] - cands[1]["score"] >= 0.08):
        return cands[0]["name"], []
    return None, cands


def _season(v):
    """'2024' -> 2024; '2023/24' stays; junk -> None (dropped, and noted)."""
    if isinstance(v, (list, tuple)):
        vals = [_season(x) for x in v]
        return [x for x in vals if x is not None] or None
    s = str(v).strip()
    if re.fullmatch(r"\d{4}", s):
        return int(s)
    return s if re.fullmatch(r"\d{4}/\d{2}", s) else None


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def question_filters(q: str) -> dict:
    """Season and phase words in the question itself, read by regex: the model's numbers are not trusted."""
    q, f = q.lower(), {}
    if m := re.search(r"\blast\s+(\d+|" + "|".join(_NUM) + r")\s+(?:years?|seasons?|editions?)", q):
        f["last_n_years"] = int(m[1]) if m[1].isdigit() else _NUM[m[1]]
    elif m := re.search(r"\bsince\s+(?:the\s+)?(\d{4})", q):
        f["season_from"] = int(m[1])
    elif m := re.search(r"\b(?:between|from)\s+(\d{4})\s+(?:and|to|-)\s+(\d{4})", q):
        f["season_from"], f["season_to"] = int(m[1]), int(m[2])
    elif m := re.findall(r"\b((?:19|20)\d{2})\b", q):
        f["season"] = int(m[0]) if len(m) == 1 else [int(x) for x in m]
    # innings_list wording ("matches/innings/games" is NOT a season count: only years/seasons set last_n_years)
    if m := re.search(r"\b(first|last)\s+(?:(\d+|" + "|".join(_NUM) + r")\s+)?(?:matches|match|innings|games?)\b", q):
        f["order"], f["n"] = m[1], (int(m[2]) if m[2] and m[2].isdigit() else _NUM.get(m[2], 1))
    elif re.search(r"\bdebut\b", q):
        f["order"], f["n"] = "first", 1
    elif re.search(r"\b(?:best|top)\s+(?:innings|figures|bowling)|highest score|top score", q):
        f["order"] = "best"
        if re.search(r"figures|bowling", q):
            f["role"] = "bowling"
    for word, ph in (("powerplay", "powerplay"), ("power play", "powerplay"), ("death", "death"), ("middle overs", "middle")):
        if word in q:
            f["phase"] = ph
    return f


def resolve(tool: dict, picks: dict | None = None, question: str = "") -> tuple[dict, list[dict], list[str]]:
    """Model arguments -> (params for api.run, clarifications, notes). `picks` = {param: exact name} chosen by the user."""
    mod = registry.get(tool["name"])
    allowed = {p.name for p in mod.params}
    a = {k: v for k, v in tool["arguments"].items() if v not in (None, "", [], "null", "None")}
    notes = [f"ignored {k}={v!r} (not a parameter of {mod.id})" for k, v in a.items() if k not in allowed]
    a = {k: v for k, v in a.items() if k in allowed}
    if "competition" in a and a["competition"] not in competitions.COMPETITIONS:
        notes.append(f"ignored unknown competition {a.pop('competition')!r}")
    if "phase" in a and a["phase"] not in ("powerplay", "middle", "death"):
        notes.append(f"ignored unknown phase {a.pop('phase')!r}")
    if "season" in a:
        s = _season(a.pop("season"))
        if s is None:
            notes.append("ignored a season that was not a year")
        else:
            a["season"] = s
    qf = question_filters(question)
    if "order" in qf and "last_n_years" not in qf:
        a.pop("last_n_years", None)   # the model confuses "last 5 matches" with last 5 seasons
    if qf:
        if {"season", "season_from", "season_to", "last_n_years"} & qf.keys():
            for k in ("season", "season_from", "season_to", "last_n_years"):
                a.pop(k, None)
        a.update({k: v for k, v in qf.items() if k in allowed})
    asks, picks = [], dict(picks or {})
    comp = a.get("competition")
    for key in ("player", "player2", "team", "opposition"):
        if key not in a:
            continue
        if key in picks:
            a[key] = picks[key]
            continue
        vals = a[key] if isinstance(a[key], list) else [a[key]]
        done = []
        for v in vals:
            exact, cands = (pick_team if key in ("team", "opposition") else pick_player)(str(v), comp)
            if exact:
                done.append(exact)
            else:
                asks.append({"param": key, "said": str(v), "candidates": [c["name"] for c in cands]})
        a[key] = done if isinstance(a[key], list) else (done[0] if done else None)
    return {k: v for k, v in a.items() if v is not None}, asks, notes


# ---------------------------------------------------------------- answer text
def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}" if isinstance(v, int) else str(v)


def _row_text(row: pd.Series, n: int) -> str:
    return ", ".join(f"{str(k).replace('_', ' ')} {_fmt(v)}" for k, v in list(row.dropna().items())[:n])


def make_answer(r: api.Result) -> str:
    """One plain sentence or two from the rows. Every number is copied from the data, none comes from the model."""
    m, df = r.meta, r.data
    scope = ", ".join(f"{k}={v}" for k, v in m["params"].items()
                      if k in ("player", "player2", "team", "opposition", "competition", "season", "phase", "last_n_years", "season_from", "season_to"))
    head = f"{m['title']} ({scope or 'all data'}), data through {m['data_through']}."
    if df.empty:
        return head + " No rows for these filters."
    if len(df) == 1:
        return f"{head} {_row_text(df.iloc[0], 12)}."
    labs = [c for c in df.columns if df[c].dtype == object and not c.endswith("id")][:2] or [df.columns[0]]
    nums = [c for c in df.columns if c not in labs and pd.api.types.is_numeric_dtype(df[c]) and not c.endswith("id")][:4]
    top = "; ".join(" / ".join(str(row[c]) for c in labs) + ": " + ", ".join(f"{c.replace('_', ' ')} {_fmt(row[c])}" for c in nums if pd.notna(row[c]))
                    for _, row in df.head(5).iterrows())
    return f"{head} {len(df)} rows. Top 5: {top}."


# ---------------------------------------------------------------- the whole flow
def execute(question: str, tool: dict, picks: dict | None = None, db_path: Path | None = None, timings: dict | None = None) -> dict:
    """Steps after the model: resolve names, run the module, build the answer. Also used to re-run after the user picks a candidate."""
    timings = dict(timings or {})
    out = {"question": question, "tool_call": tool, "resolved_params": None, "clarify": [], "notes": [],
           "result": None, "answer": None, "status": "ok", "timings": timings}
    t = time.perf_counter()
    try:
        with use_db(db_path):
            params, asks, out["notes"] = resolve(tool, picks, question)
        out["resolved_params"] = params
        if asks:
            out["clarify"], out["status"] = asks, "clarify"
            who = "; ".join(f"'{x['said']}' could be " + (" or ".join(x["candidates"][:4]) or "nobody I can find") for x in asks)
            out["answer"] = f"I need to know who/what you mean: {who}."
            return out
        r = api.run(tool["name"], db_path=db_path, **params)
        if r.data.empty and tool["name"] == "matchup" and {"player", "player2"} <= params.keys():
            params["player"], params["player2"] = params["player2"], params["player"]   # asked the wrong way round
            r2 = api.run("matchup", db_path=db_path, **params)
            if not r2.data.empty:
                r, out["resolved_params"] = r2, params
                out["notes"].append("batter and bowler were swapped: the first name had never faced the second as a batter")
        out["result"] = {"meta": r.meta, "rows": r.to_records()}
        out["answer"] = make_answer(r)
    except ValueError as e:   # bad params, missing required player...
        out["status"], out["answer"] = "error", f"I could not run that: {e}"
        out["error_id"] = getattr(e, "error_id", None) or applog.log_error("ask.execute", e, question=question, tool=tool)
    finally:
        timings["run_s"] = round(time.perf_counter() - t, 2)
        timings["total_s"] = round(sum(v for k, v in timings.items() if k != "total_s"), 2)
    return out


def ask(question: str, model: str = DEFAULT_MODEL, db_path: Path | None = None) -> dict:
    """question -> {id, question, tool_call, resolved_params, clarify, notes, result{meta, rows}, answer, status, timings}.

    status: ok | clarify (a name was ambiguous: see `clarify`) | no_tool (model found no module) | error.
    Raises AskError when Ollama cannot be reached. Every call is appended to logs/ask.jsonl (see applog).
    """
    ask_id, t = applog.new_id("A"), time.perf_counter()
    try:
        resp = _chat(question, model)
    except AskError as e:
        eid = applog.log_error("ask.chat", e, question=question, model=model)
        applog.log_ask({"id": ask_id, "question": question, "model": model, "status": "error", "error_id": eid, "answer": str(e)})
        e.error_id = eid
        raise
    timings = {"model_s": round(time.perf_counter() - t, 2)}
    tool = _tool_call(resp)
    raw = json.dumps((resp.get("message") or {}), default=str)
    if tool is None or tool["name"] not in {m.id for m in registry.all_modules()}:
        text = ((resp.get("message") or {}).get("content") or "").strip()
        out = {"question": question, "tool_call": tool, "resolved_params": None, "clarify": [], "notes": [],
               "result": None, "status": "no_tool", "timings": {**timings, "total_s": timings["model_s"]},
               "answer": "No analysis module fits this question." + (f" Model said: {text[:200]}" if text else "")}
        out["error_id"] = applog.log_note("ask.no_tool", "model returned no usable tool", question=question, model=model, tool=tool)
    else:
        out = execute(question, tool, db_path=db_path, timings=timings)
    out["id"] = ask_id
    applog.log_ask({"id": ask_id, "question": question, "model": model, "raw": raw, "tool_call": out["tool_call"],
                    "resolved_params": out["resolved_params"], "status": out["status"], "clarify": out["clarify"],
                    "notes": out["notes"], "row_count": (out["result"] or {}).get("meta", {}).get("row_count"),
                    "answer": out["answer"], "timings": out["timings"], "error_id": out.get("error_id")})
    return out
