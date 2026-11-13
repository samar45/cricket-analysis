"""Fair baselines (F-score, F-chase) against every cached model, per the rule pre-registered in docs/ML_PREDICTION.md section 9
("fair-baseline worker", commit a2c05be).

  python -m cricket_analytics.ml.fair_report fit      # fit F-score / F-chase per fold, cache data/external/ml/fair_*.parquet
  python -m cricket_analytics.ml.fair_report report   # tables + paired intervals + decision rule (reads caches only)

Sets: 'ipl' = IPL 2022-25 rolling, 'non' = men's non-IPL 2024-25 rolling (dev folds, pooled = 'dev');
'ipl26' = IPL 2026 and 'non26' = men's non-IPL 2026-01-01..2026-10-14 (spent sets: reporting only).
Checkpoints 0 / 6 / 10 / 15 overs. Rows dated 2026-10-15 or later are never read (asserted); fresh3/ is never opened.
Everything is read-only apart from data/external/ml/fair_*.
"""

import sys

import numpy as np
import pandas as pd

from . import evaluate as ev
from . import features as F
from . import flaw_tests as T
from .baselines import FChase, LevelResource, md, usable
from .dataset import OUT_DIR
from .validate import CP, ENS1, G1, SIM

KEY = ["match_id", "innings", "balls_bowled"]
QC = ["q10", "q50", "q90"]
CUT = pd.Timestamp("2026-10-15")
P = lambda n: OUT_DIR / f"fair_{n}.parquet"  # noqa: E731
STATE_COLS = ["match_id", "innings", "balls_bowled", "runs", "wickets", "date", "season_year", "competition", "gender", "batting_team", "bowling_team",
              "target", "max_balls", "final_total", "chase_won", "reduced", "balls_left", "runs_needed"]


# ---------- data ----------
def load():
    """States (men's, with the prior-only level lvl_ew) and per-match meta. Refuses rows of the locked fresh set #3."""
    s = pd.read_parquet(OUT_DIR / "states.parquet", columns=STATE_COLS)
    ev.assert_no_fresh3(s, "fair_report")
    assert s.date.max() < CUT, "states contain rows on or after 2026-10-15"
    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet")
    lv = F.innings_features(inn).drop_duplicates("match_id").set_index("match_id").lvl_ew
    s = s[s.gender == "male"].copy()
    s["lvl_ew"] = s.match_id.map(lv).astype(float)
    s["match_id"] = s.match_id.astype(str)
    return s


def fold_models(s, pool, train_mask, val_mask, val_train_mask):
    """Table (+ conformal deltas) and chase model for one fold. train_mask / val_* are row masks of `s`."""
    t = s[train_mask]
    tab = LevelResource(pool).fit(t)
    vt = LevelResource(pool).fit(s[val_train_mask])
    v = usable(s[val_mask & (s.innings == 1) & (s.balls_bowled % 6 == 0)])
    tab.delta = vt.calibrate(v).delta
    return tab, FChase(tab).fit(t)


def predict(tab, ch, test):
    t1 = usable(test[test.innings == 1])
    t2 = usable(test[test.innings == 2])
    t2 = t2[t2.chase_won.notna() & (t2.runs_needed > 0)]
    cols = KEY + ["final_total", "chase_won", "competition", "season_year"]
    S = t1[cols].assign(**tab.score(t1))
    W = t2[cols].assign(p=ch.win(t2).to_numpy())
    return S, W


def fit():
    s = load()
    cp = s.balls_bowled.isin(CP)
    ipl = s.competition == "ipl"
    out = {k: ([], []) for k in ("ipl", "non", "ipl26", "non26")}
    for Y in (2022, 2023, 2024, 2025, 2026):
        key = "ipl" if Y < 2026 else "ipl26"
        tab, ch = fold_models(s, "ipl", ipl & (s.season_year < Y), ipl & (s.season_year == Y - 1), ipl & (s.season_year < Y - 1))
        S, W = predict(tab, ch, s[cp & ipl & (s.season_year == Y)])
        out[key][0].append(S.assign(fold=Y, model="F-score", den=tab.den))
        out[key][1].append(W.assign(fold=Y, model="F-chase"))
        print(Y, "ipl", len(S), len(W), "den", round(tab.den, 1), flush=True)
    for Y in (2024, 2025):
        ni = ~ipl
        tab, ch = fold_models(s, "all", s.season_year < Y, ni & (s.season_year == Y - 1), s.season_year < Y - 1)
        S, W = predict(tab, ch, s[cp & ni & (s.season_year == Y)])
        out["non"][0].append(S.assign(fold=Y, model="F-score", den=tab.den))
        out["non"][1].append(W.assign(fold=Y, model="F-chase"))
        print(Y, "non", len(S), len(W), "den", round(tab.den, 1), flush=True)
    # spent non-IPL set: trained on matches dated before 2026-01-01; inner fold season 2025 (before 2026-01-01), table for it fitted on seasons < 2025
    pre = s.date < pd.Timestamp("2026-01-01")
    tab, ch = fold_models(s, "all", pre, pre & ~ipl & (s.season_year == 2025), s.season_year < 2025)
    keys = pd.concat([pd.read_parquet(OUT_DIR / f"v2_fresh_{k}.parquet")[KEY] for k in "SW"]).drop_duplicates()
    keys = keys.assign(match_id=keys.match_id.astype(str), innings=keys.innings.astype(int), balls_bowled=keys.balls_bowled.astype(int))
    test = s[cp].merge(keys.assign(_k=1), on=KEY, how="inner").drop(columns="_k")
    assert (test.date >= pd.Timestamp("2026-01-01")).all() and (test.date < CUT).all() and (test.competition != "ipl").all()
    S, W = predict(tab, ch, test)
    out["non26"][0].append(S.assign(fold=2026, model="F-score", den=tab.den))
    out["non26"][1].append(W.assign(fold=2026, model="F-chase"))
    print("non26", len(S), len(W), flush=True)
    for k, (a, b) in out.items():
        pd.concat(a).to_parquet(P(f"{k}_S"))
        pd.concat(b).to_parquet(P(f"{k}_W"))


# ---------- cached models of the other families, per set ----------
def _cp(d):
    return d[d.balls_bowled.isin(CP)]


def _meta():
    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet", columns=["match_id", "competition", "season_year", "gender", "date"]).drop_duplicates("match_id")
    return inn.assign(match_id=lambda d: d.match_id.astype(str))


def _scope(d, meta):
    m = d[KEY + [c for c in ("final_total", "chase_won", "q10", "q50", "q90", "p") if c in d.columns]].merge(meta, on="match_id", how="left")
    m = m[m.gender == "male"]
    sc = np.where((m.competition == "ipl") & m.season_year.between(2022, 2025), "ipl", np.where((m.competition == "ipl") & (m.season_year == 2026), "ipl26",
                  np.where((m.competition != "ipl") & m.season_year.between(2024, 2025), "non", "")))
    return m.assign(scope=sc)[sc != ""]


def cached():
    """name -> {set -> (S, W)} for G1, G2, b2, sim-B, ens-G1, resource-ipl (dev and IPL 2026) and v1 parts for the spent non-IPL set."""
    meta = _meta()
    out = {}
    gs, gw = T.g_frames("g1r")  # G1 (g1r = conformalised G1), every state; cut to the checkpoints
    d = T._norm(pd.concat([pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet").assign(competition="ipl"), pd.read_parquet(OUT_DIR / "s2_preds_B_men_nonipl.parquet")], ignore_index=True))
    d = d[d.balls_bowled.isin(CP)]  # sim-B at 0 / 6 / 10 / 15 overs (T.simb_frames drops ball 0)
    ks, kw = KEY + ["final_total"] + QC, KEY + ["chase_won", "p"]
    ss = d[d.innings == 1][ks]
    sw = d[(d.innings == 2) & d.chase_won.notna()].rename(columns={"win": "p"})[kw]
    gs, gw = _cp(gs)[ks], _cp(gw)[kw]
    mods = {G1: (gs, gw), SIM: (ss, sw), ENS1: (T.blend(gs, ss, "score")[ks], T.blend(gw, sw, "win")[kw])}
    for nm, (S, W) in mods.items():
        out[nm] = (_scope(S, meta), _scope(W, meta))
    S, W = (T._norm(pd.read_parquet(OUT_DIR / f"g2_g2_{k}.parquet")) for k in "SW")
    out["G2"] = (_scope(_cp(S), meta), _scope(_cp(W), meta))
    S, W = (T._norm(pd.read_parquet(OUT_DIR / f"db_b2_{k}.parquet")) for k in "SW")
    out["b2"] = (_scope(_cp(S), meta), _scope(_cp(W), meta))
    b = pd.concat([pd.read_parquet(OUT_DIR / f) for f in ("direct_baseline_score.parquet", "holdout_base_S.parquet")])
    out["resource-ipl"] = (_scope(_cp(T._norm(b)), meta), None)
    return out, meta


def fresh_non(meta):
    """The spent non-IPL set: v1 parts as stored by the fresh run (v2_fresh_*), men's non-IPL 2026-01-01..2026-10-14."""
    S, W = (pd.read_parquet(OUT_DIR / f"v2_fresh_{k}.parquet") for k in "SW")
    out = {}
    for src, nm in (("v1-G1", G1), ("v1-sim-B", SIM), ("v1-ens", ENS1)):
        s, w = T._norm(S[S.model == src]), T._norm(W[W.model == src])
        out[nm] = (s.merge(meta[["match_id", "competition", "season_year", "date"]], on="match_id").assign(scope="non26"),
                   w.merge(meta[["match_id", "competition", "season_year", "date"]], on="match_id").assign(scope="non26"))
    return out


def build_frames():
    """frames[set][model] = (S, W); sets: ipl, non, ipl26, non26. Adds F-*, mean(F,G1)."""
    cm, meta = cached()
    frames = {sc: {} for sc in ("ipl", "non", "ipl26", "non26")}
    for nm, (S, W) in cm.items():
        for sc in ("ipl", "non", "ipl26"):
            s = S[S.scope == sc]
            w = None if W is None else W[W.scope == sc]
            if len(s):
                frames[sc][nm] = (s, w)
    for nm, v in fresh_non(meta).items():
        frames["non26"][nm] = v
    from . import holdout as H  # the official IPL 2026 v1 frames (conformalised G1, sim-B, ens-G1, resource-ipl) at 0/6/10/15 overs

    hs, hw = H.models()
    frames["ipl26"] = {k: v for k, v in frames["ipl26"].items() if k == "G2"}
    for nm, k in ((G1, G1), (SIM, SIM), (ENS1, ENS1), ("resource-ipl", "resource-ipl")):
        frames["ipl26"][nm] = tuple(_scope(T._norm(x[k]), meta) if x[k] is not None else None for x in (hs, hw))
    for sc in frames:
        fs, fw = pd.read_parquet(P(f"{sc}_S")), pd.read_parquet(P(f"{sc}_W"))
        fs, fw = T._norm(fs).assign(scope=sc), T._norm(fw).assign(scope=sc)
        frames[sc]["F-score"] = (fs, None)
        frames[sc]["F-chase"] = (None, fw)
        if G1 in frames[sc]:
            g = frames[sc][G1][0]
            m = fs[KEY + ["final_total", "q10", "q50", "q90", "competition", "season_year"]].merge(g[KEY + QC], on=KEY, suffixes=("", "_g"))
            q = np.sort((m[QC].to_numpy() + m[[c + "_g" for c in QC]].to_numpy()) / 2, axis=1)
            frames[sc]["mean(F,G1)"] = (m[[c for c in m.columns if not c.endswith("_g")]].assign(**dict(zip(QC, q.T)), scope=sc), None)
    return frames


# ---------- metrics ----------
def _loss(S, kind):
    if kind in SK:
        y = S.final_total.to_numpy(float)
    if kind == "mae":
        return np.abs(y - S.q50.to_numpy(float))
    if kind == "pin":
        return sum(np.maximum(q * (y - S[c].to_numpy(float)), (q - 1) * (y - S[c].to_numpy(float))) for q, c in ((0.1, "q10"), (0.5, "q50"), (0.9, "q90"))) / 3
    if kind == "cov":
        return ((y >= S.q10.to_numpy(float)) & (y <= S.q90.to_numpy(float))).astype(float)
    if kind == "bias":
        return S.q50.to_numpy(float) - y
    y, p = S.chase_won.to_numpy(float), np.clip(S.p.to_numpy(float), 1e-6, 1 - 1e-6)
    if kind == "ll":
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))
    if kind == "brier":
        return (p - y) ** 2
    if kind == "acc":
        return ((p > 0.5) == (y > 0.5)).astype(float)
    raise ValueError(kind)


SK, WK = ("mae", "pin", "cov", "bias"), ("ll", "brier", "acc")


def common(frames, which):
    """Per checkpoint: the keys present in every model that has any row at that checkpoint. which: 0 score, 1 win."""
    out, keys = {n: {} for n in frames}, {}
    for cp in CP:
        have = {n: f[which] for n, f in frames.items() if f[which] is not None and (f[which].balls_bowled == cp).any()}
        k = None
        for n, d in have.items():
            kk = pd.MultiIndex.from_frame(d[d.balls_bowled == cp][KEY].drop_duplicates())
            k = kk if k is None else k.intersection(kk)
        keys[cp] = k
        for n, d in have.items():
            x = d[d.balls_bowled == cp].drop_duplicates(KEY).set_index(KEY).loc[k].reset_index().sort_values(KEY).reset_index(drop=True)
            out[n][cp] = x
    return out


def dev_frames(frames):
    """Pooled dev set: IPL 2022-25 + non-IPL 2024-25, only for models present in both."""
    out = {}
    for m in frames["ipl"]:
        if m in frames["non"]:
            out[m] = tuple(None if frames["ipl"][m][i] is None else pd.concat([frames["ipl"][m][i], frames["non"][m][i]], ignore_index=True) for i in (0, 1))
    return out


def tables(frames, sets=("ipl", "non", "dev", "ipl26", "non26")):
    rows = []
    for sc in sets:
        fr = dev_frames(frames) if sc == "dev" else frames[sc]
        for which, kinds in ((0, SK), (1, WK)):
            cm = common(fr, which)
            for n, d in cm.items():
                if not d:
                    continue
                per = {cp: {k: float(np.mean(_loss(x, k))) for k in kinds} for cp, x in d.items()}
                for cp, r in per.items():
                    rows.append({"set": sc, "model": n, "kind": "score" if which == 0 else "win", "cp": cp // 6, "n": len(d[cp]), **r})
                for lab, cps in (("mean4", CP), ("mean3", CP[1:])):
                    if all(c in per for c in cps):
                        rows.append({"set": sc, "model": n, "kind": "score" if which == 0 else "win", "cp": lab, "n": sum(len(d[c]) for c in cps), **{k: np.mean([per[c][k] for c in cps]) for k in kinds}})
    return pd.DataFrame(rows)


def paired(frames, a, b, sc, kind, unit="match", n=2000, seed=0, cps=CP):
    """Paired difference loss(a) - loss(b), mean over the checkpoints; bootstrap over `unit` ('match' or 'block' = competition x season).
    Returns dict diff, lo, hi (two-sided 95%), n_units, and per-block signs for unit='block'."""
    which = 0 if kind in SK else 1
    fr = {k: v for k, v in (dev_frames(frames) if sc == "dev" else frames[sc]).items() if k in (a, b)}
    cm = common(fr, which)
    parts = []
    for ci, cp in enumerate(cps):
        if cp not in cm[a] or cp not in cm[b]:
            continue
        A, B = cm[a][cp], cm[b][cp]
        d = _loss(A, kind) - _loss(B, kind)
        u = A.match_id.to_numpy() if unit == "match" else (A.competition.astype(str) + "|" + A.season_year.astype(str)).to_numpy()
        parts.append(pd.DataFrame({"u": u, "d": d, "n": 1.0, "cp": ci}))
    z = pd.concat(parts)
    codes, uniq = pd.factorize(z.u)
    nu, nc = len(uniq), z.cp.nunique()
    D, N = np.zeros((nu, nc)), np.zeros((nu, nc))
    ci = pd.factorize(z.cp)[0]
    np.add.at(D, (codes, ci), z.d.to_numpy())
    np.add.at(N, (codes, ci), z.n.to_numpy())
    stat = lambda C: np.mean((C @ D) / np.maximum(C @ N, 1e-9), axis=1)  # noqa: E731
    est = float(np.mean(D.sum(0) / N.sum(0)))
    C = np.random.default_rng(seed).multinomial(nu, np.ones(nu) / nu, size=n).astype(float)
    b = stat(C)
    out = {"diff": est, "lo": float(np.percentile(b, 2.5)), "hi": float(np.percentile(b, 97.5)), "units": nu}
    if unit == "block":
        per = np.mean(D / np.maximum(N, 1e-9), axis=1)
        keep = N.sum(1) >= 30
        out["neg_blocks"], out["blocks30"] = int((per[keep] < 0).sum()), int(keep.sum())
    return out


def decision(frames):
    """The pre-registered rule, on the dev folds (point estimates, mean of the 4 checkpoints). Each rule is evaluated on the rows present
    in ALL of its own candidates (the registered "rows present in all candidate caches")."""
    def only(names):
        return {sc: {m: v for m, v in frames[sc].items() if m in names} for sc in ("ipl", "non")}

    ca = ["F-score", "mean(F,G1)", G1, ENS1]
    ts = tables(only(ca), ("dev",))
    tw = tables(only([ENS1, SIM]), ("dev",))
    ll = {m: float(tw[(tw.model == m) & (tw.kind == "win") & (tw.cp == "mean4")].ll.iloc[0]) for m in (ENS1, SIM)}
    chase = SIM if ll[SIM] <= ll[ENS1] + 0.005 else ENS1
    t = ts[(ts.cp == "mean4") & (ts.kind == "score")].set_index("model")
    mae, cov = {m: float(t.loc[m, "mae"]) for m in ca}, {m: float(t.loc[m, "cov"]) for m in ca}
    best = min(mae.values())
    score = next((m for m in ca if mae[m] <= best + 0.2 and 0.75 <= cov[m] <= 0.85), ENS1)
    return {"chase_ll": ll, "chase_margin": ll[SIM] - ll[ENS1], "chase": chase, "mae": mae, "cov80": cov, "best_mae": best, "score": score,
            "n_score_rows_per_cp": {cp: int(n) for cp, n in ts[(ts.model == G1) & (ts.kind == "score") & ts.cp.isin([0, 6, 10, 15])].set_index("cp").n.items()},
            "n_win_rows_per_cp": {cp: int(n) for cp, n in tw[(tw.model == ENS1) & (tw.kind == "win") & tw.cp.isin([0, 6, 10, 15])].set_index("cp").n.items()}}


# ---------- reviewer's check (all IPL 2022-25 states, innings-weighted) ----------
def check_reviewer():
    """Sanity: F-score on the same 33,873 IPL 2022-25 states and weights as the review (MAE 18.12 table, 16.40 scaled, G1 16.30)."""
    from . import direct as D

    s = load()
    ipl = s.competition == "ipl"
    base = pd.read_parquet(OUT_DIR / "direct_baseline_score.parquet")
    g1 = pd.read_parquet(OUT_DIR / "s4b_g1_S.parquet")
    from . import s4b

    g1 = s4b.conformalise(g1, pd.read_parquet(OUT_DIR / "s4b_g1_V.parquet"), "G1")
    out = []
    for Y in (2022, 2023, 2024, 2025):
        tab, _ = fold_models(s, "ipl", ipl & (s.season_year < Y), ipl & (s.season_year == Y - 1), ipl & (s.season_year < Y - 1))
        b = base[base.fold == Y]
        test = s[ipl & (s.season_year == Y) & (s.innings == 1)].assign(match_id=lambda d: d.match_id.astype(str))
        k = b[KEY].assign(match_id=lambda d: d.match_id.astype(str))
        t = test.merge(k, on=KEY)
        out.append(t[KEY + ["final_total"]].assign(fold=Y, **tab.score(t)))
    f = pd.concat(out)
    b = base.assign(match_id=base.match_id.astype(str))
    g1 = g1.assign(match_id=g1.match_id.astype(str))
    w = lambda d: ev.match_weights(d)  # noqa: E731
    res = {"resource-ipl": b, "F-score": f, "G1": g1[g1.set_index(KEY).index.isin(b.set_index(KEY).index)]}
    for n, d in res.items():
        print(f"{n}: n={len(d)} MAE {ev.mae(d.final_total, d.q50, w(d)):.2f} bias {np.average(d.q50 - d.final_total, weights=w(d)):+.2f} cov80 {ev.coverage(d.final_total, d.q10, d.q90, w(d)):.3f}")
    print("G1 - F-score MAE (match bootstrap 5-95):", D.boot_diff(res["G1"].assign(fold=0), f.assign(fold=0), "mae"))
    print("F-score - resource MAE:", D.boot_diff(f.assign(fold=0), b.assign(fold=0), "mae"))


# ---------- report ----------
def report():
    frames = build_frames()
    t = tables(frames)
    t.to_csv(OUT_DIR / "fair_tables.csv", index=False)
    pd.set_option("display.width", 250)
    for sc in ("dev", "ipl", "non", "ipl26", "non26"):
        for kind, kk in (("score", SK), ("win", WK)):
            x = t[(t.set == sc) & (t.kind == kind)]
            print(f"\n### {sc} {kind}: mean of 4 checkpoints (0/6/10/15 overs) and by checkpoint")
            piv = x.pivot_table(index="model", columns="cp", values=kk[0], aggfunc="first")
            m4 = x[x.cp == "mean4"].set_index("model")
            m3 = x[x.cp == "mean3"].set_index("model")
            tab = pd.DataFrame({"mean4": m4[kk[0]], "mean3(6/10/15)": m3[kk[0]], **{f"{c} ov": piv.get(c) for c in (0, 6, 10, 15)}}).round(3)
            for k in kk[1:]:
                tab[k + "_m4"] = m4[k].round(3)
            print(tab.to_string())
    d = decision(frames)
    print("\n### Decision rule (dev folds, pre-registered)\n", d)
    rows = []
    for sc in ("dev", "ipl", "non", "ipl26", "non26"):
        jobs = [(m, "F-score", k) for m in (G1, "G2", "b2", ENS1, "mean(F,G1)", "resource-ipl") for k in ("mae", "pin")]
        jobs += [("F-score", ENS1, k) for k in ("mae", "pin")] + [(G1, ENS1, k) for k in ("mae", "pin")] + [("mean(F,G1)", ENS1, k) for k in ("mae", "pin")]
        jobs += [(m, "F-chase", k) for m in (G1, "G2", "b2", SIM, ENS1) for k in ("ll", "brier")] + [(SIM, ENS1, k) for k in ("ll", "brier")]
        for a, b, k in jobs:
            for unit in ("match", "block"):
                try:
                    r = paired(frames, a, b, sc, k, unit)
                except (KeyError, ValueError):
                    continue
                rows.append({"set": sc, "a": a, "b": b, "metric": k, "unit": unit, **r})
    pr = pd.DataFrame(rows)
    pr.to_csv(OUT_DIR / "fair_paired.csv", index=False)
    return frames, t, d, pr


def tidy(pr):
    """One row per (set, a - b, metric): match-bootstrap interval, and the season-block result (interval if >= 6 blocks, else the sign count)."""
    f = lambda r: f"{r['diff']:+.3f} [{r['lo']:+.3f}, {r['hi']:+.3f}]" + ("*" if (r["lo"] > 0 or r["hi"] < 0) else "")  # noqa: E731
    m = pr[pr.unit == "match"].set_index(["set", "a", "b", "metric"])
    b = pr[pr.unit == "block"].set_index(["set", "a", "b", "metric"])
    out = pd.DataFrame({"match95": m.apply(f, axis=1)})
    out["blocks"] = b.units
    out["block95"] = b.apply(lambda r: f(r) if r.units >= 6 else f"{int(r.neg_blocks)}/{int(r.blocks30)} blocks negative", axis=1)
    return out.reset_index()


if __name__ == "__main__":
    if sys.argv[1:2] == ["fit"]:
        fit()
    elif sys.argv[1:2] == ["report"]:
        frames, t, d, pr = report()
        print(tidy(pr).to_string())
    elif sys.argv[1:2] == ["check"]:
        check_reviewer()
    else:
        print(__doc__)
