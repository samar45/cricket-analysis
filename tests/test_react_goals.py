"""Goal tests for the "react harder" chase fix (B), pre-registered in docs/ML_PREDICTION.md section 9 (commit 9fe2ee1).
Written and frozen BEFORE src/cricket_analytics/ml/react.py exists. Do not edit to make code pass.

Names the code must provide (ml/react.py):
  dev_rows()                 DataFrame: the ens-G1 dev-fold chase rows at 6/10/15 overs (balls_bowled 36/60/90, innings 2, men's, IPL 2022-25 +
                             non-IPL 2024-25): match_id (str), innings, balls_bowled, chase_won, p_ens (ens-G1 probability), season_year,
                             competition, date, scope ('ipl' | 'non'), wickets, rrr, balls_left
  f1_rolling(rows, fit_fn=None)
                             Series (index = rows.index): the F1 probability. For each season_year S the layer is fit with
                             fit_fn(train) where train = rows[rows.season_year < S] only (default fit_fn = fit_f1); S with no earlier rows is not refit
                             (identity). fit_fn is called once per season S (so a spy can see every training set).
  candidates()               dev_rows() plus columns p_F1 and p_F2 (F2 = mean of G2 and the spline GAM = the cached b2 chase frame)
"""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import react as R

LOCK_DATE = pd.Timestamp("2026-10-15")
pytestmark = pytest.mark.skipif(not (R.OUT_DIR / "db_b2_W.parquet").exists(), reason="dev-fold caches not present")


@pytest.fixture(scope="module")
def rows():
    return R.dev_rows()


@pytest.fixture(scope="module")
def cand():
    return R.candidates()


def test_f1_season_S_fit_only_on_earlier_seasons(rows):
    seen = {}

    def spy(train):
        seen[len(seen)] = train.season_year.max()
        return R.fit_f1(train)

    p = R.f1_rolling(rows, fit_fn=spy)
    assert len(p) == len(rows)
    years = sorted(rows.season_year.unique())
    # every fit saw only seasons strictly before the season it is applied to
    calls = []

    def spy2(train):
        calls.append(train.season_year.max())
        return R.fit_f1(train)

    R.f1_rolling(rows, fit_fn=spy2)
    assert calls and all(c < years[-1] for c in calls)
    assert len(calls) <= len(years) - 1 + 1  # at most one fit per season
    assert max(calls) == years[-2] or max(calls) < years[-1]


def test_f1_ignores_outcomes_of_season_S_and_later(rows):
    """Behavioural leak test: scrambling chase_won in seasons >= S must not change F1 for seasons <= S."""
    base = R.f1_rolling(rows)
    for S in sorted(rows.season_year.unique())[1:]:
        alt = rows.copy()
        late = alt.season_year >= S
        alt.loc[late, "chase_won"] = 1.0 - alt.loc[late, "chase_won"]
        p2 = R.f1_rolling(alt)
        same = (rows.season_year <= S)
        assert np.allclose(base[same], p2[same]), S


def test_f1_f2_strictly_inside_unit_interval(cand):
    for c in ("p_F1", "p_F2"):
        assert cand[c].notna().all()
        assert (cand[c] > 0).all() and (cand[c] < 1).all()


def test_every_candidate_scored_on_the_same_rows_as_ens_g1(cand):
    from cricket_analytics.ml import fair_report as FR

    cm, _ = FR.cached()
    W = cm["ens-G1"][1]
    W = W[W.balls_bowled.isin((36, 60, 90)) & W.chase_won.notna() & W.scope.isin(["ipl", "non"])]
    want = set(zip(W.match_id.astype(str), W.innings.astype(int), W.balls_bowled.astype(int)))
    got = set(zip(cand.match_id.astype(str), cand.innings.astype(int), cand.balls_bowled.astype(int)))
    assert got == want and len(cand) == len(want)
    assert not cand.duplicated(["match_id", "innings", "balls_bowled"]).any()
    assert set(cand.balls_bowled) == {36, 60, 90} and set(cand.innings) == {2}
    assert cand[["p_ens", "p_F1", "p_F2", "chase_won"]].notna().all().all()


def test_no_rows_on_or_after_the_lock_date(cand):
    assert (pd.to_datetime(cand.date) < LOCK_DATE).all()
    assert cand.season_year.max() <= 2025
