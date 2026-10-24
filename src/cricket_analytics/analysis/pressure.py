"""Real pressure: how a player does in chases when the asking rate or the wickets lost squeeze, against calm chase overs."""

from dataclasses import replace

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.extra import bowl_cols, ratio
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, DISMISSAL, IS_FOUR, IS_SIX
from ..sql.state import LEVELS, ball_state, pressure_cond

MIN_BALLS = 60


@module(
    id="pressure",
    title="Performance under pressure",
    category="advanced",
    description="Batters: strike rate and average in chase balls under pressure vs calm chase balls. Bowlers: economy and "
                "wickets when the chasing side is under pressure vs not. Pressure = the asking rate is 10+ an over, or 5+ "
                "wickets are down with 5+ overs left (level picks the rule). Chases only; D/L and shortened matches left out.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec("level", "choice", default="high", choices=tuple(LEVELS),
                  help="high = required rate >= 10 or 5+ down with 30+ balls left; extreme = required rate >= 12; collapse = 5+ down with 30+ balls left"),
        ParamSpec("min_balls", "int", help="Hide players with fewer pressure balls than this (default 60 in a ranking; 1 when you pick one player)"),
        ParamSpec("top", "int", default=40, help="Rows to return"),
    ],
    caveats=[
        "Second innings only: pressure needs a target. First-innings balls are in neither column. 'calm' = the other balls of trusted chases, so both columns come from the same kind of match.",
        "Matches decided by D/L or awarded, and matches whose first innings was cut short (not 20 overs / 100 balls and not all out), are left out because the target or the balls left cannot be trusted.",
        "Rates are runs per 6 balls, also for The Hundred. 'Wickets down' counts every dismissal incl. run outs; a ball in the middle of a chase is judged by the state BEFORE it.",
        "Selection bias: a batter is under pressure mostly when his side is behind, and teams chase well more often against weak bowling, so strike rates under pressure are not 'clutch ability'. Small samples swing a lot: 60 balls is about +/-13% on a strike rate.",
        "The pressure score (required rate + wickets down) is a rule of thumb, not a win probability.",
    ],
)
def pressure(f: Filters, role: str = "batting", level: str = "high", min_balls: int | None = None, top: int = 40) -> pd.DataFrame:
    if min_balls is None:
        min_balls = 1 if getattr(f, "player", None) else MIN_BALLS
    st, sp = ball_state(f)
    cond = pressure_cond(level)
    flag = f"CASE WHEN {cond} THEN 'p' ELSE 'c' END"
    chase = "d.is_chase AND d.trusted AND d.balls_remaining >= 1"
    if role == "batting":
        wf, pf = f.where("bat")
        wo, po = replace(f, player=None).where("bat")
        if f.player:
            wo += " AND d.player_out = ?"
            po = po + [f.player]
        sql = f"""
        WITH d AS ({st}),
        e AS (
            SELECT d.batter AS who, {flag} AS k, d.runs_batter AS runs, CASE WHEN {BALL_FACED} THEN 1 ELSE 0 END AS balls,
                   CASE WHEN {IS_FOUR} OR {IS_SIX} THEN 1 ELSE 0 END AS bnd, 0 AS out
            FROM d JOIN matches m ON d.match_id = m.match_id WHERE {wf} AND {chase}
            UNION ALL
            SELECT d.player_out, {flag}, 0, 0, 0, 1
            FROM d JOIN matches m ON d.match_id = m.match_id WHERE {wo} AND {chase} AND {DISMISSAL}
        ),
        a AS (SELECT who, SUM(runs) FILTER (WHERE k='p') AS pr, SUM(balls) FILTER (WHERE k='p') AS pb, SUM(out) FILTER (WHERE k='p') AS po,
                     SUM(bnd) FILTER (WHERE k='p') AS pbn,
                     SUM(runs) FILTER (WHERE k='c') AS cr, SUM(balls) FILTER (WHERE k='c') AS cb, SUM(out) FILTER (WHERE k='c') AS co
              FROM e GROUP BY who)
        SELECT who AS batter, COALESCE(pb, 0)::INTEGER AS pressure_balls, COALESCE(pr, 0)::INTEGER AS pressure_runs,
               COALESCE(po, 0)::INTEGER AS pressure_outs,
               {ratio("pr", "pb", 100.0)} AS pressure_sr, {ratio("pr", "po")} AS pressure_avg,
               {ratio("pbn", "pb", 100.0, 1)} AS pressure_boundary_pct,
               COALESCE(cb, 0)::INTEGER AS calm_balls, COALESCE(cr, 0)::INTEGER AS calm_runs, COALESCE(co, 0)::INTEGER AS calm_outs,
               {ratio("cr", "cb", 100.0)} AS calm_sr, {ratio("cr", "co")} AS calm_avg,
               ROUND({ratio("pr", "pb", 100.0)} - {ratio("cr", "cb", 100.0)}, 2) AS sr_change
        FROM a WHERE COALESCE(pb, 0) >= ? ORDER BY pressure_sr DESC NULLS LAST, batter LIMIT ?"""
        return query(sql, sp + pf + po + [int(min_balls), int(top)])
    w, p = f.where("bowl")
    inner = f"""
    WITH d AS ({st})
    SELECT bowler,
           {bowl_cols("pressure_", f"{flag} = 'p'")},
           {bowl_cols("calm_", f"{flag} = 'c'")}
    FROM d JOIN matches m ON d.match_id = m.match_id WHERE {w} AND {chase} GROUP BY bowler"""
    sql = f"""
    SELECT bowler, pressure_legal_balls, pressure_runs_conceded, pressure_wickets,
           {ratio("pressure_runs_conceded", "pressure_legal_balls", 6.0)} AS pressure_economy,
           {ratio("pressure_dots", "pressure_legal_balls", 100.0, 1)} AS pressure_dot_pct,
           calm_legal_balls, calm_runs_conceded, calm_wickets,
           {ratio("calm_runs_conceded", "calm_legal_balls", 6.0)} AS calm_economy,
           ROUND({ratio("pressure_runs_conceded", "pressure_legal_balls", 6.0)} - {ratio("calm_runs_conceded", "calm_legal_balls", 6.0)}, 2) AS economy_change
    FROM ({inner}) WHERE pressure_legal_balls >= ? ORDER BY pressure_economy ASC NULLS LAST, bowler LIMIT ?"""
    return query(sql, sp + p + [int(min_balls), int(top)])
