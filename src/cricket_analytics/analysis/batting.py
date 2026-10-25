"""Batting: runs, average, strike rate, milestones, boundaries. Data only, no charts."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import phase_sql
from ..sql.innings import batter_innings

# group_by -> (group keys as (SQL expr, output name), ORDER BY of the final query)
_GROUPS = {
    "player": ([], "total_runs DESC"),
    "season": ([("m.competition", "competition"), ("m.season", "season")], "batter, MIN(date)"),
    "phase": (
        [(phase_sql(), "phase")],
        "batter, MIN(CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END)",
    ),
    "year": ([("year(m.date)", "year")], "batter, year"),
    "venue": ([("m.venue", "venue")], "batter, total_runs DESC"),
    "opposition": ([("d.bowling_team", "opposition")], "batter, total_runs DESC"),
}


@module(
    id="batting",
    title="Batting stats",
    category="basic",
    description="Per-batter innings, runs, average, strike rate, 50s/100s, ducks, 4s/6s, dot% and boundary%, "
    "grouped by player, season, phase of the innings, calendar year, venue or opposition.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec(
            "group_by",
            "choice",
            default="player",
            choices=tuple(_GROUPS),
            help="player = one row per batter; season / phase / year (calendar year of the match) / venue / opposition "
            "= one row per batter per group, to compare side by side",
        ),
        ParamSpec("min_balls", "int", default=0, help="Hide rows with fewer balls faced than this"),
    ],
    caveats=[
        "Dismissals are taken from player_out, so a non-striker run out counts as an out for that batter. "
        "He has an innings even if he never faced a ball; a batter left not out at the non-striker's end "
        "without facing a ball has none.",
        "With group_by=phase, innings/not_outs/highest are per phase: an innings counts in each phase the batter faced a ball or was dismissed.",
        "group_by=year is the calendar year of the match date (a BBL season spanning December-January splits into two years); "
        "season is the competition's own season label.",
        "Super-over innings (innings 3+) are excluded, as in official records.",
        "Retired hurt / retired not out are not outs; 'retired out' is.",
    ],
)
def batting(f: Filters, group_by: str = "player", min_balls: int = 0) -> pd.DataFrame:
    keys, order = _GROUPS[group_by]
    ggrp = "".join(f", {n}" for _, n in keys)
    inn, params = batter_innings(f, keys)
    sql = f"""
    WITH inn AS ({inn})
    SELECT batter{ggrp},
           COUNT(*)::INTEGER AS innings,
           SUM(1 - out)::INTEGER AS not_outs,
           SUM(runs)::INTEGER AS total_runs,
           SUM(balls)::INTEGER AS balls,
           MAX(runs)::INTEGER AS highest,
           ROUND(SUM(runs) * 1.0 / NULLIF(SUM(out), 0), 2) AS average,
           ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
           COUNT(*) FILTER (WHERE runs BETWEEN 50 AND 99)::INTEGER AS fifties,
           COUNT(*) FILTER (WHERE runs >= 100)::INTEGER AS hundreds,
           COUNT(*) FILTER (WHERE runs = 0 AND out = 1)::INTEGER AS ducks,
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
