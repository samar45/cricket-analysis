"""Goal tests for the SMAT 2025-26 scouting tables (built from local Cricbuzz scorecards, gitignored). Frozen."""
import pandas as pd
import pytest

from cricket_analytics.scouting import smat2025 as s

D = s.ROOT
pytestmark = pytest.mark.skipif(not (D / "batting.parquet").exists(), reason="SMAT scorecards not saved locally")


def test_batter_runs_plus_extras_is_total_of_all_innings():
    t = s.batter_table(min_balls=0)
    inn = pd.read_parquet(D / "innings.parquet")
    assert t.runs.sum() + inn.extras.sum() == inn.runs.sum()


def test_no_player_in_two_rows():
    assert s.batter_table(min_balls=0).cricbuzz_id.is_unique
    assert s.bowler_table(min_overs=0).cricbuzz_id.is_unique


def test_min_filters_hold():
    assert (s.batter_table().balls >= 100).all()
    assert (s.bowler_table().balls >= 72).all()  # 12 overs


def test_ishan_kishan_517_runs_10_innings():
    t = s.batter_table(min_balls=0)
    r = t[t.name.str.contains("Ishan Kishan")]
    assert len(r) == 1 and r.runs.iloc[0] == 517 and r.inns.iloc[0] == 10
