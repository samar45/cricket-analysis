"""worth_plus vs worth: pooled 2024-26 backtest (total, bowl_rate), paired bootstrap of the difference, XII-level test.
Run: .venv\Scripts\python experiments\worth_plus_backtest.py   (needs data/external/commentary/parsed_ipl_*.csv; DB read-only)"""
import numpy as np
import pandas as pd

from cricket_analytics.models import backtest as B
from cricket_analytics.models import xii_basis as XB

NAMES = ("worth", "worth_plus", "worth_plus3", "worth2", "recent_value", "ipl3")
TARGETS = (2024, 2025, 2026)


def paired(a: str, b: str, what: str, boot: int = 1000):
    """Pooled spearman(b) - spearman(a) on the same players, with a 5-95% bootstrap range (players resampled)."""
    T = B.tables()
    xs, ys, zs = [], [], []
    for t in TARGETS:
        truth = B.truth_runs(T, t)
        pa, pb = (B.PREDICTORS[n][0](T[T.sy <= t - 1], t - 1, {}) for n in (a, b))
        xa, y, pl = B._pairs(pa, truth, what, B.MIN_BALLS)
        xb, _, _ = B._pairs(pb.reindex(pa.index), truth, what, B.MIN_BALLS)
        m = ~(np.isnan(xa) | np.isnan(xb))
        xs.append(xa[m]), ys.append(y[m]), zs.append(xb[m])
    x, y, z = map(np.concatenate, (xs, ys, zs))
    rho = lambda u, i: np.corrcoef(pd.Series(u[i]).rank(), pd.Series(y[i]).rank())[0, 1]  # noqa: E731
    rng, full = np.random.default_rng(1), np.arange(len(y))
    d = [rho(z, i) - rho(x, i) for i in (rng.integers(0, len(y), len(y)) for _ in range(boot))]
    return len(y), rho(x, full), rho(z, full), rho(z, full) - rho(x, full), np.percentile(d, [5, 95])


if __name__ == "__main__":
    res = B.run(names=NAMES, targets=TARGETS, whats=("total", "bowl_rate"))
    for w in ("total", "bowl_rate"):
        print(w)
        print(B.table(res, w).to_string())
        print(res[(res.target == "pooled") & (res.what == w)][["predictor", "n", "spearman", "lo", "hi"]].round(3).to_string(index=False))
    for p in ("worth_plus", "worth_plus3"):
        for w in ("total", "bowl_rate"):
            n, ra, rb, dd, (lo, hi) = paired("worth", p, w)
            print(f"{p} - worth on {w}: n={n} {ra:+.3f} -> {rb:+.3f}, diff {dd:+.3f} (5-95% {lo:+.3f}..{hi:+.3f})")
    bases = ("worth_plus", "worth_plus3")
    d = XB.xii_test(0.5, TARGETS, bases)
    print(XB.summary(d, bases).to_string(index=False))
