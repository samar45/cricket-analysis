"""Goal tests (frozen): over/under calculator and chart lines on the Match predictor page."""

from statistics import NormalDist

import numpy as np
import pytest

from cricket_analytics.ml import predict as P

Z = 1.2816
Q = (174.0, 197.0, 223.0)


def test_p_over_at_median_is_half():
    assert P.p_over(*Q, 197.0) == pytest.approx(0.5, abs=1e-6)


def test_p_over_at_q10_and_q90():
    assert P.p_over(*Q, Q[0]) == pytest.approx(0.9, abs=1e-6)
    assert P.p_over(*Q, Q[2]) == pytest.approx(0.1, abs=1e-6)


def test_p_over_decreases_and_stays_in_unit_interval():
    ps = [P.p_over(*Q, x) for x in np.arange(100, 320, 0.5)]
    assert all(0.0 <= p <= 1.0 for p in ps)
    assert all(a >= b for a, b in zip(ps, ps[1:]))
    assert ps[0] > 0.99 and ps[-1] < 0.01


def test_over_plus_under_is_one():
    for x in (150.5, 190.5, 230.5):
        over = P.p_over(*Q, x)
        assert over + (1 - over) == pytest.approx(1.0)


def test_symmetric_quantiles_equal_plain_normal():
    sd = 20 / Z
    nd = NormalDist(180, sd)
    for x in (140.5, 170.5, 180.5, 200.5, 225.5):
        assert P.p_over(160, 180, 200, x) == pytest.approx(1 - nd.cdf(x), abs=1e-6)


def test_chart_lines_use_simulator_quantiles():
    sims = np.arange(1, 1001)
    lines = P.sim_lines(sims)
    assert lines["q10"] == pytest.approx(np.percentile(sims, 10))
    assert lines["q50"] == pytest.approx(np.percentile(sims, 50))
    assert lines["q90"] == pytest.approx(np.percentile(sims, 90))


def test_sim_share_over():
    sims = np.array([100, 150, 200, 250])
    assert P.sim_share_over(sims, 175.5) == 0.5
