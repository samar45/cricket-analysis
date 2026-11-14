"""Goal tests for reels follow-ups: curve.swing_mid and short team codes. Frozen."""

import json

import pytest
from click.testing import CliRunner

from cricket_analytics.cli import cli

MID = "1535464"


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    out = tmp_path_factory.mktemp("g") / "f.json"
    r = CliRunner().invoke(cli, ["facts", "--match", MID, "--out", str(out)])
    assert r.exit_code == 0, r.output
    return json.loads(out.read_text(encoding="utf-8"))


def test_swing_mid(facts):
    c = facts["facts"]["curve"]
    sm = c["swing_mid"]
    assert {"over", "delta", "from", "to", "batter", "bowler", "inn"} <= set(sm) and sm["over"] >= 3 and sm["inn"] == 2
    ch = [r for r in facts["facts"]["series"]["overs"] if r["inn"] == 2 and "win_pct" in r]
    steps = [abs(b["win_pct"] - a["win_pct"]) for a, b in zip(ch, ch[1:]) if b["over"] >= 3]
    assert abs(abs(sm["delta"]) - max(steps)) < 1e-6
    assert "swing" in c and c["swing"]["over"] <= 2 or c["swing"]["over"] == sm["over"]  # curve.swing is the unrestricted one


def test_team_short_tokens(facts):
    t, m = facts["tokens"], facts["facts"]["match"]
    assert t["match.team1_short"] == "RR" and t["match.team2_short"] == "GT" and m["team2_short"] == "GT"


def test_team_short_table():
    from cricket_analytics.reference import team_short

    assert team_short("Rising Pune Supergiants") == "RPS"
    assert team_short("Gujarat Titans") == "GT" and team_short("Mumbai Indians") == "MI"
    assert team_short("Deccan Chargers") == "DCG" and team_short("India") == "IND"
    assert team_short("Some Brand New Team") == "SBNT"  # fallback: first letters


def test_charts_draw_only_short_team_codes(tmp_path):
    from cricket_analytics.viz import match_reel

    for args in (["match_curve", MID, "--mark", "swing,low"], ["score_curve", MID, "--inn", "2"]):
        match_reel.DRAWN.clear()
        r = CliRunner().invoke(cli, ["chart", *args, "--png", str(tmp_path / "a.png")])
        assert r.exit_code == 0, r.output
        text = " ".join(match_reel.DRAWN)
        assert "GT" in text or "RR" in text
        assert not any(n in text for n in ("Gujarat Titans", "Rajasthan Royals", "GUJARAT TITANS", "RAJASTHAN ROYALS"))
    match_reel.DRAWN.clear()
    r = CliRunner().invoke(cli, ["chart", "wpa", "--player", "V Kohli", "--competition", "ipl", "--png", str(tmp_path / "w.png")])
    assert r.exit_code == 0, r.output
    text = " ".join(match_reel.DRAWN)
    assert "Rising Pune" not in text and "RPS" in text
