"""Model-zoo report: one big comparison table (every model family on identical states), paired bootstrap vs the G2 control, event battery, plot.

  python -m cricket_analytics.ml.model_zoo report            # all zoo models (z1..z6, zb_*) + reference models
"""

import json

import numpy as np
import pandas as pd

from . import drawing_board as B
from . import drawing_board_report as R
from . import evaluate as ev
from . import flaw_fit as FF
from .dataset import OUT_DIR

REFS = ["g2oe", "m1", "m2", "m3", "b2", "b23"]
LABEL = {"g2oe": "G2 LightGBM (control)", "G1": "G1 LightGBM", "resource": "Resource table (baseline)", "sim-B": "sim-B simulator", "v1-blend": "v1 ens-G1 (G1 + sim-B)",
         "m1": "k-NN (M1)", "m2": "Spline GAM (M2)", "m3": "MLP (M3)", "b2": "b2 = G2 + GAM", "b23": "b23 = G2 + GAM + MLP",
         "z1": "Z1 XGBoost", "z2": "Z2 CatBoost", "z3": "Z3 RandomForest", "z4": "Z4 ExtraTrees", "z5": "Z5 HistGradientBoosting", "z6": "Z6 GRU (ball sequence)"}
CK = {"mae6": 36, "mae10": 60, "mae15": 90}


def _stats(S, W, sc):
    s, w = S[(S.scope == sc) & (S.innings == 1)], W[W.scope == sc]
    r = {f"{sc.upper()}_MAE@{k[3:]}": ev.mae(s[s.balls_bowled == b].final_total, s[s.balls_bowled == b].q50) for k, b in CK.items()}
    for ov, b in ((10, 60), (15, 90)):
        x = w[w.balls_bowled == b]
        r[f"{sc.upper()}_acc@{ov}"] = float(((x.p > 0.5) == (x.chase_won > 0.5)).mean()) if len(x) else np.nan
    return r


def table(fr, ev_res=None, times=None):
    mt = B.metrics_by_scope({n: v for n, v in fr.items()}).set_index(["model", "scope"])
    rows = []
    for n, (S, W) in fr.items():
        r = {"model": n}
        ip, no = (mt.loc[(n, sc)] if (n, sc) in mt.index else None for sc in ("ipl", "non"))
        r.update(_stats(S, W, "ipl"))
        r.update({"IPL_MAE": ip.MAE, "IPL_pinball": ip.pinball, "IPL_cov80": ip.cov80, "IPL_chase_LL": ip.ll, "IPL_ECE": ip.ece, "nonIPL_MAE": no.MAE, "nonIPL_LL": no.ll, "nonIPL_ECE": no.ece})
        if ev_res is not None and n in set(ev_res.model):
            c = ev_res[(ev_res.model == n) & (ev_res.event == "collapse 3wk/12b") & (ev_res.group == "nonIPL") & (ev_res.kind == "inn1")]
            r["collapse_bias"] = float(c.bias_diff.iloc[0]) if len(c) else np.nan
            es = FF.event_summary(ev_res, n)
            m = lambda g: float(es[("mean |excess| (all events)", g)]) if ("mean |excess| (all events)", g) in es.index else np.nan  # noqa: E731
            r["events_inn1"] = np.nanmean([m("IPL/inn1"), m("nonIPL/inn1")])
            r["events_chase_pp"] = np.nanmean([m("IPL/chase"), m("nonIPL/chase")])
        t = (times or {}).get(n, {})
        r["train_s_per_fold"], r["predict_us_per_state"] = t.get("train_s_per_fold"), (t.get("predict_us_per_state") or None)
        rows.append(r)
    return pd.DataFrame(rows)


def fmt_md(t):
    cols = [("IPL_MAE@6", 2), ("IPL_MAE@10", 2), ("IPL_MAE@15", 2), ("IPL_pinball", 3), ("IPL_cov80", 3), ("IPL_acc@10", 3), ("IPL_acc@15", 3), ("IPL_chase_LL", 3), ("IPL_ECE", 3),
            ("nonIPL_MAE", 2), ("nonIPL_LL", 3), ("collapse_bias", 1), ("events_inn1", 2), ("events_chase_pp", 2), ("train_s_per_fold", 0), ("predict_us_per_state", 1)]
    head = "| model | " + " | ".join(c for c, _ in cols) + " |\n|" + "---|" * (len(cols) + 1)
    out = [head]
    for _, r in t.iterrows():
        cells = []
        for c, nd in cols:
            v = r.get(c, np.nan)
            cells.append("-" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}")
        out.append(f"| {LABEL.get(r["model"], r["model"])} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def report(names=None, Bn=300):
    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    zoo = names or sorted(p.name[3:-10] for p in OUT_DIR.glob("db_z*_S.parquet"))
    meta = B.meta_table()
    fr = R.load_models(REFS + zoo, meta)
    ref = R.reference_frames(meta)
    fr["G1"] = ref["G1"]
    feat = B.load_feat(None, even=True)
    for k, v in B.baseline_frames(feat).items():
        if k == "resource":
            fr["resource"] = (B.scope_of(v[0], meta), B.scope_of(v[1], meta))
    del feat
    fr = B.common(fr)
    print("states:", len(fr["g2oe"][0]), len(fr["g2oe"][1]), flush=True)
    times = json.loads((OUT_DIR / "zoo_times.json").read_text()) if (OUT_DIR / "zoo_times.json").exists() else {}
    res = B.battery(fr, Bn)
    res.to_csv(OUT_DIR / "zoo_battery.csv", index=False)
    t = table(fr, res, times)
    # checkpoint-only table (adds sim-B and the v1 blend, which exist only at 6/10/15 overs)
    cp = R.to_checkpoints(fr)
    ss, sw = B.simb_scoped()
    cp["sim-B"] = (B.scope_of(ss, meta), B.scope_of(sw, meta))
    cp["v1-blend"] = R.v1_blend(meta)
    cp = {n: (S[S.balls_bowled.isin(B.CKPT)], W[W.balls_bowled.isin(B.CKPT)]) for n, (S, W) in cp.items()}
    cp = B.common(cp)
    tc = table(cp, None, times)
    tc.to_csv(OUT_DIR / "zoo_table_ckpt.csv", index=False)
    t.to_csv(OUT_DIR / "zoo_table.csv", index=False)
    # paired vs G2
    p = B.paired(fr, "g2oe")
    p.to_csv(OUT_DIR / "zoo_paired.csv", index=False)
    pc = B.paired(cp, "g2oe")
    pc.to_csv(OUT_DIR / "zoo_paired_ckpt.csv", index=False)
    print("\n### main table (over-end states, identical for every model)\n" + fmt_md(t))
    print("\n### checkpoint-only table (6/10/15 overs; adds sim-B and v1 blend)\n" + fmt_md(tc[tc.model.isin(["sim-B", "v1-blend", "g2oe", "b2"])]))
    print("\n### paired vs G2 (model minus G2, 5-95% over matches; * = excludes 0)\n" + R.fmt_paired(p).to_string(index=False))
    print("\n### paired vs G2 at checkpoints, sim-B / v1\n" + R.fmt_paired(pc[pc.model.isin(["sim-B", "v1-blend"])]).to_string(index=False))
    p2 = paired2(fr)
    p2.to_csv(OUT_DIR / "zoo_paired2.csv", index=False)
    print("\n### paired vs G2, 90% and 95% two-sided intervals\n" + p2.round(3).to_string(index=False))
    plot(t)
    return t, p


def paired2(fr, ref="g2oe", n=1000, seed=0):
    """Paired bootstrap over matches (model - ref), both 5-95% and 95% two-sided (2.5-97.5%) intervals, for MAE, pinball (innings 1) and chase log loss."""
    rows = []
    for nm, (S, W) in fr.items():
        if nm == ref:
            continue
        for sc in ("ipl", "non"):
            for kind, a, b, cols in (("MAE", S, fr[ref][0], None), ("pinball", S, fr[ref][0], None), ("LL", W, fr[ref][1], None)):
                A, Bf = a[a.scope == sc], b[b.scope == sc]
                key = ["match_id", "innings", "balls_bowled"]
                A, Bf = A.merge(Bf[key], on=key).sort_values(key), Bf.merge(A[key], on=key).sort_values(key)
                w = ev.match_weights(A)
                if kind == "LL":
                    f = lambda d: -(d.chase_won * np.log(np.clip(d.p, 1e-6, 1 - 1e-6)) + (1 - d.chase_won) * np.log(1 - np.clip(d.p, 1e-6, 1 - 1e-6)))  # noqa: E731
                elif kind == "MAE":
                    f = lambda d: (d.final_total - d.q50).abs()  # noqa: E731
                else:
                    f = lambda d: sum(np.maximum(q * (d.final_total - d[c]), (q - 1) * (d.final_total - d[c])) for q, c in ((0.1, "q10"), (0.5, "q50"), (0.9, "q90"))) / 3  # noqa: E731
                g = pd.DataFrame({"m": A.match_id.to_numpy(), "d": (f(A).to_numpy() - f(Bf).to_numpy()) * w, "w": w}).groupby("m").sum()
                c = np.random.default_rng(seed).multinomial(len(g), np.ones(len(g)) / len(g), size=n)
                d = (c @ g.d.to_numpy()) / (c @ g.w.to_numpy())
                lo5, hi95, lo25, hi975 = np.percentile(d, [5, 95, 2.5, 97.5])
                rows.append({"model": nm, "scope": sc, "metric": kind, "diff": d.mean(), "lo5": lo5, "hi95": hi95, "lo2.5": lo25, "hi97.5": hi975,
                             "sig90": lo5 > 0 or hi95 < 0, "sig95": lo25 > 0 or hi975 < 0})
    return pd.DataFrame(rows)


def plot(t):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1, 3, figsize=(15, 4.6))
    fam = {"z1": "C0", "z2": "C1", "z3": "C2", "z4": "C3", "z5": "C4", "z6": "C5"}
    for ax, (x, y, xl, yl) in zip(axs, (("IPL_MAE", "nonIPL_MAE", "IPL first-innings MAE (runs)", "non-IPL MAE (runs)"), ("IPL_chase_LL", "nonIPL_LL", "IPL chase log loss", "non-IPL chase log loss"),
                                        ("events_inn1", "collapse_bias", "mean |event excess| innings 1 (runs)", "collapse bias, 3 wkts/12 balls (runs)"))):
        for _, r in t.iterrows():
            a, b = getattr(r, x), getattr(r, y)
            if np.isnan(a) or np.isnan(b):
                continue
            ax.scatter(a, b, c=fam.get(r.model.split("_")[0], "grey"), s=40, marker="s" if r.model.startswith("zb") or r.model.startswith("b") else "o")
            ax.annotate(LABEL.get(r.model, r.model).split(" ")[0] if r.model not in ("g2oe",) else "G2", (a, b), fontsize=7, xytext=(3, 3), textcoords="offset points")
        ax.set(xlabel=xl, ylabel=yl)
    fig.suptitle("Model zoo on identical out-of-sample over-end states (lower left = better; squares = blends)", fontsize=10)
    fig.tight_layout()
    fig.savefig(ev.IMG_DIR / "ml_zoo.png", dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    report()
