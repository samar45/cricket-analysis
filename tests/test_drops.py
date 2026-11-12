import pandas as pd

from cricket_analytics.models.drops import bowler_season, drop_costs, pair_stats


def _balls():
    # batter A: 1 (drop here), 4, 6 -> 10 runs after the drop; B: drop then nothing
    rows = [(1, 1, 1, "A", "X", 1, 1), (1, 1, 2, "A", "X", 4, 0), (1, 1, 3, "A", "Y", 6, 0), (1, 1, 4, "B", "Y", 0, 1)]
    d = pd.DataFrame(rows, columns=["match_id", "innings", "ball_seq", "batter", "bowler", "runs_batter", "f_drop"])
    return d.assign(player_out=None, wicket_type=None, wides=0, noballs=0, legal=1.0, year=2024, bowling_team="T")


def test_cost_and_adjusted_wickets():
    d = _balls()
    c = drop_costs(d)
    assert c.set_index("batter").runs_after.to_dict() == {"A": 10, "B": 0}
    b = bowler_season(d, c).set_index("bowler")
    assert b.loc["X", "drops"] == 1 and b.loc["X", "wickets_adj"] == 1 and b.loc["Y", "wickets_adj"] == 1


def test_pair_stats_runs():
    b = pd.DataFrame({"bowler": list("aabbccdd"), "year": [1, 2] * 4, "balls": 200, "wk_rate": [.1, .1, .05, .06, .08, .07, .02, .03],
                      "wk_adj_rate": [.11, .1, .06, .06, .09, .07, .03, .03]})
    assert pair_stats(b)["n_pairs"] == 4
