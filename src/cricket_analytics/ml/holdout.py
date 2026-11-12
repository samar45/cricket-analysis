"""S5 part 2: open the IPL 2026 holdout ONCE, per the pre-registration in docs/ML_PREDICTION.md section 9.

  python -m cricket_analytics.ml.holdout fit      # refit G0, G1, sim-B, resource-ipl on seasons <= 2025, predict 2026 (caches parquet)
  python -m cricket_analytics.ml.holdout report   # tables, pass rule, bias audit, tails, curves, sanity (reads the caches only)

No model logic is changed: the functions of direct.py / s4b.py / ball_model.py / simulate.py / baselines.py are reused as they are.
Tuning procedure is the same as for the 2022-25 folds (inner fold = the season before the test season, i.e. 2025).
Caches: data/external/ml/holdout_*.parquet. Never writes a .duckdb.
"""

import json
import sys
import time

import numpy as np
import pandas as pd

from . import direct as D
from . import evaluate as ev
from . import features as F
from . import s4b
from .ball_model import BallModel, load_balls
from .baselines import Resource, md, usable
from .dataset import OUT_DIR, load
from .sim_eval import test_keys
from .sim_report import bootstrap
from .simulate import fill_missing_batter, simulate, start_states, summarize
from .validate import BASE, CP, ENS1, G0, G1, KEYS, SIM, align, audit, ensemble, per_checkpoint

Y = 2026
N_SIMS = 1000
REPORT = OUT_DIR / "holdout_report.md"
P = lambda n: OUT_DIR / f"holdout_{n}.parquet"  # noqa: E731


# ---------- fit ----------
def fit():
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:5.0f}s] {m}", flush=True)  # noqa: E731
    states, inn = load()
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))  # same shrinkage as every earlier fold
    feat = D.prep(F.build_features(states, inn, kv, kt))
    log(f"features {feat.shape}; 2026 IPL matches {feat[(feat.season_year == Y) & (feat.competition == 'ipl')].match_id.nunique()}")
    cols = F.FEATURE_SETS["full"]
    tp = OUT_DIR / "holdout_tuned.json"
    tuned = json.loads(tp.read_text()) if tp.exists() else {str(Y): D.tune(feat, Y, cols)}  # inner fold = 2025
    tp.write_text(json.dumps(tuned, indent=1))
    log(f"tuned {tuned}")

    # resource-ipl baseline (fit on <= 2025)
    if not P("base_S").exists():
        _, train, test = next(ev.rolling_splits(states, (Y,), allow_holdout=True))
        test = usable(test[test.competition == "ipl"])
        t1, t2 = test[test.innings == 1], D.win_rows(test)
        m = Resource("ipl").fit(train)
        pd.concat([t1[D.META].assign(model=BASE, fold=Y, **m.score(t1))]).to_parquet(P("base_S"))
        t2[D.META].assign(model=BASE, fold=Y, p=m.win(t2)).to_parquet(P("base_W"))
        log("baseline done")
    # G0 = S3 lgbm-global
    if not P("G0_S").exists():
        S, W = D.run_variant(feat, states, "lgbm-global", "global", "full", tuned, years=(Y,))
        S.to_parquet(P("G0_S"))
        W.to_parquet(P("G0_W"))
        log("G0 done")
    # G1 = s4b "g1" (level-relative season-level target, no season_year, chase classifier); conformal widening applied at report time
    if not P("G1_S").exists():
        S, V, W = s4b.run_score(feat, "g1", s4b.NO_SEASON, tuned, "lvl_season", True, years=(Y,))
        S.to_parquet(P("G1_S"))
        V.to_parquet(P("G1_V"))
        W.to_parquet(P("G1_W"))
        log("G1 done")
    del feat
    # sim-B: ball model variant B, IPL pool, trained on seasons < 2026 (inner early stopping on IPL 2025), 1000 paths
    if not P("simB").exists():
        balls = load_balls()
        balls = balls[~balls.reduced & balls.lvl_slow.notna()]
        pool_f = lambda d: d[d.competition == "ipl"]  # noqa: E731
        m = BallModel("B").fit(pool_f(balls[balls.season_year < Y - 1]), balls[(balls.season_year == Y - 1) & (balls.competition == "ipl")])
        m = BallModel("B").fit(pool_f(balls[balls.season_year < Y]), None, n_rounds=int(m.best_iter * 1.1) + 1)
        m.save(f"ball_B_ipl_{Y}")
        keys = test_keys(states, Y)
        out = []
        for k, kk in keys.groupby("balls_bowled"):
            k = int(k)
            st = fill_missing_batter(start_states(balls[balls.season_year == Y], kk[["match_id", "innings"]].to_numpy(), k), m)
            res = simulate(m, st, n=N_SIMS, seed=k)
            yv = kk.set_index(["match_id", "innings"]).loc[list(zip(st.match_id, st.innings))].final_total.to_numpy(float)
            d = pd.concat([st[["match_id", "innings", "balls_bowled", "target"]], summarize(res["final"])], axis=1)
            d["win"] = res["win"]
            d["final_total"] = yv
            out.append(d)
        r = pd.concat(out, ignore_index=True)
        meta = states[["match_id", "innings", "balls_bowled", "chase_won"]].drop_duplicates(["match_id", "innings", "balls_bowled"])
        r.merge(meta, on=["match_id", "innings", "balls_bowled"]).to_parquet(P("simB"), index=False)
        log(f"sim-B done ({N_SIMS} paths, iters {m.best_iter})")
    log("fit finished")


# ---------- assemble ----------
def models():
    """Aligned checkpoint frames (score: innings 1, win: innings 2), plus meta. ens-G1 = mean of G1 and sim-B."""
    rd = lambda n: pd.read_parquet(P(n))  # noqa: E731
    cp = lambda d: d[d.balls_bowled.isin(CP)]  # noqa: E731
    S1 = s4b.conformalise(rd("G1_S"), rd("G1_V"), G1)
    sb = rd("simB")
    st = {BASE: cp(rd("base_S")), G0: cp(rd("G0_S")), G1: cp(S1), SIM: sb[sb.innings == 1]}
    wn = {BASE: cp(rd("base_W")), G0: cp(rd("G0_W")), G1: cp(rd("G1_W")), SIM: sb[sb.innings == 2].rename(columns={"win": "p"})}
    wn = {k: v[v.chase_won.notna()] for k, v in wn.items()}
    st, wn = align(st), align(wn)
    st[ENS1] = ensemble(st[G1], st[SIM], "score")
    wn[ENS1] = ensemble(wn[G1], wn[SIM], "win")
    keep = ["match_id", "innings", "balls_bowled", "final_total", "chase_won", "q10", "q50", "q90", "p"]
    st = {k: v[[c for c in keep if c in v.columns]] for k, v in st.items()}
    wn = {k: v[[c for c in keep if c in v.columns]] for k, v in wn.items()}
    return st, wn


def match_meta():
    from ..db import query

    states, inn = load()
    a = inn[(inn.competition == "ipl") & (inn.season_year == Y)]
    one = a[a.innings == 1][["match_id", "date", "venue", "batting_team", "final_total", "reduced"]].rename(columns={"batting_team": "team1", "final_total": "score1"})
    two = a[a.innings == 2][["match_id", "batting_team", "final_total", "target", "chase_won"]].rename(columns={"batting_team": "chaser", "final_total": "score2"})
    m = one.merge(two, on="match_id")
    t = query("select match_id, toss_decision from matches")
    m = m.merge(t, on="match_id", how="left")
    m["toss_bat"] = np.where(m.toss_decision == "bat", "toss winner bats first", "toss winner fields first")
    m["tbucket"] = pd.cut(m.target, [0, 159.5, 189.5, 219.5, 999], labels=["<160", "160-189", "190-219", "220+"]).astype(str)
    return m


def audit_meta(m):
    """Meta in the format validate.audit expects: key rows -> venue, batting_team (innings batting side), season_year, toss_bat, tbucket."""
    states, _ = load()
    k = states[(states.competition == "ipl") & (states.season_year == Y) & states.balls_bowled.isin(CP)][KEYS + ["venue", "batting_team", "season_year"]]
    return k.merge(m[["match_id", "toss_bat", "tbucket"]], on="match_id", how="left")


# ---------- report ----------
def main_report():
    out = []

    def log(x):
        print(x, flush=True)
        out.append(x)

    st, wn = models()
    m = match_meta()
    log(f"aligned rows: first innings {len(st[G0])}, chases {len(wn[G0])}; matches {st[G0].match_id.nunique()} (score), {wn[G0].match_id.nunique()} (chase); models {list(st)}")
    ts, tw = per_checkpoint(st, "score"), per_checkpoint(wn, "win")
    log("\n#### First-innings score, mean of 4 checkpoints (n = states per model)\n" + md(ts[ts.cp == "mean of 4"], 3))
    log("\nMAE by checkpoint:\n" + md(ts[ts.cp != "mean of 4"].pivot(index="model", columns="cp", values="mae").reset_index()[["model", "0 ov", "6 ov", "10 ov", "15 ov"]], 2))
    log("\nCoverage by checkpoint:\n" + md(ts[ts.cp != "mean of 4"].pivot(index="model", columns="cp", values="cov80").reset_index()[["model", "0 ov", "6 ov", "10 ov", "15 ov"]], 2))
    log("\nBias by checkpoint:\n" + md(ts[ts.cp != "mean of 4"].pivot(index="model", columns="cp", values="bias").reset_index()[["model", "0 ov", "6 ov", "10 ov", "15 ov"]], 2))
    log("\nn per checkpoint: " + str(ts[ts.model == ENS1][["cp", "n"]].set_index("cp").n.to_dict()))
    log("\n#### Chase win probability, mean of 4 checkpoints\n" + md(tw[tw.cp == "mean of 4"], 3))
    log("\nLog loss by checkpoint:\n" + md(tw[tw.cp != "mean of 4"].pivot(index="model", columns="cp", values="logloss").reset_index()[["model", "0 ov", "6 ov", "10 ov", "15 ov"]], 3))
    log("\nn per checkpoint (chases): " + str(tw[tw.model == ENS1][["cp", "n"]].set_index("cp").n.to_dict()))

    pooled = {}
    for n, g in wn.items():
        pooled[n] = ev.ece(g.chase_won, g.p)
    log("\nECE pooled over all 4 checkpoints (not the pre-registered form, for reference): " + str({k: round(v, 3) for k, v in pooled.items()}))

    rows = []
    for a, b in ((ENS1, BASE), (ENS1, SIM), (G1, SIM), (ENS1, G1), (G1, G0), (SIM, BASE)):
        r = {"comparison": f"{a} - {b}"}
        for kind, lab in (("mae", "MAE"), ("pinball", "pinball")):
            p = bootstrap(st[a], st[b], kind)
            r[lab] = f"{p[0]:+.2f} [{p[1]:+.2f}, {p[2]:+.2f}]"
        for kind, lab in (("logloss", "log loss"), ("brier", "Brier")):
            p = bootstrap(wn[a], wn[b], kind)
            r[lab] = f"{p[0]:+.3f} [{p[1]:+.3f}, {p[2]:+.3f}]"
        rows.append(r)
    log("\n#### Paired bootstrap over matches (2000 resamples, 5-95%, mean-of-4 difference; negative = first model better)\n" + md(pd.DataFrame(rows)))

    # ---- pass rule ----
    e = ts[(ts.model == ENS1) & (ts.cp == "mean of 4")].iloc[0]
    ew = tw[(tw.model == ENS1) & (tw.cp == "mean of 4")].iloc[0]
    mae_b, ll_b = bootstrap(st[ENS1], st[BASE], "mae"), bootstrap(wn[ENS1], wn[BASE], "logloss")
    crit = [
        ("1a ens-G1 beats resource-ipl on first-innings MAE (interval excludes 0)", f"{mae_b[0]:+.2f} [{mae_b[1]:+.2f}, {mae_b[2]:+.2f}]", mae_b[2] < 0),
        ("1b ens-G1 beats resource-ipl on chase log loss (interval excludes 0)", f"{ll_b[0]:+.3f} [{ll_b[1]:+.3f}, {ll_b[2]:+.3f}]", ll_b[2] < 0),
        ("2 80% coverage in [0.72, 0.88]", f"{e.cov80:.3f}", 0.72 <= e.cov80 <= 0.88),
        ("3 |bias| < 5 runs", f"{e.bias:+.2f}", abs(e.bias) < 5),
        ("4 ECE < 0.08", f"{ew.ece:.3f} (pooled {pooled[ENS1]:.3f})", ew.ece < 0.08),
    ]
    log("\n#### Pass rule for ens-G1 (as pre-registered)\n" + md(pd.DataFrame([{"criterion": c, "value": v, "result": "PASS" if ok else "FAIL"} for c, v, ok in crit])))
    log("OVERALL: " + ("PASS" if all(ok for *_, ok in crit) else "FAIL"))

    # ---- bias audit ----
    am = audit_meta(m)
    for kind, fr in (("score", st), ("win", wn)):
        for mod in (ENS1, BASE, SIM, G1):
            t = audit(fr, am, kind, mod)
            t = t[t.group != "season_year"]
            t.to_csv(OUT_DIR / f"holdout_audit_{kind}_{mod}.csv", index=False)
            log(f"\n#### Bias audit {kind}, {mod}: flagged {int(t.flag.sum())} of {len(t)} groups (about {0.05 * len(t):.1f} by chance)\n" + md(t[t.flag], 3))
            if mod == ENS1:
                log(f"\nAll groups, {kind}, {mod}:\n" + md(t.drop(columns="flag"), 3))

    # ---- tails ----
    mm = m.set_index("match_id")
    for mod in (ENS1, G1, SIM, G0):
        w = wn[mod].merge(m[["match_id", "date", "chaser", "team1", "target"]], on="match_id")
        lo, hi = w[w.p < 0.1], w[w.p > 0.9]
        log(f"\n#### Tails {mod}: p<10%: {len(lo)} states ({lo.match_id.nunique()} matches), chase won {int(lo.chase_won.sum())}, expected {lo.p.sum():.1f}; "
            f"p>90%: {len(hi)} states ({hi.match_id.nunique()} matches), chase lost {int((1 - hi.chase_won).sum())}, expected {(1 - hi.p).sum():.1f}")
        if mod == ENS1:
            lst = pd.concat([lo[lo.chase_won == 1].assign(what="won from <10%"), hi[hi.chase_won == 0].assign(what="lost from >90%")])
            lst = pd.DataFrame({"what": lst.what, "date": lst.date.astype(str).str[:10], "match": lst.team1 + " v " + lst.chaser, "target": lst.target.astype(int),
                                "state": (lst.balls_bowled // 6).astype(int).astype(str) + " ov", "p(chase wins)": lst.p.round(3)})
            log("Every ens-G1 surprise:\n" + md(lst, 3))

    # ---- last-over defence ----
    states, _ = load()
    s = states[(states.competition == "ipl") & (states.season_year == Y) & (states.innings == 2) & (states.balls_bowled == 114) & states.runs_needed.between(1, 10) & ~states.reduced][["match_id"]]
    for lab, f in (("G0", "G0_W"), ("G1", "G1_W")):
        g = pd.read_parquet(P(f))
        g = g[g.balls_bowled == 114].merge(s, on="match_id")
        log(f"\nLast-over defence {lab}: {len(g)} chases entered over 20 needing 1-10; defence held {int((g.chase_won == 0).sum())}, model expected {(1 - g.p).sum():.1f}")

    # ---- sanity: scoring level ----
    f1 = states[(states.competition == "ipl") & (states.season_year == Y) & (states.innings == 1) & (states.balls_bowled == 0) & ~states.reduced]
    sb = pd.read_parquet(P("simB"))
    at0 = {k: v[v.balls_bowled == 0] for k, v in st.items()}
    log(f"\n#### Sanity: IPL 2026 first-innings average total (non-reduced, n = {len(f1)}): actual {f1.final_total.mean():.1f}; all matches incl. reduced "
        f"{load()[1].query('competition == \"ipl\" and season_year == 2026 and innings == 1').final_total.mean():.1f}")
    log("Mean model prediction at 0 overs (first innings, aligned states, n = %d): " % len(at0[ENS1]) + ", ".join(f"{k} median {v.q50.mean():.1f}" for k, v in at0.items())
        + f"; sim-B mean-of-paths {sb[(sb.innings == 1) & (sb.balls_bowled == 0)]['mean'].mean():.1f}")

    # ---- curves ----
    curves(m, log)
    REPORT.write_text("\n".join(out), encoding="utf-8")


def curves(m, log):
    import pickle

    plt = ev._plt()
    g0, g1 = pd.read_parquet(P("G0_W")), pd.read_parquet(P("G1_W"))
    g1 = g1[g1.match_id.isin(m.match_id)]
    r = g1.groupby("match_id").agg(minp=("p", "min"), maxp=("p", "max"), won=("chase_won", "first")).reset_index().merge(m[["match_id", "target", "date", "team1", "chaser", "score1", "score2"]], on="match_id")
    big = r[r.won == 1].sort_values("target", ascending=False).iloc[0]
    sw = r[r.match_id != big.match_id].assign(swing=lambda d: d.maxp - d.minp).sort_values("swing", ascending=False).iloc[0]
    why = [(big, "biggest successful chase of 2026"), (sw, "biggest swing (largest G1 max - min win probability)")]
    balls = load_balls()
    model = pickle.load(open(OUT_DIR / "models" / f"ball_B_ipl_{Y}.pkl", "rb"))
    for x, lab in why:
        bl = balls[balls.match_id == x.match_id]
        ps, ks = [], []
        for ov in range(20):
            s = start_states(bl, [(x.match_id, 2)], 6 * ov)
            if len(s):
                ps.append(float(simulate(model, fill_missing_batter(s, model), n=N_SIMS, seed=ov)["win"][0]))
                ks.append(ov)
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.axhline(0.5, color="grey", ls=":")
        for d, name, mk in ((g0, "G0", "o-"), (g1, "G1", "^-")):
            gg = d[(d.match_id == x.match_id) & (d.balls_bowled % 6 == 0) & (d.balls_bowled < 120)].sort_values("balls_bowled")
            ax.plot(gg.balls_bowled / 6, gg.p, mk, label=name, ms=4)
        ax.plot(ks, ps, "s-", label="sim-B", ms=4)
        res = "chase WON" if x.won == 1 else "chase LOST"
        ax.set(xlabel="overs bowled in the chase", ylabel="P(chasing team wins)", ylim=(0, 1),
               title=f"{x.chaser} chasing {int(x.target)} v {x.team1}, {str(x.date)[:10]} ({res})\n{lab}")
        ax.title.set_fontsize(9)
        ax.legend(fontsize=8)
        fp = ev.IMG_DIR / f"ml_holdout_curve_{int(x.match_id)}.png"
        fig.savefig(fp, dpi=110, bbox_inches="tight")
        plt.close(fig)
        g1m = g1[(g1.match_id == x.match_id) & (g1.balls_bowled % 6 == 0)]
        log(f"- {int(x.match_id)} ({str(x.date)[:10]}, {x.team1} {int(x.score1)} v {x.chaser} {int(x.score2)}, {res}; {lab}): G1 min/max {g1m.p.min():.2f}/{g1m.p.max():.2f}, sim-B min/max {min(ps):.2f}/{max(ps):.2f}; plot {fp.name}")


def plots():
    plt = ev._plt()
    st, wn = models()
    ts, tw = per_checkpoint(st, "score"), per_checkpoint(wn, "win")
    cps = ["0 ov", "6 ov", "10 ov", "15 ov"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.8))
    for i, (tab, col, ttl) in enumerate(((ts, "mae", "first-innings MAE (runs)"), (tw, "logloss", "chase log loss"))):
        for j, n in enumerate(st):
            ax[i].bar(np.arange(4) + (j - len(st) / 2 + 0.5) * 0.8 / len(st), [tab[(tab.model == n) & (tab.cp == c)][col].iloc[0] for c in cps], 0.8 / len(st), label=n)
        ax[i].set_xticks(range(4), cps)
        ax[i].set_title(ttl)
    ax[0].legend(fontsize=7)
    ax[2].plot([0, 1], [0, 1], "--", color="grey")
    for n in wn:
        t = ev.reliability_table(wn[n].chase_won, wn[n].p, 10)
        ax[2].plot(t.pred, t.obs, "o-", label=n, ms=4)
    ax[2].set(xlabel="predicted chase win prob", ylabel="observed win rate", title="reliability, IPL 2026")
    fig.savefig(ev.IMG_DIR / "ml_holdout_h2h.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    # bias by checkpoint for ens-G1 and the baseline
    fig, ax = plt.subplots(figsize=(5, 3.6))
    for n in (BASE, SIM, ENS1):
        b = [ts[(ts.model == n) & (ts.cp == c)].bias.iloc[0] for c in cps]
        ax.plot(cps, b, "o-", label=n)
    ax.axhline(0, color="grey", ls=":")
    ax.set(ylabel="mean (predicted median - actual), runs", title="first-innings bias by checkpoint, IPL 2026")
    ax.title.set_fontsize(9)
    ax.legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_holdout_bias.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    if sys.argv[1:2] == ["fit"]:
        fit()
    elif sys.argv[1:2] == ["report"]:
        main_report()
        plots()
    else:
        print(__doc__)
