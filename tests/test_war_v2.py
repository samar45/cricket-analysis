"""WAR v2 (fielding credit, lower replacement level; docs/VALUE_war_fix.md). Default WAR (v1) must not change."""

import warnings

import pandas as pd
import pytest

from cricket_analytics import api
from cricket_analytics.models import war as W
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")


def test_v2_params_only_change_replacement_and_fielding():
    a, b = W.load_params("v1"), W.load_params("v2")
    for k in ("2023", "pre"):
        assert a["era"][k]["rpw"] == b["era"][k]["rpw"]
        assert b["era"][k]["repl"]["bat"] == b["era"][k]["repl"]["bowl"] == -6.0
    assert b["fielding"] == W.FIELD_SHARES and a["era"]["2023"]["repl"]["bowl"] == pytest.approx(-3.3248, abs=1e-3)


def test_centre_with_fielding_credit_keeps_bowling_side_zero_sum():
    rows = pd.DataFrame(
        dict(comp="ipl", sy=2024, role=["bat", "bowl", "bowl", "field"], balls=[100, 50, 50, 0], sc=[3.0, 1.0, 2.0, 0.0], wk=[-1.0, 0.0, 0.0, 4.0])
    )
    c = W.centre(rows)
    assert (c.sc + c.wk)[c.role == "bat"].sum() == pytest.approx(0)
    assert (c.sc + c.wk)[c.role.isin(["bowl", "field"])].sum() == pytest.approx(0)


@requires_real_db
def test_v2_fielding_moves_credit_and_default_is_v2():
    r1, _ = W.season_table("ipl")
    r2, _ = W.season_table("ipl", fielding=W.FIELD_SHARES)
    assert "field" not in set(r1.role) and "field" in set(r2.role)
    # bat rows identical; the bowlers' wicket credit only shrinks (catches / stumpings moved to fielders)
    k = ["sy", "team", "player"]
    b1, b2 = (x[x.role == "bat"].groupby(k)[["sc", "wk"]].sum() for x in (r1, r2))
    assert (b1 - b2).abs().max().max() < 1e-9
    v1 = api.run("war", competition="ipl", season=2024, player="JJ Bumrah", version="v1")
    v2 = api.run("war", competition="ipl", season=2024, player="JJ Bumrah", version="v2")
    assert "field_war" not in v1.data.columns and "field_war" in v2.data.columns


def test_main_role_thresholds():
    r = W.main_role([300, 0, 150, 10, 0], [0, 200, 150, 300, 0])
    assert list(r) == ["batter", "bowler", "all-rounder", "bowler", "batter"]


def test_fair_field_centres_groups_and_shrinks(monkeypatch):
    f = pd.DataFrame(
        dict(
            player=["K1", "K2", "A", "B"], sy=2024, role="field", balls=0, runs=0,
            wkts=[10, 6, 4, 2], sc=[10.0, 6.0, 4.0, 2.0], wk=[1.0, 0.0, 0.0, 0.0],
        )
    )
    apps = pd.DataFrame(dict(player=f.player, sy=2024, team="X", matches=[10, 10, 10, 10]))
    fair = dict(k_keeper=10.0, k_other=10.0, ro_w=0.5)
    monkeypatch.setattr(W, "keepers", lambda: frozenset(["K1", "K2"]))  # the reviewed list is not needed here
    out = W.fair_field(f, apps, fair).set_index("player")
    # keepers: group mean is 0.8 catches/match -> K1 +2, K2 -2 (x m/(m+k) = 0.5); others: A +1, B -1
    assert out.sc.round(3).to_dict() == {"K1": 1.0, "K2": -1.0, "A": 0.5, "B": -0.5}
    assert out.wk["K1"] == pytest.approx(0.5 * (1.0 - 0.025 * 10))  # run-outs: league mean 1/40 per match, then x ro_w
