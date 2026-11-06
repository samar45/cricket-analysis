"""Availability / opportunity predictors for the backtest (docs/VALUE_moneyball_v2.md, M12).

Targets (backtest `what`): share = share of the team's IPL matches played in season X+1; balls = balls faced + bowled.
Predictors fill `share` / `balls` columns; `ropp_*` fill bat / bowl (runs added) = marcel_ipl rate x predicted opportunity.
"""

import numpy as np
import pandas as pd

from . import war as W
from .backtest import player_year, predictor
from .marcel import WEIGHTS, _mk

SEASON_MATCHES = 14.0
K_SHARE = 4.0  # weights' worth of the average share added (regression to the mean; a guess, not tuned)
_pred_marcel = _mk(other_w=0.0)


def share_table(X: int) -> pd.DataFrame:
    """player x (X, X-1, X-2) share of team matches in IPL seasons <= X (matches / the median team's maximum, capped at 1)."""
    apps = W.season_table("ipl")[1]
    apps = apps[apps.sy <= X]
    tm = apps.groupby(["sy", "team"]).matches.max().groupby("sy").median()
    m = apps.groupby(["player", "sy"]).matches.sum().unstack(fill_value=0)
    m = m.reindex(columns=[X - i for i in range(len(WEIGHTS))], fill_value=0)
    return (m / tm.reindex(m.columns).values).clip(upper=1.0)


def weighted_share(sh: pd.DataFrame, k: float = 0.0, mean: float = 0.0) -> pd.Series:
    """5/4/3-weighted mean share (a missed season = 0), with k weights' worth of `mean` added (regression to the mean)."""
    w = np.array(WEIGHTS, float)
    return ((sh * w).sum(axis=1) + k * mean) / (w.sum() + k)


def _shrunk(X) -> pd.Series:
    sh = share_table(X)
    return weighted_share(sh, K_SHARE, weighted_share(sh).mean())


@predictor("share_last", "rank")
def share_last(T, X, ctx):
    return pd.DataFrame({"share": share_table(X)[X]})


@predictor("share_3", "rank")
def share_3(T, X, ctx):
    return pd.DataFrame({"share": weighted_share(share_table(X))})


@predictor("share_shrunk", "rank")
def share_shrunk(T, X, ctx):
    return pd.DataFrame({"share": _shrunk(X)})


@predictor("share_price", "rank")
def share_price(T, X, ctx):
    a = ctx["auctions"]
    a = a[(a.auction_year == X + 1) & a.sold]
    return pd.DataFrame({"share": a.groupby("cricsheet_name").price_cr.max()})


@predictor("share_marcel", "rank")
def share_marcel(T, X, ctx):
    """Marcel value (runs added) used as a ranker of next-season availability: do good players play more?"""
    m = _pred_marcel(T, X, ctx)
    return pd.DataFrame({"share": m[["bat", "bowl"]].sum(axis=1, min_count=1)})


def _balls(T, X):
    p = player_year(T, ["ipl"])
    p = p[p.sy <= X]
    b = p.pivot_table(index=["player", "role"], columns="sy", values="balls", aggfunc="sum")
    return b.reindex(columns=[X - i for i in range(len(WEIGHTS))]).fillna(0.0)


@predictor("balls_last", "rank")
def balls_last(T, X, ctx):
    return pd.DataFrame({"balls": _balls(T, X)[X].groupby("player").sum()})


@predictor("balls_3", "rank")
def balls_3(T, X, ctx):
    b = _balls(T, X)
    return pd.DataFrame({"balls": ((b * np.array(WEIGHTS)).sum(axis=1) / sum(WEIGHTS)).groupby("player").sum()})


def _ropp(mode):
    def fn(T, X, ctx):
        m = _pred_marcel(T, X, ctx)
        b = _balls(T, X)
        out = pd.DataFrame(index=m.index, columns=["bat", "bowl", "bat_rate", "bowl_rate"], dtype=float)
        out[["bat_rate", "bowl_rate"]] = m[["bat_rate", "bowl_rate"]]
        sh, shr, w = share_table(X), _shrunk(X), np.array(WEIGHTS, float)
        for r in ("bat", "bowl"):
            br = b.xs(r, level="role")
            if mode == "last":
                ball = br[X]
            else:  # balls per match played x predicted matches (shrunk share x 14)
                mp = (sh.reindex(br.index) * SEASON_MATCHES).fillna(0.0)
                per = (br.values * w).sum(axis=1) / np.maximum((mp.values * w).sum(axis=1), 1e-9)
                ball = pd.Series(per, index=br.index) * shr.reindex(br.index).fillna(0.0) * SEASON_MATCHES
            out[r] = m[f"{r}_rate"] * ball.reindex(m.index).fillna(0.0)
        return out

    return fn


predictor("ropp_last", "runs")(_ropp("last"))
predictor("ropp_share", "runs")(_ropp("share"))
