"""Ask the data in plain English, with a LOCAL Ollama model.

    from cricket_analytics.ask import ask
    out = ask("Kohli's IPL strike rate in 2024")   # dict, see ask()

The model only picks ONE module and fills its params (tool calling). It never writes SQL and never supplies
numbers: names are resolved to exact data names in Python (ambiguous -> candidates, no guess), the module runs
through api.run, and the answer sentence is built from the result rows.
"""

import datetime as dt
import json
import re
import time
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import pandas as pd
import requests

from . import api, applog, ask_rules, competitions, registry
from .db import current_db_path, query, use_db

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "nemotron-3.5-bolt:e4b-q4_K_M"
_KEEP_KINDS = {"player", "player2", "team", "opposition", "competition", "phase", "choice", "venue"}
_KEEP_INTS = {
    "last_n_years",
    "season_from",
    "season_to",
    "top",
    "min_balls",
    "min_matches",
    "n",
    "window",
}
_KEEP_FALLBACK_NAMES = {
    "season"
}  # the one multi/season param, flattened to a plain string for the model
_ABBREV = {
    "csk": "Chennai Super Kings",
    "mi": "Mumbai Indians",
    "rcb": "Royal Challengers Bengaluru",
    "kkr": "Kolkata Knight Riders",
    "srh": "Sunrisers Hyderabad",
    "dc": "Delhi Capitals",
    "pbks": "Punjab Kings",
    "kxip": "Punjab Kings",
    "rr": "Rajasthan Royals",
    "lsg": "Lucknow Super Giants",
    "gt": "Gujarat Titans",
}
_PLAYER_ALIAS = {
    "sky": "SA Yadav",
    "suryakumar": "SA Yadav",
    "suryakumar yadav": "SA Yadav",
    "rohit": "RG Sharma",
    "rohit sharma": "RG Sharma",
    "hardik": "HH Pandya",
    "hardik pandya": "HH Pandya",
    "kohli": "V Kohli",
    "virat": "V Kohli",
    "virat kohli": "V Kohli",
    "bumrah": "JJ Bumrah",
    "jasprit bumrah": "JJ Bumrah",
    "msd": "MS Dhoni",
    "dhoni": "MS Dhoni",
    "ms dhoni": "MS Dhoni",
    "abd": "AB de Villiers",
    "de villiers": "AB de Villiers",
    "jadeja": "RA Jadeja",
    "ravindra jadeja": "RA Jadeja",
}
SYSTEM = (
    "You answer cricket data questions by calling exactly one tool. Pick the tool whose description fits best. "
    "Copy player and team names as the user wrote them. Fill only what the user said; leave everything else out. "
    "competition: ipl = IPL, t20i = men's T20 internationals, t20i_women = women's T20 internationals; "
    "leave it out for all leagues. A single year like 2024 goes in season; 'last 3 seasons' means last_n_years=3. "
    "'best/top/most' questions are lists: do not give a player. 'X vs Y' or 'X against Y' for a batter and a bowler "
    "is matchup (player = batter, player2 = bowler); compare is only for 'compare X and Y'. "
    "Wins above replacement / 'added the most wins' = war; runs above average = runs_added; win probability = wpa; "
    "'predict' or expected outcome per ball for a batter v bowler = matchup_predict; IPL auction prices = auction; "
    "player swaps = trade; catches, stumpings, run-outs = fielding. If no tool fits, answer in words without a tool call."
)


def system_prompt() -> str:
    """SYSTEM plus today's date and how far the data goes, so the model never says a recent season has not happened."""
    try:
        info = api.data_info()["competitions"]
        thr = "; ".join(f"{c['competition']} to {c['latest']}" for c in info)
    except Exception:  # no DB: the prompt still works
        thr = "unknown"
    return f"{SYSTEM} Today is {dt.date.today()}. The data runs through: {thr}. Seasons up to those dates have happened and are in the data."


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
                    prop["description"] = (
                        "player name"
                        if p.kind == "player"
                        else "second player (the bowler in a duel)"
                    )
                elif p.kind == "venue":
                    prop["description"] = "ground name as the user wrote it, e.g. Wankhede"
                elif p.name == "season":
                    prop["description"] = "year, e.g. 2024"
                props[p.name] = prop
        out.append(
            {
                "type": "function",
                "function": {
                    "name": m.id,
                    "description": f"{m.title}. {_short(m.description)}",
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": [p.name for p in m.params if p.required and p.name in props],
                    },
                },
            }
        )
    return out


def _chat(question: str, model: str, timeout: int = 180) -> dict:
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": 0, "num_ctx": 12288},
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": question},
        ],
        "tools": tools(),
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as e:
        raise AskError(
            f"Could not reach Ollama at {OLLAMA_URL} ({type(e).__name__}). "
            "Start it with `ollama serve` and check `ollama list`."
        ) from e
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
    return {
        "name": m.group(1),
        "arguments": {
            k: (a or b or c or d).strip() for k, a, b, c, d in _TEXT_ARG.findall(m.group(2))
        },
    }


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


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


@lru_cache(maxsize=16)
def _roster(db_key: tuple, competition: str | None) -> tuple:
    """((name, matches played), ...) for everyone who batted or bowled; cached per DB file version."""
    cond, p = "1=1", []
    if competition:
        c = competitions.get(competition)
        cond, p = "m.competition = ? AND m.gender = ?", [c.competition, c.gender]
    sql = (
        "SELECT name, count(DISTINCT match_id) AS n FROM ("
        f"SELECT d.match_id, d.batter AS name FROM deliveries d JOIN matches m USING (match_id) WHERE {cond} "
        f"UNION ALL SELECT d.match_id, d.bowler FROM deliveries d JOIN matches m USING (match_id) WHERE {cond}"
        ") GROUP BY name"
    )
    df = query(sql, p + p)
    return tuple((r.name, int(r.n)) for r in df.itertuples())


def _db_key() -> tuple:
    path = current_db_path()
    return str(path), path.stat().st_mtime


def pick_player(name: str, competition: str | None) -> tuple[str | None, list[dict]]:
    """(exact data name, []) when sure; (None, candidates) when ambiguous or unknown.

    Data names are initials + surname ('V Kohli'). Rule: the typed surname is compared to every data surname
    (spelling similarity, so 'kholi' and 'bumra' work) and, when a first name was typed, its initial must match.
    Among spellings equally close, take the player with 3x the matches of the next; otherwise ask.
    """
    key = name.strip().lower()
    roster = _roster(_db_key(), competition)
    have = {n for n, _ in roster}
    alias = _PLAYER_ALIAS.get(key)
    if not alias and len(key) >= 5:  # a typo of an alias ('kholi', 'bumra')
        close = [(_sim(key, k), v) for k, v in _PLAYER_ALIAS.items() if len(k) >= 5]
        best = max(close, default=(0, None))
        alias = best[1] if best[0] >= 0.8 else None
    if alias in have:
        return alias, []
    exact = [n for n in have if n.lower() == key]
    if exact:
        return exact[0], []
    q = _tokens(name)
    if q:
        scored = []
        for n, m in roster:
            t = _tokens(n)
            if not t or (len(q) > 1 and t[0][0] != q[0][0]):
                continue
            if (s := _sim(q[-1], t[-1])) >= 0.78:
                scored.append((s, m, n))
        if scored:
            top = max(s for s, _, _ in scored)
            pool = sorted((x for x in scored if x[0] >= top - 0.06), key=lambda x: -x[1])
            if len(pool) == 1 or pool[0][1] >= 3 * pool[1][1]:
                return pool[0][2], []
            return None, [{"name": n, "matches": m} for _, m, n in pool[:5]]
    cands = api.resolve_player(name, competition, limit=5)
    if len(cands) == 1 or (
        cands and cands[0]["score"] >= 0.85 and cands[0]["score"] - cands[1]["score"] >= 0.05
    ):
        return cands[0]["name"], []
    return None, cands


def pick_team(name: str, competition: str | None) -> tuple[str | None, list[dict]]:
    name = _ABBREV.get(name.strip().lower(), name)
    cands = api.resolve_team(name, competition, limit=4)
    if (
        cands
        and cands[0]["score"] >= 0.8
        and (len(cands) < 2 or cands[0]["score"] - cands[1]["score"] >= 0.08)
    ):
        return cands[0]["name"], []
    return None, cands


_GENERIC = {"stadium", "ground", "cricket", "international", "the", "at", "in", "oval", "of", "and"}
_VENUE_ALIAS = {  # old / common names -> a word in the data name
    "kotla": "jaitley",
    "motera": "narendra",
    "chepauk": "chidambaram",
    "bangalore": "chinnaswamy",
    "bengaluru": "chinnaswamy",
    "mohali": "bindra",
}


def _venue_groups(competition: str | None) -> dict[str, list[str]]:
    """Venue names grouped by the part before the comma ('X' and 'X, City' are the same ground)."""
    g: dict[str, list[str]] = {}
    for v in api.choices("venue", competition):
        g.setdefault(v.split(",")[0].strip().lower(), []).append(v)
    return g


def pick_venue(name: str, competition: str | None) -> tuple[str | list[str] | None, list[dict]]:
    """Data venue name(s) for a loose ground name ('wankhede', 'chinnaswamy'): every spelling of the one ground.

    All typed words (minus 'stadium' etc.) must match a word of the data name, allowing typos. Several different
    grounds -> the one with 3x the matches, else ask.
    """
    q = [_VENUE_ALIAS.get(t, t) for t in _tokens(name) if t not in _GENERIC]
    if not q:
        return None, []
    hits = {
        k: vs
        for k, vs in _venue_groups(competition).items()
        if all(any(_sim(w, t) >= 0.85 for t in _tokens(k)) for w in q)
    }
    if not hits:
        return None, []
    if len(hits) > 1:
        c = ",".join("?" * len(hits))
        df = query(
            f"SELECT venue, count(*) AS n FROM matches WHERE lower(split_part(venue, ',', 1)) IN ({c}) GROUP BY venue",
            list(hits),
        )
        n = {k: 0 for k in hits}
        for r in df.itertuples():
            n[r.venue.split(",")[0].strip().lower()] += int(r.n)
        order = sorted(hits, key=lambda k: -n[k])
        if n[order[0]] < 3 * n[order[1]]:
            return None, [{"name": hits[k][0], "matches": n[k]} for k in order[:4]]
        hits = {order[0]: hits[order[0]]}
    vs = next(iter(hits.values()))
    return (vs[0] if len(vs) == 1 else vs), []


def venue_in_question(question: str, competition: str | None) -> str | None:
    """A ground named in the question that the model left out: a word (6+ letters) found in only one or two venue
    names and not part of any team name ('Wankhede', 'Chinnaswamy'), or a known old name ('Chepauk')."""
    teams = {t for x in api.choices("team", competition) for t in _tokens(x)}
    qt = _tokens(question)
    words = {w for w in qt if len(w) >= 6 and w not in teams and w not in _GENERIC}
    words |= {w for w in qt if w in _VENUE_ALIAS}
    groups = _venue_groups(competition)
    for w in sorted(words):
        t = _VENUE_ALIAS.get(w, w)
        if sum(t in _tokens(k) for k in groups) in (1, 2):
            return t
    return None


def _season(v):
    """'2024' -> 2024; '2023/24' stays; junk -> None (dropped, and noted)."""
    if isinstance(v, (list, tuple)):
        vals = [_season(x) for x in v]
        return [x for x in vals if x is not None] or None
    s = str(v).strip()
    if re.fullmatch(r"\d{4}", s):
        return int(s)
    return s if re.fullmatch(r"\d{4}/\d{2}", s) else None


_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


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
    if m := re.search(
        r"\b(first|last)\s+(?:(\d+|"
        + "|".join(_NUM)
        + r")\s+)?(?:(?!seasons?\b|years?\b)[a-z0-9]+\s+)?(?:matches|match|innings|games?)\b",
        q,
    ):
        f["order"], f["n"] = m[1], (int(m[2]) if m[2] and m[2].isdigit() else _NUM.get(m[2], 1))
    elif re.search(r"\bdebut\b", q):
        f["order"], f["n"] = "first", 1
    elif m := re.search(
        r"\b(?:best|top)\s+(?:(\d+|"
        + "|".join(_NUM)
        + r")\s+)?(?:innings|figures|bowling)|highest score|top score",
        q,
    ):
        f["order"] = "best"
        f["n"] = (
            int(m[1]) if m[1] and m[1].isdigit() else _NUM.get(m[1], 1)
        )  # "best figures" = the one best
        if re.search(r"figures|bowling", q):
            f["role"] = "bowling"
    if m := re.search(
        r"\b(\d+)\s*\+\s*(?:matches|games)|\b(?:at least|min(?:imum)?)\s+(\d+)\s+(?:matches|games)",
        q,
    ):
        f["min_matches"] = int(m[1] or m[2])
    for word, ph in (
        ("powerplay", "powerplay"),
        ("power play", "powerplay"),
        ("death", "death"),
        ("middle overs", "middle"),
    ):
        if word in q:
            f["phase"] = ph
    return f


def _only_competition(team: str) -> str | None:
    """The competition key when this team appears in exactly one (competition, gender) of the data, else None."""
    df = query(
        "SELECT DISTINCT competition, gender FROM matches WHERE team1 = ? OR team2 = ?",
        [team, team],
    )
    keys = {(c.competition, c.gender): k for k, c in competitions.COMPETITIONS.items()}
    found = {keys.get((r.competition, r.gender)) for r in df.itertuples()}
    return found.pop() if len(found) == 1 and None not in found else None


_PLAYER_FILL = {
    "matchup_predict",
    "auction",
}  # modules where a missing player is the model slipping, not intent
_SEASON_KEYS = ("season", "season_from", "season_to", "last_n_years")


def resolve(
    tool: dict, picks: dict | None = None, question: str = ""
) -> tuple[dict, list[dict], list[str]]:
    """Model arguments -> (params for api.run, clarifications, notes). `picks` = {param: exact name} chosen by the user.

    Rules applied here, not by the model: the competition comes from the words (IPL, T20I, women's...), seasons from
    the question's own numbers, choices must be in the allowed list.
    """
    mod = registry.get(tool["name"])
    allowed = {p.name for p in mod.params}
    a = {k: v for k, v in tool["arguments"].items() if v not in (None, "", [], "null", "None")}
    notes = [
        f"ignored {k}={v!r} (not a parameter of {mod.id})" for k, v in a.items() if k not in allowed
    ]
    a = {k: v for k, v in a.items() if k in allowed}
    if "competition" in a and a["competition"] not in competitions.COMPETITIONS:
        notes.append(f"ignored unknown competition {a.pop('competition')!r}")
    if "phase" in a and a["phase"] not in ("powerplay", "middle", "death"):
        notes.append(f"ignored unknown phase {a.pop('phase')!r}")
    for (
        p
    ) in mod.params:  # a choice outside its list ('batter' for a batting/bowling choice) is dropped
        if p.choices and p.name in a and str(a[p.name]) not in p.choices:
            notes.append(f"ignored {p.name}={a.pop(p.name)!r} (not one of {', '.join(p.choices)})")
    if question and "competition" in allowed:
        named = ask_rules.competition_in(question)
        if named:
            a["competition"] = named
        elif "competition" in a:
            notes.append(
                f"dropped competition {a.pop('competition')!r}: the question does not name one"
            )
    if "season" in a:
        s = _season(a.pop("season"))
        if s is None:
            notes.append("ignored a season that was not a year")
        else:
            a["season"] = s
    qf = question_filters(question)
    if "order" in qf and "last_n_years" not in qf:
        a.pop("last_n_years", None)  # the model confuses "last 5 matches" with last 5 seasons
    if {"season", "season_from", "season_to", "last_n_years"} & qf.keys():
        for k in _SEASON_KEYS:
            a.pop(k, None)
    else:  # the model cannot know the year: its season numbers are dropped unless the question has them
        for k in _SEASON_KEYS:
            if k in a:
                notes.append(f"dropped {k}={a.pop(k)!r}: the question gives no such season")
        if m := re.search(r"\b(this|current|latest|last|previous)\s+season\b", question.lower()):
            seasons = api.choices("season", a.get("competition"))
            i = 0 if m[1] in ("this", "current", "latest") else 1
            if len(seasons) > i and "season" in allowed:
                a["season"] = seasons[i]
                notes.append(f"'{m[1]} season' read as {seasons[i]} (newest season in the data)")
    a.update({k: v for k, v in qf.items() if k in allowed})
    if "window" in allowed and "n" in qf:
        a["window"] = qf["n"]
    if mod.id == "pace_vs_spin" and "mode" not in a and "player" not in a:
        if re.search(r"\bteams?\b|\bsides?\b", question.lower()):
            a["mode"] = "team_vs_type"
    if mod.id == "dismissal_profile" and (g := ask_rules.dismissal_group(question)):
        a["group_by"] = g
    for m_id, fn in (
        ("war", ask_rules.war_view),
        ("trade", ask_rules.trade_view),
        ("scarcity", ask_rules.scarcity_view),
    ):
        if mod.id == m_id and "view" in allowed and (v := fn(question)):
            a["view"] = v
    if "player" in allowed and "player" not in a and mod.id in _PLAYER_FILL:
        if who := ask_rules.player_in_question(question, _PLAYER_ALIAS):
            a["player"] = who
    if (
        mod.id == "war" and a.get("view") == "projected"
    ):  # the fixed IPL 2027 table takes no season/competition filter
        for k in (*_SEASON_KEYS, "competition"):
            a.pop(k, None)
    if mod.id == "auction":  # the model rarely picks a view; wording decides
        a["view"] = ask_rules.auction_view(question, "player" in a)
    if mod.id == "partnerships":
        a["group_by"] = ask_rules.partnership_group(question)
    if "venue" in a and question:  # a ground the model made up (not in the question) is dropped
        qt = _tokens(question)
        said = [t for t in _tokens(str(a["venue"])) if t not in _GENERIC]
        said = [_VENUE_ALIAS.get(t, t) for t in said]
        if not said or not all(
            any(_sim(w, t) >= 0.85 or _VENUE_ALIAS.get(t) == w for t in qt) for w in said
        ):
            notes.append(f"dropped venue={a.pop('venue')!r}: the question does not name it")
    if "venue" in allowed and "venue" not in a and question:
        if v := venue_in_question(question, a.get("competition")):
            a["venue"] = v
    asks, picks = [], dict(picks or {})
    comp = a.get("competition")
    for key in ("team", "opposition", "venue", "player", "player2", "give", "get"):
        if key not in a:
            continue
        if key in picks:
            a[key] = picks[key]
            continue
        vals = a[key] if isinstance(a[key], list) else [a[key]]
        done = []
        for v in vals:
            picker = {"team": pick_team, "opposition": pick_team, "venue": pick_venue}.get(
                key, pick_player
            )
            exact, cands = picker(str(v), comp or ("ipl" if key in ("give", "get") else None))
            if exact:
                done.extend(exact if isinstance(exact, list) else [exact])
            else:
                asks.append(
                    {"param": key, "said": str(v), "candidates": [c["name"] for c in cands]}
                )
        a[key] = done if isinstance(a[key], list) or len(done) > 1 else (done[0] if done else None)
        if key == "team" and done and not comp and "competition" in allowed:
            if only := _only_competition(done[0]):  # e.g. Chennai Super Kings plays only in the IPL
                a["competition"] = comp = only
                notes.append(f"competition set to {only}: {done[0]} only plays there")
    return {k: v for k, v in a.items() if v is not None}, asks, notes


def _team_pair(question: str) -> tuple[str, str] | None:
    """('MI', 'CSK') for 'MI vs CSK head to head': both sides of a vs/against are teams (3, 2 or 1 words each)."""
    m = re.search(r"\b(?:vs\.?|versus|against|v)\b", question.lower())
    if not m:
        return None
    left, right = _tokens(question[: m.start()]), _tokens(question[m.end() :])

    def side(words):
        for n in (3, 2, 1):
            if len(words) >= n:
                w = " ".join(words[:n] if words is right else words[-n:])
                if pick_team(w, None)[0]:
                    return w
        return None

    a, b = side(left), side(right)
    return (a, b) if a and b and a != b else None


def apply_rules(question: str, tool: dict | None, db_path: Path | None = None) -> dict | None:
    """Python overrides of the model's module pick. Returns the (possibly new) tool call, with `overrides` listing why."""
    cur = tool["name"] if tool else None
    args = dict(tool["arguments"]) if tool else {}
    with use_db(db_path):
        pair = _team_pair(question)
        if pair and not re.search(r"\bcompare\b|\bhome\b|\baway\b", question.lower()):
            mod, why = "teams", f"two teams on either side of vs: {pair[0]!r}, {pair[1]!r}"
            args = {k: v for k, v in args.items() if k not in ("player", "player2")}
            args["team"], args["opposition"] = pair
        else:
            mod, why = ask_rules.route(question, cur)
            q = question.lower()
            if (
                not mod
                and cur not in ("matchup", "matchup_predict", "compare", None)
                and "player" in args
                and "player2" in args
                and re.search(r"\bvs\.?\b|\bversus\b|\bagainst\b", q)
                and not re.search(r"compare|better|\bor\b", q)
            ):
                mod, why = "matchup", "a player vs a second player means matchup"
    if mod and mod == cur and pair:  # already teams, but the model may have left a side out
        return {**tool, "arguments": args}
    if not mod or mod == cur:
        return tool
    return {"name": mod, "arguments": args, "overrides": [(tool or {}).get("name"), mod, why]}


# ---------------------------------------------------------------- answer text
def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,}" if isinstance(v, int) else str(v)


def _row_text(row: pd.Series, n: int) -> str:
    return ", ".join(
        f"{str(k).replace('_', ' ')} {_fmt(v)}" for k, v in list(row.dropna().items())[:n]
    )


def make_answer(r: api.Result) -> str:
    """One plain sentence or two from the rows. Every number is copied from the data, none comes from the model."""
    m, df = r.meta, r.data
    scope = ", ".join(
        f"{k}={v}"
        for k, v in m["params"].items()
        if k
        in (
            "player",
            "player2",
            "team",
            "opposition",
            "competition",
            "season",
            "phase",
            "last_n_years",
            "season_from",
            "season_to",
        )
    )
    head = f"{m['title']} ({scope or 'all data'}), data through {m['data_through']}."
    if df.empty:
        return head + " No rows for these filters."
    if len(df) == 1:
        return f"{head} {_row_text(df.iloc[0], 12)}."
    labs = [c for c in df.columns if df[c].dtype == object and not c.endswith("id")][:2] or [
        df.columns[0]
    ]
    nums = [
        c
        for c in df.columns
        if c not in labs and pd.api.types.is_numeric_dtype(df[c]) and not c.endswith("id")
    ][:4]
    top = "; ".join(
        " / ".join(str(row[c]) for c in labs)
        + ": "
        + ", ".join(f"{c.replace('_', ' ')} {_fmt(row[c])}" for c in nums if pd.notna(row[c]))
        for _, row in df.head(5).iterrows()
    )
    return f"{head} {len(df)} rows. Top 5: {top}."


# ---------------------------------------------------------------- the whole flow
def execute(
    question: str,
    tool: dict,
    picks: dict | None = None,
    db_path: Path | None = None,
    timings: dict | None = None,
) -> dict:
    """Steps after the model: resolve names, run the module, build the answer. Also used to re-run after the user picks a candidate."""
    timings = dict(timings or {})
    out = {
        "question": question,
        "tool_call": tool,
        "resolved_params": None,
        "clarify": [],
        "notes": [],
        "result": None,
        "answer": None,
        "status": "ok",
        "timings": timings,
    }
    t = time.perf_counter()
    try:
        with use_db(db_path):
            params, asks, notes = resolve(tool, picks, question)
        if ov := tool.get("overrides"):
            notes.insert(0, f"routing: {ov[0] or 'no module'} -> {ov[1]} ({ov[2]})")
        out["notes"] = notes
        out["resolved_params"] = params
        if asks:
            out["clarify"], out["status"] = asks, "clarify"
            who = "; ".join(
                f"'{x['said']}' could be "
                + (" or ".join(x["candidates"][:4]) or "nobody I can find")
                for x in asks
            )
            out["answer"] = f"I need to know who/what you mean: {who}."
            return out
        r = api.run(tool["name"], db_path=db_path, **params)
        if r.data.empty and tool["name"] == "matchup" and {"player", "player2"} <= params.keys():
            params["player"], params["player2"] = (
                params["player2"],
                params["player"],
            )  # asked the wrong way round
            r2 = api.run("matchup", db_path=db_path, **params)
            if not r2.data.empty:
                r, out["resolved_params"] = r2, params
                out["notes"].append(
                    "batter and bowler were swapped: the first name had never faced the second as a batter"
                )
        out["result"] = {"meta": r.meta, "rows": r.to_records()}
        out["answer"] = make_answer(r)
    except ValueError as e:  # bad params, missing required player...
        out["status"], out["answer"] = "error", f"I could not run that: {e}"
        out["error_id"] = getattr(e, "error_id", None) or applog.log_error(
            "ask.execute", e, question=question, tool=tool
        )
    finally:
        timings["run_s"] = round(time.perf_counter() - t, 2)
        timings["total_s"] = round(sum(v for k, v in timings.items() if k != "total_s"), 2)
    return out


def ask(question: str, model: str = DEFAULT_MODEL, db_path: Path | None = None) -> dict:
    """question -> {id, question, tool_call, resolved_params, clarify, notes, result{meta, rows}, answer, status, timings}.

    status: ok | clarify (a name was ambiguous: see `clarify`) | no_tool (model found no module) | out_of_scope
    (not T20 ball-by-ball data: Test/ODI, line and length, weather...; the model is not even called) | error.
    Raises AskError when Ollama cannot be reached. Every call is appended to logs/ask.jsonl (see applog).
    """
    ask_id, t = applog.new_id("A"), time.perf_counter()
    if why := ask_rules.out_of_scope(question):
        out = {
            "id": ask_id,
            "question": question,
            "tool_call": None,
            "resolved_params": None,
            "clarify": [],
            "notes": [],
            "result": None,
            "status": "out_of_scope",
            "timings": {"total_s": round(time.perf_counter() - t, 2)},
            "answer": f"This app has T20 ball-by-ball data only; it can't answer {why}.",
        }
        applog.log_ask(
            {k: out[k] for k in ("id", "question", "status", "answer", "timings")}
            | {"model": model}
        )
        return out
    try:
        resp = _chat(question, model)
    except AskError as e:
        eid = applog.log_error("ask.chat", e, question=question, model=model)
        applog.log_ask(
            {
                "id": ask_id,
                "question": question,
                "model": model,
                "status": "error",
                "error_id": eid,
                "answer": str(e),
            }
        )
        e.error_id = eid
        raise
    timings = {"model_s": round(time.perf_counter() - t, 2)}
    tool = _tool_call(resp)
    if tool and tool["name"] not in {m.id for m in registry.all_modules()}:
        tool = None
    tool = apply_rules(question, tool, db_path)
    raw = json.dumps((resp.get("message") or {}), default=str)
    if tool is None or tool["name"] not in {m.id for m in registry.all_modules()}:
        text = ((resp.get("message") or {}).get("content") or "").strip()
        out = {
            "question": question,
            "tool_call": tool,
            "resolved_params": None,
            "clarify": [],
            "notes": [],
            "result": None,
            "status": "no_tool",
            "timings": {**timings, "total_s": timings["model_s"]},
            "answer": "No analysis module fits this question."
            + (f" Model said: {text[:200]}" if text else ""),
        }
        out["error_id"] = applog.log_note(
            "ask.no_tool",
            "model returned no usable tool",
            question=question,
            model=model,
            tool=tool,
        )
    else:
        out = execute(question, tool, db_path=db_path, timings=timings)
    out["id"] = ask_id
    applog.log_ask(
        {
            "id": ask_id,
            "question": question,
            "model": model,
            "raw": raw,
            "tool_call": out["tool_call"],
            "resolved_params": out["resolved_params"],
            "status": out["status"],
            "clarify": out["clarify"],
            "notes": out["notes"],
            "overrides": (out["tool_call"] or {}).get("overrides"),
            "row_count": (out["result"] or {}).get("meta", {}).get("row_count"),
            "answer": out["answer"],
            "timings": out["timings"],
            "error_id": out.get("error_id"),
        }
    )
    return out
