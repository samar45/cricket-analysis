"""Wins Above Replacement (WAR) and projected WAR (pWAR) from Runs Added.

Per player, season, league: batting and bowling Runs Added (models/run_expectancy.py, shortened matches included), each split
into a scoring part (runs and balls used up) and a wicket part. WAR = (runs added - replacement rate x balls) / runs per win.
Replacement rate, runs per win, and the projection settings are fitted and kept in models/data/war_params.json.

Rebuild:  python -m cricket_analytics.models.war            (fit + write pwar CSV)
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .. import competitions
from ..db import query
from ..sql.filters import Filters
from .run_expectancy import BALL_COLS, USABLE, load, ra_state

DATA = Path(__file__).parent / "data"
PARAMS = DATA / "war_params.json"
# men's leagues + men's T20Is feed the projection (a league's own average is 0 by construction)
LEAGUES = ["ipl", "bbl", "psl", "cpl", "sa20", "hundred", "blast", "t20i"]
SEASON_COLS = ["comp", "sy", "season", "team", "player", "role", "balls", "runs", "wkts", "sc", "wk"]


def _int_cols(df):
    for c in ("wickets_before", "b", "score_before", "legal", "wk", "striker_out", "bowler_wk", "faced"):
        df[c] = df[c].astype("int64")
    return df


def season_table(comp: str, db_path=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player-season-team rows, appearances) for one competition key.

    Rows: comp, sy (calendar year the season ended), season (label), team, player, role (bat/bowl), balls (faced / legal
    bowled), runs (off the bat / conceded), sc (scoring part of runs added), wk (wicket part), with sc + wk = runs added.
    Appearances: comp, sy, team, player, matches (matches in which he batted, was non-striker, or bowled)."""
    f = Filters(competition=comp)
    st, sp = ra_state(f)
    sql = (
        f"WITH d AS ({st}) SELECT {BALL_COLS}, d.batting_team, d.bowling_team, d.non_striker, m.date, m.season "
        f"FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE}"
    )
    rows = _int_cols(query(sql, sp, db_path=db_path))
    if rows.empty:
        return pd.DataFrame(columns=SEASON_COLS), pd.DataFrame(columns=["comp", "sy", "team", "player", "matches"])
    a = load().annotate(rows)
    sy = a.groupby("season").date.max().dt.year
    a["sy"] = a.season.map(sy).astype(int)
    key = ["comp", "sy", "season", "team", "player", "role"]
    a["comp"] = comp
    s = (a.faced == 1) | (a.striker_out == 1)
    bs = a[s]
    bat_s = pd.DataFrame(
        dict(
            comp=comp, sy=bs.sy, season=bs.season, team=bs.batting_team, player=bs.batter, role="bat",
            balls=bs.faced, runs=bs.runs_batter * bs.faced, wkts=0,
            sc=bs.runs_batter + bs.vf * bs.ball_part + bs.bat_k, wk=bs.vf * bs.wkt_part * bs.striker_out,
        )
    )
    ns = a[(a.wk == 1) & (a.striker_out == 0)]
    bat_n = pd.DataFrame(
        dict(
            comp=comp, sy=ns.sy, season=ns.season, team=ns.batting_team, player=ns.player_out, role="bat",
            balls=0, runs=0, wkts=0, sc=0.0, wk=ns.vf * ns.wkt_part,
        )
    )
    bow = pd.DataFrame(
        dict(
            comp=comp, sy=a.sy, season=a.season, team=a.bowling_team, player=a.bowler, role="bowl",
            balls=a.legal, runs=a.conceded, wkts=a.bowler_wk,
            sc=-a.conceded - a.vf * a.ball_part + a.bowl_k, wk=-a.vf * a.wkt_part * a.bowler_wk,
        )
    )
    out = pd.concat([bat_s, bat_n, bow]).groupby(key, as_index=False)[["balls", "runs", "wkts", "sc", "wk"]].sum()
    pres = pd.concat(
        [
            a[["match_id", "sy", "batting_team", "batter"]].set_axis(["match_id", "sy", "team", "player"], axis=1),
            a[["match_id", "sy", "batting_team", "non_striker"]].set_axis(["match_id", "sy", "team", "player"], axis=1),
            a[["match_id", "sy", "bowling_team", "bowler"]].set_axis(["match_id", "sy", "team", "player"], axis=1),
        ]
    ).drop_duplicates()
    app = pres.groupby(["sy", "team", "player"], as_index=False).size().rename(columns={"size": "matches"})
    app.insert(0, "comp", comp)
    return out[SEASON_COLS], app


# --------------------------------------------------------------------------- tables
def centre(rows: pd.DataFrame) -> pd.DataFrame:
    """Make the league-season average player exactly 0 per ball (batting and bowling separately): the shipped offsets are fitted
    on first innings; chases, short matches and other leagues leave a small drift (up to 3 runs per 100 balls in T20Is)."""
    g = rows.groupby(["comp", "sy", "role"])
    mu = (g.sc.transform("sum") + g.wk.transform("sum")) / g.balls.transform("sum")
    out = rows.copy()
    out["sc"] = out.sc - mu * out.balls
    return out


@lru_cache(maxsize=2)
def all_tables(leagues: tuple = tuple(LEAGUES)):
    """{comp: centred rows}, {comp: appearances}. About 15 s for all leagues."""
    rows, apps = {}, {}
    for c in leagues:
        r, a = season_table(c)
        rows[c], apps[c] = r, a
    cen = centre(pd.concat(rows.values(), ignore_index=True))
    return {c: g for c, g in cen.groupby("comp")}, apps


def player_year(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.groupby(["role", "player", "sy"], as_index=False)[["balls", "runs", "wkts", "sc", "wk"]].sum()


class Panel:
    """Wide matrices (player x year) of balls / sc / wk for IPL (`I`) and every other league pooled (`O`)."""

    def __init__(self, ipl: pd.DataFrame, other: pd.DataFrame, y0=2008, y1=2027):
        self.years = list(range(y0, y1 + 1))
        ip, op = player_year(ipl), player_year(other)
        self.players = sorted(set(ip.player) | set(op.player))
        self.M = {}
        for tag, df in (("I", ip), ("O", op)):
            for role in ("bat", "bowl"):
                d = df[df.role == role]
                for col in ("balls", "runs", "wkts", "sc", "wk"):
                    x = d.pivot(index="player", columns="sy", values=col) if len(d) else pd.DataFrame()
                    self.M[tag, role, col] = x.reindex(index=self.players, columns=self.years).fillna(0.0)

    def g(self, tag, role, col, y):
        return self.M[tag, role, col][y].values


def _evidence(P: Panel, role: str, col: str, t: int, a: float, s: float, ipl_from: int, pre_w: float, window=5):
    num, den = 0.0, 0.0
    for y in range(max(P.years[0], t - window), t):
        wy = 1.0 if y >= ipl_from else pre_w
        n_i, n_o = P.g("I", role, "balls", y), P.g("O", role, "balls", y)
        num = num + wy * P.g("I", role, col, y) + a * s * P.g("O", role, col, y)
        den = den + wy * n_i + a * n_o
    return num, den


def project_rate(P: Panel, role: str, t: int, prm: dict) -> tuple[np.ndarray, np.ndarray]:
    """Projected (scoring, wicket) runs added per ball for season t from earlier seasons only, and the evidence balls."""
    k1, k2 = prm["k"][role]
    nsc, den = _evidence(P, role, "sc", t, prm["a"], prm["s"], prm["ipl_from"], prm["pre_w"])
    nwk, _ = _evidence(P, role, "wk", t, prm["a"], prm["s"], prm["ipl_from"], prm["pre_w"])
    return nsc / (den + k1), nwk / (den + k2), den


def _prior_balls(P: Panel, role: str, t: int, ipl_from: int) -> np.ndarray:
    """IPL balls in the last three seasons (seasons before ipl_from count 0) as columns b1, b2, b3."""
    return np.column_stack(
        [P.g("I", role, "balls", t - L) if (t - L >= ipl_from and t - L >= P.years[0]) else np.zeros(len(P.players)) for L in (1, 2, 3)]
    )


def fit_balls(P: Panel, role: str, targets, ipl_from: int) -> np.ndarray:
    """OLS: balls in season t on [1, b1, mean(b2,b3)] for players with any IPL balls in the 3 prior seasons (zeros kept)."""
    X, y = [], []
    for t in targets:
        b = _prior_balls(P, role, t, ipl_from)
        m = b.sum(1) > 0
        X.append(np.column_stack([np.ones(m.sum()), b[m, 0], b[m, 1:].mean(1)]))
        y.append(P.g("I", role, "balls", t)[m])
    coef, *_ = np.linalg.lstsq(np.vstack(X), np.concatenate(y), rcond=None)
    return coef


def exp_balls(P: Panel, role: str, t: int, coef, ipl_from: int, any_hist: np.ndarray) -> np.ndarray:
    b = _prior_balls(P, role, t, ipl_from)
    e = coef[0] + coef[1] * b[:, 0] + coef[2] * b[:, 1:].mean(1)
    return np.where(any_hist, np.clip(e, 0, None), 0.0)


def loss(P: Panel, role: str, targets, prm: dict, minb=60) -> float:
    err = wt = 0.0
    for t in targets:
        n = P.g("I", role, "balls", t)
        sc, wk, den = project_rate(P, role, t, prm)
        m = (n >= minb) & (den > 0)
        y = (P.g("I", role, "sc", t) + P.g("I", role, "wk", t)) / np.where(n > 0, n, np.nan)
        err += (((y - sc - wk) ** 2) * n)[m].sum()
        wt += n[m].sum()
    return float((err / wt) ** 0.5)


KGRID = (400, 800, 1600, 3000, 6000)


def fit_k(P: Panel, role: str, targets, base: dict) -> tuple[list, float]:
    best = None
    for k1 in KGRID:
        for k2 in KGRID:
            v = loss(P, role, targets, {**base, "k": {**base.get("k", {}), role: [k1, k2]}})
            if best is None or v < best[0]:
                best = (v, [k1, k2])
    return best[1], best[0]


# --------------------------------------------------------------------------- runs per win, replacement, WAR
ERA_IPL = 2023  # Impact Player era: IPL numbers for the current game use these seasons only
IPL_PRE_LABEL, IPL_NOW_LABEL = "pre", "2023"


def era_key(sy) -> str:
    return IPL_NOW_LABEL if sy >= ERA_IPL else IPL_PRE_LABEL


def team_seasons(db_path=None) -> pd.DataFrame:
    """One row per IPL team-season: matches decided (no D/L, ties, no result), win share, mean run margin per match with
    every innings scaled to 120 balls (a chase won with balls to spare would otherwise understate the winner's runs)."""
    df = query(
        """SELECT m.match_id, year(m.date) yr, m.winner, d.innings, d.batting_team bt, SUM(d.runs_total) runs,
                  SUM(CASE WHEN d.wides = 0 AND d.noballs = 0 THEN 1 ELSE 0 END) lb
           FROM deliveries d JOIN matches m ON d.match_id = m.match_id
           WHERE m.competition = 'ipl' AND m.gender = 'male' AND d.innings <= 2 AND m.result IN ('runs', 'wickets')
             AND COALESCE(m.outcome_method, '') <> 'D/L' GROUP BY ALL""",
        db_path=db_path,
    )
    df["runs"] = df.runs * 120 / df.lb.clip(lower=1)
    p = df.pivot_table(index=["match_id", "yr", "winner"], columns="innings", values=["runs", "bt"], aggfunc="first").reset_index()
    p.columns = ["match_id", "yr", "winner", "bt1", "bt2", "r1", "r2"]
    a = pd.DataFrame({"yr": p.yr, "team": p.bt1, "rd": p.r1 - p.r2, "win": (p.winner == p.bt1).astype(int)})
    b = pd.DataFrame({"yr": p.yr, "team": p.bt2, "rd": p.r2 - p.r1, "win": (p.winner == p.bt2).astype(int)})
    return pd.concat([a, b]).groupby(["yr", "team"], as_index=False).agg(n=("win", "size"), rd=("rd", "mean"), w=("win", "mean"))


def runs_per_win(ts: pd.DataFrame, years) -> dict:
    """1 / slope of (win share - 0.5) on mean run margin, through the origin, weighted by matches; bootstrap 95% range."""
    s = ts[ts.yr.isin(list(years))]
    x, y, w = s.rd.values, s.w.values - 0.5, s.n.values
    slope = lambda i: (w[i] * x[i] * y[i]).sum() / (w[i] * x[i] ** 2).sum()
    rng = np.random.default_rng(0)
    bs = [slope(rng.integers(0, len(s), len(s))) for _ in range(1000)]
    return dict(rpw=float(1 / slope(np.arange(len(s)))), lo=float(1 / np.percentile(bs, 97.5)), hi=float(1 / np.percentile(bs, 2.5)), team_seasons=int(len(s)), r2=float(np.corrcoef(x, y)[0, 1] ** 2))


def _usage_rank(r: pd.DataFrame, app: pd.DataFrame) -> pd.DataFrame:
    u = r.groupby(["sy", "team", "player"], as_index=False).balls.sum().rename(columns={"balls": "b_all"})
    a = app.merge(u, on=["sy", "team", "player"], how="left").fillna({"b_all": 0})
    a = a.sort_values(["sy", "team", "matches", "b_all"], ascending=[True, True, False, False])
    a["rk"] = a.groupby(["sy", "team"]).cumcount() + 1
    return a


def replacement(r: pd.DataFrame, app: pd.DataFrame, prior_years, cut=11) -> dict:
    """Runs added per 100 balls (batting per ball faced, bowling per ball bowled) in the NEXT season of the players who were
    outside their team's top `cut` (by matches, then balls) in a year of `prior_years`. Using the next season keeps the
    group from being picked by the very results being measured. Returns rate, balls, and a bootstrap SE."""
    a = _usage_rank(r, app)
    fr = a[a.rk > cut].groupby(["sy", "player"]).size().rename("f").reset_index()
    ps = player_year(r)
    out, rng = {}, np.random.default_rng(1)
    for role in ("bat", "bowl"):
        q = ps[ps.role == role].copy()
        q["sy"] -= 1
        z = q[q.sy.isin(list(prior_years))].merge(fr, on=["sy", "player"])
        ra, n = (z.sc + z.wk).values, z.balls.values
        bs = [ra[i].sum() / n[i].sum() * 100 for i in (rng.integers(0, len(z), len(z)) for _ in range(300))]
        out[role] = dict(per100=float(ra.sum() / n.sum() * 100), se=float(np.std(bs)), balls=int(n.sum()), players=int(len(z)))
    return out


def load_params() -> dict:
    return json.loads(PARAMS.read_text())


def war_table(r: pd.DataFrame, prm: dict) -> pd.DataFrame:
    """Per player-season (all teams together): batting and bowling runs added, WAR parts and total.
    WAR = (runs added - replacement per ball x balls) / runs per win of that era."""
    ps = player_year(r)
    out = []
    for role in ("bat", "bowl"):
        d = ps[ps.role == role].copy()
        e = d.sy.map(era_key)
        repl = e.map({k: v["repl"][role] for k, v in prm["era"].items()}) / 100.0
        rpw = e.map({k: v["rpw"] for k, v in prm["era"].items()})
        d["ra"] = d.sc + d.wk
        d["war"] = (d.ra - repl * d.balls) / rpw
        d["repl_runs"] = repl * d.balls
        out.append(d.assign(role=role))
    b = pd.concat(out)
    w = b.pivot_table(index=["player", "sy"], columns="role", values=["balls", "ra", "war", "repl_runs", "runs", "wkts"], fill_value=0.0)
    w.columns = [f"{'bat' if c[1] == 'bat' else 'bowl'}_{c[0]}" for c in w.columns]
    w = w.reset_index()
    w["war"] = w.bat_war + w.bowl_war
    return w


# --------------------------------------------------------------------------- projection and validation
def project_table(P: Panel, t: int, prm: dict, coefs: dict, era_cfg: dict) -> pd.DataFrame:
    """pWAR for season t for every player with history: per role projected rate, expected balls, pWAR."""
    e = era_cfg[era_key(t)]
    out = pd.DataFrame({"player": P.players})
    for role in ("bat", "bowl"):
        sc, wk, den = project_rate(P, role, t, prm)
        b = _prior_balls(P, role, t, prm["ipl_from"])
        eb = exp_balls(P, role, t, coefs[role], prm["ipl_from"], b.sum(1) > 0)
        rate = sc + wk
        out[f"{role}_rate"] = rate * 100
        out[f"{role}_balls"] = eb
        out[f"{role}_pwar"] = (rate - e["repl"][role] / 100.0) * eb / e["rpw"]
        out[f"{role}_ev"] = den
    out["pwar"] = out.bat_pwar + out.bowl_pwar
    return out


def fit_all(db_path=None) -> dict:
    """Fit runs per win, replacement level, projection constants. Seasons used (see docs/VALUE_step3.md):
    2023 era numbers: IPL 2023-2026 only; 'pre' era numbers (for old-season WAR display only): IPL 2008-2022."""
    rows, apps = all_tables()
    ts = team_seasons(db_path)
    now, pre = list(range(ERA_IPL, 2027)), list(range(2008, ERA_IPL))
    rp_now, rp_pre = runs_per_win(ts, now), runs_per_win(ts, pre)
    rep_now = replacement(rows["ipl"], apps["ipl"], range(ERA_IPL, 2026))
    rep_pre = replacement(rows["ipl"], apps["ipl"], range(2008, ERA_IPL - 1))
    cap = lambda d: {k: min(v["per100"], 0.0) for k, v in d.items()}  # replacement is never better than the average player
    oth = pd.concat([rows[c] for c in rows if c != "ipl"])
    P = Panel(rows["ipl"], oth)
    prm = dict(a=0.5, s=1.0, ipl_from=ERA_IPL, pre_w=0.0, k={})
    for role in ("bat", "bowl"):
        prm["k"][role], _ = fit_k(P, role, range(2024, 2027), prm)
    coefs = {role: fit_balls(P, role, range(2024, 2027), ERA_IPL).tolist() for role in ("bat", "bowl")}
    return dict(
        era={
            IPL_NOW_LABEL: dict(rpw=rp_now["rpw"], repl=cap(rep_now)),
            IPL_PRE_LABEL: dict(rpw=rp_pre["rpw"], repl=cap(rep_pre)),
        },
        proj=prm,
        balls_coef=coefs,
        detail=dict(rpw_now=rp_now, rpw_pre=rp_pre, repl_now=rep_now, repl_pre=rep_pre),
    )


def projections(prm_all: dict, season: int = 2027, db_path=None) -> pd.DataFrame:
    rows, _ = all_tables()
    oth = pd.concat([rows[c] for c in rows if c != "ipl"])
    P = Panel(rows["ipl"], oth)
    return project_table(P, season, prm_all["proj"], {k: np.array(v) for k, v in prm_all["balls_coef"].items()}, prm_all["era"])


def write_pwar_csv(prm_all: dict, season: int = 2027) -> pd.DataFrame:
    """Players with any T20 balls in the last two years, ranked by pWAR. Columns: cricsheet_name, pwar, bat, bowl, balls basis."""
    p = projections(prm_all, season)
    rows, _ = all_tables()
    recent = pd.concat(rows.values())
    recent = recent[recent.sy >= season - 2].groupby("player").balls.sum()
    p = p[p.player.isin(recent.index)]
    out = pd.DataFrame(
        {
            "cricsheet_name": p.player,
            "pwar": p.pwar.round(3),
            "bat": p.bat_pwar.round(3),
            "bowl": p.bowl_pwar.round(3),
            "exp_balls_bat": p.bat_balls.round(0).astype(int),
            "exp_balls_bowl": p.bowl_balls.round(0).astype(int),
            "ipl_balls_since_2023": [int(P_) for P_ in 0 * np.arange(len(p))],
        }
    ).drop(columns="ipl_balls_since_2023")
    out = out.sort_values("pwar", ascending=False)
    out.to_csv(DATA / f"pwar_ipl_{season}.csv", index=False)
    return out


def main() -> None:
    prm = fit_all()
    PARAMS.write_text(json.dumps(prm, indent=1))
    print(json.dumps(prm["era"], indent=1), json.dumps(prm["proj"]), prm["balls_coef"])
    print(write_pwar_csv(prm).head(25).to_string())


if __name__ == "__main__":
    main()
