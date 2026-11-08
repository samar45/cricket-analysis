"""Opponent-adjusted player value: ridge regression (RAPM = regularised adjusted plus-minus) on ball-level runs added.

Every ball: y = batter effect - bowler effect + noise. y is the batter-side runs added of WAR (runs on the ball + change in run
expectancy; the wicket part only when the bowler is credited, so run-outs are not charged to the bowler; centred per league-season).
Wides and other balls nobody faced have no batter: y = minus the bowler's credit, batter term absent. Effects are positive = good
(batter adds runs, bowler removes them). An L2 penalty pulls every effect to 0 (the league average); lambda is in balls of
average evidence (a player with n balls keeps about n / (n + lambda) of his raw rate). Separate lambdas for batting and bowling are
chosen by cross-validation on held-out MATCHES. Solved by conjugate gradients on the normal equations (numpy only, no scipy).

    fit(frame, lam_b, lam_w) -> (bat, bowl) Series of effects per ball
    cv_lambda(frame)         -> best (lam_b, lam_w) + the grid
    ball_frame(comps)        -> the ball-level frame (cached)
Docs: docs/VALUE_rapm.md.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..db import query
from ..sql.filters import Filters
from ..sql.fragments import phase_sql  # noqa: F401  (kept for parity with match_adjust)
from .run_expectancy import BALL_COLS, USABLE, load, ra_state
from .war import _int_cols

LAMBDA = (1000.0, 500.0)  # (batting, bowling), chosen by cv_lambda on IPL 2023-26 (docs/VALUE_rapm.md)
LAM_GRID_B = (500, 1000, 2000, 4000, 8000)
LAM_GRID_W = (250, 500, 1000, 2000, 4000)


# ------------------------------------------------------------------------------------------------ data
@lru_cache(maxsize=16)
def ball_frame(comp: str) -> pd.DataFrame:
    """One row per usable ball (no super overs): comp, sy, season, match_id, bat_team, bowl_team, batter (None if nobody faced it),
    bowler, y (see module doc), bc (the bowler's own credit incl. wicket, as WAR), wk (bowler wicket 0/1), b (balls left),
    legal. Centred per league-season like WAR (batter-side y over rows with a batter)."""
    st, sp = ra_state(Filters(competition=comp))
    sql = (f"WITH d AS ({st}) SELECT {BALL_COLS}, d.batting_team, d.bowling_team, m.date, m.season "
           f"FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE}")
    a = load().annotate(_int_cols(query(sql, sp)))
    a["sy"] = a.season.map(a.groupby("season").date.max().dt.year).astype(int)
    has = (a.faced == 1) | (a.striker_out == 1)
    yb = a.runs_batter + a.vf * (a.ball_part + a.wkt_part * a.bowler_wk) + a.bat_k
    bc = -a.conceded - a.vf * (a.ball_part + a.wkt_part * a.bowler_wk) + a.bowl_k
    y = pd.Series(np.where(has, yb, -bc), index=a.index)
    mu = y.groupby([a.sy, has]).transform("mean")  # centre batter-side and bowler-only rows separately: both average 0
    return pd.DataFrame(dict(
        comp=comp, sy=a.sy, season=a.season, match_id=a.match_id, bat_team=a.batting_team, bowl_team=a.bowling_team,
        batter=a.batter.where(has), bowler=a.bowler, y=y - mu, bc=bc, wk=a.bowler_wk, b=a.b, legal=a.legal,
    )).reset_index(drop=True)


def frames(comps, sy_from=None, sy_to=None) -> pd.DataFrame:
    d = pd.concat([ball_frame(c) for c in comps], ignore_index=True)
    if sy_from is not None:
        d = d[d.sy >= sy_from]
    if sy_to is not None:
        d = d[d.sy <= sy_to]
    return d.reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ the solver
def _index(d: pd.DataFrame):
    bi, bn = pd.factorize(d.batter)  # -1 where batter is missing
    wi, wn = pd.factorize(d.bowler)
    return bi, bn, wi, wn


def solve(bi, wi, y, nb, nw, lam_b, lam_w, wt=None, tol=1e-9, maxit=1000):
    """argmin sum wt (y - b[bi] + w[wi])^2 + lam_b |b|^2 + lam_w |w|^2, where w is the bowler's SKILL sign-flipped: the model is
    y = b[bi] - w[wi] (bi = -1: no batter). Preconditioned conjugate gradients on the normal equations."""
    wt = np.ones(len(y)) if wt is None else wt
    m = bi >= 0
    bim = bi[m]

    def Xt(r):  # X' r
        return np.concatenate([np.bincount(bim, (r * wt)[m], nb), -np.bincount(wi, r * wt, nw)])

    def X(v):
        return np.where(m, v[:nb][np.where(m, bi, 0)], 0.0) - v[nb:][wi]

    lam = np.concatenate([np.full(nb, lam_b, float), np.full(nw, lam_w, float)])
    A = lambda v: Xt(X(v)) + lam * v  # noqa: E731
    dg = np.concatenate([np.bincount(bim, wt[m], nb), np.bincount(wi, wt, nw)]) + lam
    rhs = Xt(y)
    x = np.zeros(nb + nw)
    r = rhs.copy()
    z = r / dg
    p = z.copy()
    rz, nrm = r @ z, np.linalg.norm(rhs) + 1e-30
    for _ in range(maxit):
        Ap = A(p)
        a = rz / (p @ Ap)
        x += a * p
        r -= a * Ap
        if np.linalg.norm(r) < tol * nrm:
            break
        z = r / dg
        rz2 = r @ z
        p = z + rz2 / rz * p
        rz = rz2
    return x[:nb], x[nb:]


def fit(d: pd.DataFrame, lam_b: float, lam_w: float, wt=None) -> tuple[pd.Series, pd.Series]:
    """(batter effects, bowler effects): runs added per ball above the league-season average, shrunk toward 0."""
    bi, bn, wi, wn = _index(d)
    b, w = solve(bi, wi, d.y.to_numpy(float), len(bn), len(wn), lam_b, lam_w, wt)
    return pd.Series(b, index=bn), pd.Series(w, index=wn)


def predict(d: pd.DataFrame, bat: pd.Series, bowl: pd.Series) -> np.ndarray:
    return d.batter.map(bat).fillna(0.0).to_numpy() - d.bowler.map(bowl).fillna(0.0).to_numpy()


def folds(d: pd.DataFrame, k: int = 5) -> np.ndarray:
    return pd.factorize(d.match_id)[0] % k


def cv_lambda(d: pd.DataFrame, grid_b=LAM_GRID_B, grid_w=LAM_GRID_W, k: int = 5, wt=None) -> tuple[tuple, pd.DataFrame]:
    """Held-out-match mean squared error over the lambda grid. Returns ((lam_b, lam_w), table)."""
    f = folds(d, k)
    rows = []
    for lb in grid_b:
        for lw in grid_w:
            se = 0.0
            for i in range(k):
                tr, te = d[f != i], d[f == i]
                b, w = fit(tr, lb, lw, None if wt is None else wt[f != i])
                se += ((te.y.to_numpy() - predict(te, b, w)) ** 2).sum()
            rows.append(dict(lam_b=lb, lam_w=lw, mse=se / len(d)))
    t = pd.DataFrame(rows)
    best = t.loc[t.mse.idxmin()]
    return (float(best.lam_b), float(best.lam_w)), t


# ------------------------------------------------------------------------------------------------ outputs
def effects_table(d: pd.DataFrame, bat: pd.Series, bowl: pd.Series) -> pd.DataFrame:
    """Per player: balls faced / bowled in d and the effect per ball (runs added above average), batting and bowling."""
    nb = d.batter.value_counts().rename("bat_balls")
    nw = d.bowler[d.legal == 1].value_counts().rename("bowl_balls")
    out = pd.concat([nb, bat.rename("bat_eff"), nw, bowl.rename("bowl_eff")], axis=1)
    out.index.name = "player"
    return out.fillna({"bat_balls": 0, "bowl_balls": 0})


def seasonal(d: pd.DataFrame, lam_b: float, lam_w: float) -> pd.DataFrame:
    """One ridge per league-season (opponent-adjusted, shrunk value of THAT season): player, comp, sy, role, balls, eff (per ball),
    ra = eff x balls."""
    out = []
    for (c, s), g in d.groupby(["comp", "sy"]):
        b, w = fit(g.reset_index(drop=True), lam_b, lam_w)
        e = effects_table(g, b, w)
        for role, bc, ec in (("bat", "bat_balls", "bat_eff"), ("bowl", "bowl_balls", "bowl_eff")):
            x = e[e[bc] > 0][[bc, ec]].rename(columns={bc: "balls", ec: "eff"})
            out.append(x.assign(comp=c, sy=s, role=role).reset_index())
    r = pd.concat(out, ignore_index=True)
    r["ra"] = r.eff * r.balls
    return r


def opp_delta(d: pd.DataFrame, bat: pd.Series, bowl: pd.Series, wicket_h: int = 0) -> pd.DataFrame:
    """Opponent adjustment to add to WAR's actual runs added (keeps v3's definition, non-striker run-outs, match adjustment).
    Batter's ball: + the bowler's effect (a good bowler lowers y, so his victims are credited back). Bowler's ball: + the batter's
    effect on balls with a batter. wicket_h > 0 (variant): on a bowler wicket the dismissed batter's effect counts for his expected
    remaining balls min(balls left, wicket_h) instead of one ball (a star's wicket costs more). Summed to rows keyed like WAR's
    (comp, sy, season, team, player, role): column `delta`; add it to `sc`, then re-centre."""
    eb = d.batter.map(bat).fillna(0.0).to_numpy()
    ew = d.bowler.map(bowl).fillna(0.0).to_numpy()
    h = np.where(d.wk == 1, np.minimum(d.b.to_numpy(), wicket_h) - 1, 0) if wicket_h else 0
    k = ["comp", "sy", "season", "team", "player", "role"]
    bt = d.batter.notna()
    a = pd.DataFrame(dict(comp=d.comp, sy=d.sy, season=d.season, team=d.bat_team, player=d.batter, role="bat", delta=ew))[bt]
    b = pd.DataFrame(dict(comp=d.comp, sy=d.sy, season=d.season, team=d.bowl_team, player=d.bowler, role="bowl", delta=eb * (1 + h)))
    return pd.concat([a, b]).groupby(k, as_index=False).delta.sum()


def apply_delta(rows: pd.DataFrame, delta: pd.DataFrame) -> pd.DataFrame:
    """WAR rows (centred) + opponent delta on `sc`, re-centred per league-season. Rows without a delta keep their value."""
    from .war import centre

    k = ["comp", "sy", "season", "team", "player", "role"]
    m = rows.merge(delta, on=k, how="left")
    m["sc"] = m.sc + m.delta.fillna(0.0)
    return centre(m.drop(columns="delta"))


def v4_rows(rows: pd.DataFrame, comp: str = "ipl") -> pd.DataFrame:
    """WAR v4 rows: v3 rows (centred, match-adjusted) of one league + the opponent adjustment. Effects are fitted per era
    (before 2023 and 2023 on, like the run-expectancy tables) on all that era's balls, with LAMBDA."""
    parts = []
    for lo, hi in ((2008, 2022), (2023, 9999)):
        d = frames([comp], lo, hi)
        if len(d):
            parts.append(opp_delta(d, *fit(d, *LAMBDA)))
    return apply_delta(rows, pd.concat(parts, ignore_index=True))


# ------------------------------------------------------------------------------------------------ backtest predictors
# Registered with models/backtest.py (imported at its bottom). Each fits ONLY on seasons <= X (lambda too: CV on that data).
OTHER_W = 0.5  # evidence weight of other leagues in the pooled fit (a guess, like the projection's strength s = 0.5)
_FIT: dict = {}


def _fit_upto(X: int, pooled: bool):
    key = (X, pooled)
    if key not in _FIT:
        from . import war as W

        d = frames(W.LEAGUES if pooled else ["ipl"], 2023 if not pooled else 2022, X)
        ipl = ((d.comp == "ipl") & (d.sy >= 2023)).to_numpy()
        d, wt = d[ipl | pooled].reset_index(drop=True), np.where(ipl[ipl | pooled], 1.0, OTHER_W)
        (lb, lw), _ = cv_lambda(d, k=3, wt=wt)
        _FIT[key] = fit(d, lb, lw, wt) + ((lb, lw),)
    return _FIT[key]


def _balls_q(T, X: int, role: str) -> pd.Series:
    from .backtest import player_year

    p = player_year(T, ["ipl"])
    p = p[(p.sy > X - 3) & (p.role == role)]
    return p.groupby("player").balls.sum() / 3


def _predict_rapm(T, X, ctx, pooled=False):
    bat, bowl, _ = _fit_upto(X, pooled)
    out = {}
    for role, e in (("bat", bat), ("bowl", bowl)):
        out[f"{role}_rate"] = e
        q = _balls_q(T, X, role).reindex(e.index).fillna(0.0)
        out[role] = e * q
    return pd.DataFrame(out)


def _register():
    from .backtest import predictor

    predictor("rapm", "rank")(lambda T, X, ctx: _predict_rapm(T, X, ctx, False))
    predictor("rapm_pool", "rank")(lambda T, X, ctx: _predict_rapm(T, X, ctx, True))

    @predictor("rapm_adj", "rank")
    def rapm_adj(T, X, ctx):
        """The last three IPL seasons' per-ball value (v3) corrected for the opposition faced, effects fitted on seasons <= X."""
        from .backtest import _frame, player_year

        bat, bowl, _ = _fit_upto(X, False)
        d = frames(["ipl"], 2023, X)
        dl = opp_delta(d, bat, bowl).groupby(["sy", "player", "role"], as_index=False).delta.sum()
        p = player_year(T, ["ipl"]).merge(dl, on=["sy", "player", "role"], how="left")
        p["ra"] += p.delta.fillna(0.0)
        g = p.groupby(["sy", "role"])
        p["ra"] -= g.ra.transform("sum") / g.balls.transform("sum") * p.balls
        p = p[(p.sy > X - 3) & (p.sy >= 2023)]
        s = {r: p[p.role == r].groupby("player")[["balls", "ra"]].sum() for r in ("bat", "bowl")}
        out = _frame(s["bat"], s["bowl"])
        out[["bat", "bowl"]] = out[["bat", "bowl"]] / (X - max(2023, X - 2) + 1)
        return out


_register()
