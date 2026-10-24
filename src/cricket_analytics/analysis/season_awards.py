"""Season awards: top N per season for each phase of the innings, and the best debutants of each season."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.extra import bat_cols, bowl_cols, ratio
from ..sql.filters import Filters
from ..sql.fragments import phase_sql

# role -> (player column, stat columns, ORDER BY inside a season, default min balls for phase leaders / debutants)
_BAT = ("batter", f"COUNT(DISTINCT d.match_id)::INTEGER AS matches, {bat_cols()}", "runs DESC, balls ASC", "balls", 20, 15)
_BOWL = ("bowler", f"COUNT(DISTINCT d.match_id)::INTEGER AS matches, {bowl_cols()}", "wickets DESC, runs_conceded ASC", "legal_balls", 30, 24)
_OUT = {
    "batting": ("matches, runs, balls, " + ratio("runs", "balls", 100.0) + " AS strike_rate, fours, sixes, "
                + ratio("fours + sixes", "balls", 100.0, 1) + " AS boundary_pct"),
    "bowling": ("matches, wickets, runs_conceded, legal_balls AS balls, " + ratio("runs_conceded", "legal_balls", 6.0) + " AS economy, "
                + ratio("dots", "legal_balls", 100.0, 1) + " AS dot_pct"),
}


@module(
    id="season_awards",
    title="Season awards",
    category="advanced",
    description="Top N players of every season: per phase of the innings (award=phase_leaders) or among players whose "
                "first season in the competition it was (award=debutants). Batters ranked by runs, bowlers by wickets.",
    params=[
        *std("competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("award", "choice", default="phase_leaders", choices=("phase_leaders", "debutants")),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec("top", "int", default=5, help="Players per season (per phase for phase_leaders)"),
        ParamSpec("min_balls", "int",
                  help="Minimum balls faced (batting) or legal balls bowled (bowling). Default 20/30 for phase leaders, 15/24 for debutants"),
    ],
    caveats=[
        "phase_leaders: ranked within each (competition, season, phase). Leave phase empty to get all three phases.",
        "Debutant = first season the player appears in that role in this database's data for the competition. The first season of each competition is skipped (everyone would be a debutant).",
        "Players who joined from other leagues count as debutants of this competition.",
        "Ties in runs are broken by fewer balls; ties in wickets by fewer runs conceded.",
    ],
)
def season_awards(f: Filters, award: str = "phase_leaders", role: str = "batting", top: int = 5,
                  min_balls: int | None = None) -> pd.DataFrame:
    who, cols, order, ball_col, mb_phase, mb_debut = _BAT if role == "batting" else _BOWL
    side = "bat" if role == "batting" else "bowl"
    mb = int(min_balls if min_balls is not None else (mb_phase if award == "phase_leaders" else mb_debut))
    where, params = f.where(side)
    ph = phase_sql()
    if award == "phase_leaders":
        sql = f"""
        WITH g AS (
            SELECT m.competition, m.season, {ph} AS phase, d.{who} AS player, MIN(m.date) AS first_date, {cols}
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY ALL
        ), r AS (
            SELECT *, MIN(first_date) OVER (PARTITION BY competition, season) AS season_start,
                   ROW_NUMBER() OVER (PARTITION BY competition, season, phase ORDER BY {order}, player) AS rank
            FROM g WHERE {ball_col} >= ?
        )
        SELECT competition, season, phase, rank::INTEGER AS rank, player, {_OUT[role]}
        FROM r WHERE rank <= ?
        ORDER BY competition, season_start DESC,
                 CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END, rank
        """
        return query(sql, params + [mb, int(top)])

    # debutants: first season per (competition, player), ignoring season/venue/team filters
    base = Filters(competition=f.competition)
    base_where, base_params = base.where(side)
    comp_where, comp_params = base.where("match")
    sql = f"""
    WITH debut AS (
        SELECT d.{who} AS player, m.competition, arg_min(m.season, m.date) AS debut_season
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {base_where}
        GROUP BY ALL
    ), first_season AS (
        SELECT competition, arg_min(season, date) AS season FROM matches m
        WHERE {comp_where}
        GROUP BY competition
    ), g AS (
        SELECT m.competition, m.season, d.{who} AS player, MIN(m.date) AS first_date, {cols}
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        JOIN debut ON debut.player = d.{who} AND debut.competition = m.competition AND debut.debut_season = m.season
        JOIN first_season fs ON fs.competition = m.competition AND fs.season <> m.season
        WHERE {where}
        GROUP BY ALL
    ), r AS (
        SELECT *, MIN(first_date) OVER (PARTITION BY competition, season) AS season_start,
               ROW_NUMBER() OVER (PARTITION BY competition, season ORDER BY {order}, player) AS rank
        FROM g WHERE {ball_col} >= ?
    )
    SELECT competition, season, rank::INTEGER AS rank, player, {_OUT[role]}
    FROM r WHERE rank <= ?
    ORDER BY competition, season_start DESC, rank
    """
    return query(sql, base_params + comp_params + params + [mb, int(top)])
