"""Bowling-type matchups: batters and teams against pace / spin (and, with detail, each bowling type), using the
player-attributes table (sql/attributes.py) instead of a guess from when a bowler bowls."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.attributes import attributes_cte
from ..sql.extra import bat_cols, ratio
from ..sql.filters import Filters
from ..sql.fragments import BOWLER_WICKET, LEGAL_BALL

# Labels come ONLY from the hand-kept bowling type (player_overrides.csv); the pace/spin guess derived from the data is not used.
# A bowler without an override type is 'Unknown'.
_SPIN = "(pa.bowl_type LIKE '%spin%' OR pa.bowl_type LIKE '%orthodox%')"
_KIND = f"CASE WHEN pa.bowl_type IS NULL THEN 'Unknown' WHEN {_SPIN} THEN 'Spin' ELSE 'Pace' END"
_TYPE = "CASE WHEN pa.bowl_type IS NULL THEN 'Unknown type' ELSE upper(left(pa.bowl_type, 1)) || substr(pa.bowl_type, 2) END"


@module(
    id="pace_vs_spin",
    title="Bowling-type matchups (pace vs spin, and each bowling type)",
    category="advanced",
    description="How a batter (or a batting team) scores against pace and spin, and with "
    "detail=true against each bowling type (right-arm fast ... left-arm wrist spin). A bowler's type comes only from the hand-kept "
    "list (player_overrides.csv); every other bowler is Unknown. Modes: batter_vs_type, team_vs_type, bowler_types "
    "(the bowlers and their labels with source and confidence).",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec(
            "mode",
            "choice",
            default="batter_vs_type",
            choices=("batter_vs_type", "team_vs_type", "bowler_types"),
            help="batter_vs_type: per batter; team_vs_type: per batting team; bowler_types: the bowlers and their labels (player = the bowler)",
        ),
        ParamSpec(
            "detail",
            "bool",
            default=False,
            help="Also split by bowling type (right-arm fast, left-arm orthodox, ...). Not used by bowler_types",
        ),
        ParamSpec(
            "min_balls",
            "int",
            help="Hide rows with fewer balls faced (default 20 per batter, 60 per team; not used by bowler_types)",
        ),
    ],
    caveats=[
        "A bowler has a type only if he is in the hand-kept list (player_overrides.csv, source manual-llm = written from memory by "
        "Claude, each with a confidence; check bowler_types). Everyone else is 'Unknown' (the pace/spin guess derived from the data is NOT used). "
        "Bowlers outside the list count as Unknown; outside the IPL that share is large.",
        "Coverage (measured 2026-10-24, share of balls faced by the batters whose bowler has a type): IPL 94.9%, men's T20I 36.1%, all men's 63.8%, women's T20I 22.9%. "
        "pct_of_balls is the share per row; read the Unknown row before quoting a split.",
        "Rows with level = kind are Pace / Spin / Unknown; rows with level = type (detail=true) are the finer types and cover the same balls again, so never add the two levels together. Pace = every fast / medium type; Spin = off spin, leg spin, orthodox, wrist spin.",
        "Teams use the real batting side of each ball, not 'innings 1 = team1'.",
        "dismissals = wickets credited to the bowler (run outs are not counted); average = runs / dismissals. "
        "Two people who share a Cricsheet name (21 names) get one label.",
    ],
)
def pace_vs_spin(
    f: Filters, mode: str = "batter_vs_type", detail: bool = False, min_balls: int | None = None
) -> pd.DataFrame:
    if mode == "bowler_types":
        where, params = f.where("bowl")
        sql = f"""
        WITH {attributes_cte("pa")}
        SELECT d.bowler AS bowler, COUNT(DISTINCT d.match_id)::INTEGER AS matches,
               COUNT(*) FILTER (WHERE {LEGAL_BALL})::INTEGER AS balls,
               lower({_KIND}) AS bowl_kind, pa.bowl_type AS bowl_type,
               pa.bowl_type_source AS kind_source, pa.bowl_type_confidence AS kind_confidence
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id LEFT JOIN pa ON pa.name = d.bowler
        WHERE {where}
        GROUP BY ALL
        HAVING COUNT(*) FILTER (WHERE {LEGAL_BALL}) > 0
        ORDER BY balls DESC, bowler"""
        return query(sql, params)

    where, params = f.where("bat")
    if mode == "team_vs_type":
        who, key, extra, floor = "team", "d.batting_team AS team", "", 60
    else:
        who, key, floor = "batter", "d.batter AS batter", 20
        extra = (
            ", COUNT(DISTINCT d.match_id || '-' || d.innings)::INTEGER AS innings, "
            f"COUNT(*) FILTER (WHERE {BOWLER_WICKET})::INTEGER AS dismissals"
        )
    levels = [("kind", _KIND)] + ([("type", _TYPE)] if detail else [])
    parts = " UNION ALL ".join(
        f"""
        SELECT {key}, '{lvl}' AS level, {label} AS bowler_type, {bat_cols()}{extra}
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id LEFT JOIN pa ON pa.name = d.bowler
        WHERE {where}
        GROUP BY ALL"""
        for lvl, label in levels
    )
    cols = f"runs, balls, {ratio('runs', 'balls', 100.0)} AS strike_rate, "
    if mode == "batter_vs_type":
        cols = f"innings, {cols}{ratio('runs', 'dismissals')} AS average, dismissals, dots, "
    # pct_of_balls and the ordering are computed before the min_balls filter, so a hidden small row still counts in the share
    sql = f"""
    WITH {attributes_cte("pa")}, g AS ({parts}), h AS (
        SELECT *, {ratio("balls", f"SUM(balls) OVER (PARTITION BY {who}, level)", 100.0, 1)} AS pct_of_balls,
               SUM(runs) OVER (PARTITION BY {who}, level) AS total_runs
        FROM g)
    SELECT {who}, level, bowler_type, {cols}{ratio("dots", "balls", 100.0, 1)} AS dot_pct,
           fours, sixes, {ratio("fours + sixes", "balls", 100.0, 1)} AS boundary_pct, pct_of_balls
    FROM h WHERE balls >= ?
    ORDER BY level, total_runs DESC, {who}, runs DESC"""
    return query(sql, params * len(levels) + [int(min_balls if min_balls is not None else floor)])
