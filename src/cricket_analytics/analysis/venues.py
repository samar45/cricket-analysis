"""Venue summary: scoring levels and how often the side batting first wins."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import DISMISSAL, LEGAL_BALL, MATCH_OUTCOME

# group_by -> (extra matches columns, their names, ORDER BY)
_GROUPS = {
    "venue": (", m.city", ", city", "matches DESC, venue"),
    "season": (", m.competition, m.season", ", competition, season", "venue, MIN(date)"),
}


@module(
    id="venues",
    title="Venue summary",
    category="basic",
    description="Per-venue matches, average 1st and 2nd innings scores, highest and lowest totals and the "
                "bat-first win rate. Top batters/bowlers at a venue: run batting / bowling with the venue filter.",
    params=[
        *std("venue", "competition", "season", "team", "opposition"),
        ParamSpec("group_by", "choice", default="venue", choices=("venue", "season"),
                  help="venue = one row per venue; season = per venue per season"),
        ParamSpec("min_matches", "int", default=1, help="Hide venues with fewer matches than this"),
    ],
    caveats=[
        "Scores are innings totals including extras. Rain-shortened matches are included in the averages and highest totals.",
        "lowest_total only looks at COMPLETED innings (10 wickets down, or the full 20 overs / 100 balls bowled), "
        "so a chase that ended early or a rain-cut innings never counts as a 'low total'.",
        "bat_first_win_pct = matches won by the side that batted in innings 1 / decided matches "
        "(super-over winners count; ties without a winner and no-results are left out).",
        "Super-over innings are excluded from totals.",
        "The same ground can appear under more than one name if the source spells it differently; "
        "ingest normalises the common cases only.",
    ],
)
def venues(f: Filters, group_by: str = "venue", min_matches: int = 1) -> pd.DataFrame:
    gsel, gnames, order = _GROUPS[group_by]
    where, params = f.where("match")
    sql = f"""
    WITH mo AS ({MATCH_OUTCOME}),
    sel AS (SELECT m.match_id, m.date, m.venue, m.balls_per_over{gsel} FROM matches m WHERE {where}),
    inn AS (
        SELECT d.match_id, d.innings, SUM(d.runs_total) AS score,
               (COUNT(*) FILTER (WHERE {DISMISSAL}) >= 10
                OR COUNT(*) FILTER (WHERE {LEGAL_BALL}) >= 20 * any_value(sel.balls_per_over)) AS complete
        FROM deliveries d JOIN sel USING (match_id) WHERE {f.innings_sql()} GROUP BY d.match_id, d.innings
    ),
    per AS (
        SELECT sel.match_id, sel.date, sel.venue{gnames},
               MAX(score) FILTER (WHERE innings = 1) AS s1, MAX(score) FILTER (WHERE innings = 2) AS s2,
               MIN(score) FILTER (WHERE complete) AS low
        FROM sel LEFT JOIN inn USING (match_id) GROUP BY sel.match_id, sel.date, sel.venue{gnames}
    )
    SELECT venue{gnames},
           COUNT(*)::INTEGER AS matches,
           ROUND(AVG(s1), 1) AS avg_1st_innings,
           ROUND(AVG(s2), 1) AS avg_2nd_innings,
           MAX(s1)::INTEGER AS highest_1st_innings,
           MAX(s2)::INTEGER AS highest_2nd_innings,
           MAX(GREATEST(s1, s2))::INTEGER AS highest_total,
           MIN(low)::INTEGER AS lowest_total,
           COUNT(*) FILTER (WHERE mo.winner IS NOT NULL)::INTEGER AS decided,
           COUNT(*) FILTER (WHERE mo.winner = mo.bat_first)::INTEGER AS bat_first_wins,
           ROUND(COUNT(*) FILTER (WHERE mo.winner = mo.bat_first) * 100.0
                 / NULLIF(COUNT(*) FILTER (WHERE mo.winner IS NOT NULL), 0), 1) AS bat_first_win_pct
    FROM per JOIN mo USING (match_id)
    GROUP BY venue{gnames}
    HAVING COUNT(*) >= ?
    ORDER BY {order}
    """
    return query(sql, params + [int(min_matches)])
