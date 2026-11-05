"""Win probability model (models/win_prob.py) and the `wpa` module. The model tests need only the saved JSON; the
match-level ones need the real DB (skipped in CI)."""

import numpy as np
import pytest

from cricket_analytics import api
from cricket_analytics.models import win_prob as wp
from cricket_analytics.sql.filters import Filters
from cricket_analytics.analysis.wpa import ball_wpa
from cricket_analytics.viz import video, wpa as wviz
from tests.conftest import requires_real_db

real = requires_real_db


@pytest.mark.parametrize("group", wp.GROUPS)
def test_chase_wp_range_and_monotone(group):
    r = np.arange(1, 221)
    for b in (1, 3, 6, 12, 30, 60, 120):
        for w in (0, 3, 6, 9):
            p = wp.chase_wp(r, b, w, group, 2024)
            assert ((p >= 0) & (p <= 1)).all()
            hi = p[:-1] > 0.01  # tails near 0 may wiggle by 1e-5
            assert (np.diff(p)[hi] <= 1e-9).all(), (group, b, w)  # more runs needed -> never higher


def test_chase_wp_edges():
    assert wp.chase_wp(0, 30, 3)[0] == 1.0  # target reached
    assert wp.chase_wp(10, 0, 3)[0] == 0.0  # no balls left
    assert wp.chase_wp(10, 30, 10)[0] == 0.0  # all out
    assert (
        wp.chase_wp(100, 60, 6, "ipl", 2024)[0] < wp.chase_wp(100, 60, 2, "ipl", 2024)[0]
    )  # wickets lost matter


def test_first_wp_range_and_score_effect():
    s = np.arange(0, 260, 10)
    p = wp.first_wp(s, 30, 4, "ipl", 2022)
    assert ((p > 0) & (p < 1)).all() and (np.diff(p) >= 0).all()  # a bigger score never hurts


@real
def test_wp_invariants_one_ipl_season():
    d = ball_wpa(Filters(competition="ipl", season=2025))
    assert len(d) > 8000 and d.match_id.nunique() >= 60
    for c in ("wp_bf_before", "wp_bf_after"):
        assert d[c].between(0, 1).all()
    g = d.groupby("match_id")
    first = g.wp_bf_before.first()
    last = g.tail(1).set_index("match_id")
    assert np.allclose(last.wp_bf_after, last.bf_win)  # last ball = the result
    delta = (d.wp_bf_after - d.wp_bf_before).groupby(d.match_id).sum()
    assert np.allclose(delta, last.bf_win - first)  # WPA telescopes: result - starting WP
    # the curve is continuous across the innings break
    i1 = d[d.innings == 1].groupby("match_id").tail(1).set_index("match_id")
    i2 = d[d.innings == 2].groupby("match_id").head(1).set_index("match_id")
    assert np.allclose(i1.wp_bf_after, i2.wp_bf_before, atol=1e-6)
    # credit: batter + bowler sides each see at most the ball's whole swing, extras rules hold
    assert (d.bat_wpa[d.wides > 0][d.player_out.isna()] == 0).all()
    assert (d.bowl_wpa[((d.byes > 0) | (d.legbyes > 0)) & d.player_out.isna()] == 0).all()


@real
def test_wpa_module_and_curve():
    r = api.run("wpa", competition="ipl", season=2025, role="batting", top=10)
    assert len(r.data) == 10 and r.data.wpa_total.is_monotonic_decreasing
    assert {"batter", "wpa_total", "wpa_per_match", "best_match_id", "runs"} <= set(r.data.columns)
    b = api.run("wpa", competition="ipl", season=2025, role="bowling", top=5)
    assert {"bowler", "wickets", "economy"} <= set(b.data.columns)
    mid = int(r.data.best_match_id.iloc[0])
    m = api.run("wpa", view="match", match_id=mid, competition="ipl")
    assert len(m.data) > 200 and (m.data.swing_rank > 0).sum() == 5
    assert m.data.wp_bat_first.between(0, 1).all()
    assert wviz.figure(m).data and video.video_figure("wpa", m).data
    assert wviz.figure(r).data and video.video_figure("wpa", r, "1:1").data


@real
def test_famous_last_ball_final():
    # 2019 IPL final (MI beat CSK by 1 run): the biggest swing is the last ball, Thakur lbw to Malinga
    m = api.run("wpa", view="match", match_id=1181768, competition="ipl").data
    top = m[m.swing_rank == 1].iloc[0]
    assert top.over == 20 and top.ball == 6 and "Thakur" in top.event
    assert m.wp_bat_first.iloc[-1] == 1.0  # MI batted first and won
