"""Pre-match model: prior-only, probabilities in [0, 1], team swap gives 1 - p (toss unknown). Synthetic matches, no DB."""

import numpy as np
import pandas as pd

from cricket_analytics.ml import prematch as pm

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta"]


def _matches(n=60, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        a, b = sorted(rng.choice(TEAMS, 2, replace=False))
        bat, bowl = (a, b) if rng.random() < 0.5 else (b, a)
        rows.append({"match_id": str(i), "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=2 * i), "competition": "ipl", "gender": "male",
                     "venue": "V1" if i % 2 else "V2", "a": a, "b": b, "final_total": float(rng.integers(120, 220)), "batting_team": bat,
                     "bowling_team": bowl, "reduced": False, "winner": str(rng.choice([a, b])), "toss_winner": a, "toss_decision": "bat"})
    return pd.DataFrame(rows)


def _obj():
    sc = {"beta": [0.0, 0.5, 0.5, 0.5], "q": {"all": [-30.0, 0.0, 30.0]}}
    win = {k: {"cols": c, "coef": [1.0] * len(c)} for k, c in pm.WIN_SETS.items()}
    return {"params": dict(pm.DEFAULT), "models": {"male": {g: {"score": sc, "win": win} for g in ("nat", "fr")}}}


def test_prior_only_later_matches_do_not_matter():
    M, obj = _matches(), _obj()
    d = M.date.iloc[40]
    p1 = pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=d)
    p2 = pm.predict_from(M[M.date < d], obj, "ipl", "V1", "Alpha", "Bravo", date=d)
    assert p1 == p2
    assert pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=d) != pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=M.date.iloc[-1] + pd.Timedelta(days=1))


def test_table_features_ignore_the_future():
    M = _matches()
    full, part = pm.table(M), pm.table(M.iloc[:30])
    cols = ["lvl", "venue_eff", "att_a", "dfn_b", "elo_a", "elo_b"]
    pd.testing.assert_frame_equal(full.iloc[:30][cols].reset_index(drop=True), part[cols].reset_index(drop=True))


def test_probability_range_and_swap():
    M, obj = _matches(), _obj()
    d = M.date.iloc[-1]
    ab = pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=d)
    ba = pm.predict_from(M, obj, "ipl", "V1", "Bravo", "Alpha", date=d)
    assert 0 <= ab["p_a_win"] <= 1
    assert abs(ab["p_a_win"] + ba["p_a_win"] - 1) < 1e-3
    assert ab["score_a_q50"] == ba["score_b_q50"] and ab["score_a_q10"] <= ab["score_a_q50"] <= ab["score_a_q90"]


def test_toss_moves_probability_only_when_given():
    M, obj = _matches(), _obj()
    d = M.date.iloc[-1]
    no = pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=d)
    yes = pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=d, toss_winner="Alpha", toss_decision="bat")
    assert not no["parts"]["toss_used"] and yes["parts"]["toss_used"] and yes["p_a_win"] > no["p_a_win"]


def test_names_are_resolved_loosely():
    M, obj = _matches(), _obj()
    d = M.date.iloc[-1]
    assert pm.predict_from(M, obj, "ipl", "v1", "alpha", "BRAVO", date=d) == pm.predict_from(M, obj, "ipl", "V1", "Alpha", "Bravo", date=d)
