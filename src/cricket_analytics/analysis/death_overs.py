"""Death-overs index: how a player does in the last overs of the innings compared with his own overall numbers."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.extra import bowl_cols, ratio
from ..sql.filters import Filters
from ..sql.fragments import phase_sql
from ..sql.innings import batter_innings


@module(
    id="death_overs",
    title="Death-overs index",
    category="advanced",
    description="Batters: death-overs strike rate divided by overall strike rate, times 100. Bowlers: overall economy "
                "divided by death-overs economy, times 100. Above 100 = better in the death overs than overall. "
                "Replaces the old 'clutch index'.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec("min_balls", "int", help="Hide players with fewer death-overs balls than this (default 15 faced when batting, 30 legal when bowling)"),
        ParamSpec("top", "int", default=40, help="Rows to return (highest index first)"),
    ],
    caveats=[
        "This is NOT a pressure or clutch measure. It only compares the death overs (death = overs 16-20; The Hundred: the last 25 balls) with the same player's other overs. True pressure (target, wickets down, required rate) is a later module (Phase 7).",
        "Not baseline-adjusted: scoring is faster at the death for everyone, so a typical batter's index is well above 100. Compare players with each other, or use true_performance for a league-adjusted number.",
        "The player also needs at least 3x min_balls balls overall (so the overall rate is not just the death rate).",
    ],
)
def death_overs(f: Filters, role: str = "batting", min_balls: int | None = None, top: int = 40) -> pd.DataFrame:
    ph = phase_sql()
    if role == "batting":
        inn, params = batter_innings(f, [(ph, "phase")])   # one row per batter x innings x phase
        sql = f"""
        WITH a AS (
            SELECT batter, COUNT(DISTINCT match_id)::INTEGER AS matches,
                   SUM(runs) AS total_runs, SUM(balls) AS total_balls, SUM(fours + sixes) AS bounds, SUM(out) AS outs,
                   COUNT(DISTINCT match_id || '-' || innings) FILTER (WHERE phase = 'death' AND balls > 0)::INTEGER AS death_innings,
                   SUM(runs) FILTER (WHERE phase = 'death') AS death_runs,
                   SUM(balls) FILTER (WHERE phase = 'death') AS death_balls,
                   SUM(fours + sixes) FILTER (WHERE phase = 'death') AS death_bounds,
                   SUM(out) FILTER (WHERE phase = 'death') AS death_outs
            FROM ({inn}) GROUP BY batter
        )
        SELECT batter, matches, total_runs::INTEGER AS total_runs, total_balls::INTEGER AS total_balls,
               {ratio("total_runs", "total_balls", 100.0)} AS overall_sr,
               death_innings, death_runs::INTEGER AS death_runs, death_balls::INTEGER AS death_balls,
               {ratio("death_runs", "death_balls", 100.0)} AS death_sr,
               {ratio("death_runs * 1.0 / death_balls", "total_runs * 1.0 / total_balls", 100.0, 1)} AS death_index,
               {ratio("death_bounds", "death_balls", 100.0, 1)} AS death_boundary_pct,
               {ratio("bounds", "total_balls", 100.0, 1)} AS overall_boundary_pct,
               death_outs::INTEGER AS death_dismissals,
               {ratio("death_runs", "death_outs", 1.0, 1)} AS death_avg
        FROM a WHERE total_balls >= 3 * ? AND death_balls >= ?
        ORDER BY death_index DESC NULLS LAST, batter LIMIT ?"""
        mb = int(min_balls if min_balls is not None else 15)
        return query(sql, params + [mb, mb, int(top)])

    where, params = f.where("bowl")
    sql = f"""
    WITH a AS (
        SELECT d.bowler, COUNT(DISTINCT d.match_id)::INTEGER AS matches, {bowl_cols()}, {bowl_cols("death_", f"{ph} = 'death'")},
               COUNT(DISTINCT d.match_id) FILTER (WHERE {ph} = 'death')::INTEGER AS death_innings
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
        GROUP BY d.bowler
    )
    SELECT bowler, matches, {ratio("runs_conceded", "legal_balls", 6.0)} AS overall_economy, wickets AS total_wickets,
           death_innings, death_runs_conceded AS death_runs, death_legal_balls AS death_balls,
           {ratio("death_runs_conceded", "death_legal_balls", 6.0)} AS death_economy, death_wickets,
           {ratio("runs_conceded * 1.0 / legal_balls", "death_runs_conceded * 1.0 / death_legal_balls", 100.0, 1)} AS death_index,
           {ratio("death_dots", "death_legal_balls", 100.0, 1)} AS death_dot_pct,
           {ratio("dots", "legal_balls", 100.0, 1)} AS overall_dot_pct,
           {ratio("death_wickets", "death_legal_balls", 6.0)} AS death_wickets_per_over
    FROM a WHERE legal_balls >= 3 * ? AND death_legal_balls >= ?
    ORDER BY death_index DESC NULLS LAST, bowler LIMIT ?"""
    mb = int(min_balls if min_balls is not None else 30)
    return query(sql, params + [mb, mb, int(top)])
