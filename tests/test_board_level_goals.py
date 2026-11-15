"""Goal tests for board `level` and the new meaning of ipl_capped = unknown (only doubtful links). Frozen."""
import pytest

from cricket_analytics.scouting import profile as P

pytestmark = pytest.mark.skipif(not P.available(), reason="local Cricbuzz data not present")

LEVELS = {"IPL", "T20I", "SMAT", "state league only", "unclear (doubtful link)"}


@pytest.fixture(scope="module")
def board():
    return P.board()


def test_no_record_player_is_no_and_state_league_only(board):
    r = board.set_index("cricbuzz_id").loc[12636]  # Jhathavedh Subramanyan: no Cricsheet link, no SMAT 2025
    assert r.ipl_link == "" and not r.smat_in_2025
    assert r.ipl_capped == "no" and r.level == "state league only"


def test_naman_dhir_is_ipl(board):
    assert board.set_index("cricbuzz_id").loc[36139].level == "IPL"


def test_unknown_equals_doubtful(board):
    assert ((board.ipl_capped == "unknown") == (board.ipl_link == "doubtful")).all()
    assert (board[board.ipl_link == "doubtful"].level == "unclear (doubtful link)").all()


def test_level_values_allowed_and_consistent(board):
    assert set(board.level) <= LEVELS
    assert (board[board.ipl_capped == "yes"].level == "IPL").all()
    assert not (board[board.level == "IPL"].ipl_capped != "yes").any()
    assert (board[board.smat_in_2025 & (board.ipl_capped == "no")].level.isin(["SMAT", "T20I"])).all()
