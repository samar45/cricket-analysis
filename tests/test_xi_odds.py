"""xi_odds module: numbers for a chosen XI against the tool's best XII (DB-free: saved match file, contracts, beta file)."""

import numpy as np
import pytest

from cricket_analytics.analysis import xi_odds as X
from cricket_analytics.models import trade as T
from cricket_analytics.viz import xi_odds as V


@pytest.fixture(scope="module")
def mi():
    return X.evaluate_xi("Mumbai Indians")


def test_no_players_is_the_best_xii(mi):
    assert mi["you"]["value"] == mi["best"]["value"] and not mi["custom"]
    assert all(q["ok"] for q in mi["best"]["rules"])  # the search only returns legal XIs
    for m in ("win", "playoff", "title"):
        assert 0 <= mi["best"][m][1] <= mi["best"][m][0] <= mi["best"][m][2] <= 1
    assert mi["best"]["range"][0] < mi["best"]["value"] < mi["best"]["range"][1]


def test_custom_xi_is_worse_than_best_and_flags_rules(mi):
    # the 11 lowest-valued MI players: worse value, lower odds, and the same-team XI needs no outside flag
    names = list(T.squads().query("team == 'MI'").player)
    pt = T.player_table(T.squads(), T.values(), T.DEFAULT_BASIS)
    mi_pt = pt[pt.team == "MI"].sort_values("value")
    r = X.evaluate_xi("MI", list(mi_pt.player[:11]), list(mi_pt.player[11:12]))
    assert r["custom"] and r["you"]["value"] < r["best"]["value"]
    assert r["you"]["win"][0] < r["best"]["win"][0] and r["you"]["playoff"][0] <= r["best"]["playoff"][0]
    assert not any(q["outside"] for q in r["you"]["rows"]) and len(r["you"]["rows"]) == 12
    assert len(names) >= 11 and len(r["you"]["rules"]) == 4


def test_outside_player_flagged_and_bad_input_rejected(mi):
    best = [q["name"] for q in mi["best"]["rows"] if q["slot"] == "XI"]
    rr = T.player_table(T.squads(), T.values())
    outsider = rr[rr.team == "RR"].player.iloc[0]
    r = X.evaluate_xi("MI", best[:10] + [outsider])
    assert [q["name"] for q in r["you"]["rows"] if q["outside"]] == [outsider]
    with pytest.raises(ValueError, match="exactly 11"):
        X.evaluate_xi("MI", best[:10])
    with pytest.raises(ValueError, match="impact"):
        X.evaluate_xi("MI", best, [best[0]])


def test_more_value_means_more_win_pct():
    pt = T.player_table(T.squads(), T.values(), T.DEFAULT_BASIS)
    top = pt.sort_values("value", ascending=False).player
    r = X.evaluate_xi("MI", list(top[:11]))
    assert r["you"]["win"][0] > 0.5 and np.isfinite(r["you"]["title"][0])  # an XI of the league's 11 best beats the average


def test_html_has_the_numbers_and_escapes(mi):
    import pandas as pd

    mi["best"]["rows"][0]["name"] = "<b>x</b>"
    df = pd.DataFrame({"a": [1]})
    df.attrs["card"] = mi
    res = type("R", (), {"data": df})()
    h = V.html(res)
    assert "WIN %" in h and "PLAYOFF %" in h and "TITLE %" in h
    assert [t for t, _ in V.details(res)] == ["Rules check", "Players"] and V.method_note(res)
    assert "&lt;b&gt;" in "".join(b for _, b in V.details(res))
