"""Backtest tool (models/backtest.py) on a tiny synthetic league table: no DB needed."""

import numpy as np
import pandas as pd

from cricket_analytics.models import backtest as B


def _T():
    rng = np.random.default_rng(0)
    rows = []
    for sy in (2023, 2024, 2025):
        for i in range(30):
            ra = i * 1.0 + (sy == 2025) * rng.normal(0, 1)  # skill = i, stable across years
            for role in ("bat", "bowl"):
                rows.append(dict(comp="ipl", sy=sy, player=f"P{i}", role=role, balls=100, ra=ra, phase="middle"))
    return pd.DataFrame(rows)


def test_predictor_sees_only_past_and_ranks_skill():
    seen = []

    def mine(T, X, ctx):
        seen.append((int(T.sy.max()), X))
        last = T[(T.sy == X) & (T.role == "bat")].set_index("player").ra
        return pd.DataFrame({"bat": last})

    res = B.run(("last_ipl", "mine"), targets=(2025,), whats=("bat",), T=_T(), extra={"mine": (mine, "runs")})
    assert seen == [(2024, 2024)]  # cut at X = target - 1: the target season is invisible
    r = res[res.target == 2025].set_index("predictor")
    assert r.loc["last_ipl", "n"] == 30 and r.loc["last_ipl", "spearman"] > 0.95
    assert r.loc["mine", "spearman"] > 0.95 and r.loc["mine", "mae"] < 2
