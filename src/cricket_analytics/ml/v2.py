"""v2 of the direct models + ensemble (docs/ML_PREDICTION.md section 9, "v2 development results").

  python -m cricket_analytics.ml.v2 run [fold ...]   # fit every variant on every dev fold, cache to data/external/ml/v2_*.parquet
  python -m cricket_analytics.ml.v2 report           # tables, stacking, bootstrap, plots (reads caches only)
  python -m cricket_analytics.ml.v2 fresh            # the pre-registered fresh-holdout comparison v1 vs v2 (THE LEAD RUNS THIS; workers never)
  python -m cricket_analytics.ml.v2 fresh --rehearse # same code path on DEV data (non-IPL 2025 as the pretend holdout) to test it

Dev folds: IPL 2022-2025 (rolling), IPL 2026 (seen), and non-IPL franchise leagues 2024 and 2025 (rolling, dated < 2026-01-01).
LOCK: men's non-IPL matches dated >= 2026-01-01 (evaluate.fresh_holdout_mask) are dropped from everything during development;
`split()` raises if one reaches a train / validation / test set. Only `fresh` passes allow_fresh=True.
"""

import json
import sys
import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from . import direct as D
from . import evaluate as ev
from . import features as F
from .baselines import md, usable
from .dataset import OUT_DIR, load
from .s4b import NO_SEASON
from .sim_report import bootstrap
from .validate import CP, KEYS, QC, align, ensemble, per_checkpoint

V2_DIR = D.MODEL_DIR / "v2"
P = lambda n: OUT_DIR / f"v2_{n}.parquet"  # noqa: E731
MONO = {"runs_needed": -1, "rrr": -1, "wickets": -1, "balls_left": 1, "req_vs_exp": -1, "req_ratio": -1, "rr_diff": 1}
# chase-model variants: name -> (columns, monotone constraints?)
WIN = {
    "w0": (NO_SEASON, False),                                  # control = the v1 G1 chase model, refit on dev data
    "w1m": (NO_SEASON, True),                                  # monotone constraints only
    "w1": (NO_SEASON + F.V2_RESOURCE, True),                   # C1: monotone + req_vs_exp
    "w2c": (NO_SEASON + F.V2_CHASE, False),                    # C2 alone
    "w2": (NO_SEASON + F.V2_RESOURCE + F.V2_CHASE, True),      # C1 + C2
    "w2s": (NO_SEASON + F.V2_RESOURCE + F.V2_CHASE10, True),   # C1 + C2 with a fixed fast season weight (k=10)
}
SCORE_COLS = NO_SEASON  # score side = v1 G1 recipe (level-relative target on lvl_season, conformal widening)
FOLDS = {  # name -> (year Y: train < Y, tuned-config key)
    "ipl2022": 2022, "ipl2023": 2023, "ipl2024": 2024, "ipl2025": 2025, "ipl2026": 2026, "lg2024": 2024, "lg2025": 2025,
}


# ---------- locked-holdout-safe data and splits ----------
def drop_fresh(states, inn):
    """Remove every match of the locked holdout from both tables (development never sees them)."""
    ids = set(inn.match_id[ev.fresh_holdout_mask(inn)])
    return states[~states.match_id.isin(ids)], inn[~inn.match_id.isin(ids)]


def train_pools(feat, cut, val_sel):
    """Training pools for a fit that predicts season `cut` (or later): train = seasons < cut, inner = seasons < cut-1, validation = val_sel
    rows. Raises if a locked row is in any of them (training on the locked set is never allowed, not even with allow_fresh)."""
    tr, w = D.pool_rows(feat, "global", cut)
    itr, iw = D.pool_rows(feat, "global", cut, last=cut - 1)
    val = feat[val_sel(feat) & (feat.balls_bowled % 2 == 0)]
    for df, nm in ((tr, "train"), (itr, "inner-train"), (val, "validation")):
        ev.assert_no_fresh(df, nm)
    return tr, w, itr, iw, val


def split(feat, Y, test_sel, val_sel, allow_fresh=False):
    """(train rows + weights, inner-train rows + weights, validation rows, test rows) for a fold. Raises on any locked row
    in train / validation; a locked row in the test rows raises unless allow_fresh=True."""
    test = ev.assert_no_fresh(feat[test_sel(feat)], "test", allow_fresh)
    return (*train_pools(feat, Y, val_sel), test)


def fold_sel(name):
    """(test_sel, val_sel) for a fold name: IPL season Y (val IPL Y-1) or the non-IPL franchise leagues in season Y (val: the same in Y-1)."""
    Y = FOLDS[name]
    if name.startswith("ipl"):
        return (lambda f: (f.competition == "ipl") & (f.season_year == Y)), (lambda f: (f.competition == "ipl") & (f.season_year == Y - 1))
    lg = lambda f: f.competition.isin(ev.FRESH_LEAGUES)  # noqa: E731
    return (lambda f: lg(f) & (f.season_year == Y)), (lambda f: lg(f) & (f.season_year == Y - 1))


def mono_list(cols):
    return [MONO.get(c, 0) for c in cols]


def dev_features(log=print):
    states, inn = drop_fresh(*load())
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    base = D.prep(F.build_features(states, inn, kv, kt))
    log(f"dev features {base.shape} (locked rows dropped: {int(ev.fresh_holdout_mask(base).sum())} left)")
    return base, inn


def tuned_cfg(name):
    t = json.loads((OUT_DIR / "direct_tuned.json").read_text())
    t.update(json.loads((OUT_DIR / "holdout_tuned.json").read_text()))  # key "2026"
    return t[str(FOLDS[name])]


# ---------- one fold ----------
def train_models(feat, cut, val_sel, t, variants=tuple(WIN), log=print):
    """Fit the G1-recipe score model (+ conformal widening from the inner fold) and the chase variants on seasons < cut.
    t = tuned config dict (score_cfg, win_cfg indices). Returns a dict of models."""
    tr, w, itr, iw, val = train_pools(feat, cut, val_sel)
    cfg, cw = D.CONFIGS[t["score_cfg"]], D.CONFIGS[t["win_cfg"]]
    inner = D.fit_score(itr, iw, SCORE_COLS, cfg, val=val, scale="lvl_season")
    sm = D.fit_score(tr, w, SCORE_COLS, cfg, rounds={q: inner[q][1] for q in D.QS}, scale="lvl_season")
    v1 = usable(val)
    v1 = v1[v1.innings == 1]
    V = v1[D.META].assign(**D.predict_score(inner, v1, SCORE_COLS, scale="lvl_season"))
    dl = D.conformal_delta(V.final_total, V.q10, V.q90, D.over_bucket(V.balls_bowled))
    win = {}
    for v in variants:
        cols, mono = WIN[v]
        ex = {"monotone_constraints": mono_list(cols)} if mono else None
        wi, n = D.fit_win(itr, iw, cols, cw, val=val, extra=ex)
        win[v] = D.fit_win(tr, w, cols, cw, rounds=n, extra=ex)[0]
        log(f"  {v}: {n} trees")
    return {"score": sm, "delta": dl, "win": win, "V": V}


def predict_models(m, test, name):
    """Predictions for the usable test rows: S (conformal-widened first-innings quantiles) and W (one row per variant)."""
    test = usable(test)
    t1 = test[test.innings == 1]
    S = t1[D.META].assign(model="G1v2", fold=name, **D.predict_score(m["score"], t1, SCORE_COLS, scale="lvl_season"))
    lo, hi = D.conformal_apply(S.q10, S.q50, S.q90, D.over_bucket(S.balls_bowled), m["delta"])
    S = S.assign(q10=lo, q90=hi)
    t2 = D.win_rows(test)
    W = pd.concat([t2[D.META].assign(model=v, fold=name, p=b.predict(t2[WIN[v][0]])) for v, b in m["win"].items()])
    return S, W


def save_models(m, prefix):
    """Write the boosters (score q10/q50/q90, chase variants) and the conformal deltas to data/external/ml/models/v2/."""
    V2_DIR.mkdir(parents=True, exist_ok=True)
    for q, (b, n) in m["score"].items():
        b.save_model(str(V2_DIR / f"{prefix}_score_q{int(q * 100)}.txt"), num_iteration=n)
    for v, b in m["win"].items():
        b.save_model(str(V2_DIR / f"{prefix}_win_{v}.txt"))
    (V2_DIR / f"{prefix}_conformal_delta.json").write_text(json.dumps({str(k): v for k, v in m["delta"].items()}))


def final(log=print):
    """v2 trained on everything dated < 2026-01-01 plus IPL 2026 (inner fold = IPL 2026); never reads a locked row."""
    states, inn = drop_fresh(*load())
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    k, _ = F.tune_k_chase(inn, 2027)
    feat = F.add_v2(D.prep(F.build_features(states, inn, kv, kt)), inn, k)
    m = train_models(feat, 2027, lambda f: (f.competition == "ipl") & (f.season_year == 2026), tuned_cfg("ipl2026"), variants=("w0", WIN_PICK), log=log)
    save_models(m, "final")
    log(f"saved final v2 models to {V2_DIR}")


def fit_fold(base, inn, name, log=print, save=True):
    """One dev fold: tune the season weight k on seasons < Y, fit, predict. Returns (S, V, W)."""
    Y = FOLDS[name]
    k, _ = F.tune_k_chase(inn[inn.season_year < Y], Y)
    feat = F.add_v2(base, inn, k)
    test_sel, val_sel = fold_sel(name)
    ev.assert_no_fresh(feat[test_sel(feat)], "test")
    m = train_models(feat, Y, val_sel, tuned_cfg(name), log=log)
    S, W = predict_models(m, feat[test_sel(feat)], name)
    log(f"{name}: k_season={k}, {len(S)} score rows, {len(W) // len(WIN)} chase rows")
    return S, m["V"].assign(model="G1v2", fold=name), W.assign(k_season=k)


def run(names=None):
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:5.0f}s] {m}", flush=True)  # noqa: E731
    base, inn = dev_features(log)
    for name in names or FOLDS:
        if P(f"{name}_W").exists():
            continue
        S, V, W = fit_fold(base, inn, name, log=log)
        S.to_parquet(P(f"{name}_S"))
        V.to_parquet(P(f"{name}_V"))
        W.to_parquet(P(f"{name}_W"))
        log(f"{name} cached")


# ---------- comparison frames ----------
WIN_PICK = "w1m"  # chase variant used inside v2 (set from the dev results; see the doc)
IPL_FOLDS = ("ipl2022", "ipl2023", "ipl2024", "ipl2025", "ipl2026")
LG_FOLDS = ("lg2024", "lg2025")
KEEP_S = KEYS + ["final_total", *QC]
KEEP_W = KEYS + ["chase_won", "p"]
sig = lambda x: 1 / (1 + np.exp(-x))  # noqa: E731
logit = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))  # noqa: E731


def v1_frames(fold):
    """v1 models on one IPL fold from their caches (G1 = direct model, sim-B = ball simulator): (S_g1, W_g1, S_sim, W_sim) at the checkpoints."""
    from .s4b import conformalise

    rd = lambda n: pd.read_parquet(OUT_DIR / n)  # noqa: E731
    Y = FOLDS[fold]
    if Y == 2026:
        gS, gW, sb = conformalise(rd("holdout_G1_S.parquet"), rd("holdout_G1_V.parquet"), "G1"), rd("holdout_G1_W.parquet"), rd("holdout_simB.parquet")
    else:
        gS = conformalise(rd("s4b_g1_S.parquet"), rd("s4b_g1_V.parquet"), "G1")
        gS, gW, sb = gS[gS.fold == Y], rd("s4b_g1_W.parquet").query("fold == @Y"), rd("s2_preds_B_ipl.parquet").query("year == @Y")
    cp = lambda d: d[d.balls_bowled.isin(CP)]  # noqa: E731
    sW = sb[(sb.innings == 2) & sb.chase_won.notna()].rename(columns={"win": "p"})
    return cp(gS)[KEEP_S], cp(gW)[KEEP_W], cp(sb[sb.innings == 1])[KEEP_S], cp(sW)[KEEP_W]


def fold_frames(fold):
    """({model: frame} for score, same for win) of one fold at the checkpoints, aligned on identical states.
    IPL folds also hold the v1 models (v1-G1, v1-sim-B)."""
    rd = lambda n: pd.read_parquet(P(f"{fold}_{n}"))  # noqa: E731
    cp = lambda d: d[d.balls_bowled.isin(CP)]  # noqa: E731
    S, W = cp(rd("S")), cp(rd("W"))
    W = W[W.chase_won.notna()]
    st, wn = {"v2-G1": S[KEEP_S]}, {v: W[W.model == v][KEEP_W] for v in WIN}
    if fold in IPL_FOLDS:
        a, b, c, d = v1_frames(fold)
        st.update({"v1-G1": a, "v1-sim-B": c})
        wn.update({"v1-G1": b, "v1-sim-B": d})
    elif (OUT_DIR / "s2_preds_B_men_nonipl.parquet").exists():  # sim worker's men's-pool sim-B on the non-IPL folds (300 paths)
        sb = pd.read_parquet(OUT_DIR / "s2_preds_B_men_nonipl.parquet").query("year == @FOLDS[@fold]")
        sb = sb[sb.balls_bowled.isin(CP)]
        st.update({"v1-G1": st["v2-G1"], "v1-sim-B": sb[sb.innings == 1][KEEP_S]})
        wn.update({"v1-G1": wn["w0"], "v1-sim-B": sb[(sb.innings == 2) & sb.chase_won.notna()].rename(columns={"win": "p"})[KEEP_W]})
    return align(st), align(wn)


def attach_ens(st, wn, weights=None):
    """Add v1-ens (50/50 of G1 and sim-B) and, if weights are given, v2-ens (stacked direct v2 + sim-B) to aligned frames."""
    st, wn = dict(st), dict(wn)
    st["v1-ens"] = ensemble(st["v1-G1"], st["v1-sim-B"], "score")
    wn["v1-ens"] = ensemble(wn["v1-G1"], wn["v1-sim-B"], "win")
    if weights is not None:
        st["v2-ens"] = stack_score(st["v2-G1"], st["v1-sim-B"], weights)
        wn["v2-ens"] = stack_win(wn[WIN_PICK], wn["v1-sim-B"], weights)
    return st, wn


# ---------- C3: stacking weights ----------
def _pin(y, q, lv):
    d = y - q
    return np.maximum(lv * d, (lv - 1) * d).mean()


def fit_weights(pairs, mode="global"):
    """pairs = list of (score_direct, score_sim, win_direct, win_sim) aligned frames, one per training fold.
    Win: p = sigmoid(w*logit(p_direct) + (1-w)*logit(p_sim)) (mode 'lin': p = w*p_direct + (1-w)*p_sim), ONE weight w in [0, 1] (no intercept, so the chase base rate is never re-learned).
    Score: per quantile level one weight on the direct quantile, the rest on sim-B (rows then sorted). mode 'cp' = one set per checkpoint; mode 'lin' keeps the score weights at 0.5."""
    S1, S2, W1, W2 = (pd.concat([p[i] for p in pairs]) for i in range(4))
    out = {"mode": mode, "win": {}, "score": {}}
    lin = mode == "lin"  # linear pool of probabilities (like the plain average) instead of a pool in logit space
    for g in ([None] if mode in ("global", "lin") else list(CP)):
        ms = np.ones(len(S1), bool) if g is None else (S1.balls_bowled == g).to_numpy()
        mw = np.ones(len(W1), bool) if g is None else (W1.balls_bowled == g).to_numpy()
        y, l1, l2 = W1.chase_won.to_numpy()[mw], logit(W1.p.to_numpy()[mw]), logit(W2.p.to_numpy()[mw])

        def f(w):
            p = np.clip(w * sig(l1) + (1 - w) * sig(l2), 1e-6, 1 - 1e-6) if lin else sig(w * l1 + (1 - w) * l2)
            return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

        out["win"][str(g)] = float(minimize_scalar(f, bounds=(0, 1), method="bounded").x)
        ys = S1.final_total.to_numpy()[ms]
        if lin:  # the score side showed no gain from fitted weights (see the doc): keep the plain 50/50 average of quantiles
            out["score"][str(g)] = {c: 0.5 for c in QC}
            continue
        out["score"][str(g)] = {c: float(minimize_scalar(lambda w: _pin(ys, w * S1[c].to_numpy()[ms] + (1 - w) * S2[c].to_numpy()[ms], lv), bounds=(0, 1), method="bounded").x)
                                for c, lv in zip(QC, (0.1, 0.5, 0.9))}
    return out


def _sorted_pair(a, b):
    a, b = a.sort_values(KEYS).reset_index(drop=True), b.sort_values(KEYS).reset_index(drop=True)
    assert (a[KEYS].to_numpy() == b[KEYS].to_numpy()).all(), "stack inputs are not aligned"
    return a, b


def stack_win(a, b, weights):
    a, b = _sorted_pair(a, b)
    d = weights["win"]
    w = np.array([d.get(str(int(g)), d.get("None")) for g in a.balls_bowled])
    if weights.get("mode") == "lin":
        return a.assign(p=w * a.p.to_numpy() + (1 - w) * b.p.to_numpy())
    return a.assign(p=sig(w * logit(a.p.to_numpy()) + (1 - w) * logit(b.p.to_numpy())))


def stack_score(a, b, weights):
    a, b = _sorted_pair(a, b)
    q = np.zeros((len(a), 3))
    for g in set(a.balls_bowled):
        m = (a.balls_bowled == g).to_numpy()
        d = weights["score"].get(str(int(g)), weights["score"].get("None"))
        for j, c in enumerate(QC):
            q[m, j] = d[c] * a.loc[m, c].to_numpy() + (1 - d[c]) * b.loc[m, c].to_numpy()
    out = a.copy()
    out[QC] = np.sort(q, axis=1)
    return out


def lofo(frames, folds_for_fit, test_fold, mode):
    """Weights for `test_fold` fitted on the other folds of `folds_for_fit` (leave-one-fold-out)."""
    return fit_weights([(frames[f][0]["v2-G1"], frames[f][0]["v1-sim-B"], frames[f][1][WIN_PICK], frames[f][1]["v1-sim-B"])
                        for f in folds_for_fit if f != test_fold], mode)


# ---------- report ----------
DEV_IPL = ("ipl2022", "ipl2023", "ipl2024", "ipl2025")
MODES = ("global", "cp", "lin")


def build_all():
    """frames[fold] = (score dict, win dict) for every cached fold, with v1-ens and v2-ens-<mode> (leave-one-fold-out weights) on IPL folds."""
    done = [f for f in IPL_FOLDS + LG_FOLDS if P(f"{f}_W").exists()]
    raw = {f: fold_frames(f) for f in done}
    out = {}
    for f in done:
        st, wn = raw[f]
        if f in IPL_FOLDS:
            st, wn = attach_ens(st, wn)
            for mode in MODES:
                w = lofo(raw, [x for x in DEV_IPL if x in raw], f, mode)
                st[f"v2-ens-{mode}"] = stack_score(raw[f][0]["v2-G1"], raw[f][0]["v1-sim-B"], w)
                wn[f"v2-ens-{mode}"] = stack_win(raw[f][1][WIN_PICK], raw[f][1]["v1-sim-B"], w)
        elif "v1-sim-B" in st:
            st, wn = attach_ens(st, wn)
            w = fit_weights([(raw[x][0]["v2-G1"], raw[x][0]["v1-sim-B"], raw[x][1][WIN_PICK], raw[x][1]["v1-sim-B"]) for x in DEV_IPL if x in raw], "lin")
            st["v2-ens-lin"], wn["v2-ens-lin"] = stack_score(raw[f][0]["v2-G1"], raw[f][0]["v1-sim-B"], w), stack_win(raw[f][1][WIN_PICK], raw[f][1]["v1-sim-B"], w)
        out[f] = (st, wn)
    return out, raw


def pool(frames, folds, kind):
    i = 0 if kind == "score" else 1
    names = [m for m in frames[folds[0]][i]]
    return {m: pd.concat([frames[f][i][m] for f in folds]) for m in names if all(m in frames[f][i] for f in folds)}


def mean4(fr, kind, col):
    t = per_checkpoint(fr, kind)
    t = t[t.cp == "mean of 4"].set_index("model")
    return t[col]


def pivot(frames, kind, col, groups):
    """models x groups table of one 'mean of 4' metric. groups = {label: list of folds}."""
    cols = {}
    for lab, fl in groups.items():
        fl = [f for f in fl if f in frames]
        if fl:
            cols[lab] = mean4(pool(frames, fl, kind), kind, col)
    return pd.DataFrame(cols)


def boot_ece(a, b, n=500, seed=0):
    """Paired bootstrap over matches of pooled-checkpoint ECE(a) - ECE(b). Returns (point, p5, p95)."""
    d = a.merge(b, on=KEYS, suffixes=("_a", "_b"))
    y, pa, pb = d.chase_won_a.to_numpy(), d.p_a.to_numpy(), d.p_b.to_numpy()
    idx = list(d.groupby("match_id").indices.values())
    rng = np.random.default_rng(seed)
    est = []
    for _ in range(n):
        j = np.concatenate([idx[i] for i in rng.integers(0, len(idx), len(idx))])
        est.append(ev.ece(y[j], pa[j]) - ev.ece(y[j], pb[j]))
    return ev.ece(y, pa) - ev.ece(y, pb), *np.quantile(est, [0.05, 0.95])


def boot_row(fa, fb, a, b, kinds):
    """One table row of paired-bootstrap differences (model a minus model b) for the given kinds."""
    r = {}
    for k in kinds:
        if k == "ece":
            p = boot_ece(fa[1][a], fb[1][b])
            r[k] = f"{p[0]:+.3f} [{p[1]:+.3f}, {p[2]:+.3f}]"
            continue
        sc = k in ("mae", "pinball")
        x, y = (fa[0][a], fb[0][b]) if sc else (fa[1][a], fb[1][b])
        p = bootstrap(x, y, k)
        r[k] = f"{p[0]:+.2f} [{p[1]:+.2f}, {p[2]:+.2f}]" if k == "mae" else f"{p[0]:+.3f} [{p[1]:+.3f}, {p[2]:+.3f}]"
    return r


def merged(frames, folds):
    """(score dict, win dict) pooled over folds."""
    return pool(frames, folds, "score"), pool(frames, folds, "win")


def drift_table(frames):
    rows = {}
    for f, (_, wn) in frames.items():
        for m, g in wn.items():
            rows.setdefault(m, {})[f] = float(g.p.mean() - g.chase_won.mean())
    t = pd.DataFrame(rows).T
    t.loc["actual chase win rate"] = {f: float(next(iter(wn.values())).chase_won.mean()) for f, (_, wn) in frames.items()}
    return t


def target_table(frames, folds, inn):
    tgt = inn[inn.innings == 2].set_index("match_id").target
    rows = {}
    for m in frames[folds[0]][1]:
        if not all(m in frames[f][1] for f in folds):
            continue
        g = pd.concat([frames[f][1][m] for f in folds])
        b = pd.cut(g.match_id.map(tgt), [0, 159.5, 189.5, 219.5, 999], labels=["<160", "160-189", "190-219", "220+"])
        d = (g.p - g.chase_won).groupby(b, observed=False).mean()
        rows[m] = {**d.round(3).to_dict(), "n(220+)": int((b == "220+").sum())}
    return pd.DataFrame(rows).T


def check_262(log):
    """PBKS chase of 262 v KKR (match 1426280, IPL 2024): P(chase wins) before the first ball."""
    out = {}
    w = pd.read_parquet(P("ipl2024_W"))
    w = w[(w.match_id == "1426280") & (w.balls_bowled == 0)]
    out.update({f"v2 {r.model}": float(r.p) for r in w.itertuples()})
    g = pd.read_parquet(OUT_DIR / "s4b_g1_W.parquet")
    g = g[(g.match_id == "1426280") & (g.balls_bowled == 0)]
    out["v1 G1"] = float(g.p.iloc[0])
    s = pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet")
    s = s[(s.match_id == "1426280") & (s.innings == 2) & (s.balls_bowled == 0)]
    out["v1 sim-B"] = float(s.win.iloc[0])
    log("\n#### PBKS chase of 262 (IPL 2024, match 1426280), P(chase wins) before ball 1\n" + md(pd.DataFrame({"model": list(out), "P(chase wins)": [round(v, 3) for v in out.values()]}), 3))
    return out


def plots(frames):
    plt = ev._plt()
    if plt is None:
        return
    # reliability: pooled IPL 2022-25 and IPL 2026
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, (lab, fl) in zip(axs, (("IPL 2022-25 (rolling)", list(DEV_IPL)), ("IPL 2026 (seen fold)", ["ipl2026"]))):
        w = pool(frames, fl, "win")
        ax.plot([0, 1], [0, 1], "--", color="grey")
        for m, st in (("v1-ens", "o-"), ("v1-sim-B", "s-"), ("w0", "x:"), (WIN_PICK, "^-"), ("v2-ens-lin", "d-")):
            if m in w:
                t = ev.reliability_table(w[m].chase_won, w[m].p, 10)
                ax.plot(t.pred, t.obs, st, ms=4, label=f"{m} (ECE {ev.ece(w[m].chase_won, w[m].p):.3f})")
        ax.set(title=lab, xlabel="predicted chase win probability")
        ax.legend(fontsize=7)
    axs[0].set_ylabel("observed win rate")
    fig.savefig(ev.IMG_DIR / "ml_v2_reliability.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    # drift: mean predicted - actual chase win rate by fold
    d = drift_table(frames).drop(index="actual chase win rate")
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for m in ("v1-G1", "v1-sim-B", "v1-ens", "w0", "w1", WIN_PICK, "v2-ens-lin"):
        if m in d.index:
            ax.plot(d.columns, d.loc[m].values, "o-", ms=4, label=m)
    ax.axhline(0, color="grey", ls=":")
    ax.set(ylabel="mean predicted - actual chase win rate", title="Chase-win bias by fold (0 = unbiased; negative = chasers under-rated)")
    ax.title.set_fontsize(9)
    ax.legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_v2_drift.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    # non-IPL reliability
    lgs = [f for f in LG_FOLDS if f in frames]
    if lgs:
        w = pool(frames, lgs, "win")
        fig, ax = plt.subplots(figsize=(4.8, 4.5))
        ax.plot([0, 1], [0, 1], "--", color="grey")
        for m, st in (("w0", "x:"), ("w1", "^-"), (WIN_PICK, "s-")):
            t = ev.reliability_table(w[m].chase_won, w[m].p, 10)
            ax.plot(t.pred, t.obs, st, ms=4, label=f"{m} (ECE {ev.ece(w[m].chase_won, w[m].p):.3f})")
        ax.set(title="Non-IPL leagues 2024+2025 (rolling)", xlabel="predicted chase win probability", ylabel="observed win rate")
        ax.legend(fontsize=7)
        fig.savefig(ev.IMG_DIR / "ml_v2_lg_reliability.png", dpi=110, bbox_inches="tight")
        plt.close(fig)
    # the 262 chase through the innings
    w = pd.read_parquet(P("ipl2024_W"))
    w = w[(w.match_id == "1426280") & (w.balls_bowled % 6 == 0) & (w.balls_bowled < 120)]
    g = pd.read_parquet(OUT_DIR / "s4b_g1_W.parquet")
    g = g[(g.match_id == "1426280") & (g.balls_bowled % 6 == 0) & (g.balls_bowled < 120)].sort_values("balls_bowled")
    s = pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet")
    s = s[(s.match_id == "1426280") & (s.innings == 2)].sort_values("balls_bowled")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(g.balls_bowled / 6, g.p, "o-", ms=3, label="v1 G1")
    for m, st in (("w1", "^-"), (WIN_PICK, "s-")):
        x = w[w.model == m].sort_values("balls_bowled")
        ax.plot(x.balls_bowled / 6, x.p, st, ms=3, label=f"v2 {m}")
    ax.plot(s.balls_bowled / 6, s.win, "d", ms=6, label="v1 sim-B (checkpoints)")
    ax.set(xlabel="overs bowled in the chase", ylabel="P(PBKS win)", ylim=(0, 1), title="PBKS chasing 262 v KKR, 2024-04-26 (chase WON)")
    ax.title.set_fontsize(9)
    ax.legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_v2_curve_1426280.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def report():
    out = []

    def log(x=""):
        print(x, flush=True)
        out.append(str(x))

    frames, raw = build_all()
    _, inn = load()
    groups = {"IPL 2022-25": list(DEV_IPL), **{f[3:]: [f] for f in DEV_IPL}, "IPL 2026 (seen)": ["ipl2026"]}
    n = {f: (len(next(iter(frames[f][0].values()))), len(next(iter(frames[f][1].values())))) for f in frames}
    log("States per fold (first-innings score rows / chase rows, 4 checkpoints): " + str(n))
    wk = lambda t: t.reindex([m for m in ("v1-G1", "w0", "w1m", "w1", "w2c", "w2", "w2s", "v1-sim-B", "v1-ens", "v2-ens-global", "v2-ens-cp", "v2-ens-lin") if m in t.index])  # noqa: E731
    sk = lambda t: t.reindex([m for m in ("v1-G1", "v2-G1", "v1-sim-B", "v1-ens", "v2-ens-global", "v2-ens-cp", "v2-ens-lin") if m in t.index])  # noqa: E731
    log("\n### IPL: chase win probability (mean of the 4 checkpoints)")
    for col in ("logloss", "brier", "ece"):
        log(f"\n{col}:\n" + md(wk(pivot(frames, "win", col, groups)).reset_index().rename(columns={"index": "model"}), 3))
    log("\n### IPL: first-innings score (mean of the 4 checkpoints)")
    for col in ("mae", "pinball", "cov80", "bias"):
        log(f"\n{col}:\n" + md(sk(pivot(frames, "score", col, groups)).reset_index().rename(columns={"index": "model"}), 3))

    ipl, ipl26 = merged(frames, list(DEV_IPL)), merged(frames, ["ipl2026"])
    log("\n### Paired bootstrap over matches (2000 resamples, 5-95%, mean-of-4 differences; negative = first model better; ECE: 500 resamples, pooled checkpoints)")
    rows = []
    cmp_ = [("w1m", "w0"), ("w1", "w0"), ("w2c", "w0"), ("w2", "w0"), ("w2s", "w0"), ("w2", "w1"), ("w2s", "w1"), ("w1", "w1m"),
            ("v2-ens-global", "v1-ens"), ("v2-ens-cp", "v1-ens"), ("v2-ens-lin", "v1-ens"), ("v2-ens-lin", "v1-sim-B"), ("v2-ens-global", "v1-sim-B"), ("v2-ens-global", "v2-ens-cp"), (WIN_PICK, "v1-sim-B")]
    for lab, fr in (("IPL 2022-25", ipl), ("IPL 2026", ipl26)):
        for a, b in cmp_:
            if a not in fr[1] or b not in fr[1]:
                continue
            r = {"fold": lab, "comparison": f"{a} - {b}"}
            r.update({k: v for k, v in boot_row(fr, fr, a, b, ("logloss", "brier", "ece")).items()})
            rows.append(r)
    log("\nChase side:\n" + md(pd.DataFrame(rows), 3))
    rows = []
    for lab, fr in (("IPL 2022-25", ipl), ("IPL 2026", ipl26)):
        for a, b in (("v2-G1", "v1-G1"), ("v2-ens-global", "v1-ens"), ("v2-ens-cp", "v1-ens"), ("v2-ens-lin", "v1-ens"), ("v2-ens-lin", "v1-sim-B"), ("v2-ens-global", "v1-sim-B"), ("v2-ens-global", "v2-ens-cp")):
            if a not in fr[0] or b not in fr[0]:
                continue
            rows.append({"fold": lab, "comparison": f"{a} - {b}", **boot_row(fr, fr, a, b, ("mae", "pinball"))})
    log("\nScore side:\n" + md(pd.DataFrame(rows), 3))

    lgf = [f for f in LG_FOLDS if f in frames]
    if lgf:
        log("\n### Non-IPL franchise leagues, rolling 2024 and 2025 (direct models only: sim-B has no cache for these leagues). v1 = w0 / G1 recipe")
        gl = {"leagues 2024+2025": lgf, **{f: [f] for f in lgf}}
        for col in ("logloss", "brier", "ece"):
            t = pivot(frames, "win", col, gl).reindex([m for m in (*WIN, "v1-sim-B", "v1-ens", "v2-ens-lin") if m in frames[lgf[0]][1]])
            log(f"\n{col}:\n" + md(t.reset_index().rename(columns={"index": "model"}), 3))
        for col in ("mae", "pinball", "cov80", "bias"):
            log(f"\nscore {col}:\n" + md(pivot(frames, "score", col, gl).reset_index().rename(columns={"index": "model"}), 3))
        lg = merged(frames, lgf)
        rows = []
        for a, b in (("w1m", "w0"), ("w1", "w0"), ("w2c", "w0"), ("w2", "w0"), ("w2s", "w0"), ("w2", "w1"), ("v2-ens-lin", "v1-ens"), ("v2-ens-lin", "v1-sim-B"), ("v1-ens", "v1-sim-B")):
            if a not in lg[1] or b not in lg[1]:
                continue
            rows.append({"comparison": f"{a} - {b}", **boot_row(lg, lg, a, b, ("logloss", "brier", "ece"))})
        log("\nBootstrap, leagues 2024+2025:\n" + md(pd.DataFrame(rows), 3))
        log("\nChase-win bias in the leagues (mean predicted - actual): " + str(drift_table({f: frames[f] for f in lgf}).round(3).to_dict("index")))
    log("\n### Mean predicted minus actual chase win rate by fold (negative = chasers under-rated)\n" + md(drift_table(frames).round(3).reset_index().rename(columns={"index": "model"}), 3))
    ks = {f: int(pd.read_parquet(P(f"{f}_W")).k_season.iloc[0]) for f in frames}
    log("Season weight k tuned per fold (chase_season = (wins so far + k*long-run)/(matches so far + k)): " + str(ks))
    log("\n### Calibration by target size (mean predicted - actual chase win; IPL 2022-26 checkpoint states)\n" + md(target_table(frames, list(DEV_IPL) + ["ipl2026"], inn).reset_index().rename(columns={"index": "model"}), 3))
    check_262(log)
    w = {m: fit_weights([(frames[f][0]["v2-G1"], frames[f][0]["v1-sim-B"], frames[f][1][WIN_PICK], frames[f][1]["v1-sim-B"]) for f in DEV_IPL], m) for m in MODES}
    log("\n### Stacking weights fitted on IPL 2022-25 (weight on the direct v2 model; the rest goes to sim-B)\n" + json.dumps(w, indent=1))
    allw = {m: fit_weights([(frames[f][0]["v2-G1"], frames[f][0]["v1-sim-B"], frames[f][1][WIN_PICK], frames[f][1]["v1-sim-B"]) for f in IPL_FOLDS if f in frames], m) for m in MODES}
    V2_DIR.mkdir(parents=True, exist_ok=True)
    (V2_DIR / "stack_weights.json").write_text(json.dumps(allw, indent=1))  # fitted on IPL 2022-26: used by `fresh`
    log("Weights fitted on IPL 2022-26 (used by `fresh`): " + json.dumps(allw))
    plots(frames)
    (OUT_DIR / "v2_report.md").write_text("\n".join(out), encoding="utf-8")
    return frames


if __name__ == "__main__" and sys.argv[1:2] == ["run"]:
    run(sys.argv[2:] or None)
elif __name__ == "__main__" and sys.argv[1:2] == ["report"]:
    report()


# ---------- the fresh-holdout comparison (the lead runs this) ----------
STACK_MODE = "lin"  # which stacking weights v2-ens uses (set from the dev results)


def checkpoint_keys(states, ids):
    """Usable checkpoint states (same filter as sim_eval.test_keys) of the given matches."""
    t = states[states.match_id.isin(ids) & ~states.reduced & states.balls_bowled.isin(CP) & (states.balls_left > 0) & (states.wickets < 10)]
    t = t[(t.innings == 1) | (t.chase_won.notna() & (t.runs_needed > 0))]
    return t[["match_id", "innings", "balls_bowled", "final_total", "chase_won"]]


def sim_b(states, keys, cut, fresh_ids, n_sims, log):
    """sim-B (ball simulator, variant B) trained on ALL men's T20 seasons < cut (IPL season cut-1 as the inner early-stopping fold),
    locked matches removed from training; simulates every state in `keys`. Returns (score frame, win frame) at the checkpoints."""
    from .ball_model import BallModel, load_balls
    from .simulate import fill_missing_batter, simulate, start_states, summarize

    balls = load_balls()
    balls = balls[~balls.reduced & balls.lvl_slow.notna()]
    train = balls[~balls.match_id.isin(fresh_ids) & (balls.competition != "hundred")]
    ev.assert_no_fresh(states[states.match_id.isin(set(train.match_id))].drop_duplicates("match_id"), "sim-B train")
    m = BallModel("B").fit(train[train.season_year < cut - 1], train[(train.season_year == cut - 1) & (train.competition == "ipl")])
    m = BallModel("B").fit(train[train.season_year < cut], None, n_rounds=int(m.best_iter * 1.1) + 1)
    log(f"sim-B trained ({m.best_iter} rounds); simulating {len(keys)} states x {n_sims} paths")
    out = []
    for k, kk in keys.groupby("balls_bowled"):
        k = int(k)
        st = fill_missing_batter(start_states(balls[balls.match_id.isin(kk.match_id)], kk[["match_id", "innings"]].to_numpy(), k), m)
        res = simulate(m, st, n=n_sims, seed=k)
        yv = kk.set_index(["match_id", "innings"]).loc[list(zip(st.match_id, st.innings))]
        d = pd.concat([st[["match_id", "innings", "balls_bowled"]], summarize(res["final"])], axis=1)
        d["p"], d["final_total"], d["chase_won"] = res["win"], yv.final_total.to_numpy(float), yv.chase_won.to_numpy(float)
        out.append(d)
    r = pd.concat(out, ignore_index=True)
    return r[r.innings == 1][KEEP_S], r[(r.innings == 2) & r.chase_won.notna()][KEEP_W]


def fresh(rehearse=False, n_sims=1000, max_matches=0):
    """Pre-registered v1 vs v2 comparison on the fresh holdout (men's non-IPL franchise leagues dated >= 2026-01-01).
    rehearse=True runs the SAME code on dev data (non-IPL leagues season 2025 as the pretend holdout) and never touches locked rows."""
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:5.0f}s] {m}", flush=True)  # noqa: E731
    states_all, inn_all = load()
    states, inn = drop_fresh(states_all, inn_all)
    lg = lambda f: f.competition.isin(ev.FRESH_LEAGUES)  # noqa: E731
    if rehearse:
        cut, tname = 2025, "lg2025"
        test_sel, val_sel = (lambda f: lg(f) & (f.season_year == 2025)), (lambda f: lg(f) & (f.season_year == 2024))
        tag = "rehearsal"
    else:
        cut, tname = 2027, "ipl2026"  # train on everything dated < 2026-01-01 plus IPL 2026; inner fold = IPL 2026
        test_sel, val_sel = (lambda f: lg(f) & ev.fresh_holdout_mask(f)), (lambda f: (f.competition == "ipl") & (f.season_year == 2026))
        tag = "fresh"
        log("OPENING THE FRESH HOLDOUT (men's non-IPL franchise leagues, >= 2026-01-01). This is the one pre-registered run.")
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    k, _ = F.tune_k_chase(inn, cut)
    train_feat = F.add_v2(D.prep(F.build_features(states, inn, kv, kt)), inn, k)  # built WITHOUT the locked matches
    if rehearse:
        test = train_feat[test_sel(train_feat)]
        ev.assert_no_fresh(test, "test")
    else:  # test features come from the full history (a live forecast knows earlier 2026 matches); prior-only, so no result leaks into its own row
        full = F.add_v2(D.prep(F.build_features(states_all, inn_all, kv, kt)), inn_all, k)
        test = ev.assert_no_fresh(full[test_sel(full)], "test", allow_fresh=True)
        del full
    log(f"k_season={k}; test rows {len(test)} ({test.match_id.nunique()} matches); training rows {len(train_feat)}")
    models = train_models(train_feat, cut, val_sel, tuned_cfg(tname), variants=("w0", WIN_PICK), log=log)
    save_models(models, tag)
    S, W = predict_models(models, test, tag)
    ids = sorted(set(test.match_id))
    if max_matches:
        ids = list(np.random.default_rng(0).choice(ids, min(max_matches, len(ids)), replace=False))
    keys = checkpoint_keys(states_all if not rehearse else states, ids)
    fresh_ids = set(inn_all.match_id[ev.fresh_holdout_mask(inn_all)]) if not rehearse else set(inn_all.match_id[ev.fresh_holdout_mask(inn_all)]) | set(test.match_id)
    if rehearse:
        sS, sW = sim_b(states_all, keys, cut, fresh_ids, n_sims, log)
    else:  # the sim worker's men's-pool sim-B (matches < 2026-01-01 + IPL 2026): simfix.fit_fresh() must have been run once
        from .simfix import predict_checkpoints

        r = predict_checkpoints(keys[["match_id", "innings", "balls_bowled"]], "ball_B_men_fresh", n=n_sims)
        r = r.rename(columns={"win": "p"}).merge(keys[["match_id", "innings", "balls_bowled", "final_total", "chase_won"]], on=["match_id", "innings", "balls_bowled"])
        sS, sW = r[r.innings == 1][KEEP_S], r[(r.innings == 2) & r.chase_won.notna()][KEEP_W]
    cp = lambda d: d[d.balls_bowled.isin(CP)]  # noqa: E731
    Wc = cp(W[W.chase_won.notna()])
    st = {"v1-G1": cp(S)[KEEP_S], "v2-G1": cp(S)[KEEP_S], "v1-sim-B": sS}
    wn = {"v1-G1": Wc[Wc.model == "w0"][KEEP_W], WIN_PICK: Wc[Wc.model == WIN_PICK][KEEP_W], "v1-sim-B": sW}
    st, wn = align(st), align(wn)
    weights = json.loads((V2_DIR / "stack_weights.json").read_text())[STACK_MODE]
    st, wn = attach_ens(st, wn, weights)
    st["v2-direct"], wn["v2-direct"] = st["v2-G1"], wn[WIN_PICK]
    rep = []

    def pr(x=""):
        print(x, flush=True)
        rep.append(str(x))

    pr(f"## {tag}: v1 vs v2 on {len(wn['v1-ens'])} chase states ({wn['v1-ens'].match_id.nunique()} matches) and {len(st['v1-ens'])} first-innings states ({st['v1-ens'].match_id.nunique()} matches); sim-B {n_sims} paths")
    pr(f"stacking weights ({STACK_MODE}, fitted on IPL 2022-26): {json.dumps(weights)}")
    ts, tw = per_checkpoint(st, "score"), per_checkpoint(wn, "win")
    pr("\nScore (mean of 4 checkpoints):\n" + md(ts[ts.cp == "mean of 4"].drop(columns="cp"), 3))
    pr("\nChase (mean of 4 checkpoints):\n" + md(tw[tw.cp == "mean of 4"].drop(columns="cp"), 3))
    pooled_ece = {m: ev.ece(g.chase_won, g.p) for m, g in wn.items()}
    pr("\nPooled ECE: " + str({m: round(v, 3) for m, v in pooled_ece.items()}))
    fr = (st, wn)
    rows = []
    for a, b in (("v2-ens", "v1-ens"), ("v2-ens", "v1-sim-B"), ("v2-direct", "v1-G1"), ("v1-ens", "v1-sim-B")):
        rows.append({"comparison": f"{a} - {b}", **boot_row(fr, fr, a, b, ("mae", "pinball", "logloss", "brier", "ece"))})
    pr("\nPaired bootstrap over matches (5-95%; negative = first model better):\n" + md(pd.DataFrame(rows), 3))
    mae_d, ll_d = bootstrap(st["v2-ens"], st["v1-ens"], "mae"), bootstrap(wn["v2-ens"], wn["v1-ens"], "logloss")
    e4 = float(tw[(tw.model == "v2-ens") & (tw.cp == "mean of 4")].ece.iloc[0])
    crit = [("chase log loss beats v1 ens-G1, interval excludes 0", f"{ll_d[0]:+.3f} [{ll_d[1]:+.3f}, {ll_d[2]:+.3f}]", ll_d[2] < 0),
            ("score MAE no worse than v1 ens-G1 (interval includes or is below 0)", f"{mae_d[0]:+.2f} [{mae_d[1]:+.2f}, {mae_d[2]:+.2f}]", mae_d[1] <= 0),
            ("ECE < 0.08 (mean of 4 checkpoints)", f"{e4:.3f} (pooled {pooled_ece['v2-ens']:.3f})", e4 < 0.08)]
    pr("\n#### Pre-registered adoption rule for v2\n" + md(pd.DataFrame([{"criterion": c, "value": v, "result": "PASS" if ok else "FAIL"} for c, v, ok in crit])))
    pr("v2 ADOPTED: " + ("YES" if all(ok for *_, ok in crit) else "NO"))
    comp = inn_all[inn_all.innings == 2].set_index("match_id").competition
    d = pd.DataFrame({m: wn[m].assign(c=wn[m].match_id.map(comp)).groupby("c").apply(lambda g: g.p.mean() - g.chase_won.mean()) for m in ("v1-ens", "v2-ens", "v1-sim-B", "v2-direct")})
    d["n matches"] = wn["v1-ens"].groupby(wn["v1-ens"].match_id.map(comp)).match_id.nunique()
    d["actual chase rate"] = wn["v1-ens"].assign(c=wn["v1-ens"].match_id.map(comp)).groupby("c").chase_won.mean()
    pr("\nMean predicted - actual chase win by league:\n" + md(d.round(3).reset_index().rename(columns={"c": "league"}), 3))
    (OUT_DIR / f"v2_{tag}_report.md").write_text("\n".join(rep), encoding="utf-8")
    for n_, f_ in (("S", pd.concat([x.assign(model=k_) for k_, x in st.items()])), ("W", pd.concat([x.assign(model=k_) for k_, x in wn.items()]))):
        f_.to_parquet(P(f"{tag}_{n_}"))
    plt = ev._plt()
    if plt is not None:
        fig, ax = plt.subplots(figsize=(4.8, 4.5))
        ax.plot([0, 1], [0, 1], "--", color="grey")
        for m in ("v1-ens", "v1-sim-B", "v2-direct", "v2-ens"):
            t = ev.reliability_table(wn[m].chase_won, wn[m].p, 10)
            ax.plot(t.pred, t.obs, "o-", ms=4, label=f"{m} (ECE {pooled_ece[m]:.3f})")
        ax.set(title=f"{tag}: chase win reliability", xlabel="predicted", ylabel="observed")
        ax.legend(fontsize=7)
        fig.savefig(ev.IMG_DIR / f"ml_v2_{tag}_reliability.png", dpi=110, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__" and sys.argv[1:2] == ["final"]:
    final()
elif __name__ == "__main__" and sys.argv[1:2] == ["fresh"]:
    a = sys.argv[2:]
    fresh(rehearse="--rehearse" in a, n_sims=int(a[a.index("--sims") + 1]) if "--sims" in a else 1000,
          max_matches=int(a[a.index("--max-matches") + 1]) if "--max-matches" in a else 0)
