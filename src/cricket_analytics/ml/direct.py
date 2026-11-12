"""S3 / S4: LightGBM direct models. Score quantiles (q10/q50/q90 of remaining runs) and chase win probability.

Rolling origin: test IPL season Y trained on seasons < Y only (2026 holdout is never opened).
Tuning is on an INNER fold: validation = IPL season Y-1, training = pool rows of seasons < Y-1; the chosen config and
iteration counts are then refit on all seasons < Y. S4 variants reuse the S3 config / iterations of the same fold.
Run: python -m cricket_analytics.ml.direct   (about an hour; caches to data/external/ml/direct_*)
"""

import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from . import evaluate as ev
from . import features as F
from .baselines import CHECK, Resource, md, usable
from .dataset import OUT_DIR, load

YEARS = (2022, 2023, 2024, 2025)
QS = (0.1, 0.5, 0.9)
CONFIGS = [
    dict(num_leaves=15, min_child_samples=200),
    dict(num_leaves=31, min_child_samples=200),
    dict(num_leaves=63, min_child_samples=500),
]
BASE = dict(learning_rate=0.05, feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=10.0, verbose=-1, seed=7)
MAX_ROUNDS, PATIENCE = 500, 30
MODEL_DIR = OUT_DIR / "models"
META = ["match_id", "innings", "balls_bowled", "final_total", "chase_won", "season_year", "competition", "venue", "batting_team", "date"]

# pool name -> (row filter, stride, recency weights?)
POOLS = {
    "ipl_all": (lambda d, y: d.competition == "ipl", 2, False),
    "ipl2015": (lambda d, y: (d.competition == "ipl") & (d.season_year >= 2015), 2, False),
    "ipl2020": (lambda d, y: (d.competition == "ipl") & (d.season_year >= 2020), 2, False),
    "impact": (lambda d, y: (d.competition == "ipl") & (d.season_year >= 2023), 2, False),
    "global": (lambda d, y: d.season_year >= 0, 4, False),
    "global_rw": (lambda d, y: d.season_year >= 0, 4, True),
}


# ---------- rows ----------
def score_rows(d, innings=1):
    """Non-reduced undecided states of one innings; target = remaining runs."""
    d = usable(d[d.innings == innings])
    return d, (d.final_total - d.runs).to_numpy()


def win_rows(d):
    d = usable(d[d.innings == 2])
    return d[d.chase_won.notna() & (d.runs_needed > 0)]


def pool_rows(feat, pool, year, last=None):
    """Training rows of `pool` for test season `year` (seasons < year, or < last if given), with weights."""
    sel, stride, rw = POOLS[pool]
    cut = year if last is None else last
    d = feat[(feat.season_year < cut) & sel(feat, year)]
    d = d[d.balls_bowled % stride == 0]
    w = np.ones(len(d))
    if rw:  # half-life 2 seasons, IPL x3
        w = 0.5 ** ((cut - 1 - d.season_year.to_numpy()) / 2.0) * np.where(d.competition == "ipl", 3.0, 1.0)
    return d, w


# ---------- fitting ----------
def _ds(d, y, cols, w=None):
    return lgb.Dataset(d[cols], y, weight=w, categorical_feature=["comp_code"] if "comp_code" in cols else [], free_raw_data=False)


def fit_score(tr, w, cols, cfg, rounds=None, val=None, innings=1):
    """Three quantile boosters. rounds=None -> early stopping on val. Returns {q: (booster, n_iter)}."""
    d, y = score_rows(tr, innings)
    w = w[tr.index.isin(d.index)]
    out = {}
    for q in QS:
        p = {**BASE, **cfg, "objective": "quantile", "alpha": q, "metric": "quantile"}
        ds = _ds(d, y, cols, w)
        if val is None:
            out[q] = (lgb.train(p, ds, rounds[q]), rounds[q])
        else:
            vd, vy = score_rows(val, innings)
            b = lgb.train(p, ds, MAX_ROUNDS, valid_sets=[_ds(vd, vy, cols)], callbacks=[lgb.early_stopping(PATIENCE, verbose=False)])
            out[q] = (b, max(b.best_iteration, 10))
    return out


def predict_score(models, d, cols):
    q = np.column_stack([models[k][0].predict(d[cols], num_iteration=models[k][1]) for k in QS])
    q = np.sort(q, axis=1)  # no crossing quantiles
    return pd.DataFrame(np.maximum(q, 0) + d.runs.to_numpy()[:, None], columns=["q10", "q50", "q90"], index=d.index)


def fit_win(tr, w, cols, cfg, rounds=None, val=None):
    d = win_rows(tr)
    w = w[tr.index.isin(d.index)]
    p = {**BASE, **cfg, "objective": "binary", "metric": "binary_logloss"}
    ds = _ds(d, d.chase_won.to_numpy(), cols, w)
    if val is None:
        return lgb.train(p, ds, rounds), rounds
    vd = win_rows(val)
    b = lgb.train(p, ds, MAX_ROUNDS, valid_sets=[_ds(vd, vd.chase_won.to_numpy(), cols)], callbacks=[lgb.early_stopping(PATIENCE, verbose=False)])
    return b, max(b.best_iteration, 10)


def tune(feat, year, cols):
    """Inner fold for test `year`: pick the config + iteration counts on IPL season year-1 (pool = ipl_all, seasons < year-1)."""
    tr, w = pool_rows(feat, "ipl_all", year, last=year - 1)
    val = feat[(feat.competition == "ipl") & (feat.season_year == year - 1) & (feat.balls_bowled % 2 == 0)]
    best_s, best_w = None, None
    for i, cfg in enumerate(CONFIGS):
        m = fit_score(tr, w, cols, cfg, val=val)
        loss = sum(m[q][0].best_score["valid_0"]["quantile"] for q in QS)
        if best_s is None or loss < best_s[0]:
            best_s = (loss, i, {str(q): m[q][1] for q in QS})
        b, n = fit_win(tr, w, cols, cfg, val=val)
        ll = b.best_score["valid_0"]["binary_logloss"]
        if best_w is None or ll < best_w[0]:
            best_w = (ll, i, n)
    return {"score_cfg": best_s[1], "score_iters": best_s[2], "score_val": best_s[0],
            "win_cfg": best_w[1], "win_iters": best_w[2], "win_val": best_w[0]}


def platt(model_pred, y):
    """Platt scaling on logit(p): returns f(p)."""
    lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6))).reshape(-1, 1)  # noqa: E731
    lr = LogisticRegression(C=100).fit(lg(model_pred), y)
    return lambda p: lr.predict_proba(lg(p))[:, 1]


# ---------- experiment ----------
def run_variant(feat, states, name, pool, fset, tuned, years=YEARS, comp="ipl", calibrate=False, save=False):
    """Rolling-origin run. Returns (S, W): test-row predictions (long, with model/fold columns)."""
    cols = F.FEATURE_SETS[fset]
    S, W = [], []
    for Y in years:
        tr, w = pool_rows(feat, pool, Y)
        if len(tr) == 0 or tr.season_year.nunique() < 1:
            continue
        t = tuned[str(Y)]
        test = usable(feat[(feat.season_year == Y) & (feat.competition == comp)])
        t1 = test[test.innings == 1]
        t2 = win_rows(test)
        sm = fit_score(tr, w, cols, CONFIGS[t["score_cfg"]], rounds={q: t["score_iters"][str(q)] for q in QS})
        S.append(t1[META].assign(model=name, fold=Y, **predict_score(sm, t1, cols)))
        wm, n = fit_win(tr, w, cols, CONFIGS[t["win_cfg"]], rounds=t["win_iters"])
        p = wm.predict(t2[cols])
        W.append(t2[META].assign(model=name, fold=Y, p=p))
        if calibrate:  # Platt fitted on the inner fold (train seasons only): model w/o season Y-1 -> predictions on Y-1
            tr2, w2 = pool_rows(feat, pool, Y, last=Y - 1)
            wi, _ = fit_win(tr2, w2, cols, CONFIGS[t["win_cfg"]], rounds=t["win_iters"])
            v = win_rows(feat[(feat.competition == comp) & (feat.season_year == Y - 1)])
            f = platt(wi.predict(v[cols]), v.chase_won.to_numpy())
            W.append(t2[META].assign(model=name + "+platt", fold=Y, p=f(p)))
        if save:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            for q in QS:
                sm[q][0].save_model(str(MODEL_DIR / f"{name}_{Y}_score_q{int(q * 100)}.txt"), num_iteration=sm[q][1])
            wm.save_model(str(MODEL_DIR / f"{name}_{Y}_win.txt"))
        # train-set metrics (overfit check, innings-weighted) on the fit rows
        if save:
            d, y = score_rows(tr)
            pr = predict_score(sm, d, cols)
            wt = ev.match_weights(d)
            gap = {"fold": Y, **{f"train_{k}": v for k, v in ev.score_metrics(d.final_total, pr.q10, pr.q50, pr.q90, wt).items()}}
            dw = win_rows(tr)
            gap["train_logloss"] = ev.log_loss(dw.chase_won, wm.predict(dw[cols]), ev.match_weights(dw))
            gp = OUT_DIR / "direct_gap.json"
            old = json.loads(gp.read_text()) if gp.exists() else {}
            old[f"{name}_{Y}"] = gap
            gp.write_text(json.dumps(old, indent=1))
    S, W = pd.concat(S), pd.concat(W)
    return S, W


def baseline_preds(states, years=YEARS, comp="ipl"):
    S, W = [], []
    for _, train, test in ev.rolling_splits(states, years):
        test = usable(test[test.competition == comp])
        t1, t2 = test[test.innings == 1], win_rows(test)
        m = Resource("ipl").fit(train)
        Y = int(test.season_year.iloc[0])
        S.append(t1[META].assign(model="resource-ipl", fold=Y, **m.score(t1)))
        W.append(t2[META].assign(model="resource-ipl", fold=Y, p=m.win(t2)))
    return pd.concat(S), pd.concat(W)


# ---------- tables ----------
def summarise(S, W, years=None):
    """One row per model: score metrics (6/10/15 over MAE + innings-weighted overall) and win metrics."""
    if years is not None:
        S, W = S[S.fold.isin(years)], W[W.fold.isin(years)]
    rows = []
    for name in dict.fromkeys(list(S.model) + list(W.model)):
        s, w = S[S.model == name], W[W.model == name]
        r = {"model": name, "n_inn": s.groupby(["match_id", "innings"]).ngroups}
        for lab, b in CHECK[1:]:
            r[f"MAE@{lab.split()[0]}"] = ev.mae(s[s.balls_bowled == b].final_total, s[s.balls_bowled == b].q50)
        if len(s):
            m = ev.score_metrics(s.final_total, s.q10, s.q50, s.q90, ev.match_weights(s))
            r.update(MAE=m["mae"], pinball=m["pinball"], cov80=m["cov80"], bias=m["bias"])
        if len(w):
            wm = ev.win_metrics(w.chase_won, w.p, ev.match_weights(w))
            r.update(ll=wm["logloss"], brier=wm["brier"], ece=wm["ece"])
            for lab, b in CHECK[2:]:
                x = w[w.balls_bowled == b]
                r[f"ll@{lab.split()[0]}"] = ev.log_loss(x.chase_won, x.p)
        rows.append(r)
    return pd.DataFrame(rows)


def boot_diff(A, B, kind, years=None, n=2000, seed=0):
    """Innings-weighted loss(A) - loss(B), bootstrapped over MATCHES. kind: 'mae' (A,B score preds) or 'll' (win preds).
    Returns (mean, p5, p95, n_matches). Negative = A better."""
    if years is not None:
        A, B = A[A.fold.isin(years)], B[B.fold.isin(years)]
    key = ["match_id", "innings", "balls_bowled"]
    A, B = A.sort_values(key), B.sort_values(key)
    A, B = A.merge(B[key], on=key), B.merge(A[key], on=key)  # same rows only
    w = ev.match_weights(A)
    if kind == "mae":
        la, lb = (A.final_total - A.q50).abs(), (B.final_total - B.q50).abs()
    else:
        def ll(d):
            p = np.clip(d.p, 1e-6, 1 - 1e-6)
            return -(d.chase_won * np.log(p) + (1 - d.chase_won) * np.log(1 - p))
        la, lb = ll(A), ll(B)
    g = pd.DataFrame({"m": A.match_id.to_numpy(), "a": la.to_numpy() * w, "b": lb.to_numpy() * w, "w": w}).groupby("m").sum()
    rng = np.random.default_rng(seed)
    c = rng.multinomial(len(g), np.ones(len(g)) / len(g), size=n)
    den = c @ g.w.to_numpy()
    d = (c @ g.a.to_numpy() - c @ g.b.to_numpy()) / den
    return float(d.mean()), float(np.percentile(d, 5)), float(np.percentile(d, 95)), len(g)


# ---------- main ----------
def _pq(name):
    return OUT_DIR / f"direct_{name}_score.parquet", OUT_DIR / f"direct_{name}_win.parquet"


def cached(name, fn):
    ps, pw = _pq(name)
    if ps.exists() and pw.exists():
        return pd.read_parquet(ps), pd.read_parquet(pw)
    S, W = fn()
    S.to_parquet(ps)
    W.to_parquet(pw)
    return S, W


def prep(df):
    keep = META + ["reduced", "balls_left", "runs_needed", "gender"] + F.FEATURES
    keep = list(dict.fromkeys(c for c in keep if c in df.columns))
    d = df[keep].copy()
    for c in d.select_dtypes("float64"):
        d[c] = d[c].astype("float32")
    return d


if __name__ == "__main__":
    t0 = time.time()
    log = lambda m: print(f"[{time.time() - t0:5.0f}s] {m}", flush=True)  # noqa: E731
    states, inn = load()
    kv, kt, mse = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    log(f"shrinkage k_venue={kv} k_team={kt} (val mse {mse:.0f})")
    feat = prep(F.build_features(states, inn, kv, kt))
    log(f"features built {feat.shape}")

    tp = OUT_DIR / "direct_tuned.json"
    if tp.exists():
        tuned = json.loads(tp.read_text())
    else:
        tuned = {str(Y): tune(feat, Y, F.FEATURE_SETS["full"]) for Y in YEARS}
        tp.write_text(json.dumps(tuned, indent=1))
    log(f"tuned: {json.dumps(tuned)}")

    Sb, Wb = cached("baseline", lambda: baseline_preds(states))
    res = {}
    for pool in POOLS:
        yrs = (2024, 2025) if pool == "impact" else YEARS
        res[pool] = cached(f"pool_{pool}", lambda: run_variant(feat, states, f"lgbm-{pool}", pool, "full", tuned, yrs,
                                                              calibrate=(pool == "ipl_all"), save=(pool == "ipl_all")))
        log(f"pool {pool} done")
    log("done pools")
    # hierarchy + ablation on the best pool (lowest mean of MAE rank and pinball rank, men's IPL 2022-25, impact excluded)
    allS = pd.concat([Sb] + [res[p][0] for p in POOLS if p != "impact"])
    allW = pd.concat([Wb] + [res[p][1] for p in POOLS if p != "impact"])
    sm = summarise(allS, allW)
    sm = sm[sm.model.str.startswith("lgbm") & ~sm.model.str.contains("platt")]
    best = sm.assign(r=sm.MAE.rank() + sm.pinball.rank()).sort_values("r").model.iloc[0].replace("lgbm-", "")
    log(f"best pool: {best}")
    cached(f"var_{best}_nolevel", lambda: run_variant(feat, states, f"lgbm-{best}-nolevel", best, "no_level", tuned))
    cached(f"var_{best}_none", lambda: run_variant(feat, states, f"lgbm-{best}-none", best, "none", tuned))
    log("variants none/no_level done")
    del feat
    raw = prep(F.build_features(states, inn, 0.0, 0.0, 0.0))
    cached(f"var_{best}_raw", lambda: run_variant(raw, states, f"lgbm-{best}-raw", best, "full", tuned))
    log("done all")
