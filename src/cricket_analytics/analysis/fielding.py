"""Fielding: catches, stumpings and run-outs per fielder. Data only, no charts."""

from dataclasses import replace

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.attributes import attributes_cte
from ..sql.filters import Filters, _in

_SUB = r"regexp_replace({c}, '\s*\(sub\)\s*$', '', 'i')"  # "X (sub)" -> "X"
_IS_SUB = r"regexp_matches({c}, '\(sub\)\s*$', 'i')"
# every ball gives these (name, own team, other team) triples = who was on the field / at the crease
_ROLES = (
    ("d.batter", "d.batting_team", "d.bowling_team"),
    ("d.non_striker", "d.batting_team", "d.bowling_team"),
    ("d.bowler", "d.bowling_team", "d.batting_team"),
    ("d.fielder", "d.bowling_team", "d.batting_team"),
    ("d.fielder_2", "d.bowling_team", "d.batting_team"),
    ("d.fielder_3", "d.bowling_team", "d.batting_team"),
)
# (fielder column, wicket_type, "direct" expression): a run out is direct when fielder_1 is the only fielder named
_EVENTS = (
    ("d.fielder", "caught", "0"),
    ("d.bowler", "caught and bowled", "0"),
    ("d.fielder", "stumped", "0"),
    ("d.fielder", "run out", "(d.fielder_2 IS NULL)::INTEGER"),
    ("d.fielder_2", "run out", "0"),
    ("d.fielder_3", "run out", "0"),
)


@module(
    id="fielding",
    title="Fielding stats",
    category="intermediate",
    description="Catches, caught-and-bowled, stumpings, run-outs (direct and involved), total dismissals, matches and "
    "dismissals per match for each fielder; by player or by season; filter by role (keeper / outfield).",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec(
            "group_by",
            "choice",
            default="player",
            choices=("player", "season"),
            help="player = one row per fielder; season = one row per fielder per competition season",
        ),
        ParamSpec(
            "role",
            "choice",
            default="all",
            choices=("all", "keeper", "outfield"),
            help="keeper = players marked keeper in the reviewed list; outfield = everyone else",
        ),
        ParamSpec(
            "min_matches", "int", default=0, help="Hide fielders with fewer matches than this"
        ),
        ParamSpec(
            "top", "int", default=0, help="Keep only the N best rows by total dismissals (0 = all)"
        ),
    ],
    caveats=[
        "catches = caught by a named fielder (the keeper's catches included). caught_and_bowled = the bowler catching "
        "his own ball (Cricsheet names no fielder, so it is credited to the bowler), shown separately. "
        "total_dismissals = catches + caught_and_bowled + stumpings + run_outs.",
        "run_outs = the fielder is named in any of the (up to three) fielder slots of a run-out. run_outs_direct = he is "
        "the only fielder named (an unassisted hit or gather-and-break). Cricsheet does not say who threw and who "
        "broke the wicket, so 'run_outs' includes throwers and relayers.",
        "catches_keeper = his catches, if he is a keeper in reference/player_overrides.csv (keeper yes or sometimes; a "
        "'sometimes' keeper's outfield catches are included). Players missing from that list count as outfield. "
        "Stumpings are counted for whoever made them.",
        "Substitute fielders ('Name (sub)') are credited to the named player; sub_dismissals counts those. "
        "No such names exist in the current database.",
        "Cricsheet has a few catches with no fielder recorded; they cannot be credited to anyone.",
        "matches = games where the player appears in any role (batter, non-striker, bowler or fielder) for the team in "
        "scope; unused squad members are not counted. The phase filter limits the dismissals, not matches.",
        "team = the FIELDING side. Super-over innings (3+) are excluded.",
    ],
)
def fielding(
    f: Filters, group_by: str = "player", role: str = "all", min_matches: int = 0, top: int = 0
) -> pd.DataFrame:
    by_season = group_by == "season"
    gm = ", m.competition AS competition, m.season AS season" if by_season else ""
    gc = ", competition, season" if by_season else ""
    join_g = " AND e.competition = a.competition AND e.season = a.season" if by_season else ""
    who = replace(f, player=None)
    ev_where, ev_params = who.where("bowl")
    ap_where, ap_params = replace(who, team=None, opposition=None, phase=None).where("bowl")

    tc, tp = [], []  # team / opposition apply to the player's own side in the appearance rows
    for col, vals in (("team", who.values("team")), ("opp", who.values("opposition"))):
        c, p = _in(col, vals)
        if c:
            tc.append(c)
            tp += p
    tc_sql = "".join(f" AND {c}" for c in tc)

    frm = "FROM deliveries d JOIN matches m ON d.match_id = m.match_id"
    ap_raw = "\nUNION ALL\n".join(
        f"SELECT m.match_id, m.date AS dt{gm}, {n} AS raw, {t} AS team, {o} AS opp {frm} "
        f"WHERE {ap_where} AND {n} IS NOT NULL"
        for n, t, o in _ROLES
    )
    ev_raw = "\nUNION ALL\n".join(
        f"SELECT m.match_id{gm}, {n} AS raw, '{wt}' AS wt, {direct} AS direct {frm} "
        f"WHERE {ev_where} AND d.wicket_type = '{wt}' AND {n} IS NOT NULL"
        for n, wt, direct in _EVENTS
    )
    pl = " AND name = ?" if f.player else ""
    role_c = {"all": "TRUE", "keeper": "pa.keeper IS NOT NULL", "outfield": "pa.keeper IS NULL"}[
        role
    ]
    order = "fielder, first_date" if by_season else "total_dismissals DESC, matches, fielder"
    sql = f"""
    WITH {attributes_cte()},
    apps AS (
        SELECT DISTINCT match_id, dt{gc}, {_SUB.format(c="raw")} AS name
        FROM ({ap_raw}) WHERE NOT {_IS_SUB.format(c="raw")}{tc_sql}
    ),
    ev AS (
        SELECT match_id{gc}, {_SUB.format(c="raw")} AS name, wt, direct, {_IS_SUB.format(c="raw")}::INTEGER AS is_sub
        FROM ({ev_raw})
    ),
    a AS (
        SELECT name{gc}, COUNT(*)::INTEGER AS matches, MIN(dt) AS first_date
        FROM apps WHERE TRUE{pl} GROUP BY name{gc}
    ),
    e AS (
        SELECT name{gc},
               COUNT(*) FILTER (WHERE wt = 'caught')::INTEGER AS catches,
               COUNT(*) FILTER (WHERE wt = 'caught and bowled')::INTEGER AS caught_and_bowled,
               COUNT(*) FILTER (WHERE wt = 'stumped')::INTEGER AS stumpings,
               COUNT(*) FILTER (WHERE wt = 'run out' AND direct = 1)::INTEGER AS run_outs_direct,
               COUNT(*) FILTER (WHERE wt = 'run out')::INTEGER AS run_outs,
               SUM(is_sub)::INTEGER AS sub_dismissals
        FROM ev WHERE TRUE{pl} GROUP BY name{gc}
    ),
    r AS (
        SELECT a.name AS fielder{gc.replace(", ", ", a.")}, a.matches, a.first_date,
               COALESCE(e.catches, 0) AS catches,
               CASE WHEN pa.keeper IS NOT NULL THEN COALESCE(e.catches, 0) ELSE 0 END AS catches_keeper,
               COALESCE(e.caught_and_bowled, 0) AS caught_and_bowled,
               COALESCE(e.stumpings, 0) AS stumpings,
               COALESCE(e.run_outs_direct, 0) AS run_outs_direct,
               COALESCE(e.run_outs, 0) AS run_outs,
               COALESCE(e.sub_dismissals, 0) AS sub_dismissals
        FROM a LEFT JOIN e ON e.name = a.name{join_g} LEFT JOIN pa ON pa.name = a.name
        WHERE {role_c} AND a.matches >= ?
    )
    SELECT fielder{gc}, matches, catches, catches_keeper, caught_and_bowled, stumpings, run_outs_direct, run_outs,
           (catches + caught_and_bowled + stumpings + run_outs)::INTEGER AS total_dismissals,
           ROUND((catches + caught_and_bowled + stumpings + run_outs) * 1.0 / matches, 2) AS per_match,
           sub_dismissals
    FROM r ORDER BY {order}
    """
    pf = [f.player] if f.player else []
    params = ap_params * len(_ROLES) + tp + ev_params * len(_EVENTS) + pf + pf + [int(min_matches)]
    df = query(sql, params)
    return df.head(int(top)) if top and not by_season else df
