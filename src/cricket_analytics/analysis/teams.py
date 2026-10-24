"""Team records: played / won / lost / tied / no result, win%, toss and bat-first vs chase splits."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import MATCH_OUTCOME

# group_by -> (extra group columns, ORDER BY)
_GROUPS = {
    "team": ("", "win_pct DESC NULLS LAST, played DESC"),
    "season": (", t.competition, t.season", "t.team, MIN(t.date)"),
}


@module(
    id="teams",
    title="Team records",
    category="basic",
    description="Per-team matches played, won, lost, tied, no result, win%, toss wins, and bat-first vs chasing "
                "records, for any competition, season, venue or opposition.",
    params=[
        *std("team", "opposition", "competition", "season", "venue"),
        ParamSpec("group_by", "choice", default="team", choices=tuple(_GROUPS),
                  help="team = one row per team; season = per team per season"),
        ParamSpec("min_matches", "int", default=0, help="Hide teams with fewer matches than this"),
    ],
    caveats=[
        "win_pct = won / (won + lost): decided matches only. Ties without a winner and no-results are left out of the denominator.",
        "Matches settled in a super over (or bowl-out) count as a win for the tie-break winner: ingest stores it in "
        "matches.winner and keeps result = 'tie' (outcome_method says how). `tied` = tie with no tie-break winner.",
        "bat_first_* uses the team that batted in innings 1 (not team1, not the toss).",
        "Team names are as in the data; renamed franchises (e.g. Delhi Daredevils / Capitals) are separate unless ingest normalised them.",
        "team filters to that team's rows; opposition keeps matches against that side.",
    ],
)
def teams(f: Filters, group_by: str = "team", min_matches: int = 0) -> pd.DataFrame:
    g, order = _GROUPS[group_by]
    where, wp = f.where("match")
    # unpivot team1/team2 to one row per team per match; `team` / `opposition` then narrow the rows
    narrow, np_ = "", []
    if f.team:
        narrow, np_ = " AND t.team = ?", [f.team]
    elif f.opposition:
        narrow, np_ = " AND t.team <> ?", [f.opposition]
    sql = f"""
    WITH mo AS ({MATCH_OUTCOME}),
    t AS (
        SELECT m.match_id, m.date, m.team1 AS team, m.competition, m.season, m.toss_winner, m.result
        FROM matches m WHERE {where}
        UNION ALL
        SELECT m.match_id, m.date, m.team2, m.competition, m.season, m.toss_winner, m.result
        FROM matches m WHERE {where}
    )
    SELECT t.team{g},
           COUNT(*)::INTEGER AS played,
           COUNT(*) FILTER (WHERE mo.winner = t.team)::INTEGER AS won,
           COUNT(*) FILTER (WHERE mo.winner IS NOT NULL AND mo.winner <> t.team)::INTEGER AS lost,
           COUNT(*) FILTER (WHERE mo.winner IS NULL AND t.result = 'tie')::INTEGER AS tied,
           COUNT(*) FILTER (WHERE mo.winner IS NULL AND t.result IS DISTINCT FROM 'tie')::INTEGER AS no_result,
           ROUND(COUNT(*) FILTER (WHERE mo.winner = t.team) * 100.0
                 / NULLIF(COUNT(*) FILTER (WHERE mo.winner IS NOT NULL), 0), 1) AS win_pct,
           COUNT(*) FILTER (WHERE t.toss_winner = t.team)::INTEGER AS toss_won,
           COUNT(*) FILTER (WHERE t.toss_winner = t.team AND mo.winner = t.team)::INTEGER AS won_after_toss_win,
           COUNT(*) FILTER (WHERE mo.bat_first = t.team)::INTEGER AS bat_first_matches,
           COUNT(*) FILTER (WHERE mo.bat_first = t.team AND mo.winner = t.team)::INTEGER AS bat_first_wins,
           COUNT(*) FILTER (WHERE mo.bat_first <> t.team)::INTEGER AS chase_matches,
           COUNT(*) FILTER (WHERE mo.bat_first <> t.team AND mo.winner = t.team)::INTEGER AS chase_wins
    FROM t JOIN mo USING (match_id)
    WHERE 1=1{narrow}
    GROUP BY t.team{g}
    HAVING COUNT(*) >= ?
    ORDER BY {order}
    """
    return query(sql, wp + wp + np_ + [int(min_matches)])
