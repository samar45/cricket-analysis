"""Monte Carlo innings simulator on top of a ball model (S2).

`simulate(model, states, n)` plays the rest of each innings n times, all paths at once with numpy.
A model is anything with `proba(features: dict of arrays) -> (m, 8) class probabilities` (classes as in
ball_model.RUNS) and the attributes `gen_bat` (11 x 3: rpb, out, exp of a new batter by wickets down),
`gen_bowl` (20 x 2: rpb, wk of an unknown bowler by over), `wk_runs`, `ex_extra` (mean extra runs on a wicket ball and
on a wide/no-ball beyond the 1 run), and `feats` for the real model. Batting order after the current pair is NOT
used (it would leak): an incoming batter is the average batter for that wicket number.

A start state is one row with: runs, wickets, balls_bowled, innings, target (NaN in innings 1), max_balls,
lvl_slow, lvl_fast, comp, venue_eff, and s_* / n_* (striker / non-striker rpb, out, exp, faced), bow_rpb, bow_wk.
"""

import numpy as np
import pandas as pd

from .ball_model import EX, RUNS, WK

ST = ["rpb", "out", "exp", "faced"]


def _features(p, i):
    """Feature dict for the paths `i` (indices into the path arrays)."""
    balls, runs, wk, inn = p["balls"][i], p["runs"][i], p["wk"][i], p["inn"][i]
    tgt = p["target"][i]
    left = np.maximum(p["max_balls"][i] - balls, 1)
    crr = np.where(balls > 0, runs / np.maximum(balls, 1) * 6, np.nan)
    need = tgt - runs
    rrr = np.where(inn == 2, need / left * 6, np.nan)
    f = {"over_n": balls // 6, "ball_in_over": balls % 6, "balls_bowled": balls, "wickets": wk, "innings": inn,
         "crr": crr, "crr_rel": crr - p["lvl_slow"][i], "target": tgt, "runs_needed": need, "rrr": rrr,
         "rrr_rel": rrr - p["lvl_slow"][i], "lvl_slow": p["lvl_slow"][i], "lvl_fast": p["lvl_fast"][i],
         "comp": p["comp"][i], "venue_eff": p["venue_eff"][i]}
    for c in p["lvl_extra"]:
        f[c] = p[c][i]
    s, b = p["S"][i], p["bowl"][i]
    for k, name in enumerate(["bat_rpb", "bat_out", "bat_exp", "bat_faced"]):
        f[name] = s[:, k]
    f["bow_rpb"], f["bow_wk"] = b[:, 0], b[:, 1]
    return f


def simulate(model, states, n=2000, seed=0, record_overs=False):
    """Returns dict: final (S, n) runs, wickets (S, n), win (S,) P(win) (innings 2 states; NaN for innings 1),
    over_runs (S*n, 21) cumulative runs at each over end (if record_overs)."""
    rng = np.random.default_rng(seed)
    st = states.reset_index(drop=True)
    S = len(st)
    rep = lambda c, dt=float: np.repeat(st[c].to_numpy(dt), n)  # noqa: E731
    P = S * n
    p = {"runs": rep("runs", np.int32), "wk": rep("wickets", np.int32), "balls": rep("balls_bowled", np.int32),
         "inn": rep("innings", np.int32), "target": rep("target"), "max_balls": rep("max_balls", np.int32),
         "lvl_slow": rep("lvl_slow"), "lvl_fast": rep("lvl_fast"), "comp": rep("comp", np.int32), "venue_eff": rep("venue_eff"),
         "S": np.column_stack([rep(f"s_{k}") for k in ST]), "N": np.column_stack([rep(f"n_{k}") for k in ST]),
         "bowl": np.column_stack([rep("bow_rpb"), rep("bow_wk")])}
    p["lvl_extra"] = [c for c in getattr(model, "lvl_cols", ()) if c not in ("lvl_slow", "lvl_fast")]
    for c in p["lvl_extra"]:
        p[c] = rep(c)
    gb, go = np.asarray(model.gen_bat, float), np.asarray(model.gen_bowl, float)
    wk_runs, ex_extra = getattr(model, "wk_runs", 0.0), getattr(model, "ex_extra", 0.0)

    def finished():
        return (p["balls"] >= p["max_balls"]) | (p["wk"] >= 10) | ((p["inn"] == 2) & (p["runs"] >= p["target"]))

    over_runs = np.full((P, 21), np.nan) if record_overs else None
    alive = np.flatnonzero(~finished())
    while len(alive):
        i = alive
        pr = model.proba(_features(p, i))
        c = np.minimum((pr.cumsum(1) < rng.random(len(i))[:, None]).sum(1), 7)
        r = RUNS[c].astype(np.int32)
        ex, w = c == EX, c == WK
        r = r + (ex & (rng.random(len(i)) < ex_extra)) + (w & (rng.random(len(i)) < wk_runs))
        legal = ~ex
        p["runs"][i] += r
        # strike changes on odd runs from the bat (not on a wicket or extra ball)
        swap = legal & ~w & (RUNS[c] % 2 == 1)
        sl = p["S"][i]
        sl[legal, 3] += 1  # striker faced a ball
        p["S"][i] = sl
        # wicket: new batter at the striker's end, strength by wickets down
        wi = i[w]
        p["wk"][wi] += 1
        g = gb[np.minimum(p["wk"][wi], 10)]
        p["S"][wi] = np.column_stack([g, np.zeros(len(wi))])
        p["balls"][i] += legal
        end = legal & (p["balls"][i] % 6 == 0)
        _swap(p, i[swap])
        _swap(p, i[end])
        ei = i[end]
        p["bowl"][ei] = go[np.minimum(p["balls"][ei] // 6, 19)]  # next over: unknown bowler
        if record_overs:
            over_runs[ei, p["balls"][ei] // 6] = p["runs"][ei]
        alive = i[~finished()[i]]
    final = p["runs"].reshape(S, n)
    out = {"final": final, "wickets": p["wk"].reshape(S, n)}
    tgt = st.target.to_numpy(float)[:, None]
    out["win"] = np.where(np.isnan(tgt[:, 0]), np.nan, ((final >= tgt) + 0.5 * (final == tgt - 1)).mean(1))
    if record_overs:
        out["over_runs"] = over_runs
    return out


def _swap(p, i):
    t = p["S"][i].copy()
    p["S"][i] = p["N"][i]
    p["N"][i] = t


def start_states(balls, keys, k):
    """Start-state rows for (match_id, innings) pairs after k legal balls, from the ball table (real players, real
    strengths; the non-striker's strength is read from his own rows in the match, which hold prior-date data only)."""
    keys = pd.DataFrame(keys, columns=["match_id", "innings"])
    b = balls[balls.match_id.isin(keys.match_id)]
    cur = b[(b.balls_bowled == k)].groupby(["match_id", "innings"], sort=False).head(1)
    cur = cur.merge(keys, on=["match_id", "innings"])
    rows = []
    for r in cur.itertuples(index=False):
        m = b[(b.match_id == r.match_id) & (b.innings == r.innings)]
        ns = m[m.batter == r.non_striker]
        before = m[(m.ball_seq < r.ball_seq) & (m.batter == r.non_striker) & (m.wides == 0)]
        nsr = ns.iloc[0] if len(ns) else None
        rows.append({
            "match_id": r.match_id, "innings": r.innings, "runs": r.runs, "wickets": r.wickets, "balls_bowled": r.balls_bowled,
            "target": r.target, "max_balls": r.max_balls, "lvl_slow": r.lvl_slow, "lvl_fast": r.lvl_fast, "comp": r.comp,
            "venue_eff": r.venue_eff, "s_rpb": r.bat_rpb, "s_out": r.bat_out, "s_exp": r.bat_exp, "s_faced": r.bat_faced,
            "n_rpb": getattr(nsr, "bat_rpb", np.nan), "n_out": getattr(nsr, "bat_out", np.nan),
            "n_exp": getattr(nsr, "bat_exp", np.nan), "n_faced": float(len(before)),
            "bow_rpb": r.bow_rpb, "bow_wk": r.bow_wk, "final_total": np.nan,
            "lvl_h50": r.lvl_h50, "lvl_h12": r.lvl_h12, "lvl_h400": r.lvl_h400,
        })
    return pd.DataFrame(rows)


def fill_missing_batter(st, model):
    """A non-striker who never faces a ball has no strength row: use the generic batter for the wickets down."""
    g = np.asarray(model.gen_bat)[np.minimum(st.wickets.to_numpy(), 10)]
    for j, k in enumerate(["rpb", "out", "exp"]):
        st[f"n_{k}"] = st[f"n_{k}"].fillna(pd.Series(g[:, j], index=st.index))
    return st


def summarize(final, qs=(0.1, 0.5, 0.9)):
    """Quantiles of the simulated final totals, one row per state."""
    q = np.quantile(final, qs, axis=1).T
    return pd.DataFrame(q, columns=["q10", "q50", "q90"]).assign(mean=final.mean(1), sd=final.std(1))
