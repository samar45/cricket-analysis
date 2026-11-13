"""resources.py: features change only on new batter / over boundary, never leak later balls, bowler overs never negative."""

import numpy as np

from cricket_analytics.ml import resources as R

BAT = {c: (e, 1.0, p) for c, e, p in [("A", 12, 1), ("B", 11, 2), ("C", 10, 3), ("D", 9, 4), ("E", 8, 5), ("F", 7, 6), ("G", 6, 7),
                                      ("H", 4, 8), ("I", 3, 9), ("J", 2, 10), ("K", 1, 11)]}
BOWL = {c: (e, 1.0, e, 0.8) for c, e in [("p", 0.8), ("q", 0.9), ("r", 1.0), ("s", 1.1), ("t", 1.2)]}


def rows(n=120, wk_at=(30, 50)):
    """Pairs A,B open; a wicket at ball 30 brings C, at 50 brings D; five bowlers rotate by over (p,q,r,s,t,p,q...)."""
    out, st, ns, nxt = [], "A", "B", iter("CDEFGHIJK")
    for k in range(n + 1):
        if k in wk_at:
            st = next(nxt)
        out.append((k, st, ns, "pqrst"[(k // 6) % 5]))
    return out


def test_changes_only_on_wicket_or_over():
    res = R.innings_resources(rows(), BAT, BOWL)
    for k in range(1, 121):
        bat_changed = any(res[k][c] != res[k - 1][c] for c in R.BAT_COLS)
        bowl_changed = any(res[k][c] != res[k - 1][c] for c in R.BOWL_COLS)
        assert bat_changed == (k in (30, 50)), k
        if k % 6:
            assert not bowl_changed, k
    assert res[0]["bat_left_n"] == 9 and res[30]["bat_left_n"] == 8 and res[50]["bat_left_n"] == 7
    assert res[0]["best_bat_left"] == 10 and res[30]["best_bat_left"] == 9  # best of C..K, then of D..K


def test_no_leakage_and_no_negative_overs():
    full = R.innings_resources(rows(), BAT, BOWL)
    cut = R.innings_resources(rows()[:77], BAT, BOWL)  # later deliveries deleted
    for a, b in zip(full, cut):
        assert all(np.isclose(a[c], b[c], equal_nan=True) for c in R.FIELDS)
    for r in full:
        assert r["death_top_left"] >= 0 and r["bat_left_n"] >= 0


def test_bowl_features_caps():
    f = R.bowl_features([(0.0, 0.5, 2.0, 0.5), (1.0, 1.0, 1.0, 1.0)], 3)  # overs from cap-0 bowler are unavailable; 2 overs padded
    assert abs(f["bowl_left_econ"] - (1.0 + 2 * R.PAD_BOWL[0]) / 3) < 1e-9 and f["death_top_left"] == 1.0
    assert R.bat_features([], 0)["bat_left_n"] == 0
