import numpy as np
import pandas as pd

from cricket_analytics.ml import drawing_board as B
from cricket_analytics.ml import drawing_board_fit as F


def test_slope_detects_shrunk_predictions():
    rng = np.random.default_rng(0)
    truth = rng.normal(170, 25, 4000)
    shrunk = 170 + 0.7 * (truth - 170) + rng.normal(0, 8, 4000)  # reacts to only 70% of the real deviation
    assert B.ols_slope(shrunk, truth) > 1.1
    assert abs(B.ols_slope(truth + rng.normal(0, 1, 4000), truth) - 1) < 0.05
    s, lo, hi = B.slope_ci(shrunk, truth, np.arange(4000), "score", B=200)
    assert lo > 1.0 and lo <= s <= hi


def test_calibration_slope_for_timid_probabilities():
    rng = np.random.default_rng(1)
    z = rng.normal(0, 2, 6000)
    y = (rng.random(6000) < 1 / (1 + np.exp(-z))).astype(float)
    timid = 1 / (1 + np.exp(-0.6 * z))  # probabilities pulled toward 50%
    assert B.logit_fit(B.logit(timid), y)[1] > 1.3
    assert abs(B.logit_fit(z, y)[1] - 1) < 0.15


def test_knn_quantiles_ordered_and_scaled():
    rng = np.random.default_rng(2)
    nb = rng.gamma(2.0, 0.5, size=(50, 100))
    q = F.knn_quantiles(nb, np.full(50, 40.0))
    assert q.shape == (50, 3) and (np.diff(q, axis=1) >= 0).all()
    assert np.allclose(q, F.knn_quantiles(nb, np.ones(50)) * 40.0)


def test_residual_buckets_fall_back_and_stay_ordered():
    rng = np.random.default_rng(3)
    res, bk = rng.normal(0, 1, 1000), rng.integers(0, 2, 1000)  # buckets 2..7 are empty -> fall back to all rows
    rq = F.resid_quantiles(res, bk)
    q = F.apply_resid(np.array([100.0, 150.0]), np.array([10.0, 10.0]), np.array([0, 5]), rq)
    assert (np.diff(q, axis=1) >= 0).all() and q[0, 1] < q[1, 1]
