"""S2 report: tables vs the S1 baselines, bootstrap over matches, plots, sanity checks. Reads the s2_preds files.

  python -m cricket_analytics.ml.sim_report [variants] [pool]
"""

import pickle
import sys

import numpy as np
import pandas as pd

from . import baselines as bl
from . import evaluate as ev
from .ball_model import MODEL_DIR, load_balls
from .dataset import OUT_DIR, load
from .sim_eval import test_keys
from .simulate import fill_missing_batter, simulate, start_states

KEYS = ["match_id", "innings", "balls_bowled"]
CP = [0, 36, 60, 90]


def load_preds(variants, pool="ipl"):
    s2 = pd.concat([pd.read_parquet(OUT_DIR / f"s2_preds_{v}_{pool}.parquet") for v in variants], ignore_index=True)
    s2["model"] = "sim-" + s2.variant + ("" if pool == "ipl" else "-" + pool)
    states, _ = load()
    _, _, W, S = bl.evaluate(states)
    keep = s2[KEYS].drop_duplicates()
    S = S.merge(keep, on=KEYS)
    W = W.merge(keep, on=KEYS)
    S1 = S[["match_id", "innings", "balls_bowled", "model", "q10", "q50", "q90", "final_total", "season_year"]]
    W1 = W[["match_id", "innings", "balls_bowled", "model", "p", "chase_won", "season_year"]]
    sc = pd.concat([S1, s2[s2.innings == 1].rename(columns={"year": "season_year"})[S1.columns.intersection(s2.rename(columns={"year": "season_year"}).columns)]], ignore_index=True)
    wn = pd.concat([W1, s2[s2.innings == 2].rename(columns={"year": "season_year", "win": "p"})[W1.columns]], ignore_index=True)
    return sc, wn, s2


def tables(sc, wn):
    def per(df, fn):
        rows = []
        for name, g in df.groupby("model", sort=False):
            cp = []
            for b in CP:
                sub = g[g.balls_bowled == b]
                r = fn(sub)
                rows.append({"model": name, "at": f"{b // 6} overs", "n": len(sub), **r})
                cp.append(r)
            rows.append({"model": name, "at": "mean of 4", "n": len(g), **{k: np.mean([c[k] for c in cp]) for k in cp[0]}})
        return pd.DataFrame(rows)

    st = per(sc, lambda d: ev.score_metrics(d.final_total, d.q10, d.q50, d.q90))
    wt = per(wn, lambda d: ev.win_metrics(d.chase_won, d.p))
    return st, wt


def bootstrap(a, b, kind, n_boot=2000, seed=0):
    """Paired bootstrap over matches of the mean-of-4-checkpoints loss difference (model a minus model b)."""
    def loss(df):
        if kind == "mae":
            return (df.q50 - df.final_total).abs()
        if kind == "pinball":
            return sum(np.maximum(q * (df.final_total - df[c]), (q - 1) * (df.final_total - df[c])) for q, c in ((0.1, "q10"), (0.5, "q50"), (0.9, "q90"))) / 3
        p = df.p.clip(1e-6, 1 - 1e-6)
        if kind == "logloss":
            return -(df.chase_won * np.log(p) + (1 - df.chase_won) * np.log(1 - p))
        return (p - df.chase_won) ** 2  # brier

    d = a.merge(b, on=KEYS, suffixes=("_a", "_b"))
    sa = d[[c for c in d.columns if c.endswith("_a")]].rename(columns=lambda c: c[:-2])
    sb = d[[c for c in d.columns if c.endswith("_b")]].rename(columns=lambda c: c[:-2])
    diff = (loss(sa) - loss(sb)).to_numpy()
    g = pd.DataFrame({"m": d.match_id.to_numpy(), "cp": d.balls_bowled.to_numpy(), "x": diff})
    mat = g.pivot_table(index="m", columns="cp", values="x", aggfunc=["sum", "count"]).fillna(0)
    s, c = mat["sum"].to_numpy(), mat["count"].to_numpy()
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(s), np.ones(len(s)) / len(s), size=n_boot)
    est = ((w @ s) / np.maximum(w @ c, 1)).mean(1)
    point = (s.sum(0) / c.sum(0)).mean()
    return point, *np.quantile(est, [0.05, 0.95])


def sanity(variant, pool="ipl", n=400, years=(2022, 2023, 2024, 2025)):
    """Simulate first innings from ball 0 in the test years; compare phases, wickets and spread with the real ones."""
    states, inn = load()
    balls = load_balls()
    balls = balls[~balls.reduced & balls.lvl_slow.notna()]
    rows, wk_sim, wk_act, finals = [], [], [], []
    act_over = {}
    for Y in years:
        m = pickle.load(open(MODEL_DIR / f"ball_{variant}_{pool}_{Y}.pkl", "rb"))
        keys = test_keys(states, Y)
        kk = keys[(keys.innings == 1) & (keys.balls_bowled == 0)]
        st = fill_missing_batter(start_states(balls[balls.season_year == Y], kk[["match_id", "innings"]].to_numpy(), 0), m)
        r = simulate(m, st, n=n, seed=Y, record_overs=True)
        o = r["over_runs"].reshape(len(st), n, 21)
        o[:, :, 0] = 0
        o = pd.DataFrame(o.reshape(-1, 21)).ffill(axis=1).to_numpy().reshape(len(st), n, 21)  # all out early: carry forward
        sim_cum = o.mean(1)
        act = states[(states.season_year == Y) & states.match_id.isin(st.match_id) & (states.innings == 1)]
        a = np.zeros((len(st), 21))
        for i, mid in enumerate(st.match_id):
            g = act[act.match_id == mid].set_index("balls_bowled")
            for ov in range(21):
                a[i, ov] = g.runs.get(6 * ov, g.runs.iloc[-1] if ov else 0) if ov else 0
            a[i, 20] = g.final_total.iloc[0]
        rows.append((Y, sim_cum, a))
        wk_sim.append(r["wickets"].ravel())
        wk_act.append(inn[(inn.match_id.isin(st.match_id)) & (inn.innings == 1)].set_index("match_id").loc[st.match_id].final_wickets.to_numpy())
        finals.append((r["final"], a[:, 20]))
    sim = np.concatenate([x[1] for x in rows]); act = np.concatenate([x[2] for x in rows])
    ph = {"overs 1-6": (0, 6), "overs 7-15": (6, 15), "overs 16-20": (15, 20)}
    out = []
    for name, (lo, hi) in ph.items():
        out.append({"phase": name, "sim runs/over": (sim[:, hi] - sim[:, lo]).mean() / (hi - lo), "actual runs/over": (act[:, hi] - act[:, lo]).mean() / (hi - lo)})
    pt = pd.DataFrame(out)
    ws, wa = np.concatenate(wk_sim), np.concatenate(wk_act)
    wt = pd.DataFrame({"wickets": list(range(11)), "sim share": [(ws == k).mean() for k in range(11)], "actual share": [(wa == k).mean() for k in range(11)]})
    fin_s = np.concatenate([f[0] for f in finals]); fin_a = np.concatenate([f[1] for f in finals])
    spread = {"n innings": len(fin_a), "mean sim": fin_s.mean(), "mean actual": fin_a.mean(), "sd of actual totals": fin_a.std(),
              "sd of sim totals (all paths pooled)": fin_s.std(), "mean within-innings sim sd": fin_s.std(1).mean() if False else np.mean([f[0].std(1).mean() for f in finals])}
    return pt, wt, spread, rows


if __name__ == "__main__":
    variants = sys.argv[1] if len(sys.argv) > 1 else "ABC"
    pool = sys.argv[2] if len(sys.argv) > 2 else "ipl"
    sc, wn, s2 = load_preds(variants, pool)
    st, wt = tables(sc, wn)
    sel = lambda t: t[t.model.isin(["run-rate+bias", "lookup-ipl", "resource-ipl"] + ["sim-" + v for v in variants])]  # noqa: E731
    print(bl.md(sel(st).round(2))); print(); print(bl.md(sel(wt).round(3)))
    base_s, base_w = sc[sc.model == "resource-ipl"], wn[wn.model == "resource-ipl"]
    for v in variants:
        a_s, a_w = sc[sc.model == "sim-" + v], wn[wn.model == "sim-" + v]
        print(v, "vs resource-ipl (negative = sim better; 5-95% over matches):")
        for k in ("mae", "pinball"):
            print("  ", k, "%.3f [%.3f, %.3f]" % bootstrap(a_s, base_s, k))
        for k in ("logloss", "brier"):
            print("  ", k, "%.4f [%.4f, %.4f]" % bootstrap(a_w, base_w, k))


def plots_and_breakdowns(variant="C", pool="ipl"):
    """Reliability, PIT, coverage and over-by-over plots (docs/img/ml_sim_*.png) plus bias by year / phase tables."""
    plt = ev._plt()
    sc, wn, s2 = load_preds(variant, pool)
    sim = f"sim-{variant}"
    w = wn[wn.model == sim]
    ev.reliability_plot(w.chase_won, w.p, f"sim_reliability_{variant}", w=None)
    for b in CP:
        g = w[w.balls_bowled == b]
        ev.reliability_plot(g.chase_won, g.p, f"sim_reliability_{variant}_{b // 6}ov")
    s = s2[s2.innings == 1]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.6))
    ax[0].hist(s.pit, bins=10, range=(0, 1), color="C0")
    ax[0].axhline(len(s) / 10, ls="--", color="grey")
    ax[0].set(title="where the real total fell in the simulated range (flat = calibrated)", xlabel="PIT")
    ax[0].title.set_fontsize(8)
    cov = s.assign(c=(s.final_total >= s.q10) & (s.final_total <= s.q90)).groupby("balls_bowled").c.mean()
    ax[1].bar([f"{b // 6}" for b in cov.index], cov.values)
    ax[1].axhline(0.8, ls="--", color="grey")
    ax[1].set(title="share of totals inside the 10-90% range", xlabel="overs bowled", ylim=(0, 1))
    ax[1].title.set_fontsize(8)
    yr = s.groupby("year").apply(lambda g: (g.q50 - g.final_total).mean(), include_groups=False)
    ax[2].bar(yr.index.astype(str), yr.values)
    ax[2].axhline(0, color="grey")
    ax[2].set(title="mean (predicted median - actual), runs", xlabel="test season")
    ax[2].title.set_fontsize(8)
    fig.savefig(ev.IMG_DIR / f"ml_sim_{variant}_score_checks.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    # over-by-over cumulative runs, sim vs actual (first innings from ball 0)
    _, _, _, rows = sanity(variant, pool)
    sim_c = np.concatenate([r[1] for r in rows]).mean(0)
    act_c = np.concatenate([r[2] for r in rows]).mean(0)
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    ax.plot(range(21), act_c, "o-", label="actual")
    ax.plot(range(21), sim_c, "s--", label="simulated")
    ax.set(xlabel="overs", ylabel="mean runs so far", title=f"first innings, IPL 2022-25 (variant {variant})")
    ax.legend()
    fig.savefig(ev.IMG_DIR / f"ml_sim_{variant}_overs.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    # tables
    def stats(g):
        return pd.Series({"n": len(g), "mae": (g.q50 - g.final_total).abs().mean(), "bias": (g.q50 - g.final_total).mean(),
                          "cov80": ((g.final_total >= g.q10) & (g.final_total <= g.q90)).mean(), "z sd": ((g.final_total - g["mean"]) / g.sd).std()})
    print("score by year:\n", s.groupby("year").apply(stats, include_groups=False).round(2).to_string())
    print("score by checkpoint:\n", s.groupby("balls_bowled").apply(stats, include_groups=False).round(2).to_string())
    wd = w.assign(year=w.season_year)
    print("win by year:\n", wd.groupby("year").apply(lambda g: pd.Series({"n": len(g), **ev.win_metrics(g.chase_won, g.p)}), include_groups=False).round(3).to_string())
    print("mean predicted vs actual chase win rate:", round(w.p.mean(), 3), round(w.chase_won.mean(), 3))
    low = w[w.p < 0.05]
    print("tail: p<5%: n", len(low), "won", int(low.chase_won.sum()), "expected", round(low.p.sum(), 1))
    hi = w[w.p > 0.95]
    print("tail: p>95%: n", len(hi), "lost", int((1 - hi.chase_won).sum()), "expected", round((1 - hi.p).sum(), 1))
