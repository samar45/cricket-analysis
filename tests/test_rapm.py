"""RAPM ridge (models/rapm.py) on small synthetic data: no DB needed."""

import numpy as np
import pandas as pd

from cricket_analytics.models import rapm


def _frame(n=20000, nb=15, nw=15, noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    tb, tw = rng.normal(0, 0.3, nb), rng.normal(0, 0.3, nw)  # true batter / bowler effects (positive = good)
    bi, wi = rng.integers(0, nb, n), rng.integers(0, nw, n)
    y = tb[bi] - tw[wi] + rng.normal(0, noise, n)
    d = pd.DataFrame(dict(batter=[f"B{i}" for i in bi], bowler=[f"W{i}" for i in wi], y=y, match_id=np.arange(n) // 6))
    return d, tb - tb.mean(), tw - tw.mean()


def test_recovers_known_effects_both_sides():
    d, tb, tw = _frame()
    b, w = rapm.fit(d, 5.0, 5.0)
    eb = b.reindex([f"B{i}" for i in range(15)]).to_numpy()
    ew = w.reindex([f"W{i}" for i in range(15)]).to_numpy()
    assert np.corrcoef(eb, tb)[0, 1] > 0.98 and np.corrcoef(ew, tw)[0, 1] > 0.98
    assert abs(eb - eb.mean() - tb).max() < 0.1  # opponent mix is random, so the bowlers' skill does not leak into batters


def test_lambda_to_zero_is_least_squares_and_big_lambda_is_zero():
    d, _, _ = _frame(n=400, nb=4, nw=3, noise=0.3, seed=1)
    bi, bn, wi, wn = rapm._index(d)
    X = np.zeros((len(d), len(bn) + len(wn)))
    X[np.arange(len(d)), bi] = 1.0
    X[np.arange(len(d)), len(bn) + wi] = -1.0
    ls = np.linalg.lstsq(X, d.y.to_numpy(), rcond=None)[0]  # minimum-norm least squares (batter+c, bowler+c is a free shift)
    b, w = rapm.fit(d, 1e-9, 1e-9)
    th = np.concatenate([b.to_numpy(), w.to_numpy()])
    assert np.allclose(X @ th, X @ ls, atol=1e-5)  # same fitted values (the solutions can differ only by the free shift)
    assert np.allclose(th - th.mean(), ls - ls.mean(), atol=1e-4)
    b, w = rapm.fit(d, 1e9, 1e9)
    assert np.abs(b).max() < 1e-4 and np.abs(w).max() < 1e-4


def test_opponent_adjustment_credits_the_batter_who_faced_the_star():
    # same raw y for both batters, but B1 faced only the great bowler (effect +0.5), B2 only a poor one (-0.5)
    d = pd.DataFrame(dict(batter=["B1"] * 3 + ["B2"] * 3, bowler=["W1"] * 3 + ["W2"] * 3, y=[0.0] * 6,
                          comp="ipl", sy=2024, season="2024", bat_team="X", bowl_team="Y", wk=0, b=60))
    delta = rapm.opp_delta(d, pd.Series(dtype=float), pd.Series({"W1": 0.5, "W2": -0.5}))
    bat = delta[delta.role == "bat"].set_index("player").delta
    assert bat["B1"] == 1.5 and bat["B2"] == -1.5


def test_cv_picks_a_lambda_and_is_by_match():
    d, _, _ = _frame(n=6000, noise=2.0)
    (lb, lw), t = rapm.cv_lambda(d, (0.1, 100, 1e7), (0.1, 100, 1e7), k=3)
    assert (lb, lw) == (100, 100) or lb == 100 or lw == 100  # neither extreme beats a moderate penalty
    assert len(t) == 9 and (rapm.folds(d, 3)[:6] == 0).all()  # all balls of a match share a fold
