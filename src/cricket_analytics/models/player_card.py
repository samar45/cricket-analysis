"""Everything the Player page and the player value card show for one player, built from existing modules / models.

`build(player, competition, y0, y1)` returns a plain dict. Nothing here is new maths: WAR (war module), worth metrics and
highlights (player_worth), expected matches (player_outlook), recent value (trade), splits (SQL fragments / pace_vs_spin).
"""

from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .. import api
from ..db import query
from ..sql import fragments as F
from ..sql.attributes import attributes_cte
from ..sql.filters import Filters

REF = Path(__file__).resolve().parent.parent / "reference"


@lru_cache(maxsize=1)
def _reviewed() -> pd.DataFrame:
    return pd.read_csv(REF / "player_overrides.csv", dtype=str).drop_duplicates("name").set_index("name")


@lru_cache(maxsize=1)
def _dob() -> pd.Series:
    d = pd.read_csv(REF / "player_dob.csv", dtype=str).dropna(subset=["dob"])
    return d.drop_duplicates("cricsheet_name").set_index("cricsheet_name").dob


def _teams(f: Filters) -> list[str]:
    """Teams he played for in scope, most recent first."""
    parts, params = [], []
    for side, col in (("bat", "batting_team"), ("bowl", "bowling_team")):
        w, p = f.where(side)
        parts.append(f"SELECT m.date, d.{col} AS team FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {w}")
        params += p
    t = query(f"SELECT team, max(date) AS last FROM ({' UNION ALL '.join(parts)}) GROUP BY team ORDER BY last DESC", params)
    return list(t.team)


def _phases(f: Filters, side: str) -> pd.DataFrame:
    """PP / middle / death: balls, runs, SR or economy, dot %, balls per boundary, dismissals or wickets."""
    w, p = f.where(side)
    if side == "bat":
        ball, runs, out, k, rate, outs = F.BALL_FACED, "d.runs_batter", F.BATTER_OUT, 100, "strike_rate", "dismissals"
    else:
        ball, runs, out, k, rate, outs = F.LEGAL_BALL, F.RUNS_CONCEDED, F.BOWLER_WICKET, 6, "economy", "wickets"
    sql = f"""
    SELECT {F.phase_sql()} AS phase, COUNT(*) FILTER (WHERE {ball})::INTEGER AS balls, SUM({runs})::INTEGER AS runs,
           COUNT(*) FILTER (WHERE {ball} AND {F.IS_DOT})::INTEGER AS dots,
           COUNT(*) FILTER (WHERE {F.IS_FOUR} OR {F.IS_SIX})::INTEGER AS boundaries,
           COUNT(*) FILTER (WHERE {out})::INTEGER AS {outs}
    FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {w} GROUP BY ALL"""
    t = query(sql, p).set_index("phase").reindex(F.PHASES).dropna(how="all")
    if t.empty:
        return t
    t[rate] = (t.runs * k / t.balls).round(1 if side == "bat" else 2)
    t["dot_pct"] = (t.dots * 100 / t.balls).round(1)
    t["balls_per_boundary"] = (t.balls / t.boundaries.where(t.boundaries > 0)).round(1)
    t[["balls", outs]] = t[["balls", outs]].astype(int)
    return t[["balls", rate, "dot_pct", "balls_per_boundary", outs]].reset_index()


def _vs_hand(f: Filters) -> pd.DataFrame:
    """A bowler against left- and right-handers (batting hand from the reviewed list only)."""
    w, p = f.where("bowl")
    sql = f"""
    WITH {attributes_cte("pa")}
    SELECT pa.bat_hand AS vs, COUNT(*) FILTER (WHERE {F.LEGAL_BALL})::INTEGER AS balls, SUM({F.RUNS_CONCEDED})::INTEGER AS runs,
           COUNT(*) FILTER (WHERE {F.BOWLER_WICKET})::INTEGER AS wickets,
           COUNT(*) FILTER (WHERE {F.LEGAL_BALL} AND {F.IS_DOT})::INTEGER AS dots,
           COUNT(*) FILTER (WHERE {F.IS_FOUR} OR {F.IS_SIX})::INTEGER AS boundaries
    FROM deliveries d JOIN matches m ON d.match_id = m.match_id JOIN pa ON pa.name = d.batter
    WHERE {w} AND pa.bat_hand IN ('left', 'right') GROUP BY ALL ORDER BY vs"""
    t = query(sql, p)
    t["vs"] = t.vs.map({"left": "Left-handers", "right": "Right-handers"})
    t["economy"] = (t.runs * 6 / t.balls).round(2)
    t["dot_pct"] = (t.dots * 100 / t.balls).round(1)
    t["balls_per_boundary"] = (t.balls / t.boundaries.where(t.boundaries > 0)).round(1)
    return t[["vs", "balls", "economy", "dot_pct", "balls_per_boundary", "wickets"]]


def _vs_kind(f: Filters) -> pd.DataFrame:
    t = _run("pace_vs_spin", player=f.player, competition=f.competition, season_from=f.season_from, season_to=f.season_to)
    if t.empty:
        return t
    t = t[(t.level == "kind") & (t.bowler_type != "Unknown")]
    return t.rename(columns={"bowler_type": "vs"})[["vs", "balls", "strike_rate", "dot_pct", "boundary_pct", "dismissals"]].reset_index(drop=True)


def _run(mod, **kw) -> pd.DataFrame:
    try:
        return api.run(mod, **kw).data
    except ValueError:  # no rows for this player / scope: the section is simply empty
        return pd.DataFrame()


def _recent_value(player: str) -> dict | None:
    """Recent value (wins a season, IPL 2023-26) with its 10-90% range, if he is in a 2027 squad."""
    from . import trade as T

    v = T.values()
    pt = T.player_table(T.squads(), v)
    if player not in pt.index:
        return None
    r = pt.loc[[player]]
    d = T.draws_for(r, v)[0]
    return dict(team=str(r.team.iloc[0]), value=float(r.value.iloc[0]), lo=float(np.percentile(d, 10)), hi=float(np.percentile(d, 90)), salary=float(r.salary.iloc[0]), has_evidence=bool(r.has_evidence.iloc[0]))


def build(player: str, competition: str | None = "ipl", y0: int = 2023, y1: int | None = None) -> dict:
    f = Filters(competition=competition, season_from=y0, season_to=y1, player=player)
    rv = _reviewed()
    row = rv.loc[player] if player in rv.index else None

    def rev(c):  # reviewed list only; "-" when he is not in it
        return "-" if row is None or pd.isna(row.get(c)) else str(row[c])

    dob = _dob().get(player)
    bat_ph, bowl_ph = _phases(f, "bat"), _phases(f, "bowl")
    bb, wb = (int(bat_ph.balls.sum()) if len(bat_ph) else 0), (int(bowl_ph.balls.sum()) if len(bowl_ph) else 0)
    war = _run("war", player=player, competition="ipl", season_from=y0, season_to=y1, min_balls=1) if competition == "ipl" else pd.DataFrame()
    role = war.main_role.iloc[-1] if len(war) else ("bowler" if wb > bb else "batter")
    o = _outlook(player)
    sc = dict(player=player, competition=competition, season_from=y0, season_to=y1)
    roles = [r for r, n in (("batting", bb), ("bowling", wb)) if n and role != ("bowler" if r == "batting" else "batter")]
    bat_on, bowl_on = "batting" in roles, "bowling" in roles
    return dict(
        player=player, competition=competition, y0=y0, y1=y1,
        header=dict(teams=_teams(f), role=role, bat_hand=rev("bat_hand"), bowl_type=rev("bowl_type"), keeper=rev("keeper"), dob=dob,
                    age=None if dob is None else round((date.today() - date.fromisoformat(dob)).days / 365.25, 1)),
        war=war, value=_recent_value(player), outlook=o,
        worth={r: _run("player_worth", role=r, **sc) for r in roles},
        highlights={r: _run("player_worth", role=r, mode="highlights", top=5, **sc) for r in roles},
        phases={k: v for k, v in (("batting", bat_ph), ("bowling", bowl_ph)) if k in roles},
        splits=({"Batting against bowling type": _vs_kind(f)} if bat_on else {}) | ({"Bowling against batting hand": _vs_hand(f)} if bowl_on else {}),
        dismissals=_run("dismissal_profile", **sc) if bat_on else pd.DataFrame(),
    )  # fmt: skip


def _outlook(player: str) -> dict | None:
    from . import player_outlook as PO

    o = PO.outlook([player]).iloc[0]
    if pd.isna(o.exp_matches):
        return None
    return dict(expected=float(o.exp_matches), lo=float(o.m10), hi=float(o.m90), balls_3y=int(o.balls_3y), evidence=o.evidence)
