import pytest

from cricket_analytics.ml import dataset

try:
    S, INN = dataset.build(write=False)
except Exception as e:  # no DB on this machine
    pytest.skip(f"no database: {e}", allow_module_level=True)


def test_last_state_equals_final_total():
    last = S.sort_values("balls_bowled").groupby(["match_id", "innings"]).tail(1)
    assert (last.runs.to_numpy() == last.final_total.to_numpy()).all()


def test_balls_and_target_math():
    assert (S.balls_left == S.max_balls - S.balls_bowled).all()
    s2 = S[S.innings == 2]
    assert (s2.runs_needed == s2.target - s2.runs).all()
    assert S[S.innings == 1].target.isna().all()
    assert S.wickets.between(0, 10).all()


def test_monotone_and_start_rows():
    g = S.groupby(["match_id", "innings"])
    assert (g.runs.diff().dropna() >= 0).all() and (g.wickets.diff().dropna() >= 0).all()
    assert (S[S.balls_bowled == 0].runs == 0).all()
    assert g.balls_bowled.min().eq(0).all()


def test_target_is_first_total_plus_one():
    first = INN[INN.innings == 1].set_index("match_id").final_total
    i2 = INN[INN.innings == 2]
    assert (i2.target.to_numpy() == (i2.match_id.map(first) + 1).to_numpy()).all()


def test_no_super_overs_and_ipl_totals():
    assert S.innings.isin([1, 2]).all()
    ipl = INN[(INN.competition == "ipl") & (INN.innings == 1) & ~INN.reduced]
    assert 150 < ipl[ipl.season_year == 2015].final_total.mean() < 175
    assert INN[(INN.competition == "ipl") & INN.impact_era].season_year.min() == 2023
