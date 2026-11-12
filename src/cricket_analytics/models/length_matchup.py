"""Batter-vs-bowler matchup from LENGTH (Cricbuzz commentary) vs pace/spin baselines, with a 2017-24 -> 2025-26 backtest.

Prediction for a pair = sum over 5 length buckets of (bowler's share of balls in that bucket) x (batter's rate vs that bucket),
both shrunk toward the league (empirical Bayes: (sum + k*prior)/(n + k)). Runs and wickets always come from Cricsheet columns;
commentary only supplies the length label (known on ~59% of balls). Run: python -m cricket_analytics.models.length_matchup
"""
from __future__ import annotations

import numpy as np
import pandas as pd

B = ["yorker_ft", "full", "good", "short", "bouncer"]
_MAP = {"yorker": "yorker_ft", "full toss": "yorker_ft", "full": "full", "length": "good", "back of a length": "good",
        "short of length": "short", "short": "short", "bouncer": "bouncer"}
_NOT_BOWLER = {"run out", "retired hurt", "retired out", "retired not out", "obstructing the field", "hit the ball twice"}
OUT = "data/external/commentary/length_matchup_"


def shrink(s, n, prior, k):
    """Empirical-Bayes rate: (sum + k*prior)/(n + k). n=0 gives the prior; large n gives the raw rate."""
    return (s + k * prior) / (n + k)


def load() -> pd.DataFrame:
    """All IPL 2017+ faced balls (wides excluded) with runs, wicket flag, bowl kind and length bucket (NaN if unknown)."""
    from ..ingest.commentary import load_parsed
    from ..sql.filters import Filters
    from . import worth

    d = worth.ball_frame(Filters(competition="ipl", season_from=2017))
    d = d[(d.innings <= 2) & (d.wides == 0)].copy()
    p = load_parsed()[["match_id", "innings", "ball_seq", "length"]].drop_duplicates(["match_id", "innings", "ball_seq"])
    d = d.merge(p, on=["match_id", "innings", "ball_seq"], how="left")
    d["b"] = d.length.map(_MAP)
    d["runs"] = d.runs_batter.astype(float)
    d["w"] = (d.wicket_type.notna() & ~d.wicket_type.isin(_NOT_BOWLER)).astype(float)
    d["year"] = d.year.astype(int)
    return d[["match_id", "batter", "bowler", "year", "runs", "w", "bowl_kind", "b"]]


def _mat(df, key, ids, col):
    """key x buckets matrix of sums of `col` (col='n': ball counts), rows aligned to `ids`, 0 where unseen."""
    if col == "n":
        g = df.groupby([key, "b"]).size().unstack()
    else:
        g = df.groupby([key, "b"])[col].sum().unstack()
    return g.reindex(columns=B).fillna(0.0).reindex(ids).fillna(0.0).values


def predict(train: pd.DataFrame, pairs: pd.DataFrame, kr=40, kw=300, km=60, kc=100) -> pd.DataFrame:
    """Return pairs (batter, bowler, bowl_kind) + pr_/pw_ columns (runs/ball, wicket/ball) for: league, bat, kind, kind_h,
    len, len_h, len_hc. Suffix _h = prior is the batter's own overall rate x league bucket pattern (hierarchical), else the
    plain league prior. len_hc also multiplies by the bowler's own per-bucket concession relative to league."""
    out = pairs[["batter", "bowler", "bowl_kind"]].copy().reset_index(drop=True)
    kn = train[train.b.notna()]
    bt = train.groupby("batter").agg(n=("runs", "size"), r=("runs", "sum"), w=("w", "sum")).reindex(out.batter).fillna(0.0)
    lmix = kn.b.value_counts(normalize=True).reindex(B).fillna(0.0).values
    for tag, k in (("r", kr), ("w", kw)):
        s = "runs" if tag == "r" else "w"
        base = train[s].mean()
        lg = kn.groupby("b")[s].mean().reindex(B).fillna(base).clip(lower=1e-6).values
        sc = base / (lmix * lg).sum()  # known-length balls skew to big hits: rescale to the all-balls level
        bo = shrink(bt[tag if tag == "w" else "r"].values, bt.n.values, base, k)  # batter overall, all balls
        out["p%s_league" % tag] = base
        out["p%s_bat" % tag] = bo
        kk = train.groupby("bowl_kind")[s].mean()
        kt = train.groupby(["batter", "bowl_kind"]).agg(n=("runs", "size"), x=(s, "sum"))
        kt = kt.reindex(pd.MultiIndex.from_frame(out[["batter", "bowl_kind"]])).fillna(0.0)
        rel = out.bowl_kind.map(kk / base).fillna(1.0).values
        known = out.bowl_kind.notna().values
        out["p%s_kind" % tag] = np.where(known, shrink(kt.x.values, kt.n.values, out.bowl_kind.map(kk).fillna(base).values, k), bo)
        out["p%s_kind_h" % tag] = np.where(known, shrink(kt.x.values, kt.n.values, bo * rel, k), bo)
        Nb, Xb = _mat(kn, "batter", out.batter, "n"), _mat(kn, "batter", out.batter, s)
        Mb, Xo = _mat(kn, "bowler", out.bowler, "n"), _mat(kn, "bowler", out.bowler, s)
        mix = shrink(Mb, Mb.sum(1, keepdims=True), lmix, km)
        rate = shrink(Xb, Nb, lg[None, :], k)
        rate_h = shrink(Xb, Nb, lg[None, :] * (bo / base)[:, None], k)
        f = shrink(Xo, Mb, lg[None, :], kc) / lg[None, :]
        out["p%s_len" % tag] = sc * (mix * rate).sum(1)
        out["p%s_len_h" % tag] = sc * (mix * rate_h).sum(1)
        out["p%s_len_hc" % tag] = sc * (mix * rate_h * f).sum(1)
    for c in [c for c in out if c.startswith("pw_")]:
        out[c] = out[c].clip(0.001, 0.5)
    return out


METHODS = {"league": "(a) league average", "bat": "(b) batter overall", "kind": "(c) batter vs pace/spin",
           "kind_h": "(c2) pace/spin, batter-anchored prior", "len": "(d) length model",
           "len_h": "(d2) length, batter-anchored prior", "len_hc": "(d3) d2 x bowler concession"}


def pair_table(df, years, min_balls=6):
    g = df[df.year.isin(years)].groupby(["batter", "bowler"]).agg(
        n=("runs", "size"), runs=("runs", "sum"), w=("w", "sum"), bowl_kind=("bowl_kind", "first")).reset_index()
    g = g[g.n >= min_balls].reset_index(drop=True)
    g["rate"], g["wrate"] = g.runs / g.n, g.w / g.n
    return g


def score(pred, pairs) -> pd.DataFrame:
    n, y, q = pairs.n.values, pairs.rate.values, pairs.wrate.values
    rows = []
    for m, label in METHODS.items():
        p, pw = pred["pr_" + m].values, pred["pw_" + m].values
        ll = -(q * np.log(pw) + (1 - q) * np.log(1 - pw))
        rows.append(dict(method=label, key=m, runs_mse=(n * (p - y) ** 2).sum() / n.sum(),
                         spearman=np.nan if m == "league" else pd.Series(p).rank().corr(pd.Series(y).rank()), wkt_logloss=(n * ll).sum() / n.sum()))
    return pd.DataFrame(rows)


def tune(df):
    """Pick kr and kw per method on 2017-22 -> 2023-24 (never looks at 2025-26)."""
    tr, va = df[df.year <= 2022], pair_table(df, [2023, 2024])
    best = {}
    for tag, grid, col in (("r", (15, 30, 60, 120), "runs_mse"), ("w", (100, 200, 400, 800), "wkt_logloss")):
        t = pd.DataFrame({k: score(predict(tr, va, **{"kr" if tag == "r" else "kw": k}), va).set_index("key")[col] for k in grid})
        best[tag] = t.idxmin(axis=1).to_dict()
    return best


def backtest(df=None):
    df = load() if df is None else df
    train, test = df[df.year <= 2024], pair_table(df, [2025, 2026])
    best = tune(df)
    pred = predict(train, test)
    for m in METHODS:
        if m != "league":
            p = predict(train, test, kr=best["r"][m], kw=best["w"][m])
            pred["pr_" + m], pred["pw_" + m] = p["pr_" + m], p["pw_" + m]
    return pred, test, score(pred, test), best


def bootstrap_diff(pred, pairs, a, b, reps=2000, seed=0):
    """Ball-weighted runs-MSE of a minus b, with 95% interval over pair resamples. Negative = a better."""
    n, y = pairs.n.values, pairs.rate.values
    d = n * ((pred["pr_" + a] - y) ** 2 - (pred["pr_" + b] - y) ** 2).values
    idx = np.random.default_rng(seed).integers(0, len(d), (reps, len(d)))
    bs = d[idx].sum(1) / n[idx].sum(1)
    return (d.sum() / n.sum(), *np.percentile(bs, [2.5, 97.5]))


def examples(df, k=40, minb=150, minbowl=200):
    """Batters with the weakest/strongest rate in a bucket relative to their own overall and the league pattern, plus the
    bowlers who bowl that length most (train years only)."""
    tr = df[(df.year <= 2024) & df.b.notna()]
    lr, lw = tr.groupby("b").runs.mean(), tr.groupby("b").w.mean()
    g = tr.groupby(["batter", "b"]).agg(n=("runs", "size"), r=("runs", "sum"), w=("w", "sum")).reset_index()
    g = g[g.batter.map(tr.groupby("batter").size()) >= minb * 3]
    g["rpb"] = shrink(g.r, g.n, g.b.map(lr), k)
    g["wpb"] = shrink(g.w, g.n, g.b.map(lw), 4 * k)
    g["rel"] = g.rpb / g.batter.map(tr.groupby("batter").runs.mean()) / (g.b.map(lr) / tr.runs.mean())
    mix = tr.groupby("bowler").b.value_counts().unstack().reindex(columns=B).fillna(0)
    mix = mix[mix.sum(1) >= minbowl]
    share = mix.div(mix.sum(1), axis=0)
    rows = []
    for b, how in (("short", "weak"), ("full", "weak"), ("good", "weak"), ("yorker_ft", "weak"), ("short", "strong")):
        s = g[(g.b == b) & (g.n >= 40)].sort_values("rel", ascending=(how == "weak")).iloc[0]
        for bw in share[b].sort_values(ascending=False).head(3).index:
            rows.append(dict(batter=s.batter, case=f"{how} vs {b}", batter_rpb=round(s.rpb, 2), league_rpb=round(lr[b], 2),
                             batter_wpb=round(s.wpb, 3), league_wpb=round(lw[b], 3), batter_n=int(s.n), bowler=bw,
                             bowler_share=round(share.loc[bw, b], 3), league_share=round((tr.b == b).mean(), 3)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from pathlib import Path

    df = load()
    pred, test, sc, best = backtest(df)
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    sc.to_csv(OUT + "summary.csv", index=False)
    pred.assign(n=test.n, rate=test.rate, wrate=test.wrate).to_csv(OUT + "backtest_pairs.csv", index=False)
    print(sc.to_string(index=False))
    print("k:", best)
    for a, b in (("len", "kind"), ("len_h", "kind_h"), ("len_hc", "kind_h"), ("len", "bat"), ("kind", "bat")):
        print("runs-MSE diff", a, "-", b, [round(x, 6) for x in bootstrap_diff(pred, test, a, b)])
    ex = examples(df)
    ex.to_csv(OUT + "examples.csv", index=False)
    print(ex.to_string(index=False))
    print("pairs", len(test), "balls", int(test.n.sum()), "known-length share train", df[df.year <= 2024].b.notna().mean())
