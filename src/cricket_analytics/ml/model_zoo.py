"""Model-family benchmark ("model zoo"): XGBoost, CatBoost, RandomForest, ExtraTrees, HistGradientBoosting, GRU, blends, on the drawing-board bench.

  python -m cricket_analytics.ml.model_zoo z1 z2 z3 z4 z5 z6 | blend <name> | report

Same rolling origin as drawing_board_fit: test season Y (IPL Y; men's non-IPL Y for 2024-25), trained on seasons < Y, tuned on an INNER fold
(train < Y-1, validate on all competitions of season Y-1), never on the test season. Same over-end test states, same G2 columns, same level-relative target
(remaining / s, s = lvl_season / 120 * balls_left). Native-quantile models (XGB, CatBoost, HGB, GRU) get the G2 conformal widening; mean models (RF, ET)
get residual quantiles by state bucket measured on the inner validation (as D4f / M2). Caches: data/external/ml/db_<name>_{S,W}.parquet (+ zoo_times.json).
The locked fresh sets are not in the feature table and are never read.
"""

import json
import sys
import time

import numpy as np
import pandas as pd

from . import direct as D
from . import drawing_board as B
from . import drawing_board_fit as F
from .baselines import usable
from .dataset import OUT_DIR

THREADS = 4
CMAX = 13  # comp_code 0..12
SCOLS = [c for c in B.G2_COLS if c not in ("innings", "target", "runs_needed", "rrr", "rr_diff")]  # innings-1 columns that are not constant / all-NaN
WCOLS = [c for c in B.G2_COLS if c != "innings"]
TIMES = OUT_DIR / "zoo_times.json"
QA = (0.1, 0.5, 0.9)


# ---------- losses ----------
def pin(y, q, w):
    return float(np.mean([np.average(np.maximum(a * (y - q[:, j]), (a - 1) * (y - q[:, j])), weights=w) for j, a in enumerate(QA)]))


def ll(y, p, w=None):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(np.average(-(y * np.log(p) + (1 - y) * np.log(1 - p)), weights=w))


# ---------- families: one interface ----------
class Fam:
    """fit(kind, X, y, w, cfg, val=None, n=None) -> (model, n); predict(kind, model, X, n) -> (n,3) ratio quantiles | (n,) ratio mean | (n,) p."""
    name = "?"
    quantile = True  # native quantiles for the score (else mean + residual quantiles)

    def grid(self, kind):
        return [{}]

    def X(self, d, cols):
        return d[cols].astype("float32")


class XGB(Fam):
    name = "XGBoost"

    def grid(self, kind):
        return [{"max_depth": 4}, {"max_depth": 6}]

    def X(self, d, cols):
        x = d[cols].astype("float32")
        if "comp_code" in cols:
            x["comp_code"] = pd.Categorical(d.comp_code.to_numpy(), categories=range(CMAX))
        return x

    def fit(self, kind, X, y, w, cfg, val=None, n=None):
        import xgboost as xgb

        p = dict(tree_method="hist", eta=0.05, subsample=0.8, colsample_bytree=0.8, reg_lambda=10.0, min_child_weight=100 if kind == "score" else 20, nthread=THREADS, seed=7, **cfg)
        if kind == "score":
            p.update(objective="reg:quantileerror", quantile_alpha=np.array(QA))
        else:
            p.update(objective="binary:logistic", eval_metric="logloss")
        dt = xgb.DMatrix(X, y, weight=w, enable_categorical=True)
        if val is None:
            return xgb.train(p, dt, n), n
        Xv, yv, wv = val
        dv = xgb.DMatrix(Xv, yv, weight=wv, enable_categorical=True)
        b = xgb.train(p, dt, 1500, evals=[(dv, "v")], early_stopping_rounds=40, verbose_eval=False)
        return b, max(b.best_iteration + 1, 10)

    def predict(self, kind, m, X, n):
        import xgboost as xgb

        return m.predict(xgb.DMatrix(X, enable_categorical=True), iteration_range=(0, n))


class Cat(Fam):
    name = "CatBoost"

    def grid(self, kind):
        return [{"depth": 4}, {"depth": 6}]

    def fit(self, kind, X, y, w, cfg, val=None, n=None):
        import catboost as cb

        kw = dict(learning_rate=0.08, l2_leaf_reg=10.0, thread_count=THREADS, verbose=0, random_seed=7, **cfg)
        cat = ["comp_code"] if "comp_code" in X.columns else []
        tr = cb.Pool(X, y, weight=w, cat_features=cat)
        if kind == "score":
            Mod, kw["loss_function"] = cb.CatBoostRegressor, "MultiQuantile:alpha=0.1,0.5,0.9"
        else:
            Mod, kw["loss_function"] = cb.CatBoostClassifier, "Logloss"
        if val is None:
            return Mod(iterations=n, **kw).fit(tr), n
        Xv, yv, wv = val
        m = Mod(iterations=1500, early_stopping_rounds=50, use_best_model=True, **kw).fit(tr, eval_set=cb.Pool(Xv, yv, weight=wv, cat_features=cat))
        return m, max(m.get_best_iteration() + 1, 10)

    def X(self, d, cols):
        x = d[cols].astype("float32")
        if "comp_code" in cols:
            x["comp_code"] = d.comp_code.astype(int).to_numpy()
        return x

    def predict(self, kind, m, X, n):
        if kind == "score":
            return m.predict(X, ntree_end=n)
        return m.predict_proba(X, ntree_end=n)[:, 1]


class Forest(Fam):
    quantile = False

    def __init__(self, extra):
        self.extra, self.name = extra, "ExtraTrees" if extra else "RandomForest"

    def grid(self, kind):
        return [{"min_samples_leaf": 100}, {"min_samples_leaf": 400}] if not self.extra else [{"min_samples_leaf": 50}, {"min_samples_leaf": 200}]

    def X(self, d, cols):
        x = d[cols].astype("float32").fillna(-1.0)  # sentinel for the NaN columns (forests)
        if "comp_code" in cols:
            x = x.drop(columns="comp_code")
            for c in range(CMAX):
                x[f"comp_{c}"] = (d.comp_code.to_numpy() == c).astype("float32")
        return x

    def fit(self, kind, X, y, w, cfg, val=None, n=None):
        from sklearn import ensemble as E

        k = dict(n_estimators=120, max_features=0.5, n_jobs=THREADS, random_state=0, **cfg)
        if not self.extra:
            k.update(bootstrap=True, max_samples=0.5)  # ponytail: row subsample 0.5 per tree for speed
        if self.extra:
            Mod = E.ExtraTreesRegressor if kind == "score" else E.ExtraTreesClassifier
        else:
            Mod = E.RandomForestRegressor if kind == "score" else E.RandomForestClassifier
        m = Mod(**k).fit(X, y, sample_weight=np.asarray(w, float) / np.mean(w))  # mean-1 weights (bootstrap size scales with the weight sum)
        return m, 0

    def predict(self, kind, m, X, n):
        return m.predict(X) if kind == "score" else m.predict_proba(X)[:, 1]


class HGB(Fam):
    name = "HistGradientBoosting"

    def grid(self, kind):
        return [{"max_leaf_nodes": 15}, {"max_leaf_nodes": 31}]

    def X(self, d, cols):
        return d[cols].astype("float32")

    def _mk(self, kind, cfg, it, q=None):
        from sklearn import ensemble as E

        k = dict(learning_rate=0.08, max_iter=it, min_samples_leaf=200, l2_regularization=10.0, early_stopping=False, random_state=7, **cfg)
        if kind == "score":
            return E.HistGradientBoostingRegressor(loss="quantile", quantile=q, **k)
        return E.HistGradientBoostingClassifier(**k)

    def fit(self, kind, X, y, w, cfg, val=None, n=None):
        qs = QA if kind == "score" else (None,)
        if val is None:
            return [self._mk(kind, cfg, n[i], q).fit(X, y, sample_weight=w) for i, q in enumerate(qs)], n
        Xv, yv, wv = val
        ms, ns = [], []
        for q in qs:
            m = self._mk(kind, cfg, 500, q).fit(X, y, sample_weight=w)
            best, bn = 1e18, 10
            stage = m.staged_predict if kind == "score" else m.staged_predict_proba
            for i, pv in enumerate(stage(Xv), 1):
                if i % 5:
                    continue
                if kind == "score":
                    l = np.average(np.maximum(q * (yv - pv), (q - 1) * (yv - pv)), weights=wv)
                else:
                    l = ll(yv, pv[:, 1])
                if l < best:
                    best, bn = l, i
            ms.append(m)
            ns.append(bn)
        return ms, ns

    def predict(self, kind, ms, X, n):
        out = []
        for m, k in zip(ms, n):
            if getattr(m, "max_iter", 0) == k:
                pv = m.predict(X) if kind == "score" else m.predict_proba(X)[:, 1]
            else:  # inner model: take the stage at its best iteration
                for i, p in enumerate(m.staged_predict(X) if kind == "score" else m.staged_predict_proba(X), 1):
                    if i == k:
                        pv = p if kind == "score" else p[:, 1]
                        break
            out.append(pv)
        return np.column_stack(out) if kind == "score" else out[0]


# ---------- generic fold runner ----------
def _score_xy(d, cols, fam):
    d, y = D.score_rows(d, 1)
    s = D.target_scale(d, "lvl_season")
    return d, fam.X(d, cols), y / s, s


def _win_xy(d, cols, fam):
    d = D.win_rows(d)
    return d, fam.X(d, cols), d.chase_won.to_numpy(float)


def tune(fam, kind, tr, itr, val, cols):
    """Small grid on the inner fold. Returns (cfg, n) with the lowest validation loss."""
    if kind == "score":
        di, Xi, yi, si = _score_xy(itr, cols, fam)
        dv, Xv, yv, sv = _score_xy(val, cols, fam)
        wi, wv = (si if fam.quantile else si ** 2), (sv if fam.quantile else sv ** 2)
    else:
        di, Xi, yi = _win_xy(itr, cols, fam)
        dv, Xv, yv = _win_xy(val, cols, fam)
        wi = wv = np.ones(len(yi))
        wv = np.ones(len(yv))
    best = None
    for cfg in fam.grid(kind):
        m, n = fam.fit(kind, Xi, yi, wi, cfg, val=(Xv, yv, wv))
        pv = fam.predict(kind, m, Xv, n)
        if kind == "score":
            l = pin(yv, pv, wv) if fam.quantile else float(np.average((yv - pv) ** 2, weights=wv))
        else:
            l = ll(yv, pv)
        if best is None or l < best[0]:
            best = (l, cfg, n, m, pv)
    return best[1:], (dv, (sv if kind == "score" else None), yv)


def run_family(feat, name, fam, years=F.YEARS5):
    """Returns (S, W) frames; per-fold fit/predict timings are appended to zoo_times.json."""
    S, W = [], []
    t_fit = t_pred = n_pred = 0.0
    for Y in years:
        tr, w, itr, iw, val, test = F.fold_sets(feat, Y)
        t0 = time.time()
        # ---- first innings
        (cfg, n, mi, pv), (dv, sv, yv) = tune(fam, "score", tr, itr, val, SCOLS)
        dt, Xt, yt, st = _score_xy(tr, SCOLS, fam)
        mf, _ = fam.fit("score", Xt, yt, st if fam.quantile else st ** 2, cfg, n=n)
        t1 = test[test.innings == 1]
        t1 = D.score_rows(t1, 1)[0]
        t_fit += time.time() - t0
        t0 = time.time()
        Xte = fam.X(t1, SCOLS)
        raw = fam.predict("score", mf, Xte, n)
        t_pred += time.time() - t0
        s1 = D.target_scale(t1, "lvl_season")
        run1 = t1.runs.to_numpy(float)
        if fam.quantile:
            qv = np.sort(pv, axis=1) * sv[:, None] + dv.runs.to_numpy(float)[:, None]
            dl = D.conformal_delta(dv.final_total, qv[:, 0], qv[:, 2], D.over_bucket(dv.balls_bowled))
            q = np.sort(raw, axis=1) * s1[:, None] + run1[:, None]
            lo, hi = D.conformal_apply(q[:, 0], q[:, 1], q[:, 2], D.over_bucket(t1.balls_bowled), dl)
            q = np.column_stack([lo, q[:, 1], hi])
        else:
            rq = F.resid_quantiles(yv - pv, F.bucket(dv))
            q = F.apply_resid(raw * s1, s1, F.bucket(t1), rq) + run1[:, None]
        S.append(F.pack_s(t1, q, name, Y))
        # ---- chase
        t0 = time.time()
        (cfgw, nw, _, _), _ = tune(fam, "win", tr, itr, val, WCOLS)
        dw, Xw, yw = _win_xy(tr, WCOLS, fam)
        mw, _ = fam.fit("win", Xw, yw, np.ones(len(yw)), cfgw, n=nw)
        t2 = D.win_rows(test)
        t_fit += time.time() - t0
        t0 = time.time()
        p = fam.predict("win", mw, fam.X(t2, WCOLS), nw)
        t_pred += time.time() - t0
        n_pred += len(t1) + len(t2)
        W.append(F.pack_w(t2, p, name, Y))
        print(f"  {name} fold {Y}: score cfg {cfg} n {n}; win cfg {cfgw} n {nw}; fit {t_fit:.0f}s cum", flush=True)
    log_times(name, t_fit / len(years), t_pred / n_pred * 1e6)
    return F._n(pd.concat(S)), F._n(pd.concat(W))


def log_times(name, fit_s, pred_us):
    t = json.loads(TIMES.read_text()) if TIMES.exists() else {}
    t[name] = {"train_s_per_fold": round(fit_s, 1), "predict_us_per_state": round(pred_us, 1)}
    TIMES.write_text(json.dumps(t, indent=1))


# ---------- GRU on the ball-by-ball sequence ----------
GRU_HIDDEN, GRU_BATCH, GRU_EPOCHS, GRU_PATIENCE = 48, 128, 30, 4
MAXT = 150  # deliveries kept per innings (T20: 120 legal + a few extras)


class Seqs:
    """Padded per-delivery feature tensors for every innings of the feature table + the map (innings, balls_bowled) -> delivery index."""

    def __init__(self, feat):
        import torch  # noqa: F401

        inn = feat.groupby(["match_id", "innings"]).agg(lvl=("lvl_season", "first"), tgt=("target", "first"), comp=("comp_code", "first")).reset_index()
        inn["match_id"] = inn.match_id.astype(str)
        b = pd.read_parquet(OUT_DIR / "balls.parquet", columns=["match_id", "innings", "ball_seq", "runs_total", "wides", "noballs", "wicket_type", "player_out"])
        b = b[b.innings <= 2].merge(inn[["match_id", "innings"]], on=["match_id", "innings"]).sort_values(["match_id", "innings", "ball_seq"])
        inn = inn.merge(b[["match_id", "innings"]].drop_duplicates(), on=["match_id", "innings"]).reset_index(drop=True)
        inn["i"] = np.arange(len(inn))
        b = b.merge(inn[["match_id", "innings", "i", "lvl"]], on=["match_id", "innings"])
        b["legal"] = ((b.wides == 0) & (b.noballs == 0)).astype(int)
        b["wk"] = (b.player_out.notna() & ~b.wicket_type.fillna("").isin(["retired hurt", "retired not out"])).astype(int)
        g = b.groupby("i")
        b["t"] = g.cumcount()
        b["cl"], b["cw"], b["cr"] = g.legal.cumsum(), g.wk.cumsum(), g.runs_total.cumsum()
        b = b[b.t < MAXT]
        n = len(inn)
        X = np.zeros((n, MAXT, 7), np.float32)
        X[b.i, b.t] = np.column_stack([b.runs_total / 6.0, b.wk, 1 - b.legal, b.legal, b.cl / 120.0, b.cw / 10.0, b.cr / b.lvl])
        pos = -np.ones((n, 122), np.int32)  # state after k legal balls = the delivery on which the k-th legal ball is bowled
        lg = b[b.legal == 1]
        pos[lg.i, lg.cl] = lg.t
        stat = np.zeros((n, 2 + CMAX), np.float32)
        stat[:, 0] = inn.lvl / 150.0
        stat[:, 1] = (inn.tgt.fillna(0) / inn.lvl).to_numpy()
        stat[np.arange(n), 2 + inn.comp.astype(int).clip(0, CMAX - 1).to_numpy()] = 1
        self.X, self.pos, self.stat, self.inn = X, pos, stat, inn
        self.row = {(m, k): i for m, k, i in zip(inn.match_id, inn.innings, inn.i)}

    def targets(self, d, kind):
        """Dense per-delivery targets/mask for state rows d (score: ratio remaining/s, weight s; win: chase_won). Rows without a sequence are dropped."""
        import torch

        i = d.match_id.astype(str).map(lambda m: None).to_numpy()  # placeholder to keep dtype object
        i = np.array([self.row.get((m, k), -1) for m, k in zip(d.match_id.astype(str), d.innings)])
        b = d.balls_bowled.to_numpy().astype(int)
        t = np.where(i >= 0, self.pos[np.maximum(i, 0), np.minimum(b, 121)], -1)
        ok = (i >= 0) & (t >= 0)
        i, t, d = i[ok], t[ok], d[ok]
        n = len(self.inn)
        Y, Wt = np.zeros((n, MAXT), np.float32), np.zeros((n, MAXT), np.float32)
        if kind == "score":
            s = D.target_scale(d, "lvl_season")
            Y[i, t], Wt[i, t] = (d.final_total - d.runs).to_numpy() / s, s
        else:
            Y[i, t], Wt[i, t] = d.chase_won.to_numpy(float), 1.0
        return torch.from_numpy(Y), torch.from_numpy(Wt), (i, t, d)


def _net(kind):
    import torch
    from torch import nn

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = nn.GRU(7 + 2 + CMAX, GRU_HIDDEN, batch_first=True)
            self.head = nn.Sequential(nn.Linear(GRU_HIDDEN + 2 + CMAX, 32), nn.ReLU(), nn.Linear(32, 3 if kind == "score" else 1))

        def forward(self, x, stat):
            s = stat[:, None, :].expand(-1, x.shape[1], -1)
            h, _ = self.gru(torch.cat([x, s], -1))
            o = self.head(torch.cat([h, s], -1))
            if kind == "win":
                return o[..., 0]
            a = o[..., :1]
            return torch.cat([a, a + nn.functional.softplus(o[..., 1:2]), a + nn.functional.softplus(o[..., 1:2]) + nn.functional.softplus(o[..., 2:3])], -1)  # ordered quantiles

    return Net()


def _loss(kind, out, Y, Wt):
    import torch

    if kind == "win":
        l = torch.nn.functional.binary_cross_entropy_with_logits(out, Y, reduction="none")
    else:
        e = Y[..., None] - out
        a = torch.tensor(QA)
        l = torch.maximum(a * e, (a - 1) * e).mean(-1)
    return (l * Wt).sum() / Wt.sum().clamp(min=1.0)


def gru_fit(seq, kind, trn, val, epochs=None, seed=0, max_inn=None):
    """trn / val = (Y, Wt) dense targets; returns (net, best_epochs, val loss history). epochs given -> fixed epochs, no validation."""
    import torch

    torch.manual_seed(seed)
    torch.set_num_threads(THREADS)
    net = _net(kind)
    opt = torch.optim.Adam(net.parameters(), lr=3e-3)
    X, S = torch.from_numpy(seq.X), torch.from_numpy(seq.stat)
    idx = np.where(trn[1].sum(1).numpy() > 0)[0]
    if max_inn and len(idx) > max_inn:
        idx = np.random.default_rng(seed).choice(idx, max_inn, replace=False)
    vidx = np.where(val[1].sum(1).numpy() > 0)[0] if val is not None else None
    rng = np.random.default_rng(seed)
    best, bn, hist, state = 1e18, 0, [], None
    for ep in range(1, (epochs or GRU_EPOCHS) + 1):
        net.train()
        for b in np.array_split(rng.permutation(idx), max(1, len(idx) // GRU_BATCH)):
            opt.zero_grad()
            _loss(kind, net(X[b], S[b]), trn[0][b], trn[1][b]).backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        if val is not None and epochs is None:
            net.eval()
            with torch.no_grad():
                l = float(sum(_loss(kind, net(X[c], S[c]), val[0][c], val[1][c]) * val[1][c].sum() for c in np.array_split(vidx, 8)) / val[1][vidx].sum())
            hist.append(l)
            if l < best:
                best, bn, state = l, ep, {k: v.clone() for k, v in net.state_dict().items()}
            elif ep - bn >= GRU_PATIENCE:
                break
    if state is not None:
        net.load_state_dict(state)
    return net, (bn if epochs is None else epochs), hist


def gru_predict(seq, kind, net, rows):
    """rows = (i, t, d) from Seqs.targets -> predictions (n,3) ratio quantiles | (n,) p for those state rows."""
    import torch

    net.eval()
    X, S = torch.from_numpy(seq.X), torch.from_numpy(seq.stat)
    i, t, _ = rows
    out = np.zeros((len(i),) + ((3,) if kind == "score" else ()), np.float32)
    ui = np.unique(i)
    with torch.no_grad():
        for c in np.array_split(ui, max(1, len(ui) // 256)):
            o = net(X[c], S[c]).numpy() if kind == "score" else torch.sigmoid(net(X[c], S[c])).numpy()
            m = np.isin(i, c)
            out[m] = o[np.searchsorted(c, i[m]), t[m]]
    return out


def run_gru(feat, name="z6", years=F.YEARS5, max_inn=None):
    seq = Seqs(feat)
    print(f"  GRU sequences: {len(seq.inn)} innings", flush=True)
    S, W = [], []
    fit_s = pred_s = npred = 0.0
    for Y in years:
        trf, itf = feat[feat.season_year < Y], feat[feat.season_year < Y - 1]
        val = feat[(feat.season_year == Y - 1) & (feat.balls_bowled % 2 == 0)]
        test = F.oe(__import__("cricket_analytics.ml.flaw_fit", fromlist=["x"]).test_rows(feat, Y))
        t0 = time.time()
        # first innings
        d_tr, d_it, d_va = (D.score_rows(x, 1)[0] for x in (trf, itf, val))
        (Yt, Wt, _), (Yi, Wi, _), (Yv, Wv, rv) = (seq.targets(x, "score") for x in (d_tr, d_it, d_va))
        net_i, n_ep, hist = gru_fit(seq, "score", (Yi, Wi), (Yv, Wv), max_inn=max_inn)
        pv = gru_predict(seq, "score", net_i, rv)
        dv = rv[2]
        sv = D.target_scale(dv, "lvl_season")
        qv = np.sort(pv, axis=1) * sv[:, None] + dv.runs.to_numpy(float)[:, None]
        dl = D.conformal_delta(dv.final_total, qv[:, 0], qv[:, 2], D.over_bucket(dv.balls_bowled))
        net_f, _, _ = gru_fit(seq, "score", (Yt, Wt), None, epochs=n_ep, max_inn=max_inn)
        t1 = D.score_rows(test[test.innings == 1], 1)[0]
        _, _, rt = seq.targets(t1, "score")
        t_a = time.time()
        raw = gru_predict(seq, "score", net_f, rt)
        pred_s += time.time() - t_a
        t1 = rt[2]
        s1 = D.target_scale(t1, "lvl_season")
        q = np.sort(raw, axis=1) * s1[:, None] + t1.runs.to_numpy(float)[:, None]
        lo, hi = D.conformal_apply(q[:, 0], q[:, 1], q[:, 2], D.over_bucket(t1.balls_bowled), dl)
        S.append(F.pack_s(t1, np.column_stack([lo, q[:, 1], hi]), name, Y))
        # chase
        d_tr, d_it, d_va = (D.win_rows(x) for x in (trf, itf, val))
        (Yt, Wt, _), (Yi, Wi, _), (Yv, Wv, _) = (seq.targets(x, "win") for x in (d_tr, d_it, d_va))
        net_i, n_epw, _ = gru_fit(seq, "win", (Yi, Wi), (Yv, Wv), max_inn=max_inn)
        net_f, _, _ = gru_fit(seq, "win", (Yt, Wt), None, epochs=n_epw, max_inn=max_inn)
        t2 = D.win_rows(test)
        _, _, rt2 = seq.targets(t2, "win")
        t_a = time.time()
        p = gru_predict(seq, "win", net_f, rt2)
        pred_s += time.time() - t_a
        npred += len(t1) + len(rt2[2])
        W.append(F.pack_w(rt2[2], p, name, Y))
        fit_s += time.time() - t0 - 0
        print(f"  {name} fold {Y}: epochs score {n_ep} win {n_epw}; {len(t1)} test score rows ({len(D.score_rows(test[test.innings == 1], 1)[0])} expected); {fit_s:.0f}s cum", flush=True)
    log_times(name, fit_s / len(years), pred_s / npred * 1e6)
    return F._n(pd.concat(S)), F._n(pd.concat(W))


# ---------- runner ----------
def _timed_lgbm(feat):
    """G2 (LightGBM) re-timed on one fold, for the time column only (nothing saved)."""
    Y = 2025
    t0 = time.time()
    F.run_gbm(feat, "tmp", B.G2_COLS, years=(Y,))
    log_times("g2oe", time.time() - t0, 0.0)


JOBS = {
    "z1": lambda f: run_family(f, "z1", XGB()),
    "z2": lambda f: run_family(f, "z2", Cat()),
    "z3": lambda f: run_family(f, "z3", Forest(False)),
    "z4": lambda f: run_family(f, "z4", Forest(True)),
    "z5": lambda f: run_family(f, "z5", HGB()),
    "z6": lambda f: run_gru(f, "z6"),
}


def run_jobs(names):
    feat = F.load_train(F.NEED)
    for nm in names:
        if nm == "time_g2":
            _timed_lgbm(feat)
            continue
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
        from .model_zoo_report import report

        report(a[1:])
    elif a[:1] == ["blend"]:
        for nm, ms in (("zb_g2", [a[1], "g2oe"]), ("zb_b2", [a[1], "b2"]), ("zb_3", [a[1], "g2oe", "m2"])):
            B.save_frames(nm, *F.avg_models(ms, name=nm))
    else:
        run_jobs(a)
