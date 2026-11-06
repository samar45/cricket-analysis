"""League translation factors (other competition -> IPL) and the uncapped scouting preview.

Method: for each player with >=200 balls in the source competition AND >=200 in the IPL within +-1 calendar year of
each other, factor = (sum of the player's real IPL events) / (sum of what their source-competition rate predicts for
the same IPL balls). Players are weighted by their IPL balls; 95% interval = bootstrap over players (2000 draws).
Run: python -m cricket_analytics.models.league_translation <db>
"""

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

SOURCES = ["smat", "sa20", "t20i", "bbl", "psl", "cpl", "blast"]
MIN_BALLS = 200
WICKET_COST = 20.0  # assumption: runs a wicket is worth when scoring "value" for the scouting list
DATA = Path(__file__).parent / "data"
OUT = DATA / "league_translation.csv"

# one row per (player, competition, year, role). Super overs excluded, men only, 100-ball Hundred excluded.
SQL = """
WITH d AS (
  SELECT m.competition AS comp, year(m.date) AS yr, d.*
  FROM deliveries d JOIN matches m USING (match_id)
  WHERE m.gender='male' AND d.innings <= 2 AND m.competition <> 'hundred')
SELECT 'bat' AS role, batter AS player, comp, yr,
       COUNT(*) AS balls,
       SUM(runs_batter) AS runs,
       SUM(CASE WHEN player_out = batter AND wicket_type NOT IN ('retired hurt','retired not out','retired out') THEN 1 ELSE 0 END) AS wkts,
       SUM(CASE WHEN runs_batter = 0 THEN 1 ELSE 0 END) AS dots,
       SUM(CASE WHEN runs_batter IN (4,6) THEN 1 ELSE 0 END) AS bounds
FROM d WHERE COALESCE(wides,0) = 0 GROUP BY ALL
UNION ALL
SELECT 'bowl', bowler, comp, yr,
       SUM(CASE WHEN COALESCE(wides,0) = 0 AND COALESCE(noballs,0) = 0 THEN 1 ELSE 0 END),
       SUM(runs_batter + COALESCE(noballs,0) + COALESCE(wides,0)),
       SUM(CASE WHEN wicket_type IN ('bowled','caught','caught and bowled','lbw','stumped','hit wicket') THEN 1 ELSE 0 END),
       SUM(CASE WHEN COALESCE(wides,0) = 0 AND COALESCE(noballs,0) = 0 AND runs_batter = 0 THEN 1 ELSE 0 END),
       SUM(CASE WHEN runs_batter IN (4,6) THEN 1 ELSE 0 END)
FROM d GROUP BY ALL
"""
METRICS = {
    "bat": [("runs_per_ball", "runs"), ("dismissal_rate", "wkts"), ("dot_pct", "dots"), ("boundary_pct", "bounds")],
    "bowl": [("runs_per_ball", "runs"), ("wicket_rate", "wkts"), ("dot_pct", "dots"), ("boundary_pct", "bounds")],
}


def load(db: str) -> pd.DataFrame:
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute(SQL).df()
    finally:
        con.close()


def paired(df: pd.DataFrame, role: str, src: str) -> pd.DataFrame:
    """Per player: source events/balls and IPL events/balls, restricted to years within +-1 of each other."""
    a = df[(df.role == role) & (df.comp == src)]
    i = df[(df.role == role) & (df.comp == "ipl")]
    ig = dict(list(i.groupby("player")))
    rows = []
    for p, ga in a.groupby("player"):
        gi = ig.get(p)
        if gi is None:
            continue
        sy, iy = set(ga.yr), set(gi.yr)
        ga = ga[[any(abs(y - z) <= 1 for z in iy) for y in ga.yr]]
        gi = gi[[any(abs(y - z) <= 1 for z in sy) for y in gi.yr]]
        if ga.balls.sum() >= MIN_BALLS and gi.balls.sum() >= MIN_BALLS:
            r = {"player": p, "sb": ga.balls.sum(), "ib": gi.balls.sum()}
            for c in ("runs", "wkts", "dots", "bounds"):
                r["s_" + c], r["i_" + c] = ga[c].sum(), gi[c].sum()
            rows.append(r)
    return pd.DataFrame(rows)


def factor(p: pd.DataFrame, col: str, rng) -> tuple[float, float, float]:
    num = p["i_" + col].to_numpy(float)
    den = (p["s_" + col] / p.sb * p.ib).to_numpy(float)
    n = len(p)
    bs = []
    for _ in range(2000):
        k = rng.integers(0, n, n)
        bs.append(num[k].sum() / den[k].sum())
    return num.sum() / den.sum(), *np.percentile(bs, [2.5, 97.5])


def translation(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    out = []
    for src in SOURCES:
        for role in ("bat", "bowl"):
            p = paired(df, role, src)
            if len(p) < 8:
                continue
            for name, col in METRICS[role]:
                f, lo, hi = factor(p, col, rng)
                out.append(dict(source=src, role=role, metric=name, factor=round(f, 3), ci_lo=round(lo, 3),
                                ci_hi=round(hi, 3), n_players=len(p), source_balls=int(p.sb.sum()), ipl_balls=int(p.ib.sum())))
    return pd.DataFrame(out)


def scouting(df, tr, contracts, since=2020, prior=150, top=20) -> pd.DataFrame:
    """Shrunk, translated value per 100 balls (runs above the IPL average) for players with few IPL balls."""
    f = tr[tr.source == "smat"].set_index(["role", "metric"]).factor
    ipl = df[df.comp == "ipl"]
    ipl_all = ipl.groupby("player").balls.sum()
    t20i_all = df[df.comp == "t20i"].groupby("player").balls.sum()
    rows = []
    for role in ("bat", "bowl"):
        s = df[(df.role == role) & (df.comp == "smat") & (df.yr >= since)].groupby("player")[["balls", "runs", "wkts"]].sum()
        s = s[s.balls >= 150]
        im = ipl[ipl.role == role]
        T = im[["balls", "runs", "wkts"]].sum()
        rpb, wr = T.runs / T.balls, T.wkts / T.balls
        mr, mw = s.runs.sum() / s.balls.sum(), s.wkts.sum() / s.balls.sum()
        sr = (s.runs + prior * mr) / (s.balls + prior)  # shrink toward the SMAT mean
        sw = (s.wkts + prior * mw) / (s.balls + prior)
        if role == "bat":
            val = (sr * f[("bat", "runs_per_ball")] - rpb) - (sw * f[("bat", "dismissal_rate")] - wr) * WICKET_COST
        else:
            val = (rpb - sr * f[("bowl", "runs_per_ball")]) + (sw * f[("bowl", "wicket_rate")] - wr) * WICKET_COST
        r = pd.DataFrame({"role": role, "smat_balls": s.balls, "smat_rpb": s.runs / s.balls,
                          "smat_wkt_per_ball": s.wkts / s.balls, "value_per_100": val * 100}).reset_index()
        rows.append(r)
    r = pd.concat(rows)
    r["ipl_balls_all"] = r.player.map(ipl_all).fillna(0).astype(int)
    r["t20i_balls_all"] = r.player.map(t20i_all).fillna(0).astype(int)
    r = r[r.ipl_balls_all <= 100]  # "few IPL balls" = under 17 overs, both roles together
    sq = contracts[contracts.status_2027 == "in_squad"].drop_duplicates("cricsheet_name").set_index("cricsheet_name")
    r["ipl_squad_2027"] = r.player.map(sq.team).fillna("")
    r["overseas"] = r.player.map(sq.overseas).fillna("")
    return r.sort_values("value_per_100", ascending=False).head(top)


if __name__ == "__main__":
    df = load(sys.argv[1])
    tr = translation(df)
    DATA.mkdir(exist_ok=True)
    tr.to_csv(OUT, index=False)
    print(tr.to_string())
    c = pd.read_csv(Path(__file__).parents[1] / "reference" / "ipl_contracts.csv")
    sc = scouting(df, tr, c, top=20)
    sc.to_csv(DATA / "scouting_preview_smat.csv", index=False)
    print(sc.round(3).to_string())
