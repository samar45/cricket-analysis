"""Batting: runs, average, strike rate, milestones, boundaries. Data only, no charts."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BATTER_OUT, IS_DOT, IS_FOUR, IS_SIX, phase_sql

# group_by -> (extra SELECT expressions, their output names, ORDER BY of the final query)
_GROUPS = {
    "player": ([], [], "total_runs DESC"),
    "season": (["m.competition AS competition", "m.season AS season"], ["competition", "season"],
               "batter, MIN(first_date)"),
    "phase": ([f"{phase_sql()} AS phase"], ["phase"],
              "batter, MIN(CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END)"),
}


@module(
    id="batting",
    title="Batting stats",
    category="basic",
    description="Per-batter innings, runs, average, strike rate, 50s/100s, ducks, 4s/6s, dot% and boundary%, "
                "grouped by player, by season or by phase of the innings.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("group_by", "choice", default="player", choices=tuple(_GROUPS),
                  help="player = one row per batter; season = per batter per season; phase = per batter per phase"),
        ParamSpec("min_balls", "int", default=0, help="Hide rows with fewer balls faced than this"),
    ],
    caveats=[
        "A non-striker run out is not counted as an out for anyone (Cricsheet puts player_out on the non-striker).",
        "With group_by=phase, innings/not_outs/highest are per phase: an innings counts in each phase the batter faced a ball.",
        "Super-over innings (innings 3+) are included.",
    ],
)
def batting(f: Filters, group_by: str = "player", min_balls: int = 0) -> pd.DataFrame:
    exprs, names, order = _GROUPS[group_by]
    gsel = "".join(f", {e}" for e in exprs)
    ggrp = "".join(f", {n}" for n in names)
    where, params = f.where("bat")
    sql = f"""
    WITH inn AS (
        SELECT d.batter{gsel}, d.match_id, d.innings, MIN(m.date) AS first_date,
               SUM(d.runs_batter) AS runs,
               COUNT(*) FILTER (WHERE {BALL_FACED}) AS balls,
               COUNT(*) FILTER (WHERE {IS_FOUR}) AS fours,
               COUNT(*) FILTER (WHERE {IS_SIX}) AS sixes,
               COUNT(*) FILTER (WHERE {IS_DOT}) AS dots,
               MAX(CASE WHEN {BATTER_OUT} THEN 1 ELSE 0 END) AS out
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
        GROUP BY d.batter{ggrp}, d.match_id, d.innings
    )
    SELECT batter{ggrp},
           COUNT(*)::INTEGER AS innings,
           SUM(1 - out)::INTEGER AS not_outs,
           SUM(runs)::INTEGER AS total_runs,
           SUM(balls)::INTEGER AS balls,
           MAX(runs)::INTEGER AS highest,
           ROUND(SUM(runs) * 1.0 / NULLIF(SUM(out), 0), 2) AS average,
           ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
           COUNT(*) FILTER (WHERE runs BETWEEN 50 AND 99) AS fifties,
           COUNT(*) FILTER (WHERE runs >= 100) AS hundreds,
           COUNT(*) FILTER (WHERE runs = 0 AND out = 1) AS ducks,
           SUM(fours)::INTEGER AS fours,
           SUM(sixes)::INTEGER AS sixes,
           ROUND(SUM(dots) * 100.0 / NULLIF(SUM(balls), 0), 1) AS dot_pct,
           ROUND((SUM(fours) + SUM(sixes)) * 100.0 / NULLIF(SUM(balls), 0), 1) AS boundary_pct
    FROM inn
    GROUP BY batter{ggrp}
    HAVING SUM(balls) >= ?
    ORDER BY {order}
    """
    return query(sql, params + [int(min_balls)])
