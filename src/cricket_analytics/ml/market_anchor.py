"""Market-anchored model (test 1) and state-wise diagnosis (test 2), pre-registered in docs/ML_PREDICTION.md section 9 (commit eb3efa7).

  python -m cricket_analytics.ml.market_anchor    # builds rows, writes data/external/ml/market_anchor_rows.parquet, prints the tables

Reuses ml/market.py (benchmark rows, market probabilities, out-of-sample pre-match predictions) and changes none of its outputs.
Yardstick only: no betting use. Rows dated 2026-10-15 or later are never read; fresh3/ is never opened. The DB is not touched.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from . import evaluate as ev
from . import market as M

SEASON_ORDER = list(M.SEASONS)  # BBL10 .. BBL15
OUT = M.ML_DIR / "market_anchor_rows.parquet"
WK_BINS = ["0-1", "2-3", "4+"]
RR_BINS = ["<8", "8-10", ">10"]
N_BOOT = 2000


def _sig(x):
    return 1 / (1 + np.exp(-x))


def _prematch_chaser(rows: pd.DataFrame) -> pd.DataFrame:
    """Per benchmark row: market first-ball p for the chaser and the out-of-sample pre-match model p (toss unknown) for the chaser.
    Both come from market_rows_firstball.parquet (written by market.first_ball: p for team_a = alphabetically first team)."""
    f = pd.read_parquet(M.ML_DIR / "market_rows_firstball.parquet", columns=["match_id", "team_a", "y", "p_market", "p_prematch (toss unknown)"])
    f["match_id"] = f.match_id.astype(str)
    assert f.match_id.is_unique
    f = f.rename(columns={"y": "y_fb", "p_market": "p_market_fb"})
    d = rows.merge(f, on="match_id", how="left")
    assert d.team_a.notna().all(), "benchmark rows without a first-ball / pre-match row"
    flip = d.chaser != d.team_a
    d["p_mkt0"] = np.where(flip, 1 - d.p_market_fb, d.p_market_fb)
    d["p_pre"] = np.where(flip, 1 - d["p_prematch (toss unknown)"], d["p_prematch (toss unknown)"])
    # consistency: the pre-match y (team_a won) must equal the chaser's result, flipped if the chaser is not team_a
    ya = np.where(flip, 1 - d.y, d.y)
    ok = d.y_fb.isna() | (d.y_fb == ya)
    assert ok.all(), f"{int((~ok).sum())} rows where the pre-match y disagrees with the chase result"
    return d.drop(columns=["team_a", "y_fb", "p_market_fb", "p_prematch (toss unknown)"])


def _state_cols(rows: pd.DataFrame) -> pd.DataFrame:
    """Wickets down and required rate at the checkpoint, from the state table: (target - runs) / overs left."""
    from .dataset import OUT_DIR

    s = pd.read_parquet(OUT_DIR / "states.parquet", columns=["match_id", "innings", "balls_bowled", "wickets", "runs_needed", "balls_left", "competition", "gender", "date"])
    s = s[(s.innings == 2) & (s.competition == "bbl") & (s.gender == "male") & s.balls_bowled.isin(M.CP)]
    assert s.date.max() < M.CUT
    s = s.assign(match_id=s.match_id.astype(str), balls_bowled=s.balls_bowled.astype(float))[["match_id", "balls_bowled", "wickets", "runs_needed", "balls_left"]]
    d = rows.assign(balls_bowled=rows.balls_bowled.astype(float)).merge(s, on=["match_id", "balls_bowled"], how="left", validate="1:1")
    assert d.wickets.notna().all()
    d["rrr"] = d.runs_needed / (d.balls_left / 6)
    d["wk_bin"] = pd.cut(d.wickets, [-1, 1, 3, 99], labels=WK_BINS).astype(str)
    d["rr_bin"] = np.select([d.rrr < 8, d.rrr <= 10], ["<8", "8-10"], ">10")  # < 8, 8-10 inclusive, > 10
    return d


def fit_B(rows: pd.DataFrame) -> pd.DataFrame:
    """B: per checkpoint, logistic regression of y on [logit p_mkt0, logit p_ens-G1, logit p_pre], expanding window by season: the model for season S
    is fit only on seasons before S (BBL10 gets no prediction). Adds p_B and b_train_max_season."""
    X = lambda d: np.column_stack([M._logit(d.p_mkt0), M._logit(d["p_ens-G1"]), M._logit(d.p_pre)])  # noqa: E731
    p, tm = pd.Series(np.nan, index=rows.index), pd.Series(np.nan, index=rows.index, dtype=object)
    for _, g in rows.groupby("balls_bowled"):
        for s in SEASON_ORDER[1:]:
            tr, te = g[g.season.map(SEASON_ORDER.index) < SEASON_ORDER.index(s)], g[g.season == s]
            if te.empty:
                continue
            m = LogisticRegression(C=1e6, max_iter=1000).fit(X(tr), tr.y.astype(int))  # C=1e6: effectively unpenalised
            p[te.index] = m.predict_proba(X(te))[:, 1]
            tm[te.index] = tr.season.max()
    return rows.assign(p_B=p, b_train_max_season=tm)


def anchor_rows() -> pd.DataFrame:
    """The benchmark rows (market_rows.parquet) plus p_mkt0, p_pre, p_A, p_B, b_train_max_season, wickets, rrr, wk_bin, rr_bin."""
    r = pd.read_parquet(M.ML_DIR / "market_rows.parquet")
    r["match_id"] = r.match_id.astype(str)
    r = r.reset_index(drop=True)
    r = _state_cols(_prematch_chaser(r))
    r["p_A"] = _sig(M._logit(r.p_mkt0) + M._logit(r["p_ens-G1"]) - M._logit(r.p_pre))
    r = fit_B(r)
    assert (r.date < M.CUT).all()
    return r


# ---------- test 1 ----------
def _verdict(t: pd.Series) -> str:
    """Model minus reference. Both the match and the season-block interval must agree for any claim."""
    if t.m_hi < 0 and t.s_hi < 0:
        return "better (both intervals below 0)"
    if t.m_lo > 0 and t.s_lo > 0:
        return "worse (both intervals above 0)"
    if t.m_lo <= 0 and t.s_lo <= 0:
        return "tie-or-better (neither interval shows worse)"
    return "intervals disagree"


def test1(r: pd.DataFrame, log=print) -> dict:
    out = {}
    for b in M.CP:
        g = r[r.balls_bowled == b]
        gb = g[g.p_B.notna()]
        rows = []
        for label, d, c, ref in [("A - market", g, "p_A", "p_market"), ("A - ens-G1", g, "p_A", "p_ens-G1"), ("ens-G1 - market", g, "p_ens-G1", "p_market"),
                                 ("B - market (BBL11-15)", gb, "p_B", "p_market"), ("B - ens-G1 (BBL11-15)", gb, "p_B", "p_ens-G1"),
                                 ("ens-G1 - market (BBL11-15)", gb, "p_ens-G1", "p_market"), ("A - market (BBL11-15)", gb, "p_A", "p_market")]:
            t = M.compare(d, [c], mkt=ref, n_boot=N_BOOT).iloc[0]
            rows.append(t.to_frame().T.assign(cmp=label, verdict=_verdict(t)))
        T = pd.concat(rows, ignore_index=True)
        out[b] = T
        log(f"\n=== TEST 1, chase {b // 6} overs: n={len(g)} (B rows {len(gb)}) ===")
        log(T[["cmp", "n", "ll_model", "ll_market", "diff", "m_lo", "m_hi", "s_lo", "s_hi", "blocks", "verdict"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
        log(T[["cmp", "brier_model", "brier_market", "acc_model", "acc_market", "cal_model", "cal_market"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    return out


# ---------- test 2 ----------
def _ll(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def test2(r: pd.DataFrame, log=print, n_boot=4000, min_n=20) -> pd.DataFrame:
    """27 cells (3 checkpoints x 3 wicket bins x 3 required-rate bins). One row per match per checkpoint, so the match bootstrap resamples rows.
    p = two-sided bootstrap p of the mean paired difference (2 * min tail, floor 1/(n_boot+1)); Holm over all 27 cells, cells with n < min_n get p = 1."""
    rng, out = np.random.default_rng(0), []
    for b in M.CP:
        for w in WK_BINS:
            for q in RR_BINS:
                g = r[(r.balls_bowled == b) & (r.wk_bin == w) & (r.rr_bin == q)]
                lm, lk = _ll(g.y.to_numpy(), g["p_ens-G1"].to_numpy()), _ll(g.y.to_numpy(), g.p_market.to_numpy())
                d = lm - lk
                row = {"over": b // 6, "wickets": w, "rrr": q, "n": len(g), "ll_model": float(lm.mean()) if len(g) else np.nan,
                       "ll_market": float(lk.mean()) if len(g) else np.nan, "diff": float(d.mean()) if len(g) else np.nan, "lo": np.nan, "hi": np.nan, "p": 1.0}
                if len(g) >= min_n:
                    bs = d[rng.integers(0, len(d), (n_boot, len(d)))].mean(axis=1)
                    row.update(lo=float(np.percentile(bs, 2.5)), hi=float(np.percentile(bs, 97.5)),
                               p=float(min(1.0, max(2 * min((bs <= 0).mean(), (bs >= 0).mean()), 1 / (n_boot + 1)))))
                out.append(row)
    T = pd.DataFrame(out)
    T["p_holm"] = ev.holm(T.p.to_numpy())
    T["tested"] = T.n >= min_n
    T["finding"] = T.tested & (T.p_holm < 0.05)
    assert T.groupby("over").n.sum().tolist() == [int((r.balls_bowled == b).sum()) for b in M.CP]
    log("\n=== TEST 2 (diff = ens-G1 minus market log loss; positive = model worse) ===\n" + T.drop(columns="p").to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    return T


def main(log=print):
    r = anchor_rows()
    r.to_parquet(OUT)
    log(f"rows {len(r)}; per checkpoint {r.groupby('balls_bowled').size().to_dict()}; B rows {int(r.p_B.notna().sum())}")
    t1 = test1(r, log)
    t2 = test2(r, log)
    pd.concat(t1, names=["balls"]).to_csv(M.ML_DIR / "market_anchor_test1.csv")
    t2.to_csv(M.ML_DIR / "market_anchor_test2.csv", index=False)
    return r, t1, t2


if __name__ == "__main__":
    main()
