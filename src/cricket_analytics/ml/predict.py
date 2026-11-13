"""Match predictor: inference on the trained models (production per the pre-registered rule of commit a2c05be, docs/ML_PREDICTION.md
section 9: first-innings score = G1 alone, chase win probability = v1 blend ens-G1; `model="v1"` gives the old all-blend path).

  predict_state(...)       one live state -> score range, win probabilities, per-model parts, simulated finals
  predict_match_curve(id)  a past match -> prediction after every over (for replay)
  competitions() / venues() / teams() / players() / matches()   lists for a UI

Models (read-only, data/external/ml/models/):
  G1   direct LightGBM, "final" files in v2/: refit on all data up to the cutoff in models/production_meta.json (v1 recipe: level-relative target,
       no season feature, conformal-widened q10/q90; chase classifier = the unconstrained w0 model). Score model is
       first-innings only; so the chase score range comes from the simulator alone.
  sim-B  ball-by-ball Monte Carlo (ball_B_men_fresh.pkl, men's pool). Players it does not know get the average batter / bowler.
Blend (ens-G1): score = mean of the two quantile sets, win = mean of the two probabilities.
Production (`PRODUCTION`): score range of a first innings = G1 only (the fair-baseline comparison showed the blend with sim-B adds nothing
measurable: dev MAE 19.41 vs 19.36, difference +0.05 [-0.07, +0.16]); win probability = the blend (sim-B missed the +0.005 log-loss rule by 0.00004).

All features are built "as of" `date` from earlier matches only (same code paths as training: features.innings_features,
ball_model.match_levels, the shrunk career strengths). Never writes a .duckdb. Men's competitions only, 20-over games.
Replays of matches on or before the training cutoff (production_meta.json) are in-sample (the models were trained on them).
"""

import json
from statistics import NormalDist
import math
import pickle
from functools import lru_cache

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import direct as D
from . import features as F
from .ball_model import BALLS_FILE, K_BAT_OUT, K_BAT_RUNS, K_BOWL_RUNS, K_BOWL_WK, MODEL_DIR, NOT_BOWLER_WK, match_levels
from .dataset import OUT_DIR
from .s4b import NO_SEASON
from .simulate import fill_missing_batter, simulate, start_states

V2_DIR = MODEL_DIR / "v2"
G1_PREFIX, SIM_MODEL = "final", "ball_B_men_fresh"
KV, KT = 100, 10  # shrinkage strengths (features.tune_k, the value every fold and the fresh run used)
MAX_BALLS = 120
LIVE = "__live__"
EXCLUDE = ("hundred",)  # 100-ball format: not modelled
QC = ["q10", "q50", "q90"]
PRODUCTION = {"score": "G1", "chase": "ens-G1"}  # outcome of the pre-registered rule (commit a2c05be, results in docs/ML_PREDICTION.md section 9)
MODELS = ("auto", "v1")  # "auto" = PRODUCTION; "v1" = the previous production (score and win both blended)
LEVEL_COLS = ["lvl_ew", "lvl_season", "venue_eff", "venue_n", "bat_team_eff", "bowl_team_eff"]


# ---------- parsing / lists ----------
def parse_overs(overs) -> int:
    """10.0 -> 60 balls, 10.3 -> 63 (the digit after the point is balls in the over, 0-5)."""
    o = round(float(overs), 1)
    full, part = int(o), int(round((o - int(o)) * 10))
    if not (0 <= part <= 5 and 0 <= full <= 20) or full * 6 + part > MAX_BALLS:
        raise ValueError(f"overs must look like 10.3 (0 to 20.0, balls 0-5 after the point), got {overs}")
    return full * 6 + part


@lru_cache(1)
def _inn() -> pd.DataFrame:
    return pd.read_parquet(OUT_DIR / "states_innings.parquet")


def competitions() -> list[str]:
    inn = _inn()
    return [c for c in F.COMPS if c not in EXCLUDE and ((inn.competition == c) & (inn.gender == "male")).any()]


def venues(competition: str, last_years: int = 4) -> list[str]:
    inn = _inn()
    x = inn[(inn.competition == competition) & (inn.gender == "male") & (inn.innings == 1)]
    x = x[x.date >= x.date.max() - pd.Timedelta(days=int(365 * last_years))]
    return x.venue.value_counts().index.tolist()


def teams(competition: str, last_years: int = 2) -> list[str]:
    inn = _inn()
    x = inn[(inn.competition == competition) & (inn.gender == "male") & (inn.innings == 1)]
    x = x[x.date >= x.date.max() - pd.Timedelta(days=int(365 * last_years))]
    return sorted(set(x.batting_team) | set(x.bowling_team))


def matches(competition: str, season_year: int | None = None) -> pd.DataFrame:
    """Past matches (newest first): match_id, date, season_year, label, venue, team1, team2, score1, score2, winner."""
    inn = _inn()
    a = inn[(inn.competition == competition) & (inn.gender == "male")]
    one = a[a.innings == 1][["match_id", "date", "season_year", "venue", "batting_team", "final_total", "final_wickets", "winner"]]
    one = one.rename(columns={"batting_team": "team1", "final_total": "score1", "final_wickets": "wk1"})
    two = a[a.innings == 2][["match_id", "batting_team", "final_total", "final_wickets"]].rename(columns={"batting_team": "team2", "final_total": "score2", "final_wickets": "wk2"})
    m = one.merge(two, on="match_id")
    if season_year is not None:
        m = m[m.season_year == season_year]
    m = m.sort_values(["date", "match_id"], ascending=False).reset_index(drop=True)
    m["label"] = m.date.dt.strftime("%Y-%m-%d") + "  " + m.team1 + " " + m.score1.astype(int).astype(str) + " v " + m.team2 + " " + m.score2.astype(int).astype(str)
    return m


@lru_cache(1)
def _players_table() -> pd.DataFrame:
    """(competition, team, role, player, balls, last_date) from the state table; roles: bat, bowl."""
    import pyarrow.parquet as pq

    t = pq.read_table(OUT_DIR / "states.parquet", columns=["competition", "gender", "date", "batting_team", "bowling_team", "striker", "non_striker", "bowler"])
    s = t.to_pandas(strings_to_categorical=True)
    s = s[s.gender == "male"]
    out = []
    for team_col, p_col, role in (("batting_team", "striker", "bat"), ("bowling_team", "bowler", "bowl")):
        g = s.groupby(["competition", team_col, p_col], observed=True).agg(balls=("date", "size"), last=("date", "max")).reset_index()
        g.columns = ["competition", "team", "player", "balls", "last"]
        out.append(g.assign(role=role))
    return pd.concat(out, ignore_index=True)


def players(competition: str, team: str, role: str = "bat", last_years: float = 1.5, top: int = 16) -> list[str]:
    """Players of `team` seen in this competition in the last `last_years` (most balls first)."""
    p = _players_table()
    p = p[(p.competition == competition) & (p.team == team) & (p.role == role)]
    p = p[p["last"] >= p["last"].max() - pd.Timedelta(days=int(365 * last_years))] if len(p) else p
    return p.sort_values("balls", ascending=False).player.astype(str).head(top).tolist()


# ---------- models (cached) ----------
@lru_cache(1)
def _g1():
    sc = {q: (lgb.Booster(model_file=str(V2_DIR / f"{G1_PREFIX}_score_q{int(q * 100)}.txt")), None) for q in D.QS}
    win = lgb.Booster(model_file=str(V2_DIR / f"{G1_PREFIX}_win_w0.txt"))
    delta = {int(k): v for k, v in json.loads((V2_DIR / f"{G1_PREFIX}_conformal_delta.json").read_text()).items()}
    return sc, win, delta


@lru_cache(1)
def _sim():
    return pickle.load(open(MODEL_DIR / f"{SIM_MODEL}.pkl", "rb"))


def warm() -> None:
    """Load every cached table / model once (a UI can call this behind its Run button)."""
    _g1(), _sim(), _career_g1(), _ball_tables(), _ifeat_all(), _levels_all()


# ---------- as-of-date tables ----------
@lru_cache(1)
def _career_g1() -> pd.DataFrame:
    """Runs / balls credited to each striker per match (features.player_priors definition), men only, with date."""
    import pyarrow.parquet as pq

    s = pq.read_table(OUT_DIR / "states.parquet", columns=["match_id", "innings", "runs", "striker", "gender"]).to_pandas()
    d = s.groupby(["match_id", "innings"], sort=False).runs.shift(-1) - s.runs
    ok = d.notna() & (s.striker.fillna("") != "") & (s.gender == "male")
    b = pd.DataFrame({"match_id": s.match_id[ok], "batter": s.striker[ok], "runs": d[ok], "balls": 1}).groupby(["match_id", "batter"], as_index=False).sum()
    return b.merge(_inn().drop_duplicates("match_id")[["match_id", "date"]], on="match_id")[["batter", "date", "runs", "balls"]]


def _g1_career(names, date) -> pd.DataFrame:
    c = _career_g1()
    c = c[(c.date < date) & c.batter.isin([n for n in names if n])]
    return c.groupby("batter")[["runs", "balls"]].sum()


@lru_cache(1)
def _ball_tables():
    """Per (player, date) batting and bowling sums from the ball table, as in ball_model.build_balls."""
    cols = ["batter", "bowler", "date", "wides", "noballs", "byes", "legbyes", "runs_batter", "runs_total", "wicket_type", "player_out", "wk_flag", "legal"]
    b = pd.read_parquet(BALLS_FILE, columns=cols)
    wk, faced = b.wk_flag == 1, b.wides == 0
    bat = pd.DataFrame({"batter": b.batter, "date": b.date, "f": faced.astype(int), "r": b.runs_batter.where(faced, 0),
                        "o": (wk & (b.player_out == b.batter)).astype(int)}).groupby(["batter", "date"], as_index=False).sum()
    bw = pd.DataFrame({"bowler": b.bowler, "date": b.date, "bl": b.legal.astype(int), "br": b.runs_total - b.byes - b.legbyes,
                       "bw": (wk & ~b.wicket_type.fillna("").isin(NOT_BOWLER_WK)).astype(int)}).groupby(["bowler", "date"], as_index=False).sum()
    return bat, bw


def _sim_strength(bat_name, bowl_name, date):
    """(bat_rpb, bat_out, bat_exp) and (bow_rpb, bow_wk) before `date`; None for a player with no earlier data / no name."""
    bat, bw = _ball_tables()
    bd, wd = bat[bat.date < date], bw[bw.date < date]
    gf, gr, go = bd.f.sum(), bd.r.sum(), bd.o.sum()
    g_rpb, g_out = (gr / gf if gf else 1.2), (go / gf if gf else 0.05)
    gl, gbr, gbw = wd.bl.sum(), wd.br.sum(), wd.bw.sum()
    g_brpb, g_bwk = (gbr / gl if gl else 1.2), (gbw / gl if gl else 0.04)
    out = [None, None]
    if bat_name:
        p = bd[bd.batter == bat_name][["f", "r", "o"]].sum()
        if p.f > 0:
            out[0] = ((p.r + K_BAT_RUNS * g_rpb) / (p.f + K_BAT_RUNS), (p.o + K_BAT_OUT * g_out) / (p.f + K_BAT_OUT), float(np.log1p(p.f)))
    if bowl_name:
        p = wd[wd.bowler == bowl_name][["bl", "br", "bw"]].sum()
        if p.bl > 0:
            out[1] = ((p.br + K_BOWL_RUNS * g_brpb) / (p.bl + K_BOWL_RUNS), (p.bw + K_BOWL_WK * g_bwk) / (p.bl + K_BOWL_WK))
    return out


@lru_cache(1)
def _ifeat_all() -> pd.DataFrame:
    inn = _inn()
    return F.innings_features(inn[inn.gender == "male"], KV, KT).set_index(["match_id", "innings"])


@lru_cache(8)
def _asof(comp, date_str):
    """Level / venue / team effects of a competition as of `date` (features.innings_features on the history plus one placeholder
    row per venue and per team; placeholders are 'reduced' so they never update anything, and each reads only earlier dates)."""
    inn, d = _inn(), pd.Timestamp(date_str)
    m = inn[(inn.gender == "male")]
    c = m[m.competition == comp]
    prev = c[c.date < d]
    if prev.empty:
        raise ValueError(f"no earlier matches of {comp} before {date_str}")
    last = prev.sort_values("date").iloc[-1]
    sy = int(last.season_year) if (d - last.date).days < 150 else d.year  # still the same season, or a new one
    tms, vns = sorted(set(c.batting_team) | set(c.bowling_team)), sorted(set(c.venue))
    base = {"gender": "male", "competition": comp, "season_year": sy, "date": d, "reduced": True, "final_total": 150.0, "legal_balls": 120, "innings": 1}
    ph = [{**base, "match_id": f"{LIVE}t{i}", "venue": vns[0], "batting_team": t, "bowling_team": t} for i, t in enumerate(tms)]
    ph += [{**base, "match_id": f"{LIVE}v{i}", "venue": v, "batting_team": tms[0], "bowling_team": tms[0]} for i, v in enumerate(vns)]
    f = F.innings_features(pd.concat([m, pd.DataFrame(ph)], ignore_index=True), KV, KT)
    f = f.set_index("match_id").loc[[p["match_id"] for p in ph]]
    team = {t: (f.bat_team_eff.iloc[i], f.bowl_team_eff.iloc[i]) for i, t in enumerate(tms)}
    ven = {v: (f.venue_eff.iloc[len(tms) + i], f.venue_n.iloc[len(tms) + i]) for i, v in enumerate(vns)}
    return {"lvl_ew": f.lvl_ew.iloc[0], "lvl_season": f.lvl_season.iloc[0]}, ven, team, sy


@lru_cache(1)
def _levels_all() -> pd.DataFrame:
    """Per first innings (men's, not reduced): ball-model levels and the venue residual (rpo minus competition level)."""
    inn = _inn()
    f = inn[(inn.innings == 1) & ~inn.reduced & (inn.gender == "male")][["match_id", "competition", "venue", "date", "final_total", "legal_balls"]]
    f = f.merge(match_levels(inn), on="match_id")
    f["v"] = f.final_total / f.legal_balls * 6
    f["res"] = f.v - f.lvl_slow
    return f.sort_values(["date", "match_id"]).reset_index(drop=True)


def _ball_levels(comp, venue, d):
    """ball_model.match_levels for a match that has not happened: lvl_slow / lvl_fast (exp-weighted, earlier matches of the
    competition) and the shrunk venue effect. Same code path (ew_level, K_VENUE) as training."""
    from .ball_model import HL_FAST, HL_SLOW, K_VENUE, ew_level

    f = _levels_all()
    c = f[f.competition == comp]
    ph = pd.DataFrame({"date": [d], "match_id": [LIVE], "v": [7.5]})
    x = pd.concat([c[["date", "match_id", "v"]], ph]).sort_values(["date", "match_id"]).reset_index(drop=True)
    pos = int(np.flatnonzero(x.match_id.to_numpy() == LIVE)[0])
    r = f[(f.venue == venue) & (f.date < d)].res.dropna()
    return {"lvl_slow": float(ew_level(x, HL_SLOW)[pos]), "lvl_fast": float(ew_level(x, HL_FAST)[pos]), "venue_eff": float(r.sum() / (len(r) + K_VENUE))}


def _live_levels(comp, venue, team1, team2, date_str):
    """(G1 level table indexed by innings 1/2, simulator levels dict, season_year) for a match not yet played (team1 bats first)."""
    lv, ven, team, sy = _asof(comp, date_str)
    v = ven.get(venue, (0.0, 0))
    z = (0.0, 0.0)
    rows = {i: {**lv, "venue_eff": v[0], "venue_n": v[1], "bat_team_eff": team.get(b, z)[0], "bowl_team_eff": team.get(o, z)[1]}
            for i, (b, o) in ((1, (team1, team2)), (2, (team2, team1)))}
    return pd.DataFrame(rows).T[LEVEL_COLS], _ball_levels(comp, venue, pd.Timestamp(date_str)), sy


# ---------- model inputs ----------
def _g1_frame(r: pd.DataFrame, date, comp, sy) -> pd.DataFrame:
    """r: runs, wickets, balls_bowled, innings, target, max_balls, striker, non_striker, striker_faced, ns_faced, runs_l30,
    wk_l30 and the LEVEL_COLS. Adds the derived columns exactly as features.build_features does (NO_SEASON columns)."""
    r = r.reset_index(drop=True).copy()
    left = r.max_balls - r.balls_bowled
    r["balls_left"] = left
    r["crr"] = np.where(r.balls_bowled > 0, r.runs / r.balls_bowled.clip(lower=1) * 6, r.lvl_ew / 20)
    r["runs_needed"] = r.target - r.runs
    r["rrr"] = np.where((r.innings == 2) & (left > 0), (r.runs_needed / left.clip(lower=1) * 6).clip(0, 36), np.nan)
    r["rr_diff"] = r.crr - r.rrr
    r["comp_code"] = F.COMPS.index(comp)
    r["impact_era"] = int(comp == "ipl" and sy >= 2023)
    car = _g1_career(set(r.striker.dropna()) | set(r.non_striker.dropna()), date)
    for side, col in (("striker", "striker"), ("ns", "non_striker")):
        R, B = r[col].map(car.runs).fillna(0), r[col].map(car.balls).fillna(0)
        r[f"{side}_rpb"] = (R + F.K_PLAYER * r.lvl_ew / 120.0) / (B + F.K_PLAYER)
        r[f"{side}_balls_prior"] = B
    return r


def _g1_predict(fr: pd.DataFrame) -> pd.DataFrame:
    """Conformal-widened first-innings quantiles (q10/q50/q90) and the chase classifier probability p, one row per input row."""
    sc, win, delta = _g1()
    s = D.predict_score(sc, fr, NO_SEASON, scale="lvl_season")
    lo, hi = D.conformal_apply(s.q10, s.q50, s.q90, D.over_bucket(fr.balls_bowled), delta)
    s = s.assign(q10=np.asarray(lo), q90=np.asarray(hi))
    s["p"] = win.predict(fr[NO_SEASON].astype(float).assign(comp_code=fr.comp_code))
    return s


def _sim_rows(r: pd.DataFrame, bl: pd.DataFrame, comp: str) -> pd.DataFrame:
    """Start states for the simulator. r: innings, runs, wickets, balls_bowled, target, max_balls, striker_faced, ns_faced and
    bat (rpb, out, exp) / nbat / bowl tuples (or None = the model's average batter for the wickets down / average bowler for the over);
    bl: one row per r row with lvl_slow, lvl_fast, venue_eff."""
    m = _sim()
    gb, go = np.asarray(m.gen_bat, float), np.asarray(m.gen_bowl, float)
    rows = []
    for x, lv in zip(r.itertuples(index=False), bl.itertuples(index=False)):
        gbat = gb[min(int(x.wickets), 10)]
        s, n = (x.bat or tuple(gbat)), (x.nbat or tuple(gbat))
        bw = x.bowl or tuple(go[min(int(x.balls_bowled) // 6, 19)])
        rows.append({"runs": x.runs, "wickets": x.wickets, "balls_bowled": x.balls_bowled, "innings": x.innings, "target": x.target,
                     "max_balls": x.max_balls, "lvl_slow": lv.lvl_slow, "lvl_fast": lv.lvl_fast, "comp": F.COMPS.index(comp), "venue_eff": lv.venue_eff,
                     "s_rpb": s[0], "s_out": s[1], "s_exp": s[2], "s_faced": x.striker_faced,
                     "n_rpb": n[0], "n_out": n[1], "n_exp": n[2], "n_faced": x.ns_faced, "bow_rpb": bw[0], "bow_wk": bw[1]})
    return pd.DataFrame(rows)


def _q(a):
    return {k: float(v) for k, v in zip(QC, np.quantile(a, [0.1, 0.5, 0.9]))}


_Z90 = NormalDist().inv_cdf(0.9)


def p_over(q10, q50, q90, line) -> float:
    """P(final total > line): two-piece normal through the 10/50/90% quantiles (median q50; separate spread below and above it)."""
    z = _Z90
    sd = (q50 - q10) / z if line < q50 else (q90 - q50) / z
    return 0.5 * math.erfc((line - q50) / (sd * math.sqrt(2)))


def sim_lines(sims) -> dict:
    """The simulator's own 10/50/90% (for the histogram lines)."""
    return _q(sims)


def sim_share_over(sims, line) -> float:
    return float(np.mean(np.asarray(sims) > line))


def _chase_grid(fin, lv, ball_lv, date, comp, sy, n=100, seed=1):
    """P(the side batting first wins) given simulated first-innings totals `fin`: the chasing team's win probability from ball 0
    (average players) at a grid of targets, per model, interpolated at every simulated total + 1."""
    tg = np.unique(np.linspace(fin.min(), fin.max(), 8).round()) + 1
    base = pd.DataFrame({"innings": 2, "runs": 0, "wickets": 0, "balls_bowled": 0, "target": tg, "max_balls": MAX_BALLS, "striker": None,
                         "non_striker": None, "striker_faced": 0, "ns_faced": 0, "runs_l30": 0, "wk_l30": 0})
    for c in LEVEL_COLS:
        base[c] = lv.loc[2, c]
    pg = _g1_predict(_g1_frame(base, date, comp, sy)).p.to_numpy()
    sr = base.assign(bat=None, nbat=None, bowl=None)
    ps = simulate(_sim(), _sim_rows(sr, pd.DataFrame([ball_lv] * len(sr)), comp), n=n, seed=seed)["win"]
    cut = lambda p: 1 - float(np.interp(fin + 1, tg, p).mean())  # noqa: E731
    return cut(pg), cut(ps)


# ---------- public: one live state ----------
def _blend_score(model: str) -> bool:
    """True when the first-innings score range is the G1 / sim-B blend (the v1 path, or if PRODUCTION says so)."""
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}, got {model!r}")
    return model == "v1" or PRODUCTION["score"] == "ens-G1"


def predict_state(competition, venue, batting_team, bowling_team, innings, runs, wickets, overs, target=None,
                  striker=None, non_striker=None, bowler=None, date=None, n_sims=1000, seed=0,
                  striker_faced=None, non_striker_faced=None, runs_last30=None, wickets_last30=None, model="auto") -> dict:
    """Predict from a live state. `overs` like 10.3 (10 overs 3 balls). Innings 2 needs `target` (first-innings total + 1).
    Optional: striker / non_striker / bowler names (average players if omitted or unknown), date (default today; features use only
    earlier matches), balls faced so far by the two batters, runs / wickets in the last 30 balls (default: scaled from the totals).

    model: "auto" (production: innings-1 score = G1 only, win = blend) or "v1" (score and win both the G1 / sim-B blend).

    Returns dict: score {q10,q50,q90} (innings 1: G1, or the G1 / sim-B blend with model="v1"; innings 2: sim-B only, a chase stops at the target),
    win {bat, bowl} (blend), g1 {q10,q50,q90 (innings 1), win_bat}, sim {q10,q50,q90,mean,win_bat, wickets_mean}, sims (final totals),
    plus balls, balls_left, target, players_known, date, season_year, level (lvl_season)."""
    comp = competition
    blend_score = _blend_score(model)
    if comp not in competitions():
        raise ValueError(f"unknown competition {comp!r}")
    if innings not in (1, 2):
        raise ValueError("innings must be 1 or 2")
    if not (0 <= wickets <= 10 and runs >= 0):
        raise ValueError("wickets 0-10 and runs >= 0")
    if innings == 2 and (target is None or target < 1):
        raise ValueError("a chase needs a target (first-innings total + 1)")
    if batting_team == bowling_team:
        raise ValueError("pick two different teams")
    balls = parse_overs(overs)
    d = pd.Timestamp(date) if date is not None else pd.Timestamp.today().normalize()
    t1, t2 = (batting_team, bowling_team) if innings == 1 else (bowling_team, batting_team)
    lv, ball_lv, sy = _live_levels(comp, venue, t1, t2, str(d.date()))
    tgt = float(target) if innings == 2 else np.nan
    sf = striker_faced if striker_faced is not None else min(0.3 * balls, 30.0)
    nf = non_striker_faced if non_striker_faced is not None else min(0.3 * balls, 30.0)
    l30 = min(1.0, 30 / balls) if balls else 0.0
    r30 = runs_last30 if runs_last30 is not None else runs * l30
    w30 = wickets_last30 if wickets_last30 is not None else wickets * l30
    out = {"competition": comp, "venue": venue, "batting_team": batting_team, "bowling_team": bowling_team, "innings": innings,
           "runs": runs, "wickets": wickets, "balls": balls, "balls_left": MAX_BALLS - balls, "target": None if innings == 1 else int(target),
           "date": str(d.date()), "season_year": sy, "level": float(lv.loc[innings, "lvl_season"]), "model": model}
    bs, bw = _sim_strength(striker, bowler, d)
    ns, _ = _sim_strength(non_striker, None, d)
    out["players_known"] = {"striker": bs is not None, "non_striker": ns is not None, "bowler": bw is not None}
    # finished states need no model
    if balls >= MAX_BALLS or wickets >= 10 or (innings == 2 and runs >= target):
        won = float(runs >= target) if innings == 2 else None
        if innings == 2 and not won:
            won = 0.5 if runs == target - 1 else 0.0
        fin = np.full(1, float(runs))
        out.update(score={k: float(runs) for k in QC}, g1={}, sim={}, sims=fin, finished=True,
                   win=None if innings == 1 else {"bat": won, "bowl": 1 - won})
        return out
    row = pd.DataFrame([{"innings": innings, "runs": runs, "wickets": wickets, "balls_bowled": balls, "target": tgt, "max_balls": MAX_BALLS,
                         "striker": striker, "non_striker": non_striker, "striker_faced": sf, "ns_faced": nf, "runs_l30": r30, "wk_l30": w30,
                         **{c: lv.loc[innings, c] for c in LEVEL_COLS}}])
    g = _g1_predict(_g1_frame(row, d, comp, sy)).iloc[0]
    sr = row.assign(bat=[bs], nbat=[ns], bowl=[bw], striker_faced=sf, ns_faced=nf)
    res = simulate(_sim(), _sim_rows(sr, pd.DataFrame([ball_lv]), comp), n=n_sims, seed=seed)
    fin = res["final"][0].astype(float)
    sim = {**_q(fin), "mean": float(fin.mean()), "wickets_mean": float(res["wickets"][0].mean())}
    out.update(sims=fin, finished=False)
    if innings == 1:
        gq = np.sort([g.q10, g.q50, g.q90])
        sq = np.array([sim[k] for k in QC])
        out["score"] = dict(zip(QC, (gq + sq) / 2 if blend_score else gq))
        out["g1"] = dict(zip(QC, map(float, gq)))
        pg, ps = _chase_grid(fin, lv, ball_lv, d, comp, sy)
        out["g1"]["win_bat"], sim["win_bat"] = pg, ps
        out["win"] = {"bat": (pg + ps) / 2, "bowl": 1 - (pg + ps) / 2}
    else:
        out["score"] = {k: sim[k] for k in QC}
        out["g1"] = {"win_bat": float(g.p)}
        sim["win_bat"] = float(res["win"][0])
        pb = (float(g.p) + sim["win_bat"]) / 2
        out["win"] = {"bat": pb, "bowl": 1 - pb}
    out["sim"] = sim
    return out


def is_in_sample(date, comp) -> bool:
    """True if the models were trained on a match of this date. Cutoff = production_meta.json; old rule if the file is missing."""
    try:
        return bool(pd.Timestamp(date) <= pd.Timestamp(json.loads((MODEL_DIR / "production_meta.json").read_text())["cutoff"]))
    except (OSError, KeyError, ValueError):
        return bool(pd.Timestamp(date) < pd.Timestamp("2026-01-01") or comp == "ipl")


# ---------- public: replay a past match ----------
def predict_match_curve(match_id, n_sims=200, seed=0, model="auto") -> tuple[pd.DataFrame, dict]:
    """Prediction at the start of every over of a past match, from the real state (real players and score).
    Returns (curve, meta). curve rows: innings, over, balls, runs, wickets, and
      innings 1: g1_q10/q50/q90, sim_q10/q50/q90, ens_q10/q50/q90 (projected total: the production score model, G1 alone; the G1 / sim-B blend with model="v1");
      innings 2: win_g1, win_sim, win_ens = P(chasing team wins), sim_q10/q50/q90 (projected score; a chase stops at the target).
    meta: teams, scores, winner, target, venue, date, competition, reduced, in_sample (the models saw this match in training)."""
    blend_score = _blend_score(model)
    mid = str(match_id)
    inn = _inn()
    mi = inn[inn.match_id == mid]
    if mi.empty:
        raise ValueError(f"unknown match {match_id}")
    comp, d = mi.competition.iloc[0], mi.date.iloc[0]
    if mi.gender.iloc[0] != "male" or comp in EXCLUDE:
        raise ValueError("only men's 20-over matches are modelled")
    st = pd.read_parquet(OUT_DIR / "states.parquet", filters=[("match_id", "==", mid)])
    bl = pd.read_parquet(BALLS_FILE, filters=[("match_id", "==", mid)])
    lv = _ifeat_all().loc[mid]
    sy = int(mi.season_year.iloc[0])
    first, second = mi[mi.innings == 1].iloc[0], mi[mi.innings == 2].iloc[0]
    meta = {"match_id": mid, "competition": comp, "date": str(d.date()), "venue": first.venue, "team1": first.batting_team, "team2": second.batting_team,
            "score1": int(first.final_total), "wk1": int(first.final_wickets), "score2": int(second.final_total), "wk2": int(second.final_wickets),
            "target": None if pd.isna(second.target) else int(second.target), "winner": first.winner, "result": first.result,
            "reduced": bool(first.reduced), "in_sample": is_in_sample(d, comp)}
    frames = []
    for i in (1, 2):
        s = st[(st.innings == i) & (st.balls_bowled % 6 == 0) & (st.balls_bowled < st.max_balls)].copy()
        s = s[(s.wickets < 10) & ~((i == 2) & (s.runs >= s.target))]  # live states only
        full = st[st.innings == i].sort_values("balls_bowled")
        full["runs_l30"] = full.runs - full.runs.shift(30).fillna(0)
        full["wk_l30"] = full.wickets - full.wickets.shift(30).fillna(0)
        sf, nf = F._faced(full.reset_index(drop=True))
        full["striker_faced"], full["ns_faced"] = sf, nf
        s = s.merge(full[["balls_bowled", "runs_l30", "wk_l30", "striker_faced", "ns_faced"]], on="balls_bowled")
        for c in LEVEL_COLS:
            s[c] = lv.loc[i, c]
        frames.append(s)
    s = pd.concat(frames, ignore_index=True)
    if s.empty:
        raise ValueError("no live states in this match")
    g = _g1_predict(_g1_frame(s, d, comp, sy))
    # simulator: the ball table's own strengths of the real players at each state
    sims = []
    for i in (1, 2):
        for k in s[s.innings == i].balls_bowled:
            sims.append((mid, i, int(k)))
    stt = pd.concat([start_states(bl, [(mid, i)], int(k)) for _, i, k in sims], ignore_index=True)
    stt["n_faced"] = stt.n_faced.astype(float)
    stt = fill_missing_batter(stt, _sim())
    res = simulate(_sim(), stt, n=n_sims, seed=seed)
    sq = pd.DataFrame(np.quantile(res["final"], [0.1, 0.5, 0.9], axis=1).T, columns=["sim_q10", "sim_q50", "sim_q90"])
    sq["innings"], sq["balls"], sq["win_sim"] = stt.innings.to_numpy(), stt.balls_bowled.to_numpy(), res["win"]
    c = pd.DataFrame({"innings": s.innings, "over": s.balls_bowled // 6, "balls": s.balls_bowled, "runs": s.runs, "wickets": s.wickets,
                      "g1_q10": g.q10, "g1_q50": g.q50, "g1_q90": g.q90, "win_g1": g.p})
    c = c.merge(sq, on=["innings", "balls"], how="left")
    e = np.sort(np.stack([(c[f"g1_{k}"] + c[f"sim_{k}"]) / 2 if blend_score else c[f"g1_{k}"] for k in QC], 1), axis=1)
    for j, k in enumerate(QC):
        c[f"ens_{k}"] = e[:, j]
    c["win_ens"] = (c.win_g1 + c.win_sim) / 2
    inn1 = c.innings == 1
    c.loc[inn1, ["win_g1", "win_sim", "win_ens"]] = np.nan  # no first-innings win model
    c.loc[~inn1, [f"g1_{k}" for k in QC] + [f"ens_{k}" for k in QC]] = np.nan  # G1 score model is first-innings only
    return c.sort_values(["innings", "balls"]).reset_index(drop=True), meta
