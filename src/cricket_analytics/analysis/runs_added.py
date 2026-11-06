"""Runs added: how many runs a player added over what an average player would have in the same match situation."""

from dataclasses import replace

import pandas as pd

from ..db import query
from ..models.run_expectancy import (
    BALL_COLS,
    USABLE,
    batting_credit,
    bowling_credit,
    load,
    ra_state,
)
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, DISMISSAL

MIN_BALLS = 100


@module(
    id="runs_added",
    title="Runs added (vs the average player in the same situation)",
    category="advanced",
    description="Every ball is worth its runs plus the change in 'run expectancy' (how many runs the side is expected to "
    "score from here: it falls when a ball is used up or a wicket falls). Batters get the off-bat runs plus that change; "
    "bowlers get the opposite on the runs they concede. Runs added is the total over the player's balls, per 100 balls "
    "faced (batters) or per 24 balls bowled (bowlers), so 0 = an average player for that league, era and ground, "
    "and +10 per 100 balls is clearly above. Not a win probability: it measures run scoring, not match impact.",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec(
            "rank_by",
            "choice",
            default="total",
            choices=("total", "rate"),
            help="total = runs added, rate = runs added per 100 balls (batters) / per 24 balls (bowlers)",
        ),
        ParamSpec(
            "min_balls",
            "int",
            help="Hide players with fewer balls than this (default 100 in a ranking; 1 when you pick one player)",
        ),
        ParamSpec("top", "int", default=40, help="Rows to return"),
    ],
    caveats=[
        "Run expectancy is fitted on first innings only (average runs scored from each state: wickets lost, balls left), per league and era (IPL 2023+ is its own era because scoring jumped). Second innings use the same table, capped by the runs still needed.",
        "Rain-shortened matches count, with the balls each side actually had: a cut-short first innings, and the chase when it had the same length and no D/L label, are in. A D/L match counts for its first innings only (the reset target is not stored); awarded matches, washed-out ones and the second innings of D/L matches are left out. Super overs are left out by default.",
        "Batters are charged for balls used up (a dot ball costs about one run early on) and for their own wicket, including a non-striker run out. Extras are not the batter's: a small constant is added so an average batter scores 0.",
        "Bowlers are credited for runs they concede (bat runs + wides + no-balls, not byes) and for wickets that are theirs (not run outs). A small constant is added so an average bowler scores 0.",
        "Ground factor: venue scoring versus the era average, pulled toward 1 for grounds with few matches. It scales the expectancy change, not the runs.",
        "No batting-order or opposition adjustment: openers and finishers face different tasks, and strong sides face weaker attacks. Small samples swing a lot: 100 balls is roughly +/-8 runs per 100.",
    ],
)
def runs_added(
    f: Filters,
    role: str = "batting",
    rank_by: str = "total",
    min_balls: int | None = None,
    top: int = 40,
) -> pd.DataFrame:
    if min_balls is None:
        min_balls = 1 if getattr(f, "player", None) else MIN_BALLS
    st, sp = ra_state(f)

    def sel(kind: str) -> str:
        return (
            f"SELECT '{kind}' AS kind, {BALL_COLS} FROM d JOIN matches m ON d.match_id = m.match_id"
        )

    if role == "batting":
        wf, pf = f.where("bat")
        wo, po = replace(f, player=None).where("bat")
        wo += f" AND {DISMISSAL} AND d.player_out <> d.batter"
        if f.player:
            wo += " AND d.player_out = ?"
            po = po + [f.player]
        sql = (
            f"WITH d AS ({st}) {sel('S')} WHERE {USABLE} AND {wf} "
            f"AND ({BALL_FACED} OR (d.player_out = d.batter AND {DISMISSAL})) "
            f"UNION ALL {sel('N')} WHERE {USABLE} AND {wo}"
        )
        rows = query(sql, sp + pf + po)
    else:
        w, p = f.where("bowl")
        rows = query(f"WITH d AS ({st}) {sel('B')} WHERE {USABLE} AND {w}", sp + p)
    cols = (
        ["batter", "balls", "runs", "strike_rate", "runs_added", "runs_added_per_100_balls"]
        if role == "batting"
        else [
            "bowler",
            "legal_balls",
            "runs_conceded",
            "economy",
            "wickets",
            "runs_added",
            "runs_added_per_24_balls",
        ]
    )
    if rows.empty:
        return pd.DataFrame(columns=cols)
    for c in (
        "wickets_before",
        "b",
        "score_before",
        "legal",
        "wk",
        "striker_out",
        "bowler_wk",
        "faced",
    ):
        rows[c] = rows[c].astype("int64")
    a = load().annotate(rows)
    if role == "batting":
        s = a.kind == "S"
        a["credit"] = a.vf * a.wkt_part  # kind N: the non-striker who was run out
        a.loc[s, "credit"] = batting_credit(a[s])
        a["who"] = a.player_out.where(~s, a.batter)
        a["runs_f"] = a.runs_batter.where(s, 0) * a.faced
        a["balls_f"] = a.faced.where(s, 0)
        g = a.groupby("who").agg(
            balls=("balls_f", "sum"), runs=("runs_f", "sum"), runs_added=("credit", "sum")
        )
        g = g[g.balls >= min_balls]
        g["strike_rate"] = (g.runs * 100.0 / g.balls).round(2)
        g["runs_added_per_100_balls"] = (g.runs_added * 100.0 / g.balls).round(2)
        out = g.reset_index().rename(columns={"who": "batter"})
    else:
        a["credit"] = bowling_credit(a)
        a["wk_b"] = a.bowler_wk
        g = a.groupby("bowler").agg(
            legal_balls=("legal", "sum"),
            runs_conceded=("conceded", "sum"),
            wickets=("wk_b", "sum"),
            runs_added=("credit", "sum"),
        )
        g = g[g.legal_balls >= min_balls]
        g["economy"] = (g.runs_conceded * 6.0 / g.legal_balls).round(2)
        g["runs_added_per_24_balls"] = (g.runs_added * 24.0 / g.legal_balls).round(2)
        out = g.reset_index()
    out["runs_added"] = out.runs_added.round(1)
    key = "runs_added" if rank_by == "total" else cols[-1]
    return (
        out.sort_values([key, cols[0]], ascending=[False, True])[cols]
        .head(int(top))
        .reset_index(drop=True)
    )
