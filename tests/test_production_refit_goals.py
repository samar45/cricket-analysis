"""Goal tests (frozen): production models refit on all data up to 2026-10-14, never on locked fresh set #3 (>= 2026-10-15)."""

import json

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import evaluate as ev
from cricket_analytics.ml import predict as P
from cricket_analytics.ml.dataset import OUT_DIR

CUTOFF, NEW_ENOUGH = pd.Timestamp("2026-10-14"), pd.Timestamp("2026-09-01")
META = P.MODEL_DIR / "production_meta.json"  # written by the refit: {"models": {name: {"max_train_date": "YYYY-MM-DD", "fresh3_rows": 0, ...}}}
BACKUP = P.MODEL_DIR / "backup_pre_refit_2026-11-13"
NAMES = {"G1_score", "G1_chase_w0", "G1_chase_w1m", "sim_B"}


def _meta():
    assert META.exists(), "refit must write production_meta.json next to the models"
    return json.loads(META.read_text())


def test_every_production_model_is_in_the_metadata():
    assert NAMES <= set(_meta()["models"])


@pytest.mark.parametrize("name", sorted(NAMES))
def test_training_end_date_is_recent_but_not_fresh3(name):
    d = pd.Timestamp(_meta()["models"][name]["max_train_date"])
    assert NEW_ENOUGH <= d <= CUTOFF


@pytest.mark.parametrize("name", sorted(NAMES))
def test_no_fresh3_rows_in_training(name):
    assert _meta()["models"][name]["fresh3_rows"] == 0


def test_source_tables_hold_no_fresh3_rows():
    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet")
    assert not ev.fresh3_mask(inn).any()
    assert inn.date.max() == CUTOFF  # the new data really is in the tables the refit reads
    with pytest.raises(ValueError):
        ev.assert_no_fresh3(pd.DataFrame({"gender": ["male"], "competition": ["ipl"], "date": ["2026-10-15"], "batting_team": ["India"], "bowling_team": ["Australia"]}), "x")


def test_old_artifacts_are_backed_up():
    for f in ("v2/final_score_q10.txt", "v2/final_score_q50.txt", "v2/final_score_q90.txt", "v2/final_win_w0.txt", "v2/final_win_w1m.txt",
              "v2/final_conformal_delta.json", "ball_B_men_fresh.pkl"):
        assert (BACKUP / f).stat().st_size > 0, f


def _venue_teams():
    v = P.venues("ipl")[0]
    t = P.teams("ipl")
    return v, t[0], t[1]


def _ordered(r):
    s = r["score"]
    return s["q10"] <= s["q50"] <= s["q90"]


def test_predict_state_innings1_after_5_overs():
    v, a, b = _venue_teams()
    r = P.predict_state("ipl", v, a, b, 1, 60, 2, 5.0, date="2026-10-15")
    assert _ordered(r) and r["score"]["q10"] >= 60
    assert 0 < r["win"]["bat"] < 1 and 0 < r["win"]["bowl"] < 1
    assert r["win"]["bat"] + r["win"]["bowl"] == pytest.approx(1.0)


def test_predict_state_chase_110_4_after_10_overs():
    v, a, b = _venue_teams()
    r = P.predict_state("ipl", v, a, b, 2, 110, 4, 10.0, target=209, date="2026-10-15")
    assert _ordered(r) and r["score"]["q10"] >= 110
    assert 0 < r["win"]["bat"] < 1 and 0 < r["win"]["bowl"] < 1
    assert np.isfinite(r["win"]["bat"])
