"""Innings list: a player's individual innings or bowling spells, match by match (debut, last N, best)."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BOWLER_WICKET, DISMISSAL, LEGAL_BALL, RUNS_CONCEDED
from ..sql.innings import batter_innings

_RESULT = """CASE WHEN m.winner IS NULL THEN COALESCE(m.result, 'no result')
                    WHEN m.winner = {team} THEN 'won' ELSE 'lost' END"""
_ORDER = {  # (batting, bowling) ORDER BY for each `order`
    "first": ("date, match_id, innings", "date, match_id, innings"),
    "last": ("date DESC, match_id DESC, innings DESC", "date DESC, match_id DESC, innings DESC"),
    "best": (
        "runs DESC, out ASC, balls ASC, date DESC",
        "wickets DESC, runs ASC, balls DESC, date DESC",
    ),
}


_OUTER_BEST = (
    "runs DESC, (how_out = 'not out') DESC, balls ASC, date DESC",
    "wickets DESC, runs ASC, balls DESC, date DESC",
)


@module(
    id="innings_list",
    title="Innings list (debut, last N matches, best innings)",
    category="basic",
    description="A player's debut match, first or last N matches or innings, match-by-match scorecard lines and best "
    "innings or bowling figures: one row per innings (batting) or bowling spell with date, opponent, venue, "
    "runs, balls, how out, wickets and result. Use order=first n=1 for a debut, order=last n=5 for the last "
    "5 matches, order=best for the highest score or best figures; leave the player out for the highest "
    "scores or best figures at a venue or in a season.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue"),
        ParamSpec(
            "role",
            "choice",
            default="batting",
            choices=("batting", "bowling"),
            help="batting: runs and balls; bowling: wickets and runs conceded",
        ),
        ParamSpec(
            "order",
            "choice",
            default="last",
            choices=("first", "last", "best"),
            help="first = earliest (debut), last = most recent, best = most runs / best figures",
        ),
        ParamSpec("n", "int", default=10, help="How many innings or spells to return"),
    ],
    caveats=[
        "'Debut' = the player's first innings in the filtered data (e.g. his first IPL innings with competition=ipl); "
        "Cricsheet has no debut flag, and a match where he only fielded or did not bat is not listed.",
        "Batting: a batter who stayed not out at the non-striker's end without facing a ball has no innings here.",
        "Batting position = order of first appearance at the crease (striker or non-striker) in that innings.",
        "Bowling figures are runs conceded (bat runs + wides + no-balls) and wickets credited to the bowler (no run outs). "
        "'best' = most wickets, then fewest runs.",
        "Super-over innings are excluded by default.",
    ],
)
def innings_list(
    f: Filters, role: str = "batting", order: str = "last", n: int = 10
) -> pd.DataFrame:
    n = max(int(n), 1)
    bat = role == "batting"
    top_order = _ORDER[order][0 if bat else 1]
    if bat:
        inn, params = batter_innings(
            f, [("m.season", "season"), ("m.venue", "venue"), ("m.competition", "competition")]
        )
        core = f"SELECT batter AS player, date, season, venue, competition, match_id, innings, runs, balls, fours, sixes, out FROM ({inn})"
    else:
        where, params = f.where("bowl")
        core = f"""
        SELECT d.bowler AS player, m.date, m.season, m.venue, m.competition, d.match_id, d.innings,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET})::INTEGER AS wickets,
               SUM({RUNS_CONCEDED})::INTEGER AS runs,
               COUNT(*) FILTER (WHERE {LEGAL_BALL})::INTEGER AS balls,
               COALESCE(any_value(m.balls_per_over), 6) AS bpo, any_value(d.bowling_team) AS team, any_value(d.batting_team) AS opposition
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where} GROUP BY d.bowler, m.date, m.season, m.venue, m.competition, d.match_id, d.innings"""
    ids = "SELECT match_id FROM top"
    if bat:
        sql = f"""
        WITH top AS (SELECT * FROM ({core}) ORDER BY {top_order} LIMIT {n}),
        ctx AS (SELECT match_id, innings, any_value(batting_team) AS team, any_value(bowling_team) AS opposition
                FROM deliveries WHERE match_id IN ({ids}) GROUP BY match_id, innings),
        seen AS (SELECT match_id, innings, name, MIN(ball_seq) AS first_seq FROM (
                     SELECT match_id, innings, batter AS name, ball_seq FROM deliveries WHERE match_id IN ({ids})
                     UNION ALL
                     SELECT match_id, innings, non_striker, ball_seq FROM deliveries WHERE match_id IN ({ids}))
                 GROUP BY ALL),
        pos AS (SELECT match_id, innings, name, ROW_NUMBER() OVER (PARTITION BY match_id, innings ORDER BY first_seq) AS position FROM seen),
        outs AS (SELECT d.match_id, d.innings, d.player_out AS name, any_value(d.wicket_type) AS how_out,
                        any_value(CASE WHEN {BOWLER_WICKET} THEN d.bowler END) AS bowler
                 FROM deliveries d WHERE d.match_id IN ({ids}) AND {DISMISSAL} GROUP BY ALL)
        SELECT t.date, t.season, t.competition, t.player, c.team, c.opposition, t.venue, p.position::INTEGER AS position,
               t.runs, t.balls, t.fours, t.sixes, ROUND(t.runs * 100.0 / NULLIF(t.balls, 0), 1) AS strike_rate,
               t.runs::VARCHAR || CASE WHEN t.out = 0 THEN '*' ELSE '' END AS score,
               COALESCE(o.how_out, 'not out') AS how_out, o.bowler,
               {_RESULT.format(team="c.team")} AS result, t.match_id, t.innings
        FROM top t JOIN matches m USING (match_id)
        LEFT JOIN ctx c USING (match_id, innings)
        LEFT JOIN pos p ON p.match_id = t.match_id AND p.innings = t.innings AND p.name = t.player
        LEFT JOIN outs o ON o.match_id = t.match_id AND o.innings = t.innings AND o.name = t.player
        """
        return query(
            f"SELECT * FROM ({sql}) ORDER BY {_OUTER_BEST[0] if order == 'best' else top_order}",
            params,
        )
    sql = f"""
    WITH top AS (SELECT * FROM ({core}) ORDER BY {top_order} LIMIT {n})
    SELECT t.date, t.season, t.competition, t.player, t.team, t.opposition, t.venue,
           t.balls // t.bpo || '.' || t.balls % t.bpo AS overs, t.runs, t.wickets,
           t.wickets || '/' || t.runs AS figures, t.balls,
           ROUND(t.runs * t.bpo * 1.0 / NULLIF(t.balls, 0), 2) AS economy,
           {_RESULT.format(team="t.team")} AS result, t.match_id, t.innings
    FROM top t JOIN matches m USING (match_id)
    """
    return query(
        f"SELECT * FROM ({sql}) ORDER BY {_OUTER_BEST[1] if order == 'best' else top_order}", params
    )
