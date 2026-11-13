"""Drawing board, model fits: LightGBM recipe variants (D3, D4) and other model families (M1 k-NN, M2 spline GAM, M3 MLP, M4 stretch).

  python -m cricket_analytics.ml.drawing_board_fit g2oe d3 d4a d4b d4c d4d m1 m2 m3 m4 report

Every fit is a rolling origin: test season Y (IPL Y; plus men's non-IPL Y for 2024-25; IPL 2026 is the already-seen fold), trained on seasons < Y only,
early-stopping / tuning on season Y-1 (all competitions, never the test season). Test states = over ends (balls_bowled % 6 == 0).
The locked fresh set (men's non-IPL >= 2026-01-01) is not in the feature table. Caches: data/external/ml/db_<name>_{S,W}.parquet.
"""

import contextlib
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import direct as D
from . import drawing_board as B
from . import flaw_fit as FF
from . import flaw_tests as T
from .baselines import usable
from .dataset import OUT_DIR

oe, _n, KEY, SCOPES = B.oe, B._n, B.KEY, B.SCOPES
YEARS5 = (2022, 2023, 2024, 2025)  # IPL 2026 (seen fold) is skipped here to save time; slopes (D1) and the G1/G2 caches cover it
NEED = list(dict.fromkeys(D.META + ["reduced", "balls_left", "runs_needed", "gender"] + B.G2_COLS + ["runs_l12", "wk_l12", "runs_l6", "wk_l6"]))
THREADS = 4  # LightGBM threads; the machine is shared with other heavy jobs and 16 oversubscribed threads are far slower
NB = 8  # residual buckets: over bucket (4) x (3+ wickets down?)


@contextlib.contextmanager
def lgb_budget(rounds, patience):
    """Temporarily raise direct.py's early-stopping budget (restored on exit)."""
    old = (D.MAX_ROUNDS, D.PATIENCE)
    D.MAX_ROUNDS, D.PATIENCE = rounds, patience
    try:
        yield
    finally:
        D.MAX_ROUNDS, D.PATIENCE = old


def load_train(cols=None):
    return B.load_feat(list(dict.fromkeys(cols or NEED)), even=True)


def fold_sets(feat, Y):
    """(train rows seasons < Y + weights, inner-train rows seasons < Y-1 + weights, inner validation = ALL competitions of season Y-1, test over-end states)."""
    tr, w = D.pool_rows(feat, "global", Y)
    itr, iw = D.pool_rows(feat, "global", Y, last=Y - 1)
    val = feat[(feat.season_year == Y - 1) & (feat.balls_bowled % 2 == 0)]
    return tr, w, itr, iw, val, oe(FF.test_rows(feat, Y))


def bucket(d):
    return D.over_bucket(d.balls_bowled.to_numpy()) * 2 + (d.wickets.to_numpy() >= 3).astype(int)


def resid_quantiles(res, bk, qs=(0.1, 0.5, 0.9), min_n=200):
    allq = np.quantile(res, qs)
    return {b: (np.quantile(res[bk == b], qs) if (bk == b).sum() >= min_n else allq) for b in range(NB)}


def apply_resid(mu, scale, bk, rq):
    q = np.array([rq[int(b)] for b in bk])
    return np.sort(mu[:, None] + scale[:, None] * q, axis=1)


def pack_s(t1, q, name, Y):
    q = np.maximum(q, t1.runs.to_numpy(float)[:, None])
    return t1[D.META].assign(model=name, fold=Y, q10=q[:, 0], q50=q[:, 1], q90=q[:, 2])


def pack_w(t2, p, name, Y):
    return t2[D.META].assign(model=name, fold=Y, p=np.clip(p, 1e-4, 1 - 1e-4))


# ---------- LightGBM variants ----------
def run_gbm(feat, name, cols, cfg_extra=None, scale="lvl_season", years=YEARS5, budget=None):
    """G2 recipe with options (columns, config overrides, target scale, early-stopping budget). Test rows = over-end states."""
    tuned = FF.tuned_cfg()
    S, W = [], []
    for Y in years:
        t = tuned[str(Y)]
        tr, w, itr, iw, val, test = fold_sets(feat, Y)
        cfg, cw = ({**D.CONFIGS[t[k]], "num_threads": THREADS, **(cfg_extra or {})} for k in ("score_cfg", "win_cfg"))
        with lgb_budget(*(budget or (D.MAX_ROUNDS, D.PATIENCE))):
            inner = D.fit_score(itr, iw, cols, cfg, val=val, scale=scale)
            sm = D.fit_score(tr, w, cols, cfg, rounds={q: inner[q][1] for q in D.QS}, scale=scale)
            wi, n = D.fit_win(itr, iw, cols, cw, val=val)
            wm, _ = D.fit_win(tr, w, cols, cw, rounds=n)
        t1, t2 = test[test.innings == 1], D.win_rows(test)
        v1 = usable(val)
        v1 = v1[v1.innings == 1]
        v = v1[D.META].assign(**D.predict_score(inner, v1, cols, scale=scale))
        dl = D.conformal_delta(v.final_total, v.q10, v.q90, D.over_bucket(v.balls_bowled))
        s = t1[D.META].assign(model=name, fold=Y, **D.predict_score(sm, t1, cols, scale=scale))
        lo, hi = D.conformal_apply(s.q10, s.q50, s.q90, D.over_bucket(s.balls_bowled), dl)
        S.append(s.assign(q10=np.asarray(lo), q90=np.asarray(hi)))
        W.append(pack_w(t2, wm.predict(t2[cols]), name, Y))
        print(f"  {name} fold {Y}: rounds {[inner[q][1] for q in D.QS]} win {n}", flush=True)
    return _n(pd.concat(S)), _n(pd.concat(W))


def _mk(d, scale, objective):
    d, y = D.score_rows(d, 1)
    if scale:
        s = D.target_scale(d, scale)
        return d, y / s, (s ** 2 if objective == "regression" else s)
    return d, y.astype(float), np.ones(len(d))


def fit_mean(tr, cols, cfg, val, scale, objective, rounds=None):
    d, y, w = _mk(tr, scale, objective)
    p = {**D.BASE, **cfg, "objective": objective, "metric": "l2" if objective == "regression" else "poisson"}
    cat = ["comp_code"] if "comp_code" in cols else []
    ds = lgb.Dataset(d[cols], y, weight=w, categorical_feature=cat)
    if rounds is not None:
        return lgb.train(p, ds, rounds), rounds
    vd, vy, vw = _mk(val, scale, objective)
    b = lgb.train(p, ds, D.MAX_ROUNDS, valid_sets=[lgb.Dataset(vd[cols], vy, weight=vw, categorical_feature=cat)], callbacks=[lgb.early_stopping(D.PATIENCE, verbose=False)])
    return b, max(b.best_iteration, 10)


def mean_pred(b, n, d, cols, scale):
    r = b.predict(d[cols], num_iteration=n)
    return r * D.target_scale(d, scale) if scale else r


def run_gbm_mean(feat, name, cols, objective="regression", scale=None, cfg_extra=None, years=YEARS5):
    """D4 (iv): mean objective (L2 / Poisson) for remaining runs. Quantiles = mean + scale * residual quantiles by state bucket, measured on the inner-fold
    validation (all competitions, season Y-1). Chase probabilities are copied from the g2oe frames (this variant changes only the first-innings score)."""
    tuned = FF.tuned_cfg()
    S = []
    for Y in years:
        t = tuned[str(Y)]
        tr, w, itr, iw, val, test = fold_sets(feat, Y)
        cfg = {**D.CONFIGS[t["score_cfg"]], "num_threads": THREADS, **(cfg_extra or {})}
        bi, n = fit_mean(itr, cols, cfg, val, scale, objective)
        bm, _ = fit_mean(tr, cols, cfg, None, scale, objective, rounds=n)
        v1 = usable(val)
        v1 = v1[v1.innings == 1]
        mu_v = mean_pred(bi, n, v1, cols, scale)
        sc_v = np.maximum(mu_v, 5.0) if not scale else D.target_scale(v1, scale)
        rq = resid_quantiles(((v1.final_total - v1.runs).to_numpy(float) - mu_v) / sc_v, bucket(v1))
        t1 = test[test.innings == 1]
        mu = mean_pred(bm, n, t1, cols, scale)
        sc = np.maximum(mu, 5.0) if not scale else D.target_scale(t1, scale)
        S.append(pack_s(t1, apply_resid(mu, sc, bucket(t1), rq) + t1.runs.to_numpy(float)[:, None], name, Y))
        print(f"  {name} fold {Y}: rounds {n}", flush=True)
    return _n(pd.concat(S)), B.cached_frames("g2oe")[1].assign(model=name)


# ---------- relative state features (shared by k-NN, GAM, MLP) ----------
def rel_feats(d, chase):
    """Scale-free state: everything relative to the scoring level (lvl_season = expected first-innings total)."""
    lvl = d.lvl_season.to_numpy(float)
    f = {"bl": d.balls_left.to_numpy(float) / 120, "wk": d.wickets.to_numpy(float), "runs": d.runs.to_numpy(float) / lvl,
         "w12": d.wk_l12.to_numpy(float), "r12": d.runs_l12.to_numpy(float) / (lvl / 10), "w30": d.wk_l30.to_numpy(float), "r30": d.runs_l30.to_numpy(float) / (lvl / 4)}
    if chase:
        f["rrr"] = np.nan_to_num(d.rrr.to_numpy(float), nan=0.0) / (lvl / 20)
        f["need"] = d.runs_needed.to_numpy(float) / lvl
    return pd.DataFrame(f, index=d.index)


def train_oe(d):
    return d[(d.balls_bowled % 6 == 0) & (d.balls_bowled >= 6)]


# ---------- M1: k-NN analogues ----------
KNN_W = {"bl": 2.0, "wk": 1.5, "runs": 1.0, "w12": 1.0, "r12": 0.6, "w30": 0.3, "r30": 0.3, "rrr": 2.0, "need": 1.0}
KS = (50, 100, 200, 400)


def _nn(Xtr, Xq, kmax):
    from sklearn.neighbors import NearestNeighbors

    nn = NearestNeighbors(n_neighbors=kmax, algorithm="kd_tree", n_jobs=2).fit(Xtr)
    return nn.kneighbors(Xq, return_distance=False)


def _std(tr, chase):
    f = rel_feats(tr, chase)
    mu, sd = f.mean(), f.std() + 1e-9
    w = np.array([KNN_W[c] for c in f.columns])
    return mu, sd, w


def knn_score(trn, qry, k, chase=False, kmax=None):
    """k-NN quantiles of the level-relative remaining ratio y/s for query rows; returns neighbour index matrix, ratio array."""
    mu, sd, w = _std(trn, chase)
    Xt = ((rel_feats(trn, chase) - mu) / sd).to_numpy() * w
    Xq = ((rel_feats(qry, chase) - mu) / sd).to_numpy() * w
    return _nn(Xt, Xq, kmax or max(KS))


def knn_quantiles(nb, scale, qs=(0.1, 0.5, 0.9)):
    """Quantiles (q10, q50, q90, ordered by construction) of the neighbours' remaining-ratio matrix nb (n_query, k), times each query's scale."""
    return np.quantile(nb, qs, axis=1).T * np.asarray(scale, float)[:, None]


def run_knn(feat, name="m1", years=YEARS5):
    """Analog model: first innings -> quantiles of the k nearest historical states' (remaining / s) times the query's s; chase -> mean win of k neighbours.
    k chosen per fold on the inner fold (train < Y-1 -> validate on season Y-1, 4000 random rows) by pinball (score) / log loss (win)."""
    S, W = [], []
    rng = np.random.default_rng(0)
    for Y in years:
        tr, w, itr, iw, val, test = fold_sets(feat, Y)
        out = {}
        for chase in (False, True):
            tt, ii = train_oe(usable(tr[tr.innings == (2 if chase else 1)])), train_oe(usable(itr[itr.innings == (2 if chase else 1)]))
            if chase:
                tt, ii = tt[tt.chase_won.notna() & (tt.runs_needed > 0)], ii[ii.chase_won.notna() & (ii.runs_needed > 0)]
            vv = train_oe(usable(val[val.innings == (2 if chase else 1)]))
            if chase:
                vv = vv[vv.chase_won.notna() & (vv.runs_needed > 0)]
            vv = vv.iloc[rng.permutation(len(vv))[:4000]]
            ytr = lambda d: ((d.final_total - d.runs).to_numpy(float) / D.target_scale(d, "lvl_season")) if not chase else d.chase_won.to_numpy(float)  # noqa: E731
            idx = knn_score(ii, vv, None, chase)
            yi = ytr(ii)
            best = None
            for k in KS:
                nb = yi[idx[:, :k]]
                if chase:
                    p = np.clip(nb.mean(1), 0.01, 0.99)
                    loss = -np.mean(vv.chase_won * np.log(p) + (1 - vv.chase_won) * np.log(1 - p))
                else:
                    sv = D.target_scale(vv, "lvl_season")
                    q = knn_quantiles(nb, sv)
                    y = (vv.final_total - vv.runs).to_numpy(float)
                    loss = np.mean([np.mean(np.maximum(a * (y - q[:, j]), (a - 1) * (y - q[:, j]))) for j, a in enumerate((0.1, 0.5, 0.9))])
                if best is None or loss < best[0]:
                    best = (loss, k)
            k = best[1]
            te = test[test.innings == (2 if chase else 1)]
            te = D.win_rows(te) if chase else te
            idx = knn_score(tt, te, None, chase)
            yt = ytr(tt)
            nb = yt[idx[:, :k]]
            if chase:
                W.append(pack_w(te, (nb.sum(1) + 0.5) / (k + 1), name, Y))
            else:
                q = knn_quantiles(nb, D.target_scale(te, "lvl_season")) + te.runs.to_numpy(float)[:, None]
                S.append(pack_s(te, q, name, Y))
            out["chase" if chase else "score"] = k
        print(f"  {name} fold {Y}: k {out}", flush=True)
    return _n(pd.concat(S)), _n(pd.concat(W))


# ---------- M2: spline GAM ----------
def spline_design(f, chase, fit=None):
    """Spline main effects (balls left, wickets, level-relative runs, recent windows, [rrr, need]) + balls_left x wickets (and x rrr) tensor terms."""
    from sklearn.preprocessing import SplineTransformer

    cols = ["bl", "wk", "runs", "w12", "r12", "r30"] + (["rrr", "need"] if chase else [])
    if fit is None:
        fit = {c: SplineTransformer(n_knots=6 if c != "wk" else 5, degree=3, knots="quantile", extrapolation="constant").fit(f[[c]]) for c in cols}
    base = {c: fit[c].transform(f[[c]]) for c in cols}
    mats = [base[c] for c in cols]
    mats.append((base["bl"][:, :, None] * base["wk"][:, None, :]).reshape(len(f), -1))
    if chase:
        mats.append((base["rrr"][:, :, None] * base["bl"][:, None, :]).reshape(len(f), -1))
        mats.append((base["rrr"][:, :, None] * base["wk"][:, None, :]).reshape(len(f), -1))
    return np.hstack(mats), fit


def run_gam(feat, name="m2", years=YEARS5, alphas=(1.0, 10.0, 100.0, 1000.0)):
    """Ridge on spline features for remaining/s (first innings, weights s^2 = squared-run loss); logistic on spline features for the chase.
    The ridge penalty / logistic C is chosen on the inner fold; quantiles = residual quantiles by bucket on the inner validation."""
    from sklearn.linear_model import LogisticRegression, Ridge

    S, W = [], []
    for Y in years:
        tr, w, itr, iw, val, test = fold_sets(feat, Y)
        info = {}
        for chase in (False, True):
            inn = 2 if chase else 1
            def prep(d):
                d = train_oe(usable(d[d.innings == inn]))
                return d[d.chase_won.notna() & (d.runs_needed > 0)] if chase else d
            tt, ii, vv = prep(tr), prep(itr), prep(val)
            te = D.win_rows(test) if chase else test[test.innings == 1]
            if chase:
                y = lambda d: d.chase_won.to_numpy(float)  # noqa: E731
            else:
                s_ = lambda d: D.target_scale(d, "lvl_season")  # noqa: E731
                y = lambda d: (d.final_total - d.runs).to_numpy(float) / s_(d)  # noqa: E731
            Xi, fit = spline_design(rel_feats(ii, chase), chase)
            Xv, _ = spline_design(rel_feats(vv, chase), chase, fit)
            best = None
            for a in alphas:
                if chase:
                    m = LogisticRegression(C=1.0 / a, max_iter=300).fit(Xi, y(ii))
                    p = np.clip(m.predict_proba(Xv)[:, 1], 1e-4, 1 - 1e-4)
                    loss = -np.mean(y(vv) * np.log(p) + (1 - y(vv)) * np.log(1 - p))
                else:
                    m = Ridge(alpha=a).fit(Xi, y(ii), sample_weight=s_(ii) ** 2)
                    loss = np.average((y(vv) - m.predict(Xv)) ** 2, weights=s_(vv) ** 2)
                if best is None or loss < best[0]:
                    best = (loss, a)
            a = best[1]
            Xt, fit = spline_design(rel_feats(tt, chase), chase)
            Xe, _ = spline_design(rel_feats(te, chase), chase, fit)
            if chase:
                m = LogisticRegression(C=1.0 / a, max_iter=300).fit(Xt, y(tt))
                W.append(pack_w(te, m.predict_proba(Xe)[:, 1], name, Y))
            else:
                mi = Ridge(alpha=a).fit(Xi, y(ii), sample_weight=s_(ii) ** 2)
                bk = bucket(vv)
                rq = resid_quantiles(y(vv) - mi.predict(Xv), bk)  # in ratio units; weights bigger s later via scale
                # residual scale: ratio residuals times s (runs)
                rqs = resid_quantiles((y(vv) - mi.predict(Xv)) * s_(vv), bk)
                m = Ridge(alpha=a).fit(Xt, y(tt), sample_weight=s_(tt) ** 2)
                mu = m.predict(Xe) * s_(te)
                S.append(pack_s(te, apply_resid(mu, np.ones(len(te)), bucket(te), rqs) + te.runs.to_numpy(float)[:, None], name, Y))
            info["chase" if chase else "score"] = a
        print(f"  {name} fold {Y}: alpha {info}", flush=True)
    return _n(pd.concat(S)), _n(pd.concat(W))


# ---------- M3: small MLP ----------
def run_mlp(feat, name="m3", years=YEARS5, seed=0):
    """sklearn MLP (64-32, early stopping, L2 1e-3) on standardised relative state features. First innings target = remaining / level (loss in runs units);
    chase = win classifier. Quantiles = residual quantiles by bucket on the inner validation (inner model on train < Y-1)."""
    from sklearn.neural_network import MLPClassifier, MLPRegressor
    from sklearn.preprocessing import StandardScaler

    S, W = [], []
    for Y in years:
        tr, w, itr, iw, val, test = fold_sets(feat, Y)
        for chase in (False, True):
            inn = 2 if chase else 1

            def prep(d):
                d = train_oe(usable(d[d.innings == inn]))
                return d[d.chase_won.notna() & (d.runs_needed > 0)] if chase else d
            tt, ii, vv = prep(tr), prep(itr), prep(val)
            te = D.win_rows(test) if chase else test[test.innings == 1]

            def fit(d):
                f = rel_feats(d, chase)
                sc = StandardScaler().fit(f)
                if chase:
                    m = MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3, early_stopping=True, n_iter_no_change=8, max_iter=200, random_state=seed)
                    m.fit(sc.transform(f), d.chase_won.to_numpy(int))
                else:
                    m = MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3, early_stopping=True, n_iter_no_change=8, max_iter=200, random_state=seed)
                    m.fit(sc.transform(f), (d.final_total - d.runs).to_numpy(float) / d.lvl_season.to_numpy(float))
                return sc, m, chase
            def pred(mdl, d):
                sc, m, ch = mdl
                x = sc.transform(rel_feats(d, ch))
                return m.predict_proba(x)[:, 1] if ch else m.predict(x) * d.lvl_season.to_numpy(float)
            if chase:
                W.append(pack_w(te, pred(fit(tt), te), name, Y))
            else:
                mi = fit(ii)
                mu_v = pred(mi, vv)
                rq = resid_quantiles((vv.final_total - vv.runs).to_numpy(float) - mu_v, bucket(vv))
                mu = pred(fit(tt), te)
                S.append(pack_s(te, apply_resid(mu, np.ones(len(te)), bucket(te), rq) + te.runs.to_numpy(float)[:, None], name, Y))
        print(f"  {name} fold {Y} done", flush=True)
    return _n(pd.concat(S)), _n(pd.concat(W))


# ---------- M4: post-hoc stretch of G2 on out-of-fold predictions of the training seasons (nested) ----------
def oof_g2(feat, years=range(2016, 2026)):
    """G2 recipe predictions for earlier seasons (all competitions, over-end states), each season from a model trained on earlier seasons only.
    Config: the 2022 tuned one; early stopping on season s-1 (all competitions)."""
    tuned = FF.tuned_cfg()
    S, W = [], []
    t = tuned["2022"]
    keep = D.META + ["wickets", "balls_left", "runs", "lvl_season", "wk_l12", "runs_l12", "wk_l30"]
    for Y in years:
        tr, w, itr, iw, val, _ = fold_sets(feat, Y)
        test = oe(usable(feat[feat.season_year == Y]))
        cols = B.G2_COLS
        cfg, cw = ({**D.CONFIGS[t[k]], "num_threads": THREADS} for k in ("score_cfg", "win_cfg"))
        inner = D.fit_score(itr, iw, cols, cfg, val=val, scale="lvl_season")
        sm = D.fit_score(tr, w, cols, cfg, rounds={q: inner[q][1] for q in D.QS}, scale="lvl_season")
        wi, n = D.fit_win(itr, iw, cols, cw, val=val)
        wm, _ = D.fit_win(tr, w, cols, cw, rounds=n)
        t1, t2 = test[test.innings == 1], D.win_rows(test)
        S.append(t1[keep].assign(model="oof", fold=Y, **D.predict_score(sm, t1, cols, scale="lvl_season")))
        W.append(t2[keep].assign(model="oof", fold=Y, p=wm.predict(t2[cols])))
        print(f"  oof g2 season {Y}: {len(t1)} score rows", flush=True)
    return pd.concat(S), pd.concat(W)


def run_stretch(feat, name="m4", years=YEARS5, resid_model=False):
    """For test season Y: fit actual ~ a + b*q50 (both divided by the level) and a logistic calibration logit(actual) ~ a + b*logit(p) on the OOF predictions
    of the seasons Y-4..Y-1 (all competitions, over ends 3-17), then apply them to the g2oe predictions of season Y. Nothing from season Y is used.
    resid_model=True (M4b) adds a ridge on the OOF residual with state features (wickets, balls left, wickets in the last 12 and 30 balls, recent runs)."""
    from sklearn.linear_model import Ridge

    S0, W0 = B.cached_frames("g2oe")
    po = OUT_DIR / "db_oof_S.parquet"
    if not po.exists():
        oS, oW = oof_g2(feat)
        oS.to_parquet(po)
        oW.to_parquet(OUT_DIR / "db_oof_W.parquet")
    oS, oW = pd.read_parquet(po), pd.read_parquet(OUT_DIR / "db_oof_W.parquet")
    ff = feat[(feat.balls_bowled % 6 == 0) & (feat.innings == 1)][KEY + ["wickets", "balls_left", "runs", "lvl_season", "wk_l12", "runs_l12", "wk_l30"]]
    ff = _n(ff)
    F_ = ["wickets", "balls_left", "wk_l12", "runs_l12", "wk_l30"]
    Xr = lambda d: np.column_stack([d.wickets, d.balls_left / 120, d.wk_l12, d.runs_l12 / (d.lvl_season / 10), d.wk_l30, d.wickets * d.balls_left / 120])  # noqa: E731
    S, W = [], []
    for Y in years:
        o = oS[oS.season_year.between(Y - 4, Y - 1) & oS.balls_bowled.between(18, 102)]
        ow = oW[oW.season_year.between(Y - 4, Y - 1) & oW.balls_bowled.between(18, 102)]
        x, y = (o.q50 / o.lvl_season).to_numpy(), (o.final_total / o.lvl_season).to_numpy()
        b = np.cov(x, y)[0, 1] / x.var(ddof=1)
        a = y.mean() - b * x.mean()
        s = S0[S0.fold == Y].merge(ff[KEY + ["lvl_season"] + F_], on=KEY)
        lv = s.lvl_season.to_numpy()
        q = np.column_stack([(a + b * s[c].to_numpy() / lv) * lv for c in ("q10", "q50", "q90")])
        if resid_model:
            r = Ridge(alpha=10.0).fit(Xr(o), ((o.final_total - o.q50) / o.lvl_season).to_numpy())
            q = q + (r.predict(Xr(s)) * lv)[:, None]
        q = np.sort(q, axis=1)
        S.append(s[D.META + ["fold"]].assign(model=name, q10=q[:, 0], q50=q[:, 1], q90=q[:, 2]))
        a2, b2 = B.logit_fit(B.logit(ow.p), ow.chase_won)
        w = W0[W0.fold == Y]
        W.append(w.assign(model=name, p=1 / (1 + np.exp(-(a2 + b2 * B.logit(w.p))))))
        print(f"  {name} fold {Y}: score a={a:.3f} b={b:.3f} (n={len(o)}), chase logit a={a2:.3f} b={b2:.3f} (n={len(ow)})", flush=True)
    return _n(pd.concat(S)), _n(pd.concat(W))


# ---------- blends of cached models (equal weights, on identical states) ----------
def avg_models(names, score_names=None, name="blend"):
    """Equal-weight average of cached frames: quantiles (sorted) for the score, probabilities for the chase. score_names lets the score and chase use different members."""
    def one(ns, kind):
        fr = [B.cached_frames(n)[0 if kind == "S" else 1] for n in ns]
        m = fr[0]
        cols = ["q10", "q50", "q90"] if kind == "S" else ["p"]
        for i, f in enumerate(fr[1:], 1):
            m = m.merge(f[KEY + cols], on=KEY, suffixes=("", f"_{i}"))
        arr = np.mean([m[[c if i == 0 else f"{c}_{i}" for c in cols]].to_numpy() for i in range(len(fr))], axis=0)
        if kind == "S":
            arr = np.sort(arr, axis=1)
        out = m[[c for c in m.columns if not any(c == f"{x}_{i}" for x in cols for i in range(1, 9))]].copy()
        out[cols] = arr
        return out.assign(model=name)
    return one(score_names or names, "S"), one(names, "W")


# ---------- runner ----------
D3_COLS = B.STATE_COLS
JOBS = {
    "g2oe": lambda f: run_gbm(f, "g2oe", B.G2_COLS),
    "d3": lambda f: run_gbm(f, "d3", D3_COLS),
    "d4a": lambda f: run_gbm(f, "d4a", B.G2_COLS, cfg_extra={"learning_rate": 0.02}, budget=(3000, 100)),  # more trees, lower learning rate
    "d4b": lambda f: run_gbm(f, "d4b", B.G2_COLS, cfg_extra={"min_child_samples": 20, "lambda_l2": 0.0, "num_leaves": 31}),  # small leaves, no L2
    "d4c": lambda f: run_gbm(f, "d4c", B.G2_COLS, scale=None),  # raw remaining runs, level only as a feature
    "d4d": lambda f: run_gbm_mean(f, "d4d", B.G2_COLS, "regression", None),  # L2 mean, raw remaining runs
    "d4e": lambda f: run_gbm_mean(f, "d4e", B.G2_COLS, "poisson", None),  # Poisson, raw remaining runs
    "d4f": lambda f: run_gbm_mean(f, "d4f", B.G2_COLS, "regression", "lvl_season"),  # L2 mean, level-relative
    "m1": lambda f: run_knn(f),
    "m2": lambda f: run_gam(f),
    "m3": lambda f: run_mlp(f),
    "b2": lambda f: avg_models(["g2oe", "m2"], name="b2"),
    "b3": lambda f: avg_models(["g2oe", "m3"], name="b3"),
    "b23": lambda f: avg_models(["g2oe", "m2", "m3"], name="b23"),
    "b23f": lambda f: avg_models(["g2oe", "m2", "m3"], ["d4f", "m2", "m3"], name="b23f"),
    "m4": lambda f: run_stretch(f, "m4"),
    "m4b": lambda f: run_stretch(f, "m4b", resid_model=True),
}


def run_jobs(names):
    feat = None if all(n.startswith("b") for n in names) else load_train(NEED)
    for nm in names:
        if (OUT_DIR / f"db_{nm}_S.parquet").exists():
            print(f"{nm}: cached", flush=True)
            continue
        t0 = time.time()
        S, W = JOBS[nm](feat)
        B.save_frames(nm, S, W)
        print(f"[{time.time() - t0:5.0f}s] {nm} done", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["report"]:
        from .drawing_board_report import report

        report(a[1:])
    else:
        run_jobs(a)
