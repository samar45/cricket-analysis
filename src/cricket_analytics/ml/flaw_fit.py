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
    "f2": BASE_COLS + ["res_left", "pair_balls", "pair_runs", "since_set_out"],
    "f3": BASE_COLS + F.VENUE_RECENT,
    "f4": BASE_COLS + ["pair_balls"],
}


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
        cfg, cw = D.CONFIGS[t["score_cfg"]], D.CONFIGS[t["win_cfg"]]
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
        print(f"  {name} fold {Y} done (train rows {len(tr)})", flush=True)
    return pd.concat(S), pd.concat(W), pd.concat(V)


def run(names):
    t0 = time.time()
    feat = load_feat()
    for name in names:
        p = OUT_DIR / f"g2_{name}_S.parquet"
        if p.exists():
            continue
        cols = VARIANTS[name]
        save = None
        if name == "g2":
            save = D.MODEL_DIR / "g2"
            save.mkdir(parents=True, exist_ok=True)
        S, W, V = run_variant(feat, name, cols, save=save)
        S.to_parquet(p)
        W.to_parquet(OUT_DIR / f"g2_{name}_W.parquet")
        V.to_parquet(OUT_DIR / f"g2_{name}_V.parquet")
        print(f"[{time.time() - t0:5.0f}s] {name} done", flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build()
    elif a[:1] == ["run"]:
        run(a[1:])
    elif a[:1] == ["screen"]:
        screen().to_csv(OUT_DIR / "flaw_screen_windows.csv", index=False)
