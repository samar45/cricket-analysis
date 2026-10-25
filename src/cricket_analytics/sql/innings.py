"""Shared building blocks that are bigger than a one-line fragment."""

from dataclasses import replace

from .filters import Filters
from .fragments import BALL_FACED, DISMISSAL, IS_DOT, IS_FOUR, IS_SIX


def batter_innings(f: Filters, groups: list[tuple[str, str]] | None = None) -> tuple[str, list]:
    """SQL (no WITH) for one row per batter x group keys x match x innings, plus its bind params.

    Columns: batter, <group names>, match_id, innings, date, runs, balls, fours, sixes, dots, out (0/1).
    `groups` = [(sql expr, output name)], e.g. [("m.season", "season")]; they become part of the key.

    An innings exists when the batter faced a ball OR was dismissed (so a non-striker run out before
    facing a ball is an innings of 0 runs, 0 balls, out). Dismissals come from `player_out`, so they
    count for the striker and the non-striker alike. A batter who stayed not out at the non-striker's end
    without facing a ball has NO innings here (indistinguishable from "did not bat" without extra work).
    Filters: team/opposition/venue/season/competition/phase apply to both halves; `player` is the batter
    for the faced balls and `player_out` for the dismissals.
    """
    groups = [("m.date", "date")] + list(groups or [])
    sel = "".join(f", {e} AS {n}" for e, n in groups)
    names = "".join(f", {n}" for _, n in groups)
    w_faced, p_faced = f.where("bat")
    w_out, p_out = replace(f, player=None).where("bat")
    if f.player:
        w_out += " AND d.player_out = ?"
        p_out = p_out + [f.player]
    sql = f"""
        SELECT batter{names}, match_id, innings,
               COALESCE(runs, 0)::INTEGER AS runs, COALESCE(balls, 0)::INTEGER AS balls,
               COALESCE(fours, 0)::INTEGER AS fours, COALESCE(sixes, 0)::INTEGER AS sixes,
               COALESCE(dots, 0)::INTEGER AS dots, COALESCE(out, 0)::INTEGER AS out
        FROM (
            SELECT d.batter AS batter{sel}, d.match_id, d.innings,
                   SUM(d.runs_batter) AS runs,
                   COUNT(*) FILTER (WHERE {BALL_FACED}) AS balls,
                   COUNT(*) FILTER (WHERE {IS_FOUR}) AS fours,
                   COUNT(*) FILTER (WHERE {IS_SIX}) AS sixes,
                   COUNT(*) FILTER (WHERE {IS_DOT}) AS dots
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            WHERE {w_faced}
            GROUP BY ALL
        ) faced
        FULL OUTER JOIN (
            SELECT d.player_out AS batter{sel}, d.match_id, d.innings, 1 AS out
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            WHERE {w_out} AND {DISMISSAL}
            GROUP BY ALL
        ) outs USING (batter{names}, match_id, innings)
    """
    return sql, p_faced + p_out
