"""Flaw hunt plots and feature importance: python -m cricket_analytics.ml.flaw_plot"""

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import evaluate as ev
from . import flaw_fit as FF
from . import flaw_tests as T
from .dataset import OUT_DIR


def g1_vs_g2(path=ev.IMG_DIR / "ml_flaw_g1_vs_g2.png", B=1000):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    e = T.load_events()
    res = T.run_battery({"G1": T.g_frames("g1r"), "G2": T.g_frames("g2")}, e, B=B)
    res.to_csv(OUT_DIR / "flaw_battery_g1_g2.csv", index=False)
    fig, axs = plt.subplots(2, 2, figsize=(13, 8.5), sharey=True)
    for ax, (g, k) in zip(axs.ravel(), (("IPL", "inn1"), ("nonIPL", "inn1"), ("IPL", "chase"), ("nonIPL", "chase"))):
        r = res[(res.group == g) & (res.kind == k) & res.event.isin(FF.HEAD)]
        sc = 1 if k == "inn1" else 100
        ev_names = [x for x in FF.HEAD if x in set(r.event)]
        for j, (m, c) in enumerate((("G1", "tab:blue"), ("G2", "tab:orange"))):
            x = r[r.model == m].set_index("event").loc[ev_names]
            y = np.arange(len(ev_names)) + (j - 0.5) * 0.3
            ax.errorbar(x.bias_diff * sc, y, xerr=[(x.bias_diff - x.bias_lo) * sc, (x.bias_hi - x.bias_diff) * sc], fmt="o", ms=3, lw=1, color=c, label=m)
        ax.axvline(0, color="grey", ls="--")
        ax.set_yticks(range(len(ev_names)))
        ax.set_yticklabels(ev_names, fontsize=7)
        ax.set_title(f"{g}, {'first innings (runs)' if k == 'inn1' else 'chase (win prob points)'}: excess bias at events", fontsize=9)
    axs[0, 0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def importance(prefix, years, top=15):
    """Mean share of gain per feature over folds: q50 score model and chase classifier."""
    out = {}
    for lab, pat in (("score q50", "{p}_{y}_score_q50.txt"), ("chase win", "{p}_{y}_win.txt")):
        d = []
        for y in years:
            f = FF.D.MODEL_DIR / prefix.split("_")[0] / pat.format(p=prefix.split("_")[1] if "_" in prefix else prefix, y=y)
            b = lgb.Booster(model_file=str(f))
            g = pd.Series(b.feature_importance("gain"), index=b.feature_name())
            d.append(g / g.sum())
        out[lab] = pd.concat(d, axis=1).mean(axis=1).sort_values(ascending=False).head(top)
    return out


if __name__ == "__main__":
    g1_vs_g2()
    for name, pre in (("G1 (v1)", "g1_g1"), ("G2", "g2_g2")):
        imp = importance(pre, (2022, 2023, 2024, 2025))
        for k, s in imp.items():
            print(f"\n{name} {k}: " + ", ".join(f"{i} {v * 100:.1f}%" for i, v in s.items()))
