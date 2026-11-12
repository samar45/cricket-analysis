"""sim-B overshoot investigation: candidate ball models, ball-level screen, full simulated evaluation.

  python -m cricket_analytics.ml.simfix screen        # ball-level phase bias, IPL 2022-2026 (fixed rounds, fast)
  python -m cricket_analytics.ml.simfix full <cand> [n_sims]   # simulate checkpoints, write s2_preds_<cand>_ipl.parquet
Test years 2022-2025 are rolling (train < Y); 2026 is the already-seen IPL fold. Men's non-IPL matches dated
>= 2026-01-01 are never read for training or evaluation (see `usable`).
"""

import pickle
import sys
import time

import numpy as np
import pandas as pd

from .ball_model import MODEL_DIR, RUNS, BallModel, load_balls
from .dataset import OUT_DIR, load
from .sim_eval import CHECK, test_keys
from .simulate import fill_missing_batter, simulate, start_states, summarize

LOCK = pd.Timestamp("2026-01-01")
YEARS = (2022, 2023, 2024, 2025, 2026)
ITERS = {2022: None, 2023: None, 2024: None, 2025: None, 2026: 56}
# candidate name -> BallModel kwargs (all variant B)
CAND = {
    "B": {},
    "Bshr": dict(lvl_shrink=0.5),                            # level slopes halved before the trees are fitted
    "Blog": dict(lvl_log=True),                              # level as 8*log(level/8)
    "Bh50": dict(lvl_cols=("lvl_h50", "lvl_fast")),          # slow half-life 100 -> 50
    "Bh12": dict(lvl_cols=("lvl_slow", "lvl_h12")),          # fast half-life 25 -> 12
    "Bh400": dict(lvl_cols=("lvl_h400", "lvl_fast")),        # slow half-life 100 -> 400
    "Badj": dict(adj=True),                                  # player strengths from era-rescaled runs
    "Badj_shr": dict(adj=True, lvl_shrink=0.7),
    "Bsn": dict(season_neutral=True),                        # trees cannot learn season-level scoring
    "Bsn_adj": dict(season_neutral=True, adj=True),
}


def era_balls(balls, adj):
    """adj=True: the model's bat_rpb / bow_rpb columns become the era-rescaled strengths (bat_rpa / bow_rpa)."""
    return balls.assign(bat_rpb=balls.bat_rpa, bow_rpb=balls.bow_rpa) if adj else balls


def usable(balls, Y, pool="ipl"):
    """Training balls for test year Y: strictly earlier seasons, never men's non-IPL matches dated >= 2026-01-01."""
    b = balls[(balls.match_date < LOCK) | (balls.competition == "ipl")]
    assert not ((b.competition != "ipl") & (b.match_date >= LOCK)).any()  # fresh holdout stays locked
    b = b[~b.reduced & b.lvl_slow.notna()]
    return b if pool == "men" else b[b.competition == "ipl"]


def fit(cand, Y, balls, pool="ipl", rounds=None):
    """Early-stop on IPL season Y-1, then refit on all seasons < Y with 1.1x the best iteration count."""
    kw = {k: v for k, v in CAND[cand].items() if k != "adj"}
    balls = era_balls(balls, CAND[cand].get("adj", False))
    tr = usable(balls, Y, pool)
    if rounds is None:
        va = balls[(balls.season_year == Y - 1) & (balls.competition == "ipl") & ~balls.reduced & balls.lvl_slow.notna()]
        m = BallModel("B", **kw).fit(tr[tr.season_year < Y - 1], va)
        rounds = int(m.best_iter * 1.1) + 1
    return BallModel("B", **kw).fit(tr[tr.season_year < Y], None, n_rounds=rounds)


def screen(cands, years=YEARS, log=print):
    """Ball-level first-innings bias by phase (predicted minus actual runs per over, real states) per candidate/year."""
    balls = load_balls()
    rows = []
    for c in cands:
        for Y in years:
            old = pickle.load(open(MODEL_DIR / f"ball_B_ipl_{Y}.pkl", "rb"))
            m = fit(c, Y, balls, rounds=old.best_iter)
            t = era_balls(balls, CAND[c].get("adj", False))[(balls.competition == "ipl") & (balls.season_year == Y) & (balls.innings == 1) & ~balls.reduced].copy()
            P = m.proba(t)
            t["pr"] = P @ RUNS.astype(float) + P[:, 6] * m.wk_runs + P[:, 7] * m.ex_extra
            t["ph"] = pd.cut(t.over_n, [-1, 5, 15, 19], labels=["PP", "mid", "death"])
            g = t.groupby("ph", observed=True).agg(pr=("pr", "sum"), ar=("runs_total", "sum"), l=("legal", "sum"))
            g["bias"] = (g.pr - g.ar) / g.l * 6
            tot = (t.pr.sum() - t.runs_total.sum()) / t.match_id.nunique()
            rows.append(dict(cand=c, year=Y, PP=g.bias["PP"], mid=g.bias["mid"], death=g.bias["death"], runs_per_inn=tot))
            log(rows[-1])
    return pd.DataFrame(rows)


def full(cand, n=400, pool="ipl", years=YEARS, comps=("ipl",), log=print, tag=None):
    """Simulate checkpoints (0/6/10/15) of first innings and chases; same columns as s2_preds_B_ipl.parquet."""
    states, _ = load()
    raw = load_balls()
    balls = era_balls(raw[~raw.reduced & raw.lvl_slow.notna()], CAND[cand].get("adj", False))
    out = []
    for Y in years:
        t0 = time.time()
        m = fit(cand, Y, raw, pool)
        m.save(f"ball_{cand}_{pool}_{Y}")
        for comp in comps:
            keys = test_keys(states, Y, comp)
            keys = keys[keys.match_id.isin(balls[(balls.competition == comp) & (balls.match_date < LOCK) | (balls.competition == "ipl")].match_id)]
            for k, kk in keys.groupby("balls_bowled"):
                k = int(k)
                st = fill_missing_batter(start_states(balls[(balls.season_year == Y) & (balls.competition == comp)], kk[["match_id", "innings"]].to_numpy(), k), m)
                res = simulate(m, st, n=n, seed=k)
                yv = kk.set_index(["match_id", "innings"]).loc[list(zip(st.match_id, st.innings))].final_total.to_numpy(float)
                d = pd.concat([st[["match_id", "innings", "balls_bowled", "target"]], summarize(res["final"])], axis=1)
                d["win"], d["wk_mean"], d["final_total"] = res["win"], res["wickets"].mean(1), yv
                out.append(d.assign(year=Y, variant=cand, pool=pool, competition=comp))
        log(f"{cand} {Y}: {time.time() - t0:.0f}s")
    r = pd.concat(out, ignore_index=True)
    meta = states[["match_id", "innings", "balls_bowled", "chase_won"]].drop_duplicates(["match_id", "innings", "balls_bowled"])
    r = r.merge(meta, on=["match_id", "innings", "balls_bowled"])
    r.to_parquet(OUT_DIR / f"s2_preds_{tag or cand}_{pool}.parquet", index=False)
    return r


def lastover(cands, n=1000, years=YEARS):
    """Chases that reach the 20th over (114 legal balls bowled) needing 1-10 runs: mean predicted chase win vs actual."""
    states, _ = load()
    raw = load_balls()
    raw = raw[~raw.reduced & raw.lvl_slow.notna() & (raw.competition == "ipl")]
    rows = []
    for c in cands:
        balls = era_balls(raw, CAND[c].get("adj", False))
        for Y in years:
            m = pickle.load(open(MODEL_DIR / f"ball_{c}_ipl_{Y}.pkl", "rb"))
            b = balls[balls.season_year == Y]
            keys = b[(b.innings == 2) & (b.balls_bowled == 114) & (b.ball_in_over == 0) & (b.runs_needed >= 1) & (b.runs_needed <= 10) & (b.wickets < 10)]
            keys = keys.drop_duplicates("match_id")[["match_id", "innings"]]
            if keys.empty:
                continue
            st = fill_missing_batter(start_states(b, keys.to_numpy(), 114), m)
            res = simulate(m, st, n=n, seed=7)
            won = states[(states.balls_bowled == 114)].drop_duplicates(["match_id", "innings"]).set_index(["match_id", "innings"]).chase_won
            y = won.reindex(list(zip(st.match_id, st.innings))).to_numpy()
            rows.append(pd.DataFrame({"cand": c, "year": Y, "match_id": st.match_id, "need": st.target - st.runs, "p": res["win"], "won": y}))
    return pd.concat(rows, ignore_index=True)


def predict_checkpoints(keys, model="ball_B_men_fresh", n=1000, seed=0):
    """sim-B predictions for given states. keys: DataFrame with match_id, innings, balls_bowled (any checkpoints).
    Returns match_id, innings, balls_bowled, target, q10, q50, q90, mean, sd, win (chase win prob, innings 2), wk_mean.
    Reads the ball table for those matches only; the caller is responsible for what it asks for (no lock check here)."""
    m = pickle.load(open(MODEL_DIR / f"{model}.pkl", "rb"))
    balls = load_balls()
    balls = balls[balls.match_id.isin(keys.match_id.unique())]
    out = []
    for k, kk in keys.groupby("balls_bowled"):
        st = fill_missing_batter(start_states(balls, kk[["match_id", "innings"]].to_numpy(), int(k)), m)
        res = simulate(m, st, n=n, seed=seed + int(k))
        d = pd.concat([st[["match_id", "innings", "balls_bowled", "target"]], summarize(res["final"])], axis=1)
        d["win"], d["wk_mean"] = res["win"], res["wickets"].mean(1)
        out.append(d)
    return pd.concat(out, ignore_index=True)


def fit_fresh():
    """sim-B (defaults) on the men's pool: matches dated < 2026-01-01 plus IPL 2026 (allowed). Saved as ball_B_men_fresh."""
    raw = load_balls()
    m = fit("B", 2027, raw, "men")  # inner early-stopping fold = IPL 2026; train = everything usable before
    m.save("ball_B_men_fresh")
    return m


def nonipl(years=(2024, 2025), n=300, log=print):
    """Rolling non-IPL men's league checkpoints (train < Y, men's pool): s2_preds_B_men_nonipl.parquet. Test matches
    dated >= 2026-01-01 are dropped (BBL 2025/26 has season_year 2025)."""
    states, _ = load()
    raw = load_balls()
    bt = raw[~raw.reduced & raw.lvl_slow.notna() & (raw.competition != "ipl") & (raw.competition != "hundred") & (raw.match_date < LOCK)]
    out = []
    for Y in years:
        t0 = time.time()
        m = fit("B", Y, raw, "men")
        m.save(f"ball_B_men_{Y}_nonipl")
        b = bt[bt.season_year == Y]
        t = states[(states.season_year == Y) & states.match_id.isin(b.match_id.unique()) & ~states.reduced]
        t = t[t.balls_bowled.isin([6 * o for o in CHECK]) & (t.balls_left > 0) & (t.wickets < 10)]
        t = t[(t.innings == 1) | (t.chase_won.notna() & (t.runs_needed > 0))]
        for k, kk in t.groupby("balls_bowled"):
            st = fill_missing_batter(start_states(b, kk[["match_id", "innings"]].to_numpy(), int(k)), m)
            res = simulate(m, st, n=n, seed=int(k))
            d = pd.concat([st[["match_id", "innings", "balls_bowled", "target"]], summarize(res["final"])], axis=1)
            d["win"], d["wk_mean"] = res["win"], res["wickets"].mean(1)
            out.append(d.assign(year=Y, variant="B", pool="men"))
        log(f"nonipl {Y}: {len(t)} states, {time.time() - t0:.0f}s")
    r = pd.concat(out, ignore_index=True)
    meta = states[["match_id", "innings", "balls_bowled", "final_total", "chase_won", "competition"]].drop_duplicates(["match_id", "innings", "balls_bowled"])
    r = r.merge(meta, on=["match_id", "innings", "balls_bowled"])
    r.to_parquet(OUT_DIR / "s2_preds_B_men_nonipl.parquet", index=False)
    return r


def load_cand(c):
    """Predictions of candidate c (2022-25 rolling + 2026 seen), same columns for every candidate. B comes from the
    S2 cache (2022-25, 400 paths) and the S5 holdout cache (2026, 1000 paths)."""
    if c != "B":
        r = pd.read_parquet(OUT_DIR / f"s2_preds_{c}_ipl.parquet")
    else:
        a = pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet")
        h = pd.read_parquet(OUT_DIR / "holdout_simB.parquet").assign(year=2026)
        r = pd.concat([a, h], ignore_index=True)
    r = r[r.competition.eq("ipl") if "competition" in r else slice(None)]
    r["p"] = r.win
    r["season_year"] = r.year
    return r


def compare(cands, base="B", log=print):
    """Tables: bias at 0 overs by year, MAE/pinball by checkpoint, chase metrics, paired bootstrap vs base."""
    from . import evaluate as ev
    from .sim_report import bootstrap
    P = {c: load_cand(c) for c in cands}
    rows, win = [], []
    for c, r in P.items():
        f, w = r[r.innings == 1], r[r.innings == 2]
        for y, g in f.groupby("year"):
            g0 = g[g.balls_bowled == 0]
            rows.append(dict(cand=c, year=y, bias0=(g0["mean"] - g0.final_total).mean(), bias_all=(g.q50 - g.final_total).mean(),
                             mae=(g.q50 - g.final_total).abs().mean(), pin=ev.pinball_mean(g.final_total, {.1: g.q10, .5: g.q50, .9: g.q90}),
                             cov80=((g.final_total >= g.q10) & (g.final_total <= g.q90)).mean(), n=len(g)))
        for y, g in w.groupby("year"):
            m = {k: np.mean([ev.win_metrics(gg.chase_won, gg.p)[k] for _, gg in g.groupby("balls_bowled")]) for k in ("logloss", "brier", "ece")}
            win.append(dict(cand=c, year=y, **m, mean_p=g.p.mean(), actual=g.chase_won.mean(), n=len(g)))
    S, W = pd.DataFrame(rows), pd.DataFrame(win)
    boots = []
    for c in cands:
        if c == base:
            continue
        for nm, yrs in (("2022-25", (2022, 2023, 2024, 2025)), ("2026", (2026,))):
            a, b = P[c], P[base]
            for kind, inn in (("mae", 1), ("pinball", 1), ("logloss", 2), ("brier", 2)):
                x, y_ = a[(a.innings == inn) & a.year.isin(yrs)], b[(b.innings == inn) & b.year.isin(yrs)]
                boots.append(dict(cand=c, fold=nm, metric=kind, **dict(zip(("diff", "lo", "hi"), bootstrap(x, y_, kind)))))
    return S, W, pd.DataFrame(boots)


if __name__ == "__main__":
    if sys.argv[1] == "screen":
        r = screen(sys.argv[2].split(",") if len(sys.argv) > 2 else list(CAND))
        r.to_csv(OUT_DIR / "simfix_screen.csv", index=False)
        print(r.pivot(index="cand", columns="year", values="runs_per_inn").round(1).to_string())
        print(r.groupby("cand")[["PP", "mid", "death"]].apply(lambda g: g.abs().mean()).round(2).to_string())
    elif sys.argv[1] == "fresh_fit":
        print("fitted, iters", fit_fresh().best_iter)
    elif sys.argv[1] == "nonipl":
        nonipl()
    elif sys.argv[1] == "lastover":
        r = lastover(sys.argv[2].split(","))
        r.to_csv(OUT_DIR / "simfix_lastover.csv", index=False)
        print(r.groupby("cand").agg(n=("p", "size"), pred_win=("p", "mean"), actual_win=("won", "mean")).round(3).to_string())
        print(r.groupby(["cand", "year"]).agg(n=("p", "size"), pred_win=("p", "mean"), actual_win=("won", "mean")).round(3).to_string())
    elif sys.argv[1] == "compare":
        S, W, Bt = compare(sys.argv[2].split(","))
        pd.set_option("display.width", 250)
        print(S.round(2).to_string()); print(W.round(3).to_string()); print(Bt.round(3).to_string())
    else:
        full(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 400)
