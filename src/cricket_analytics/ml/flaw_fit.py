"""Flaw hunt, part B: G1-style rolling fits with extra features (one change at a time), cached to data/external/ml/g2_*.parquet.

  python -m cricket_analytics.ml.flaw_fit build            # feature table (G1 columns + flaw-hunt columns) -> flaw_feat.parquet
  python -m cricket_analytics.ml.flaw_fit run NAME [...]   # fit variants (see VARIANTS); NAME 'g1r' = current G1 re-run on the same code path
  python -m cricket_analytics.ml.flaw_fit screen           # inner-fold-only screen of single windows (no test rows touched)

Same recipe as s4b.run_score for G1: global pool, level-relative target (lvl_season), no season_year, iterations by early stopping on
IPL season Y-1, conformal widening from that inner fold. Test rows: IPL Y (rolling 2022-25, seen fold 2026) plus non-IPL men's Y (2024-25).
The locked fresh set (men's non-IPL dated >= 2026-01-01) is removed from the feature table, so it is never read for training or testing.
"""

import json
import sys
import time

import numpy as np
import pandas as pd

from . import direct as D
from . import evaluate as ev
from . import features as F
from . import s4b
from .baselines import usable
from .dataset import OUT_DIR, load

FEAT = OUT_DIR / "flaw_feat.parquet"
YEARS = (2022, 2023, 2024, 2025, 2026)
NONIPL_YEARS = (2024, 2025)
BASE_COLS = s4b.NO_SEASON  # G1 columns
EXTRA = F.MOMENTUM + ["runs_l24", "wk_l24", "runs_l36", "wk_l36"] + F.PAIR + F.RESOURCE + F.VENUE_RECENT
VARIANTS = {
    "g1r": BASE_COLS,
    "f1a": BASE_COLS + ["runs_l6", "wk_l6", "runs_l12", "wk_l12", "runs_l18", "wk_l18"],
    "f1b": [c for c in BASE_COLS if c not in ("runs_l30", "wk_l30")] + ["runs_l18", "wk_l18"],  # l30 replaced by l18 (best single score_val in the screen)
    "f1c": [c for c in BASE_COLS if c not in ("runs_l30", "wk_l30")] + ["runs_l12", "wk_l12"],  # l30 replaced by l12 (best single win_val)
    "f2": BASE_COLS + ["res_left", "pair_balls", "pair_runs", "since_set_out"],
    "f3": BASE_COLS + F.VENUE_RECENT,
    "f4": BASE_COLS + ["pair_balls"],
    "cap1": BASE_COLS,  # diagnostic: same columns, more capacity (see CFG)
    "cap1f": BASE_COLS + ["runs_l6", "wk_l6", "runs_l12", "wk_l12", "runs_l18", "wk_l18", "res_left", "pair_balls", "pair_runs", "since_set_out"],
    "gval": BASE_COLS,  # diagnostic: early stopping on ALL competitions of season Y-1 (not IPL only) -> more rounds if there is signal
    "gvalf": BASE_COLS + ["runs_l6", "wk_l6", "runs_l12", "wk_l12", "runs_l18", "wk_l18", "res_left", "pair_balls", "pair_runs", "since_set_out"],
    "g2": BASE_COLS,  # G2 = G1 recipe + early stopping on ALL competitions of season Y-1 (identical to gval; this one saves the models)
    "gval3": BASE_COLS + F.VENUE_RECENT,
    "gvalf3": BASE_COLS + ["runs_l6", "wk_l6", "runs_l12", "wk_l12", "runs_l18", "wk_l18", "res_left", "pair_balls", "pair_runs", "since_set_out"] + F.VENUE_RECENT,
    "gval1218": [c for c in BASE_COLS if c not in ("runs_l30", "wk_l30")] + ["runs_l12", "wk_l12"],  # window replacement re-tested with the global early-stopping set
    "gval2": BASE_COLS + ["res_left", "pair_balls", "pair_runs", "since_set_out"],
    "gvalw": BASE_COLS + ["runs_l6", "wk_l6", "runs_l12", "wk_l12", "runs_l18", "wk_l18"],
}
# G3 (resources-left features, ml/resources.py). All use the G2 recipe (early stopping on all competitions of season Y-1).
from . import resources as RS

RB, RW = RS.BAT_COLS, RS.BOWL_COLS
R_SETS = {"r1": BASE_COLS + RB, "r2": BASE_COLS + RW, "r3": BASE_COLS + RB + RW}
W_ADD = {"w1": ["runs_l12", "wk_l12"], "w2": ["runs_l6", "wk_l6", "runs_l12", "wk_l12"], "w3": ["lost_l12"]}  # windows on top of a resources set
SRC = ("", "_s2", "_s3", "_s1r")  # strength source suffix: S1 default, S2 prior-season WAR, S3 recency-weighted, s1r = S1 as 1-100 ratings
for _s in SRC:
    for _r, _cols in R_SETS.items():
        VARIANTS[_r + _s] = _cols
        for _w, _add in W_ADD.items():
            VARIANTS[f"{_w}_{_r}{_s}"] = _cols + _add
VARIANTS["g3"] = BASE_COLS  # placeholder, replaced by set_g3()


def set_g3(rname):
    """G3 = the chosen resources variant (saves models to models/g3 and caches g3_{S,W,V}.parquet)."""
    VARIANTS["g3"] = VARIANTS[rname]


def src_of(name):
    return next((x for x in SRC[1:] if name.endswith(x)), "")


def with_resources(feat, src=""):
    """Merge ml/resources.py columns (resources[_s2|_s3|_s1r].parquet) + lost_l12 (strength of batters dismissed in the last 12 balls)."""
    r = pd.read_parquet(OUT_DIR / f"resources{src}.parquet" if src != "_s1r" else OUT_DIR / "resources_s1r.parquet")
    k = ["match_id", "innings", "balls_bowled"]
    feat = feat.merge(r, on=k, how="left")
    feat = feat.sort_values(k, kind="stable")
    lag = feat.groupby(["match_id", "innings"]).bat_out_str.shift(12)
    feat["lost_l12"] = (feat.bat_out_str - lag.fillna(0)).astype("float32")
    return feat


def _is_res(name):
    return name in ("g3",) or name[:1] in ("r", "w") and name[1:2].isdigit()


GVAL = ("g2", "gval", "gvalf", "gval3", "gvalf3", "gval1218", "gval2", "gvalw")
CFG = {"cap1": dict(num_leaves=63, min_child_samples=50, lambda_l2=1.0), "cap1f": dict(num_leaves=63, min_child_samples=50, lambda_l2=1.0)}


def build():
    states, inn = load()
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    s = F.build_features(states, inn, kv, kt)
    s = F.add_flaw_features(s)
    kr, _, _ = F.tune_k_recent(inn, 2022)
    s = s.merge(F.venue_recent(inn, kr), on=["match_id", "innings"], how="left")
    keep = D.META + ["reduced", "balls_left", "runs_needed", "gender"] + F.FEATURES + [c for c in EXTRA if c != "res_left"] + ["res_left"]
    d = s[list(dict.fromkeys(keep))].copy()
    for c in d.select_dtypes("float64"):
        d[c] = d[c].astype("float32")
    d = d[~ev.fresh_holdout_mask(d)].reset_index(drop=True)  # drop the locked fresh set (men's non-IPL >= 2026-01-01); IPL 2026 stays
    d.to_parquet(FEAT)
    print(f"built {d.shape}, k_venue={kv} k_team={kt} k_recent={kr}")
    return d


def win(*ws):
    return [f"{k}_l{w}" for w in ws for k in ("runs", "wk")]


def screen(names=None, years=(2022, 2023, 2024, 2025)):
    """Inner-fold-only screen: validation loss (IPL season Y-1, models trained on seasons < Y-1; no test row is touched) of column sets.
    Returns a DataFrame: score = sum of the three quantile losses (level-relative units), win = chase log loss, mean over folds."""
    feat = load_feat()
    tuned = tuned_cfg()
    base = [c for c in BASE_COLS if c not in win(30)]
    sets = {"l30 (current)": BASE_COLS, **{f"only l{w}": base + win(w) for w in (6, 12, 18, 24, 36)},
            "l6+l12+l18+l30": BASE_COLS + win(6, 12, 18), "l12+l30": BASE_COLS + win(12), "none": base}
    rows = []
    for nm, cols in sets.items():
        if names and nm not in names:
            continue
        sc, wl = [], []
        for Y in years:
            t = tuned[str(Y)]
            itr, iw, val = s4b._inner(feat, Y)
            m = D.fit_score(itr, iw, cols, D.CONFIGS[t["score_cfg"]], val=val, scale="lvl_season")
            sc.append(sum(m[q][0].best_score["valid_0"]["quantile"] for q in D.QS))
            b, _ = D.fit_win(itr, iw, cols, D.CONFIGS[t["win_cfg"]], val=val)
            wl.append(b.best_score["valid_0"]["binary_logloss"])
        rows.append({"set": nm, "score_val": np.mean(sc), "win_val": np.mean(wl), **{f"s{Y}": x for Y, x in zip(years, sc)}})
        print(rows[-1], flush=True)
    return pd.DataFrame(rows)


def load_feat():
    return pd.read_parquet(FEAT)


def tuned_cfg():
    t = json.loads((OUT_DIR / "direct_tuned.json").read_text())
    t.update(json.loads((OUT_DIR / "holdout_tuned.json").read_text()))
    return t


def test_rows(feat, Y):
    """IPL Y always; non-IPL men's Y for NONIPL_YEARS."""
    m = (feat.season_year == Y) & (feat.competition == "ipl")
    if Y in NONIPL_YEARS:
        m |= (feat.season_year == Y) & (feat.competition != "ipl")
    return usable(feat[m])


def run_variant(feat, name, cols, years=YEARS, save=None):
    """Returns (S, W, V): first-innings quantiles (raw, with conformal widening in columns c10/c90), chase p, inner-fold validation rows."""
    tuned = tuned_cfg()
    S, W, V = [], [], []
    for Y in years:
        t = tuned[str(Y)]
        tr, w = D.pool_rows(feat, "global", Y)
        itr, iw, val = s4b._inner(feat, Y)
        if name in GVAL or _is_res(name):
            val = feat[(feat.season_year == Y - 1) & (feat.balls_bowled % 2 == 0)]
        cfg, cw = ({**D.CONFIGS[t[k]], **CFG.get(name, {})} for k in ("score_cfg", "win_cfg"))
        inner = D.fit_score(itr, iw, cols, cfg, val=val, scale="lvl_season")
        sm = D.fit_score(tr, w, cols, cfg, rounds={q: inner[q][1] for q in D.QS}, scale="lvl_season")
        wi, n = D.fit_win(itr, iw, cols, cw, val=val)
        wm, _ = D.fit_win(tr, w, cols, cw, rounds=n)
        test = test_rows(feat, Y)
        t1, t2 = test[test.innings == 1], D.win_rows(test)
        v1 = usable(val)
        v1 = v1[v1.innings == 1]
        meta = D.META
        s = t1[meta].assign(model=name, fold=Y, **D.predict_score(sm, t1, cols, scale="lvl_season"))
        v = v1[meta].assign(model=name, fold=Y, **D.predict_score(inner, v1, cols, scale="lvl_season"))
        dl = D.conformal_delta(v.final_total, v.q10, v.q90, D.over_bucket(v.balls_bowled))
        lo, hi = D.conformal_apply(s.q10, s.q50, s.q90, D.over_bucket(s.balls_bowled), dl)
        S.append(s.assign(q10=np.asarray(lo), q90=np.asarray(hi)))
        V.append(v)
        W.append(t2[meta].assign(model=name, fold=Y, p=wm.predict(t2[cols])))
        if save:
            for q in D.QS:
                sm[q][0].save_model(str(save / f"{name}_{Y}_score_q{int(q * 100)}.txt"), num_iteration=sm[q][1])
            wm.save_model(str(save / f"{name}_{Y}_win.txt"))
            (save / f"{name}_{Y}_conformal.json").write_text(json.dumps({"delta": dl, "iters": {str(q): inner[q][1] for q in D.QS}, "win_iters": n, "cols": cols}))
        print(f"  {name} fold {Y} done (train rows {len(tr)}, rounds q10/q50/q90 {[inner[q][1] for q in D.QS]}, win {n})", flush=True)
    return pd.concat(S), pd.concat(W), pd.concat(V)


def run(names):
    t0 = time.time()
    feat = load_feat()
    base, cache = feat, {}
    for name in names:
        if _is_res(name):
            sr = src_of(name)
            if sr not in cache:
                cache.clear()
                cache[sr] = with_resources(base, sr)
            feat = cache[sr]
        p = OUT_DIR / f"g2_{name}_S.parquet"
        if p.exists():
            continue
        cols = VARIANTS[name]
        save = None
        if name in ("g2", "g3"):
            save = D.MODEL_DIR / name
            save.mkdir(parents=True, exist_ok=True)
        S, W, V = run_variant(feat, name, cols, save=save)
        S.to_parquet(p)
        W.to_parquet(OUT_DIR / f"g2_{name}_W.parquet")
        V.to_parquet(OUT_DIR / f"g2_{name}_V.parquet")
        if name == "g3":
            for k, d in zip("SWV", (S, W, V)):
                d.to_parquet(OUT_DIR / f"g3_{k}.parquet")
        print(f"[{time.time() - t0:5.0f}s] {name} done", flush=True)




# ---------- comparison vs the control ----------
HEAD = ["collapse 2wk/12b", "collapse 3wk/12b", "collapse 3wk/18b", "collapse 2wk/24b", "burst >=28r/12b", "burst >=39r/18b",
        "death start, >=6 wkts in hand", "late, >=7 wkts in hand", "late, <=4 wkts in hand", "chase rrr >= 13", "new pair (both <6 faced)",
        "slow middle (ov 7-12 < 7/over)"]


def _cut(S, W, scope):
    """scope: 'ipl' (IPL 2022-25), 'ipl26' (IPL 2026, seen fold) or 'non' (non-IPL men's 2024-25)."""
    if scope == "ipl":
        f = lambda d: d[(d.competition == "ipl") & d.fold.between(2022, 2025)]  # noqa: E731
    elif scope == "ipl26":
        f = lambda d: d[(d.competition == "ipl") & (d.fold == 2026)]  # noqa: E731
    else:
        f = lambda d: d[d.competition != "ipl"]  # noqa: E731
    return f(S), f(W)


def overall(name, ctl="g1r", scopes=("ipl", "ipl26", "non")):
    """Per scope: the variant's metrics, and paired-bootstrap differences (variant minus control) over matches. Win metrics use all chase states."""
    out = []
    S, W, _ = (pd.read_parquet(OUT_DIR / f"g2_{n}_{k}.parquet") for n in (name,) for k in "SWV")
    S0, W0, _ = (pd.read_parquet(OUT_DIR / f"g2_{n}_{k}.parquet") for n in (ctl,) for k in "SWV")
    for sc in scopes:
        s, w = _cut(S, W, sc)
        s0, w0 = _cut(S0, W0, sc)
        m = D.summarise(s, w).iloc[0].to_dict()
        r = {"variant": name, "scope": sc, "n_inn1": s.groupby("match_id").ngroups, "MAE": m["MAE"], "pinball": m["pinball"], "cov80": m["cov80"],
             "bias": m["bias"], "ll": m["ll"], "ece": m["ece"]}
        for k, lab in (("mae", "dMAE"), ("pin", "dpin"), ("cov", "dcov")):
            x = D.boot_diff(s, s0, k)
            r.update({lab: x[0], lab + "_lo": x[1], lab + "_hi": x[2]})
        x = D.boot_diff(w, w0, "ll")
        r.update({"dll": x[0], "dll_lo": x[1], "dll_hi": x[2]})
        out.append(r)
    return pd.DataFrame(out)


def events_for(name, B=1000):
    from . import flaw_tests as T

    e = T.load_events()
    res = T.run_battery({name: T.g_frames(name)}, e, B=B)
    return res


def event_summary(res, name):
    """Headline events as one row per (group, kind): excess bias; plus the number of significant biases and mean |z| over ALL events."""
    r = res[res.model == name].assign(sig=lambda d: (d.bias_lo > 0) | (d.bias_hi < 0))
    out = {}
    for (g, k), d in r.groupby(["group", "kind"]):
        sc = 1 if k == "inn1" else 100
        for _, x in d[d.event.isin(HEAD)].iterrows():
            out[(x.event, f"{g}/{k}")] = x.bias_diff * sc
        out[("# significant / total", f"{g}/{k}")] = f"{int(d.sig.sum())}/{len(d)}"
        out[("mean |excess| (all events)", f"{g}/{k}")] = (d.bias_diff.abs() * sc).mean()
    return pd.Series(out)


def compare(names, B=1000, ctl="g1r"):
    """Print overall metrics (+ paired differences vs g1r) and headline event excess biases for each variant; save csv."""
    pd.set_option("display.width", 250)
    ov, ev_ = [], {}
    for n in [ctl] + list(names):
        ov.append(overall(n, ctl))
        ev_[n] = event_summary(events_for(n, B), n)
    ov = pd.concat(ov)
    ov.to_csv(OUT_DIR / "flaw_overall.csv", index=False)
    et = pd.DataFrame(ev_)
    et.to_csv(OUT_DIR / "flaw_events_variants.csv")
    for sc, d in ov.groupby("scope"):
        print(f"\n### overall, scope {sc}\n" + d.drop(columns="scope").round(3).to_string(index=False))
    print("\n### headline event excess bias (runs for inn1, pp for chase)\n" + et.to_string(float_format=lambda x: f"{x:+.1f}"))


def blend_compare(name, ctl="g1r", B=1000):
    """The 50/50 blend with sim-B at the checkpoints (36/60/90 balls): metrics of blend(name) vs blend(ctl), paired over matches, plus event excess."""
    from . import flaw_tests as T

    ss, sw = T.simb_frames()
    fr = {}
    for n in (ctl, name):
        gs, gw = T.g_frames(n)
        cp = lambda d: d[d.balls_bowled.isin(T.CHECKPOINTS)]  # noqa: E731
        fr[n] = (T.blend(cp(gs), ss, "score"), T.blend(cp(gw), sw, "win"))
    rows = []
    for sc in ("ipl", "ipl26", "non"):
        a, b = _cut(*fr[name], sc), _cut(*fr[ctl], sc)
        m = D.summarise(a[0].assign(model="x"), a[1].assign(model="x")).iloc[0]
        r = {"scope": sc, "n_inn1": a[0].match_id.nunique(), "MAE": m["MAE"], "pinball": m["pinball"], "cov80": m["cov80"], "ll": m["ll"], "ece": m["ece"]}
        for k, lab in (("mae", "dMAE"), ("pin", "dpin"), ("cov", "dcov")):
            x = D.boot_diff(a[0], b[0], k)
            r.update({lab: x[0], lab + "_lo": x[1], lab + "_hi": x[2]})
        x = D.boot_diff(a[1], b[1], "ll")
        r.update({"dll": x[0], "dll_lo": x[1], "dll_hi": x[2]})
        rows.append(r)
    ov = pd.DataFrame(rows)
    e = T.load_events()
    res = T.run_battery({f"ens-{ctl}": fr[ctl], f"ens-{name}": fr[name]}, e, B=B)
    return ov, pd.DataFrame({n: event_summary(res, f"ens-{n}") for n in (ctl, name)})


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build()
    elif a[:1] == ["run"]:
        names = [x for x in a[1:] if not x.startswith("g3=")]
        for x in a[1:]:
            if x.startswith("g3="):
                set_g3(x[3:])
        run(names)
    elif a[:1] == ["compare"]:
        compare([x for x in a[1:] if not x.startswith("ctl=")], ctl=next((x[4:] for x in a[1:] if x.startswith("ctl=")), "g1r"))
    elif a[:1] == ["blend"]:
        o, e_ = blend_compare(a[1], a[2] if len(a) > 2 else "g1r")
        print(o.round(3).to_string(index=False))
        print(e_.to_string(float_format=lambda x: f"{x:+.1f}"))
    elif a[:1] == ["screen"]:
        screen().to_csv(OUT_DIR / "flaw_screen_windows.csv", index=False)
