"""Reels-facing SMAT 2025-26 scouting: resolve, facts JSON, ranked list. Reads the CSVs/parquets that smat2025.py writes."""
import datetime as dt
import json

import pandas as pd

from ..facts import _flatten, _fmt
from .smat2025 import ROOT

SOURCE = "Cricbuzz scorecards, Syed Mushtaq Ali Trophy 2025-26"


class NotExact(ValueError):
    def __init__(self, msg, candidates):
        self.candidates = candidates
        super().__init__(msg)


def table(role: str) -> pd.DataFrame:
    """Scouting CSV with rank_uncapped (rank by score among uncapped) added; the CSV is already sorted by score."""
    t = pd.read_csv(ROOT / f"scouting_{'batters' if role == 'bat' else 'bowlers'}.csv", keep_default_na=False, na_values=[""])
    u = t.t20i == "uncapped"
    t["rank_uncapped"] = u.cumsum().where(u)
    t["name_match"] = t.match.map({"team": "team", "name": "name_only", "initials": "name_only"}).fillna("none")
    return t


def _label(r) -> str:
    return f"{r['name']} ({r['team']}, id {int(r['cricbuzz_id'])})"


def candidates(name: str, limit: int = 8) -> list[dict]:
    q = name.lower().strip()
    rows = []
    for role in ("bat", "bowl"):
        for _, r in table(role).iterrows():
            n = r["name"].lower()
            hit = q == n or q in n or any(w in n for w in q.split() if len(w) > 2)
            if hit:
                rows.append(dict(cricbuzz_id=int(r.cricbuzz_id), name=r["name"], team=r.team, role=role,
                                 exact=q == n or q == str(int(r.cricbuzz_id)), _s=(q == n, q in n)))
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r.pop("_s"), reverse=True):
        if r["cricbuzz_id"] not in seen:
            seen.add(r["cricbuzz_id"])
            out.append(r)
    return out[:limit]


def resolve(name: str) -> dict:
    """Exact (case-insensitive) name or cricbuzz_id -> one candidate; else NotExact with candidates."""
    c = candidates(name, 50)
    ex = [r for r in c if r["exact"]]
    if len(ex) == 1:
        return ex[0]
    cands = ex or c
    raise NotExact(f"{name!r} is " + ("ambiguous" if ex else "not an exact name") + "; use the exact name or the cricbuzz_id", cands[:8])


def _games() -> pd.DataFrame:
    return pd.read_parquet(ROOT / "matches.parquet")


def _best(pid: int, role: str, n: int = 3) -> list[dict]:
    m = _games().set_index("match_id")
    if role == "bat":
        d = pd.read_parquet(ROOT / "batting.parquet")
        d = d[d.cricbuzz_id == pid]
        d = d.assign(_sr=d.runs / d.balls.clip(lower=1)).sort_values(["runs", "_sr"], ascending=False)
    else:
        d = pd.read_parquet(ROOT / "bowling.parquet")
        d = d[d.cricbuzz_id == pid].sort_values(["wickets", "runs"], ascending=[False, True])
    out = []
    for _, r in d.head(n).iterrows():
        g = m.loc[r.match_id]
        o = dict(opponent=g.team2 if g.team1 == r.team else g.team1, date=str(g.date)[:10], venue=g.venue,
                 result=g.status, match_id=str(int(r.match_id)))
        if role == "bat":
            o |= dict(runs=int(r.runs), balls=int(r.balls), fours=int(r.fours), sixes=int(r.sixes))
        else:
            o |= dict(wkts=int(r.wickets), runs=int(r.runs), overs=float(r.overs))
        out.append(o)
    return out


def league() -> dict:
    b, w = pd.read_parquet(ROOT / "batting.parquet"), pd.read_parquet(ROOT / "bowling.parquet")
    return dict(sr=round(b.runs.sum() / b.balls.sum() * 100, 1), econ=round(w.runs.sum() / w.balls.sum() * 6, 2))


def build_facts(name: str, role: str | None = None) -> dict:
    c = resolve(name)
    role = role or c["role"]
    t = table(role)
    rows = t[t.cricbuzz_id == c["cricbuzz_id"]]
    if rows.empty:
        raise NotExact(f"{c['name']} is not in the {role} table (min 100 balls / 12 overs)", [c])
    r = rows.iloc[0]
    lg = league()
    keys = (["team", "inns", "runs", "balls", "avg", "sr", "fifties", "hundreds", "boundary_pct", "band", "score",
             "ipl_sr_est", "smat_earlier"] if role == "bat" else
            ["team", "wkts", "overs", "econ", "avg", "score", "ipl_econ_est", "smat_earlier"])
    sc = {k: r[k].item() if hasattr(r[k], "item") else r[k] for k in keys if k in r.index and pd.notna(r[k]) and r[k] != ""}
    if "smat_earlier" in sc:
        sc["smat_hist"] = sc.pop("smat_earlier")
    sc["score_name"] = "runs above average" if role == "bat" else "runs saved"
    sc.update(cricbuzz_id=str(int(r.cricbuzz_id)), name=r["name"], name_match=r.name_match, t20i=r.t20i)
    if role == "bat":
        sc["league_sr"] = lg["sr"]
    else:
        sc.update(league_econ=lg["econ"], runs_saved=sc["score"])
    if r.name_match != "none":
        sc["ipl_status"] = r.ipl_status
    if pd.notna(r.rank_uncapped):
        sc.update(rank_uncapped=int(r.rank_uncapped), of_uncapped=int((t.t20i == "uncapped").sum()))
    facts = {"scout": sc, "best": {str(i): b for i, b in enumerate(_best(int(r.cricbuzz_id), role), 1)}}
    raw: dict = {}
    _flatten(facts, "", raw)
    caveats = ["Small samples: at most 11 innings per player; a shortlist, not a verdict.",
               "Cricbuzz scorecards, not ball-by-ball. 'uncapped' = no men's T20I in the Cricsheet DB (ODI/Test caps not covered)."]
    if r.plate:
        caveats.append("Plate-group player: weaker opposition, discount the numbers.")
    if r.name_match == "name_only":
        caveats.append("IPL/T20I status matched by name only (not team history): do not claim 'no IPL contract'.")
    if r.name_match == "none":
        caveats.append("Name not matched to Cricsheet: IPL/T20I status unknown.")
    meta = dict(facts_version=2, kind="scouting_smat2025", player=r["name"], role="batting" if role == "bat" else "bowling",
                params=dict(scouting="smat2025", player=name), generated=dt.datetime.now().isoformat(timespec="seconds"),
                data_through=str(_games().date.max())[:10], source=SOURCE, caveats=caveats, plate=bool(r.plate))
    return dict(meta=meta, facts=facts, tokens={k: _fmt(v) for k, v in raw.items()}, tokens_raw=raw)


def listing(role: str, uncapped=False, no_ipl=False, top: int = 15) -> dict:
    t = table(role)
    if uncapped:
        t = t[t.t20i == "uncapped"]
    if no_ipl:
        t = t[t.ipl_status == "no IPL record"]
    cols = ["cricbuzz_id", "name", "team", "rank_uncapped", "score", "t20i", "ipl_status", "name_match", "plate"] + (
        ["inns", "runs", "balls", "avg", "sr", "boundary_pct", "band"] if role == "bat" else ["inns", "overs", "wkts", "econ", "avg", "sr"])
    d = t.head(top)[cols].copy()
    d["rank_uncapped"] = d.rank_uncapped.astype("Int64")
    return dict(meta=dict(scouting="smat2025", role=role, uncapped=uncapped, no_ipl=no_ipl, row_count=len(d), data_through=str(_games().date.max())[:10],
                          source=SOURCE, note="name_match 'name_only' rows: IPL status is a name guess, don't claim 'no IPL contract'."),
                data=json.loads(d.to_json(orient="records")))
