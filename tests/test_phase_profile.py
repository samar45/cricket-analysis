"""Phase profile: tag rules on synthetic numbers, and Bumrah's death-over balls against a hand SQL count."""

import pytest

from cricket_analytics.db import query
from cricket_analytics.models import phase_profile as PP


def t(balls, comp, role="bowl"):
    return PP.tag(dict(zip(PP.F.PHASES, balls)), dict(zip(PP.F.PHASES, comp)), role)


def test_tags():
    assert t((200, 200, 200), (70, 80, 90)) == "Complete"
    assert t((200, 200, 200), (70, 30, 90)) == "Two-phase (PP+Death)"
    assert t((400, 50, 50), (80, 10, 10)) == "Powerplay specialist"
    assert t((50, 50, 400), (10, 10, 80), "bat") == "Finisher"
    assert t((50, 400, 50), (10, 80, 10), "bat") == "Middle-overs specialist"
    assert t((100, 300, 100), (80, 20, 20)) == "Good in powerplay"  # good in one, but most balls elsewhere
    assert t((100, 400, 100), (50, 50, 50)) == "Limited role"
    assert t((59, 59, 59), (99, 99, 99)) is None  # under the minimum everywhere
    assert t((50, 300, 200), (99, 40, 59)) == "Limited role"  # 59 is not good; 50 balls is not enough


@pytest.mark.parametrize("player,role,phase", [("JJ Bumrah", "bowl", "death")])
def test_golden_balls(player, role, phase):
    n = query(
        f"""SELECT COUNT(*) FROM deliveries d JOIN matches m USING (match_id) WHERE d.bowler = ? AND m.competition = 'ipl'
        AND m.gender = 'male' AND d.innings <= 2 AND d.wides = 0 AND d.noballs = 0 AND d.over_num >= 15
        AND year(m.date) >= 2023""",
        [player],
    ).iloc[0, 0]
    p = PP.profile(player, "ipl", 2023, None, (role,))[role]
    assert p["balls"][phase] == n > 200 and p["tag"] == "Complete"
