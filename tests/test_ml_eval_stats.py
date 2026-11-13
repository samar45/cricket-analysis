import numpy as np
import pandas as pd

from cricket_analytics.ml import evaluate as ev


def _sim(n, shift=0.0, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.95, n)
    y = (rng.random(n) < p).astype(float)
    return y, np.clip(p + shift, 0.01, 0.99)


def test_calibrated_passes():
    for seed in range(3):
        y, p = _sim(300, 0, seed)
        r = ev.calibration_test(y, p, n_sim=300)
        assert r["pass_primary"] and r["pass_secondary"], r


def test_miscalibrated_fails():
    y, p = _sim(1500, 0.1)
    r = ev.calibration_test(y, p, n_sim=300)
    assert not r["pass_primary"] and not r["pass_secondary"], r


def test_fixed_ece_limit_is_unfair_at_small_n():
    # a perfectly calibrated model at n=70 usually exceeds 0.08, but passes the null-based test
    y, p = _sim(70, 0, 5)
    r = ev.calibration_test(y, p, n_sim=300)
    assert r["ece_null_mean"] > 0.08 and r["pass_secondary"]


def test_block_bootstrap_wider_on_clustered_data():
    rng = np.random.default_rng(0)
    blocks = np.repeat(np.arange(6), 60)
    df = pd.DataFrame({"season_year": blocks, "competition": "x", "match_id": np.arange(360), "v": rng.normal(0, 1, 360) + rng.normal(0, 1, 6)[blocks] * 2})
    f = lambda d: d.v.mean()  # noqa: E731
    _, l1, h1, _ = ev.match_bootstrap(df, f, n=500)
    _, l2, h2, nb = ev.season_block_bootstrap(df, f, n=500)
    assert nb == 6 and (h2 - l2) > 1.5 * (h1 - l1)


def test_power_n_and_holm():
    assert ev.power_n(0.5, 1.0) == 32  # (1.96+0.84)^2 * 4 = 31.4
    assert ev.power_n(0.25, 1.0) > 3.9 * ev.power_n(0.5, 1.0)
    assert np.allclose(ev.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])
