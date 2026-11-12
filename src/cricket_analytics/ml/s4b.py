"""S4b: fix the two weaknesses of the global direct model (first-innings bias, 80% range too narrow).

Variants (each one change vs G0 = the S3 `lgbm-global`, global men's T20 pool, same config per fold as S3):
  g0r   same model, iterations re-tuned by early stopping on the inner fold with the GLOBAL pool (control for the new tuning)
  e1a   level-relative target (remaining runs / (lvl_ew/120 * balls_left)), weighted so the loss is still runs
  e1b   same with the in-season level lvl_season
  e2    drop season_year (score and win model)
  e3    conformal widening of q10/q90 per over bucket, from the inner fold (post-process of any variant)
  e4    chase win probability from an innings-2 remaining-runs quantile model
Run: python -m cricket_analytics.ml.s4b run | report      (caches to data/external/ml/s4b_*.parquet)
"""

import json
import sys
import time

import numpy as np
import pandas as pd

from . import direct as D
from . import evaluate as ev
from . import features as F
from .baselines import md, usable
from .dataset import OUT_DIR, load

Q9 = (0.05, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75, 0.9, 0.95)
NO_SEASON = [c for c in F.FEATURES if c != "season_year"]
G1_DIR = D.MODEL_DIR / "g1"


def _inner(feat, Y):
    """Inner-fold training pool (global, seasons < Y-1) and validation rows (IPL Y-1)."""
    tr, w = D.pool_rows(feat, "global", Y, last=Y - 1)
    val = feat[(feat.competition == "ipl") & (feat.season_year == Y - 1) & (feat.balls_bowled % 2 == 0)]
    return tr, w, val


def run_score(feat, name, cols, tuned, scale=None, win=False, years=D.YEARS, save=None):
    """Rolling run of one first-innings variant (and optionally its chase classifier). Returns (S, V, W):
    test predictions, inner-fold validation predictions (for conformal), chase probabilities."""
    S, V, W = [], [], []
    for Y in years:
        t = tuned[str(Y)]
        tr, w = D.pool_rows(feat, "global", Y)
        itr, iw, val = _inner(feat, Y)
        cfg = D.CONFIGS[t["score_cfg"]]
        inner = D.fit_score(itr, iw, cols, cfg, val=val, scale=scale)
        sm = D.fit_score(tr, w, cols, cfg, rounds={q: inner[q][1] for q in D.QS}, scale=scale)
        test = usable(feat[(feat.season_year == Y) & (feat.competition == "ipl")])
        t1 = test[test.innings == 1]
        v1 = usable(val)
        v1 = v1[v1.innings == 1]
        S.append(t1[D.META].assign(model=name, fold=Y, **D.predict_score(sm, t1, cols, scale=scale)))
        V.append(v1[D.META].assign(model=name, fold=Y, **D.predict_score(inner, v1, cols, scale=scale)))
        if win:
            cw = D.CONFIGS[t["win_cfg"]]
            wi, n = D.fit_win(itr, iw, cols, cw, val=val)
            wm, _ = D.fit_win(tr, w, cols, cw, rounds=n)
            t2 = D.win_rows(test)
            W.append(t2[D.META].assign(model=name, fold=Y, p=wm.predict(t2[cols])))
            if save:
                wm.save_model(str(save / f"{name}_{Y}_win.txt"))
        if save:
            for q in D.QS:
                sm[q][0].save_model(str(save / f"{name}_{Y}_score_q{int(q * 100)}.txt"), num_iteration=sm[q][1])
    return pd.concat(S), pd.concat(V), (pd.concat(W) if W else None)


def run_inn2(feat, name, cols, tuned, scale=None, years=D.YEARS, save=None):
    """E4: innings-2 remaining-runs quantile model -> P(win) = P(remaining >= runs needed). Returns W (same rows as the classifier)."""
    W = []
    for Y in years:
        t = tuned[str(Y)]
        tr, w = D.pool_rows(feat, "global", Y)
        itr, iw, val = _inner(feat, Y)
        cfg = D.CONFIGS[t["score_cfg"]]
        inner = D.fit_score(itr, iw, cols, cfg, val=val, innings=2, qs=Q9, scale=scale)
        sm = D.fit_score(tr, w, cols, cfg, rounds={q: inner[q][1] for q in Q9}, innings=2, qs=Q9, scale=scale)
        t2 = D.win_rows(usable(feat[(feat.season_year == Y) & (feat.competition == "ipl")]))
        pr = D.predict_score(sm, t2, cols, qs=Q9, scale=scale)
        rem = pr.to_numpy() - t2.runs.to_numpy()[:, None]
        W.append(t2[D.META].assign(model=name, fold=Y, p=D.p_from_quantiles(rem, Q9, t2.runs_needed.to_numpy())))
        if save:
            for q in Q9:
                sm[q][0].save_model(str(save / f"{name}_{Y}_chase_q{round(q * 100)}.txt"), num_iteration=sm[q][1])
    return pd.concat(W)


def conformalise(S, V, name):
    """E3: widen q10/q90 of S by the per-bucket delta fitted on the inner-fold validation predictions V (train-only)."""
    out = []
    for Y, s in S.groupby("fold"):
        v = V[V.fold == Y]
        dl = D.conformal_delta(v.final_total, v.q10, v.q90, D.over_bucket(v.balls_bowled))
        lo, hi = D.conformal_apply(s.q10, s.q50, s.q90, D.over_bucket(s.balls_bowled), dl)
        out.append(s.assign(model=name, q10=lo.values if hasattr(lo, "values") else lo, q90=hi))
    return pd.concat(out)


def _cache(name, fn):
    p = OUT_DIR / f"s4b_{name}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    x = fn()
    x.to_parquet(p)
    return x


def run():
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:5.0f}s] {m}", flush=True)  # noqa: E731
    states, inn = load()
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    feat = D.prep(F.build_features(states, inn, kv, kt))
    tuned = json.loads((OUT_DIR / "direct_tuned.json").read_text())
    log(f"features {feat.shape}, k_venue={kv}, k_team={kt}")
    full = F.FEATURE_SETS["full"]
    for name, cols, scale, win in (("g0r", full, None, False), ("e1a", full, "lvl_ew", False), ("e1b", full, "lvl_season", False),
                                   ("e2", NO_SEASON, None, True)):
        if (OUT_DIR / f"s4b_{name}_S.parquet").exists():
            continue
        S, V, W = run_score(feat, name, cols, tuned, scale, win)
        S.to_parquet(OUT_DIR / f"s4b_{name}_S.parquet")
        V.to_parquet(OUT_DIR / f"s4b_{name}_V.parquet")
        if W is not None:
            W.to_parquet(OUT_DIR / f"s4b_{name}_W.parquet")
        log(f"{name} done")
    if not (OUT_DIR / "s4b_g1_S.parquet").exists():  # G1 = level-relative (season level) target + no season_year (+ conformal at report time)
        G1_DIR.mkdir(parents=True, exist_ok=True)
        S, V, W = run_score(feat, "g1", NO_SEASON, tuned, "lvl_season", True, save=G1_DIR)
        S.to_parquet(OUT_DIR / "s4b_g1_S.parquet")
        V.to_parquet(OUT_DIR / "s4b_g1_V.parquet")
        W.to_parquet(OUT_DIR / "s4b_g1_W.parquet")
        log("g1 done")
    for name, scale in (("e4raw", None), ("e4lvl", "lvl_ew")):
        if not (OUT_DIR / f"s4b_{name}_W.parquet").exists():
            D_ = run_inn2(feat, name, full, tuned, scale)
            D_.to_parquet(OUT_DIR / f"s4b_{name}_W.parquet")
            log(f"{name} done")


if __name__ == "__main__" and sys.argv[1:2] == ["run"]:
    run()


# ---------- report ----------
def load_all():
    """All predictions in one place: S (score), W (win), V (inner-fold validation predictions)."""
    rd = lambda f: pd.read_parquet(OUT_DIR / f)  # noqa: E731
    S = [rd("direct_baseline_score.parquet"), rd("direct_pool_global_score.parquet")]
    W = [rd("direct_baseline_win.parquet"), rd("direct_pool_global_win.parquet")]
    V = {}
    for n in ("g0r", "e1a", "e1b", "e2", "g1"):
        if (OUT_DIR / f"s4b_{n}_S.parquet").exists():
            S.append(rd(f"s4b_{n}_S.parquet"))
            V[n] = rd(f"s4b_{n}_V.parquet")
            if (OUT_DIR / f"s4b_{n}_W.parquet").exists():
                W.append(rd(f"s4b_{n}_W.parquet"))
    for n in ("e4raw", "e4lvl", "e4g1"):
        if (OUT_DIR / f"s4b_{n}_W.parquet").exists():
            W.append(rd(f"s4b_{n}_W.parquet"))
    S, W = pd.concat(S), pd.concat(W)
    S = pd.concat([S] + [conformalise(S[S.model == n], V[n], n + "+cf") for n in V])
    W["_k"] = list(zip(W.match_id, W.innings, W.balls_bowled))
    g, e = W[W.model == "lgbm-global"].set_index("_k"), W[W.model == "e4raw"].set_index("_k")
    for n in [m for m in ("e4raw", "e4lvl", "e4g1") if m in set(W.model)]:
        e = W[W.model == n].set_index("_k")
        k = g.index.intersection(e.index)
        avg = g.loc[k].assign(model=f"avg(G0,{n})", p=(g.loc[k].p + e.loc[k].p) / 2).reset_index(drop=True)
        W = pd.concat([W, avg])
    return S, W.drop(columns="_k"), V


def _plots(S, W):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.axhline(0.8, ls="--", color="grey")
    for m, lab in (("lgbm-global", "G0"), ("g1", "G1 (no widening)"), ("g1+cf", "G1 + conformal")):
        s = S[S.model == m]
        c = ((s.final_total >= s.q10) & (s.final_total <= s.q90)).groupby(s.balls_bowled // 6).mean()
        ax.plot(c.index, c.values, "o-", ms=3, label=lab)
    ax.set(xlabel="overs bowled", ylabel="share inside 10-90% range", ylim=(0.4, 1), title="First-innings range coverage by over, IPL 2022-25")
    ax.legend()
    fig.savefig(ev.IMG_DIR / "ml_g1_coverage.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True)
    for ax, m, lab in zip(axs, ("lgbm-global", "g1"), ("G0", "G1")):
        w = W[W.model == m]
        t = ev.reliability_table(w.chase_won, w.p, w=ev.match_weights(w))
        ax.plot([0, 1], [0, 1], "--", color="grey")
        ax.plot(t.pred, t.obs, "o-")
        ax.set(title=f"{lab} chase win probability", xlabel="predicted", ylabel="actual win share")
    fig.savefig(ev.IMG_DIR / "ml_g1_reliability.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for m, lab in (("resource-ipl", "baseline"), ("lgbm-global", "G0"), ("g1+cf", "G1")):
        s = S[S.model == m]
        b = s.groupby("fold").apply(lambda d: np.average(d.q50 - d.final_total, weights=ev.match_weights(d)))
        ax.plot(b.index, b.values, "o-", label=lab)
    ax.axhline(0, color="grey", ls="--")
    ax.set(xlabel="test season", ylabel="mean bias (runs, predicted - actual)", title="First-innings bias by season")
    ax.legend()
    fig.savefig(ev.IMG_DIR / "ml_g1_bias_by_season.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def report():
    S, W, V = load_all()
    base = (S[S.model == "resource-ipl"], W[W.model == "resource-ipl"])
    g0 = (S[S.model == "lgbm-global"], W[W.model == "lgbm-global"])
    print("### summary 2022-25\n" + md(D.summarise(S, W).round(3)))
    print("\n### bootstrap vs G0 (variant minus G0; negative = better for mae/pin/ll; bias: closer to 0 is better), n matches")
    for m in sorted(S.model.unique()):
        if m in ("lgbm-global", "resource-ipl"):
            continue
        r = [D.boot_diff(S[S.model == m], g0[0], k) for k in ("mae", "bias", "pin", "cov")]
        print(f"{m}: " + " | ".join(f"{k} {x[0]:+.3f} [{x[1]:+.3f},{x[2]:+.3f}]" for k, x in zip(("MAE", "bias", "pinball", "cov"), r)) + f" | n={r[0][3]}")
    for m in sorted(W.model.unique()):
        if m in ("lgbm-global", "resource-ipl"):
            continue
        x = D.boot_diff(W[W.model == m], g0[1], "ll")
        print(f"{m}: win ll vs G0 {x[0]:+.4f} [{x[1]:+.4f},{x[2]:+.4f}] n={x[3]}")
    ctl = S[S.model == "g0r"]
    print("\n### vs control g0r / vs e1a")
    for m, ref in (("e1a", ctl), ("e1b", ctl), ("e1b", S[S.model == "e1a"]), ("g1", ctl), ("g1", S[S.model == "e1b"]), ("g1+cf", S[S.model == "g1"])):
        r = [D.boot_diff(S[S.model == m], ref, k) for k in ("mae", "bias", "pin", "cov")]
        print(f"{m} vs {ref.model.iloc[0]}: " + " | ".join(f"{k} {x[0]:+.3f} [{x[1]:+.3f},{x[2]:+.3f}]" for k, x in zip(("MAE", "bias", "pinball", "cov"), r)))
    print("\n### by test season")
    keep = ["resource-ipl", "lgbm-global", "e1a", "e1b", "g1", "g1+cf"]
    for y in D.YEARS:
        s = D.summarise(S[S.model.isin(keep)], W[W.model.isin(keep)], (y,))
        n = S[(S.fold == y) & (S.model == "lgbm-global")].groupby(["match_id", "innings"]).ngroups
        print(f"\n#### {y} (n={n})\n" + md(s.round(3)))
    if "g1" in set(S.model):
        print("\n### G1 vs baseline / G0")
        for ref in ("resource-ipl", "lgbm-global"):
            r = [D.boot_diff(S[S.model == "g1+cf"], S[S.model == ref], k) for k in ("mae", "bias", "pin", "cov")]
            print(f"g1+cf vs {ref}: " + " | ".join(f"{k} {x[0]:+.3f} [{x[1]:+.3f},{x[2]:+.3f}]" for k, x in zip(("MAE", "bias", "pinball", "cov"), r)))
            x = D.boot_diff(W[W.model == "g1"], W[W.model == ref], "ll")
            print(f"   win ll {x[0]:+.4f} [{x[1]:+.4f},{x[2]:+.4f}]")
        v = V["g1"]
        dl = {int(Y): D.conformal_delta(x.final_total, x.q10, x.q90, D.over_bucket(x.balls_bowled)) for Y, x in v.groupby("fold")}
        (G1_DIR / "conformal_delta.json").write_text(json.dumps(dl, indent=1))
        print("conformal deltas (runs added to each side of q10/q90, buckets over 1-6/7-10/11-15/16-20):", dl)
        _plots(S, W)
    return S, W, V


if __name__ == "__main__" and sys.argv[1:2] == ["report"]:
    report()
