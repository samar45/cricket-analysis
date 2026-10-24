"""Batting partnerships. A stand runs from one wicket to the next inside an innings."""

from dataclasses import replace

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, DISMISSAL

# group_by -> (extra select, group columns, order by) on the `stands` CTE
_GROUPS = {
    "pair": ("batter1, batter2", "batter1, batter2", "runs DESC, balls"),
    "wicket": ("wicket_no", "wicket_no", "wicket_no"),
    "stand": ("batter1, batter2, wicket_no, match_id, date, team, opposition, unbroken",
              None, "runs DESC, balls"),
}


@module(
    id="partnerships",
    title="Batting partnerships",
    category="intermediate",
    description="Real partnerships: the runs two batters add between one wicket and the next. List the best "
                "individual stands, total up each pair, or group by wicket number.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue"),
        ParamSpec("group_by", "choice", default="pair", choices=tuple(_GROUPS),
                  help="pair = totals per pair of batters; stand = each individual stand; wicket = per wicket number"),
        ParamSpec("top", "int", default=50, help="Maximum rows returned (ignored for wicket)"),
    ],
    caveats=[
        "A stand ends at ANY fall of a wicket or retirement (including retired hurt); runs on that ball belong to the stand. "
        "Runs include extras, balls are balls faced by the two batters (wides excluded).",
        "wicket_no = dismissals before the stand + 1 (retired hurt / retired not out do not add to the count).",
        "player = any stand that batter was part of. The phase filter is not supported (a stand spans phases).",
        "unbroken = the innings ended while the pair was still together (chase completed, overs ran out).",
        "Super-over stands are excluded.",
    ],
)
def partnerships(f: Filters, group_by: str = "pair", top: int = 50) -> pd.DataFrame:
    sel, grp, order = _GROUPS[group_by]
    where, params = replace(f, player=None, phase=None).where("bat")
    pl = ""
    if f.player:
        pl, params_pl = " WHERE ? IN (batter1, batter2)", [f.player]
    else:
        params_pl = []
    # stand_no counts every wicket/retirement before a ball (window frame excludes the ball itself).
    sql = f"""
    WITH b AS (
        SELECT d.match_id, d.innings, d.ball_seq, m.date, d.batting_team, d.bowling_team,
               LEAST(d.batter, d.non_striker) AS batter1, GREATEST(d.batter, d.non_striker) AS batter2,
               d.runs_total, ({BALL_FACED})::INTEGER AS faced, (d.player_out IS NOT NULL)::INTEGER AS ended,
               ({DISMISSAL})::INTEGER AS dismissal
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
    ),
    e AS (
        SELECT *,
               COALESCE(SUM(ended) OVER w, 0)::INTEGER AS stand_no,
               (COALESCE(SUM(dismissal) OVER w, 0) + 1)::INTEGER AS wicket_no
        FROM b WINDOW w AS (PARTITION BY match_id, innings ORDER BY ball_seq ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
    ),
    stands AS (
        SELECT match_id, innings, stand_no, batter1, batter2, MIN(wicket_no) AS wicket_no, MIN(date) AS date,
               any_value(batting_team) AS team, any_value(bowling_team) AS opposition,
               SUM(runs_total)::INTEGER AS runs, SUM(faced)::INTEGER AS balls, (MAX(ended) = 0) AS unbroken
        FROM e GROUP BY match_id, innings, stand_no, batter1, batter2
    ),
    s AS (SELECT * FROM stands{pl})
    """
    if group_by == "stand":
        sql += f"""
        SELECT {sel}, runs, balls, ROUND(runs * 100.0 / NULLIF(balls, 0), 1) AS strike_rate
        FROM s ORDER BY {order} LIMIT ?
        """
        return query(sql, params + params_pl + [int(top)])
    sql += f"""
    SELECT {sel},
           COUNT(*)::INTEGER AS stands,
           SUM(runs)::INTEGER AS runs,
           SUM(balls)::INTEGER AS balls,
           ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 1) AS strike_rate,
           MAX(runs)::INTEGER AS highest_stand,
           ROUND(AVG(runs), 1) AS average_stand,
           COUNT(*) FILTER (WHERE runs >= 50)::INTEGER AS fifty_stands,
           COUNT(*) FILTER (WHERE runs >= 100)::INTEGER AS hundred_stands
    FROM s GROUP BY {grp} ORDER BY {order}
    """
    if group_by == "pair":
        sql += " LIMIT ?"
        return query(sql, params + params_pl + [int(top)])
    return query(sql, params + params_pl)
