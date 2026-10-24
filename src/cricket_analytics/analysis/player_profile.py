"""Player profile. Data only.

FIXED FACTS (role, keeper, bowling type, batting hand): keeper / bowl_type / bat_hand only from player_overrides.csv, else 'unknown'.
USAGE (how he is really used) is computed from the deliveries for exactly the filters asked for, so "Dhoni, IPL, last 3 seasons"
differs from "Dhoni, IPL, career":
  batting position mix   innings at No.1-2 / 3-4 / 5-6 / 7+ (and each No.1..11); order = first appearance (striker or non-striker)
  batting phase mix      balls faced in powerplay / middle / death
  bowling phase mix      legal balls bowled in powerplay / middle / death
plus a "usually ..." hint = the biggest bucket with its percentage. Phases: sql/fragments.phase_sql (overs 0-5 / 6-14 / 15-19).
"""

import dataclasses

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.attributes import BOWL_KINDS, BOWL_TYPES, ROLES, attributes_cte
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BOWLER_WICKET, LEGAL_BALL, PHASES, phase_sql

# The fixed-fact columns returned in both modes (each value has its *_source and *_confidence next to it).
# No hint_* guess is ever returned: the usage mix below replaces the old "batting slot" / "phase role" labels.
_ATTRS = ("pa.gender AS player_gender, pa.matches AS career_matches, pa.role, pa.role_source, pa.role_confidence, "
          "pa.keeper, pa.keeper_source, pa.keeper_confidence, pa.bat_hand, pa.bat_hand_source, pa.bat_hand_confidence, "
          "pa.bowl_kind, pa.bowl_type, pa.bowl_type_source, pa.bowl_type_confidence, pa.bowl_kind_source, pa.bowl_kind_confidence")
_FACTS = ("keeper", "bowl_type", "bowl_kind", "bat_hand")

# count column -> label. Percent columns are "pct_" + the count column; the 3 "usually" sentences are built from these.
EN = "–"
POS_BUCKETS = {"pos_1_2": f"No.1{EN}2", "pos_3_4": f"No.3{EN}4", "pos_5_6": f"No.5{EN}6", "pos_7_plus": "No.7+"}
_PHASE_LABEL = {"powerplay": "powerplay", "middle": "middle overs", "death": "death overs"}
FACED = {f"faced_{p}": _PHASE_LABEL[p] for p in PHASES}
BOWLED = {f"bowled_{p}": _PHASE_LABEL[p] for p in PHASES}
POS_COLS = [f"pos_{i}" for i in range(1, 12)]   # pos_11 = No.11 or lower
COUNTS = [*POS_BUCKETS, "bat_innings", *FACED, *BOWLED]   # the columns usage_of() needs; sum them over rows to merge rows
_GROUPS = ((POS_BUCKETS, "usually_bats_at"), (FACED, "usually_faces_in"), (BOWLED, "usually_bowls_in"))
SORT_CHOICES = ("matches", *[f"{p}_{k}" for k in ("bowled", "faced") for p in PHASES])   # death_bowled = most death-over balls bowled


def _mix(counts: dict[str, int], labels: dict[str, str]) -> tuple[dict[str, float | None], str | None]:
    """({column: percent}, 'usually <biggest label> (52%)') from bucket counts; (all None, None) when there are none."""
    tot = sum(counts.values())
    if not tot:
        return {k: None for k in counts}, None
    pct = {k: round(100 * v / tot, 1) for k, v in counts.items()}
    best = max(counts, key=counts.get)   # ties: the first bucket
    return pct, f"usually {labels[best]} ({round(pct[best])}%)"


def usage_of(c) -> dict:
    """Percentages (pct_pos_1_2, pct_faced_death, pct_bowled_middle, ...) and the three 'usually' sentences from one set
    of counts (dict / Series / row holding pos_1_2 ... bowled_death). Sum the count columns over several rows first to
    get one mix for e.g. all competitions."""
    out: dict = {}
    for labels, hint in _GROUPS:
        pct, usual = _mix({k: int(c[k]) for k in labels}, labels)
        out.update({f"pct_{k}": v for k, v in pct.items()})
        out[hint] = usual
    return out


def with_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """pos_1_2 ... pos_7_plus from the individual pos_1..pos_11 columns."""
    df = df.copy()
    df["pos_1_2"], df["pos_3_4"] = df.pos_1 + df.pos_2, df.pos_3 + df.pos_4
    df["pos_5_6"], df["pos_7_plus"] = df.pos_5 + df.pos_6, df[POS_COLS[6:]].sum(axis=1)
    return df


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    """Unknown facts become the word 'unknown'; one-player rows get the bucket counts, percentages and 'usually' hints."""
    if "pos_1" in df.columns:
        df = with_buckets(df)
        df = pd.concat([df, pd.DataFrame([usage_of(r) for _, r in df.iterrows()], index=df.index)], axis=1)
    for c in _FACTS:
        if c in df.columns:
            df[c] = df[c].fillna("unknown")
    return df


@module(
    id="player_profile",
    title="Player profile (role, keeper, bowling type, batting hand, usage)",
    category="intermediate",
    description="With `player`: fixed facts (role, keeper, bowling type, batting hand; keeper / type / hand only from the reviewed "
                "list, else 'unknown') plus how he is USED under the filters: batting position mix (No.1-2 / 3-4 / 5-6 / 7+ and "
                "each number), balls faced and balls bowled by phase (powerplay / middle / death) as counts and %, and a 'usually ...' "
                "line for each; also matches, runs, balls faced, wickets and balls bowled per competition. Without `player`: a list "
                "of players filtered by role / keeper / bowl_kind / bowl_type / bat_hand and by competition, season, team, opposition "
                "or venue, optionally sorted by a usage count (sort_by=death_bowled = most death-over balls bowled).",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue"),
        ParamSpec("role", "choice", choices=ROLES[:3], help="batter | bowler | all-rounder (list mode)"),
        ParamSpec("keeper", "choice", choices=("yes", "sometimes", "either"), help="wicket-keeper filter, reviewed list only (list mode); either = yes or sometimes"),
        ParamSpec("bowl_kind", "choice", choices=BOWL_KINDS, help="pace | spin, implied by the reviewed bowling type (list mode)"),
        ParamSpec("bowl_type", "choice", choices=BOWL_TYPES, help="exact bowling type, reviewed list only (list mode)"),
        ParamSpec("bat_hand", "choice", choices=("right", "left"), help="batting hand, reviewed list only (list mode)"),
        ParamSpec("sort_by", "choice", choices=SORT_CHOICES, default="matches",
                  help="List mode: matches (default) or a usage count under the filters, e.g. death_bowled = most legal balls bowled in "
                       "overs 15-19, powerplay_faced = most balls faced in overs 0-5. Adds the faced_* / bowled_* columns."),
        ParamSpec("min_matches", "int", default=30, help="List mode: hide players with fewer matches in the data (default 30)"),
        ParamSpec("limit", "int", default=100, help="List mode: maximum rows (default 100)"),
    ],
    caveats=[
        "keeper, bowl_type, bowl_kind (pace/spin) and bat_hand are NOT in Cricsheet. They exist only for players in "
        "player_overrides.csv (source manual-llm = written from memory by Claude, with a confidence; check it before quoting). Everyone else is 'unknown': "
        "no guess is made from the data.",
        "Role is derived from the player's share of his team's balls faced / bowled (batter, bowler, all-rounder).",
        "Usage (position and phase mix) is computed from the deliveries under the filters, so it changes with season / team / venue. "
        "Position = order of first appearance in the innings (as striker or non-striker); the opener on strike is No.1. Phases: "
        "powerplay overs 0-5, middle 6-14, death 15-19 (The Hundred: 25 balls / 50 balls / 25 balls). A phase filter makes its own mix 100%.",
        "Different people can share a Cricsheet name (21 names are used by both a man and a woman; gender = 'both'): their numbers are mixed.",
        "Career summary respects competition/season/team/opposition/venue; with no competition it is men's only, like every module.",
    ],
)
def player_profile(f: Filters, role=None, keeper=None, bowl_kind=None, bowl_type=None, bat_hand=None,
                   sort_by: str = "matches", min_matches: int = 30, limit: int = 100) -> pd.DataFrame:
    cte = attributes_cte("pa")
    if getattr(f, "player", None):
        return _finish(_one(f, cte))
    return _finish(_list(f, cte, role, keeper, bowl_kind, bowl_type, bat_hand, sort_by, min_matches, limit))


def _phase_counts(prefix: str, flag: str) -> str:
    """`COUNT(*) FILTER (WHERE <flag> AND phase = 'x') AS <prefix>_x` for the three phases."""
    return ", ".join(f"COUNT(*) FILTER (WHERE {flag} AND phase = '{p}')::INTEGER AS {prefix}_{p}" for p in PHASES)


def _list(f, cte, role, keeper, bowl_kind, bowl_type, bat_hand, sort_by, min_matches, limit) -> pd.DataFrame:
    conds, params = ["pa.matches >= ?"], [int(min_matches)]
    if role:
        conds.append("pa.role = ?"); params.append(role)
    if keeper == "either":
        conds.append("pa.keeper IN ('yes', 'sometimes')")
    elif keeper:
        conds.append("pa.keeper = ?"); params.append(keeper)
    for col, val in (("bowl_kind", bowl_kind), ("bowl_type", bowl_type), ("bat_hand", bat_hand)):
        if val:
            conds.append(f"pa.{col} = ?"); params.append(val)
    wb, pb = f.where("bat")
    wl, pl = f.where("bowl")
    scoped = any(v for k, v in dataclasses.asdict(f).items() if k not in ("player", "include_super_overs"))
    if scoped:   # only players who batted or bowled in the filtered matches
        conds.append(f"""pa.name IN (SELECT d.batter FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wb}
                                     UNION SELECT d.bowler FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wl})""")
        params += pb + pl
    if sort_by in (None, "matches"):
        sql = f"""WITH {cte}
        SELECT pa.name AS player, {_ATTRS}
        FROM pa WHERE {' AND '.join(conds)} ORDER BY pa.matches DESC, pa.name LIMIT {int(limit)}"""
        return query(sql, params)
    if sort_by not in SORT_CHOICES:
        raise ValueError(f"sort_by must be one of {SORT_CHOICES}, not {sort_by!r}")
    phase, kind = sort_by.split("_")   # 'death_bowled' -> column bowled_death
    col = f"{kind}_{phase}"
    sql = f"""WITH {cte},
    fc AS (SELECT d.batter AS player, {_phase_counts('faced', BALL_FACED)}
           FROM (SELECT d.*, {phase_sql()} AS phase FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wb}) d GROUP BY 1),
    bc AS (SELECT d.bowler AS player, {_phase_counts('bowled', LEGAL_BALL)}
           FROM (SELECT d.*, {phase_sql()} AS phase FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wl}) d GROUP BY 1)
    SELECT pa.name AS player, {_ATTRS},
           {', '.join(f'COALESCE(fc.faced_{p}, 0) AS faced_{p}' for p in PHASES)},
           {', '.join(f'COALESCE(bc.bowled_{p}, 0) AS bowled_{p}' for p in PHASES)}
    FROM pa LEFT JOIN fc ON fc.player = pa.name LEFT JOIN bc ON bc.player = pa.name
    WHERE {' AND '.join(conds)} AND COALESCE({'fc' if kind == 'faced' else 'bc'}.{col}, 0) > 0
    ORDER BY {col} DESC, pa.matches DESC, pa.name LIMIT {int(limit)}"""
    return query(sql, pb + pl + params)


def _one(f: Filters, cte: str) -> pd.DataFrame:
    """Facts of one player joined to his per-competition totals and usage counts (all under the filters)."""
    wb, pb = f.where("bat")
    wl, pl = f.where("bowl")
    # the whole innings (not only his balls) is needed to rank the batting order, so drop the player and phase filters here
    wa, pa_ = dataclasses.replace(f, player=None, phase=None).where("bat")
    sql = f"""
    WITH {cte},
    bat AS (SELECT m.competition, m.gender, d.match_id, d.runs_batter, {BALL_FACED} AS faced, {phase_sql()} AS phase
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wb}),
    bowl AS (SELECT m.competition, m.gender, d.match_id, {LEGAL_BALL} AS legal, {BOWLER_WICKET} AS wkt, {phase_sql()} AS phase
             FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {wl}),
    played AS (SELECT competition, gender, COUNT(DISTINCT match_id) AS matches
               FROM (SELECT competition, gender, match_id FROM bat UNION SELECT competition, gender, match_id FROM bowl)
               GROUP BY ALL),
    b AS (SELECT competition, gender, SUM(runs_batter) AS runs, COUNT(*) FILTER (WHERE faced) AS balls_faced,
                 {_phase_counts('faced', 'faced')}
          FROM bat GROUP BY ALL),
    w AS (SELECT competition, gender, COUNT(*) FILTER (WHERE wkt) AS wickets, COUNT(*) FILTER (WHERE legal) AS balls_bowled,
                 {_phase_counts('bowled', 'legal')}
          FROM bowl GROUP BY ALL),
    -- batting order of every innings he was in: rank of first appearance (batter or non-striker); on ball 1 the striker is No.1
    base AS (SELECT d.match_id, d.innings, d.ball_seq, d.batter, d.non_striker, m.competition, m.gender
             FROM deliveries d JOIN matches m ON d.match_id = m.match_id
             WHERE {wa} AND d.match_id IN (SELECT match_id FROM deliveries WHERE batter = ? OR non_striker = ?)),
    seen AS (SELECT match_id, innings, competition, gender, player, MIN(ball_seq) AS first_seq,
                    FIRST(is_striker ORDER BY ball_seq, is_striker DESC) AS is_striker
             FROM (SELECT match_id, innings, competition, gender, ball_seq, batter AS player, 1 AS is_striker FROM base
                   UNION ALL SELECT match_id, innings, competition, gender, ball_seq, non_striker, 0 FROM base)
             GROUP BY ALL),
    ord AS (SELECT competition, gender, player,
                   ROW_NUMBER() OVER (PARTITION BY match_id, innings ORDER BY first_seq, is_striker DESC) AS pos FROM seen),
    posc AS (SELECT competition, gender, COUNT(*)::INTEGER AS bat_innings,
                    {', '.join(f"COUNT(*) FILTER (WHERE pos {'>=' if i == 11 else '='} {i})::INTEGER AS pos_{i}" for i in range(1, 12))}
             FROM ord WHERE player = ? GROUP BY ALL)
    SELECT pa.name AS player, {_ATTRS},
           p.competition, p.gender AS match_gender, p.matches::INTEGER AS matches,
           COALESCE(b.runs, 0)::INTEGER AS runs, COALESCE(b.balls_faced, 0)::INTEGER AS balls_faced,
           COALESCE(w.wickets, 0)::INTEGER AS wickets, COALESCE(w.balls_bowled, 0)::INTEGER AS balls_bowled,
           COALESCE(x.bat_innings, 0) AS bat_innings,
           {', '.join(f'COALESCE(x.pos_{i}, 0) AS pos_{i}' for i in range(1, 12))},
           {', '.join(f'COALESCE(b.faced_{p}, 0)::INTEGER AS faced_{p}' for p in PHASES)},
           {', '.join(f'COALESCE(w.bowled_{p}, 0)::INTEGER AS bowled_{p}' for p in PHASES)}
    FROM pa JOIN played p ON TRUE
    LEFT JOIN b ON b.competition = p.competition AND b.gender = p.gender
    LEFT JOIN w ON w.competition = p.competition AND w.gender = p.gender
    LEFT JOIN posc x ON x.competition = p.competition AND x.gender = p.gender
    WHERE pa.name = ?
    ORDER BY p.matches DESC, p.competition"""
    return query(sql, pb + pl + pa_ + [f.player, f.player, f.player, f.player])
