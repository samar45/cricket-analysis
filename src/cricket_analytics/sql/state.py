"""Per-ball match state (score, wickets, balls left, target, required rate) and the pressure label.

`ball_state(f)` returns (sql, params): every ball of the matches in scope (competition, season, venue; innings 1-2
unless super overs are included) with the state BEFORE the ball. The windows run over the whole innings, so filter on
player/team/phase OUTSIDE it: `FROM ({sql}) d JOIN matches m ON d.match_id = m.match_id WHERE {f.where('bat')}`
(the sql returns `d.*` too, so the usual `d.` / `m.` filters work).

Columns added: score_before, wickets_before, legal_before (legal balls bowled), balls_remaining, current_rr, is_chase,
target (innings-2 only: first-innings total + 1), runs_needed, required_rr, trusted, pressure_score, under_pressure.
All "rr" are runs per 6 balls (also for The Hundred, so one threshold fits every format).

Trusted = the target and the length of the innings can be believed: the match is NOT decided by D/L or awarded
(matches.outcome_method), AND the first innings was complete (all 20 overs / 100 balls bowled, or all out).
A ball with no balls left (11 T20I matches bowl a 121st legal ball) also gets NULL. A match that is not trusted gets NULL for target, runs_needed, required_rr, pressure_score, under_pressure (never a guess).
First innings: no target, so pressure is NULL there too (this module measures chase pressure only).

Pressure rule (why: in a chase the two things that squeeze a batter are the asking rate and lost wickets):
    high     required_rr >= 10  OR  (wickets_before >= 5 AND balls_remaining >= 30)   <- default label
    extreme  required_rr >= 12
    collapse wickets_before >= 5 AND balls_remaining >= 30   (5 down with at least 5 overs to go: the rebuild)
pressure_score = required_rr + wickets_before. A heuristic of "runs per over harder than a free hit" (each wicket lost
costs about one run an over of difficulty); not calibrated against win probability.
"""

from dataclasses import replace

from .filters import Filters
from .fragments import DISMISSAL, LEGAL_BALL

LEVELS = {
    "high": "(required_rr >= 10 OR (wickets_before >= 5 AND balls_remaining >= 30))",
    "extreme": "(required_rr >= 12)",
    "collapse": "(wickets_before >= 5 AND balls_remaining >= 30)",
}


def pressure_cond(level: str = "high") -> str:
    """SQL boolean over ball_state columns; NULL (not false) when the ball has no trusted target."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {sorted(LEVELS)}, not {level!r}")
    return LEVELS[level]


def ball_state(f: Filters) -> tuple[str, list]:
    base = replace(f, team=None, opposition=None, player=None, phase=None)  # match-level scope only
    where, params = base.where("match")
    wk = f"CASE WHEN {DISMISSAL} THEN 1 ELSE 0 END"
    lg = f"CASE WHEN {LEGAL_BALL} THEN 1 ELSE 0 END"
    sql = f"""
    SELECT s.*,
           CASE WHEN is_chase AND trusted AND balls_remaining >= 1 THEN target - score_before END AS runs_needed,
           CASE WHEN is_chase AND trusted AND balls_remaining >= 1 THEN ROUND((target - score_before) * 6.0 / balls_remaining, 2) END AS required_rr,
           CASE WHEN is_chase AND trusted AND balls_remaining >= 1 THEN ROUND((target - score_before) * 6.0 / balls_remaining + wickets_before, 2) END AS pressure_score
    FROM (
        SELECT t.*, t.innings = 2 AS is_chase,
               ROUND(t.score_before * 6.0 / NULLIF(t.legal_before, 0), 2) AS current_rr,
               t.max_balls - t.legal_before AS balls_remaining,
               CASE WHEN t.innings = 2 AND t.trusted THEN t.first_total + 1 END AS target
        FROM (
            SELECT d.*, m.balls_per_over * 20 AS max_balls,
                   SUM(d.runs_total) OVER w - d.runs_total AS score_before,
                   SUM({wk}) OVER w - {wk} AS wickets_before,
                   SUM({lg}) OVER w - {lg} AS legal_before,
                   fi.first_total,
                   COALESCE(m.outcome_method, '') NOT IN ('D/L', 'Awarded')
                     AND (fi.first_legal >= m.balls_per_over * 20 OR fi.first_wkts >= 10) AS trusted
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            JOIN (SELECT match_id, SUM(runs_total) AS first_total, SUM({lg.replace("d.", "x.")}) AS first_legal,
                         SUM({wk.replace("d.", "x.")}) AS first_wkts
                  FROM deliveries x WHERE innings = 1 GROUP BY match_id) fi ON fi.match_id = d.match_id
            WHERE {where} AND {base.innings_sql()}
            WINDOW w AS (PARTITION BY d.match_id, d.innings ORDER BY d.ball_seq ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        ) t
    ) s
    """
    return sql, params
