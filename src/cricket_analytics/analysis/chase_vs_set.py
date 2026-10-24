"""Setting (1st innings) vs chasing (2nd innings) for a player. Data only, no charts. Team level: see `teams`."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BOWLER_WICKET, LEGAL_BALL, RUNS_CONCEDED
from ..sql.innings import batter_innings

_SETTING = "CASE {i} WHEN 1 THEN 'setting' WHEN 2 THEN 'chasing' ELSE 'super over' END"
_ORDER = "CASE setting WHEN 'setting' THEN 1 WHEN 'chasing' THEN 2 ELSE 3 END"


@module(
    id="chase_vs_set",
    title="Setting vs chasing (players)",
    category="intermediate",
    description="A player's batting (or bowling) when his team sets the target (1st innings) vs when it chases (2nd innings): "
                "runs, average, strike rate (economy for bowlers), and how often his team won when he scored 30+ "
                "(or took 2+ wickets).",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec("threshold", "int", help="A 'big' game: runs scored (batting, default 30) or wickets taken (bowling, default 2)"),
        ParamSpec("min_innings", "int", default=0, help="Hide rows with fewer innings than this"),
    ],
    caveats=[
        "setting = the player's team batted/bowled in innings 1 (the target is being set); chasing = innings 2. "
        "Team-level records are in the `teams` module.",
        "Big game: batting = scored `threshold` runs or more (default 30, a guess at a useful T20 contribution); "
        "bowling = took `threshold` wickets or more (default 2). win_pct = big games his team won / big games with a winner; "
        "ties with no tie-break winner and no-results are left out; a super-over tie-break win counts as a win.",
        "win_pct shows how often a big game and a win went together, not that one caused the other.",
        "Batting follows the batting module's rules (dismissals from player_out, innings exist if he faced a ball or was out).",
        "Bowling: runs conceded = bat runs + wides + no-balls; economy per legal ball; innings = innings bowled.",
        "Super-over innings (innings 3+) are excluded unless include_super_overs, then shown as 'super over'.",
    ],
)
def chase_vs_set(f: Filters, role: str = "batting", threshold: int | None = None, min_innings: int = 0) -> pd.DataFrame:
    big = int(threshold) if threshold is not None else (30 if role == "batting" else 2)
    if role == "batting":
        inn, ip = batter_innings(f)
        sql = f"""
        WITH inn AS ({inn}),
        bt AS (SELECT match_id, innings, any_value(batting_team) AS team FROM deliveries GROUP BY match_id, innings),
        x AS (SELECT i.batter AS player, {_SETTING.format(i='i.innings')} AS setting, i.runs, i.balls, i.out,
                     (i.runs >= ?) AS big, (m.winner IS NOT NULL) AS decided, (m.winner = bt.team) AS won
              FROM inn i JOIN matches m USING (match_id) JOIN bt USING (match_id, innings))
        SELECT player, setting, COUNT(*)::INTEGER AS innings, SUM(1 - out)::INTEGER AS not_outs,
               SUM(runs)::INTEGER AS runs, SUM(balls)::INTEGER AS balls,
               ROUND(SUM(runs) * 1.0 / NULLIF(SUM(out), 0), 2) AS average,
               ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
               COUNT(*) FILTER (WHERE big)::INTEGER AS big_games,
               COUNT(*) FILTER (WHERE big AND decided)::INTEGER AS big_decided,
               COUNT(*) FILTER (WHERE big AND won)::INTEGER AS big_wins,
               ROUND(COUNT(*) FILTER (WHERE big AND won) * 100.0 / NULLIF(COUNT(*) FILTER (WHERE big AND decided), 0), 1) AS win_pct
        FROM x GROUP BY player, setting HAVING COUNT(*) >= ?
        ORDER BY SUM(SUM(runs)) OVER (PARTITION BY player) DESC, player, {_ORDER}
        """
        return query(sql, ip + [big, int(min_innings)])
    where, wp = f.where("bowl")
    sql = f"""
    WITH x AS (
        SELECT d.bowler AS player, {_SETTING.format(i='d.innings')} AS setting, d.match_id,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET}) AS wkts, SUM({RUNS_CONCEDED}) AS runs,
               COUNT(*) FILTER (WHERE {LEGAL_BALL}) AS legal, any_value(m.winner) AS winner, any_value(d.bowling_team) AS team
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where} GROUP BY d.bowler, d.match_id, d.innings
    )
    SELECT player, setting, COUNT(*)::INTEGER AS innings, SUM(wkts)::INTEGER AS wickets,
           SUM(runs)::INTEGER AS runs_conceded, SUM(legal)::INTEGER AS balls,
           ROUND(SUM(runs) * 6.0 / NULLIF(SUM(legal), 0), 2) AS economy,
           ROUND(SUM(runs) * 1.0 / NULLIF(SUM(wkts), 0), 2) AS average,
           COUNT(*) FILTER (WHERE wkts >= ?)::INTEGER AS big_games,
           COUNT(*) FILTER (WHERE wkts >= ? AND winner IS NOT NULL)::INTEGER AS big_decided,
           COUNT(*) FILTER (WHERE wkts >= ? AND winner = team)::INTEGER AS big_wins,
           ROUND(COUNT(*) FILTER (WHERE wkts >= ? AND winner = team) * 100.0
                 / NULLIF(COUNT(*) FILTER (WHERE wkts >= ? AND winner IS NOT NULL), 0), 1) AS win_pct
    FROM x GROUP BY player, setting HAVING COUNT(*) >= ?
    ORDER BY SUM(SUM(wkts)) OVER (PARTITION BY player) DESC, player, {_ORDER}
    """
    return query(sql, wp + [big] * 5 + [int(min_innings)])
