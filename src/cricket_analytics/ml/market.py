"""Model-vs-market benchmark on Betfair BBL in-play odds (pre-registered in docs/ML_PREDICTION.md section 9, commit da40fa4).

  python -m cricket_analytics.ml.market preds    # fit every model per BBL season on matches dated before that season starts, predict chase checkpoints
  python -m cricket_analytics.ml.market report   # join, market probabilities, metrics (reads the caches), writes market_rows.parquet

Yardstick only: no betting use. Rows dated 2026-10-15 or later are never read; fresh3/ is never opened. The DB is read-only.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
ODDS_DIR = ROOT / "data" / "external" / "odds" / "betfair_ds"
ML_DIR = ROOT / "data" / "external" / "ml"
CUT = pd.Timestamp("2026-10-15")
SEASONS = {"BBL10": 2020, "BBL11": 2021, "BBL12": 2022, "BBL13": 2023, "BBL14": 2024, "BBL15": 2025}  # tag -> Cricsheet season_year ("2020/21" = 2020)
CP = (36, 60, 90)  # chase checkpoints in legal balls = 6 / 10 / 15 overs
SNAP = {36: "SECOND_INN_SIX_OV", 60: "SECOND_INN_TEN_OV", 90: "SECOND_INN_FIFTEEN_OV"}
SNAP1 = {36: "FIRST_INN_SIX_OV", 60: "FIRST_INN_TEN_OV", 90: "FIRST_INN_FIFTEEN_OV"}
NAME_MAP: dict[str, str] = {}  # Betfair team name -> Cricsheet name (identical for all eight BBL clubs; checked)
MODELS = ("ens-G1", "G1", "sim-B", "F-chase")


# ---------- odds ----------
def load_odds() -> pd.DataFrame:
    """All BBL10..BBL15 Match_Odds CSVs, one row per runner per event, plus SEASON (BBL10..)."""
    fs = sorted(ODDS_DIR.glob("BBL1*_Match_Odds.csv"))
    if not fs:
        raise FileNotFoundError(f"no odds files in {ODDS_DIR}")
    d = pd.concat([pd.read_csv(f, encoding="utf-8-sig").assign(SEASON=f.name[:5]) for f in fs], ignore_index=True)
    d = d[d.EVENT_DATE.notna()].copy()
    d["EVENT_DATE"] = pd.to_datetime(d.EVENT_DATE, utc=True).dt.tz_localize(None).dt.normalize()
    assert d.EVENT_DATE.max() < CUT, "odds contain rows on or after 2026-10-15"
    return d


def market_probs(df: pd.DataFrame) -> pd.DataFrame:
    """Long frame EVENT_ID, RUNNER_NAME, snapshot, p. Per runner and snapshot: mid = mean of 1/best_back and 1/best_lay (whichever exist);
    then the two runners are normalised to sum to 1 (removes the overround). An event-snapshot without two priced runners is dropped."""
    snaps = [c[len("BEST_BACK_"):] for c in df.columns if c.startswith("BEST_BACK_")]
    out = []
    for s in snaps:
        inv = 1.0 / df[[f"BEST_BACK_{s}", f"BEST_LAY_{s}"]].astype(float).where(lambda x: x > 1.0)
        d = pd.DataFrame({"EVENT_ID": df.EVENT_ID.to_numpy(), "RUNNER_NAME": df.RUNNER_NAME.to_numpy(), "snapshot": s, "mid": inv.mean(axis=1, skipna=True).to_numpy()})
        d = d.dropna(subset=["mid"])
        d = d[d.groupby("EVENT_ID").mid.transform("size") == 2]
        d["p"] = d.mid / d.groupby("EVENT_ID").mid.transform("sum")
        out.append(d.drop(columns="mid"))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["EVENT_ID", "RUNNER_NAME", "snapshot", "p"])


# ---------- join to Cricsheet ----------
def cricsheet_bbl() -> pd.DataFrame:
    """Men's BBL matches before the lock date: match_id (str), date, season, team1, team2, winner, result, outcome_method."""
    from ..db import query

    m = query(f"select match_id, date, season, team1, team2, winner, result, outcome_method from matches "
              f"where competition = 'bbl' and gender = 'male' and date < '{CUT.date()}'")
    m["match_id"] = m.match_id.astype(str)
    m["date"] = pd.to_datetime(m.date)
    return m


def _canon(n):
    return NAME_MAP.get(n, n)


def join_events(odds: pd.DataFrame, db: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per odds event: EVENT_ID, SEASON, EVENT_DATE, team_a, team_b, bf_winner, match_id (NaN if unjoined), cs_team1, cs_team2,
    cs_date, cs_winner. Rule: same two teams and Cricsheet date within +-1 day of the Betfair date (UTC midnight); nearest date wins;
    a Cricsheet match is never used twice."""
    db = cricsheet_bbl() if db is None else db
    ev_rows = []
    for eid, g in odds.groupby("EVENT_ID", sort=False):
        a, b = sorted(g.RUNNER_NAME)
        w = g.loc[g.IS_WINNER == 1, "RUNNER_NAME"]
        ev_rows.append({"EVENT_ID": eid, "SEASON": g.SEASON.iloc[0] if "SEASON" in g else None, "EVENT_DATE": pd.Timestamp(g.EVENT_DATE.iloc[0]),
                        "team_a": a, "team_b": b, "bf_winner": w.iloc[0] if len(w) == 1 else None})
    ev_df = pd.DataFrame(ev_rows).sort_values(["EVENT_DATE", "EVENT_ID"]).reset_index(drop=True)
    d = db.assign(_pair=[frozenset((_canon(x), _canon(y))) for x, y in zip(db.team1, db.team2)], _date=pd.to_datetime(db.date))
    used, res = set(), []
    for r in ev_df.itertuples():
        pair = frozenset((_canon(r.team_a), _canon(r.team_b)))
        c = d[(d._pair == pair) & ((d._date - r.EVENT_DATE).abs() <= pd.Timedelta(days=1)) & ~d.match_id.isin(used)]
        if len(c):
            c = c.assign(_gap=(c._date - r.EVENT_DATE).abs()).sort_values(["_gap", "_date"]).iloc[0]
            used.add(c.match_id)
            res.append((c.match_id, c.team1, c.team2, c._date, c.winner))
        else:
            res.append((np.nan, None, None, pd.NaT, None))
    ev_df[["match_id", "cs_team1", "cs_team2", "cs_date", "cs_winner"]] = pd.DataFrame(res, index=ev_df.index)
    return ev_df


# ---------- out-of-sample model predictions ----------
def season_starts() -> dict[str, pd.Timestamp]:
    m = cricsheet_bbl()
    first = m.groupby("season").date.min()
    return {tag: first[f"{y}/{str(y + 1)[2:]}"] for tag, y in SEASONS.items()}


def _prep_all():
    """Features for every competition (prior-only features); refuses rows of the lock."""
    from . import direct as D
    from . import features as F
    from .dataset import load
    from .predict import KT, KV

    states, inn = load()
    assert states.date.max() < CUT and inn.date.max() < CUT
    return D.prep(F.build_features(states, inn, KV, KT))


def _g1(feat, Y, S, test, log):
    """G1 chase classifier for the BBL season of season_year Y that starts on date S. Config picked on IPL Y (train: IPL seasons < Y), early
    stopping on IPL Y (train: all seasons < Y), final fit on every row dated before S (balls_bowled % 4 == 0). Same recipe as s4b.run_score."""
    from . import direct as D
    from . import features as F
    from .s4b import NO_SEASON

    full = F.FEATURE_SETS["full"]
    val = feat[(feat.competition == "ipl") & (feat.season_year == Y) & (feat.balls_bowled % 2 == 0)]
    assert val.date.max() < S
    ttr, tw = D.pool_rows(feat, "ipl_all", Y + 1, last=Y)
    best = min((D.fit_win(ttr, tw, full, cfg, val=val)[0].best_score["valid_0"]["binary_logloss"], i) for i, cfg in enumerate(D.CONFIGS))
    cfg = D.CONFIGS[best[1]]
    itr, iw = D.pool_rows(feat, "global", Y + 1, last=Y)
    _, n = D.fit_win(itr, iw, NO_SEASON, cfg, val=val)
    tr = feat[(feat.date < S) & (feat.balls_bowled % 4 == 0)]
    m, _ = D.fit_win(tr, np.ones(len(tr)), NO_SEASON, cfg, rounds=n)
    log(f"  G1: cfg {best[1]}, {n} trees, train rows {len(tr)}, cutoff {tr.date.max().date()}")
    t2 = D.win_rows(test)
    return pd.Series(m.predict(t2[NO_SEASON]), index=t2.index), tr.date.max()


def _fchase(S, test_keys, log):
    """F-chase (fair logistic) with the all-men's resource table, fitted on men's states dated before S."""
    from . import fair_report as FR
    from .baselines import FChase, LevelResource

    s = FR.load()  # men's states with lvl_ew; asserts no lock rows
    tr = s[s.date < S]
    tab = LevelResource("all").fit(tr)
    ch = FChase(tab).fit(tr)
    t = s[s.innings.eq(2) & s.balls_bowled.isin(CP)].merge(test_keys.astype({"match_id": str}), on=["match_id", "innings", "balls_bowled"])
    log(f"  F-chase: train states {len(tr)}, cutoff {tr.date.max().date()}")
    return pd.DataFrame({"match_id": t.match_id.astype(str).to_numpy(), "balls_bowled": t.balls_bowled.to_numpy(), "p": ch.win(t).to_numpy()}), tr.date.max()


def _simb(balls, Y, S, keys, log, n=1000):
    """sim-B (ball simulator, men's pool): early stop on IPL Y with train seasons < Y, refit on every ball dated before S, 1000 paths."""
    from .ball_model import BallModel
    from .simulate import fill_missing_batter, simulate, start_states

    b = balls[~balls.reduced & balls.lvl_slow.notna() & (balls.match_date < S)]
    va = b[(b.competition == "ipl") & (b.season_year == Y)]
    m = BallModel("B").fit(b[b.season_year < Y], va)
    rounds = int(m.best_iter * 1.1) + 1
    m = BallModel("B").fit(b, None, n_rounds=rounds)
    log(f"  sim-B: {rounds} rounds, train balls {len(b)}, cutoff {b.match_date.max().date()}")
    tb = balls[balls.match_id.isin(keys.match_id.unique()) & ~balls.reduced & balls.lvl_slow.notna()]
    out = []
    for k, kk in keys.groupby("balls_bowled"):
        st = fill_missing_batter(start_states(tb, kk[["match_id", "innings"]].to_numpy(), int(k)), m)
        res = simulate(m, st, n=n, seed=int(k))
        out.append(pd.DataFrame({"match_id": st.match_id.astype(str).to_numpy(), "balls_bowled": st.balls_bowled.to_numpy(), "p": np.clip(res["win"], 0.5 / n, 1 - 0.5 / n)}))  # a count of 0 or n paths is not a probability of exactly 0 or 1: half-path continuity clip
    return pd.concat(out, ignore_index=True), b.match_date.max()


def build_predictions(tags=None, log=print):
    """Per BBL season: G1, sim-B, ens-G1 (mean of the two), F-chase at chase states of 36/60/90 balls; caches market_preds_<tag>.parquet,
    then concatenates to market_preds.parquet. Every model is fitted only on rows dated before the season's first match."""
    from . import direct as D
    from .ball_model import load_balls

    starts = season_starts()
    feat = _prep_all()
    balls = load_balls()
    for tag in tags or SEASONS:
        f = ML_DIR / f"market_preds_{tag}.parquet"
        if f.exists():
            continue
        t0, Y, S = time.time(), SEASONS[tag], starts[tag]
        log(f"{tag} (season_year {Y}, starts {S.date()})")
        test = feat[(feat.competition == "bbl") & (feat.gender == "male") & (feat.season_year == Y) & (feat.date >= S)
                    & feat.balls_bowled.isin(CP) & (feat.innings == 2)]
        assert test.date.max() < CUT
        t2 = D.win_rows(test)
        g1, c_g1 = _g1(feat, Y, S, test, log)
        keys = t2[["match_id", "innings", "balls_bowled"]].astype({"match_id": str})
        info = t2[["match_id", "balls_bowled", "date", "chase_won"]].astype({"match_id": str}).assign(G1=g1.to_numpy())
        fc, c_fc = _fchase(S, keys, log)
        info = info.merge(fc.rename(columns={"p": "F-chase"}), on=["match_id", "balls_bowled"], how="left")
        sb, c_sb = _simb(balls, Y, S, keys, log)
        info = info.merge(sb.rename(columns={"p": "sim-B"}), on=["match_id", "balls_bowled"], how="left")
        info["ens-G1"] = (info["G1"] + info["sim-B"]) / 2
        cut = {"G1": c_g1, "sim-B": c_sb, "ens-G1": max(c_g1, c_sb), "F-chase": c_fc}
        long = info.melt(id_vars=["match_id", "balls_bowled", "date", "chase_won"], value_vars=list(MODELS), var_name="model", value_name="p")
        long = long.assign(season=tag, season_start=S, train_cutoff=long.model.map(cut), y=long.chase_won)
        assert (long.train_cutoff < S).all()
        long.to_parquet(f)
        log(f"{tag} done: {len(info)} states, {info.match_id.nunique()} matches, nan {info[list(MODELS)].isna().sum().to_dict()}, {time.time() - t0:.0f}s")
    p = pd.concat([pd.read_parquet(ML_DIR / f"market_preds_{t}.parquet") for t in SEASONS])
    p.to_parquet(ML_DIR / "market_preds.parquet")
    return p


def load_predictions() -> pd.DataFrame:
    """Out-of-sample predictions: match_id, balls_bowled, date, season, season_start, train_cutoff, model, p, y."""
    f = ML_DIR / "market_preds.parquet"
    if not f.exists():
        raise FileNotFoundError(f)
    return pd.read_parquet(f)


# ---------- benchmark ----------
def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _chasers() -> pd.Series:
    """match_id (str) -> batting team of innings 2 (Cricsheet), non-reduced or not (reduced matches simply have no model row)."""
    from .dataset import OUT_DIR

    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet", columns=["match_id", "innings", "batting_team", "competition", "gender"])
    inn = inn[(inn.innings == 2) & (inn.competition == "bbl") & (inn.gender == "male")]
    return inn.assign(match_id=inn.match_id.astype(str)).set_index("match_id").batting_team


def rows_table() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(rows, joined events, accounting). rows: one per match and chase checkpoint with y (chaser won), p_market, p_<model> for the four models."""
    odds = load_odds()
    j = join_events(odds, cricsheet_bbl())
    mp = market_probs(odds)
    pr = load_predictions()
    wide = pr.pivot_table(index=["match_id", "balls_bowled", "date", "season", "y"], columns="model", values="p").reset_index()
    wide = wide.rename(columns={m: f"p_{m}" for m in MODELS})
    wide["chaser"] = wide.match_id.map(_chasers())
    wide = wide.merge(j[["EVENT_ID", "match_id"]], on="match_id", how="left")
    rows, acc = [], []
    for b, snap in SNAP.items():
        m = mp[mp.snapshot == snap].rename(columns={"p": "p_market"})
        m["RUNNER_NAME"] = m.RUNNER_NAME.map(_canon)
        w = wide[wide.balls_bowled == b].merge(m[["EVENT_ID", "RUNNER_NAME", "p_market"]], left_on=["EVENT_ID", "chaser"], right_on=["EVENT_ID", "RUNNER_NAME"], how="left")
        acc.append({"balls": b, "events_joined": int(j.match_id.notna().sum()), "model_rows": len(w), "market_missing": int(w.p_market.isna().sum()), "both": int(w.p_market.notna().sum())})
        rows.append(w[w.p_market.notna()].drop(columns="RUNNER_NAME"))
    rows = pd.concat(rows, ignore_index=True)
    rows["over"] = rows.balls_bowled // 6
    return rows, j, pd.DataFrame(acc)


def compare(df: pd.DataFrame, model_cols: list[str], mkt="p_market", n_boot=2000) -> pd.DataFrame:
    """Per model column: n, log loss model / market, paired difference (model - market) with the match bootstrap and the season-block
    bootstrap (two-sided 95%), Brier and accuracy of both, calibration_test of both. df needs y, match_id, season and the p columns."""
    from . import evaluate as ev

    out = []
    for c in model_cols:
        d = df.assign(ll_m=lambda x, c=c: -(x.y * np.log(np.clip(x[c], 1e-6, 1)) + (1 - x.y) * np.log(np.clip(1 - x[c], 1e-6, 1))),
                      ll_k=lambda x: -(x.y * np.log(np.clip(x[mkt], 1e-6, 1)) + (1 - x.y) * np.log(np.clip(1 - x[mkt], 1e-6, 1))))
        f = lambda x: float((x.ll_m - x.ll_k).mean())  # noqa: E731
        e, lo, hi, nm = ev.match_bootstrap(d, f, n=n_boot)
        _, slo, shi, nb = ev.season_block_bootstrap(d, f, block_cols=("season",), n=n_boot)
        per = d.groupby("season").apply(lambda x: float((x.ll_m - x.ll_k).mean()), include_groups=False)
        cm, ck = ev.calibration_test(d.y, d[c], groups=d.match_id), ev.calibration_test(d.y, d[mkt], groups=d.match_id)
        out.append({"model": c, "n": len(d), "ll_model": d.ll_m.mean(), "ll_market": d.ll_k.mean(), "diff": e, "m_lo": lo, "m_hi": hi, "s_lo": slo, "s_hi": shi, "blocks": nb,
                    "seasons_model_better": int((per < 0).sum()),
                    "brier_model": ev.brier(d.y, d[c]), "brier_market": ev.brier(d.y, d[mkt]),
                    "acc_model": float(((d[c] > 0.5) == (d.y == 1)).mean()), "acc_market": float(((d[mkt] > 0.5) == (d.y == 1)).mean()),
                    "cal_model": f"a={cm['intercept']:+.2f} b={cm['slope']:.2f} ece={cm['ece']:.3f} (null p95 {cm['ece_null_p95']:.3f}) {'pass' if cm['pass_primary'] else 'fail'}",
                    "cal_market": f"a={ck['intercept']:+.2f} b={ck['slope']:.2f} ece={ck['ece']:.3f} (null p95 {ck['ece_null_p95']:.3f}) {'pass' if ck['pass_primary'] else 'fail'}"})
    return pd.DataFrame(out)


def blend(df: pd.DataFrame, c: str, mkt="p_market") -> pd.Series:
    """50/50 average of the logits of model column c and the market."""
    return pd.Series(1 / (1 + np.exp(-(_logit(df[c]) + _logit(df[mkt])) / 2)), index=df.index)


def report(log=print):
    rows, j, acc = rows_table()
    rows.to_parquet(ML_DIR / "market_rows.parquet")
    log("ACCOUNTING\n" + acc.to_string(index=False))
    log(f"join: {int(j.match_id.notna().sum())}/{len(j)} events; unjoined: {j[j.match_id.isna()][['EVENT_ID', 'SEASON', 'EVENT_DATE', 'team_a', 'team_b']].to_dict('records')}")
    d = j[j.match_id.notna() & j.cs_winner.notna()]
    log(f"winner agreement: {(d.bf_winner == d.cs_winner).mean():.4f} of {len(d)} decided joined matches")
    res = {}
    for b in CP:
        r = rows[rows.balls_bowled == b].copy()
        r["p_blend"] = blend(r, "p_ens-G1")
        t = compare(r, ["p_ens-G1", "p_G1", "p_sim-B", "p_F-chase", "p_blend"])
        res[b] = t
        log(f"\n=== chase {b // 6} overs (n={len(r)}; per season {r.groupby('season').size().to_dict()}) ===\n" + t.round(4).to_string(index=False))
    pd.concat(res, names=["balls"]).to_csv(ML_DIR / "market_report.csv")
    return rows, res


def first_ball(log=print):
    """Secondary: market at the first ball vs the pre-match model (prematch.py), fitted per season on matches dated before its start.
    p = P(team A wins), A = alphabetically first team (prematch's convention). Two model variants: toss unknown ('logit') and toss known."""
    from . import prematch as PM

    odds = load_odds()
    j = join_events(odds, cricsheet_bbl())
    mp = market_probs(odds)
    M = PM.load_matches(drop_locked=False)
    M = M[M.date < CUT].assign(match_id=lambda x: x.match_id.astype(str))
    T = PM.table(M, PM._load_params())
    starts, out = season_starts(), []
    for tag in SEASONS:
        tr = T[(T.date < starts[tag]) & (T.gender == "male")]
        ids = j[(j.SEASON == tag) & j.match_id.notna()].match_id
        W, _ = PM._eval(tr, T[T.match_id.isin(ids)], ("level",), tag)
        out.append(W.assign(season=tag, train_cutoff=tr.date.max(), season_start=starts[tag]))
    W = pd.concat(out, ignore_index=True)
    assert (W.train_cutoff < W.season_start).all()
    m = mp[mp.snapshot == "FIRST_BALL"].rename(columns={"p": "p_market"})
    W = W.merge(j[["match_id", "EVENT_ID", "team_a"]], on="match_id").merge(m, left_on=["EVENT_ID", "team_a"], right_on=["EVENT_ID", "RUNNER_NAME"])
    W = W.rename(columns={"logit": "p_prematch (toss unknown)", "logit+toss": "p_prematch (toss known)"})
    W = W[W.y.notna() & W["p_prematch (toss known)"].notna()]
    t = compare(W, ["p_prematch (toss unknown)", "p_prematch (toss known)"])
    log(f"\n=== first ball vs pre-match model (n={len(W)}) ===\n" + t.round(4).to_string(index=False))
    W.to_parquet(ML_DIR / "market_rows_firstball.parquet")
    return W, t


if __name__ == "__main__" and sys.argv[1:2] == ["report"]:
    report()
    first_ball()


if __name__ == "__main__":
    if sys.argv[1:2] == ["preds"]:
        t0 = time.time()
        build_predictions(log=lambda m: print(f"[{time.time() - t0:5.0f}s] {m}", flush=True))
