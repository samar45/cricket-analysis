"""Match-conditions adjustment of runs added (docs/VALUE_match_adjust.md).

Runs added already compares each ball with the expected value for the over / wickets / innings state, centred per league-season.
This adds a "match condition" c for every (match, phase, role): the mean runs added per ball of ALL OTHER players in the same
match and phase (both innings, role-specific), leave-one-player-out so a player never sets his own baseline.
Adjusted runs added = runs added - w * c * balls, then re-centred per league-season so an average player is still 0.
w in [0, 1] is fitted (match_adjust_curve); the sign works for both roles because bowlers' credit is already "less conceded = more".

Use:  match_adjusted_runs_added(Filters(competition="ipl"), w=0.5)   -> per player-season bat / bowl adjusted runs added + balls.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..sql.filters import Filters
from ..sql.fragments import phase_sql
from ..db import query
from .run_expectancy import BALL_COLS, USABLE, load, ra_state
from .war import _int_cols, centre

KEY = ["comp", "sy", "season", "match_id", "phase", "team", "player", "role"]
W_GRID = (0, 0.25, 0.5, 0.75, 1)


@lru_cache(maxsize=16)
def match_rows(comp: str) -> pd.DataFrame:
    """One row per (match, phase, team, player, role): balls and runs added (v1 definition, centred per league-season)."""
    st, sp = ra_state(Filters(competition=comp))
    sql = (f"WITH d AS ({st}) SELECT {BALL_COLS}, d.batting_team, d.bowling_team, d.non_striker, m.date, m.season, "
           f"{phase_sql()} AS phase FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE}")
    a = load().annotate(_int_cols(query(sql, sp)))
    a["sy"] = a.season.map(a.groupby("season").date.max().dt.year).astype(int)
    a["comp"] = comp
    s = a[(a.faced == 1) | (a.striker_out == 1)]
    n = a[(a.wk == 1) & (a.striker_out == 0)]
    z = lambda x, team, p, role, balls, ra: pd.DataFrame(dict(  # noqa: E731
        comp=comp, sy=x.sy, season=x.season, match_id=x.match_id, phase=x.phase, team=team, player=p, role=role, balls=balls, ra=ra))
    parts = [
        z(s, s.batting_team, s.batter, "bat", s.faced, s.runs_batter + s.vf * (s.ball_part + s.wkt_part * s.striker_out) + s.bat_k),
        z(n, n.batting_team, n.player_out, "bat", 0, n.vf * n.wkt_part),
        z(a, a.bowling_team, a.bowler, "bowl", a.legal, -a.conceded - a.vf * (a.ball_part + a.wkt_part * a.bowler_wk) + a.bowl_k),
    ]
    r = pd.concat(parts).groupby(KEY, as_index=False)[["balls", "ra"]].sum()
    c = centre(r.assign(sc=r.ra, wk=0.0, runs=0, wkts=0))  # same league-season centring as WAR
    r["ra"] = c.sc.values
    return r


def condition(r: pd.DataFrame) -> pd.Series:
    """c per row: mean ra per ball of the other players in the same (match, phase, role); 0 where nobody else has balls."""
    g = r.groupby(["match_id", "phase", "role"])
    tot_ra, tot_b = g.ra.transform("sum"), g.balls.transform("sum")
    # a player may have several rows (two teams never; same player twice in a group only if the key repeats) -> use rows
    pr = r.groupby(["match_id", "phase", "role", "player"])
    own_ra, own_b = pr.ra.transform("sum"), pr.balls.transform("sum")
    den = tot_b - own_b
    return ((tot_ra - own_ra) / den.where(den > 0)).fillna(0.0)


def adjusted(r: pd.DataFrame, w: float) -> pd.DataFrame:
    """r with column ra_adj = ra - w * c * balls, re-centred per comp / season / role (average player = 0)."""
    out = r.copy()
    out["c"] = condition(r)
    out["ra_adj"] = r.ra - w * out.c * r.balls
    mu = out.groupby(["comp", "sy", "role"]).ra_adj.transform("sum") / out.groupby(["comp", "sy", "role"]).balls.transform("sum")
    out["ra_adj"] -= mu * out.balls
    return out


def match_adjusted_runs_added(f: Filters, w: float) -> pd.DataFrame:
    """Per player-season: comp, sy, player, bat_balls, bat_ra (raw), bat_ra_adj, bowl_balls, bowl_ra, bowl_ra_adj.
    f.competition picks the league (required); f.player / f.season (4-digit year = sy) narrow the rows."""
    r = adjusted(match_rows(f.competition), w)
    if f.player:
        r = r[r.player == f.player]
    g = r.groupby(["comp", "sy", "player", "role"])[["balls", "ra", "ra_adj"]].sum().unstack("role")
    g.columns = [f"{role}_{col}" for col, role in g.columns]
    return g.fillna(0.0).reset_index()


# ------------------------------------------------------------------------------------------------ fitting the weight
MINB = {"bat": 100, "bowl": 60}


def _rate_pairs(r: pd.DataFrame, col: str, role: str, a, b):
    """player rates (col per ball) in two disjoint groups of rows a, b (boolean masks); players with enough balls in both."""
    d = r[r.role == role]
    g = lambda m: d[m.loc[d.index]].groupby("player")[["balls", col]].sum()  # noqa: E731
    x, y = g(a), g(b)
    j = x.join(y, lsuffix="_x", rsuffix="_y", how="inner")
    j = j[(j.balls_x >= MINB[role]) & (j.balls_y >= MINB[role])]
    return j[f"{col}_x"] / j.balls_x, j[f"{col}_y"] / j.balls_y


def repeatability(r: pd.DataFrame, comp: str, years, col: str = "ra_adj") -> dict:
    """Pearson r of per-ball value, consecutive seasons (pooled over the year pairs) and odd / even matches (same season)."""
    r = r[(r.comp == comp) & r.sy.isin(list(years))]
    out = {}
    for role in ("bat", "bowl"):
        xs, ys, hs, hy = [], [], [], []
        for y in sorted(set(years))[:-1]:
            x, z = _rate_pairs(r, col, role, r.sy == y, r.sy == y + 1)
            xs.append(x.values); ys.append(z.values)  # noqa: E702
        ord_ = r.drop_duplicates("match_id").assign(k=lambda d: d.groupby("sy").cumcount()).set_index("match_id").k
        odd = r.match_id.map(ord_) % 2 == 1
        for y in years:
            x, z = _rate_pairs(r, col, role, (r.sy == y) & odd, (r.sy == y) & ~odd)
            hs.append(x.values); hy.append(z.values)  # noqa: E702
        c = lambda p, q: float(np.corrcoef(np.concatenate(p), np.concatenate(q))[0, 1])  # noqa: E731
        out[role] = dict(consec=c(xs, ys), n_consec=sum(map(len, xs)), half=c(hs, hy), n_half=sum(map(len, hs)))
    return out


def team_fit(r: pd.DataFrame, ts: pd.DataFrame, years, col: str = "ra_adj") -> dict:
    """r and slope of (win share - 0.5) x matches on a team's summed runs added (IPL team-seasons), as war.runs_per_win."""
    t = r[r.comp == "ipl"].groupby(["sy", "team"], as_index=False)[col].sum().rename(columns={"sy": "yr", col: "ra"})
    s = ts[ts.yr.isin(list(years))].merge(t, on=["yr", "team"])
    y, x = (s.w - 0.5) * s.n, s.ra
    return dict(r=float(np.corrcoef(x, y)[0, 1]), rpw=float(1 / ((x * y).sum() / (x**2).sum())), n=len(s))


def curve(comps=("ipl", "bbl", "psl"), ws=W_GRID) -> pd.DataFrame:
    """The table behind the chosen w: per w, repeatability (IPL 2023-26 and other leagues, bat / bowl) and IPL team-season fit."""
    from .war import team_seasons

    ts = team_seasons()
    rows = []
    for w in ws:
        row = dict(w=w)
        for comp in comps:
            r = adjusted(match_rows(comp), w)
            yrs = range(2023, 2027) if comp == "ipl" else sorted(r[r.comp == comp].sy.unique())[-4:]
            rp = repeatability(r, comp, yrs)
            for role in ("bat", "bowl"):
                row[f"{comp}_{role}_consec"], row[f"{comp}_{role}_half"] = rp[role]["consec"], rp[role]["half"]
        r = adjusted(match_rows("ipl"), w)
        for lab, yrs in (("all", range(2008, 2027)), ("2023+", range(2023, 2027))):
            row[f"team_r_{lab}"] = team_fit(r, ts, yrs)["r"]
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ predictive check
def adjusted_tables(T: pd.DataFrame, w: float) -> pd.DataFrame:
    """backtest.tables() with `ra` replaced by the match-adjusted value (same keys; comps without match rows are kept as is)."""
    parts = []
    for comp, d in T.groupby("comp"):
        try:
            r = adjusted(match_rows(comp), w)
        except Exception:  # ponytail: a league that fails to load keeps its raw values
            parts.append(d); continue  # noqa: E702
        k = ["comp", "sy", "season", "team", "player", "role", "phase"]
        g = r.groupby(k, as_index=False)[["ra_adj"]].sum()
        m = d.merge(g, on=k, how="left")
        parts.append(m.assign(ra=m.ra_adj.fillna(m.ra)).drop(columns="ra_adj"))
    return pd.concat(parts, ignore_index=True)


def predictive(ws=W_GRID, names=("ipl3", "lw_all"), targets=(2024, 2025, 2026)) -> pd.DataFrame:
    """Next-season Spearman rho (pooled over targets) of per-ball predictors fed adjusted values; truth = raw, and truth = adjusted."""
    from . import backtest as B

    T0 = B.tables()
    rows = []
    for w in ws:
        Tw = adjusted_tables(T0, w) if w else T0
        for tl, tf in (("raw", lambda T, t: B.truth_runs(T0, t)), ("adj", lambda T, t: B.truth_runs(Tw, t))):
            res = B.run(names, targets, whats=("bat_rate", "bowl_rate"), truth_fn=tf, T=Tw)
            p = res[res.target == "pooled"]
            for _, x in p.iterrows():
                rows.append(dict(w=w, truth=tl, predictor=x.predictor, what=x.what, rho=x.spearman, n=x.n))
    return pd.DataFrame(rows)
