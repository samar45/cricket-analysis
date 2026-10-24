"""Compare two players side by side: overall and per phase, as batters or as bowlers."""

import dataclasses

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.extra import bowl_cols, ratio
from ..sql.filters import Filters
from ..sql.fragments import phase_sql
from ..sql.innings import batter_innings

_SCOPE_ORDER = "CASE scope WHEN 'overall' THEN 0 WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END"

_BAT_PARTS = """
    SELECT batter AS player, match_id, innings, 'overall' AS scope, SUM(runs) AS runs, SUM(balls) AS balls,
           SUM(fours) AS fours, SUM(sixes) AS sixes, SUM(dots) AS dots, SUM(out) AS outs
    FROM b GROUP BY batter, match_id, innings
    UNION ALL
    SELECT batter, match_id, innings, phase, runs, balls, fours, sixes, dots, out FROM b"""

_BAT_OUT = f"""
    SELECT player, scope, COUNT(*)::INTEGER AS innings, SUM(runs)::INTEGER AS runs, SUM(balls)::INTEGER AS balls,
           SUM(outs)::INTEGER AS outs,
           {ratio("SUM(runs)", "SUM(outs)")} AS average,
           {ratio("SUM(runs)", "SUM(balls)", 100.0)} AS strike_rate,
           SUM(fours)::INTEGER AS fours, SUM(sixes)::INTEGER AS sixes,
           {ratio("SUM(fours) + SUM(sixes)", "SUM(balls)", 100.0, 1)} AS boundary_pct,
           {ratio("SUM(dots)", "SUM(balls)", 100.0, 1)} AS dot_pct,
           MAX(runs) FILTER (WHERE scope = 'overall')::INTEGER AS highest,
           CASE WHEN scope = 'overall' THEN COUNT(*) FILTER (WHERE runs BETWEEN 50 AND 99)::INTEGER END AS fifties,
           CASE WHEN scope = 'overall' THEN COUNT(*) FILTER (WHERE runs >= 100)::INTEGER END AS hundreds,
           CASE WHEN scope = 'overall' THEN COUNT(*) FILTER (WHERE runs = 0 AND outs > 0)::INTEGER END AS ducks"""

_BOWL_SUMS = ("SUM(runs_conceded) AS runs_conceded, SUM(legal_balls) AS legal_balls, SUM(wickets) AS wickets, "
              "SUM(dots) AS dots, SUM(boundaries) AS boundaries, SUM(faced) AS faced")
_BOWL_OUT = f"""
    SELECT player, scope, COUNT(*)::INTEGER AS innings, SUM(wickets)::INTEGER AS wickets,
           SUM(runs_conceded)::INTEGER AS runs_conceded, SUM(legal_balls)::INTEGER AS balls,
           {ratio("SUM(runs_conceded)", "SUM(wickets)")} AS average,
           {ratio("SUM(runs_conceded)", "SUM(legal_balls)", 6.0)} AS economy,
           {ratio("SUM(legal_balls)", "SUM(wickets)")} AS strike_rate,
           {ratio("SUM(dots)", "SUM(legal_balls)", 100.0, 1)} AS dot_pct,
           {ratio("SUM(boundaries)", "SUM(faced)", 100.0, 1)} AS boundary_pct,
           MAX(wickets) FILTER (WHERE scope = 'overall')::INTEGER AS best_wickets"""


@module(
    id="compare",
    title="Player comparison",
    category="advanced",
    description="Two players side by side, as batters (role=batting) or bowlers (role=bowling): one row per player and "
                "scope (overall, powerplay, middle, death).",
    params=[
        ParamSpec("player", "player", required=True, help="First player, exact name as in the data (use resolve first)"),
        ParamSpec("player2", "player2", required=True, help="Second player, exact name"),
        *std("competition", "season", "team", "opposition", "venue"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
    ],
    caveats=[
        "A player with no balls under the filters has no rows. highest / fifties / hundreds / ducks (batting) and best_wickets (bowling) are filled for scope=overall only.",
        "Both players are measured under the same filters, so the team filter compares them for one side only.",
        "Per-phase innings = innings in which the player faced (or bowled) a ball in that phase, or was dismissed in it.",
        "Batting dismissals come from player_out, so a non-striker run out counts (same rule as the batting module).",
    ],
)
def compare(f: Filters, player2: str, role: str = "batting") -> pd.DataFrame:
    if f.player == player2:
        raise ValueError("compare needs two different players")
    f = dataclasses.replace(f, phase=None)
    order = f"ORDER BY CASE player WHEN ? THEN 0 ELSE 1 END, {_SCOPE_ORDER}"
    if role == "batting":
        # one query: two batter_innings subqueries (each filtered to its player) glued with UNION ALL
        parts = [batter_innings(dataclasses.replace(f, player=p), [(phase_sql(), "phase")]) for p in (f.player, player2)]
        sql = (f"WITH b AS ({' UNION ALL '.join(f'SELECT * FROM ({q})' for q, _ in parts)}), parts AS ({_BAT_PARTS})"
               f"{_BAT_OUT} FROM parts GROUP BY player, scope {order}")
        params = parts[0][1] + parts[1][1] + [f.player]
    else:
        where, params = dataclasses.replace(f, player=None).where("bowl")
        ph = phase_sql()
        sql = f"""
        WITH b AS (
            SELECT d.bowler AS player, d.match_id, d.innings, {ph} AS phase, {bowl_cols()}
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            WHERE {where} AND d.bowler IN (?, ?)
            GROUP BY ALL
        ), parts AS (
            SELECT player, match_id, innings, 'overall' AS scope, {_BOWL_SUMS} FROM b GROUP BY player, match_id, innings
            UNION ALL
            SELECT player, match_id, innings, phase, runs_conceded, legal_balls, wickets, dots, boundaries, faced FROM b
        )
        {_BOWL_OUT}
        FROM parts GROUP BY player, scope {order}"""
        params = params + [f.player, player2, f.player]
    return query(sql, params)
