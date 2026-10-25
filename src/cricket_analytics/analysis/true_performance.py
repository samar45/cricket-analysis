"""True strike rate / true economy: a player's rate judged against the league rate for the same phases and seasons."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import (
    BALL_FACED,
    BOWLER_WICKET,
    IS_DOT,
    IS_FOUR,
    IS_SIX,
    LEGAL_BALL,
    RUNS_CONCEDED,
    phase_sql,
)


@module(
    id="true_performance",
    title="True strike rate / true economy",
    category="advanced",
    description="Phase-adjusted strike rate (role=batting) or economy (role=bowling). Every ball is compared with the "
    "league rate for the same competition, season and phase (powerplay / middle / death), then scaled to "
    "the league's overall rate.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec(
            "min_balls",
            "int",
            help="Hide players below this many balls (default 30 faced when batting, 60 legal when bowling)",
        ),
        ParamSpec("top", "int", default=40, help="Rows to return (best true rate first)"),
    ],
    caveats=[
        "true_sr = runs / expected runs * league SR. Expected runs = balls faced in each (competition, season, phase) x that cell's league runs per ball.",
        "league = every batter or bowler in the same competition and season, men's only unless competition=t20i_women; it ignores the team, opposition, venue, player and phase filters.",
        "adjustment = true - raw. Batting: negative means the batter faced easy (death-heavy) phases and is marked down. Bowling: negative means the bowler worked in hard phases and is credited.",
        "Phases come from over numbers (The Hundred: first 25 balls powerplay, last 25 death). Wickets fallen, target and venue are not adjusted for.",
    ],
)
def true_performance(
    f: Filters, role: str = "batting", min_balls: int | None = None, top: int = 40
) -> pd.DataFrame:
    base_where, base_params = Filters(competition=f.competition, season=f.season).where("match")
    ph = phase_sql()
    if role == "batting":
        who, side, minb = "batter", "bat", 30
        base_den, base_num, ball = (
            f"COUNT(*) FILTER (WHERE {BALL_FACED})",
            "SUM(d.runs_batter)",
            BALL_FACED,
        )
        runs = "d.runs_batter"
    else:
        who, side, minb = "bowler", "bowl", 60
        base_den, base_num, ball = (
            f"COUNT(*) FILTER (WHERE {LEGAL_BALL})",
            f"SUM{RUNS_CONCEDED}",
            LEGAL_BALL,
        )
        runs = RUNS_CONCEDED
    where, params = f.where(side)
    # base = league runs per ball in each cell and in the whole competition-season (lg_rpb)
    cte = f"""
    WITH cell AS (
        SELECT m.competition, m.season, {ph} AS phase, {base_num} AS runs, {base_den} AS balls
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {base_where} AND {f.innings_sql()}   -- where('match') has no `d`, so add the super-over rule here
        GROUP BY ALL
    ), base AS (
        SELECT competition, season, phase, runs * 1.0 / balls AS rpb,
               SUM(runs) OVER w * 1.0 / SUM(balls) OVER w AS lg_rpb
        FROM cell WINDOW w AS (PARTITION BY competition, season)
    ), agg AS (
        SELECT d.{who} AS player,
               COUNT(DISTINCT d.match_id) AS matches,
               SUM({runs}) AS runs,
               COUNT(*) FILTER (WHERE {ball}) AS balls,
               SUM(CASE WHEN {ball} THEN b.rpb END) AS expected,
               SUM(CASE WHEN {ball} THEN b.lg_rpb END) AS league,
               {_phase_cols(runs, ball, ph, role)}
               {_extra_cols(role)}
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        JOIN base b ON b.competition = m.competition AND b.season = m.season AND b.phase = {ph}
        WHERE {where}
        GROUP BY d.{who}
    )"""
    if role == "batting":
        sel = """
        SELECT player AS batter, matches::INTEGER AS matches, runs::INTEGER AS total_runs, balls::INTEGER AS total_balls,
               ROUND(runs * 100.0 / balls, 2) AS raw_sr,
               ROUND(expected * 100.0 / balls, 2) AS par_sr,
               ROUND(runs / NULLIF(expected, 0) * league * 100.0 / balls, 2) AS true_sr,
               ROUND(runs / NULLIF(expected, 0) * league * 100.0 / balls - runs * 100.0 / balls, 2) AS sr_adjustment,
               fours::INTEGER AS fours, sixes::INTEGER AS sixes,
               sr_powerplay, sr_middle, sr_death
        FROM agg WHERE balls >= ? ORDER BY true_sr DESC NULLS LAST, batter LIMIT ?"""
    else:
        sel = """
        SELECT player AS bowler, matches::INTEGER AS matches, runs::INTEGER AS runs_conceded, balls::INTEGER AS balls,
               wickets::INTEGER AS wickets,
               ROUND(runs * 6.0 / balls, 2) AS raw_economy,
               ROUND(expected * 6.0 / balls, 2) AS par_economy,
               ROUND(runs / NULLIF(expected, 0) * league * 6.0 / balls, 2) AS true_economy,
               ROUND(runs / NULLIF(expected, 0) * league * 6.0 / balls - runs * 6.0 / balls, 2) AS econ_adjustment,
               ROUND(dots * 100.0 / balls, 1) AS dot_pct,
               econ_powerplay, econ_middle, econ_death
        FROM agg WHERE balls >= ? ORDER BY true_economy ASC NULLS LAST, bowler LIMIT ?"""
    return query(
        cte + sel,
        base_params + params + [int(min_balls if min_balls is not None else minb), int(top)],
    )


def _phase_cols(runs: str, ball: str, ph: str, role: str) -> str:
    k, mult, nd = ("sr", 100.0, 2) if role == "batting" else ("econ", 6.0, 2)
    return ", ".join(
        f"ROUND(SUM({runs}) FILTER (WHERE {ph} = '{p}') * {mult} / NULLIF(COUNT(*) FILTER (WHERE {ph} = '{p}' AND {ball}), 0), {nd}) AS {k}_{p}"
        for p in ("powerplay", "middle", "death")
    )


def _extra_cols(role: str) -> str:
    if role == "batting":
        return f", COUNT(*) FILTER (WHERE {IS_FOUR}) AS fours, COUNT(*) FILTER (WHERE {IS_SIX}) AS sixes"
    return f", COUNT(*) FILTER (WHERE {BOWLER_WICKET}) AS wickets, COUNT(*) FILTER (WHERE {IS_DOT}) AS dots"
