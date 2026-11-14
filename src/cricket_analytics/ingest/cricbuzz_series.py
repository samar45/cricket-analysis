"""Cricbuzz series scraper (pilot: Syed Mushtaq Ali Trophy 2025-26): raw fetch, then parse to parquet.

  python -m cricket_analytics.ingest.cricbuzz_series fetch   # raw files, resume-safe, polite
  python -m cricket_analytics.ingest.cricbuzz_series parse   # raw files -> parquet tables

Raw per match: scorecard.html.gz (page with the embedded scorecard JSON), comm1.json, comm2.json (innings commentary).
Reuses the throttle / Blocked / counters from commentary.py. Local only; never fetches matches dated >= S26_FROM.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

from . import commentary as cm

ROOT = Path("data/external/cricbuzz/smat2025")
SERIES = {10493: "syed-mushtaq-ali-trophy-elite-2025", 10487: "syed-mushtaq-ali-trophy-plate-2025"}
S26_FROM = dt.date(2026, 10, 15)  # locked live test set: never fetch
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BASE = "https://www.cricbuzz.com"
_dec = json.JSONDecoder()


def get(path: str) -> str:
    """One polite GET (>= cm.GAP s apart, long rest every cm.PAUSE_EVERY requests). Raises cm.Blocked on 403/429/captcha."""
    n = cm.requests_made[0]
    if n and n % cm.PAUSE_EVERY == 0:
        time.sleep(cm.PAUSE)
        cm._last[0] = time.time()
    wait = cm.GAP + 1 - (time.time() - cm._last[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get(BASE + path, headers={"User-Agent": UA}, timeout=30)
    cm._last[0] = time.time()
    cm.requests_made[0] += 1
    low = r.text[:3000].lower()
    if r.status_code in (403, 429) or "captcha" in low or "access denied" in low:
        raise cm.Blocked(f"{r.status_code} on {path}")
    r.raise_for_status()
    return r.text


# ------------------------------------------------------------------ list + fetch
def list_matches(sid: int, slug: str) -> list[dict]:
    """Series /matches page -> [{id, series, date (IST), desc, team1, team2}], sorted by date."""
    f = ROOT / "_series" / f"{sid}.html"
    if f.exists():
        t = f.read_text(encoding="utf-8")
    else:
        t = get(f"/cricket-series/{sid}/{slug}/matches")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(t, encoding="utf-8")
    t = t.replace('\\"', '"')
    seen = {}
    for m in re.finditer(r'"matchInfo":\{"matchId":(\d+),"seriesId":(\d+).*?"matchDesc":"([^"]*)".*?"startDate":"?(\d+).*?"team1":\{"teamId":\d+,"teamName":"([^"]+)".*?"team2":\{"teamId":\d+,"teamName":"([^"]+)"', t):
        if int(m[2]) == sid:
            d = (dt.datetime.fromtimestamp(int(m[4]) / 1000, dt.timezone.utc) + dt.timedelta(hours=5.5)).date()
            seen[m[1]] = dict(id=m[1], series=sid, date=d, desc=m[3], team1=m[5], team2=m[6])
    return sorted(seen.values(), key=lambda r: (r["date"], r["id"]))


def all_matches() -> list[dict]:
    ms = [m for sid, slug in SERIES.items() for m in list_matches(sid, slug)]
    return sorted((m for m in ms if m["date"] < S26_FROM), key=lambda r: (r["date"], r["id"]))


def fetch_match(mid: str, log=print) -> bool:
    """Save raw scorecard + commentary for one match; skip files already saved. Returns True if anything was fetched."""
    d = ROOT / str(mid)
    d.mkdir(parents=True, exist_ok=True)
    did = False
    if not (d / "scorecard.html.gz").exists():
        (d / "scorecard.html.gz").write_bytes(gzip.compress(get(f"/live-cricket-scorecard/{mid}/x").encode()))
        did = True
    for i in (1, 2):
        f = d / f"comm{i}.json"
        if not f.exists():
            f.write_text(get(f"/api/mcenter/{mid}/full-commentary/{i}"), encoding="utf-8")
            did = True
    return did


def fetch_all(log=print):
    ms = all_matches()
    log(f"{len(ms)} matches listed")
    try:
        for k, m in enumerate(ms, 1):
            fetch_match(m["id"])
            if k % 20 == 0:
                log(f"MILESTONE: {k}/{len(ms)} matches saved, {cm.requests_made[0]} requests this run")
    except cm.Blocked as e:
        log(f"MILESTONE: BLOCKED, stopped: {e}")
        raise
    log(f"MILESTONE: fetch complete, {len(ms)} matches")


# ------------------------------------------------------------------------ parse
def _grab(t: str, key: str):
    i = t.find(f'"{key}":')
    return _dec.raw_decode(t, i + len(key) + 3)[0] if i >= 0 else None


def load_scorecard(mid) -> tuple[dict, list]:
    t = gzip.decompress((ROOT / str(mid) / "scorecard.html.gz").read_bytes()).decode().replace('\\"', '"')
    return _grab(t, "matchHeader"), _grab(t, "scoreCard") or []


def _short(name: str) -> str:
    """'Ishan Kishan' -> 'I Kishan', 'Rajat Manohar Patidar' -> 'RM Patidar' (Cricsheet style)."""
    p = name.split()
    return name if len(p) < 2 else "".join(w[0] for w in p[:-1]).upper() + " " + p[-1]


def team_players(db="data/cricket_analytics.duckdb") -> dict[str, set[str]]:
    """lower-case Cricsheet SMAT team name -> set of Cricsheet player names that played for it (read-only DB)."""
    import duckdb

    con = duckdb.connect(db, read_only=True)
    rows = con.sql(
        "select batting_team, batter from deliveries d join matches m using(match_id) where m.competition='smat' "
        "union select bowling_team, bowler from deliveries d join matches m using(match_id) where m.competition='smat'").fetchall()
    con.close()
    out: dict[str, set[str]] = {}
    for t, n in rows:
        out.setdefault(t.lower(), set()).add(n)
    return out


def cs_name(name: str, team: str, tp: dict) -> str:
    """Cricsheet name only on an exact, unique hit among that team's SMAT players (derived 'RM Patidar' or the full name)."""
    pool = tp.get(team.lower(), set())
    hits = {n for n in pool if n.lower() in (_short(name).lower(), name.lower())}
    return hits.pop() if len(hits) == 1 else ""


def parse_match(mid, meta: dict, tp: dict) -> dict:
    mh, sc = load_scorecard(mid)
    ts = dt.datetime.fromtimestamp(mh["matchStartTimestamp"] / 1000, dt.timezone.utc) + dt.timedelta(hours=5.5)
    res, toss, v = mh.get("result") or {}, mh.get("tossResults") or {}, mh.get("venue") or {}
    status = mh.get("status", "")
    method = "VJD" if re.search(r"vjd|v\.?j\.?d|dls|d/l", status + (mh.get("revisedTarget") or {}).get("reason", ""), re.I) else ""
    overs = [s["scoreDetails"].get("revisedOvers") or s["scoreDetails"].get("overs") for s in sc]
    mrow = dict(match_id=str(mid), date=ts.date(), series=mh.get("seriesName"), stage=meta["desc"], venue=v.get("name"), city=v.get("city"),
                team1=mh["team1"]["name"], team2=mh["team2"]["name"], toss_winner=toss.get("tossWinnerName"), toss_decision=toss.get("decision"),
                status=status, result_type=res.get("resultType"), winner=res.get("winningTeam"), margin=res.get("winningMargin"),
                by_runs=res.get("winByRuns"), method=method, overs_inn1=overs[0] if overs else None, overs_inn2=overs[1] if len(overs) > 1 else None,
                complete=mh.get("complete"))
    bat, bowl, inn = [], [], []
    for s in sc:
        bt, bw = s["batTeamDetails"], s["bowlTeamDetails"]
        sd, ex = s["scoreDetails"], s["extrasData"]
        inn.append(dict(match_id=str(mid), innings=s["inningsId"], team=bt["batTeamName"], runs=sd["runs"], wickets=sd["wickets"],
                        overs=sd["overs"], balls=sd["ballNbr"], extras=ex["total"], wides=ex["wides"], noballs=ex["noBalls"],
                        byes=ex["byes"], legbyes=ex["legByes"], penalty=ex["penalty"], fow=json.dumps([(w["batId"], w["wktRuns"], w["wktOver"]) for w in (s.get("wicketsData") or {}).values()])))
        for k, b in enumerate(bt["batsmenData"].values(), 1):
            out = b["outDesc"].strip().lower() not in ("", "not out", "batting")
            bat.append(dict(match_id=str(mid), innings=s["inningsId"], team=bt["batTeamName"], pos=k, cricbuzz_id=b["batId"], name=b["batName"],
                            cricsheet_name=cs_name(b["batName"], bt["batTeamName"], tp), runs=b["runs"], balls=b["balls"], fours=b["fours"], sixes=b["sixes"],
                            out_desc=b["outDesc"], is_out=out, wicket_code=b["wicketCode"], bowler_id=b["bowlerId"], fielder_id=b["fielderId1"]))
        for b in bw["bowlersData"].values():
            bowl.append(dict(match_id=str(mid), innings=s["inningsId"], team=bw["bowlTeamName"], cricbuzz_id=b["bowlerId"], name=b["bowlName"],
                             cricsheet_name=cs_name(b["bowlName"], bw["bowlTeamName"], tp), overs=b["overs"], balls=b["balls"], maidens=b["maidens"],
                             runs=b["runs"], wickets=b["wickets"], wides=b["wides"], noballs=b["no_balls"]))
    return dict(match=mrow, batting=bat, bowling=bowl, innings=inn, deliveries=parse_deliveries(mid, sc, tp))


def parse_deliveries(mid, sc, tp) -> list[dict]:
    """Ball rows from the commentary, only when the match has complete ball-by-ball (legal balls and runs agree with the scorecard)."""
    rows = []
    for s in sc:
        f = ROOT / str(mid) / f"comm{s['inningsId']}.json"
        if not f.exists():
            return []
        d = json.loads(f.read_text(encoding="utf-8"))
        items = [x for c in d.get("commentary", []) for x in c["commentaryList"] if x.get("ballNbr") and x.get("overNumber")]
        items.sort(key=lambda x: (x["timestamp"], x["ballNbr"]))
        if sum(x["totalRuns"] for x in items) != s["scoreDetails"]["runs"] or not items:
            return []  # partial coverage: skip the whole match, never mix
        bt, bw = s["batTeamDetails"], s["bowlTeamDetails"]
        outs = {b["batId"]: b for b in bt["batsmenData"].values()}
        seq: dict[int, int] = {}
        for x in items:
            p = cm.parse_item(x) or {}
            ov = int(x["overNumber"])
            seq[ov] = seq.get(ov, 0) + 1
            ext = p.get("extra")
            tot = x["totalRuns"]
            wide, nb, by, lb = (tot if ext == "wide" else 0), (1 if ext == "no ball" else 0), (tot if ext == "byes" else 0), (tot if ext == "leg byes" else 0)
            extras = wide + nb + by + lb
            bs, bo = x.get("batsmanStriker") or {}, x.get("bowlerStriker") or {}
            wk = "WICKET" in x.get("event", "")
            o = outs.get(bs.get("batId")) if wk else None
            rows.append(dict(
                match_id=str(mid), innings=s["inningsId"], over_num=ov, ball_num=seq[ov], batter=bs.get("batName"), bowler=bo.get("bowlName"),
                non_striker=None, batter_id=bs.get("batId"), bowler_id=bo.get("bowlId"),
                batter_cs=cs_name(bs.get("batName", ""), bt["batTeamName"], tp), bowler_cs=cs_name(bo.get("bowlName", ""), bw["bowlTeamName"], tp),
                runs_batter=tot - extras, runs_extras=extras, runs_total=tot, extra_type=ext, wides=wide, noballs=nb, byes=by, legbyes=lb,
                wicket_type=(o["wicketCode"].lower().replace("_", " ") if o else None), player_out=bs.get("batName") if o else None,
                fielder=None, batting_team=bt["batTeamName"], bowling_team=bw["bowlTeamName"], text=p.get("text")))
    return rows


def _body(x):
    return x.get("commText", "")


def parse_all(log=print) -> dict:
    tp = team_players()
    out = {k: [] for k in ("match", "batting", "bowling", "innings", "deliveries")}
    failed = []
    for m in all_matches():
        if not (ROOT / m["id"] / "scorecard.html.gz").exists():
            failed.append((m["id"], "not fetched"))
            continue
        try:
            r = parse_match(m["id"], m, tp)
        except Exception as e:  # report, don't chase
            failed.append((m["id"], repr(e)))
            continue
        out["match"].append(r["match"])
        for k in ("batting", "bowling", "innings", "deliveries"):
            out[k] += r[k]
    names = {"match": "matches", "batting": "batting", "bowling": "bowling", "innings": "innings", "deliveries": "deliveries"}
    for k, v in out.items():
        pd.DataFrame(v).to_parquet(ROOT / f"{names[k]}.parquet", index=False)
    log(f"MILESTONE: parsed {len(out['match'])} matches, {len(failed)} failed: {failed[:5]}")
    return dict(out, failed=failed)


if __name__ == "__main__":
    {"fetch": fetch_all, "parse": parse_all}[sys.argv[1]]()
