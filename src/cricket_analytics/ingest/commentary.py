"""Cricbuzz ball-by-ball commentary: polite cached fetch + parser (pilot)."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import requests

CACHE = Path("data/external/commentary/cricbuzz")
UA = "cricket-analysis personal research"
GAP = 2        # seconds between requests (Samar: never below 2)
PAUSE_EVERY = 100  # extra rest of PAUSE s after this many requests in one process
PAUSE = 30
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
    if requests_made[0] and requests_made[0] % PAUSE_EVERY == 0 and _last[0] >= 0:
        time.sleep(PAUSE)
        _last[0] = time.time()
    wait = GAP - (time.time() - _last[0])
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
    ("bouncer", r"bouncer|bumper"),  # explicit only: "short ball" / "banged in short" are just "short" (spinners bowl those too)
    ("short of length", r"short of (?:a )?(?:good )?length"), ("back of a length", r"back of (?:a )?length"),
    ("short", r"\bshortish|\bfraction shorter|\bshort\b(?! (?:third|mid|fine|leg|cover|midwicket|extra|square|backward|fielder))"),
    ("length", r"\blength and|\b(?:good )?length (?:ball|delivery)|\bgood length|\blength delivery|\bon a length"),
    ("full", r"\bfull\b|\bfullish|\bfuller\b|half[- ]volley|pitched up"),
]
LINE = [
    ("outside off", r"outside off|outside the off|wide of off|around off|off stump|on off|outside the line of off"),
    ("leg", r"\bon leg\b|down (?:the )?leg|leg[- ]lined|leg stump|on the pads|on the legs|leg side|into the pads"),
    ("wide", r"\bwide\b(?! (?:long|mid|third|fine|cover|deep|square|backward|point|slip|gully|of the))|called as a wide"),
    ("body", r"at the body|into the body|at the hips|at the ribs|at the throat|at the left-hander|at the batter|at the batsman|at the head|at the helmet"),
    ("middle", r"middle stump|\bmiddle and|on middle|on the stumps|at the stumps|\bstumps\b"),
]
DELIVERY = [
    ("slower ball", r"slower (?:ball|one|delivery)|\bslower\b"), ("knuckle ball", r"knuckle"),
    ("cutter", r"cutter|cut(?:s)? it back"), ("back of the hand", r"back of the hand"),
    ("googly", r"googly|wrong[- ]?'?un"), ("carrom", r"carrom"), ("flipper", r"flipper"),
    ("doosra", r"doosra"), ("arm ball", r"arm ball"), ("topspinner", r"top[- ]?spinner"),
    ("leg break", r"leg[- ]?(?:break|spin)"), ("off break", r"off[- ]?(?:break|spin)"),
    ("inswinger", r"in[- ]?swing|swinging in"), ("outswinger", r"out[- ]?swing|swinging away|away swing"),
]
CONTACT = [
    ("inside edge", r"inside[- ]edg"), ("top edge", r"top[- ]?edg"), ("leading edge", r"leading[- ]?edg"),
    ("bottom edge", r"bottom[- ]?edg"), ("edge", r"\bedge[sd]?\b|\bnick"),
    ("miss", r"swings? and (?:a )?miss|\bmisses\b|\bmissed\b|beaten|no contact|not make contact|does not connect|fails to connect"),
    ("mistimed", r"mistime|not off the middle|not middled|didn'?t middle|toe[- ]end|bottom of the bat"),
    ("middle", r"off the middle|middled|\bconnected\b|\bsweet\b|timed|well[- ]timed|connects"),
]
SHOT = [
    ("reverse sweep", r"reverse[- ]sweep|reverse[- ]?scoop"), ("scoop", r"scoop|ramp|dilscoop"),
    ("sweep", r"sweep"), ("hook", r"\bhook"), ("pull", r"\bpull"), ("cut", r"\bcuts?\b(?! (?:it )?off\b)|upper[- ]?cut|\bslaps\b|\bchop"),
    ("drive", r"\bdr(?:ive|ives|ove)\b|\bdriv"), ("flick", r"flick|whip"), ("glance", r"glanc|tickle"),
    ("slog", r"slog|\bheav"), ("loft", r"\bloft|\bover the (?:top|rope)|clears? the rope|hoick"),
    ("punch", r"punch(?!es the air)|\bswat"), ("steer", r"steer|dab|guide|deflect|\bnudge|\bpaddle|\blap\b|\bclip"),
    ("block", r"\bblock|\bdefen[ds]|\bpush|\bpats?\b|\bprod|digs? it out"), ("leave", r"\bleaves?\b|left alone|lets? (?:it|the ball) (?:go|pass)|shoulders arms"),
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
    if not m and not x.get("ballNbr"):
        return None
    # Cricbuzz sometimes serves a truncated text fragment for a real delivery: keep the row, parse nothing
    bowler, batter, end = (m.group(1), m.group(2), m.end()) if m else ("?", "?", len(text))
    low = text.lower()
    body = low[end:]  # skip "bowler to batter," so names never match
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
        "bat_id": (x.get("batsmanStriker") or {}).get("batId"), "bowl_id": (x.get("bowlerStriker") or {}).get("bowlId"),
        "bat_mins": (x.get("batsmanStriker") or {}).get("batMins"), "bat_dots": (x.get("batsmanStriker") or {}).get("batDots"),
        "team_score": x.get("batTeamScore"), "bat_team": x.get("batTeamName"),
        "bowler": bowler, "batter": batter,
        "runs_total": x.get("totalRuns", 0), "runs_legal": x.get("legalRuns", 0),
        "extra": extra if x.get("totalRuns", 0) > 0 or extra else None, "wicket": wk, "event": ev,
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


def extras(mid) -> dict:
    """Everything else in the cached JSON (0 requests): match header row, over summaries, players, impact-sub mentions. No commentary text."""
    import json

    m, overs, imp = {}, [], []
    for i in (1, 2):
        f = CACHE / (hashlib.sha1(API.format(mid=mid, inn=i).encode()).hexdigest()[:16] + ".txt")
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if not m:
            h, ms = d["matchDetails"]["matchHeader"], d["matchDetails"].get("miniscore") or {}
            r, t, v = h.get("result") or {}, h.get("tossResults") or {}, h.get("venue") or {}
            pm = (h.get("playersOfTheMatch") or [{}])[0]
            pp = (ms.get("ppData") or {}).get("pp_1") or {}
            ud = ms.get("matchUdrs") or {}
            m = dict(cricbuzz_id=mid, desc=h.get("matchDescription"), day_night=h.get("dayNight"),
                     start_ts=h.get("matchStartTimestamp"), end_ts=h.get("matchCompleteTimestamp"), state=h.get("state"),
                     toss_winner=t.get("tossWinnerName"), toss_decision=t.get("decision"),
                     result_type=r.get("resultType"), winner=r.get("winningTeam"), margin=r.get("winningMargin"),
                     by_runs=r.get("winByRuns"), dls_reason=(h.get("revisedTarget") or {}).get("reason"),
                     potm_id=pm.get("id"), potm=pm.get("name"), venue_id=v.get("id"), venue=v.get("name"),
                     city=v.get("city"), lat=v.get("latitude"), lon=v.get("longitude"), tz=v.get("timezone"),
                     pp_from=pp.get("ppOversFrom"), pp_to=pp.get("ppOversTo"),
                     udrs=json.dumps({k: v for k, v in ud.items() if k.startswith("team")}) if ud else None,
                     pots=json.dumps([{k: p.get(k) for k in ("id", "name", "battingStyle", "bowlingStyle", "role")}
                                      for p in h.get("playersOfTheSeries") or []]) or None)
        for c in d["commentary"]:
            for x in c["commentaryList"]:
                o = x.get("overSeparator")
                if o:
                    overs.append(dict(cricbuzz_id=mid, innings=i, over=int(o["overNum"]), ts=o.get("timestamp"),
                                      score=o["score"], wickets=o["wickets"], runs=o["runs"], o_summary=o["o_summary"],
                                      bowl_id=(o.get("bowlIds") or [None])[0], bat_ids=json.dumps(o.get("batStrikerIds")),
                                      nonstriker_ids=json.dumps(o.get("batNonStrikerIds"))))
                if re.search(r"impact (?:player|sub)", x["commText"] + str(x.get("commentaryFormats")), re.I):
                    # free text only (names not reliably parseable): keep where/when, not the text
                    imp.append(dict(cricbuzz_id=mid, innings=i, ts=x["timestamp"], team=x.get("batTeamName"), is_ball=bool(x.get("overNumber"))))
    return dict(match=m, overs=overs, impact=imp)


def coverage(rows: list[dict]) -> dict[str, float]:
    keys = ["speed", "length", "line", "delivery", "contact", "shot", "lapse"]
    return {k: round(100 * sum(r[k] is not None for r in rows) / len(rows), 1) for k in keys}


# ----------------------------------------------------------------------- join
def join_cricsheet(rows: list[dict], cricsheet_id: str, db="data/cricket_analytics.duckdb"):
    """Pair by (innings, delivery order). Returns (pairs, stats). Read-only DB."""
    import duckdb

    con = duckdb.connect(db, read_only=True)
    cs = con.sql(
        "select innings, over_num, ball_num, batter, bowler, runs_total, ball_seq from deliveries "
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


def series_ids(sid: int, slug: str, db="data/cricket_analytics.duckdb"):
    """Cricbuzz series /matches page -> rows mapped to Cricsheet by IST date + team pair. Returns (mapped, unmatched)."""
    import datetime as dt
    import duckdb

    t = fetch(f"https://www.cricbuzz.com/cricket-series/{sid}/{slug}/matches").replace('\\"', '"')
    seen = {}
    for m in re.finditer(r'"matchInfo":\{"matchId":(\d+),"seriesId":(\d+).*?"startDate":"?(\d+).*?"team1":\{"teamId":\d+,"teamName":"([^"]+)".*?"team2":\{"teamId":\d+,"teamName":"([^"]+)"', t):
        if int(m[2]) == sid:
            d = (dt.datetime.fromtimestamp(int(m[3]) / 1000, dt.timezone.utc) + dt.timedelta(hours=5.5)).date().isoformat()
            seen[m[1]] = (d, m[4], m[5])
    con = duckdb.connect(db, read_only=True)
    cs = con.sql("select match_id, date, team1, team2 from matches where competition='ipl' and year(date)=? ",
                 params=[int(slug[-4:])]).fetchall()
    con.close()
    key = lambda d, a, b: (str(d), frozenset((a.split()[0].lower(), b.split()[0].lower())))
    idx = {key(d, a, b): mid for mid, d, a, b in cs}
    mapped, unmatched = [], []
    for cb, (d, a, b) in sorted(seen.items(), key=lambda kv: kv[1]):
        mid = idx.get(key(d, a, b))
        (mapped if mid else unmatched).append((cb, mid, d, a, b))
    return mapped, unmatched, len(cs)


IDS = Path(__file__).parents[1] / "reference" / "cricbuzz_ids.csv"


def series_run(season: int, limit: int, only=None, out=None, db="data/cricket_analytics.duckdb"):
    """Fetch+parse mapped IPL matches (cache-aware: cached matches cost 0 requests, so reruns resume)."""
    import csv

    todo = [r for r in csv.DictReader(open(IDS)) if r["date"].startswith(str(season))]
    if only:
        todo = [r for r in todo if r["cricbuzz_id"] in only]
    allrows = []
    for m in todo[:limit]:
        try:
            rs = parse_match(m["cricbuzz_id"])
        except Blocked:
            raise
        except Exception as e:  # abandoned / no commentary: skip and list
            print("SKIP", m["cricbuzz_id"], m["cricsheet_match_id"], type(e).__name__, e, flush=True)
            continue
        pairs, st = join_cricsheet(rs, m["cricsheet_match_id"], db)
        for r, d in pairs:
            r.update(match_id=m["cricsheet_match_id"], cricbuzz_id=m["cricbuzz_id"], cs_ball_num=d[2], ball_seq=d[6])
        print(m["cricbuzz_id"], m["cricsheet_match_id"], "paired", st["paired"], "/", st["cricsheet"],
              "runs_ok", st["runs"], "bowler_ok", st["bowler"], "batter_ok", st["batter"],
              "reqs", requests_made[0], flush=True)
        allrows += [r for r, _ in pairs]
    if out and allrows:
        import pandas as pd

        pd.DataFrame(allrows).drop(columns=["text"]).to_csv(out, index=False)  # no raw commentary text
    if allrows:
        print("coverage", coverage(allrows))
    return allrows


PARSED = Path("data/external/commentary/parsed_ipl_2023_2026.csv")
PARSED_OLD = Path("data/external/commentary/parsed_ipl_2020_2022.csv")


def load_parsed(path=None):
    """Parsed commentary, one row per ball (IPL 2020-2026 when both files exist). Join to deliveries on (match_id, innings, ball_seq)."""
    import pandas as pd

    paths = [path] if path else sorted(PARSED.parent.glob("parsed_ipl_[0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9].csv"))
    return pd.concat([pd.read_csv(p, dtype={"match_id": str, "cricbuzz_id": str}) for p in paths], ignore_index=True)


def pull_all(seasons=(2023, 2024, 2025, 2026), out=PARSED):
    """Fetch (cache-aware, resumable) + parse every mapped IPL match of the seasons into one CSV, no raw text.
    Also writes <out stem>_matches / _overs / _impact / _players CSVs from the same cached JSON."""
    import pandas as pd

    rows = []
    for y in seasons:
        rows += series_run(y, 10**6)
    df = pd.DataFrame(rows).drop(columns=["text"])
    df.to_csv(out, index=False)
    out = Path(out)
    ex = [(extras(c), c, mid) for c, mid in df[["cricbuzz_id", "match_id"]].drop_duplicates().itertuples(index=False)]
    ids = {c: mid for _, c, mid in ex}
    for key in ("overs", "impact"):
        t = pd.DataFrame([r for e, _, _ in ex for r in e[key]], columns=None if any(e[key] for e, _, _ in ex) else ["cricbuzz_id"])
        t.insert(1, "match_id", t.cricbuzz_id.map(ids))
        t.to_csv(out.with_name(out.stem + f"_{key}.csv"), index=False)
    t = pd.DataFrame([e["match"] for e, _, _ in ex if e["match"]])
    t.insert(1, "match_id", t.cricbuzz_id.map(ids))
    t.to_csv(out.with_name(out.stem + "_matches.csv"), index=False)
    pl = pd.concat([df[["match_id", "bat_id", "batter", "bat_team"]].set_axis(["match_id", "cricbuzz_player_id", "name", "team"], axis=1).assign(role="bat"),
                    df[["match_id", "bowl_id", "bowler"]].set_axis(["match_id", "cricbuzz_player_id", "name"], axis=1).assign(role="bowl")])
    pl.drop_duplicates().to_csv(out.with_name(out.stem + "_players.csv"), index=False)
    print("wrote", out, len(rows), "balls; requests", requests_made[0], flush=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--match", help="Cricbuzz match id")
    ap.add_argument("--all", action="store_true", help="pull_all IPL 2023-2026")
    ap.add_argument("--seasons", help="e.g. 2017-2019: pull into parsed_ipl_2017_2019.csv")
    ap.add_argument("--old", action="store_true", help="pull IPL 2020-2022 into parsed_ipl_2020_2022.csv")
    ap.add_argument("--series", choices=["ipl"], help="fetch mapped matches of a series")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--ids", help="comma-separated Cricbuzz ids (with --series)")
    ap.add_argument("--out", help="parsed CSV path (no raw text)")
    ap.add_argument("--cricsheet", help="Cricsheet match_id to join to")
    a = ap.parse_args()
    if a.seasons:
        lo, hi = map(int, a.seasons.split("-"))
        pull_all(range(lo, hi + 1), PARSED.with_name(f"parsed_ipl_{lo}_{hi}.csv"))
        raise SystemExit
    if a.old:
        pull_all((2020, 2021, 2022), PARSED_OLD)
        raise SystemExit
    if a.all:
        pull_all()
        raise SystemExit
    if a.series:
        series_run(a.season, a.limit, set(a.ids.split(",")) if a.ids else None, a.out)
        raise SystemExit
    rs = parse_match(a.match)
    print(len(rs), "balls;", requests_made[0], "requests;", coverage(rs))
    if a.cricsheet:
        print(join_cricsheet(rs, a.cricsheet)[1])
