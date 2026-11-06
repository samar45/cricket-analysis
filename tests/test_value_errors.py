"""Clear errors instead of silent empty tables (E2E findings F1-F6, docs/E2E_value.md). Real DB, read-only."""

import pytest

from cricket_analytics import api
from tests.conftest import requires_real_db

pytestmark = requires_real_db
MI, RR = "Mumbai Indians", "Rajasthan Royals"


def test_f1_wpa_bad_and_dl_match_ids_explained():
    with pytest.raises(ValueError, match="not in the database"):
        api.run("wpa", view="match", match_id=1)
    with pytest.raises(ValueError, match="Duckworth"):
        api.run("wpa", view="match", match_id=1370353)  # 2023 IPL final, D/L


def test_f1_unknown_player_has_spelling_hint():
    with pytest.raises(ValueError, match="Closest"):
        api.run("runs_added", player="Virat Kohlii", competition="ipl")


def test_f1_known_player_no_data_in_filters():
    with pytest.raises(ValueError, match="widen them"):
        api.run("war", player="V Kohli", season=1999, competition="ipl")


def test_f2_war_projected_chart_scope_is_ipl():
    from cricket_analytics.viz.video import scope_text

    r = api.run("war", view="projected", top=5)
    assert scope_text(r, default="IPL") == "IPL"


def test_f3_same_player_both_sides():
    with pytest.raises(ValueError, match="both sides"):
        api.run("trade", team=MI, team2=RR, give="Hardik Pandya", get="hardik pandya")


def test_f4_unknown_must_play_is_short():
    with pytest.raises(ValueError, match="Closest") as e:
        api.run("trade", team=MI, team2=RR, give="Hardik Pandya", must_play=["Zzzz Nobody"])
    assert len(str(e.value)) < 300


def test_f5_empty_give_and_get_is_a_labelled_no_change():
    d = api.run("trade", team=MI, team2=RR).data
    assert (d.verdict == "no change to the best XII").all()


def test_f6_caveat_explains_recentring():
    from cricket_analytics import registry

    for mod in ("war", "runs_added"):
        assert any("re-centre" in c for c in registry.get(mod).caveats)
