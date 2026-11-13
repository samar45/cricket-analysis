"""Goal tests for the market-anchored model (test 1) and state-wise diagnosis (test 2), pre-registered in docs/ML_PREDICTION.md section 9.
Written and frozen BEFORE src/cricket_analytics/ml/market_anchor.py exists. Do not edit to make code pass.

Names the code must provide (ml/market_anchor.py):
  anchor_rows()      DataFrame, one row per benchmark row (match_id, balls_bowled), columns: match_id, balls_bowled, date, season (BBL10..BBL15), y,
                     p_ens-G1, p_market, p_A, p_B (NaN for BBL10), b_train_max_season (latest season used to fit the B row's model; NaN if no B),
                     wk_bin, rr_bin (test-2 cell labels, 3 x 3 per checkpoint)
  SEASON_ORDER       ["BBL10", ..., "BBL15"]
"""

import pandas as pd
import pytest

from cricket_analytics.ml import market as M
from cricket_analytics.ml import market_anchor as MA

LOCK_DATE = pd.Timestamp("2026-10-15")
BENCH = M.ML_DIR / "market_rows.parquet"
pytestmark = pytest.mark.skipif(not BENCH.exists(), reason="benchmark rows not present")


@pytest.fixture(scope="module")
def rows():
    return MA.anchor_rows()


def test_A_and_B_strictly_inside_unit_interval(rows):
    assert rows.p_A.notna().all()
    assert ((rows.p_A > 0) & (rows.p_A < 1)).all()
    b = rows.p_B.dropna()
    assert len(b) > 0
    assert ((b > 0) & (b < 1)).all()


def test_B_fit_only_on_earlier_seasons(rows):
    order = {s: i for i, s in enumerate(MA.SEASON_ORDER)}
    has = rows.p_B.notna()
    assert not has[rows.season == "BBL10"].any(), "BBL10 has no earlier season, so no B prediction"
    assert has[rows.season != "BBL10"].all()
    got = rows[has]
    assert (got.b_train_max_season.map(order) < got.season.map(order)).all()


def test_test2_cells_partition_rows(rows):
    assert rows.wk_bin.notna().all() and rows.rr_bin.notna().all()
    assert set(rows.wk_bin) == {"0-1", "2-3", "4+"} and set(rows.rr_bin) == {"<8", "8-10", ">10"}
    assert not rows.duplicated(["match_id", "balls_bowled", "wk_bin", "rr_bin"]).any()
    assert not rows.duplicated(["match_id", "balls_bowled"]).any(), "a row appears in two cells"
    for b, g in rows.groupby("balls_bowled"):
        cells = g.groupby(["wk_bin", "rr_bin"]).size()
        assert cells.sum() == len(g)
        assert len(cells) <= 9


def test_row_set_equals_benchmark_rows(rows):
    bench = pd.read_parquet(BENCH)
    key = lambda d: set(zip(d.match_id.astype(str), d.balls_bowled.astype(int)))  # noqa: E731
    assert key(rows) == key(bench)
    assert len(rows) == len(bench)


def test_no_rows_on_or_after_lock_date(rows):
    assert (pd.to_datetime(rows.date) < LOCK_DATE).all()
