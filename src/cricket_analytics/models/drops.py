"""Dropped catches from Cricbuzz (event DROPPED or commentary lapse 'drop'), joined to Cricsheet runs (docs/VALUE_execution_drops.md).

Cost of a drop = runs the reprieved batter scored after that ball until the end of his innings (Cricsheet runs).
Team-season fielding cost = sum of those; bowler drop luck = drops off his bowling, and adjusted wickets = wickets + drops.
"""

import numpy as np
import pandas as pd

from .commentary_features import OUT, ball_features, fill, load_frame


def drop_costs(d: pd.DataFrame) -> pd.DataFrame:
    """One row per dropped ball: match, innings, bowler, batter, fielding team, year, runs the batter added afterwards.
    Needs f_drop, runs_batter, wides, batter, ball_seq. A wide is not a batter ball, so it never counts for him."""
    d = d.sort_values(["match_id", "innings", "ball_seq"]).copy()
    g = d.groupby(["match_id", "innings", "batter"]).runs_batter
    d["after"] = g.transform(lambda s: s[::-1].cumsum()[::-1] - s)
    d["out_later"] = (d.player_out == d.batter).groupby([d.match_id, d.innings, d.batter]).transform("max") if "player_out" in d else False
    x = d[d.f_drop == 1]
    return x[["match_id", "innings", "ball_seq", "year", "bowler", "batter", "bowling_team", "after", "out_later"]].rename(columns={"after": "runs_after"})


def team_season(d: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    t = d.groupby(["bowling_team", "year"]).agg(balls=("legal", "size")).reset_index()
    s = c.groupby(["bowling_team", "year"]).agg(drops=("runs_after", "size"), cost_runs=("runs_after", "sum")).reset_index()
    t = t.merge(s, how="left").fillna({"drops": 0, "cost_runs": 0})
    t["avg_cost"] = (t.cost_runs / t.drops).where(t.drops > 0)
    t["cost_per_match"] = t.cost_runs / (t.balls / 240)  # ~120 legal balls per innings fielded; 2 innings of balls = 1 match
    return t


def bowler_season(d: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    """Per (bowler, year): balls, wickets credited to the bowler, drops off him, wickets_adj = wickets + drops."""
    d = d.copy()
    w = d.wicket_type.notna() & ~d.wicket_type.isin(["run out", "retired hurt", "retired out", "obstructing the field"])
    d["wk"] = w.astype(float)
    b = d.groupby(["bowler", "year"]).agg(balls=("legal", "sum"), wickets=("wk", "sum")).reset_index()
    s = c.groupby(["bowler", "year"]).size().rename("drops").reset_index()
    b = b.merge(s, how="left").fillna({"drops": 0})
    b["wickets_adj"] = b.wickets + b.drops
    b["wk_rate"], b["wk_adj_rate"] = b.wickets / b.balls, b.wickets_adj / b.balls
    return b


def pair_stats(b: pd.DataFrame, min_balls: int = 120) -> dict:
    """Does wickets/ball in t (raw vs drop-adjusted) predict raw wickets/ball in t+1? Pairs >= min_balls both years."""
    p = b.merge(b.assign(year=b.year + 1), on=["bowler", "year"], suffixes=("_next", "_prev"))
    p = p[(p.balls_prev >= min_balls) & (p.balls_next >= min_balls)]
    out = {"n_pairs": len(p), "r_raw": p.wk_rate_prev.corr(p.wk_rate_next), "r_adj": p.wk_adj_rate_prev.corr(p.wk_adj_rate_next),
           "r_adj_vs_adj_next": p.wk_adj_rate_prev.corr(p.wk_adj_rate_next)}
    out["r_raw_to_adj_next"] = p.wk_rate_prev.corr(p.wk_adj_rate_next)
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(1000):
        q = p.iloc[rng.integers(0, len(p), len(p))]
        diffs.append(q.wk_adj_rate_prev.corr(q.wk_rate_next) - q.wk_rate_prev.corr(q.wk_rate_next))
    out["r_adj_to_raw_next"] = p.wk_adj_rate_prev.corr(p.wk_rate_next)
    out["r_raw_to_raw_next"] = out["r_raw"]
    out["diff"], out["diff_lo"], out["diff_hi"] = out["r_adj_to_raw_next"] - out["r_raw"], *np.percentile(diffs, [5, 95])
    return out


def build(save: bool = True):
    d = ball_features(fill(load_frame(2017)))
    c = drop_costs(d)
    t, b = team_season(d, c), bowler_season(d, c)
    if save:
        c.to_csv(f"{OUT}/drops_events.csv", index=False)
        t.to_csv(f"{OUT}/drops_team_season.csv", index=False)
        b.to_csv(f"{OUT}/drops_bowler_season.csv", index=False)
    return c, t, b
