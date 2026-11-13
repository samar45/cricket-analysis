"""Goal tests for test 3 (wicket overreaction) and test 4 (player information vs the market gap), pre-registered in docs/ML_PREDICTION.md section 9
(commit 29efa9c). Written and frozen BEFORE src/cricket_analytics/ml/market_t34.py exists. Do not edit to make code pass.

Names the code must provide (ml/market_t34.py):
  pair_rows()   DataFrame, one row per innings x consecutive snapshot pair (4->6, 6->10, 10->15 overs): match_id (str), season (BBL10..), date, innings (1|2),
                pair ("4-6" | "6-10" | "10-15"), b0, b1 (legal balls at the two snapshots: 24/36, 36/60, 60/90), batting_team, p_bat (de-vigged market p that the
                batting team wins, at the later snapshot), p_fld (the other team's p at that snapshot), W (wickets that fell with legal ball b0 < ... <= b1), y (batting team won)
  t4_rows()     DataFrame: the benchmark rows (market_rows.parquet) plus r, f_crease, f_notin, f_bowl
  player_features(rows, d, dates, d_strength=None)
                DataFrame (match_id, balls_bowled, f_crease, f_notin, f_bowl) for benchmark-style rows. d = deliveries (resources.load_deliveries),
                dates = Series match_id -> date. Strengths are built from d_strength (default d); the XI and who has batted come from d / states.
"""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import market as M
from cricket_analytics.ml import market_t34 as T

LOCK_DATE = pd.Timestamp("2026-10-15")
BENCH = M.ML_DIR / "market_rows.parquet"
pytestmark = pytest.mark.skipif(not BENCH.exists(), reason="benchmark rows not present")
NOT_DISMISSAL = ("retired hurt", "retired not out")


@pytest.fixture(scope="module")
def pairs():
    return T.pair_rows()


@pytest.fixture(scope="module")
def t4():
    return T.t4_rows()


def test_market_p_in_unit_interval_and_pair_sums_to_one(pairs):
    assert len(pairs) > 500
    assert ((pairs.p_bat > 0) & (pairs.p_bat < 1)).all()
    assert ((pairs.p_fld > 0) & (pairs.p_fld < 1)).all()
    assert np.allclose(pairs.p_bat + pairs.p_fld, 1.0, atol=1e-9)
    assert set(pairs.pair) == {"4-6", "6-10", "10-15"} and set(pairs.innings) == {1, 2}
    assert not pairs.duplicated(["match_id", "innings", "pair"]).any()


def test_W_equals_cricsheet_wickets_between_snapshots(pairs):
    from cricket_analytics.db import query

    assert pairs.W.between(0, 10).all()
    smp = pairs.sample(60, random_state=1)
    ids = ", ".join(f"'{m}'" for m in smp.match_id.unique())
    d = query(f"select match_id, innings, ball_seq, wides, noballs, wicket_type, player_out from deliveries where match_id in ({ids}) order by match_id, innings, ball_seq")
    d["legal"] = ((d.wides == 0) & (d.noballs == 0)).astype(int)
    d["before"] = d.groupby(["match_id", "innings"]).legal.cumsum() - d.legal  # legal balls bowled before this delivery
    d["wk"] = (d.player_out.notna() & ~d.wicket_type.isin(NOT_DISMISSAL)).astype(int)
    for r in smp.itertuples():
        x = d[(d.match_id == r.match_id) & (d.innings == r.innings)]
        want = int(x[(x.before >= r.b0) & (x.before < r.b1)].wk.sum())
        assert r.W == want, (r.match_id, r.innings, r.pair, r.W, want)


def test_player_features_use_only_prior_matches(t4):
    from cricket_analytics.ml import resources as R

    d, dates = R.load_deliveries()
    rows = t4[t4.balls_bowled == 60]
    for season in ("BBL12", "BBL15"):
        one = rows[rows.season == season].sort_values("date").iloc[[0]]
        day = pd.Timestamp(dates[str(one.match_id.iloc[0])])
        prior = d[d.match_id.map(dates).pipe(pd.to_datetime) < day]
        full = T.player_features(one, d, dates)
        cut = T.player_features(one, d, dates, d_strength=prior)
        cols = ["f_crease", "f_notin", "f_bowl"]
        assert full[cols].notna().all().all()
        assert np.allclose(full[cols].to_numpy(float), cut[cols].to_numpy(float)), (season, full[cols], cut[cols])


def test_test4_rows_equal_benchmark_rows(t4):
    bench = pd.read_parquet(BENCH)
    key = lambda x: set(zip(x.match_id.astype(str), x.balls_bowled.astype(int)))  # noqa: E731
    assert key(t4) == key(bench)
    assert len(t4) == len(bench)
    assert not t4.duplicated(["match_id", "balls_bowled"]).any()


def test_no_rows_on_or_after_lock_date(pairs, t4):
    assert pd.to_datetime(pairs.date).max() < LOCK_DATE
    assert pd.to_datetime(t4.date).max() < LOCK_DATE
