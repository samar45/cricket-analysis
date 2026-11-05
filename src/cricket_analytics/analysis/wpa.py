"""Win Probability Added (WPA): how much each ball moved the batting side's chance of winning, credited to the people on it."""

import numpy as np
import pandas as pd

from ..db import query
from ..models import win_prob as wp
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import MATCH_OUTCOME
from ..sql.state import ball_state

MIN_BALLS = 60
SWINGS = 5

_COLS = (
    "match_id, innings, ball_seq, over_num, ball_num, batter, bowler, non_striker, player_out, wicket_type, runs_batter, "
    "runs_total, wides, noballs, byes, legbyes, penalty, batting_team, bowling_team, score_before, wickets_before, "
    "balls_remaining, runs_needed"
)


def ball_wpa(f: Filters) -> pd.DataFrame:
    """One row per ball of every usable match in scope, sorted by match and ball.

    Columns added: group, wp_bf_before / wp_bf_after (chance the side batting FIRST wins, before and after the ball),
    wpa (change in the BATTING side's chance, positive = good for the batters), bat_who / bat_wpa (who is credited as batter),
    bowl_wpa (credit to the bowler), bat_first, date, opposition-ready team names.
    Usable = 6-ball T20 match with a trusted target and a result (ties count 0.5); everything else is dropped."""
    st, sp = ball_state(f)
    sql = f"""
    WITH s AS ({st}), mo AS ({MATCH_OUTCOME})
    SELECT {", ".join("s." + c.strip() for c in _COLS.split(","))}, m.date, m.competition, m.gender, year(m.date) AS year,
           mo.bat_first, mo.winner,
           CASE WHEN m.result = 'tie' THEN 0.5 WHEN mo.winner IS NULL THEN NULL
                WHEN mo.winner = mo.bat_first THEN 1.0 ELSE 0.0 END AS bf_win
    FROM s JOIN matches m ON m.match_id = s.match_id JOIN mo ON mo.match_id = s.match_id
    WHERE s.trusted AND m.balls_per_over = 6"""
    d = query(sql, sp)
    d = d.sort_values(["match_id", "innings", "ball_seq"], kind="stable").reset_index(drop=True)
    # drop matches with an unusable ball (no result, or the odd 121st legal ball) so every kept match has a whole curve
    bad = d.bf_win.isna() | ((d.innings == 2) & d.runs_needed.isna())
    d = d[~d.match_id.isin(d.match_id[bad])].reset_index(drop=True)
    if d.empty:
        return d.assign(
            group=[], wp_bf_before=[], wp_bf_after=[], wpa=[], bat_who=[], bat_wpa=[], bowl_wpa=[]
        )
    d["group"] = [wp.group_of(c, g, y) for c, g, y in zip(d.competition, d.gender, d.year)]
    inn1 = (d.innings == 1).to_numpy()
    before = np.empty(len(d))
    before[inn1] = wp.first_wp(
        d.score_before[inn1],
        d.balls_remaining[inn1],
        d.wickets_before[inn1],
        d.group[inn1],
        d.year[inn1],
    )
    before[~inn1] = 1 - wp.chase_wp(
        d.runs_needed[~inn1],
        d.balls_remaining[~inn1],
        d.wickets_before[~inn1],
        d.group[~inn1],
        d.year[~inn1],
    )
    d["wp_bf_before"] = before
    nxt = d.groupby("match_id").wp_bf_before.shift(-1)
    last = nxt.isna()  # last ball of each match
    last_inn1 = last | (d.innings != d.groupby("match_id").innings.shift(-1))
    after = nxt.to_numpy().copy()
    # last ball of innings 1: the chase starts at ball 0 against total + 1 (no jump between the innings)
    end1 = (inn1 & last_inn1).to_numpy()
    after[end1] = 1 - wp.chase_wp(
        (d.score_before + d.runs_total + 1)[end1], 120, 0, d.group[end1], d.year[end1]
    )
    after[(~inn1 & last).to_numpy()] = d.bf_win[~inn1 & last]  # last ball of the match: the result
    d["wp_bf_after"] = after
    d["wpa"] = (d.wp_bf_after - d.wp_bf_before) * np.where(inn1, 1, -1)
    out = (
        d.player_out.notna() & ~d.wicket_type.isin(["retired hurt", "retired not out"])
    ).to_numpy()
    # batter: gets the ball unless it was a wide / bye / leg bye / penalty with nobody out; a dismissal goes to the one who left
    # (so a non-striker run out is charged to the non-striker)
    bat_ok = ((d.wides == 0) & (d.byes == 0) & (d.legbyes == 0) & (d.penalty == 0)) | out
    d["bat_who"] = np.where(out, d.player_out, d.batter)
    d["bat_wpa"] = np.where(bat_ok, d.wpa, 0.0)
    # bowler: the opposite of the batting side's change on every ball except byes / leg byes / penalty runs with nobody out
    bowl_ok = ~(((d.byes > 0) | (d.legbyes > 0) | (d.penalty > 0)) & ~out)
    d["bowl_wpa"] = np.where(bowl_ok, -d.wpa, 0.0)
    d["event"] = _event(d, out)
    return d


def _event(d, out) -> pd.Series:
    ev = np.where(
        out,
        "WICKET " + d.player_out.fillna("") + " (" + d.wicket_type.fillna("") + ")",
        np.where(
            d.wides > 0,
            "wide",
            np.where(
                d.runs_batter == 6,
                "SIX",
                np.where(d.runs_batter == 4, "FOUR", d.runs_total.astype(str) + " run(s)"),
            ),
        ),
    )
    return pd.Series(ev, index=d.index)


def _phase(over_num: pd.Series) -> pd.Series:
    return pd.Series(
        np.where(over_num < 6, "powerplay", np.where(over_num < 15, "middle", "death")),
        index=over_num.index,
    )


def match_curve(d: pd.DataFrame, match_id: str) -> pd.DataFrame:
    m = d[d.match_id == str(match_id)].copy()
    if m.empty:
        return m
    m["ball_no"] = np.arange(1, len(m) + 1)
    m["over"] = m.over_num + 1
    m["ball"] = m.ball_num
    m["chasing_team"] = np.where(m.batting_team == m.bat_first, m.bowling_team, m.batting_team)
    m["wp_bat_first"] = m.wp_bf_after
    m["swing"] = m.wp_bf_after - m.wp_bf_before  # from the view of the team batting first
    m["swing_rank"] = 0
    top = m.swing.abs().nlargest(SWINGS).index
    m.loc[top, "swing_rank"] = (
        m.swing.abs().loc[top].rank(ascending=False, method="first").astype(int)
    )
    return m[
        [
            "match_id",
            "date",
            "ball_no",
            "innings",
            "over",
            "ball",
            "batting_team",
            "bat_first",
            "chasing_team",
            "winner",
            "batter",
            "bowler",
            "event",
            "wp_bf_before",
            "wp_bat_first",
            "swing",
            "swing_rank",
        ]
    ].reset_index(drop=True)


@module(
    id="wpa",
    title="Win Probability Added",
    category="advanced",
    description="How much each ball changed the batting side's chance of winning (from our own win-probability model), "
    "credited to the batter (off the bat) and, with the sign flipped, to the bowler. Totals per player, or "
    "view=match for the ball-by-ball win-probability curve of one match with its 5 biggest swings.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec("view", "choice", default="players", choices=("players", "match")),
        ParamSpec("match_id", "int", help="Cricsheet match id (for view=match)"),
        ParamSpec(
            "min_balls",
            "int",
            help="Hide players with fewer balls than this (default 60 in a ranking; 1 when you pick one player)",
        ),
        ParamSpec("top", "int", default=40, help="Rows to return"),
    ],
    caveats=[
        "Win probability comes from OUR model (logistic regression on state: score, wickets, balls left, competition, era), not from any official source. It knows nothing about who the teams or players are.",
        "WPA is context-heavy: a six in a close finish is worth far more than a six in over 3. Totals reward being in the match in the right moments, so they are not a pure skill measure.",
        "Extras: a wide goes to the bowler only; byes, leg byes and penalty runs go to neither player. A no-ball hit by the batter counts for the batter. A dismissal is charged to the player who left (a non-striker run out is the non-striker's) and to the bowler's ledger as well.",
        "Only 6-ball T20 matches with a result and a trusted target are used (no The Hundred, D/L, no results, abandoned or shortened first innings); super overs are excluded. Ties count 0.5.",
        "Matches in the model's own training years are scored with a model fitted on them (in-sample); see docs/VALUE_step2.md for the out-of-sample check.",
    ],
)
def wpa(
    f: Filters,
    role: str = "batting",
    view: str = "players",
    match_id: int | None = None,
    min_balls: int | None = None,
    top: int = 40,
) -> pd.DataFrame:
    d = ball_wpa(f)
    if view == "match":
        if match_id is None:
            raise ValueError("view=match needs match_id")
        return match_curve(d, str(match_id))
    if d.empty:
        return pd.DataFrame()
    bat = role == "batting"
    mine, other = ("batting_team", "bowling_team") if bat else ("bowling_team", "batting_team")
    who = d.bat_who if bat else d.bowler
    keep = pd.Series(True, index=d.index)
    for name, col in (("team", mine), ("opposition", other)):
        vals = f.values(name)
        if vals:
            keep &= d[col].isin(vals)
    if f.phase:
        keep &= _phase(d.over_num) == f.phase
    if f.player:
        keep &= who == f.player
    d, who = d[keep], who[keep]
    if d.empty:
        return pd.DataFrame()
    val = d.bat_wpa if bat else d.bowl_wpa
    e = pd.DataFrame(
        {
            "player": who.to_numpy(),
            "match_id": d.match_id.to_numpy(),
            "date": d.date.to_numpy(),
            "opposition": d[other].to_numpy(),
            "wpa": val.to_numpy(),
        }
    )
    if bat:
        faced = ((d.batter == who) & (d.wides == 0)).to_numpy()
        e["balls"] = faced.astype(int)
        e["runs"] = np.where(d.batter == who, d.runs_batter, 0)
        e["outs"] = (
            (
                d.player_out.notna()
                & (d.player_out == who)
                & ~d.wicket_type.isin(["retired hurt", "retired not out"])
            )
            .astype(int)
            .to_numpy()
        )
    else:
        legal = ((d.wides == 0) & (d.noballs == 0)).to_numpy()
        e["balls"] = legal.astype(int)
        e["runs"] = (d.runs_batter + d.wides + d.noballs).to_numpy()
        e["outs"] = (
            (
                d.wicket_type.notna()
                & ~d.wicket_type.isin(
                    [
                        "run out",
                        "retired hurt",
                        "retired out",
                        "retired not out",
                        "obstructing the field",
                        "hit the ball twice",
                    ]
                )
            )
            .astype(int)
            .to_numpy()
        )
    per_match = e.groupby(["player", "match_id"], as_index=False).agg(
        wpa=("wpa", "sum"), date=("date", "first"), opposition=("opposition", "first")
    )
    best = (
        per_match.sort_values("wpa", ascending=False).drop_duplicates("player").set_index("player")
    )
    tot = e.groupby("player").agg(
        balls=("balls", "sum"), runs=("runs", "sum"), outs=("outs", "sum"), wpa_total=("wpa", "sum")
    )
    tot["matches"] = per_match.groupby("player").size()
    tot["wpa_per_match"] = tot.wpa_total / tot.matches
    tot["wpa_per_100_balls"] = tot.wpa_total / tot.balls.where(tot.balls > 0) * 100
    tot["best_match_wpa"] = best.wpa
    tot["best_match_id"] = best.match_id
    tot["best_match_date"] = pd.to_datetime(best.date).dt.date
    tot["best_match_opposition"] = best.opposition
    if min_balls is None:
        min_balls = 1 if f.player else MIN_BALLS
    tot = tot[tot.balls >= int(min_balls)].reset_index()
    if bat:
        tot = tot.rename(columns={"player": "batter", "runs": "runs", "outs": "dismissals"})
        tot["strike_rate"] = (tot.runs * 100 / tot.balls.where(tot.balls > 0)).round(1)
        cols = ["batter", "matches", "balls", "runs", "dismissals", "strike_rate"]
    else:
        tot = tot.rename(
            columns={
                "player": "bowler",
                "balls": "legal_balls",
                "runs": "runs_conceded",
                "outs": "wickets",
            }
        )
        tot["economy"] = (tot.runs_conceded * 6 / tot.legal_balls.where(tot.legal_balls > 0)).round(
            2
        )
        cols = ["bowler", "matches", "legal_balls", "runs_conceded", "wickets", "economy"]
    for c in ("wpa_total", "wpa_per_match", "wpa_per_100_balls", "best_match_wpa"):
        tot[c] = tot[c].round(4)
    cols += [
        "wpa_total",
        "wpa_per_match",
        "wpa_per_100_balls",
        "best_match_wpa",
        "best_match_id",
        "best_match_date",
        "best_match_opposition",
    ]
    return tot[cols].sort_values("wpa_total", ascending=False).head(int(top)).reset_index(drop=True)
