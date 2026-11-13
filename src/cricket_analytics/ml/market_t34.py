"""Test 3 (do Betfair BBL prices overreact to wickets?) and test 4 (do player features explain the model-vs-market gap?), pre-registered in
docs/ML_PREDICTION.md section 9 (commit 29efa9c). Goal tests: tests/test_market_t34_goals.py (frozen first).

  python -m cricket_analytics.ml.market_t34     # writes market_t34_rows.parquet (test 3 rows) and market_t34_t4_rows.parquet (test 4 rows), prints both tests

Yardstick only: no betting use. Rows dated 2026-10-15 or later are never read; fresh3/ is never opened. The DB is read-only.
"""

import numpy as np
import pandas as pd

from . import evaluate as ev
from . import market as M

PAIRS = {"4-6": (24, 36), "6-10": (36, 60), "10-15": (60, 90)}  # legal balls at the two snapshots (over-end)
SNAP_LATE = {36: "SIX", 60: "TEN", 90: "FIFTEEN"}
NOT_DISMISSAL = ("retired hurt", "retired not out")
OUT3, OUT4 = M.ML_DIR / "market_t34_rows.parquet", M.ML_DIR / "market_t34_t4_rows.parquet"
FEATS = ["f_crease", "f_notin", "f_bowl"]  # the registered 4th (keeper/finisher flag) is not used
N_BOOT = 2000


# ---------- test 3 rows ----------
def _innings_windows(match_ids) -> pd.DataFrame:
    """Per (match, innings, pair): batting team, W from Cricsheet, and whether the innings was still live after the later snapshot ball."""
    from ..db import query

    ids = ", ".join(f"'{m}'" for m in match_ids)
    d = query(f"select match_id, innings, ball_seq, wides, noballs, wicket_type, player_out, batting_team from deliveries where innings <= 2 and match_id in ({ids})")
    d = d.sort_values(["match_id", "innings", "ball_seq"], kind="stable")
    d["legal"] = ((d.wides == 0) & (d.noballs == 0)).astype(int)
    g = d.groupby(["match_id", "innings"])
    d["before"] = g.legal.cumsum() - d.legal  # legal balls bowled before this delivery
    d["wk"] = (d.player_out.notna() & ~d.wicket_type.isin(NOT_DISMISSAL)).astype(int)
    out = []
    for (m, i), x in d.groupby(["match_id", "innings"]):
        for pair, (b0, b1) in PAIRS.items():
            out.append({"match_id": m, "innings": int(i), "pair": pair, "b0": b0, "b1": b1, "batting_team": x.batting_team.iloc[0],
                        "W": int(x[(x.before >= b0) & (x.before < b1)].wk.sum()), "live": bool((x.before >= b1).any())})
    return pd.DataFrame(out)


def pair_rows() -> pd.DataFrame:
    """Test 3 rows: one per innings and consecutive snapshot pair with a market p for the batting team at the later snapshot, the innings still live
    after that ball, a decided match (winner known) and not rain-reduced (states.reduced)."""
    from .dataset import OUT_DIR

    odds = M.load_odds()
    cs = M.cricsheet_bbl()
    j = M.join_events(odds, cs)
    j = j[j.match_id.notna()]
    mp = M.market_probs(odds)
    w = _innings_windows(j.match_id)
    st = pd.read_parquet(OUT_DIR / "states.parquet", columns=["match_id", "reduced", "competition", "gender"])
    reduced = set(st[(st.competition == "bbl") & (st.gender == "male") & st.reduced.astype(bool)].match_id.astype(str))
    w = w[w.live & ~w.match_id.isin(reduced)].merge(j[["match_id", "EVENT_ID", "SEASON"]], on="match_id")
    w = w.merge(cs[["match_id", "winner", "date"]], on="match_id")
    w = w[w.winner.notna()]
    parts = []
    for inn, pre in ((1, "FIRST_INN_"), (2, "SECOND_INN_")):
        for b1, name in SNAP_LATE.items():
            x = w[(w.innings == inn) & (w.b1 == b1)]
            m = mp[mp.snapshot == f"{pre}{name}_OV"].assign(RUNNER_NAME=lambda z: z.RUNNER_NAME.map(M._canon))
            bat = x.merge(m[["EVENT_ID", "RUNNER_NAME", "p"]], left_on=["EVENT_ID", "batting_team"], right_on=["EVENT_ID", "RUNNER_NAME"])
            fld = m.merge(x[["EVENT_ID", "batting_team"]], on="EVENT_ID")
            fld = fld[fld.RUNNER_NAME != fld.batting_team].groupby("EVENT_ID").p.first().rename("p_fld")
            parts.append(bat.merge(fld, on="EVENT_ID").rename(columns={"p": "p_bat"}))
    r = pd.concat(parts, ignore_index=True)
    r["y"] = (r.winner == r.batting_team).astype(int)
    r = r.rename(columns={"SEASON": "season"})
    r = r[["match_id", "season", "date", "innings", "pair", "b0", "b1", "batting_team", "p_bat", "p_fld", "W", "y"]].sort_values(["match_id", "innings", "b1"]).reset_index(drop=True)
    assert pd.to_datetime(r.date).max() < M.CUT
    return r


# ---------- test 3 statistics ----------
def fit_beta(y, off, W, intercept=False):
    """Logistic regression of y on offset `off` (= logit market p, coefficient fixed at 1) plus beta * W (plus a free intercept if asked). Returns beta."""
    X = np.column_stack([np.ones(len(y)), W]) if intercept else np.asarray(W, float)[:, None]
    b = np.zeros(X.shape[1])
    for _ in range(50):
        mu = 1 / (1 + np.exp(-(off + X @ b)))
        H = X.T @ (X * (mu * (1 - mu))[:, None]) + 1e-9 * np.eye(len(b))
        step = np.clip(np.linalg.solve(H, X.T @ (y - mu)), -2, 2)
        b = b + step
        if np.abs(step).max() < 1e-8:
            break
    return float(b[-1])


def _beta_df(df, intercept=False):
    if df.W.nunique() < 2:
        return np.nan
    return fit_beta(df.y.to_numpy(float), M._logit(df.p_bat), df.W.to_numpy(float), intercept)


def test3(r: pd.DataFrame, n_boot=N_BOOT, log=print) -> pd.DataFrame:
    sets = [("PRIMARY inn1 pooled", r.innings == 1), ("inn2 pooled", r.innings == 2)]
    sets += [(f"inn{i} {p}", (r.innings == i) & (r.pair == p)) for i in (1, 2) for p in PAIRS]
    out = []
    for name, mask in sets:
        d = r[mask]
        e, lo, hi, nm = ev.match_bootstrap(d, _beta_df, n=n_boot)
        _, slo, shi, nb = ev.season_block_bootstrap(d, _beta_df, block_cols=("season",), n=n_boot)
        out.append({"set": name, "rows": len(d), "matches": d.match_id.nunique(), "wk_rows": int((d.W > 0).sum()), "beta": e, "m_lo": lo, "m_hi": hi, "s_lo": slo, "s_hi": shi,
                    "blocks": nb, "beta_with_intercept": _beta_df(d, True),
                    "finding": bool((lo > 0 or hi < 0) and (slo > 0 or shi < 0))})
    T = pd.DataFrame(out)
    log("\n=== TEST 3 (beta > 0: market too pessimistic about the batting team after wickets) ===\n" + T.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    return T


# ---------- test 4 ----------
def player_features(rows, d, dates, d_strength=None) -> pd.DataFrame:
    """Per benchmark-style row (match_id, balls_bowled; chase innings) three prior-only player features, with the real XI (xi.parquet):
    f_crease  strength (resources.Strengths.bat exp) of the two batters at the crease, summed;
    f_notin   summed strength of the chasing XI not yet in (resources.bat_left_str);
    f_bowl    bowling strength of the fielding side's remaining overs (resources.bowl_left_econ; runs conceded vs average, LOWER = stronger).
    Strengths come from d_strength (default d) and use only matches dated strictly before the match."""
    from . import resources as R
    from .dataset import OUT_DIR

    rows = rows.assign(match_id=rows.match_id.astype(str))
    ids = set(rows.match_id)
    S = R.Strengths.build(d if d_strength is None else d_strength, dates)
    xi = R.xi_from_info(d[d.match_id.isin(ids)])
    side = {k: v.player.tolist() for k, v in xi.groupby(["match_id", "team"])}
    st = pd.read_parquet(OUT_DIR / "states.parquet", columns=["match_id", "innings", "balls_bowled", "striker", "non_striker", "bowler", "batting_team", "bowling_team", "date"])
    st["match_id"] = st.match_id.astype(str)
    st = st[st.match_id.isin(ids) & (st.innings == 2)].sort_values(["match_id", "balls_bowled"], kind="stable")
    want = {(m, int(b)) for m, b in zip(rows.match_id, rows.balls_bowled)}
    out = []
    for mid, s in st.groupby("match_id", sort=False):
        day = int(R._days(pd.Series([dates[mid]]))[0])
        bt, bw = s.batting_team.iloc[0], s.bowling_team.iloc[0]
        bat_xi = {p: S.bat(f"{p}|male", day) for p in side[(mid, bt)]}
        bowl_xi = {p: S.bowl(f"{p}|male", day) for p in side[(mid, bw)]}
        res = R.innings_resources(zip(s.balls_bowled, s.striker, s.non_striker, s.bowler), bat_xi, bowl_xi)
        for b, a, c, rr in zip(s.balls_bowled, s.striker, s.non_striker, res):
            if (mid, int(b)) in want:
                out.append({"match_id": mid, "balls_bowled": float(b), "f_crease": sum(S.bat(f"{p}|male", day)[0] for p in (a, c) if isinstance(p, str)),
                            "f_notin": rr["bat_left_str"], "f_bowl": rr["bowl_left_econ"]})
    return pd.DataFrame(out)


def t4_rows() -> pd.DataFrame:
    """The benchmark rows (market_rows.parquet) plus r = logit(p_market) - logit(p_ens-G1) and the three player features."""
    from . import resources as R

    b = pd.read_parquet(M.ML_DIR / "market_rows.parquet")
    b["match_id"] = b.match_id.astype(str)
    d, dates = R.load_deliveries()
    f = player_features(b, d, dates)
    b = b.assign(balls_bowled=b.balls_bowled.astype(float)).merge(f, on=["match_id", "balls_bowled"], how="left", validate="1:1")
    b["r"] = M._logit(b.p_market) - M._logit(b["p_ens-G1"])
    assert b[FEATS].notna().all().all() and (b.date < M.CUT).all()
    return b


def _ols(Z, r):
    return np.linalg.lstsq(np.column_stack([np.ones(len(r)), Z]), r, rcond=None)[0][1:]


def _boot(df, Z, r, cols, n, seed=0):
    """Cluster bootstrap of the OLS slopes: resample whole groups (match_id or season)."""
    idx = list(df.reset_index(drop=True).groupby(cols, sort=False).indices.values())
    rng = np.random.default_rng(seed)
    out = np.empty((n, Z.shape[1]))
    for i in range(n):
        pick = np.concatenate([idx[j] for j in rng.integers(0, len(idx), len(idx))])
        out[i] = _ols(Z[pick], r[pick])
    return out


def test4(t: pd.DataFrame, n_boot=N_BOOT, log=print) -> pd.DataFrame:
    """OLS of r on the standardised features (each z-scored within its checkpoint, then pooled). Holm over 4 (the 4th, the keeper flag, is untested: p = 1)."""
    t = t.reset_index(drop=True)
    Z = np.column_stack([t.groupby("balls_bowled")[c].transform(lambda x: (x - x.mean()) / x.std(ddof=0)).to_numpy() for c in FEATS])
    r = t.r.to_numpy()
    est = _ols(Z, r)
    bm, bs = _boot(t, Z, r, ["match_id"], n_boot), _boot(t, Z, r, ["season"], n_boot)
    pm = np.maximum(2 * np.minimum((bm <= 0).mean(0), (bm >= 0).mean(0)), 1 / (n_boot + 1))
    T = pd.DataFrame({"feature": FEATS, "slope": est, "m_lo": np.percentile(bm, 2.5, 0), "m_hi": np.percentile(bm, 97.5, 0),
                      "s_lo": np.percentile(bs, 2.5, 0), "s_hi": np.percentile(bs, 97.5, 0), "p_match": pm, "p_holm4": ev.holm(np.r_[pm, 1.0])[:3]})
    T["survives"] = (T.p_holm4 < 0.05) & ((T.s_lo > 0) | (T.s_hi < 0))
    log(f"\n=== TEST 4 (n={len(t)} rows, {t.match_id.nunique()} matches; r = logit market - logit ens-G1, per 1 SD of the feature) ===\n" + T.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    return T


def main(log=print):
    p = pair_rows()
    p.to_parquet(OUT3)
    log(f"test 3 rows {len(p)}, matches {p.match_id.nunique()}; per innings and pair:\n" + p.groupby(["innings", "pair"]).agg(rows=("y", "size"), matches=("match_id", "nunique"), with_wk=("W", lambda x: int((x > 0).sum()))).to_string())
    t3 = test3(p, log=log)
    t = t4_rows()
    t.to_parquet(OUT4)
    t4 = test4(t, log=log)
    t3.to_csv(M.ML_DIR / "market_t34_test3.csv", index=False)
    t4.to_csv(M.ML_DIR / "market_t34_test4.csv", index=False)
    return p, t3, t, t4


if __name__ == "__main__":
    main()
