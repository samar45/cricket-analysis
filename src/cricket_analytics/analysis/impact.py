"""Player impact score: one number per player per match that blends batting and bowling, summed over matches."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BOWLER_WICKET, IS_DOT, IS_FOUR, IS_SIX, LEGAL_BALL, RUNS_CONCEDED


@module(
    id="impact",
    title="Player impact score",
    category="intermediate",
    description="All-rounder value per player: batting points (runs x strike rate) plus bowling points (wickets plus "
                "runs saved against a par economy), summed over matches. Weights are parameters.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("min_matches", "int", default=3, help="Hide players with fewer matches than this"),
        ParamSpec("top", "int", default=30, help="Rows to return (best total impact first)"),
        ParamSpec("bat_weight_pct", "int", default=60,
                  help="Batting points per match = runs * strike_rate/100 * this/100"),
        ParamSpec("wicket_points", "int", default=20, help="Bowling points per wicket"),
        ParamSpec("econ_par", "int", default=8,
                  help="Par economy. Bowling points also get (par - economy) * overs * econ_weight_pct/100 (never below 0)"),
        ParamSpec("econ_weight_pct", "int", default=40, help="Weight of the economy bonus, in percent"),
    ],
    caveats=[
        "The score is an invented blend, not a standard statistic. Defaults: batting 0.6, wicket 20 points, par economy 8, economy weight 0.4.",
        "Overs in the economy bonus are legal balls / 6 in every competition (The Hundred included).",
        "The match-level score has no context (target, pitch, opposition), only the player's own batting and bowling.",
    ],
)
def impact(f: Filters, min_matches: int = 3, top: int = 30, bat_weight_pct: int = 60, wicket_points: int = 20,
           econ_par: int = 8, econ_weight_pct: int = 40) -> pd.DataFrame:
    wb, pb = f.where("bat")
    wo, po = f.where("bowl")
    sql = f"""
    WITH bat AS (
        SELECT d.batter AS player, d.match_id,
               SUM(d.runs_batter) AS runs,
               COUNT(*) FILTER (WHERE {BALL_FACED}) AS balls,
               COUNT(*) FILTER (WHERE {IS_FOUR}) AS fours,
               COUNT(*) FILTER (WHERE {IS_SIX}) AS sixes
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {wb}
        GROUP BY ALL
    ), bowl AS (
        SELECT d.bowler AS player, d.match_id,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET}) AS wickets,
               SUM({RUNS_CONCEDED}) AS runs_conceded,
               COUNT(*) FILTER (WHERE {LEGAL_BALL}) AS legal_balls,
               COUNT(*) FILTER (WHERE {IS_DOT}) AS dots
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {wo}
        GROUP BY ALL
    ), combined AS (
        SELECT COALESCE(bat.player, bowl.player) AS player, COALESCE(bat.match_id, bowl.match_id) AS match_id,
               COALESCE(runs, 0) AS runs, COALESCE(balls, 0) AS balls,
               COALESCE(fours, 0) AS fours, COALESCE(sixes, 0) AS sixes,
               COALESCE(wickets, 0) AS wickets, COALESCE(runs_conceded, 0) AS runs_conceded,
               COALESCE(legal_balls, 0) AS legal_balls, COALESCE(dots, 0) AS dots
        FROM bat FULL OUTER JOIN bowl ON bat.player = bowl.player AND bat.match_id = bowl.match_id
    ), scored AS (
        SELECT *,
               CASE WHEN balls > 0 THEN runs * runs * 1.0 / balls * ? ELSE 0 END AS bat_pts,
               wickets * ?
               + CASE WHEN legal_balls > 0
                      THEN GREATEST(? - runs_conceded * 6.0 / legal_balls, 0) * legal_balls / 6.0 * ?
                      ELSE 0 END AS bowl_pts
        FROM combined
    )
    SELECT player,
           COUNT(DISTINCT match_id)::INTEGER AS matches,
           SUM(runs)::INTEGER AS total_runs,
           SUM(wickets)::INTEGER AS total_wickets,
           SUM(fours)::INTEGER AS fours,
           SUM(sixes)::INTEGER AS sixes,
           ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 1) AS batting_sr,
           ROUND(SUM(runs_conceded) * 6.0 / NULLIF(SUM(legal_balls), 0), 2) AS economy,
           ROUND(SUM(dots) * 100.0 / NULLIF(SUM(legal_balls), 0), 1) AS dot_pct,
           ROUND((SUM(bat_pts) + SUM(bowl_pts)) / COUNT(DISTINCT match_id), 2) AS avg_impact,
           ROUND(SUM(bat_pts), 1) AS bat_impact,
           ROUND(SUM(bowl_pts), 1) AS bowl_impact,
           ROUND(SUM(bat_pts) + SUM(bowl_pts), 1) AS total_impact
    FROM scored
    GROUP BY player
    HAVING COUNT(DISTINCT match_id) >= ?
    ORDER BY total_impact DESC, player
    LIMIT ?
    """
    weights = [bat_weight_pct / 100.0, wicket_points, econ_par, econ_weight_pct / 100.0]
    return query(sql, pb + po + weights + [int(min_matches), int(top)])
