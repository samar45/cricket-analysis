"""Match-conditions adjustment: leave-one-player-out on a tiny synthetic match (no DB)."""

import pandas as pd
import pytest

from cricket_analytics.models import match_adjust as M


def _rows():
    # one match, one phase: batters A (10 balls, +5), B (10 balls, -1), C (20 balls, +4); a bowler row must not leak into bat
    d = [("A", "bat", 10, 5.0), ("B", "bat", 10, -1.0), ("C", "bat", 20, 4.0), ("X", "bowl", 6, 3.0)]
    return pd.DataFrame(
        [dict(comp="t", sy=2020, season="2020", match_id="m1", phase="powerplay", team="T", player=p, role=r, balls=b, ra=v) for p, r, b, v in d]
    )


def test_leave_one_out():
    c = M.condition(_rows())
    assert c.iloc[0] == pytest.approx((-1 + 4) / 30)  # A: others = B + C
    assert c.iloc[1] == pytest.approx((5 + 4) / 30)
    assert c.iloc[2] == pytest.approx((5 - 1) / 20)
    assert c.iloc[3] == 0  # nobody else bowled: no condition


def test_w_zero_is_raw_and_adjusted_is_recentred():
    r = _rows()
    a0 = M.adjusted(r, 0)
    assert a0.ra_adj.sum() == pytest.approx(0)  # re-centred like WAR: bat and bowl each sum to 0 per league-season
    a1 = M.adjusted(r, 1)
    assert a1[a1.role == "bat"].ra_adj.sum() == pytest.approx(0)
    assert a1.ra_adj.iloc[0] - a1.ra_adj.iloc[1] != pytest.approx(a0.ra_adj.iloc[0] - a0.ra_adj.iloc[1])
