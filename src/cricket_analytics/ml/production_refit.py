"""Refit the production models (G1 score + chase, sim-B) on every match dated <= 2026-10-14. Fresh set #3 (>= 2026-10-15) never enters.

  python -m cricket_analytics.ml.production_refit

Same recipe as v2.final() and simfix.fit_fresh(), minus the old 2026-01-01 lock (fresh set #1 was already opened). Old artifacts are copied to
models/backup_pre_refit_2026-11-13/ first; the training cutoff is written to models/production_meta.json.
"""

import json
import shutil

import pandas as pd

from . import direct as D
from . import evaluate as ev
from . import features as F
from . import simfix as S
from . import v2
from .ball_model import MODEL_DIR, BallModel, load_balls
from .dataset import load
from .v2 import SCORE_COLS, WIN, WIN_PICK, mono_list, tuned_cfg
from .baselines import usable

BACKUP = MODEL_DIR / "backup_pre_refit_2026-11-13"
OLD = ["v2/final_score_q10.txt", "v2/final_score_q50.txt", "v2/final_score_q90.txt", "v2/final_win_w0.txt", "v2/final_win_w1m.txt",
       "v2/final_conformal_delta.json", "ball_B_men_fresh.pkl"]


def backup():
    for f in OLD:
        if (BACKUP / f).exists():
            continue  # never overwrite a backup
        (BACKUP / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MODEL_DIR / f, BACKUP / f)


_MI = None


def _matches(df):
    """One row per match of `df` with date, gender, competition and both teams (from the innings table)."""
    global _MI
    if _MI is None:
        _MI = load()[1].drop_duplicates("match_id")[["match_id", "date", "gender", "competition", "batting_team", "bowling_team"]]
    return df[["match_id"]].drop_duplicates().merge(_MI, on="match_id", how="left")


def _guard(df, what):
    ev.assert_no_fresh3(_matches(df), what)  # allow_fresh3 stays False
    return df


def _info(df, extra=None):
    m = _matches(df)
    return {"max_train_date": str(m.date.max().date()), "min_train_date": str(m.date.min().date()), "fresh3_rows": int(ev.fresh3_mask(m).sum()),
            "n_matches": len(m), **(extra or {})}


def fit_g1(log=print):
    states, inn = load()
    ids = set(inn.match_id[ev.fresh3_mask(inn)])
    states, inn = states[~states.match_id.isin(ids)], inn[~inn.match_id.isin(ids)]
    log(f"fresh3 matches dropped from the source tables: {len(ids)}")
    kv, kt, _ = F.tune_k(inn, 2022, k_venue_grid=(10, 30, 100, 300, 1000))
    log(f"tune_k: kv={kv} kt={kt} (predict.py uses 100, 10)")
    k, _ = F.tune_k_chase(inn, 2027)
    feat = F.add_v2(D.prep(F.build_features(states, inn, kv, kt)), inn, k)
    t, cut = tuned_cfg("ipl2026"), 2027
    val_sel = lambda f: (f.competition == "ipl") & (f.season_year == 2026)  # noqa: E731
    tr, w = D.pool_rows(feat, "global", cut)
    itr, iw = D.pool_rows(feat, "global", cut, last=cut - 1)
    val = feat[val_sel(feat) & (feat.balls_bowled % 2 == 0)]
    for df, nm in ((tr, "train"), (itr, "inner-train"), (val, "validation")):
        _guard(df, nm)
    cfg, cw = D.CONFIGS[t["score_cfg"]], D.CONFIGS[t["win_cfg"]]
    inner = D.fit_score(itr, iw, SCORE_COLS, cfg, val=val, scale="lvl_season")
    sm = D.fit_score(tr, w, SCORE_COLS, cfg, rounds={q: inner[q][1] for q in D.QS}, scale="lvl_season")
    v1 = usable(val)
    v1 = v1[v1.innings == 1]
    V = v1[D.META].assign(**D.predict_score(inner, v1, SCORE_COLS, scale="lvl_season"))
    dl = D.conformal_delta(V.final_total, V.q10, V.q90, D.over_bucket(V.balls_bowled))
    win = {}
    for v in ("w0", WIN_PICK):
        cols, mono = WIN[v]
        ex = {"monotone_constraints": mono_list(cols)} if mono else None
        wi, n = D.fit_win(itr, iw, cols, cw, val=val, extra=ex)
        win[v] = D.fit_win(tr, w, cols, cw, rounds=n, extra=ex)[0]
        log(f"  {v}: {n} trees")
    v2.save_models({"score": sm, "delta": dl, "win": win}, "final")
    return {"G1_score": _info(tr, {"rows": len(tr)}), "G1_chase_w0": _info(tr), "G1_chase_w1m": _info(tr)}


def fit_sim(log=print):
    raw = load_balls()
    ok = ~raw.reduced & raw.lvl_slow.notna()
    tr = _guard(raw[ok], "sim-B train")
    assert tr.match_date.max() < pd.Timestamp(ev.FRESH3_FROM)
    Y = 2027
    va = raw[(raw.season_year == Y - 1) & (raw.competition == "ipl") & ok]
    m = BallModel("B").fit(tr[tr.season_year < Y - 1], va)
    rounds = int(m.best_iter * 1.1) + 1
    m = BallModel("B").fit(tr[tr.season_year < Y], None, n_rounds=rounds)
    m.save("ball_B_men_fresh")
    log(f"sim-B: rounds {rounds}")
    return {"sim_B": _info(tr[tr.season_year < Y], {"rounds": rounds})}


if __name__ == "__main__":
    backup()
    models = {**fit_g1(), **fit_sim()}
    (MODEL_DIR / "production_meta.json").write_text(json.dumps({"cutoff": "2026-10-14", "locked_from": ev.FRESH3_FROM, "models": models}, indent=1))
    print(json.dumps(models, indent=1))
