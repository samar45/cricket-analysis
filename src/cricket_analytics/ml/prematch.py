"""Pre-match prediction (before the toss): expected first-innings score range for each side + P(team A wins).

  from cricket_analytics.ml.prematch import predict
  predict("ipl", "Wankhede Stadium", "Mumbai Indians", "Chennai Super Kings", date="2026-04-10")

Everything is PRIOR-ONLY: team / venue / level state for a match on date D comes from matches dated < D (same-day matches
do not see each other). One chronological pass (`roll`) builds the feature table for the backtest and, stopped at D, the
state for a live forecast, so both use the same code.
  score  = level (competition, decayed mean) + a*venue + b*bat-team attack + c*bowl-team defence (weighted OLS) ; 10/50/90 =
           recent residual quantiles of the competition
  win    = antisymmetric logistic (no intercept) on Elo difference, run-margin strength difference, home, [toss]
           -> swapping the teams gives exactly 1 - p when the toss is unknown
XI strength is NOT used (not prior-only cheap; xi_a / xi_b are accepted and ignored).

  python -m cricket_analytics.ml.prematch tune | backtest | fit | fresh
"""

import json
import sys
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ..db import query
from ..reference import REFERENCE_DIR
from . import evaluate as ev
from .dataset import OUT_DIR
from .features import HL_LEVEL, PRIOR_MEAN, PRIOR_W, _decay

MODEL_DIR = OUT_DIR / "models" / "prematch"
LEAGUES = ev.FRESH_LEAGUES
DEFAULT = {"k_venue": 30.0, "k_team": 15.0, "hl_team": 12.0, "elo_gap": 120,
           "elo_k_nat": 20.0, "elo_reg_nat": 1.0, "elo_k_fr": 20.0, "elo_reg_fr": 0.8}  # nat = national teams (t20i), fr = franchise leagues
WIN_SETS = {"elo": ["elo"], "logit": ["elo", "strength", "home"], "logit+toss": ["elo", "strength", "home", "toss", "toss_dec"]}
MIN_OWN = 250
SCORE_X = ["venue_eff", "att", "dfn"]


# ---------- data ----------
def load_matches(drop_locked=True) -> pd.DataFrame:
    """One row per match (A = alphabetically first team), with first-innings total, toss and winner."""
    m = query("SELECT match_id, date, competition, gender, venue, city, team1, team2, toss_winner, toss_decision, winner FROM matches WHERE gender IN ('male','female')")
    i = pd.read_parquet(OUT_DIR / "states_innings.parquet")
    i = i[i.innings == 1][["match_id", "final_total", "batting_team", "bowling_team", "reduced"]]
    m = m.merge(i, on="match_id", how="left")
    m["date"] = pd.to_datetime(m["date"])
    m["a"] = np.where(m.team1 < m.team2, m.team1, m.team2)
    m["b"] = np.where(m.team1 < m.team2, m.team2, m.team1)
    m["reduced"] = m.reduced.fillna(True).astype(bool) | m.final_total.isna()
    m = m.sort_values(["date", "match_id"], kind="stable").reset_index(drop=True)
    if drop_locked:
        m = m[~ev.fresh_holdout_mask(m)].reset_index(drop=True)
    return m


@lru_cache(maxsize=1)
def _ref():
    v = pd.read_csv(REFERENCE_DIR / "venue_country.csv", keep_default_na=False).drop_duplicates("venue").set_index("venue")
    t = {}
    for r in pd.read_csv(REFERENCE_DIR / "team_home.csv", keep_default_na=False).itertuples():
        t[r.team] = (r.kind, {x for x in r.home.split(";") if x}, {int(x[:4]) for x in r.no_home_seasons.split(";") if x})
    return v, t


def is_home(team, venue, year) -> int:
    v, t = _ref()
    if venue not in v.index or team not in t:
        return 0
    kind, places, nohome = t[team]
    r = v.loc[venue]
    if kind == "national":
        return int(r.country in places or r.region in places)
    return int(kind == "franchise" and r.site in places and year not in nohome)


# ---------- rolling state ----------
def new_state():
    return {"lvl": {}, "ven": {}, "att": {}, "dfn": {}, "elo": {}}


def grp(comp):
    return "nat" if comp == "t20i" else "fr"


def _elo(S, key, date, P, gp):
    r, last = S["elo"].get(key, (1500.0, None))
    if last is not None and (date - last).days > P["elo_gap"]:
        r = 1500.0 + (r - 1500.0) * P[f"elo_reg_{gp}"]
    return r


def features(S, P, g, comp, venue, a, b, date, home_a=0, home_b=0) -> dict:
    """Prior-only features of a match between a and b from state S."""
    s, w = S["lvl"].get((g, comp), (0.0, 0.0))
    ew = (s + PRIOR_W * PRIOR_MEAN) / (w + PRIOR_W)
    vs, vn = S["ven"].get((g, venue), (0.0, 0))
    kt = P["k_team"]
    eff = lambda d, t: d.get((g, t), (0.0, 0.0))[0] / (d.get((g, t), (0.0, 0.0))[1] + kt)  # noqa: E731
    return {"lvl": ew, "venue_eff": vs / (vn + P["k_venue"]), "venue_n": vn,
            "att_a": eff(S["att"], a), "dfn_a": eff(S["dfn"], a), "att_b": eff(S["att"], b), "dfn_b": eff(S["dfn"], b),
            "elo_a": _elo(S, (g, a), date, P, grp(comp)), "elo_b": _elo(S, (g, b), date, P, grp(comp)), "home": home_a - home_b}


def update(S, P, r, f):
    """Add a finished match (row r, features f recorded BEFORE it) to the state."""
    g, comp = r.gender, r.competition
    if not r.reduced:
        x = float(r.final_total)
        bat, bowl = r.batting_team, r.bowling_team
        dl, dt = _decay(HL_LEVEL), _decay(P["hl_team"])
        s, w = S["lvl"].get((g, comp), (0.0, 0.0))
        S["lvl"][(g, comp)] = (s * dl + x, w * dl + 1.0)
        vs, vn = S["ven"].get((g, r.venue), (0.0, 0))
        S["ven"][(g, r.venue)] = (vs + x - f["lvl"], vn + 1)
        res = x - f["lvl"] - f["venue_eff"]
        for d, t in ((S["att"], bat), (S["dfn"], bowl)):
            u, c = d.get((g, t), (0.0, 0.0))
            d[(g, t)] = (u * dt + res, c * dt + 1.0)
    if r.winner in (r.a, r.b):
        ea = 1 / (1 + 10 ** ((f["elo_b"] - f["elo_a"]) / 400))
        sa = float(r.winner == r.a)
        k = P[f"elo_k_{grp(comp)}"]
        S["elo"][(g, r.a)] = (f["elo_a"] + k * (sa - ea), r.date)
        S["elo"][(g, r.b)] = (f["elo_b"] - k * (sa - ea), r.date)


def roll(M, P=DEFAULT, stop=None):
    """Chronological pass. Returns (feature table of every match before `stop`, state after them)."""
    S, rows = new_state(), []
    for date, day in M.groupby("date", sort=True):
        if stop is not None and date >= stop:
            break
        fs = []
        for r in day.itertuples(index=False):
            f = features(S, P, r.gender, r.competition, r.venue, r.a, r.b, date, is_home(r.a, r.venue, date.year), is_home(r.b, r.venue, date.year))
            fs.append(f)
            rows.append({"match_id": r.match_id, **f})
        for r, f in zip(day.itertuples(index=False), fs):  # update AFTER the whole day was read
            update(S, P, r, f)
    return pd.DataFrame(rows), S


def table(M, P=DEFAULT):
    """Match table with prior-only features and targets (columns of M kept)."""
    F, _ = roll(M, P)
    d = M.merge(F, on="match_id")
    d["strength"] = ((d.att_a - d.dfn_a) - (d.att_b - d.dfn_b)) / 10.0
    d["elo"] = (d.elo_a - d.elo_b) / 400.0
    d["toss"] = np.where(d.toss_winner == d.a, 1.0, np.where(d.toss_winner == d.b, -1.0, 0.0))
    d["toss_dec"] = d.toss * np.where(d.toss_decision == "bat", 1.0, -1.0)
    d["y"] = np.where(d.winner == d.a, 1.0, np.where(d.winner == d.b, 0.0, np.nan))
    d["grp"] = np.where(d.competition == "t20i", "nat", "fr")
    d["bat_first_a"] = d.batting_team == d.a
    # score features for the side that actually batted first
    d["att"] = np.where(d.bat_first_a, d.att_a, d.att_b)
    d["dfn"] = np.where(d.bat_first_a, d.dfn_b, d.dfn_a)
    return d


# ---------- models ----------
def fit_score(T, half_life_years=2.0):
    """Weighted OLS of (total - level) on venue / attack / defence; residual quantiles by competition."""
    t = T[~T.reduced & T.final_total.notna()]
    age = (t.date.max() - t.date).dt.days / 365.25
    w = 0.5 ** (age / half_life_years)
    X = np.c_[np.ones(len(t)), t[SCORE_X].to_numpy()]
    sw = np.sqrt(w.to_numpy())[:, None]
    beta = np.linalg.lstsq(X * sw, ((t.final_total - t.lvl).to_numpy()[:, None]) * sw, rcond=None)[0].ravel()
    res = t.assign(res=t.final_total - t.lvl - X @ beta)
    qs = lambda x: [float(v) for v in np.quantile(x, [0.1, 0.5, 0.9])]  # noqa: E731
    out = {"beta": beta.tolist(), "q": {"all": qs(res.res.tail(600))}}
    for (g, c), x in res.groupby(["gender", "competition"]):
        if len(x) >= 150:
            out["q"][f"{g}|{c}"] = qs(x.res.tail(400))
    return out


def score_pred(model, kind, lvl, venue_eff, att, dfn, g, comp):
    """q10/q50/q90 arrays. kind: 'level' (a), 'venue' (lvl+venue), 'full'."""
    b = model["beta"]
    mu = lvl + b[0]
    if kind in ("venue", "full"):
        mu = mu + b[1] * venue_eff
    if kind == "full":
        mu = mu + b[2] * att + b[3] * dfn
    comps = np.broadcast_to(np.asarray(comp, dtype=object), np.shape(mu))
    q = np.array([model["q"].get(f"{g}|{c}", model["q"]["all"]) for c in comps.ravel()]).reshape(np.shape(mu) + (3,))
    return mu + q[..., 0], mu + q[..., 1], mu + q[..., 2]


def fit_win(T, cols, C=1.0):
    t = T[T.y.notna()]
    X = t[cols].to_numpy()
    lr = LogisticRegression(C=C, fit_intercept=False)
    lr.fit(np.r_[X, -X], np.r_[t.y.to_numpy(), 1 - t.y.to_numpy()])  # swap augmentation: exactly antisymmetric
    return {"cols": cols, "coef": lr.coef_.ravel().tolist()}


def fit_models(tr):
    """{group: {'score': ..., 'win': {name: model}}} fitted on a training table (falls back to all rows for a thin group)."""
    out = {}
    for gp in ("nat", "fr"):
        t = tr[tr.grp == gp]
        t = t if len(t) >= 300 else tr
        out[gp] = {"score": fit_score(t), "win": {k: fit_win(t, c) for k, c in WIN_SETS.items()}}
    for c, t in tr.groupby("competition"):  # a competition with enough history gets its own coefficients
        if c != "t20i" and len(t) >= MIN_OWN:
            out[c] = {"score": fit_score(t), "win": {k: fit_win(t, c_) for k, c_ in WIN_SETS.items()}}
    return out


def _mkey(df, mods):
    return df.competition.where(df.competition.isin(list(mods)) & (df.competition != "t20i"), df.grp)


def win_pred(model, X):
    return 1 / (1 + np.exp(-(np.asarray(X) @ np.array(model["coef"]))))


# ---------- backtest ----------
def folds():
    """name -> (train mask fn, test mask fn) on a table T."""
    yr = lambda T: T.date.dt.year  # noqa: E731
    out = {f"ipl{y}": ((lambda T, y=y: T.date < pd.Timestamp(y, 1, 1)), (lambda T, y=y: (T.competition == "ipl") & (yr(T) == y))) for y in range(2022, 2027)}
    for y in (2024, 2025):
        out[f"lg{y}"] = ((lambda T, y=y: T.date < pd.Timestamp(y, 1, 1)), (lambda T, y=y: T.competition.isin(LEAGUES) & (yr(T) == y) & (T.gender == "male")))
    return out


def eval_fold(T, name, kinds=("level", "venue", "full")):
    """Returns (win frame, score frame): one row per match with a prediction per model."""
    tr_f, te_f = folds()[name]
    tr, te = T[tr_f(T) & (T.gender == "male")], T[te_f(T)]
    return _eval(tr, te, kinds, name)


def _eval(tr, te, kinds, name):
    mods = fit_models(tr)
    tw = te[te.y.notna()]
    W = tw[["match_id", "date", "competition", "y"]].copy()
    W["base"] = 0.5
    for k, cols in WIN_SETS.items():
        W[k] = np.nan
        for gp, m in mods.items():
            sel = (_mkey(tw, mods) == gp).to_numpy()
            if sel.any():
                W.loc[sel, k] = win_pred(m["win"][k], tw.loc[sel, cols])
    ts = te[~te.reduced & te.final_total.notna() & te.bat_first_a.notna()]
    S = ts[["match_id", "date", "competition", "final_total"]].copy()
    for k in kinds:
        for c in ("q10", "q50", "q90"):
            S[f"{k}_{c}"] = np.nan
        for gp, m in mods.items():
            sel = (_mkey(ts, mods) == gp).to_numpy()
            if sel.any():
                x = ts[sel]
                q = score_pred(m["score"], k, x.lvl.to_numpy(), x.venue_eff.to_numpy(), x.att.to_numpy(), x.dfn.to_numpy(), "male", x.competition.to_numpy())
                S.loc[sel, [f"{k}_q10", f"{k}_q50", f"{k}_q90"]] = np.c_[q]
    S["fold"] = W["fold"] = name
    return W, S


def metrics(W, S):
    win = {k: ev.win_metrics(W.y, W[k]) | {"acc": float(((W[k] > 0.5) == (W.y == 1)).mean())} for k in ["base"] + list(WIN_SETS)}
    kinds = sorted({c.split("_")[0] for c in S.columns if c.endswith("_q50")})
    sc = {k: ev.score_metrics(S.final_total, S[f"{k}_q10"], S[f"{k}_q50"], S[f"{k}_q90"]) for k in kinds}
    return win, sc


def boot(d, n=2000, seed=0):
    """Paired bootstrap over matches of mean(d); returns (point, p5, p95). d is a per-match series."""
    d = np.asarray(d, float)
    r = np.random.default_rng(seed)
    est = d[r.integers(0, len(d), (n, len(d)))].mean(1)
    return d.mean(), *np.quantile(est, [0.05, 0.95])


def ll_each(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


# ---------- tune (pre-2022 data only) ----------
def tune(M):
    """Pick Elo k / regression per group and k_venue / k_team on data dated < 2022 (fit < 2020, validate 2020-21)."""
    M = M[M.date < "2022-01-01"]
    best = dict(DEFAULT)

    def val(P, gp):
        T = table(M, P)
        tr, te = T[(T.date < "2020-01-01") & (T.gender == "male") & (T.grp == gp)], T[(T.date >= "2020-01-01") & (T.gender == "male") & (T.grp == gp)]
        wm = fit_win(tr, ["elo"])
        tw = te[te.y.notna()]
        ll = float(ev.log_loss(tw.y, win_pred(wm, tw[["elo"]])))
        sm = fit_score(tr)
        ts = te[~te.reduced & te.final_total.notna()]
        q = score_pred(sm, "full", ts.lvl.to_numpy(), ts.venue_eff.to_numpy(), ts.att.to_numpy(), ts.dfn.to_numpy(), "male", ts.competition.to_numpy())
        return ll, float(np.abs(ts.final_total - q[1]).mean())

    out = []
    for gp in ("nat", "fr"):
        rows = [{"grp": gp, "elo_k": ek, "elo_reg": er, "logloss": val({**best, f"elo_k_{gp}": ek, f"elo_reg_{gp}": er}, gp)[0]} for ek in (10, 20, 30) for er in (0.4, 0.6, 0.8, 1.0)]
        e = pd.DataFrame(rows)
        b = e.sort_values("logloss").iloc[0]
        best.update({f"elo_k_{gp}": float(b.elo_k), f"elo_reg_{gp}": float(b.elo_reg)})
        out.append(e)
    rows = []
    for gp in ("nat", "fr"):
        for kv in (30, 100, 300, 1000):
            for kt in (2, 5, 15):
                rows.append({"grp": gp, "k_venue": kv, "k_team": kt, "mae": val({**best, "k_venue": kv, "k_team": kt}, gp)[1]})
    s_ = pd.DataFrame(rows)
    # k_venue / k_team are shared: choose by summed MAE over both groups
    t = s_.groupby(["k_venue", "k_team"]).mae.sum().reset_index().sort_values("mae").iloc[0]
    best.update(k_venue=float(t.k_venue), k_team=float(t.k_team))
    return best, pd.concat(out), s_


# ---------- live prediction ----------
def _fit_all(T):
    out = {"male": fit_models(T[T.gender == "male"])}
    fw = T[T.gender == "female"]
    if len(fw) > 300:
        out["female"] = fit_models(fw)
    return out


def fit_final(P=None, drop_locked=False):
    """Fit on every match in the DB and save to data/external/ml/models/prematch/model.json."""
    M = load_matches(drop_locked=drop_locked)
    P = P or _load_params()
    T = table(M, P)
    obj = {"params": P, "fitted_through": str(M.date.max().date()), "models": _fit_all(T)}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    (MODEL_DIR / "model.json").write_text(json.dumps(obj, indent=1))
    return obj


def _load_params():
    p = MODEL_DIR / "params.json"
    return json.loads(p.read_text()) if p.exists() else dict(DEFAULT)


@lru_cache(maxsize=1)
def _bundle():
    return json.loads((MODEL_DIR / "model.json").read_text()), load_matches(drop_locked=False)


@lru_cache(maxsize=16)
def _state(stop_iso, n_matches):
    obj, M = _bundle()
    return roll(M, obj["params"], stop=pd.Timestamp(stop_iso))[1]


def _resolve(name, values):
    """Exact name, else the most frequent known name that contains (or is contained in) it ignoring case, else unchanged."""
    if name is None or name in values.values:
        return name
    n = name.lower()
    c = values[values.str.lower().map(lambda v: n in v or v in n)]
    return c.value_counts().index[0] if len(c) else name


def predict_from(M, obj, competition, venue, team_a, team_b, date=None, toss_winner=None, toss_decision=None, gender=None) -> dict:
    """Core of predict(): state is built ONLY from rows of M dated before `date` (testable prior-only)."""
    P = obj["params"]
    mm = M[M.gender == ("female" if competition == "t20i_women" else gender or "male")]
    teams = pd.concat([mm.a, mm.b], ignore_index=True)
    venue, team_a, team_b = _resolve(venue, mm.venue.dropna()), _resolve(team_a, teams), _resolve(team_b, teams)
    toss_winner = _resolve(toss_winner, teams) if toss_winner else None
    comp, g = ("t20i", "female") if competition == "t20i_women" else (competition, gender or "male")
    d = pd.Timestamp(date) if date is not None else M.date.max() + pd.Timedelta(days=1)
    S = roll(M, P, stop=d)[1]
    a, b = sorted([team_a, team_b])
    f = features(S, P, g, comp, venue, a, b, d, is_home(a, venue, d.year), is_home(b, venue, d.year))
    ms = obj["models"].get(g, obj["models"]["male"])
    mod = ms[comp if comp in ms else grp(comp)]
    sm = mod["score"]
    q_a = score_pred(sm, "full", f["lvl"], f["venue_eff"], f["att_a"], f["dfn_b"], g, comp)  # a bats first
    q_b = score_pred(sm, "full", f["lvl"], f["venue_eff"], f["att_b"], f["dfn_a"], g, comp)
    toss = 0.0
    if toss_winner in (a, b):
        toss = 1.0 if toss_winner == a else -1.0
    dec = toss * (1.0 if toss_decision == "bat" else -1.0 if toss_decision == "field" else 0.0)
    x = {"elo": (f["elo_a"] - f["elo_b"]) / 400.0, "strength": ((f["att_a"] - f["dfn_a"]) - (f["att_b"] - f["dfn_b"])) / 10.0,
         "home": f["home"], "toss": toss, "toss_dec": dec}
    key = "logit+toss" if toss else "logit"
    wm = mod["win"][key]
    p_ab = float(win_pred(wm, [[x[c] for c in wm["cols"]]])[0])
    if team_a != a:
        q_a, q_b, p_ab = q_b, q_a, 1 - p_ab
        fa, fb = "b", "a"
    else:
        fa, fb = "a", "b"
    r = lambda t: [round(float(v), 1) for v in t]  # noqa: E731
    return {"score_a_q10": r(q_a)[0], "score_a_q50": r(q_a)[1], "score_a_q90": r(q_a)[2],
            "score_b_q10": r(q_b)[0], "score_b_q50": r(q_b)[1], "score_b_q90": r(q_b)[2],
            "p_a_win": round(p_ab, 4),
            "parts": {"competition_level": round(f["lvl"], 1), "venue_effect": round(f["venue_eff"], 1), "venue_matches": int(f["venue_n"]),
                      "elo_a": round(f[f"elo_{fa}"], 0), "elo_b": round(f[f"elo_{fb}"], 0),
                      "attack_a": round(f[f"att_{fa}"], 1), "defence_a": round(f[f"dfn_{fa}"], 1),
                      "attack_b": round(f[f"att_{fb}"], 1), "defence_b": round(f[f"dfn_{fb}"], 1),
                      "home_a_minus_b": f["home"] * (1 if team_a == a else -1), "toss_used": bool(toss), "win_model": key,
                      "xi_used": False, "features_through": str((d - pd.Timedelta(days=1)).date()),
                      "note": "pre-match T20 results are close to a coin flip; expect p within about 0.35-0.65"}}


def predict(competition, venue, team_a, team_b, date=None, toss_winner=None, toss_decision=None, xi_a=None, xi_b=None) -> dict:
    """Pre-match forecast. competition: a key of competitions.py ('ipl', 't20i', 't20i_women', 'bbl', ...). score_a_* = team_a's
    first-innings score IF it bats first. date=None means 'now' (uses every match in the database). xi_a / xi_b are ignored."""
    obj, M = _bundle()
    return predict_from(M, obj, competition, venue, team_a, team_b, date, toss_winner, toss_decision)


# ---------- report ----------
def _inplay(S):
    """In-play models at ball 0 of innings 1 (they know the opening pair; nothing else about the match), keyed by match."""
    from . import v2

    out = {}
    for fold in S.fold.unique():
        a = v2.v1_frames(fold)[0] if fold.startswith("ipl") else None
        if a is not None:
            c = v2.v1_frames(fold)[2]
            out.setdefault("G1 (in-play v1, ball 0)", []).append(a[(a.balls_bowled == 0) & (a.innings == 1)])
            out.setdefault("sim-B (in-play, ball 0)", []).append(c[(c.balls_bowled == 0) & (c.innings == 1)])
        else:
            g = pd.read_parquet(OUT_DIR / f"v2_{fold}_S.parquet")
            out.setdefault("G1 (in-play v1, ball 0)", []).append(g[(g.balls_bowled == 0) & (g.innings == 1)])
            b = pd.read_parquet(OUT_DIR / "s2_preds_B_men_nonipl.parquet")
            out.setdefault("sim-B (in-play, ball 0)", []).append(b[(b.balls_bowled == 0) & (b.innings == 1)])
    return {k: pd.concat(v, ignore_index=True).drop_duplicates("match_id") for k, v in out.items()}


def report(W=None, S=None, name="dev"):
    if W is None:
        W, S = pd.read_parquet(OUT_DIR / "prematch_dev_W.parquet"), pd.read_parquet(OUT_DIR / "prematch_dev_S.parquet")
    groups = {"IPL 2022-25": [f"ipl{y}" for y in range(2022, 2026)], "IPL 2026 (seen)": ["ipl2026"], "Leagues 2024-25": ["lg2024", "lg2025"]}
    if name != "dev":
        groups = {name: list(W.fold.unique())}
    from .baselines import md as md_
    md = lambda df: md_(df, 4)  # noqa: E731
    lines = []
    wins = ["base", "elo", "logit", "logit+toss"]
    for gname, fl in groups.items():
        w, sc = W[W.fold.isin(fl)], S[S.fold.isin(fl)]
        rows = []
        for k in wins:
            m = ev.win_metrics(w.y, w[k])
            d = boot(ll_each(w.y.to_numpy(), w[k].to_numpy()) - ll_each(w.y.to_numpy(), w.base.to_numpy()))
            rows.append({"model": k, "n": len(w), "logloss": m["logloss"], "brier": m["brier"], "acc": float(((w[k] > 0.5) == (w.y == 1)).mean()), "ECE": m["ece"],
                         "logloss minus base [5%, 95%]": "-" if k == "base" else f"{d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}]"})
        lines += [f"\n**Win, {gname}**\n", md(pd.DataFrame(rows))]
        rows = []
        ip = _inplay(sc) if name == "dev" else {}
        common = set(sc.match_id)
        for v in ip.values():
            common &= set(v.match_id)
        sc2 = sc[sc.match_id.isin(common)]
        for k in ("level", "venue", "full"):
            m = ev.score_metrics(sc2.final_total, sc2[f"{k}_q10"], sc2[f"{k}_q50"], sc2[f"{k}_q90"])
            rows.append({"model": {"level": "(a) competition level", "venue": "level + venue", "full": "level + venue + teams"}[k], "n": len(sc2), **m})
        for k, v in ip.items():
            v = v[v.match_id.isin(common)]
            m = ev.score_metrics(v.final_total, v.q10, v.q50, v.q90)
            rows.append({"model": k, "n": len(v), **m})
        lines += [f"\n**First-innings score, {gname}** (same {len(common) if ip else len(sc)} matches for all rows)\n", md(pd.DataFrame(rows))]
    txt = "\n".join(lines)
    (OUT_DIR / f"prematch_report_{name}.md").write_text(txt, encoding="utf-8")
    plt = ev._plt()
    if plt is not None:
        fig, ax = plt.subplots(1, 2, figsize=(9, 4.2))
        for a, (gname, fl) in zip(ax, [(k, v) for k, v in groups.items() if k != "IPL 2026 (seen)"][:2]):
            w = W[W.fold.isin(fl)]
            a.plot([0, 1], [0, 1], "--", color="grey")
            for k in ("elo", "logit"):
                t = ev.reliability_table(w.y, w[k], 6)
                a.plot(t.pred, t.obs, "o-", ms=4, label=f"{k} (ECE {ev.ece(w.y, w[k], 6):.3f})")
            a.set(title=f"{gname}: P(team A wins), n={len(w)}", xlabel="predicted", ylabel="observed")
            a.legend(fontsize=7)
        fig.savefig(ev.IMG_DIR / f"ml_prematch_reliability_{name}.png", dpi=110, bbox_inches="tight")
        fig, ax = plt.subplots(figsize=(5, 4))
        for gname, fl in groups.items():
            w = W[W.fold.isin(fl)]
            ax.bar([f"{gname}\n{k}" for k in ("base", "elo", "logit")], [ev.log_loss(w.y, w[k]) - 0.6931 for k in ("base", "elo", "logit")])
        ax.axhline(0, color="k", lw=0.5)
        ax.set(title="log loss minus coin flip (below 0 = better)")
        ax.tick_params(axis="x", labelsize=6)
        fig.savefig(ev.IMG_DIR / f"ml_prematch_logloss_{name}.png", dpi=110, bbox_inches="tight")
    print(txt)
    return txt


def fresh():
    """The ONE pre-registered run on men's franchise leagues dated >= 2026-01-01 (docs/ML_PREDICTION.md). Refuses a second run."""
    flag = OUT_DIR / "prematch_fresh_done.flag"
    if flag.exists():
        raise SystemExit("the fresh run was already done; see prematch_report_fresh.md")
    P = _load_params()
    train = table(load_matches(True), P)  # built WITHOUT the locked matches
    full = table(load_matches(False), P)  # a live forecast knows earlier 2026 matches (prior-only, so no result leaks into its own row)
    test = full[ev.fresh_holdout_mask(full) & full.competition.isin(LEAGUES)]
    W, S = _eval(train[train.gender == "male"], test, ("level", "venue", "full"), "fresh")
    W.to_parquet(OUT_DIR / "prematch_fresh_W.parquet")
    S.to_parquet(OUT_DIR / "prematch_fresh_S.parquet")
    flag.write_text("done")
    txt = report(W, S, "fresh")
    d = boot(ll_each(W.y.to_numpy(), W.logit.to_numpy()) - ll_each(W.y.to_numpy(), W.base.to_numpy()))
    e = ev.ece(W.y, W.logit)
    ok1, ok2 = d[2] < 0, e < 0.08
    out = (f"\nPRE-REGISTERED RULE (primary model = logit, no toss): log loss minus coin flip {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] -> {'PASS' if ok1 else 'FAIL'}; "
           f"ECE {e:.3f} (limit 0.08) -> {'PASS' if ok2 else 'FAIL'}; OVERALL {'PASS' if ok1 and ok2 else 'FAIL'}; n={len(W)} matches")
    print(out)
    (OUT_DIR / "prematch_report_fresh.md").write_text(txt + out, encoding="utf-8")


# ---------- CLI ----------
def _prep(drop_locked=True):
    M = load_matches(drop_locked=drop_locked)
    return M, table(M, _load_params())


def backtest():
    M, T = _prep()
    Ws, Ss = [], []
    for n in folds():
        W, S = eval_fold(T, n)
        Ws.append(W)
        Ss.append(S)
    W, S = pd.concat(Ws), pd.concat(Ss)
    W.to_parquet(OUT_DIR / "prematch_dev_W.parquet")
    S.to_parquet(OUT_DIR / "prematch_dev_S.parquet")
    return W, S


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    if cmd == "tune":
        M = load_matches()
        best, e, s = tune(M)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        (MODEL_DIR / "params.json").write_text(json.dumps(best))
        print(e.to_string(), "\n", s.to_string(), "\n", best)
    elif cmd == "backtest":
        W, S = backtest()
        for n, w in W.groupby("fold"):
            wm, sm = metrics(w, S[S.fold == n])
            print(n, len(w), {k: round(v["logloss"], 4) for k, v in wm.items()}, {k: round(v["mae"], 1) for k, v in sm.items()})
    elif cmd == "fresh":
        fresh()
    elif cmd == "report":
        report()
    elif cmd == "fit":
        print(fit_final()["fitted_through"])
