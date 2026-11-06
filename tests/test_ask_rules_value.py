"""DB-free routing rules for the value modules (ask_rules)."""

import pytest

from cricket_analytics import ask_rules as R


@pytest.mark.parametrize(
    "q,mod",
    [
        ("who added the most wins in IPL 2025", "war"),
        ("projected war for ipl 2027", "war"),
        ("which batters swung win probability most", "wpa"),
        ("most runs above average in ipl", "runs_added"),
        ("Kohli v Bumrah prediction", "matchup_predict"),
        ("swap Hardik for Jaiswal", "trade"),
        ("auction price for Pant", "auction"),
        ("which roles are scarce", "scarcity"),
        ("most catches in ipl 2024", "fielding"),
        ("most stumpings by a keeper", "fielding"),
    ],
)
def test_route_new_modules(q, mod):
    assert R.route(q, "batting")[0] == mod
    assert R.route(q, None)[0] == mod  # the fallback when the model returns no tool


def test_old_routes_unchanged():
    assert R.route("Kohli against spin", "batting")[0] == "pace_vs_spin"
    assert R.route("Kohli runs in ipl", "batting")[0] is None


def test_prediction_of_ball_is_not_out_of_scope_but_future_match_is():
    assert R.out_of_scope("Kohli v Bumrah prediction") is None
    assert R.out_of_scope("predicted auction price for Pant") is None
    assert R.out_of_scope("who will win the ipl final tonight")
    assert R.out_of_scope("predict the winner of the next match")


def test_views():
    assert R.auction_view("cheapest alternatives to expensive buys", False) == "cheapest"
    assert R.auction_view("value for money at auction", False) == "market"
    assert R.auction_view("how much did Pant go for", True) == "player"
    assert R.auction_view("auction prices", False) == "predict"
    assert R.war_view("best players projected for 2027") == "projected"
    assert R.war_view("most wins added in 2025") is None
    assert R.trade_view("best xi for CSK") == "squad"
    assert R.trade_view("swap Pant for Kuldeep") is None
    assert R.scarcity_view("team needs before the auction") == "team_needs"


def test_priority_and_fill():
    assert (
        R.route("predicted auction price for players on the block", "matchup_predict")[0]
        == "auction"
    )
    assert R.route("team needs ahead of next auction", "auction")[0] == "scarcity"
    assert (
        R.player_in_question("how much did Rishabh Pant go for in the auction", {})
        == "Rishabh Pant"
    )
    assert R.player_in_question("ek ball pe Rohit vs spin", {"rohit": 1}) == "rohit"


from cricket_analytics import ask as A  # noqa: E402
from tests.conftest import REAL_DB, requires_real_db  # noqa: E402


@requires_real_db
def test_resolve_trade_names_and_projected_war():
    with A.use_db(REAL_DB):
        p, asks, _ = A.resolve(
            {
                "name": "trade",
                "arguments": {
                    "team": "Mumbai Indians",
                    "team2": "Rajasthan Royals",
                    "give": "Hardik",
                    "get": "Jaiswal",
                },
            },
            None,
            "mumbai swap hardik for jaiswal",
        )
        assert not asks and p["give"] == "HH Pandya" and p["get"].endswith("Jaiswal")
        p, _, _ = A.resolve(
            {"name": "war", "arguments": {"view": "projected", "season": "2027"}},
            None,
            "projected war ipl 2027",
        )
        assert p == {"view": "projected"}


@requires_real_db
def test_matchup_predict_survives_two_player_rule():
    tool = {"name": "matchup_predict", "arguments": {"player": "Kohli", "player2": "Bumrah"}}
    assert (
        A.apply_rules("predict Bumrah vs Kohli per ball", tool, REAL_DB)["name"]
        == "matchup_predict"
    )


@requires_real_db
def test_team_pair_fills_missing_opposition():
    tool = {"name": "teams", "arguments": {"team": "Mumbai Indians", "competition": "ipl"}}
    out = A.apply_rules("MI vs CSK head to head", tool, REAL_DB)
    assert out["arguments"]["opposition"].lower() == "csk"
