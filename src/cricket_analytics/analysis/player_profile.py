"""Player profile: role, keeper, batting slot, bowling type and batting hand, plus a career summary. Data only."""

import dataclasses

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.attributes import BAT_SLOTS, BOWL_KINDS, BOWL_TYPES, ROLES, attributes_cte
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BOWLER_WICKET, LEGAL_BALL

# the attribute columns returned in both modes (each value has its *_source and *_confidence next to it)
_ATTRS = ("pa.gender AS player_gender, pa.matches AS career_matches, pa.role, pa.role_source, pa.role_confidence, "
          "pa.keeper, pa.keeper_source, pa.keeper_confidence, pa.bat_slot, pa.bat_position, pa.bat_slot_source, "
          "pa.bat_slot_confidence, pa.bat_hand, pa.bat_hand_source, pa.bat_hand_confidence, pa.bowl_kind, pa.bowl_type, "
          "pa.bowl_type_source, pa.bowl_type_confidence, pa.bowl_kind_source, pa.bowl_kind_confidence, pa.bowl_phase_role")


@module(
    id="player_profile",
    title="Player profile (role, keeper, bowling type, batting hand)",
    category="intermediate",
    description="With `player`: that player's attributes (role, keeper, batting slot, pace/spin and bowling type, batting hand, "
                "bowling phase role) with where each came from, plus matches, runs, balls faced, wickets and balls bowled per "
                "competition. Without `player`: a list of players, filtered by role / keeper / bowl_kind / bowl_type / bat_slot "
                "/ bat_hand and by competition, season, team, opposition or venue.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue"),
        ParamSpec("role", "choice", choices=ROLES[:3], help="batter | bowler | all-rounder (list mode)"),
        ParamSpec("keeper", "choice", choices=("yes", "sometimes", "either"), help="wicket-keeper filter (list mode); either = yes or sometimes"),
        ParamSpec("bowl_kind", "choice", choices=BOWL_KINDS, help="pace | spin (list mode)"),
        ParamSpec("bowl_type", "choice", choices=BOWL_TYPES, help="exact bowling type, only known for players in the override file (list mode)"),
        ParamSpec("bat_slot", "choice", choices=BAT_SLOTS[:5], help="opener | top order | middle | finisher | tail (list mode)"),
        ParamSpec("bat_hand", "choice", choices=("right", "left"), help="batting hand, only known for players in the override file (list mode)"),
        ParamSpec("min_matches", "int", default=30, help="List mode: hide players with fewer matches in the data (default 30)"),
        ParamSpec("limit", "int", default=100, help="List mode: maximum rows (default 100)"),
    ],
    caveats=[
        "Role, keeper, batting slot and phase role are DERIVED from ball-by-ball data (see reference/build_attributes.py for the rules); "
        "bowl_kind (pace/spin) is derived too unless the player is in player_overrides.csv.",
        "bowl_type and bat_hand are NOT in Cricsheet. They exist only for players in player_overrides.csv (source manual-llm = written "
        "from memory by Claude, with a confidence; check the confidence column before quoting). Empty = unknown.",
        "Different people can share a Cricsheet name (21 names are used by both a man and a woman; gender = 'both'): their numbers are mixed.",
        "Career summary respects competition/season/team/opposition/venue; with no competition it is men's only, like every module.",
    ],
)
def player_profile(f: Filters, role=None, keeper=None, bowl_kind=None, bowl_type=None, bat_slot=None, bat_hand=None,
                   min_matches: int = 30, limit: int = 100) -> pd.DataFrame:
    cte = attributes_cte("pa")
    if getattr(f, "player", None):
        return _one(f, cte)

    # list mode
    conds, params = ["pa.matches >= ?"], [int(min_matches)]
    if role:
        conds.append("pa.role = ?"); params.append(role)
    if keeper == "either":
        conds.append("pa.keeper IN ('yes', 'sometimes')")
    elif keeper:
        conds.append("pa.keeper = ?"); params.append(keeper)
    for col, val in (("bowl_kind", bowl_kind), ("bowl_type", bowl_type), ("bat_slot", bat_slot), ("bat_hand", bat_hand)):
        if val:
            conds.append(f"pa.{col} = ?"); params.append(val)
    scoped = any(v for k, v in dataclasses.asdict(f).items() if k not in ("player", "include_super_overs"))
    if scoped:   # only players who batted or bowled in the filtered matches
        wb, pb = f.where("bat")
        wl, pl = f.where("bowl")
        conds.append(f"""pa.name IN (SELECT d.batter FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wb}
                                     UNION SELECT d.bowler FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wl})""")
        params += pb + pl
    sql = f"""WITH {cte}
    SELECT pa.name AS player, {_ATTRS}
    FROM pa WHERE {' AND '.join(conds)} ORDER BY pa.matches DESC, pa.name LIMIT {int(limit)}"""
    return query(sql, params)


def _one(f: Filters, cte: str) -> pd.DataFrame:
    """Attributes of one player joined to his per-competition totals (filters apply to the totals)."""
    wb, pb = f.where("bat")
    wl, pl = f.where("bowl")
    sql = f"""
    WITH {cte},
    bat AS (SELECT m.competition, m.gender, d.match_id, d.runs_batter, {BALL_FACED} AS faced
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wb}),
    bowl AS (SELECT m.competition, m.gender, d.match_id, {LEGAL_BALL} AS legal, {BOWLER_WICKET} AS wkt
             FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wl}),
    played AS (SELECT competition, gender, COUNT(DISTINCT match_id) AS matches
               FROM (SELECT competition, gender, match_id FROM bat UNION SELECT competition, gender, match_id FROM bowl)
               GROUP BY ALL),
    b AS (SELECT competition, gender, SUM(runs_batter) AS runs, COUNT(*) FILTER (WHERE faced) AS balls_faced FROM bat GROUP BY ALL),
    w AS (SELECT competition, gender, COUNT(*) FILTER (WHERE wkt) AS wickets, COUNT(*) FILTER (WHERE legal) AS balls_bowled
          FROM bowl GROUP BY ALL)
    SELECT pa.name AS player, {_ATTRS},
           p.competition, p.gender AS match_gender, p.matches::INTEGER AS matches,
           COALESCE(b.runs, 0)::INTEGER AS runs, COALESCE(b.balls_faced, 0)::INTEGER AS balls_faced,
           COALESCE(w.wickets, 0)::INTEGER AS wickets, COALESCE(w.balls_bowled, 0)::INTEGER AS balls_bowled
    FROM pa JOIN played p ON TRUE
    LEFT JOIN b ON b.competition = p.competition AND b.gender = p.gender
    LEFT JOIN w ON w.competition = p.competition AND w.gender = p.gender
    WHERE pa.name = ?
    ORDER BY p.matches DESC, p.competition"""
    return query(sql, pb + pl + [f.player])
