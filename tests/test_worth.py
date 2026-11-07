"""player_worth: the estimators on synthetic data, the shipped selection, and one number checked by hand from SQL."""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics import api, registry
from cricket_analytics.db import query
from cricket_analytics.models import worth as W
from cricket_analytics.sql.filters import Filters
from tests.conftest import requires_real_db


def test_fit_k_recovers_a_known_constant_and_shrink_is_the_posterior_mean():
    # true rates ~ N(0.3, tau2); balls ~ Bernoulli(rate): k = p(1-p)/tau2 is about 0.21/0.0025 = 84
    rng = np.random.default_rng(0)
    n = rng.integers(60, 400, 4000)
    p = np.clip(rng.normal(0.3, 0.05, 4000), 0.01, 0.99)
    s1 = rng.binomial(n, p).astype(float)
    k, mu = W.fit_k(pd.DataFrame({"n": n, "s1": s1, "s2": s1}))  # x is 0/1, so x^2 = x
    assert 65 < k < 105 and mu == pytest.approx(0.3, abs=0.01)
    assert W.shrink(100, 40.0, 100.0, 0.2) == pytest.approx((40 + 20) / 200)  # halfway between 0.4 and 0.2


def test_pure_noise_has_no_skill_so_k_is_infinite():
    rng = np.random.default_rng(1)
    n = rng.integers(60, 400, 2000)
    s1 = rng.binomial(n, 0.3).astype(float)
    assert W.fit_k(pd.DataFrame({"n": n, "s1": s1, "s2": s1}))[0] > 1500


def test_selection_skips_a_clone_of_a_kept_metric():
    idx = pd.MultiIndex.from_product([list("abcdefghij" * 3), [1, 2, 3]]).unique()
    base = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    vals = {"a|all|abs": base, "b|all|abs": base * 2 + 1, "c|all|abs": pd.Series(np.random.default_rng(2).normal(size=len(idx)), index=idx)}
    t = pd.DataFrame(
        {"id": list(vals), "metric": list("abc"), "phase": "all", "variant": "abs", "n_ps": 500, "n_pairs": 500, "k": 50.0,
         "rel_pool": 0.5, "relevance_pool": 0.5, "score": [3, 2, 1.0]}
    )
    kept = W.select(t, vals).set_index("id").kept
    assert kept.to_dict() == {"a|all|abs": True, "b|all|abs": False, "c|all|abs": True}


def test_shipped_panel_is_small_and_registered():
    for role, lo in (("bat", 6), ("bowl", 3)):
        p = W.panel(role)
        assert lo <= len(p) <= 8 and (p.rel_pool >= W.MIN_REL).all() and np.isfinite(p.k).all()
    assert "player_worth" in registry.json_schema("player_worth")["title"]


@requires_real_db
def test_golden_kohli_dot_ball_share_matches_sql_by_hand():
    f = Filters(competition="ipl", season_from=2023)
    d = W.ball_frame(f)
    row = W.profile(d, "bat").query("player == 'V Kohli' and metric == 'dot ball %'").iloc[0]
    ids = d.match_id.unique().tolist()  # the matches the module used (trusted target, a result)
    q = query(
        "SELECT COUNT(*) FILTER (WHERE wides = 0) AS faced, COUNT(*) FILTER (WHERE wides = 0 AND runs_total = 0 AND noballs = 0) AS dots "
        f"FROM deliveries WHERE batter = 'V Kohli' AND innings <= 2 AND match_id IN ({','.join('?' * len(ids))})",
        ids,
    ).iloc[0]
    assert row.n == q.faced and row.raw == pytest.approx(q.dots / q.faced)
    assert 1500 < row.n < 2200 and 0.2 < row.raw < 0.33  # sanity: about four seasons of Kohli


@requires_real_db
def test_module_profile_leaderboard_and_highlights():
    prof = api.run("player_worth", player="JJ Bumrah", role="bowling").data
    assert prof.pctile.min() >= 90 and (prof.own_share.between(0, 1)).all()  # best-in-class by every kept measure
    lb = api.run("player_worth", role="batting", top=5).data
    assert len(lb) == 5 and lb.avg_pctile.is_monotonic_decreasing and (lb.balls >= 100).all()
    hl = api.run("player_worth", role="batting", mode="highlights", top=3).data
    assert hl.runs_vs_match.is_monotonic_decreasing and (hl.balls >= 12).all()
    from cricket_analytics.viz import player_worth as viz

    assert viz.figure(api.run("player_worth", player="V Kohli")) is not None
