"""Home vs away vs neutral: a player's or a team's record split by where the match was played."""

from dataclasses import replace
from functools import lru_cache

import pandas as pd

from ..db import _reader, query
from ..reference import REFERENCE_DIR
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BOWLER_WICKET, LEGAL_BALL, MATCH_OUTCOME, RUNS_CONCEDED
from ..sql.innings import batter_innings

LOCATIONS = ("home", "away", "neutral")


@lru_cache(maxsize=1)
def _reference() -> tuple[pd.DataFrame, dict]:
    """(venue table keyed by venue+city, team -> (kind, set of home places, set of seasons with no home games))."""
    venues = pd.read_csv(REFERENCE_DIR / "venue_country.csv", keep_default_na=False)
    teams = {}
    for r in pd.read_csv(REFERENCE_DIR / "team_home.csv", keep_default_na=False).itertuples():
        teams[r.team] = (r.kind, {x for x in r.home.split(";") if x}, {x for x in r.no_home_seasons.split(";") if x})
    return venues, teams


def match_sides(f: Filters) -> pd.DataFrame:
    """One row per match x side in scope: match_id, team, opp, location ('home'|'away'|'neutral'|'unknown').

    National teams: home = the venue's country or region is the team's home place. Franchises: home = the venue's
    site is one of the team's home sites (and the season is not one played away from home, e.g. IPL 2009/2021/2022).
    Away = the venue is home for the opposition; neutral = home for neither.
    """
    venues, teams = _reference()
    where, params = replace(f, team=None, opposition=None, player=None, phase=None).where("match")
    m = query(f"SELECT m.match_id, m.venue, COALESCE(m.city, '') AS city, m.team1, m.team2, m.season FROM matches m WHERE {where}", params)
    m = m.merge(venues[["venue", "city", "country", "region", "site"]], on=["venue", "city"], how="left")

    def is_home(team, country, region, site, season):
        kind, places, no_home = teams.get(team, ("", set(), set()))
        if kind == "national":
            return country in places or region in places
        return kind == "franchise" and site in places and season not in no_home

    sides = []
    for a, b in (("team1", "team2"), ("team2", "team1")):
        known = m["site"].notna()
        h_me = [is_home(t, c, r, s, se) for t, c, r, s, se in zip(m[a], m["country"], m["region"], m["site"], m["season"])]
        h_op = [is_home(t, c, r, s, se) for t, c, r, s, se in zip(m[b], m["country"], m["region"], m["site"], m["season"])]
        loc = ["home" if x else "away" if y else "neutral" for x, y in zip(h_me, h_op)]
        sides.append(pd.DataFrame({"match_id": m["match_id"], "team": m[a], "opp": m[b],
                                   "location": [v if k else "unknown" for v, k in zip(loc, known)]}))
    return pd.concat(sides, ignore_index=True)


def _run(sql: str, params: list, sides: pd.DataFrame) -> pd.DataFrame:
    cur = _reader(None).cursor()   # `sides` is registered as view `hv` on this cursor only
    try:
        cur.register("hv", sides)
        return cur.execute(sql, params).fetchdf()
    finally:
        cur.close()


_ORDER = "CASE location WHEN 'home' THEN 1 WHEN 'away' THEN 2 WHEN 'neutral' THEN 3 ELSE 4 END"


@module(
    id="home_away",
    title="Home vs away",
    category="intermediate",
    description="A player's (batting or bowling) or a team's record split into home, away and neutral matches. "
                "Give a player to get his batting or bowling split; give a team (or nothing) to get win % and average scores.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling"),
                  help="For a player: batting or bowling figures. Ignored for team rows"),
    ],
    caveats=[
        "Home/away/neutral comes from reference/venue_country.csv and team_home.csv (hand-made, with a confidence column). "
        "Rows with location 'unknown' are venues missing from that file.",
        "National teams: home = a ground in the team's own country (England includes Wales, Ireland includes Northern Ireland, "
        "West Indies = any Caribbean ground in the file). Franchises: home = the team's home city/grounds.",
        "Away = the ground is the opposition's home; neutral = it is home for neither (a third city, a neutral final, "
        "the UAE in 2014/2020, any T20I in a third country).",
        "IPL 2009 (South Africa), 2020/21, 2021 and 2022 were played away from the franchises' homes, so every match of those seasons is neutral.",
        "A player's side in a match is the team he batted or bowled for in that match (so moves between teams are handled).",
        "Team rows: win_pct = won / (won + lost); avg_runs_* are per innings in the first two innings and include rain-shortened ones.",
    ],
)
def home_away(f: Filters, role: str = "batting") -> pd.DataFrame:
    sides = match_sides(f)
    if f.player and role == "batting":
        inn, p = batter_innings(f, [("d.batting_team", "team")])
        sql = f"""
        WITH inn AS ({inn})
        SELECT batter, location, COUNT(DISTINCT inn.match_id)::INTEGER AS matches, COUNT(*)::INTEGER AS innings,
               SUM(1 - out)::INTEGER AS not_outs, SUM(runs)::INTEGER AS total_runs, SUM(balls)::INTEGER AS balls,
               ROUND(SUM(runs) * 1.0 / NULLIF(SUM(out), 0), 2) AS average,
               ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
               MAX(runs)::INTEGER AS highest,
               COUNT(*) FILTER (WHERE runs BETWEEN 50 AND 99)::INTEGER AS fifties,
               COUNT(*) FILTER (WHERE runs >= 100)::INTEGER AS hundreds
        FROM inn JOIN hv ON hv.match_id = inn.match_id AND hv.team = inn.team
        GROUP BY batter, location ORDER BY batter, {_ORDER}"""
        return _run(sql, p, sides)

    if f.player:
        where, p = f.where("bowl")
        sql = f"""
        SELECT d.bowler AS bowler, location, COUNT(DISTINCT d.match_id)::INTEGER AS matches,
               COUNT(DISTINCT d.match_id || '-' || d.innings)::INTEGER AS innings,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET})::INTEGER AS wickets,
               SUM({RUNS_CONCEDED})::INTEGER AS runs_conceded,
               COUNT(*) FILTER (WHERE {LEGAL_BALL})::INTEGER AS balls,
               ROUND(SUM({RUNS_CONCEDED}) * 6.0 / NULLIF(COUNT(*) FILTER (WHERE {LEGAL_BALL}), 0), 2) AS economy,
               ROUND(SUM({RUNS_CONCEDED}) * 1.0 / NULLIF(COUNT(*) FILTER (WHERE {BOWLER_WICKET}), 0), 2) AS average,
               ROUND(COUNT(*) FILTER (WHERE {LEGAL_BALL}) * 1.0 / NULLIF(COUNT(*) FILTER (WHERE {BOWLER_WICKET}), 0), 2) AS strike_rate
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
             JOIN hv ON hv.match_id = d.match_id AND hv.team = d.bowling_team
        WHERE {where}
        GROUP BY d.bowler, location ORDER BY d.bowler, {_ORDER}"""
        return _run(sql, p, sides)

    teams, opps = f.values("team"), f.values("opposition")
    narrow, p = "", []
    if teams:
        narrow += f" AND hv.team IN ({', '.join('?' * len(teams))})"
        p += teams
    if opps:
        narrow += f" AND hv.opp IN ({', '.join('?' * len(opps))})"
        p += opps
    sql = f"""
    WITH mo AS ({MATCH_OUTCOME}),
    tot AS (SELECT match_id, batting_team AS team, SUM(runs_total) AS runs FROM deliveries d
            WHERE {f.innings_sql()} GROUP BY ALL)
    SELECT hv.team AS team, location, COUNT(*)::INTEGER AS matches,
           COUNT(*) FILTER (WHERE mo.winner = hv.team)::INTEGER AS won,
           COUNT(*) FILTER (WHERE mo.winner IS NOT NULL AND mo.winner <> hv.team)::INTEGER AS lost,
           COUNT(*) FILTER (WHERE mo.winner IS NULL)::INTEGER AS no_result,
           ROUND(COUNT(*) FILTER (WHERE mo.winner = hv.team) * 100.0
                 / NULLIF(COUNT(*) FILTER (WHERE mo.winner IS NOT NULL), 0), 1) AS win_pct,
           ROUND(AVG(own.runs), 1) AS avg_runs_for, ROUND(AVG(oth.runs), 1) AS avg_runs_against
    FROM hv JOIN mo ON mo.match_id = hv.match_id
         LEFT JOIN tot own ON own.match_id = hv.match_id AND own.team = hv.team
         LEFT JOIN tot oth ON oth.match_id = hv.match_id AND oth.team = hv.opp
    WHERE 1=1{narrow}
    GROUP BY hv.team, location ORDER BY matches DESC, hv.team, {_ORDER}"""
    out = _run(sql, p, sides)
    # order: busiest team first, its rows home/away/neutral together
    out["_n"] = out.groupby("team")["matches"].transform("sum")
    out["_o"] = out["location"].map({loc_name: i for i, loc_name in enumerate(LOCATIONS)}).fillna(9)
    return out.sort_values(["_n", "team", "_o"], ascending=[False, True, True]).drop(columns=["_n", "_o"]).reset_index(drop=True)
