"""Pace vs spin (EXPERIMENTAL): batters and teams against bowlers whose type is GUESSED from when they bowl."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.extra import bat_cols, ratio
from ..sql.filters import Filters
from ..sql.fragments import BOWLER_WICKET, LEGAL_BALL, phase_sql

MIN_CLASSIFY_BALLS = 120   # fewer legal balls than this -> bowler_type 'Unknown'
SPIN_MIN_MIDDLE, SPIN_MAX_DEATH = 0.50, 0.20   # Spin = >50% of balls in the middle overs AND <20% at the death

_TYPE_CTE = f"""bowler_type AS (
        SELECT d.bowler,
               COUNT(*) FILTER (WHERE {LEGAL_BALL}) AS legal_balls,
               COUNT(DISTINCT d.match_id) AS matches,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND {{ph}} = 'powerplay') AS pp_balls,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND {{ph}} = 'middle') AS mid_balls,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND {{ph}} = 'death') AS death_balls
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {{where}}
        GROUP BY d.bowler HAVING COUNT(*) FILTER (WHERE {LEGAL_BALL}) >= {MIN_CLASSIFY_BALLS}
    ), typed AS (
        SELECT *, CASE WHEN mid_balls * 1.0 / legal_balls > {SPIN_MIN_MIDDLE} AND death_balls * 1.0 / legal_balls < {SPIN_MAX_DEATH}
                       THEN 'Spin' ELSE 'Pace' END AS bowler_type
        FROM bowler_type
    )"""


def _type_cte(where: str) -> str:
    return _TYPE_CTE.format(ph=phase_sql(), where=where)


@module(
    id="pace_vs_spin",
    title="Pace vs spin (EXPERIMENTAL, bowler type is guessed)",
    category="experimental",
    description="EXPERIMENTAL. The data has no bowling style, so each bowler is labelled Pace or Spin from WHEN he bowls "
                "(spin = more than half his balls in the middle overs and under 20% at the death; fewer than 120 legal "
                "balls = Unknown). Modes: batter_vs_type, team_vs_type, bowler_classification.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("mode", "choice", default="batter_vs_type", choices=("batter_vs_type", "team_vs_type", "bowler_classification"),
                  help="batter_vs_type: per batter; team_vs_type: per batting team; bowler_classification: the labels themselves (player = the bowler)"),
        ParamSpec("min_balls", "int", help="Hide rows with fewer balls faced (default 20 per batter, 60 per team; not used by bowler_classification)"),
    ],
    caveats=[
        "EXPERIMENTAL: bowler type (Pace / Spin) is a GUESS from over distribution, not data. Medium-pacers who bowl the middle overs are labelled Spin; part-timers and short careers are Unknown. Use only for rough comparisons.",
        "batter_vs_type and team_vs_type label each bowler on his whole career in the competition (season, venue, team filters do not change the label). bowler_classification labels from the filtered balls.",
        "Teams use the real batting side of each ball, not 'innings 1 = team1'.",
        "dismissals = wickets credited to the bowler (run outs are not counted). Planned replacement: a real bowling-style lookup.",
    ],
)
def pace_vs_spin(f: Filters, mode: str = "batter_vs_type", min_balls: int | None = None) -> pd.DataFrame:
    ph = phase_sql()
    if mode == "bowler_classification":
        where, params = f.where("bowl")
        sql = f"""
        WITH {_type_cte(where)}
        SELECT bowler, matches::INTEGER AS matches, legal_balls::INTEGER AS total_balls,
               {ratio("pp_balls", "legal_balls", 100.0, 1)} AS pp_pct,
               {ratio("mid_balls", "legal_balls", 100.0, 1)} AS mid_pct,
               {ratio("death_balls", "legal_balls", 100.0, 1)} AS death_pct,
               bowler_type
        FROM typed ORDER BY total_balls DESC, bowler"""
        return query(sql, params)

    base_where, base_params = Filters(competition=f.competition).where("bowl")   # label = whole career in the competition
    where, params = f.where("bat")
    if mode == "team_vs_type":
        sel = f"d.batting_team AS team, COALESCE(bt.bowler_type, 'Unknown') AS bowler_type, {bat_cols()}"
        out = f"""SELECT team, bowler_type, runs, balls, {ratio("runs", "balls", 100.0)} AS strike_rate,
                         {ratio("fours + sixes", "balls", 100.0, 1)} AS boundary_pct, {ratio("dots", "balls", 100.0, 1)} AS dot_pct
                  FROM g WHERE balls >= ? ORDER BY strike_rate DESC NULLS LAST, team"""
        floor = 60
    else:
        sel = (f"d.batter AS batter, COALESCE(bt.bowler_type, 'Unknown') AS bowler_type, "
               f"COUNT(DISTINCT d.match_id || '-' || d.innings)::INTEGER AS innings, {bat_cols()}, "
               f"COUNT(*) FILTER (WHERE {BOWLER_WICKET})::INTEGER AS dismissals")
        out = f"""SELECT batter, bowler_type, innings, runs, balls, {ratio("runs", "balls", 100.0)} AS strike_rate,
                         {ratio("runs", "dismissals")} AS average, dismissals, dots, {ratio("dots", "balls", 100.0, 1)} AS dot_pct,
                         fours, sixes, {ratio("fours + sixes", "balls", 100.0, 1)} AS boundary_pct
                  FROM g WHERE balls >= ? ORDER BY runs DESC, batter"""
        floor = 20
    sql = f"""
    WITH {_type_cte(base_where)}, g AS (
        SELECT {sel}
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        LEFT JOIN typed bt ON d.bowler = bt.bowler
        WHERE {where}
        GROUP BY ALL
    )
    {out}"""
    return query(sql, base_params + params + [int(min_balls if min_balls is not None else floor)])
