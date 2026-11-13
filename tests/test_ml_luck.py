"""Luck tracker: curve maths on a synthetic curve, luck sums to ~0, calibrated probabilities give ~0 luck."""

import numpy as np
import pytest

from cricket_analytics.ml import luck as L


def test_curve_metrics_comeback_swing_leads():
    # chaser trails (0.2), surges to 0.9, collapses to 0.4, wins
    m = L.curve_metrics([0.6, 0.2, 0.9, 0.4], 1)
    assert m["comeback_low"] == pytest.approx(0.2)
    assert m["surprise"] == pytest.approx(0.4)
    assert m["swing"] == pytest.approx(0.4 + 0.7 + 0.5 + 0.6)  # includes the final move to the result (1.0)
    assert m["lead_changes"] == 4  # 0.6 > 0.2 < 0.9 > 0.4 < 1.0: every step crosses 50%
    assert m["decisive_over"] == 1


def test_curve_metrics_setter_wins_uses_winner_view():
    m = L.curve_metrics([0.8, 0.6, 0.1], 0)
    assert m["p_winner_start"] == pytest.approx(0.2) and m["comeback_low"] == pytest.approx(0.2)


def test_luck_sums_to_zero_and_calibrated_is_small(monkeypatch):
    import pandas as pd

    rng = np.random.default_rng(0)
    n = 4000
    p = rng.uniform(0.1, 0.9, n)
    won = (rng.random(n) < p).astype(int)
    teams = np.array(list("ABCDEFGH"))
    t = pd.DataFrame({"season": 2026, "chaser": teams[rng.integers(0, 8, n)], "setter": teams[rng.integers(0, 8, n)], "chase_won": won, "p_start": p})
    t = t[t.chaser != t.setter].reset_index(drop=True)
    monkeypatch.setattr(L, "_matches", lambda c="ipl", s=None: t)
    for adj in (False, True):
        out = L.team_luck(adjust=adj)
        assert abs(out.luck.sum()) < 0.5  # rounding only
        assert out.z.abs().max() < 4 and abs(out.z.mean()) < 0.5
