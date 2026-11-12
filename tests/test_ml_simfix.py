import numpy as np
import pandas as pd

from cricket_analytics.ml.ball_model import RUNS, BallModel, _softmax


def test_season_shift_matches_group_mean():
    rng = np.random.default_rng(0)
    n = 3000
    d = pd.DataFrame({"over_n": rng.integers(0, 20, n), "competition": "ipl", "season_year": rng.integers(2020, 2022, n),
                      "cls": rng.choice(8, n, p=[.3, .38, .07, .004, .1, .05, .05, .046]), "lvl_slow": 8.0, "lvl_fast": 8.0})
    m = BallModel("B", season_neutral=True)
    m.lr_coef, m.lr_b = np.zeros((8, 9)), np.zeros(8)
    pr = _softmax(m._off(d) + m._season_shift(d))
    ph = np.where(d.over_n < 6, 0, np.where(d.over_n < 16, 1, 2))
    for (y, p), g in d.groupby(["season_year", ph]):
        assert abs((pr[g.index] @ RUNS).mean() - RUNS[g.cls].mean()) < 1e-3
