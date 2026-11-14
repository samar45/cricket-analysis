"""S26 live logger: watches the Cricbuzz SMAT 2026 series and appends predictions to data/external/live/s26/predictions.jsonl.

  python -m cricket_analytics.live.smat_logger run

Does exactly what the pre-registration in docs/ML_PREDICTION.md says: pre-match once, in-play at the end of overs 6, 10, 15, one
result line per match. Append-only, de-duplicated by (match, innings, checkpoint, kind). Missed checkpoints are never filled in.
Reuses the polite fetch of ingest/cricbuzz_series.py (>= 3 s between requests, one at a time, stops on a block).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import time
import traceback
from pathlib import Path

from ..ingest import commentary as cm
from ..ingest import cricbuzz_series as cs

VERSION = "1.0"
SERIES = {12420: "Elite", 12431: "Plate"}
OUT = Path("data/external/live/s26")
PRED, LOG = OUT / "predictions.jsonl", OUT / "logger.log"
COMP = "smat"
OVERS = (6, 10, 15)
MAX_LAG = 6 * 60      # s: an over-summary older than this at poll time is a missed checkpoint, never logged
POLL, LIST_EVERY, PRE_WINDOW = 75, 600, 6 * 3600
REQUIRED_KEYS = {"utc", "match_id", "series", "team_a", "team_b", "venue", "innings", "checkpoint", "kind", "state", "outputs",
                 "source_url", "model_hash", "logger_version", "flags"}
TEAM_ALIAS = {"hyderabad": "Hyderabad (India)", "jammu and kashmir": "Jammu & Kashmir"}
MODEL_FILES = ["v2/final_conformal_delta.json", "v2/final_score_q10.txt", "v2/final_score_q50.txt", "v2/final_score_q90.txt",
               "v2/final_win_w0.txt", "v2/final_win_w1m.txt", "ball_B_men_fresh.pkl", "prematch/model.json", "prematch/params.json",
               "production_meta.json"]
_hash = [""]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{now_utc()} {msg}\n")


# ------------------------------------------------------------------ writer
class Writer:
    """Append-only JSONL; a line is skipped if its (match_id, innings, checkpoint, kind) is already in the file."""

    def __init__(self, path):
        self.path, self.seen, self.count = Path(path), set(), 0
        if self.path.exists():
            for ln in self.path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    self.seen.add(self._k(json.loads(ln)))

    @staticmethod
    def _k(r):
        return (str(r["match_id"]), r.get("innings"), r["checkpoint"], r["kind"])

    def has(self, match_id, innings, checkpoint, kind) -> bool:
        return (str(match_id), innings, checkpoint, kind) in self.seen

    def has_match(self, match_id) -> bool:
        return any(k[0] == str(match_id) for k in self.seen)

    def write(self, rec: dict) -> bool:
        k = self._k(rec)
        if k in self.seen:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=float) + "\n")
        self.seen.add(k)
        self.count += 1
        return True


def line(kind, match, checkpoint, innings, state, outputs, url, flags=()) -> dict:
    return {"utc": now_utc(), "match_id": str(match["id"]), "series": match["series"], "team_a": match["team_a"], "team_b": match["team_b"],
            "venue": match["venue"], "innings": innings, "checkpoint": checkpoint, "kind": kind, "state": state, "outputs": outputs,
            "source_url": url, "model_hash": _hash[0], "logger_version": VERSION, "flags": list(flags)}


def model_hash() -> str:
    from ..ml.predict import MODEL_DIR

    per = {f: hashlib.sha256((MODEL_DIR / f).read_bytes()).hexdigest() for f in MODEL_FILES}
    (OUT / "model_hash.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "model_hash.json").write_text(json.dumps(per, indent=1), encoding="utf-8")
    return hashlib.sha256(json.dumps(per, sort_keys=True).encode()).hexdigest()


# ------------------------------------------------------------------ parsing
def checkpoints(payload: dict) -> dict[int, dict]:
    """Ends of overs 6, 10, 15 in one innings' commentary payload: {over: {runs, wickets, balls, ts (epoch s)}}.
    Uses the per-over summary item (overSeparator, overNum x.6 = end of over x+1); for overs 10 and 15 falls back to the
    'B0$ 99/3 (10), ...' summary line when ball-by-ball is not covered."""
    out = {}
    items = [x for c in payload.get("commentary", []) for x in c.get("commentaryList", [])]
    for x in items:
        s = x.get("overSeparator")
        if s and abs(s["overNum"] % 1 - 0.6) < 1e-6 and int(s["overNum"]) + 1 in OVERS:
            o = int(s["overNum"]) + 1
            out[o] = dict(runs=s["score"], wickets=s["wickets"], balls=o * 6, ts=(s.get("timestamp") or x["timestamp"]) / 1000)
    for x in items:
        m = re.match(r"B0\$ (\d+)/(\d+) \((\d+)\)", x.get("commText", ""))
        if m and int(m[3]) in OVERS and int(m[3]) != 6 and int(m[3]) not in out:
            out[int(m[3])] = dict(runs=int(m[1]), wickets=int(m[2]), balls=int(m[3]) * 6, ts=x["timestamp"] / 1000)
    return out


def list_series(sid: int) -> list[dict]:
    t = cs.get(f"/cricket-series/{sid}/x/matches").replace('\\"', '"')
    dec, seen = json.JSONDecoder(), {}
    for m in re.finditer('"matchInfo":', t):
        try:
            mi, _ = dec.raw_decode(t, m.end())
        except ValueError:
            continue
        if mi.get("seriesId") == sid:
            start = int(mi["startDate"]) / 1000
            seen[str(mi["matchId"])] = dict(id=str(mi["matchId"]), sid=sid, series=mi["seriesName"], start=start, state=mi["state"],
                                           team_a=mi["team1"]["teamName"], team_b=mi["team2"]["teamName"], venue=mi["venueInfo"]["ground"],
                                           date=(dt.datetime.fromtimestamp(start, dt.timezone.utc) + dt.timedelta(hours=5.5)).date().isoformat())
    return sorted(seen.values(), key=lambda r: (r["start"], r["id"]))


def fetch_comm(mid, inn) -> dict:
    return json.loads(cs.get(f"/api/mcenter/{mid}/full-commentary/{inn}"))


# ------------------------------------------------------------------ names
_known = {}


def known():
    if not _known:
        from ..ml import predict as P

        i = P._inn()
        s = i[(i.competition == COMP) & (i.gender == "male")]
        _known["teams"] = set(s.batting_team) | set(s.bowling_team)
        _known["venues"] = s.venue.value_counts()
    return _known


def map_team(name):
    k = known()["teams"]
    if name in k:
        return name, True
    a = TEAM_ALIAS.get(name.lower().replace("&", "and"))
    return (a, True) if a in k else (name, False)


def map_venue(name):
    vc = known()["venues"]
    if name in vc.index:
        return name, True
    key = lambda v: re.sub(r"[^a-z0-9]", "", v.split(",")[0].lower())  # noqa: E731
    hits = [v for v in vc.index if key(v) == key(name)]
    return (hits[0], True) if hits else (name, False)  # value_counts is sorted: the most used spelling wins


# ------------------------------------------------------------------ models
_F = {}


def build_f():
    import pandas as pd

    from ..ml import fair_report as FR

    s = FR.load()
    ipl = s.competition == "ipl"
    tab, ch = FR.fold_models(s, "all", pd.Series(True, index=s.index), ~ipl & (s.season_year == 2025), s.season_year < 2025)
    _F.update(tab=tab, ch=ch)


def f_values(innings, runs, wickets, balls, target, lvl_ew):
    import pandas as pd

    d = pd.DataFrame([dict(innings=innings, runs=runs, wickets=wickets, balls_bowled=balls, balls_left=120 - balls, lvl_ew=lvl_ew,
                           runs_needed=(target - runs) if target else 0)])
    if innings == 1:
        q = _F["tab"].score(d).iloc[0]
        return dict(q10=float(q.q10), q50=float(q.q50), q90=float(q.q90))
    return dict(win_bat=float(_F["ch"].win(d).iloc[0])) if target - runs > 0 else None


def predict_inplay(m, innings, bat, bowl, runs, wickets, balls, target):
    from ..ml import predict as P

    (vn, vok), (tb, tbok), (to, took) = map_venue(m["venue"]), map_team(bat), map_team(bowl)
    flags = [f for f, ok in (("unknown_venue", vok), ("unknown_team", tbok and took)) if not ok]
    r = P.predict_state(COMP, vn, tb, to, innings, runs, wickets, balls // 6 + (balls % 6) / 10, target=target, date=m["date"])
    out = {"p0": dict(**{k: float(v) for k, v in r["score"].items()}, win_bat=(r["win"] or {}).get("bat"))}
    try:
        t1, t2 = (tb, to) if innings == 1 else (to, tb)
        lv = P._live_levels(COMP, vn, t1, t2, m["date"])[0]
        out["f"] = f_values(innings, runs, wickets, balls, target, float(lv.loc[innings, "lvl_ew"]))
    except Exception as e:  # report, don't chase
        out["f"] = None
        flags.append("f_error")
        log(f"F error {m['id']}: {e!r}")
    return out, flags


def predict_prematch(m):
    from ..ml import prematch

    (vn, vok), (a, aok), (b, bok) = map_venue(m["venue"]), map_team(m["team_a"]), map_team(m["team_b"])
    flags = [f for f, ok in (("unknown_venue", vok), ("unknown_team", aok and bok)) if not ok]
    r = prematch.predict(COMP, vn, a, b, date=m["date"])
    return {"p_a_win": r["p_a_win"], "win_model": r["parts"]["win_model"]}, flags


# ------------------------------------------------------------------ one match
def poll_match(m, w: Writer, now: float):
    mid = m["id"]
    inn = m.get("inn", 1)
    d = fetch_comm(mid, inn)
    mini = d.get("matchDetails", {}).get("miniscore") or {}
    cur = mini.get("inningsId") or inn
    if cur != inn and cur in (1, 2):
        inn, d = cur, fetch_comm(mid, cur)
        mini = d.get("matchDetails", {}).get("miniscore") or mini
    m["inn"] = inn
    hdr = d.get("matchDetails", {}).get("matchHeader") or {}
    if hdr.get("complete") or hdr.get("state") == "Complete":
        write_result(m, d, w)
        m["done"] = True
        return
    sc = (mini.get("matchScoreDetails") or {}).get("inningsScoreList") or []
    bat_id = next((s["batTeamId"] for s in sc if s["inningsId"] == inn), None)
    names = {hdr["team1"]["id"]: hdr["team1"]["name"], hdr["team2"]["id"]: hdr["team2"]["name"]} if hdr.get("team1") else {}
    if bat_id not in names:
        return log(f"no batting team yet for {mid}")
    bat = names[bat_id]
    bowl = next(n for i, n in names.items() if i != bat_id)
    target = None
    if inn == 2:
        first = next((s["score"] for s in sc if s["inningsId"] == 1), None)
        target = mini.get("target") or (first + 1 if first is not None else None)
        if not target:
            return log(f"no target yet for {mid}")
    url = cs.BASE + f"/api/mcenter/{mid}/full-commentary/{inn}"
    for o, c in sorted(checkpoints(d).items()):
        cp = f"over{o}"
        if w.has(mid, inn, cp, "inplay"):
            continue
        lag = now - c["ts"]
        if lag > MAX_LAG:
            continue  # missed: never filled in
        out, flags = predict_inplay(m, inn, bat, bowl, c["runs"], c["wickets"], c["balls"], target)
        rec = line("inplay", m, cp, inn, dict(runs=c["runs"], wickets=c["wickets"], balls=c["balls"], target=target, batting_team=bat), out, url, flags)
        rec["outputs"]["lag_s"] = round(lag)
        w.write(rec)


def write_result(m, d, w: Writer):
    mid = m["id"]
    if w.has(mid, None, "result", "result") or not (m.get("tracked") or w.has_match(mid)):
        return
    hdr = d.get("matchDetails", {}).get("matchHeader") or {}
    sc = ((d.get("matchDetails", {}).get("miniscore") or {}).get("matchScoreDetails") or {}).get("inningsScoreList") or []
    res = hdr.get("result") or {}
    why = hdr.get("status", "") + (hdr.get("revisedTarget") or {}).get("reason", "")
    out = dict(innings=[dict(innings=s["inningsId"], team=s["batTeamName"], runs=s["score"], wickets=s["wickets"], overs=s["overs"]) for s in sorted(sc, key=lambda s: s["inningsId"])],
               winner=res.get("winningTeam"), result_type=res.get("resultType"), margin=res.get("winningMargin"), by_runs=res.get("winByRuns"),
               method="VJD/DLS" if re.search(r"vjd|v\.?j\.?d|dls|d/l", why, re.I) else None, status=hdr.get("status"))
    w.write(line("result", m, "result", None, {}, out, cs.BASE + f"/api/mcenter/{mid}/full-commentary/{m.get('inn', 1)}"))


# ------------------------------------------------------------------ main loop
def run():
    OUT.mkdir(parents=True, exist_ok=True)
    w = Writer(PRED)
    log(f"start logger v{VERSION}")
    ms: dict[str, dict] = {}
    refresh(ms, first=True)
    _hash[0] = model_hash()
    known()
    build_f()
    log(f"ready model_hash={_hash[0][:12]}")
    next_list, blocked = time.time() + LIST_EVERY, 0
    while True:
        try:
            now = time.time()
            if now >= next_list:
                refresh(ms)
                next_list = now + LIST_EVERY
            polled = 0
            for m in sorted(ms.values(), key=lambda r: r["start"]):
                now = time.time()
                if m.get("done") or m["state"] == "Complete" and not m.get("tracked"):
                    continue
                if m["state"].lower() in ("upcoming", "preview", "toss") and now <= m["start"] <= now + PRE_WINDOW:
                    if not w.has(m["id"], None, "prematch", "prematch"):
                        out, flags = predict_prematch(m)
                        w.write(line("prematch", m, "prematch", None, {}, out, cs.BASE + f"/cricket-series/{m['sid']}/x/matches", flags))
                        m["tracked"] = True
                elif m["start"] - 300 <= now <= m["start"] + 9 * 3600 and m["state"] != "Complete" or m.get("tracked") and m["state"] == "Complete":
                    if now >= m.get("next", 0):
                        m["tracked"] = True
                        poll_match(m, w, now)
                        m["next"] = time.time() + POLL
                        polled += 1
            live = sum(1 for m in ms.values() if not m.get("done") and m["state"] != "Complete" and m["start"] - 300 <= time.time() <= m["start"] + 9 * 3600)
            if polled:
                log(f"seen={len(ms)} live={live} lines_written={w.count} requests={cm.requests_made[0]}")
            blocked = 0
            time.sleep(5)
        except cm.Blocked as e:
            blocked += 1
            if blocked > 1:
                log(f"BLOCKED twice ({e}); exiting. Restart by hand later.")
                sys.exit(f"Cricbuzz blocked the logger twice ({e}). Exiting.")
            log(f"BLOCKED ({e}); backing off 15 min")
            time.sleep(900)
        except KeyboardInterrupt:
            log("stopped by user")
            return
        except Exception:
            log("ERROR " + traceback.format_exc().replace("\n", " | ")[-600:])
            time.sleep(30)


def refresh(ms, first=False):
    for sid in SERIES:
        for m in list_series(sid):
            old = ms.get(m["id"])
            if old:
                old.update(state=m["state"], start=m["start"])
            else:
                ms[m["id"]] = m
                if first and m["state"] == "Complete":
                    m["done"] = True  # finished before we looked: nothing to log
    log(f"series list refreshed: seen={len(ms)}")


if __name__ == "__main__":
    if sys.argv[1:] != ["run"]:
        sys.exit("usage: python -m cricket_analytics.live.smat_logger run")
    run()
