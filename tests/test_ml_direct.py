import numpy as np
import pandas as pd

from cricket_analytics.ml import direct as D


def test_level_relative_target_round_trips():
    d = pd.DataFrame({"lvl_ew": [150.0, 190.0, 170.0], "balls_left": [120, 60, 1]})
    s = D.target_scale(d, "lvl_ew")
    y = np.array([160.0, 90.0, 2.0])
    assert np.allclose(D.from_ratio(D.to_ratio(y, s), s), y)
    # a higher scoring level scales the same ratio to more runs (the point of the transform)
    hi = D.target_scale(d.assign(lvl_ew=d.lvl_ew + 30), "lvl_ew")
    assert (hi > s).all() and (s >= 0.5).all()


def test_conformal_widening_reaches_target_coverage():
    rng = np.random.default_rng(1)
    n = 4000
    y = rng.normal(0, 10, 2 * n)
    lo, hi = np.full(2 * n, -5.0), np.full(2 * n, 5.0)  # far too narrow (about 38% coverage)
    b = np.zeros(2 * n, int)
    dl = D.conformal_delta(y[:n], lo[:n], hi[:n], b[:n])
    lo2, hi2 = D.conformal_apply(lo[n:], np.zeros(n), hi[n:], b[n:], dl)
    cov = np.mean((y[n:] >= lo2) & (y[n:] <= hi2))
    assert 0.78 <= cov <= 0.83 and dl[0] > 0


def test_p_from_quantiles_monotone_and_clipped():
    lv = (0.1, 0.5, 0.9)
    q = np.tile([[10.0, 30.0, 50.0]], (4, 1))
    p = D.p_from_quantiles(q, lv, np.array([5.0, 30.0, 40.0, 99.0]))
    assert np.allclose(p[[0, 3]], [0.98, 0.02]) and abs(p[1] - 0.5) < 1e-9 and p[1] > p[2]
