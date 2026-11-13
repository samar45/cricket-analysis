import numpy as np
import pandas as pd

from cricket_analytics.ml import error_report as er


def test_score_stats_bias_and_within20():
    d = pd.DataFrame({"match_id": list("abcdefgh") * 2, "q50": 150.0, "final_total": [130.0] * 8 + [170.0] * 8})
    r = er.score_stats(d)
    assert r["bias"] == 0 and r["MAE"] == 20 and r["within20"] == 1.0 and r["n_matches"] == 8 and not r["flag"]


def test_score_stats_flags_constant_bias():
    d = pd.DataFrame({"match_id": range(20), "q50": 150.0, "final_total": np.linspace(130, 140, 20)})
    r = er.score_stats(d)
    assert r["bias"] > 0 and r["flag"]  # same direction every time, tiny s.e.


def test_win_stats_gap_and_right():
    d = pd.DataFrame({"match_id": range(4), "p": [0.8, 0.8, 0.2, 0.6], "chase_won": [1.0, 1.0, 1.0, 0.0]})
    r = er.win_stats(d)
    assert abs(r["gap"] - (0.6 - 0.75)) < 1e-9 and r["right%"] == 50.0


def test_by_group_counts_matches_and_playoffs():
    s = pd.DataFrame({"match_id": [1, 1, 2, 3], "g": ["x", "x", "y", "y"], "q50": 100.0, "final_total": 90.0})
    w = s.assign(p=0.5, chase_won=1.0)
    t = er.by_group(s, w, "g").set_index("group")
    assert t.loc["x", "1st n"] == 1 and t.loc["y", "1st n"] == 2 and t.loc["x", "1st bias"] == 10
    m = pd.DataFrame({"match_id": range(6), "season_year": 2024, "date": pd.date_range("2024-01-01", periods=6)})
    assert er.playoff_flag(m).sum() == 4 and er.playoff_flag(m).iloc[0] == False  # noqa: E712
