"""Per-player outlook for the auction page: expected IPL matches next season (10-90% range) and an evidence label.

Matches: shrunk 3-season share (availability.py) x 14. The range is the 10th / 90th percentile of what really happened in
2024-26 (truth share minus prediction, all players with IPL history before, absent = 0), by predicted-share band.
Evidence: balls faced + bowled over the last 3 seasons, IPL + the other leagues in backtest.tables(). Thresholds from
docs/VALUE_m2.md: thin < 300 (under the batter dismissal-rate n50 of 362), some < 900 (runs added per ball needs ~900 for
bowlers, 2,700 for batters, so nobody gets past 'solid' on rate alone), solid >= 900.
"""

import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import availability as AV
from . import backtest as B
from .. import db

BANDS = (0.0, 0.25, 0.6, 1.01)
THIN, SOLID = 300, 900


def evidence_label(balls: float) -> str:
    return "thin" if balls < THIN else "some" if balls < SOLID else "solid"


CACHE = Path(__file__).parents[3] / "data" / "external" / "outlook_model.pkl"  # gitignored; B.tables() alone takes ~50 s


def _key() -> list:
    """DB + model source files: the cache is stale when any of them changes."""
    fs = [db.current_db_path(), *(Path(__file__).with_name(f"{m}.py") for m in ("war", "backtest", "availability", "player_outlook"))]
    return [(f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in fs]


@lru_cache(maxsize=1)
def _model():
    """(latest IPL season X, shrunk share series for X, {band: (q10, q90)} of residuals, tables). Disk-cached next to the data."""
    try:
        k = _key()
    except OSError:  # no DB: just build, no caching
        k = None
    try:
        saved = pickle.loads(CACHE.read_bytes())
        if saved[0] == k:
            return saved[1]
    except Exception:  # no cache yet or unreadable: build
        pass
    out = _build_model()
    if k:
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_bytes(pickle.dumps((k, out)))
        except OSError:
            pass
    return out


def _build_model():
    T = B.tables()
    X = int(T[T.comp == "ipl"].sy.max())
    res = []
    for t in (X - 2, X - 1, X):
        p = AV._shrunk(t - 1)
        y = B.opportunity(t).share.reindex(p.index).fillna(0.0)
        res.append(pd.DataFrame({"pred": p, "res": y - p}))
    r = pd.concat(res)
    r["band"] = pd.cut(r.pred, BANDS, right=False, labels=False)
    q = r.groupby("band").res.quantile([0.1, 0.9]).unstack()
    return X, AV._shrunk(X), {int(b): (q.loc[b, 0.1], q.loc[b, 0.9]) for b in q.index}, T


def outlook(players) -> pd.DataFrame:
    """One row per cricsheet name: exp_matches, m10, m90 (NaN without IPL history), balls_3y, evidence."""
    X, sh, qs, T = _model()
    balls = T[T.sy >= X - 2].groupby("player").balls.sum()
    rows = []
    for p in players:
        b = float(balls.get(p, 0.0))
        row = dict(player=p, exp_matches=np.nan, m10=np.nan, m90=np.nan, balls_3y=int(b), evidence=evidence_label(b))
        if p in sh.index:
            s = sh[p]
            lo, hi = qs[int(np.digitize(s, BANDS[1:-1]))]
            row.update(
                exp_matches=round(s * AV.SEASON_MATCHES, 1),
                m10=round(float(np.clip(s + lo, 0, 1)) * AV.SEASON_MATCHES, 1),
                m90=round(float(np.clip(s + hi, 0, 1)) * AV.SEASON_MATCHES, 1),
            )
        rows.append(row)
    return pd.DataFrame(rows)
