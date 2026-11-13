"""S1 baselines: run-rate projection, lookup table, resource table (DLS-like). Fit on train seasons only.

Each model has fit(train_states) and
  score(states) -> DataFrame q10,q50,q90 of the FINAL total (first-innings states)
  win(states)   -> P(chasing side wins) for second-innings states.
Run: python -m cricket_analytics.ml.baselines   (IPL 2022-2025 rolling; never opens 2026).
"""

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from . import evaluate as ev
from .dataset import OUT_DIR, load

BPO = 6


def usable(s):
    """Non-reduced rows that are not terminal (the game is still undecided)."""
    return s[~s.reduced & (s.balls_left > 0) & (s.wickets < 10)]


def _first(train):
    return usable(train[train.innings == 1]).assign(rem=lambda d: d.final_total - d.runs)


def _over(s):
    return (s.balls_bowled // BPO).clip(upper=19).to_numpy()


def _p_ge(sorted_arr, need):
    """Smoothed share of the sample that is >= need."""
    n_ge = len(sorted_arr) - np.searchsorted(sorted_arr, need, side="left")
    return (n_ge + 0.5) / (len(sorted_arr) + 1)


class RunRate:
    """runs + current_rr * balls_left; interval from train residuals of the same over (+ optional bias shift)."""

    def __init__(self, bias_corrected=False):
        self.bc = bias_corrected
        self.name = "run-rate+bias" if bias_corrected else "run-rate"

    def _point(self, s):
        rr = np.where(s.balls_bowled > 0, s.runs / s.balls_bowled.clip(lower=1), self.rr0)
        return (s.runs + rr * s.balls_left).to_numpy()

    def fit(self, train):
        f = _first(train)
        self.rr0 = (f[f.balls_bowled == 0].final_total / 120).mean()
        res = (f.final_total - self._point(f)).groupby(_over(f)).quantile([0.1, 0.5, 0.9]).unstack()
        self.res = res.reindex(range(20)).ffill()
        return self

    def score(self, s):
        r = self.res.iloc[_over(s)]
        p = self._point(s)
        q50 = p + r[0.5].to_numpy() if self.bc else p
        return pd.DataFrame({"q10": p + r[0.1].to_numpy(), "q50": q50, "q90": p + r[0.9].to_numpy()}, index=s.index)

    def win(self, s):
        return None  # a plain run rate has no win probability


class Lookup:
    """Empirical distribution of remaining runs by (over, wickets capped at 7); over-only if the cell is thin."""

    MIN_N = 30

    def __init__(self, pool="ipl"):
        self.pool, self.name = pool, f"lookup-{pool}"

    def fit(self, train):
        if self.pool == "ipl":
            train = train[train.competition == "ipl"]
        f = _first(train)
        o, w = _over(f), np.minimum(f.wickets.to_numpy(), 7)
        self.cells = {k: np.sort(g.rem.to_numpy()) for k, g in f.groupby([o, w])}
        self.by_over = {k: np.sort(g.rem.to_numpy()) for k, g in f.groupby(o)}
        return self

    def _dist(self, o, w):
        a = self.cells.get((o, min(w, 7)))
        return a if a is not None and len(a) >= self.MIN_N else self.by_over[o]

    def score(self, s):
        q = np.array([np.quantile(self._dist(o, w), [0.1, 0.5, 0.9]) for o, w in zip(_over(s), s.wickets)])
        return pd.DataFrame(q + s.runs.to_numpy()[:, None], columns=["q10", "q50", "q90"], index=s.index)

    def win(self, s):
        return pd.Series([_p_ge(self._dist(o, w), n) for o, w, n in zip(_over(s), s.wickets, s.runs_needed)], index=s.index)


class Resource:
    """E[remaining | balls_left u, wickets w] = Z0[w] * (1 - exp(-b*u/Z0[w])) (DLS form), least squares on cell means.
    Z0 is forced to fall with wickets. Interval and win probability use train residuals by over."""

    def __init__(self, pool="ipl"):
        self.pool, self.name = pool, f"resource-{pool}"

    def _z(self, u, w, p):
        z0 = np.minimum.accumulate(p[:10])[np.minimum(np.asarray(w, int), 9)]
        return z0 * (1 - np.exp(-p[10] * u / z0))

    def fit(self, train):
        if self.pool == "ipl":
            train = train[train.competition == "ipl"]
        f = _first(train)
        c = f.groupby(["balls_left", "wickets"]).rem.agg(["mean", "size"]).reset_index()
        u, w, y, n = (c[k].to_numpy() for k in ("balls_left", "wickets", "mean", "size"))
        x0 = np.r_[np.linspace(260, 120, 10), 1.0]
        self.p = np.abs(least_squares(lambda p: np.sqrt(n) * (self._z(u, w, np.abs(p)) - y), x0).x)
        r = f.rem.to_numpy() - self._z(f.balls_left.to_numpy(), f.wickets.to_numpy(), self.p)
        self.res = {k: np.sort(g.to_numpy()) for k, g in pd.Series(r, index=f.index).groupby(_over(f))}
        return self

    def mean_remaining(self, s):
        return self._z(s.balls_left.to_numpy(), s.wickets.to_numpy(), self.p)

    def score(self, s):
        z = self.mean_remaining(s) + s.runs.to_numpy()
        q = np.array([np.quantile(self.res[o], [0.1, 0.5, 0.9]) for o in _over(s)])
        return pd.DataFrame(z[:, None] + q, columns=["q10", "q50", "q90"], index=s.index)

    def win(self, s):
        z = self.mean_remaining(s)
        return pd.Series([_p_ge(self.res[o], n - zi) for zi, o, n in zip(z, _over(s), s.runs_needed)], index=s.index)


class LevelResource(Resource):
    """F-score: the resource table with its remaining runs scaled by a PRIOR-ONLY level ratio k = lvl_ew / den.
    den = mean first-innings total of the (non-reduced) training innings, i.e. the scoring level the table was anchored to.
    `lvl_ew` (features.innings_features) uses only earlier matches, so no test-fold information enters.
    fit(train) needs men's rows (the caller filters); score(s) needs an `lvl_ew` column. q10 / q90 can be widened by
    `calibrate(val)` (split conformal per over bucket, same as G1): val = states of a later season, table fitted before it."""

    def __init__(self, pool="ipl"):
        super().__init__(pool)
        self.name, self.delta = "F-score", {}

    def fit(self, train):
        super().fit(train)
        t = train[train.competition == "ipl"] if self.pool == "ipl" else train
        f = t[(t.innings == 1) & (t.balls_bowled == 0) & ~t.reduced]
        self.den = float(f.final_total.mean())
        return self

    def k(self, s):
        return s.lvl_ew.to_numpy(float) / self.den

    def expected_left(self, s):
        """Level-scaled expected remaining runs (used by F-chase as the yardstick for runs needed)."""
        return np.maximum(self.mean_remaining(s) * self.k(s), 1.0)

    def raw(self, s):
        q = np.array([np.quantile(self.res[o], [0.1, 0.5, 0.9]) for o in _over(s)])
        rem = np.maximum((self.mean_remaining(s)[:, None] + q) * self.k(s)[:, None], 0.0)
        return rem + s.runs.to_numpy()[:, None]

    def score(self, s):
        from . import direct as D

        q = self.raw(s)
        lo, hi = D.conformal_apply(q[:, 0], q[:, 1], q[:, 2], D.over_bucket(s.balls_bowled), self.delta)
        return pd.DataFrame({"q10": np.asarray(lo), "q50": q[:, 1], "q90": np.asarray(hi)}, index=s.index)

    def calibrate(self, val):
        """Conformal deltas from `val` (first-innings states with final_total) scored by THIS table (fitted before val)."""
        from . import direct as D

        q = self.raw(val)
        self.delta = D.conformal_delta(val.final_total.to_numpy(), q[:, 0], q[:, 2], D.over_bucket(val.balls_bowled))
        return self


class FChase:
    """F-chase: logistic regression of the chase result on level-scaled quantities (prior-only, fitted per fold).
    Inputs: log(runs needed / level-scaled expected runs left), that ratio, wickets in hand, balls left / 120, lvl_ew / 150,
    and two interactions (log ratio x balls left, log ratio x wickets in hand). `table` = a fitted LevelResource."""

    name = "F-chase"

    def __init__(self, table):
        self.table = table

    def _x(self, s):
        r = s.runs_needed.to_numpy(float) / self.table.expected_left(s)
        lr = np.log(np.clip(r, 0.02, 50.0))
        wk = 10.0 - s.wickets.to_numpy(float)
        bl = s.balls_left.to_numpy(float) / 120.0
        return np.column_stack([lr, np.clip(r, 0, 10), wk, bl, s.lvl_ew.to_numpy(float) / 150.0, lr * bl, lr * wk])

    def fit(self, train, stride=2):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        d = usable(train[train.innings == 2])
        d = d[d.chase_won.notna() & (d.runs_needed > 0) & (d.balls_bowled % stride == 0)]
        self.m = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)).fit(self._x(d), d.chase_won.to_numpy(int))
        return self

    def win(self, s):
        return pd.Series(self.m.predict_proba(self._x(s))[:, 1], index=s.index)


class Const:
    """Win probability = share of chases won in train (reference line)."""

    name = "const"

    def fit(self, train):
        c = usable(train[(train.innings == 2) & (train.balls_bowled == 0)]).dropna(subset=["chase_won"])
        self.p = c.chase_won.mean()
        return self

    def win(self, s):
        return pd.Series(self.p, index=s.index)


def _models():
    return [RunRate(), RunRate(True), Lookup("ipl"), Lookup("all"), Resource("ipl"), Resource("all")]


CHECK = [("0 overs", 0), ("6 overs", 36), ("10 overs", 60), ("15 overs", 90)]


def evaluate(states, comp="ipl", test_years=(2022, 2023, 2024, 2025)):
    """Rolling-origin evaluation on `comp`. Returns (score_table, win_table, win_preds, score_preds)."""
    ps, pw = [], []
    for _, train, test in ev.rolling_splits(states, test_years):
        test = usable(test[test.competition == comp])
        t1 = test[test.innings == 1]
        t2 = test[(test.innings == 2) & test.chase_won.notna() & (test.runs_needed > 0)]
        for m in _models() + [Const()]:
            m.fit(train)
            if hasattr(m, "score"):
                ps.append(t1.assign(model=m.name, **m.score(t1)))
            w = m.win(t2)
            if w is not None:
                pw.append(t2.assign(model=m.name, p=w))
    S, W = pd.concat(ps), pd.concat(pw)
    S["y"], S["over"] = S.final_total, S.balls_bowled // BPO

    def table(df, fn):
        out = []
        for name, g in df.groupby("model", sort=False):
            ninn = g.groupby(["match_id", "innings"]).ngroups
            for label, b in CHECK:
                sub = g[g.balls_bowled == b]
                out.append({"model": name, "at": label, "n": len(sub), **fn(sub, None)})
            out.append({"model": name, "at": "all (innings-weighted)", "n": ninn, **fn(g, ev.match_weights(g))})
            out.append({"model": name, "at": "all (per state)", "n": len(g), **fn(g, None)})
        return pd.DataFrame(out)

    sc = table(S, lambda d, w: ev.score_metrics(d.y, d.q10, d.q50, d.q90, w))
    wn = table(W, lambda d, w: ev.win_metrics(d.chase_won, d.p, w))
    return sc, wn, W, S


def md(df, nd=3):
    """Markdown table without the tabulate dependency."""
    cols = list(df.columns)
    fmt = lambda v: f"{v:.{nd}f}" if isinstance(v, float) else str(v)  # noqa: E731
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


if __name__ == "__main__":
    states, _ = load()
    sc, wn, W, S = evaluate(states)
    sc.to_csv(OUT_DIR / "baseline_score.csv", index=False)
    wn.to_csv(OUT_DIR / "baseline_win.csv", index=False)
    print(md(sc.round(2)), "\n")
    print(md(wn.round(3)))
    b = W[W.model == "resource-ipl"]
    print(ev.reliability_plot(b.chase_won, b.p, "baseline_resource_ipl_reliability", w=ev.match_weights(b)))
    print(ev.coverage_by_over_plot(S[S.model == "lookup-ipl"], "baseline_lookup_ipl_coverage"))
