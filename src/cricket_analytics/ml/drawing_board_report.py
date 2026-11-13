"""Drawing board report: paired comparison of cached db_* models against the G2 control on identical states, plus the event battery and plots.

  python -m cricket_analytics.ml.drawing_board_fit report [names ...]      (default: all db_*_S.parquet except oof)
"""

import numpy as np
import pandas as pd

from . import direct as D
from . import drawing_board as B
from . import evaluate as ev
from . import flaw_fit as FF
from . import flaw_tests as T
from .dataset import OUT_DIR

KEY = B.KEY


def scoped(S, W, meta):
    return B.scope_of(S, meta), B.scope_of(W, meta)


def load_models(names, meta):
    fr = {}
    for n in names:
        S, W = B.cached_frames(n)
        fr[n] = scoped(S, W, meta)
    return fr


def reference_frames(meta):
    """G1 (g1r cache), G2 (g2 cache) and the v1 blend are used as references; all cut to over-end states."""
    fr = {}
    for nm, cn in (("G1", "g1r"), ("G2-orig", "g2")):
        S, W = B.cache_frames(cn, meta)
        fr[nm] = scoped(S, W, meta)
    return fr


def v1_blend(meta, g="g1r"):
    """ens-G1 = 50/50 blend of G1 and sim-B at the checkpoints (the v1 model), all scopes."""
    m = T.models(g)
    S, W = m["ens-G1"]
    return B.scope_of(S, meta), B.scope_of(W, meta)


def to_checkpoints(fr):
    return {n: (S[S.balls_bowled.isin(B.CKPT)], W[W.balls_bowled.isin(B.CKPT)]) for n, (S, W) in fr.items()}


def summary(res, models):
    """Per model: number of significant event biases / total, and mean |excess| (runs for innings 1, pp for chase), by group/kind."""
    rows = {}
    for m in models:
        rows[m] = FF.event_summary(res, m)
    t = pd.DataFrame(rows)
    return t[t.index.get_level_values(0).isin(["# significant / total", "mean |excess| (all events)"])]


def fmt_paired(p):
    out = []
    for r in p.itertuples():
        f = lambda v, lo, hi, nd=2: f"{v:+.{nd}f} [{lo:+.{nd}f}, {hi:+.{nd}f}]{'*' if (lo > 0 or hi < 0) else ''}"  # noqa: E731
        out.append({"model": r.model, "scope": r.scope, "dMAE": f(r.dmae, r.dmae_lo, r.dmae_hi), "dpinball": f(r.dpin, r.dpin_lo, r.dpin_hi, 3),
                    "dbias": f(r.dbias, r.dbias_lo, r.dbias_hi), "dcov80": f(r.dcov, r.dcov_lo, r.dcov_hi, 3), "dLL": f(r.dll, r.dll_lo, r.dll_hi, 3)})
    return pd.DataFrame(out)


def report(names=None, ref="g2oe", Bn=500):
    pd.set_option("display.width", 280)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_colwidth", 60)
    names = names or sorted(p.name[3:-6] for p in OUT_DIR.glob("db_*_S.parquet") if p.name[3:-6] not in ("oof", "d1", "g2oe"))
    names = [ref] + [n for n in names if n != ref]
    meta = B.meta_table()
    fr = load_models(names, meta)
    fr.update(reference_frames(meta))
    fr = B.common(fr)  # identical states for all models
    n_s = {sc: fr[ref][0][fr[ref][0].scope == sc].match_id.nunique() for sc in B.SCOPES}
    print("matches in first-innings frames per scope:", n_s, " rows:", len(fr[ref][0]), len(fr[ref][1]))
    mt = B.metrics_by_scope(fr)
    print("\n### overall metrics on identical over-end states\n" + mt.round(3).to_string(index=False))
    mt.to_csv(OUT_DIR / "db_report_metrics.csv", index=False)
    p = B.paired(fr, ref)
    p.to_csv(OUT_DIR / "db_report_paired.csv", index=False)
    print(f"\n### paired differences vs {ref} (model minus {ref}; negative = better for MAE, pinball, LL; * = interval excludes 0)\n" + fmt_paired(p).to_string(index=False))
    # event battery
    res = B.battery(fr, Bn)
    res.to_csv(OUT_DIR / "db_report_battery.csv", index=False)
    print("\n### event excess biases (runs inn1, pp chase)\n" + B.headline(res, heads=B.HEAD[:8] + ["chase rrr >= 13"]).to_string())
    print("\n### significant / mean |excess| over all events\n" + summary(res, list(fr)).to_string())
    # vs the v1 blend at checkpoints
    bl = {"v1-blend": v1_blend(meta)}
    cp = to_checkpoints({**{n: fr[n] for n in fr}, **bl})
    cp = B.common(cp)
    p2 = B.paired(cp, "v1-blend")
    print("\n### paired differences vs the v1 blend (ens-G1) at the 3 checkpoints (6/10/15 overs)\n" + fmt_paired(p2).to_string(index=False))
    p2.to_csv(OUT_DIR / "db_report_vs_blend.csv", index=False)
    return fr, mt, p, res


def plots():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = pd.read_csv(OUT_DIR / "db_d1_slopes_all.csv")
    t = t[t.ckpt == "all"]
    models = list(dict.fromkeys(t.model))  # note: slope CIs for the baselines were drawn from the D1 run
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for ax, kind, lab in ((axs[0], "score", "first-innings OLS slope (actual on predicted median)"), (axs[1], "win", "chase calibration slope (logit actual on logit p)")):
        for j, sc in enumerate(("ipl", "non")):
            d = t[(t.kind == kind) & (t.scope == sc)].set_index("model").reindex(models).dropna(subset=["slope"])
            x = np.arange(len(d)) + (j - 0.5) * 0.25
            ax.errorbar(x, d.slope, yerr=[(d.slope - d.lo).clip(lower=0), (d.hi - d.slope).clip(lower=0)], fmt="o", ms=4, label=sc, lw=1)
        ax.axhline(1, color="grey", ls="--")
        ax.set_xticks(range(len(models)))
        ax.set_xticklabels(models, rotation=30, fontsize=8)
        ax.set(title=lab, ylim=(0.6, 1.5) if kind == "win" else (0.85, 1.4))
        ax.legend(fontsize=7)
    fig.suptitle("Slope 1 = calibrated; >1 = predictions compressed toward the mean (under-reacting)", fontsize=9)
    fig.tight_layout()
    fig.savefig(ev.IMG_DIR / "ml_db_calibration_slope.png", dpi=110)
    plt.close(fig)
    d = pd.read_csv(OUT_DIR / "db_d1_deciles_all.csv")
    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for ax, kind in zip(axs, ("score", "win")):
        for m in ("G1", "g2oe", "m2", "b2", "resource"):
            x = d[(d.kind == kind) & (d.model == m) & (d.scope == "non")]
            ax.plot(x.pred, x.actual, "o-", ms=3, label=m)
        lo, hi = ax.get_xlim()
        ax.plot([lo, hi], [lo, hi], color="grey", ls="--")
        ax.set(title=f"{'first-innings final total' if kind == 'score' else 'chase win rate'} by prediction decile (non-IPL men's 2024-25)", xlabel="mean predicted", ylabel="mean actual")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(ev.IMG_DIR / "ml_db_deciles.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["plots"]:
        plots()
    else:
        report(sys.argv[1:] or None)
