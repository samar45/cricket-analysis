"""Batter vs bowler: balls, runs, dismissals, strike rate, dot% and boundary%."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BOWLER_WICKET, IS_DOT, LEGAL_BALL, RUNS_CONCEDED


@module(
    id="matchup",
    title="Batter vs bowler",
    category="basic",
    description="Head-to-head of batters against bowlers. Give player (batter) and player2 (bowler) for one duel; "
    "give only one to list that player's opponents, busiest first.",
    params=[
        *std("player", "player2", "competition", "season", "venue", "phase", "team", "opposition"),
        ParamSpec(
            "min_balls",
            "int",
            default=6,
            help="Hide pairs with fewer balls faced than this (ignored when both players are given)",
        ),
        ParamSpec("top", "int", default=50, help="Maximum rows returned"),
    ],
    caveats=[
        "player = the batter, player2 = the bowler. At least one of them is required.",
        "dismissals = wickets credited to that bowler (bowled, caught, lbw, stumped, hit wicket); run outs are not his.",
        "balls = balls the batter faced (wides excluded); dot_pct and boundary_pct use that denominator.",
        "economy = runs charged to the bowler (bat runs + wides + no-balls) * 6 / legal balls in those duels.",
        "team = the batter's side, opposition = the bowler's side.",
        "Super-over balls are excluded.",
    ],
)
def matchup(
    f: Filters, player2: str | None = None, min_balls: int = 6, top: int = 50
) -> pd.DataFrame:
    if not f.player and not player2:
        raise ValueError("matchup needs player (batter), player2 (bowler), or both")
    where, params = f.where("bat")
    if player2:
        where += " AND d.bowler = ?"
        params = params + [player2]
    if f.player and player2:
        min_balls = 0
    sql = f"""
    SELECT d.batter, d.bowler,
           COUNT(*) FILTER (WHERE {BALL_FACED})::INTEGER AS balls,
           SUM(d.runs_batter)::INTEGER AS runs,
           COUNT(*) FILTER (WHERE {BOWLER_WICKET} AND d.player_out = d.batter)::INTEGER AS dismissals,
           ROUND(SUM(d.runs_batter) * 100.0 / NULLIF(COUNT(*) FILTER (WHERE {BALL_FACED}), 0), 2) AS strike_rate,
           ROUND(SUM(d.runs_batter) * 1.0 / NULLIF(COUNT(*) FILTER (WHERE {BOWLER_WICKET} AND d.player_out = d.batter), 0), 2) AS average,
           ROUND(COUNT(*) FILTER (WHERE {IS_DOT}) * 100.0 / NULLIF(COUNT(*) FILTER (WHERE {BALL_FACED}), 0), 1) AS dot_pct,
           ROUND(COUNT(*) FILTER (WHERE d.runs_batter IN (4, 6)) * 100.0
                 / NULLIF(COUNT(*) FILTER (WHERE {BALL_FACED}), 0), 1) AS boundary_pct,
           ROUND(SUM({RUNS_CONCEDED}) * 6.0 / NULLIF(COUNT(*) FILTER (WHERE {LEGAL_BALL}), 0), 2) AS economy,
           COUNT(*) FILTER (WHERE {IS_DOT})::INTEGER AS dots,
           COUNT(*) FILTER (WHERE d.runs_batter = 1)::INTEGER AS ones,
           COUNT(*) FILTER (WHERE d.runs_batter = 2)::INTEGER AS twos,
           COUNT(*) FILTER (WHERE d.runs_batter = 3)::INTEGER AS threes,
           COUNT(*) FILTER (WHERE d.runs_batter = 4)::INTEGER AS fours,
           COUNT(*) FILTER (WHERE d.runs_batter = 6)::INTEGER AS sixes,
           COUNT(DISTINCT d.match_id)::INTEGER AS matches
    FROM deliveries d JOIN matches m ON d.match_id = m.match_id
    WHERE {where}
    GROUP BY d.batter, d.bowler
    HAVING COUNT(*) FILTER (WHERE {BALL_FACED}) >= ?
    ORDER BY balls DESC, runs DESC
    LIMIT ?
    """
    return query(sql, params + [int(min_balls), int(top)])
