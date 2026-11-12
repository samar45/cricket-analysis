"""Cricbuzz ball-by-ball commentary: polite cached fetch + parser (pilot)."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import requests

CACHE = Path("data/external/commentary/cricbuzz")
UA = "cricket-analysis personal research"
_last = [0.0]
requests_made = [0]


class Blocked(RuntimeError):
    pass


def fetch(url: str) -> str:
    """GET with disk cache, 1 request / 3 s, stop on any block."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")
    if f.exists():
        return f.read_text(encoding="utf-8")
    wait = 3 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    _last[0] = time.time()
    requests_made[0] += 1
    low = r.text[:3000].lower()
    if r.status_code in (403, 429) or "captcha" in low or "access denied" in low:
        raise Blocked(f"{r.status_code} on {url}")
    r.raise_for_status()
    f.write_text(r.text, encoding="utf-8")
    return r.text


# ---------------------------------------------------------------- fetch match
API = "https://www.cricbuzz.com/api/mcenter/{mid}/full-commentary/{inn}"


def fetch_match(mid: int | str, innings=(1, 2)) -> list[dict]:
    """One request per innings returns that innings' whole commentary (no paging)."""
    import json

    items = []
    for i in innings:
        d = json.loads(fetch(API.format(mid=mid, inn=i)))
        items += [x for c in d["commentary"] for x in c["commentaryList"]]
    return items


# ---------------------------------------------------------------------- parse
def _first(rules, text):
    for label, pat in rules:
        if re.search(pat, text):
            return label
    return None


LENGTH = [
    ("full toss", r"full[- ]toss"), ("yorker", r"yorker"),
    ("bouncer", r"bouncer|banged in short|short and (?:at|into|rising)|short ball"),
    ("short of length", r"short of (?:a )?length"), ("back of a length", r"back of (?:a )?length"),
    ("short", r"\bshort\b(?! (?:third|mid|fine|leg|cover|midwicket|extra|square|backward|fielder))"),
    ("length", r"\b(?:good )?length (?:ball|delivery)|\bgood length|\blength delivery|\bon a length"),
    ("full", r"\bfull\b|\bfuller\b|half[- ]volley"),
]
LINE = [
    ("wide", r"\bwide\b|called as a wide"), ("outside off", r"outside off|outside the off|wide of off|around off|off stump|on off"),
    ("leg", r"down (?:the )?leg|leg stump|on the pads|on the legs|leg side|into the pads"),
    ("body", r"at the body|into the body|at the hips|at the ribs|at the throat|at the left-hander|at the batter|at the batsman|at the head|at the helmet"),
    ("middle", r"middle stump|\bmiddle and|on middle|\bstraight\b|on the stumps|on the stumps"),
]
DELIVERY = [
    ("slower ball", r"slower (?:ball|one|delivery)|\bslower\b"), ("knuckle ball", r"knuckle"),
    ("cutter", r"cutter|cut(?:s)? it back"), ("back of the hand", r"back of the hand"),
    ("googly", r"googly|wrong[- ]?'?un"), ("carrom", r"carrom"), ("flipper", r"flipper"),
    ("doosra", r"doosra"), ("arm ball", r"arm ball"), ("topspinner", r"top[- ]?spinner"),
    ("leg break", r"leg[- ]?(?:break|spin)"), ("off break", r"off[- ]?(?:break|spin)"),
    ("inswinger", r"in[- ]?swing|swinging in|angled in"), ("outswinger", r"out[- ]?swing|swinging away|away swing"),
]
CONTACT = [
    ("inside edge", r"inside[- ]edge"), ("top edge", r"top[- ]?edge"), ("leading edge", r"leading[- ]?edge"),
    ("bottom edge", r"bottom[- ]?edge"), ("edge", r"\bedge[sd]?\b|\bnick"),
    ("miss", r"swings? and (?:a )?miss|\bmisses\b|\bmissed\b|beaten|no contact|not make contact|does not connect|fails to connect"),
    ("mistimed", r"mistime|not off the middle|not middled|didn'?t middle|toe[- ]end|bottom of the bat"),
    ("middle", r"off the middle|middled|\bsweet\b|timed|well[- ]timed|connects"),
]
SHOT = [
    ("reverse sweep", r"reverse[- ]sweep|reverse[- ]?scoop"), ("scoop", r"scoop|ramp|dilscoop"),
    ("sweep", r"sweep"), ("hook", r"\bhook"), ("pull", r"\bpull"), ("cut", r"\bcut(?:s)?\b|upper[- ]?cut|\bslaps\b"),
    ("drive", r"\bdr(?:ive|ives|ove)\b|\bdriv"), ("flick", r"flick|whip"), ("glance", r"glanc|tickle"),
    ("slog", r"slog|\bheav"), ("loft", r"\bloft|\bover the (?:top|rope)|clears? the rope|hoick"),
    ("punch", r"punch|\bswat"), ("steer", r"steer|dab|guide|deflect|\bnudge|\bpaddle|\blap\b|\bclip"),
    ("block", r"\bblock|\bdefend|\bpush|\bpat\b"), ("leave", r"\bleaves?\b|lets? (?:it|the ball) (?:go|pass)|shoulders arms"),
]
LAPSE = [
    ("drop", r"dropped(?! (?:in front|short|just|towards|it))|puts down|spilled|can'?t hold on|fails to hold|grassed"),
    ("misfield", r"misfield|fumble|\bmisjudge|overthrow|let (?:it|the ball) through|through the legs|lets it slip"),
]


def parse_item(x: dict) -> dict | None:
    """One Cricbuzz commentary item -> one parsed ball row (None if not a delivery)."""
    on = x.get("overNumber")
    if not on:
        return None
    text = x["commText"]
    fm = (x.get("commentaryFormats") or {}).get("bold")
    if fm:
        for k, v in zip(fm["formatId"], fm["formatValue"]):
            text = text.replace(k, v)
    m = re.match(r"(.+?) to (.+?),", text)
    if not m:
        return None
    low = text.lower()
    body = low[m.end():]  # skip "bowler to batter," so names never match
    sp = re.search(r"(\d{2,3}(?:\.\d)?)\s*(?:ks|kph|km/h|kmph)\b", low)
    ev = x.get("event", "")
    extra = _first(
        [("wide", r"\bwide\b"), ("no ball", r"no[- ]ball"), ("leg byes", r"leg[- ]byes?"), ("byes", r"\bbyes?\b")],
        body[:60] if "wide" not in ev.lower() else body,
    )
    wk = "WICKET" in ev
    return {
        "innings": x["inningsId"], "over": int(on), "ball": round((on - int(on)) * 10),
        "ball_no": x["ballNbr"], "ts": x["timestamp"],
        "bowler": m.group(1), "batter": m.group(2),
        "runs_total": x["totalRuns"], "runs_legal": x["legalRuns"],
        "extra": extra if x["totalRuns"] > 0 or extra else None, "wicket": wk, "event": ev,
        "text": text,
        "speed": float(sp.group(1)) if sp else None,
        "length": _first(LENGTH, body), "line": _first(LINE, body),
        "delivery": _first(DELIVERY, body), "contact": _first(CONTACT, body),
        "shot": _first(SHOT, body), "lapse": _first(LAPSE, body) or ("drop" if "DROPPED" in ev else None),
    }


def parse_match(mid) -> list[dict]:
    rows = [r for x in fetch_match(mid) if (r := parse_item(x))]
    rows.sort(key=lambda r: (r["innings"], r["ts"], r["ball_no"]))
    return rows


def coverage(rows: list[dict]) -> dict[str, float]:
    keys = ["speed", "length", "line", "delivery", "contact", "shot", "lapse"]
    return {k: round(100 * sum(r[k] is not None for r in rows) / len(rows), 1) for k in keys}


# ----------------------------------------------------------------------- join
def join_cricsheet(rows: list[dict], cricsheet_id: str, db="data/cricket_analytics.duckdb"):
    """Pair by (innings, delivery order). Returns (pairs, stats). Read-only DB."""
    import duckdb

    con = duckdb.connect(db, read_only=True)
    cs = con.sql(
        "select innings, over_num, ball_num, batter, bowler, runs_total from deliveries "
        "where match_id=? order by innings, ball_seq", params=[cricsheet_id]).fetchall()
    con.close()
    by_inn: dict[int, list] = {}
    for r in rows:
        by_inn.setdefault(r["innings"], []).append(r)
    pairs, st = [], dict(cricsheet=len(cs), commentary=len(rows), over=0, runs=0, bowler=0, batter=0)
    for inn in sorted(by_inn):
        c = [d for d in cs if d[0] == inn]
        for r, d in zip(by_inn[inn], c):
            st["over"] += r["over"] == d[1]
            st["runs"] += r["runs_total"] == d[5]
            st["bowler"] += r["bowler"].split()[-1].lower() == d[4].split()[-1].lower()
            st["batter"] += r["batter"].split()[-1].lower() == d[3].split()[-1].lower()
            pairs.append((r, d))
    st["paired"] = len(pairs)
    return pairs, st


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="Cricbuzz match id")
    ap.add_argument("--cricsheet", help="Cricsheet match_id to join to")
    a = ap.parse_args()
    rs = parse_match(a.match)
    print(len(rs), "balls;", requests_made[0], "requests;", coverage(rs))
    if a.cricsheet:
        print(join_cricsheet(rs, a.cricsheet)[1])
