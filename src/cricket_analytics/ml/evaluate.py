"""Evaluation harness: time-based splits, score and win metrics, bias breakdowns, plots.

Rule: evaluate by season (train < Y, test == Y). The final holdout season (2026) is refused unless
`allow_holdout=True`. All metrics take optional weights; `match_weights` gives each innings equal weight.
"""

from pathlib import Path

import numpy as np
import pandas as pd

HOLDOUT = 2026
IMG_DIR = Path(__file__).resolve().parents[3] / "docs" / "img"
CHECKPOINT_OVERS = (0, 6, 10, 15)
QS = (0.1, 0.5, 0.9)


# ---------- splits ----------
def rolling_splits(df, test_years=(2022, 2023, 2024, 2025), holdout=HOLDOUT, allow_holdout=False, year_col="season_year"):
    """Yield (year, train, test). train = year < Y, test = year == Y. Holdout rows never appear in train."""
    if not allow_holdout and any(int(y) >= holdout for y in test_years):
        raise ValueError(f"season {holdout} is the locked holdout; pass allow_holdout=True to open it")
    for y in test_years:
        yield int(y), df[df[year_col] < y], df[df[year_col] == y]


# ---------- weights ----------
def match_weights(df, keys=("match_id", "innings")):
    """1 / (rows in the same innings): every innings counts equally whatever its length."""
    return (1.0 / df.groupby(list(keys))[keys[0]].transform("size")).to_numpy()


def _w(y, w):
    return np.ones(len(y)) if w is None else np.asarray(w, float)


def _avg(x, w):
    return float(np.sum(np.asarray(x) * w) / np.sum(w))


# ---------- score metrics ----------
def mae(y, pred, w=None):
    y = np.asarray(y, float)
    return _avg(np.abs(y - np.asarray(pred, float)), _w(y, w))


def pinball(y, pred, q, w=None):
    """Quantile loss for level q (0..1)."""
    y = np.asarray(y, float)
    d = y - np.asarray(pred, float)
    return _avg(np.maximum(q * d, (q - 1) * d), _w(y, w))


def pinball_mean(y, preds: dict, w=None):
    """Mean pinball loss over the given {level: prediction} (about half a CRPS when levels are spread out)."""
    return float(np.mean([pinball(y, p, q, w) for q, p in preds.items()]))


def crps_samples(y, samples, w=None):
    """CRPS from an (n, k) sample matrix: E|X-y| - 0.5 E|X-X'|. Exact for the ensemble."""
    y = np.asarray(y, float)
    x = np.sort(np.asarray(samples, float), axis=1)
    k = x.shape[1]
    t1 = np.abs(x - y[:, None]).mean(1)
    i = np.arange(1, k + 1)
    t2 = (x * (2 * i - k - 1)).sum(1) / k**2  # = 0.5 * E|X-X'| via sorted formula
    return _avg(t1 - t2, _w(y, w))


def coverage(y, lo, hi, w=None):
    y = np.asarray(y, float)
    return _avg((y >= np.asarray(lo)) & (y <= np.asarray(hi)), _w(y, w))


def score_metrics(y, q10, q50, q90, w=None):
    return {
        "mae": mae(y, q50, w),
        "pinball": pinball_mean(y, {0.1: q10, 0.5: q50, 0.9: q90}, w),
        "cov80": coverage(y, q10, q90, w),
        "bias": _avg(np.asarray(q50, float) - np.asarray(y, float), _w(y, w)),
    }


# ---------- win metrics ----------
def _clip(p, eps=1e-6):
    return np.clip(np.asarray(p, float), eps, 1 - eps)


def log_loss(y, p, w=None):
    y, p = np.asarray(y, float), _clip(p)
    return _avg(-(y * np.log(p) + (1 - y) * np.log(1 - p)), _w(y, w))


def brier(y, p, w=None):
    y = np.asarray(y, float)
    return _avg((np.asarray(p, float) - y) ** 2, _w(y, w))


def reliability_table(y, p, bins=10, w=None):
    """Per probability bin: mean predicted, observed win rate, count (and weight)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    w = _w(y, w)
    b = np.minimum((p * bins).astype(int), bins - 1)
    rows = []
    for i in range(bins):
        k = b == i
        if k.any():
            rows.append({"bin": i, "pred": _avg(p[k], w[k]), "obs": _avg(y[k], w[k]), "n": int(k.sum()), "w": float(w[k].sum())})
    return pd.DataFrame(rows)


def ece(y, p, bins=10, w=None):
    """Expected calibration error: weighted mean |observed - predicted| over probability bins."""
    t = reliability_table(y, p, bins, w)
    return float((t.w * (t.obs - t.pred).abs()).sum() / t.w.sum())


def win_metrics(y, p, w=None):
    return {"logloss": log_loss(y, p, w), "brier": brier(y, p, w), "ece": ece(y, p, 10, w)}


# ---------- slicing ----------
def at_checkpoints(df, overs=CHECKPOINT_OVERS, balls_per_over=6):
    """Rows where exactly `o` overs have been bowled, with a `checkpoint` column (over number)."""
    out = []
    for o in overs:
        out.append(df[df.balls_bowled == o * balls_per_over].assign(checkpoint=o))
    return pd.concat(out, ignore_index=True)


def by_group(df, group_col, metric_fn):
    """metric_fn(sub_df) -> dict of numbers; returns one row per group value with n rows."""
    rows = [{group_col: k, "n": len(g), **metric_fn(g)} for k, g in df.groupby(group_col)]
    return pd.DataFrame(rows)


# ---------- plots (matplotlib optional) ----------
def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError:
        print("matplotlib not installed: plot skipped")
        return None


def reliability_plot(y, p, name, bins=10, w=None):
    """Save docs/img/ml_<name>.png. Returns the path or None."""
    plt = _plt()
    if plt is None:
        return None
    t = reliability_table(y, p, bins, w)
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], "--", color="grey")
    ax.plot(t.pred, t.obs, "o-")
    ax.set(xlabel="predicted win probability", ylabel="observed win rate", title=name)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    path = IMG_DIR / f"ml_{name}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


def coverage_by_over_plot(df, name, y="y", lo="q10", hi="q90", over="over"):
    """80% interval coverage per over (df has columns y, lo, hi, over). Saves docs/img/ml_<name>.png."""
    plt = _plt()
    if plt is None:
        return None
    g = df.assign(_in=(df[y] >= df[lo]) & (df[y] <= df[hi])).groupby(over)._in.mean()
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.axhline(0.8, ls="--", color="grey")
    ax.plot(g.index, g.values, "o-")
    ax.set(xlabel="overs bowled", ylabel="share inside 10-90% range", ylim=(0, 1), title=name)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    path = IMG_DIR / f"ml_{name}.png"
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path
