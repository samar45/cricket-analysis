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
def test_v2_fielding_moves_credit_and_keeps_v1_default():
    r1, _ = W.season_table("ipl")
    r2, _ = W.season_table("ipl", fielding=W.FIELD_SHARES)
    assert "field" not in set(r1.role) and "field" in set(r2.role)
    # bat rows identical; the bowlers' wicket credit only shrinks (catches / stumpings moved to fielders)
    k = ["sy", "team", "player"]
    b1, b2 = (x[x.role == "bat"].groupby(k)[["sc", "wk"]].sum() for x in (r1, r2))
    assert (b1 - b2).abs().max().max() < 1e-9
    v1 = api.run("war", competition="ipl", season=2024, player="JJ Bumrah")
    v2 = api.run("war", competition="ipl", season=2024, player="JJ Bumrah", version="v2")
    assert "field_war" not in v1.data.columns and "field_war" in v2.data.columns
