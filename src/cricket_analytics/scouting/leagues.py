"""One-league analytics for the Cricbuzz state leagues. Reuses profile._cb (per-innings rows, season = match year, cutoff applied).

`key` is the folder name ("state_spl"); `seasons` is a list of years or None for all.
"""

import functools
import glob

import pandas as pd

from . import profile as P

SHORT = {"spl": "Sher-e-Punjab", "upt20": "UP T20", "cgpl": "Chhattisgarh Premier League"}  # others: P.STATE names


def _name(key: str) -> str:
    k = key.removeprefix("state_")
    return SHORT.get(k) or P.STATE.get(k, k)


@functools.lru_cache(maxsize=1)
def _data():
    b, w = P._cb("batting"), P._cb("bowling")
    m = pd.concat([pd.read_parquet(f).assign(_k=f.replace("\\", "/").split("/")[-3]) for f in glob.glob(str(P.CB / "state_*" / "*" / "matches.parquet"))])
    m = m.drop_duplicates("match_id")
    m["season"] = pd.to_datetime(m.date).dt.year
    m = m[pd.to_datetime(m.date) < P.CUTOFF]
    inn = pd.concat([pd.read_parquet(f) for f in glob.glob(str(P.CB / "state_*" / "*" / "innings.parquet"))])
    keymap = m.set_index("match_id")["_k"]
    for d in (b, w):
        d["key"] = d.match_id.map(keymap)
        d["season"] = d.season.astype(int)
    return b[b.key.notna()], w[w.key.notna()], m, inn


def _sel(df, key, seasons):
    df = df[df.key == key] if "key" in df else df[df._k == key]
    return df if not seasons else df[df.season.isin([int(s) for s in seasons])]


def leagues() -> list[tuple[str, str, list[int]]]:
    m = _data()[2]
    return sorted(((k, _name(k), sorted(g.season.unique().tolist())) for k, g in m.groupby("_k")), key=lambda x: x[1])


def league_batting(key, seasons=None) -> pd.DataFrame:
    b = _sel(_data()[0], key, seasons)
    b = b.assign(f50=(b.runs >= 50) & (b.runs < 100), f100=b.runs >= 100)
    t = b.groupby("cricbuzz_id").agg(name=("name", P._mode), team=("team", P._mode), inns=("runs", "size"), runs=("runs", "sum"), balls=("balls", "sum"),
                                     outs=("is_out", "sum"), fours=("fours", "sum"), sixes=("sixes", "sum"), fifties=("f50", "sum"),
                                     hundreds=("f100", "sum"), hs=("runs", "max")).reset_index(drop=True)
    t["avg"] = (t.runs / t.outs.replace(0, float("nan"))).round(1)
    t["sr"] = (t.runs / t.balls.replace(0, float("nan")) * 100).round(1)
    return t.drop(columns="outs").sort_values(["runs", "sr"], ascending=False, ignore_index=True)


def league_bowling(key, seasons=None) -> pd.DataFrame:
    w = _sel(_data()[1], key, seasons)
    best = w.sort_values(["wickets", "runs"], ascending=[False, True]).groupby("cricbuzz_id").first()
    t = w.groupby("cricbuzz_id").agg(name=("name", P._mode), team=("team", P._mode), inns=("balls", "size"), balls=("balls", "sum"),
                                     conceded=("runs", "sum"), wkts=("wickets", "sum"))
    t["best"] = best.wickets.astype(int).astype(str) + "/" + best.runs.astype(int).astype(str)
    t["overs"] = (t.balls // 6 + t.balls % 6 / 10).round(1)
    t["econ"] = (t.conceded / t.balls.replace(0, float("nan")) * 6).round(2)
    t["avg"] = (t.conceded / t.wkts.replace(0, float("nan"))).round(1)
    t["sr"] = (t.balls / t.wkts.replace(0, float("nan"))).round(1)  # balls per wicket
    return t.reset_index(drop=True).drop(columns="conceded").sort_values(["wkts", "econ"], ascending=[False, True], ignore_index=True)


def league_teams(key, seasons=None) -> pd.DataFrame:
    """played = matches a side was listed in; lost = a winner exists and it is the other side; nr = no winner recorded (abandoned / no result)."""
    m = _sel(_data()[2], key, seasons)
    rows = pd.concat([m[["match_id", "team1", "winner"]].rename(columns={"team1": "team"}), m[["match_id", "team2", "winner"]].rename(columns={"team2": "team"})])
    rows["won"] = rows.winner == rows.team
    rows["nr"] = rows.winner.fillna("") == ""
    rows["lost"] = ~rows.won & ~rows.nr
    t = rows.groupby("team").agg(played=("match_id", "size"), won=("won", "sum"), lost=("lost", "sum"), nr=("nr", "sum")).astype(int)
    return t.sort_values(["won", "played"], ascending=[False, True]).reset_index()


def league_summary(key, seasons=None) -> dict:
    b, w, m, inn = _data()
    m = _sel(m, key, seasons)
    i = inn[inn.match_id.isin(m.match_id)]
    bt, bw = league_batting(key, seasons), league_bowling(key, seasons)
    first = i[i.innings == 1].runs
    return {"matches": len(m), "seasons": sorted(m.season.unique().tolist()), "total_runs": int(i[i.innings <= 2].runs.sum()),
            "avg_first_innings": round(float(first.mean()), 1) if len(first) else None,
            "top_scorer": f"{bt.iloc[0]['name']} ({int(bt.iloc[0]['runs'])})" if len(bt) else "-",
            "top_wicket_taker": f"{bw.iloc[0]['name']} ({int(bw.iloc[0]['wkts'])})" if len(bw) else "-"}
