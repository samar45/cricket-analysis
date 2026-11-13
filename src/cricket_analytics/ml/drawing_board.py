"""Drawing board: is the shock under-reaction (collapses, steep chases, extreme wickets states) generic SHRINKAGE or hidden information?

  python -m cricket_analytics.ml.drawing_board d1     # regression-slope / calibration-slope test of every model's out-of-sample predictions
  python -m cricket_analytics.ml.drawing_board d2     # empirical-truth check: pure lookup tables vs the event battery
  python -m cricket_analytics.ml.drawing_board d3 d4  # LightGBM recipe variants (minimal columns, capacity, targets, objectives)
  python -m cricket_analytics.ml.drawing_board m1 m2 m3 m4   # other model families (k-NN, spline GAM, MLP, post-hoc stretch)
  python -m cricket_analytics.ml.drawing_board report [names...]   # paired comparison + event battery for cached drawing-board models

Scopes (all out-of-sample, men's only): 'ipl' = IPL 2022-25 rolling, 'ipl26' = IPL 2026 (seen fold), 'non' = men's non-IPL 2024-25.
The locked fresh set (men's non-IPL dated >= 2026-01-01) is not in flaw_feat.parquet and is never read. States are over ends (balls_bowled % 6 == 0).
Other ml modules are used read-only. Caches: data/external/ml/db_<name>_{S,W}.parquet.
"""

import sys
import time

import numpy as np
import pandas as pd

from . import direct as D
from . import evaluate as ev
from . import flaw_fit as FF
from . import flaw_tests as T
from .baselines import Lookup, Resource, usable
from .dataset import OUT_DIR

KEY = T.KEY
CKPT = (36, 60, 90)
SCOPES = ("ipl", "ipl26", "non")
STATE_COLS = ["balls_left", "wickets", "runs", "crr", "runs_l30", "wk_l30", "innings", "target", "runs_needed", "rrr", "rr_diff", "lvl_ew", "lvl_season", "comp_code"]
G2_COLS = FF.BASE_COLS


# ---------- data ----------
def load_feat(cols=None, even=True):
    """flaw_feat.parquet (locked fresh set already removed), men's AND women's rows, optionally only even balls (training stride)."""
    d = pd.read_parquet(FF.FEAT, columns=cols)
    if even:
        d = d[d.balls_bowled % 2 == 0]
    return d.reset_index(drop=True)


def meta_table(feat=None):
    f = feat if feat is not None else pd.read_parquet(FF.FEAT, columns=["match_id", "competition", "season_year", "gender"])
    return f[["match_id", "competition", "season_year", "gender"]].drop_duplicates("match_id").assign(match_id=lambda d: d.match_id.astype(str))


def scope_of(d, meta):
    """Add a 'scope' column (ipl / ipl26 / non / NaN) and keep men's only."""
    m = d.drop(columns=[c for c in ("competition", "season_year", "gender") if c in d.columns]).merge(meta, on="match_id", how="left")
    m = m[m.gender == "male"]
    sc = np.where((m.competition == "ipl") & m.season_year.between(2022, 2025), "ipl",
                  np.where((m.competition == "ipl") & (m.season_year == 2026), "ipl26",
                           np.where((m.competition != "ipl") & m.season_year.between(2024, 2025), "non", "")))
    return m.assign(scope=sc)[sc != ""]


def oe(d):
    """Over-end states only (balls_bowled % 6 == 0, 6..114)."""
    return d[(d.balls_bowled % 6 == 0) & d.balls_bowled.between(6, 114)]


def cached_frames(name):
    return _n(pd.read_parquet(OUT_DIR / f"db_{name}_S.parquet")), _n(pd.read_parquet(OUT_DIR / f"db_{name}_W.parquet"))


def _n(d):
    return T._norm(d)


def save_frames(name, S, W):
    S.to_parquet(OUT_DIR / f"db_{name}_S.parquet")
    W.to_parquet(OUT_DIR / f"db_{name}_W.parquet")


# ---------- slope tests ----------
def ols_slope(x, y, w=None):
    """OLS slope of y on x (weights w). Slope > 1: predictions are compressed toward the mean (under-reacting)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    w = np.ones(len(x)) if w is None else np.asarray(w, float)
    mx, my = (w * x).sum() / w.sum(), (w * y).sum() / w.sum()
    return float((w * (x - mx) * (y - my)).sum() / (w * (x - mx) ** 2).sum())


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def logit_fit(z, y, w=None, iters=25):
    """Weighted logistic regression y ~ a + b*z by Newton steps. Returns (a, b); b > 1: probabilities too timid (under-confident)."""
    z, y = np.asarray(z, float), np.asarray(y, float)
    w = np.ones(len(z)) if w is None else np.asarray(w, float)
    X = np.column_stack([np.ones(len(z)), z])
    beta = np.array([0.0, 1.0])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ beta))
        g = X.T @ (w * (y - p))
        H = (X * (w * p * (1 - p))[:, None]).T @ X + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        beta = beta + step
        if np.abs(step).max() < 1e-8:
            break
    return float(beta[0]), float(beta[1])


def _counts(match_ids, B, seed=0):
    codes, uniq = pd.factorize(pd.Series(match_ids))
    c = np.random.default_rng(seed).multinomial(len(uniq), np.ones(len(uniq)) / len(uniq), size=B).astype(float)
    return c[:, codes]


def slope_ci(x, y, mid, kind, B=500, seed=0):
    """(slope, lo5, hi5) bootstrapped over matches. kind 'score': OLS of actual on predicted; 'win': logistic calibration slope on logit(p)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    W = _counts(mid, B, seed)
    if kind == "score":
        s0 = ols_slope(x, y)
        sw = W.sum(1)
        mx, my = W @ x / sw, W @ y / sw
        sxy, sxx = W @ (x * y) - sw * mx * my, W @ (x * x) - sw * mx ** 2
        b = sxy / sxx
    else:
        z = logit(x)
        s0 = logit_fit(z, y)[1]
        b = np.array([logit_fit(z, y, w)[1] for w in W])
    return s0, float(np.percentile(b, 5)), float(np.percentile(b, 95))


def slope_table(frames, B=500, ckpts=CKPT):
    """frames: name -> (S, W) with a 'scope' column. One row per model x scope x kind x checkpoint (+ 'all' = pooled checkpoints)."""
    rows = []
    for name, (S, W) in frames.items():
        for sc in SCOPES:
            for kind, P, xc, yc in (("score", S[S.innings == 1], "q50", "final_total"), ("win", W, "p", "chase_won")):
                P = P[P.scope == sc]
                for ck in list(ckpts) + ["all"]:
                    d = P if ck == "all" else P[P.balls_bowled == ck]
                    d = d.dropna(subset=[xc, yc])
                    if ck == "all":
                        d = d[d.balls_bowled.isin(ckpts)]
                    if len(d) < 30:
                        continue
                    s, lo, hi = slope_ci(d[xc], d[yc], d.match_id, kind, B)
                    rows.append({"model": name, "scope": sc, "kind": kind, "ckpt": ck if ck == "all" else ck // 6, "n": len(d), "slope": s, "lo": lo, "hi": hi})
    return pd.DataFrame(rows)


def decile_table(frames, scope="ipl", ckpts=CKPT, q=10):
    """By prediction decile (pooled checkpoints): mean predicted vs mean actual (innings 1 final total; chase win rate)."""
    rows = []
    for name, (S, W) in frames.items():
        for kind, P, xc, yc in (("score", S[S.innings == 1], "q50", "final_total"), ("win", W, "p", "chase_won")):
            d = P[(P.scope == scope) & P.balls_bowled.isin(ckpts)].dropna(subset=[xc, yc])
            if len(d) < 50:
                continue
            g = d.groupby(pd.qcut(d[xc], q, labels=False, duplicates="drop"))
            for k, x in g:
                rows.append({"model": name, "kind": kind, "scope": scope, "decile": int(k), "n": len(x), "pred": x[xc].mean(), "actual": x[yc].mean(), "bias": x[xc].mean() - x[yc].mean()})
    return pd.DataFrame(rows)


# ---------- model frames (men's, scoped, over ends) ----------
def _keep_s(d):
    return d[KEY + ["final_total", "q10", "q50", "q90", "chase_won"]] if "chase_won" in d.columns else d[KEY + ["final_total", "q10", "q50", "q90"]]


def cache_frames(name, meta, prefix="g2_"):
    S, W = (_n(pd.read_parquet(OUT_DIR / f"{prefix}{name}_{k}.parquet")) for k in "SW")
    return oe(S), oe(W)


def baseline_frames(feat, years=(2022, 2023, 2024, 2025)):
    """Lookup and Resource tables fit on seasons < Y (IPL pool for IPL tests, all-competition pool for non-IPL), tested on over-end states."""
    out = {"lookup": [[], []], "resource": [[], []]}
    for Y in (2022, 2023, 2024, 2025, 2026):
        tr = feat[feat.season_year < Y]
        for comp_ipl in (True, False):
            if not comp_ipl and Y not in (2024, 2025):
                continue
            te = feat[(feat.season_year == Y) & ((feat.competition == "ipl") == comp_ipl)]
            te = usable(oe(te))
            if not len(te):
                continue
            t1, t2 = te[te.innings == 1], D.win_rows(te)
            pool = "ipl" if comp_ipl else "all"
            for nm, M in (("lookup", Lookup(pool)), ("resource", Resource(pool))):
                M.fit(tr)
                out[nm][0].append(t1[D.META].assign(model=nm, **M.score(t1)))
                out[nm][1].append(t2[D.META].assign(model=nm, p=M.win(t2)))
    return {k: (_n(pd.concat(v[0])), _n(pd.concat(v[1]))) for k, v in out.items()}


def simb_scoped():
    ss, sw = T.simb_frames()
    return ss, sw


def all_frames(feat):
    meta = meta_table(feat)
    fr = {}
    for nm, cn in (("G1", "g1r"), ("G2", "g2")):
        S, W = cache_frames(cn, meta)
        fr[nm] = (scope_of(S, meta), scope_of(W, meta))
    ss, sw = simb_scoped()
    fr["sim-B"] = (scope_of(ss, meta), scope_of(sw, meta))
    for k, (S, W) in baseline_frames(feat).items():
        fr[k] = (scope_of(S, meta), scope_of(W, meta))
    return fr


def d1():
    t0 = time.time()
    feat = load_feat(["match_id", "innings", "balls_bowled", "final_total", "chase_won", "season_year", "competition", "venue", "batting_team", "date",
                      "reduced", "balls_left", "runs_needed", "gender", "wickets", "runs"], even=False)
    feat = feat[feat.balls_bowled % 2 == 0]
    fr = all_frames(feat)
    print(f"frames built {time.time() - t0:.0f}s")
    tab = slope_table(fr)
    tab.to_csv(OUT_DIR / "db_d1_slopes.csv", index=False)
    dec = pd.concat([decile_table(fr, sc) for sc in SCOPES])
    dec.to_csv(OUT_DIR / "db_d1_deciles.csv", index=False)
    pd.set_option("display.width", 250)
    for kind in ("score", "win"):
        t = tab[(tab.kind == kind) & (tab.ckpt == "all")]
        print(f"\n### D1 {kind}: pooled-checkpoint slope (5-95% over matches)")
        print(t.assign(ci=lambda d: d.lo.round(2).astype(str) + ".." + d.hi.round(2).astype(str)).pivot(index="model", columns="scope", values="slope").round(3))
        print(t.assign(ci=lambda d: "[" + d.lo.round(2).astype(str) + "," + d.hi.round(2).astype(str) + "]").pivot(index="model", columns="scope", values="ci"))
        t = tab[(tab.kind == kind) & (tab.ckpt != "all")]
        print(t.pivot_table(index=["model", "ckpt"], columns="scope", values="slope").round(3))
    return tab, dec, fr


# ---------- D2: empirical truth ----------
OVERS = T.OVERS
RRR_EDGES = [6, 8, 9, 10, 11, 12, 13, 14, 16, 19]
MIN_CELL = 40


def _band(feat):
    lvl = feat.lvl_season.to_numpy(float)
    rb = np.digitize(feat.runs_l12.to_numpy(float) / np.maximum(lvl / 10.0, 1e-6), [0.7, 1.0, 1.3])  # recent scoring pace relative to the level
    return rb


def _cells(df, keys, val):
    return {k: np.sort(g.to_numpy()) for k, g in df.groupby(keys)[val]}


class Empirical:
    """Pure empirical lookup with back-off: (balls, wickets, wickets in last 12, pace band) -> (balls, wickets, wk12) -> (balls, wickets).
    fine=False uses only (balls, wickets). level=True works with remaining / (level/120 * balls_left) and rescales to the test row's level."""

    def __init__(self, fine, level, mean=False):
        self.fine, self.level, self.mean = fine, level, mean

    def _prep(self, d):
        d = d.assign(bo=d.balls_bowled // 6 * 6, wk=np.minimum(d.wickets, 9), w12=np.minimum(d.wk_l12, 3), rb=_band(d))  # training rows of the same over share a cell
        return d

    def fit(self, tr):
        tr = self._prep(tr)
        a = tr[(tr.innings == 1) & ~tr.reduced & (tr.wickets < 10) & (tr.balls_left > 0) & tr.bo.between(18, 102)]
        rem = (a.final_total - a.runs).to_numpy(float)
        s = np.maximum(a.lvl_season.to_numpy(float) / 120 * a.balls_left.to_numpy(float), 0.5)
        a = a.assign(y=rem / s if self.level else rem)
        self.c = [_cells(a, ["bo", "wk"], "y"), _cells(a, ["bo", "wk", "w12"], "y"), _cells(a, ["bo", "wk", "w12", "rb"], "y")]
        w = tr[(tr.innings == 2) & ~tr.reduced & (tr.wickets < 10) & (tr.balls_left > 0) & tr.bo.between(18, 102) & tr.chase_won.notna() & (tr.runs_needed > 0)]
        w = w.assign(rr=np.digitize((w.runs_needed / w.balls_left.clip(lower=1) * 6).to_numpy(float), RRR_EDGES))
        self.wc = [{k: g.chase_won.to_numpy(float) for k, g in w.groupby(["bo", "wk", "rr"])},
                   {k: g.chase_won.to_numpy(float) for k, g in w.groupby(["bo", "wk", "rr", "w12"])},
                   {k: g.chase_won.to_numpy(float) for k, g in w.groupby(["bo", "wk", "rr", "w12", "rb"])}]
        return self

    def _pick(self, cells, keys):
        lv = (2, 1, 0) if self.fine else (0,)
        for l in lv:
            k = keys[l]
            a = cells[l].get(k)
            if a is not None and len(a) >= MIN_CELL:
                return a, l
        return cells[0].get(keys[0], np.array([0.0])), 0

    def score(self, te):
        te = self._prep(te)
        out, lev = np.zeros((len(te), 3)), []
        s = np.maximum(te.lvl_season.to_numpy(float) / 120 * te.balls_left.to_numpy(float), 0.5)
        for i, (b, wk, w12, rb) in enumerate(zip(te.balls_bowled, te.wk, te.w12, te.rb)):
            a, l = self._pick(self.c, [(b, wk), (b, wk, w12), (b, wk, w12, rb)])
            out[i] = np.quantile(a, [0.1, 0.5, 0.9])
            if self.mean:
                out[i, 1] = a.mean()
            lev.append(l)
        if self.level:
            out = out * s[:, None]
        return pd.DataFrame(out + te.runs.to_numpy(float)[:, None], columns=["q10", "q50", "q90"], index=te.index), np.array(lev)

    def win(self, te):
        te = self._prep(te)
        rr = np.digitize((te.runs_needed / te.balls_left.clip(lower=1) * 6).to_numpy(float), RRR_EDGES)
        out, lev = [], []
        for b, wk, r, w12, rb in zip(te.balls_bowled, te.wk, rr, te.w12, te.rb):
            a, l = self._pick(self.wc, [(b, wk, r), (b, wk, r, w12), (b, wk, r, w12, rb)])
            out.append((a.sum() + 0.5) / (len(a) + 1))
            lev.append(l)
        return np.array(out), np.array(lev)


def empirical_frames(feat, meta):
    """Fine/coarse empirical lookups, men's training seasons < Y, men's test over-end states 18..102 (the event table range)."""
    men = feat[feat.gender == "male"]
    out = {}
    for variant, fine, level, mean in (("emp-coarse", False, False, False), ("emp-fine", True, False, False), ("emp-fine-mean", True, False, True), ("emp-fine-lvl", True, True, False)):
        S, W, used = [], [], []
        for Y in (2022, 2023, 2024, 2025, 2026):
            m = Empirical(fine, level, mean).fit(men[men.season_year < Y])
            te = men[(men.season_year == Y) & ((men.competition == "ipl") | (Y in (2024, 2025))) & men.balls_bowled.isin(OVERS) & ~men.reduced & (men.balls_left > 0) & (men.wickets < 10)]
            t1, t2 = te[te.innings == 1], te[(te.innings == 2) & te.chase_won.notna() & (te.runs_needed > 0)]
            q, lev = m.score(t1)
            S.append(t1[D.META].assign(model=variant, **q))
            p, lv2 = m.win(t2)
            W.append(t2[D.META].assign(model=variant, p=p))
            used.append((lev == 2).mean())
        out[variant] = (_n(pd.concat(S)), _n(pd.concat(W)))
        print(f"  {variant}: share of first-innings states served by the full 4-way cell, by fold: {np.round(used, 2)}", flush=True)
    return out


HEAD = ["collapse 2wk/12b", "collapse 3wk/12b", "collapse 3wk/18b", "burst >=28r/12b", "death start, >=6 wkts in hand", "late, >=7 wkts in hand", "late, <=4 wkts in hand", "chase rrr >= 13", "new pair (both <6 faced)"]


def battery(frames, B=500):
    """Event battery on {name: (S, W)}; returns the long result table (flaw_tests.run_battery)."""
    e = T.load_events()
    fr = {n: (S[KEY + ["final_total", "q10", "q50", "q90"]], W[KEY + ["chase_won", "p"]]) for n, (S, W) in frames.items()}
    return T.run_battery(fr, e, B=B)


def headline(res, models=None, heads=None, col="bias"):
    """Pretty table: excess bias of headline events (runs for innings 1, pp for chase) with * where the interval excludes 0."""
    heads = heads or [h for h in HEAD]
    models = models or list(dict.fromkeys(res.model))
    r = res[res.event.isin(heads) & res.model.isin(models)].copy()
    if col == "med":  # median-correct test for innings 1: share of finals below the predicted median minus 50%, excess over matched non-event states, in pp
        r = r[r.kind == "inn1"]
    sc = np.where(r.kind == "inn1", 1.0, 100.0) if col == "bias" else np.full(len(r), 100.0)
    sig = (r[f"{col}_lo"] > 0) | (r[f"{col}_hi"] < 0)
    r["cell"] = [f"{v * s:+.1f}{'*' if g else ''}" for v, s, g in zip(r[f"{col}_diff"], sc, sig)]
    r["col"] = r.group + "/" + r.kind
    t = r.pivot_table(index=["event", "col"], columns="model", values="cell", aggfunc="first")
    return t[[m for m in models if m in t.columns]]


def d2(B=500):
    t0 = time.time()
    cols = ["match_id", "innings", "balls_bowled", "final_total", "chase_won", "season_year", "competition", "venue", "batting_team", "date", "reduced",
            "balls_left", "runs_needed", "gender", "wickets", "runs", "wk_l12", "runs_l12", "lvl_season"]
    feat = load_feat(cols, even=False)
    feat = feat[feat.balls_bowled.between(18, 107)]
    meta = meta_table(feat)
    fr = empirical_frames(feat, meta)
    for nm, cn in (("G1", "g1r"), ("G2", "g2")):
        S, W = cache_frames(cn, meta)
        fr[nm] = (S, W)
    print(f"frames {time.time() - t0:.0f}s", flush=True)
    res = battery(fr, B)
    res.to_csv(OUT_DIR / "db_d2_battery.csv", index=False)
    pd.set_option("display.width", 260)
    pd.set_option("display.max_colwidth", 30)
    print(headline(res).to_string())
    print(headline(res, heads=["collapse 2wk/12b", "collapse 3wk/12b", "collapse 3wk/18b"], col="med").to_string())
    # raw (not excess) collapse bias, for reading
    r = res[res.event.isin(["collapse 3wk/12b"])][["model", "group", "kind", "n_matches", "bias_event", "bias_rest", "bias_diff", "bias_lo", "bias_hi"]]
    print(r.round(3).to_string())
    return res


def d2_floor(B=300):
    """Stationary floor: the same empirical lookups with RANDOM 5-fold CV over men's matches 2018-25 (no time shift) and in-sample.
    Whatever excess remains here is an artefact of the event test itself (median vs mean, cell mixing), not of the model or the era."""
    cols = ["match_id", "innings", "balls_bowled", "final_total", "chase_won", "season_year", "competition", "venue", "batting_team", "date", "reduced",
            "balls_left", "runs_needed", "gender", "wickets", "runs", "wk_l12", "runs_l12", "lvl_season"]
    feat = load_feat(cols, even=False)
    ms = feat[(feat.gender == "male") & feat.season_year.between(2018, 2025) & feat.balls_bowled.between(18, 107)]
    ids = ms.match_id.unique()
    fold = pd.Series(np.random.default_rng(1).integers(0, 5, len(ids)), index=ids)
    ms = ms.assign(f=ms.match_id.map(fold))
    ok = ~ms.reduced & (ms.balls_left > 0) & (ms.wickets < 10) & ms.balls_bowled.isin(OVERS)
    fr = {}
    for nm, mean in (("emp-fine-cv", False), ("emp-fine-cv-mean", True)):
        S, W = [], []
        for k in range(5):
            m = Empirical(True, False, mean).fit(ms[ms.f != k])
            te = ms[(ms.f == k) & ok]
            t1, t2 = te[te.innings == 1], te[(te.innings == 2) & te.chase_won.notna() & (te.runs_needed > 0)]
            S.append(t1[D.META].assign(model=nm, **m.score(t1)[0]))
            W.append(t2[D.META].assign(model=nm, p=m.win(t2)[0]))
        fr[nm] = (_n(pd.concat(S)), _n(pd.concat(W)))
    m = Empirical(True, False, False).fit(ms)
    te = ms[ok]
    t1, t2 = te[te.innings == 1], te[(te.innings == 2) & te.chase_won.notna() & (te.runs_needed > 0)]
    fr["emp-fine-insample"] = (_n(t1[D.META].assign(model="emp-fine-insample", **m.score(t1)[0])), _n(t2[D.META].assign(model="emp-fine-insample", p=m.win(t2)[0])))
    e = T.load_events()
    e = e[e.season_year.between(2018, 2025)]
    fr2 = {n: (S[KEY + ["final_total", "q10", "q50", "q90"]], W[KEY + ["chase_won", "p"]]) for n, (S, W) in fr.items()}
    res = T.run_battery(fr2, e, B=B)
    res.to_csv(OUT_DIR / "db_d2_floor_battery.csv", index=False)
    print("\n### D2 floor: stationary (random-match CV 2018-25, in-sample); excess is an artefact of the test itself")
    print(headline(res, heads=HEAD).to_string())
    return res


# ---------- metrics on identical states ----------
def common(frames):
    """Restrict every (S, W) to the keys all frames share (so paired comparisons are on identical states)."""
    ks = None
    kw = None
    for S, W in frames.values():
        a, b = set(map(tuple, S[KEY].to_numpy())), set(map(tuple, W[KEY].to_numpy()))
        ks = a if ks is None else ks & a
        kw = b if kw is None else kw & b
    ks, kw = pd.MultiIndex.from_tuples(sorted(ks)), pd.MultiIndex.from_tuples(sorted(kw))
    return {n: (S[pd.MultiIndex.from_frame(S[KEY]).isin(ks)], W[pd.MultiIndex.from_frame(W[KEY]).isin(kw)]) for n, (S, W) in frames.items()}


def metrics_by_scope(frames, scopes=SCOPES):
    rows = []
    for n, (S, W) in frames.items():
        for sc in scopes:
            s, w = S[S.scope == sc].assign(model=n, fold=0), W[W.scope == sc].assign(model=n, fold=0)
            if not len(s):
                continue
            m = D.summarise(s, w).iloc[0]
            rows.append({"model": n, "scope": sc, "MAE": m["MAE"], "pinball": m["pinball"], "cov80": m["cov80"], "bias": m["bias"], "ll": m["ll"], "ece": m["ece"]})
    return pd.DataFrame(rows)


def paired(frames, ref, scopes=SCOPES, n=1000):
    """Per scope: bootstrap over matches of (model - ref) for MAE, pinball, cov, bias, chase log loss, on identical states."""
    rows = []
    for nm, (S, W) in frames.items():
        if nm == ref:
            continue
        for sc in scopes:
            a = (S[S.scope == sc].assign(model=nm), W[W.scope == sc].assign(model=nm))
            b = (frames[ref][0][frames[ref][0].scope == sc], frames[ref][1][frames[ref][1].scope == sc])
            if not len(a[0]):
                continue
            r = {"model": nm, "scope": sc}
            for k in ("mae", "pin", "cov", "bias"):
                x = D.boot_diff(a[0], b[0], k, n=n)
                r[f"d{k}"], r[f"d{k}_lo"], r[f"d{k}_hi"] = x[:3]
            x = D.boot_diff(a[1], b[1], "ll", n=n)
            r["dll"], r["dll_lo"], r["dll_hi"] = x[:3]
            rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["d1"]:
        d1()
    elif a[:1] == ["d2"]:
        d2()
        d2_floor()
