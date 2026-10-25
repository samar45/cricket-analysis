"""Dismissal profile: how batters get out (kind, phase, pace/spin). Data only, no charts."""

from dataclasses import replace

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.attributes import attributes_cte
from ..sql.filters import Filters
from ..sql.fragments import DISMISSAL, phase_sql

KINDS = (
    "bowled",
    "lbw",
    "caught (fielder)",
    "caught (keeper)",
    "caught and bowled",
    "run out",
    "stumped",
    "other",
)
_GROUPS = {
    "kind": ("", ""),
    "phase": (", phase", "CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END"),
    "bowler_kind": (
        ", bowler_kind",
        "CASE bowler_kind WHEN 'pace' THEN 1 WHEN 'spin' THEN 2 ELSE 3 END",
    ),
}


@module(
    id="dismissal_profile",
    title="Dismissal profile",
    category="intermediate",
    description="How a batter (or a filtered group of batters) gets out: counts and % by kind (bowled, lbw, caught by a "
    "fielder / by the keeper / caught and bowled, run out, stumped, other), optionally split by phase or "
    "by the bowler's kind (pace / spin).",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec(
            "group_by",
            "choice",
            default="kind",
            choices=tuple(_GROUPS),
            help="kind = one row per dismissal kind; phase / bowler_kind = kinds split by phase or by pace/spin",
        ),
        ParamSpec(
            "min_outs", "int", default=0, help="Hide batters with fewer dismissals than this"
        ),
    ],
    caveats=[
        "Dismissals come from player_out, so they equal the outs in the batting module (a non-striker run out counts). "
        "Retired hurt / retired not out are not outs; 'retired out' is, under 'other' with hit wicket and obstructing the field.",
        "pct = share of that batter's dismissals within the group (all kinds, or one phase / bowler kind): each group sums to 100.",
        "'caught (keeper)' = the catcher is a keeper in reference/player_overrides.csv (keeper yes or sometimes); a 'sometimes' "
        "keeper who caught in the field is counted there too, and a keeper missing from the list shows as 'caught (fielder)'. "
        "Stumpings are always the keeper's and have their own kind.",
        "bowler_kind is pace / spin from the override list's bowl_type; bowlers not in the list are 'Unknown'. "
        "A run out is attributed to the bowler of that ball.",
        "The catcher is the Cricsheet fielder name; substitute fielders are not special-cased.",
        "Super-over innings (innings 3+) are excluded, as in official records.",
    ],
)
def dismissal_profile(f: Filters, group_by: str = "kind", min_outs: int = 0) -> pd.DataFrame:
    g, order = _GROUPS[group_by]
    where, params = replace(f, player=None).where("bat")
    if f.player:
        where += " AND d.player_out = ?"
        params = params + [f.player]
    order_by = f", {order}" if order else ""
    sql = f"""
    WITH {attributes_cte()},
    base AS (
        SELECT d.player_out AS batter, {phase_sql()} AS phase,
               COALESCE(b.bowl_kind, 'Unknown') AS bowler_kind,
               CASE d.wicket_type
                    WHEN 'caught' THEN CASE WHEN k.keeper IS NOT NULL THEN 'caught (keeper)' ELSE 'caught (fielder)' END
                    WHEN 'caught and bowled' THEN 'caught and bowled'
                    WHEN 'bowled' THEN 'bowled' WHEN 'lbw' THEN 'lbw' WHEN 'run out' THEN 'run out'
                    WHEN 'stumped' THEN 'stumped' ELSE 'other' END AS kind
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        LEFT JOIN pa k ON k.name = d.fielder LEFT JOIN pa b ON b.name = d.bowler
        WHERE {where} AND {DISMISSAL}
    ),
    agg AS (
        SELECT batter{g}, kind, COUNT(*)::INTEGER AS outs,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY batter{g}), 1) AS pct,
               SUM(COUNT(*)) OVER (PARTITION BY batter) AS tot
        FROM base GROUP BY batter{g}, kind
    )
    SELECT batter{g}, kind, outs, pct FROM agg WHERE tot >= ?
    ORDER BY tot DESC, batter{order_by}, outs DESC, kind
    """
    return query(sql, params + [int(min_outs)])
