"""React-harder chase fix (B), pre-registered in docs/ML_PREDICTION.md section 9 (commit 9fe2ee1). Goal tests: tests/test_react_goals.py (frozen).

  python -m cricket_analytics.ml.react report     # all tables + the adoption verdict -> data/external/ml/react_*.csv / react_verdict.json

Candidates (only these two), judged against ens-G1 on the dev-fold chase rows at 6/10/15 overs (IPL 2022-25 + men's non-IPL 2024-25):
  F1 = logistic recalibration of ens-G1: y ~ [logit p, wickets, required rate, balls left, wickets x balls left], fit rolling (season S uses only
       seasons < S; a season with no earlier rows is left unchanged). Choices the registration left open: features standardised on the training
       rows, a ridge penalty (lam = 1, not tuned) pulling the coefficients toward "no change" (slope 1 on logit p, 0 on the rest), rrr clipped to [0, 30].
  F2 = the cached b2 chase frame = mean(G2, spline GAM).
Only cached out-of-sample predictions are read. Rows dated on or after 2026-10-15 are never used; fresh3/ is never opened.
"""

import json
import sys

import numpy as np
import pandas as pd

from . import evaluate as ev
from . import fair_report as FR
from . import flaw_fit as FF
from . import flaw_tests as T
from .dataset import OUT_DIR

KEY = ["match_id", "innings", "balls_bowled"]
CPS = (36, 60, 90)
LOCK_DATE = pd.Timestamp("2026-10-15")
LAM = 1.0
EPS = 1e-6
PRIOR = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
COLLAPSE = ("collapse 2wk/12b", "collapse 3wk/12b", "collapse 3wk/18b")  # "collapse in the chase" = these three events of the flaw battery
RRR13 = "chase rrr >= 13"


def _clip(p):
    return np.clip(np.asarray(p, float), EPS, 1 - EPS)


def _logit(p):
    p = _clip(p)
    return np.log(p / (1 - p))


# ---------- data ----------
def dev_rows() -> pd.DataFrame:
    """ens-G1 chase probabilities at 36/60/90 balls on the dev folds, with the state columns F1 needs."""
    cm, _ = FR.cached()
    W = cm["ens-G1"][1]
    W = W[W.balls_bowled.isin(CPS) & W.chase_won.notna() & W.scope.isin(["ipl", "non"])]
    W = T._norm(W).rename(columns={"p": "p_ens"})
    W = W[pd.to_datetime(W.date) < LOCK_DATE]
    st = _state()
    d = W.merge(st, on=KEY, how="left")
    return d[KEY + ["chase_won", "p_ens", "season_year", "competition", "date", "scope", "wickets", "rrr", "balls_left"]].reset_index(drop=True)


def _state():
    st = pd.read_parquet(FF.FEAT, columns=KEY + ["wickets", "rrr", "balls_left"])
    return T._norm(st[(st.innings == 2) & st.balls_bowled.isin(CPS)]).drop_duplicates(KEY)


# ---------- F1 ----------
def _design(d, mu=None, sd=None):
    ex = np.column_stack([d.wickets, np.clip(d.rrr.fillna(0), 0, 30), d.balls_left, d.wickets * d.balls_left]).astype(float)
    if mu is None:
        mu, sd = ex.mean(0), ex.std(0) + 1e-9
    return np.column_stack([np.ones(len(d)), _logit(d.p_ens), (ex - mu) / sd]), mu, sd


def fit_f1(train: pd.DataFrame) -> dict:
    """Ridge-to-identity logistic regression by Newton steps. Returns the coefficients and the training standardisation."""
    X, mu, sd = _design(train)
    y = train.chase_won.to_numpy(float)
    pen = np.diag([0.0] + [LAM] * 5)
    beta = PRIOR.copy()
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ beta))
        g = X.T @ (y - p) - pen @ (beta - PRIOR)
        H = X.T @ (X * (p * (1 - p))[:, None]) + pen + 1e-9 * np.eye(6)
        step = np.linalg.solve(H, g)
        beta = beta + step
        if np.abs(step).max() < 1e-9:
            break
    return {"beta": beta, "mu": mu, "sd": sd}


def apply_f1(m: dict, d: pd.DataFrame) -> np.ndarray:
    X, _, _ = _design(d, m["mu"], m["sd"])
    return _clip(1 / (1 + np.exp(-X @ m["beta"])))


def f1_rolling(rows: pd.DataFrame, fit_fn=None) -> pd.Series:
    """F1 probabilities, season by season: season S is scored by a layer fit only on rows with season_year < S (identity when there are none)."""
    fit_fn = fit_fn or fit_f1
    out = pd.Series(_clip(rows.p_ens), index=rows.index)
    for S in sorted(rows.season_year.unique()):
        train = rows[rows.season_year < S]
        if not len(train):
            continue
        te = rows.season_year == S
        out[te] = apply_f1(fit_fn(train), rows[te])
    return out


def candidates() -> pd.DataFrame:
    d = dev_rows()
    d["p_F1"] = f1_rolling(d)
    b2 = T._norm(pd.read_parquet(OUT_DIR / "db_b2_W.parquet"))[KEY + ["p"]].rename(columns={"p": "p_F2"})
    d = d.merge(b2, on=KEY, how="left")
    d["p_F2"] = _clip(d.p_F2)
    d["p_ens"] = _clip(d.p_ens)
    assert (pd.to_datetime(d.date) < LOCK_DATE).all()
    return d


# ---------- tables ----------
def _ll(y, p):
    p = _clip(p)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_ll(d, cand, ref="p_ens", n=2000):
    """cand minus ref chase log loss (negative = better): match bootstrap and season x competition block bootstrap, two-sided 95%."""
    x = d.assign(dl=_ll(d.chase_won, d[cand]) - _ll(d.chase_won, d[ref]))
    f = lambda z: float(z.dl.mean())  # noqa: E731
    e, lo, hi, nm = ev.match_bootstrap(x, f, n=n)
    _, slo, shi, nb = ev.season_block_bootstrap(x, f, n=n)
    return {"n": len(x), "n_matches": nm, "ll_ref": float(_ll(x.chase_won, x[ref]).mean()), "ll_cand": float(_ll(x.chase_won, x[cand]).mean()),
            "diff": e, "m_lo": lo, "m_hi": hi, "s_lo": slo, "s_hi": shi, "blocks": nb}


def ll_tables(c, n=2000):
    rows = []
    subs = {"dev": c.scope.isin(["ipl", "non"]), "ipl": c.scope == "ipl", "non": c.scope == "non"}
    for cand in ("p_F1", "p_F2"):
        for sc, m in subs.items():
            for cp in ("all",) + CPS:
                x = c[m & ((c.balls_bowled == cp) if cp != "all" else True)]
                rows.append({"cand": cand[2:], "set": sc, "cp": "all" if cp == "all" else cp // 6, **paired_ll(x, cand, n=n)})
        x = c[c.season_year > 2022]  # F1 sensitivity: rows where F1 was actually fit (2022 is identity)
        rows.append({"cand": cand[2:], "set": "dev", "cp": "all, 2023+", **paired_ll(x, cand, n=n)})
    return pd.DataFrame(rows)


def cal_table(c):
    rows = []
    for nm in ("p_ens", "p_F1", "p_F2"):
        for sc, m in {"dev": c.scope.isin(["ipl", "non"]), "ipl": c.scope == "ipl", "non": c.scope == "non"}.items():
            x = c[m]
            r = ev.calibration_test(x.chase_won, x[nm], groups=x.match_id, by=x.balls_bowled)
            rows.append({"model": nm[2:], "set": sc, "n": r["n"], "a": r["intercept"], "a_lo": r["intercept_ci"][0], "a_hi": r["intercept_ci"][1],
                         "b": r["slope"], "b_lo": r["slope_ci"][0], "b_hi": r["slope_ci"][1], "ece": r["ece"], "ece_p95": r["ece_null_p95"], "pass": r["pass_primary"]})
    return pd.DataFrame(rows)


def event_table(c, B=2000):
    """Chase event excess bias (pred - actual, event minus matched non-event) at the checkpoint rows, for ens-G1 / F1 / F2.
    group 'dev' = IPL and non-IPL pooled (competition relabelled so the battery sees one group), 'IPL' / 'nonIPL' = the battery's own groups."""
    ev_tab = T.load_events()
    ev_tab = ev_tab[pd.to_datetime(ev_tab.date) < LOCK_DATE]
    thr = T.thresholds(ev_tab)
    empty = pd.DataFrame(columns=KEY + ["final_total", "q10", "q50", "q90"])
    frames = {nm[2:]: (empty, c[KEY + ["chase_won"]].assign(p=c[nm])) for nm in ("p_ens", "p_F1", "p_F2")}
    res = T.run_battery(frames, ev_tab, thr=thr, B=B)
    pooled = T.run_battery(frames, ev_tab.assign(competition="x"), thr=thr, B=B, groups=("nonIPL",))
    pooled["group"] = "dev"
    out = pd.concat([res, pooled], ignore_index=True)
    return out[out.kind == "chase"].replace({"ens": "ens-G1"})


def decide(ll, cal, ev_t):
    """The registered rule, applied literally (pooled dev rows, all three checkpoints). Returns {cand: {check: bool, ...}, 'adopt': name or None}."""
    out = {}
    e = ev_t[ev_t.group == "dev"].set_index(["model", "event"])
    for k in ("F1", "F2"):
        r = ll[(ll.cand == k) & (ll.set == "dev") & (ll.cp == "all")].iloc[0]
        non = ll[(ll.cand == k) & (ll.set == "non") & (ll.cp == "all")].iloc[0]
        sizes = {}
        for evn in (RRR13,) + COLLAPSE:
            if ("ens-G1", evn) in e.index and (k, evn) in e.index:
                sizes[evn] = (abs(float(e.loc[("ens-G1", evn), "bias_diff"])) * 100, abs(float(e.loc[(k, evn), "bias_diff"])) * 100)
        c = cal[(cal.model == k) & (cal.set == "dev")].iloc[0]
        chk = {"ll_better_both_intervals": bool(r.m_hi < 0 and r.s_hi < 0), "events_smaller": bool(sizes) and all(b < a for a, b in sizes.values()),
               "non_ipl_not_worse": bool(non["diff"] <= 0), "calibration_passes": bool(c["pass"])}
        out[k] = {**chk, "qualifies": all(chk.values()), "ll_diff": float(r["diff"]), "event_sizes_pp(ens,cand)": sizes}
    q = [k for k in ("F1", "F2") if out[k]["qualifies"]]
    out["adopt"] = min(q, key=lambda k: ll[(ll.cand == k) & (ll.set == "dev") & (ll.cp == "all")].iloc[0].ll_cand) if q else None
    return out


# ---------- secondary: BBL market gap (reported, not used to decide) ----------
def bbl_gap(c, n=2000):
    from . import market as M

    mr = pd.read_parquet(M.ML_DIR / "market_rows.parquet")
    mr = mr.assign(match_id=mr.match_id.astype(str), balls_bowled=mr.balls_bowled.astype(int), innings=2)
    mr = mr.merge(_state(), on=KEY, how="left")
    mr["season_year"] = mr.season.map(M.SEASONS)
    mr["p_ens"] = _clip(mr["p_ens-G1"])
    mr["chase_won"] = mr.y
    pool = c[c.scope.isin(["ipl", "non"])]
    p1 = pd.Series(mr.p_ens.to_numpy().copy(), index=mr.index)
    for S in sorted(mr.season_year.unique()):  # layer fit on the dev rows of earlier seasons only
        tr = pool[pool.season_year < S]
        if len(tr):
            te = mr.season_year == S
            p1[te] = apply_f1(fit_f1(tr), mr[te])
    mr["p_F1"] = p1
    mr = mr.merge(c[KEY + ["p_F2"]], on=KEY, how="left")
    rows = []
    for nm, sub in (("BBL10-15 rows with a state (BBL15 after 2025-12-31 has none)", mr[mr.wickets.notna()]), ("BBL rows with an F2 prediction", mr[mr.p_F2.notna()])):
        for cp in ("all",) + CPS:
            x = sub if cp == "all" else sub[sub.balls_bowled == cp]
            for k in ("p_ens", "p_F1", "p_F2"):
                if x[k].isna().any():
                    continue
                t = M.compare(x, [k], n_boot=n).iloc[0]
                rows.append({"rows": nm, "cp": "all" if cp == "all" else cp // 6, "model": k[2:], "n": int(t.n), "ll_model": t.ll_model, "ll_market": t.ll_market,
                             "gap": t["diff"], "m_lo": t.m_lo, "m_hi": t.m_hi, "s_lo": t.s_lo, "s_hi": t.s_hi})
    return pd.DataFrame(rows)


def report(n=2000, log=print):
    c = candidates()
    log(f"rows {len(c)}, matches {c.match_id.nunique()}, per cp {c.groupby('balls_bowled').size().to_dict()}, F1 coefficients per season:")
    for S in sorted(c.season_year.unique()):
        tr = c[c.season_year < S]
        if len(tr):
            log(f"  {S}: n_train={len(tr)} beta={np.round(fit_f1(tr)['beta'], 3).tolist()}")
    ll, cal, evt = ll_tables(c, n), cal_table(c), event_table(c, n)
    bb = bbl_gap(c, n)
    for nm, t in (("ll", ll), ("cal", cal), ("events", evt), ("bbl", bb)):
        t.to_csv(OUT_DIR / f"react_{nm}.csv", index=False)
    verdict = decide(ll, cal, evt)
    (OUT_DIR / "react_verdict.json").write_text(json.dumps(verdict, indent=1, default=str))
    pd.set_option("display.width", 250)
    log("\n== log loss, cand - ens-G1 ==\n" + ll.round(4).to_string(index=False))
    log("\n== calibration ==\n" + cal.round(3).to_string(index=False))
    ec = evt[evt.event.isin((RRR13,) + COLLAPSE)]
    ec = ec.assign(ex=ec.bias_diff * 100, lo=ec.bias_lo * 100, hi=ec.bias_hi * 100)
    log("\n== chase events (excess pp = pred - actual) ==\n" + ec[["group", "event", "model", "n_matches", "n_states", "ex", "lo", "hi"]].round(2).sort_values(["group", "event", "model"]).to_string(index=False))
    log("\n== BBL gap to market (model - market log loss) ==\n" + bb.round(4).to_string(index=False))
    log("\nVERDICT " + json.dumps(verdict, indent=1, default=str))
    return verdict


if __name__ == "__main__":
    if sys.argv[1:2] == ["report"]:
        report()
