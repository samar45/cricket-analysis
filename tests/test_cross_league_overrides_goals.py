"""Goal tests for reviewed Cricbuzz -> Cricsheet player link overrides (hand check docs/CHECK_uncapped.md). Frozen."""
import pytest

from cricket_analytics.scouting import profile as P

pytestmark = pytest.mark.skipif(not P.available(), reason="local Cricbuzz data not present")

IDS = {12926: "Varun Chakaravarthy", 14254: "Prabhsimran Singh", 10226: "Shahrukh Khan",
       11595: "Ravisrinivasan Sai Kishore", 10520: "Sharath BR", 12639: "Tejas Baroka"}


@pytest.mark.parametrize("cid", IDS)
def test_reviewed_player_is_ipl_capped_on_board(cid):
    row = P.board().set_index("cricbuzz_id").loc[cid]
    assert row.ipl_capped == "yes" and row.ipl_link == "reviewed"


def test_varun_profile_has_ipl_rows():
    p = P.profile("12926")
    assert len(p[p.competition == "IPL"]) >= 1 and (p[p.competition == "IPL"].link == "reviewed").all()
