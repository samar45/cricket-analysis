"""Auction supply and demand (models/scarcity.py, the `scarcity` module). DB-free: uses the saved usage file and reference CSVs."""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics import api, registry
from cricket_analytics.models import scarcity as S
from cricket_analytics.viz import scarcity as vs


def test_bowl_style_from_reviewed_list_only():
    assert S.bowl_style("right-arm leg spin") == "wrist"
    assert S.bowl_style("left-arm wrist spin") == "wrist"
    assert S.bowl_style("left-arm orthodox") == "finger"
    assert S.bowl_style("right-arm off spin") == "finger"
    assert S.bowl_style("right-arm fast") == "pace"
    assert S.bowl_style(np.nan) is None


def test_features_use_only_earlier_years():
    u = S.usage()
    f26 = S.features(2026)
    pd.testing.assert_frame_equal(
        f26, S.features(2026, u[u.yr < 2026])
    )  # 2026 or later data cannot matter
    bat = f26[[f"w_{r}" for r in S.ROLES[1:5]]]
    assert (bat >= 0).all().all() and (bat.sum(1) <= 1 + 1e-9).all()


def test_roles_are_sensible_on_known_players():
    f = S.features(2026)
    assert f.loc["JJ Bumrah", "w_death_pace"] > 0.3
    assert f.loc["Rashid Khan", "w_spin_wrist"] > 0.5


def test_roll_forward_matches_real_2026_list_mostly():
    tot = S.squad_check().query("team == 'ALL'").iloc[0]
    assert tot.recall > 0.8 and tot.precision > 0.7


def test_team_needs_cap_and_purse():
    s = S.squads_before()
    for y in (2023, 2026):
        dem, summ = S.team_needs(s[y], S.features(y), y)
        assert (summ.need_scale <= 1).all() and (summ.purse_weight <= 3).all()
        assert (dem.demand >= 0).all() and (dem.need <= dem.need_raw + 1e-9).all()


def test_index_table_shape_and_relative_mean():
    i = S.index_table()
    assert set(i.year) == set(S.YEARS) and (i.groupby("year").size() == len(S.ROLES)).all()
    assert (i.supply_quality <= i.supply_all).all()
    assert (i.groupby("year").log_rel_index.mean().abs() < 1e-3).all()


def test_scarcity_for():
    keeper, pace = S.scarcity_for(["keeper"], 2026), S.scarcity_for(["pp_pace"], 2026)
    mix = S.scarcity_for({"keeper": 1.0, "pp_pace": 1.0}, 2026)
    assert min(keeper, pace) <= mix <= max(keeper, pace)
    assert np.isnan(S.scarcity_for({"keeper": 0.1}, 2026))
    assert S.scarcity_for(["spin"], 2027) > 0
    with pytest.raises(ValueError):
        S.scarcity_for(["googly"], 2026)
    with pytest.raises(ValueError):
        S.scarcity_for(["spin"], 2019)


def test_tests_file_has_all_tests_with_ordered_intervals():
    t = pd.read_csv(S.TESTS_CSV)
    assert {"A", "A2", "B", "C"} <= {x.split()[0] for x in t.test}
    assert (t.lo90 <= t.hi90).all()


def test_logit_and_ols_recover_truth():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(4000, 2))
    y = 1 + 2 * X[:, 0] - X[:, 1] + rng.normal(size=4000) * 0.1
    assert np.allclose(S._ols(X, y), [1, 2, -1], atol=0.02)
    yb = (rng.random(4000) < 1 / (1 + np.exp(-(0.5 + 1.5 * X[:, 0])))).astype(float)
    assert np.allclose(S._logit(X, yb)[:2], [0.5, 1.5], atol=0.25)


def test_module_views_and_figure():
    r = api.run("scarcity", year=2026)
    assert set(r.data.role) == set(S.ROLES) and r.data.scarcity_index.is_monotonic_decreasing
    assert vs.figure(r).data
    tn = api.run("scarcity", year=2026, view="team_needs")
    assert len(tn.data) == 10 and vs.figure(tn).data
    assert len(api.run("scarcity", view="2027").data) == len(S.ROLES)
    assert registry.get("scarcity")
    with pytest.raises(ValueError):
        api.run("scarcity", year=2019)
