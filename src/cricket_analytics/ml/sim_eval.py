"""S2 evaluation: rolling-origin (test IPL 2022-2025, never 2026) of ball model + simulator at checkpoints.

  python -m cricket_analytics.ml.sim_eval [variants] [pool] [n_sims]    e.g.  ABC ipl 500
Writes data/external/ml/s2_preds_<variant>_<pool>.parquet (one row per test state and variant) and saves the
last-fold models to data/external/ml/models/.
"""

import sys
import time

import numpy as np
import pandas as pd

from . import evaluate as ev
from .ball_model import BallModel, load_balls
from .dataset import OUT_DIR, load
from .simulate import fill_missing_batter, simulate, start_states, summarize

CHECK = (0, 6, 10, 15)


def test_keys(states, year, comp="ipl"):
    """(match_id, innings, k) triples of usable test states at the checkpoints (as baselines.usable + chase filters)."""
    t = states[(states.season_year == year) & (states.competition == comp) & ~states.reduced]
    t = t[t.balls_bowled.isin([6 * o for o in CHECK]) & (t.balls_left > 0) & (t.wickets < 10)]
    t = t[(t.innings == 1) | (t.chase_won.notna() & (t.runs_needed > 0))]
    return t[["match_id", "innings", "balls_bowled", "final_total", "chase_won", "season_year"]]


def run(variant="B", pool="ipl", n=500, years=(2022, 2023, 2024, 2025), seed=0, log=print):
    states, _ = load()
    balls = load_balls()
    balls = balls[~balls.reduced & balls.lvl_slow.notna()]
    out = []
    for Y, _, _ in ev.rolling_splits(states, years):  # raises for the holdout
        t0 = time.time()
        pool_f = (lambda d: d[d.competition == "ipl"]) if pool == "ipl" else (lambda d: d[d.competition != "hundred"])
        tr_in, va = pool_f(balls[balls.season_year < Y - 1]), balls[(balls.season_year == Y - 1) & (balls.competition == "ipl")]
        m = BallModel(variant).fit(tr_in, va)
        m = BallModel(variant).fit(pool_f(balls[balls.season_year < Y]), None, n_rounds=int(m.best_iter * 1.1) + 1)
        m.save(f"ball_{variant}_{pool}_{Y}")
        keys = test_keys(states, Y)
        for k, kk in keys.groupby("balls_bowled"):
            k = int(k)
            st = fill_missing_batter(start_states(balls[balls.season_year == Y], kk[["match_id", "innings"]].to_numpy(), k), m)
            res = simulate(m, st, n=n, seed=seed + k)
            yv = kk.set_index(["match_id", "innings"]).loc[list(zip(st.match_id, st.innings))].final_total.to_numpy(float)
            d = pd.concat([st[["match_id", "innings", "balls_bowled", "target"]], summarize(res["final"])], axis=1)
            d["win"], d["wk_mean"] = res["win"], res["wickets"].mean(1)
            d["pit"] = (res["final"] <= yv[:, None]).mean(1)
            d["crps"] = [ev.crps_samples(np.array([a]), b[None, :]) for a, b in zip(yv, res["final"])]
            out.append(d.assign(year=Y, variant=variant, pool=pool))
        log(f"{variant} {pool} {Y}: iters {m.best_iter}, {len(keys)} states, {time.time()-t0:.0f}s")
    r = pd.concat(out, ignore_index=True)
    meta = states[["match_id", "innings", "final_total", "chase_won", "runs", "balls_bowled"]].drop_duplicates(["match_id", "innings", "balls_bowled"])
    r = r.merge(meta[["match_id", "innings", "balls_bowled", "final_total", "chase_won"]], on=["match_id", "innings", "balls_bowled"])
    r.to_parquet(OUT_DIR / f"s2_preds_{variant}_{pool}.parquet", index=False)
    return r


if __name__ == "__main__":
    v = sys.argv[1] if len(sys.argv) > 1 else "B"
    pool = sys.argv[2] if len(sys.argv) > 2 else "ipl"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    for x in v:
        run(x, pool, n)
