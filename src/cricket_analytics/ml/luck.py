"""Luck / surprise tracker built on out-of-sample chase win-probability curves (IPL 2022-2026).

Curve = G1 (direct model) P(chasing team wins) at the start of every over of the chase, from the cached out-of-sample
per-ball predictions (rolling folds 2022-25: s4b_g1_W.parquet; 2026 holdout: holdout_G1_W.parquet), then the real result (1/0)
after the last over. The pre-chase probability (start of chase) is the blend (G1 + sim-B)/2 where the sim-B cache has the match
(s2_preds_B_ipl.parquet, holdoutsimB), else G1 alone. Matches without a decided chase (ties, no results) are skipped.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..db import query
from .dataset import OUT_DIR

COMPS = ("ipl",)  # ponytail: only IPL has cached out-of-sample curves; other leagues need predict_match_curve (in-sample, ~10 s/match)


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def curve_metrics(p, chase_won: int) -> dict:
    """Pure maths. p = P(chaser wins) at the start of each over (index = over); chase_won = 1/0. The real result is appended as a
    final point so the last over's move counts. Winner-view w = p if chaser won else 1-p."""
    p = np.asarray(p, float)
    full = np.append(p, float(chase_won))
    w = full if chase_won else 1 - full
    steps = np.abs(np.diff(full))
    return {
        "p_start": float(p[0]), "p_winner_start": float(w[0]), "surprise": float(1 - w[0]),
        "comeback_low": float(w[:-1].min()),  # winner's worst moment, before the result is known
        "swing": float(steps.sum()), "lead_changes": int((np.diff(np.sign(full - 0.5)) != 0).sum()),
        "decisive_over": int(steps.argmax()), "decisive_move": float(full[steps.argmax() + 1] - full[steps.argmax()]),
    }


@lru_cache(maxsize=1)
def _data():
    g = pd.concat([pd.read_parquet(OUT_DIR / f) for f in ("s4b_g1_W.parquet", "holdout_G1_W.parquet")], ignore_index=True)
    g = g[g.competition.isin(COMPS) & (g.innings == 2)].drop_duplicates(["match_id", "balls_bowled"])
    g["match_id"] = g.match_id.astype(str)
    parts = []
    for f in ("s2_preds_B_ipl.parquet", "holdout_simB.parquet"):
        x = pd.read_parquet(OUT_DIR / f)
        x = x[(x.innings == 2) & (x.balls_bowled == 0)]
        if "variant" in x:
            x = x[x.variant == "B"]
        parts.append(x[["match_id", "win"]])
    sim = pd.concat(parts).assign(match_id=lambda d: d.match_id.astype(str)).drop_duplicates("match_id").set_index("match_id").win
    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet")
    inn["match_id"] = inn.match_id.astype(str)
    first = inn[inn.innings == 1].set_index("match_id")
    return g, sim, first


def _matches(competition="ipl", season=None) -> pd.DataFrame:
    """One row per decided chase with curve metrics + pre-chase probability and the two teams."""
    g, sim, first = _data()
    rows = []
    for mid, d in g[g.competition == competition].groupby("match_id"):
        if pd.isna(d.chase_won.iloc[0]):
            continue
        sy = int(d.season_year.iloc[0])
        if season is not None and sy != int(season):
            continue
        d = d[d.balls_bowled % 6 == 0].sort_values("balls_bowled")
        if d.empty or d.balls_bowled.iloc[0] != 0:
            continue
        m = curve_metrics(d.p.to_numpy(), int(d.chase_won.iloc[0]))
        p_g1 = float(d.p.iloc[0])
        p0 = (p_g1 + float(sim[mid])) / 2 if mid in sim.index else p_g1
        if mid in sim.index:  # surprise / start-of-chase numbers use the blend
            m["p_start"] = p0
            m["p_winner_start"] = p0 if d.chase_won.iloc[0] == 1 else 1 - p0
            m["surprise"] = 1 - m["p_winner_start"]
        chaser = d.batting_team.iloc[0]
        setter = first.batting_team.get(mid)
        rows.append({"match_id": mid, "season": sy, "date": d.date.iloc[0].date(), "venue": d.venue.iloc[0], "chaser": chaser, "setter": setter,
                     "chase_won": int(d.chase_won.iloc[0]), "winner": chaser if d.chase_won.iloc[0] == 1 else setter, **m,
                     "blend": mid in sim.index})
    return pd.DataFrame(rows)


def _decisive(mid: str, over: int) -> dict:
    x = query("SELECT runs_total r, (player_out IS NOT NULL)::INT w FROM deliveries WHERE match_id = ? AND innings = 2 AND over_num = ?", [mid, over])
    return {"runs": int(x.r.sum()), "wickets": int(x.w.sum())}


def match_luck(match_id) -> dict:
    """Curve metrics for one decided IPL chase 2022-26 (see module doc), plus what happened in the decisive over."""
    mid = str(match_id)
    t = _matches()
    r = t[t.match_id == mid]
    if r.empty:
        raise ValueError(f"match {match_id} has no cached out-of-sample chase curve (IPL 2022-26, decided chases only)")
    r = r.iloc[0].to_dict()
    r["decisive_what"] = _decisive(mid, r["decisive_over"])
    return r


def _adjust(p, rate):
    """Shift pre-chase logits by one constant so the mean equals `rate` (the season's real chase win rate)."""
    lo, hi = -5.0, 5.0
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if (1 / (1 + np.exp(-(_logit(p) + mid)))).mean() < rate else (lo, mid)
    return 1 / (1 + np.exp(-(_logit(p) + (lo + hi) / 2)))


def team_luck(competition="ipl", season=None, adjust=False) -> pd.DataFrame:
    """Per team: matches, wins, expected wins, luck = wins - expected (+ = luckier than the model's pre-chase view), z = luck / sd.
    Chaser expects p, the side batting first 1-p. adjust=True shifts p per season so the model's mean chase win rate equals the real one."""
    t = _matches(competition, season)
    if t.empty:
        return pd.DataFrame(columns=["team", "matches", "wins", "expected", "luck", "z"])
    p = t.p_start.to_numpy()
    if adjust:
        p = pd.Series(p, index=t.index)
        for s in t.season.unique():
            k = t.season == s
            p[k] = _adjust(p[k].to_numpy(), t.chase_won[k].mean())
        p = p.to_numpy()
    a = pd.concat([pd.DataFrame({"team": t.chaser, "won": t.chase_won, "e": p}),
                   pd.DataFrame({"team": t.setter, "won": 1 - t.chase_won, "e": 1 - p})])
    a["v"] = a.e * (1 - a.e)
    out = a.groupby("team").agg(matches=("won", "size"), wins=("won", "sum"), expected=("e", "sum"), v=("v", "sum"))
    out["luck"] = out.wins - out.expected
    out["z"] = out.luck / np.sqrt(out.v)
    return out.drop(columns="v").round(2).reset_index().sort_values("luck", ascending=False, ignore_index=True)


def top_matches(competition="ipl", season=None, by="surprise", n=10) -> pd.DataFrame:
    """by='surprise' (1 - P(winner) at the start of the chase) or 'swing' (total |change| in win probability) or 'comeback'."""
    col = {"surprise": "surprise", "swing": "swing", "comeback": "comeback_low"}[by]
    t = _matches(competition, season)
    t = t.sort_values(col, ascending=(by == "comeback")).head(n).copy()
    t["decisive_what"] = [_decisive(m, o) for m, o in zip(t.match_id, t.decisive_over)]
    return t.reset_index(drop=True)
