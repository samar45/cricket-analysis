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
def rolling_splits(df, test_years=(2022, 2023, 2024, 2025), holdout=HOLDOUT, allow_holdout=False, year_col="season_year", allow_fresh3=False):
    """Yield (year, train, test). train = year < Y, test = year == Y. Holdout rows never appear in train."""
    if not allow_holdout and any(int(y) >= holdout for y in test_years):
        raise ValueError(f"season {holdout} is the locked holdout; pass allow_holdout=True to open it")
    if not allow_fresh3 and {"gender", "competition", "date", "batting_team", "bowling_team"} <= set(df.columns):
        assert_no_fresh3(df, "rolling_splits")
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


# ---------- v2 fresh holdout lock ----------
FRESH_FROM = "2026-01-01"
FRESH_LEAGUES = ("bbl", "blast", "bpl", "cpl", "ilt20", "lpl", "mlc", "psl", "sa20")  # the pre-registered fresh test set


def fresh_holdout_mask(df):
    """True for rows of the LOCKED v2 holdout: men's non-IPL matches dated 2026-01-01 or later (needs gender, competition, date).
    The lock is deliberately wider than the test set (it also covers men's T20I and Hundred)."""
    return ((df["gender"] == "male") & (df["competition"] != "ipl") & (pd.to_datetime(df["date"]) >= pd.Timestamp(FRESH_FROM))).to_numpy()


def assert_no_fresh(df, what, allow_fresh=False):
    """Raise if any locked row is in `df` (a train / validation / test set), unless allow_fresh=True."""
    n = int(fresh_holdout_mask(df).sum())
    if n and not allow_fresh:
        raise ValueError(f"{n} rows of the locked fresh holdout (men's non-IPL, >= {FRESH_FROM}) are in the {what} set; pass allow_fresh=True only for the one pre-registered run")
    return df


# ---------- fresh set #3 lock (pre-registered 2026-11-13, docs/ML_PREDICTION.md section 9) ----------
FRESH3_FROM = "2026-10-15"
FULL_MEMBERS = ("Afghanistan", "Australia", "Bangladesh", "England", "India", "Ireland", "New Zealand", "Pakistan", "South Africa", "Sri Lanka",
                "West Indies", "Zimbabwe")


def fresh3_mask(df):
    """True for rows of fresh set #3: men's, date >= 2026-10-15, and (not T20I, or both teams are full members).
    Needs gender, competition, date, batting_team, bowling_team (states / innings tables)."""
    full = df["batting_team"].isin(FULL_MEMBERS) & df["bowling_team"].isin(FULL_MEMBERS)
    ok = (df["competition"] != "t20i") | full
    return ((df["gender"] == "male") & (pd.to_datetime(df["date"]) >= pd.Timestamp(FRESH3_FROM)) & ok).to_numpy()


S26_FROM = "2026-10-15"  # SMAT 2026 live test set (Amendment 2); still inside fresh3_mask, so the training lock holds


def s26_mask(df):
    """True for men's Syed Mushtaq Ali Trophy rows dated >= S26_FROM. Needs gender, competition, date."""
    return ((df["gender"] == "male") & (df["competition"] == "smat") & (pd.to_datetime(df["date"]) >= pd.Timestamp(S26_FROM))).to_numpy()


def fresh3_scoring_mask(df):
    """Rows the one-time fresh-3 scoring run uses: fresh3_mask without S26 (scored in its own run)."""
    return fresh3_mask(df) & ~s26_mask(df)


def assert_no_fresh3(df, what, allow_fresh3=False):
    """Raise if any fresh-set-#3 row is in `df` (a development split), unless allow_fresh3=True (the one pre-registered run)."""
    n = int(fresh3_mask(df).sum())
    if n and not allow_fresh3:
        raise ValueError(f"{n} rows of locked fresh set #3 are in the {what} set; pass allow_fresh3=True only for the one pre-registered run")
    return df


# ---------- test statistics (added 2026-11-13 after the external review: HIGH 1, HIGH 3, MEDIUM 4, MEDIUM 6) ----------
def _logit(p, eps=1e-6):
    p = _clip(p, eps)
    return np.log(p / (1 - p))


def _logistic_fit(x, y, groups=None):
    """Logistic regression y ~ a + b*x by Newton steps. Returns (coef[2], cov[2,2]); cov is cluster-robust when `groups` is given."""
    X = np.column_stack([np.ones(len(x)), x])
    beta = np.array([0.0, 1.0])  # start at "perfectly calibrated"
    for _ in range(50):
        mu = 1 / (1 + np.exp(-X @ beta))
        H = X.T @ (X * (mu * (1 - mu))[:, None]) + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, X.T @ (y - mu))
        beta = beta + step
        if np.abs(step).max() < 1e-8:
            break
    mu = 1 / (1 + np.exp(-X @ beta))
    Hinv = np.linalg.inv(X.T @ (X * (mu * (1 - mu))[:, None]) + 1e-9 * np.eye(2))
    if groups is None:
        return beta, Hinv
    s = pd.DataFrame(X * (y - mu)[:, None]).groupby(np.asarray(groups)).sum().to_numpy()
    return beta, Hinv @ (s.T @ s) @ Hinv


def calibration_test(y, p, groups=None, by=None, n_sim=2000, seed=0, bins=10):
    """Calibration test for win probabilities. PRIMARY = logistic recalibration: fit y ~ a + b*logit(p); pass if the 95% CI of the
    intercept a (calibration-in-the-large) contains 0 AND the 95% CI of the slope b contains 1. SECONDARY = ECE against its own null:
    outcomes y* ~ Bernoulli(p) (a perfectly calibrated model), `n_sim` draws; pass if ECE <= null 95th percentile.
    Why: a fixed ECE limit (0.08) is failed ~98% of the time by a PERFECT model at n ~ 70 (external review, HIGH 1).
    groups: match id per row; gives cluster-robust CIs and one shared uniform per match in the null (rows of one match are correlated).
    by: checkpoint label per row; ECE is then the mean of per-checkpoint ECEs ("mean of 4"), otherwise pooled.
    Returns a dict; `pass_primary` and `pass_secondary` are the two verdicts; `passes` = pass_primary."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    g = None if groups is None else np.asarray(groups)
    b = None if by is None else np.asarray(by)
    z = _logit(p)
    beta, cov = _logistic_fit(z, y, g)
    se = np.sqrt(np.diag(cov))
    ci_a, ci_b = (beta[0] - 1.96 * se[0], beta[0] + 1.96 * se[0]), (beta[1] - 1.96 * se[1], beta[1] + 1.96 * se[1])

    def _ece(yy):
        if b is None:
            return ece(yy, p, bins)
        return float(np.mean([ece(yy[b == k], p[b == k], bins) for k in np.unique(b)]))

    obs = _ece(y)
    rng = np.random.default_rng(seed)
    if g is None:
        codes, ng = np.arange(len(y)), len(y)
    else:
        codes, uniq = pd.factorize(g)
        ng = len(uniq)
    nulls = np.array([_ece((rng.random(ng)[codes] < p).astype(float)) for _ in range(n_sim)])
    p95 = float(np.percentile(nulls, 95))
    pass1 = (ci_a[0] <= 0 <= ci_a[1]) and (ci_b[0] <= 1 <= ci_b[1])
    return {
        "n": len(y), "n_groups": int(ng), "mean_p": float(p.mean()), "mean_y": float(y.mean()),
        "intercept": float(beta[0]), "intercept_ci": ci_a, "slope": float(beta[1]), "slope_ci": ci_b,
        "ece": obs, "ece_null_mean": float(nulls.mean()), "ece_null_p95": p95, "ece_p": float((nulls >= obs).mean()),
        "pass_primary": bool(pass1), "pass_secondary": bool(obs <= p95), "passes": bool(pass1),
    }


def match_bootstrap(df, stat_fn, match_col="match_id", n=2000, seed=0, ci=(2.5, 97.5)):
    """Resample whole matches (rows of a match stay together); stat_fn(df) -> float. Returns (estimate, lo, hi, n_matches).
    Default ci is the two-sided 95% interval (2.5, 97.5)."""
    return _block_bootstrap(df, stat_fn, [match_col], n, seed, ci)


def season_block_bootstrap(df, stat_fn, block_cols=("season_year", "competition"), n=2000, seed=0, ci=(2.5, 97.5)):
    """Resample whole season x competition blocks (the dominant error is season-level drift: MEDIUM 4). stat_fn(df) -> float.
    Returns (estimate, lo, hi, n_blocks). Few blocks (4 IPL seasons) means a wide, honest interval; claims need this AND the match bootstrap."""
    return _block_bootstrap(df, stat_fn, list(block_cols), n, seed, ci)


def _block_bootstrap(df, stat_fn, cols, n, seed, ci):
    df = df.reset_index(drop=True)
    idx = list(df.groupby(cols, sort=False).indices.values())
    rng = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        pick = rng.integers(0, len(idx), len(idx))
        out[i] = stat_fn(df.iloc[np.concatenate([idx[j] for j in pick])])
    return float(stat_fn(df)), float(np.percentile(out, ci[0])), float(np.percentile(out, ci[1])), len(idx)


def power_n(effect, sd_of_paired_diff, alpha=0.05, power=0.8):
    """Matches needed to detect a mean paired difference `effect` (two-sided alpha, given power) when the per-match paired
    differences have SD `sd_of_paired_diff`: n = ((z_{1-a/2} + z_power) * sd / effect)^2. Normal approximation."""
    from scipy.stats import norm

    return int(np.ceil(((norm.ppf(1 - alpha / 2) + norm.ppf(power)) * sd_of_paired_diff / abs(effect)) ** 2))


def holm(pvals):
    """Holm step-down adjusted p-values (same order as input). Count EVERY variant tried on the same bench, not just the winners."""
    p = np.asarray(pvals, float)
    o = np.argsort(p)
    adj = np.maximum.accumulate((len(p) - np.arange(len(p))) * p[o])
    out = np.empty(len(p))
    out[o] = np.minimum(adj, 1.0)
    return out
