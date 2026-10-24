"""Bowling: wickets, runs conceded, economy, average, strike rate, dots, hauls. Data only, no charts."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BOWLER_WICKET, IS_DOT, IS_FOUR, IS_SIX, LEGAL_BALL, RUNS_CONCEDED, phase_sql

# group_by -> (group keys as (SQL expr, output name), ORDER BY of the final query)
_GROUPS = {
    "player": ([], "wickets DESC, economy"),
    "season": ([("m.competition", "competition"), ("m.season", "season")], "bowler, MIN(first_date)"),
    "phase": ([(phase_sql(), "phase")],
              "bowler, MIN(CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END)"),
}


@module(
    id="bowling",
    title="Bowling stats",
    category="basic",
    description="Per-bowler wickets, runs conceded, economy, average, strike rate, dot%, boundaries conceded, "
                "wides, no-balls, 3-/5-wicket hauls and best figures, grouped by player, season or phase.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("group_by", "choice", default="player", choices=tuple(_GROUPS),
                  help="player = one row per bowler; season = per bowler per season; phase = per bowler per phase"),
        ParamSpec("min_balls", "int", default=0, help="Hide rows with fewer legal balls bowled than this"),
    ],
    caveats=[
        "Runs conceded = bat runs + wides + no-balls; byes, leg-byes and penalty runs are not charged to the bowler.",
        "Wickets exclude run outs, retirements, obstructing the field and hit-the-ball-twice.",
        "Economy = runs conceded * 6 / legal balls (wides and no-balls are not legal balls), also in The Hundred.",
        "dot_pct = dots / legal balls. boundary_pct = fours+sixes / balls faced by batters (no-balls count, wides do not).",
        "wides / no_balls are runs from those extras (a wide that also ran 4 counts 5).",
        "A 'haul' is per innings bowled: three_plus = 3 or more wickets, five_plus = 5 or more.",
        "team = the bowler's own side. With group_by=phase an innings counts in each phase the bowler bowled.",
        "Super-over innings (innings 3+) are excluded, as in official records.",
    ],
)
def bowling(f: Filters, group_by: str = "player", min_balls: int = 0) -> pd.DataFrame:
    keys, order = _GROUPS[group_by]
    gsel = "".join(f", {e} AS {n}" for e, n in keys)
    ggrp = "".join(f", {n}" for _, n in keys)
    where, params = f.where("bowl")
    sql = f"""
    WITH inn AS (
        SELECT d.bowler{gsel}, d.match_id, d.innings, MIN(m.date) AS first_date,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET}) AS wkts,
               SUM({RUNS_CONCEDED}) AS runs,
               COUNT(*) FILTER (WHERE {LEGAL_BALL}) AS legal,
               COUNT(*) FILTER (WHERE {BALL_FACED}) AS faced,
               COUNT(*) FILTER (WHERE {IS_DOT}) AS dots,
               COUNT(*) FILTER (WHERE {IS_FOUR}) AS fours,
               COUNT(*) FILTER (WHERE {IS_SIX}) AS sixes,
               SUM(d.wides) AS wides,
               SUM(d.noballs) AS noballs
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
        GROUP BY d.bowler{ggrp}, d.match_id, d.innings
    )
    SELECT bowler{ggrp},
           COUNT(*)::INTEGER AS innings,
           SUM(wkts)::INTEGER AS wickets,
           SUM(runs)::INTEGER AS runs_conceded,
           SUM(legal)::INTEGER AS balls,
           ROUND(SUM(runs) * 6.0 / NULLIF(SUM(legal), 0), 2) AS economy,
           ROUND(SUM(runs) * 1.0 / NULLIF(SUM(wkts), 0), 2) AS average,
           ROUND(SUM(legal) * 1.0 / NULLIF(SUM(wkts), 0), 2) AS strike_rate,
           ROUND(SUM(dots) * 100.0 / NULLIF(SUM(legal), 0), 1) AS dot_pct,
           ROUND((SUM(fours) + SUM(sixes)) * 100.0 / NULLIF(SUM(faced), 0), 1) AS boundary_pct,
           SUM(dots)::INTEGER AS dots,
           SUM(fours)::INTEGER AS fours_conceded,
           SUM(sixes)::INTEGER AS sixes_conceded,
           SUM(wides)::INTEGER AS wides,
           SUM(noballs)::INTEGER AS no_balls,
           COUNT(*) FILTER (WHERE wkts >= 3)::INTEGER AS three_plus,
           COUNT(*) FILTER (WHERE wkts >= 5)::INTEGER AS five_plus,
           arg_max(wkts::VARCHAR || '/' || runs::VARCHAR, wkts * 100000 - runs) AS best_figures
    FROM inn
    GROUP BY bowler{ggrp}
    HAVING SUM(legal) >= ?
    ORDER BY {order}
    """
    return query(sql, params + [int(min_balls)])
