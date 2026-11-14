"""Goal tests for the reel `--video` mode, bold headline numbers and percent-token formatting. Frozen."""

import re

import pytest
from click.testing import CliRunner

from cricket_analytics.cli import cli
from cricket_analytics.viz import match_reel

MID = "1535464"
CHARTS = {
    "match_curve": ["chart", "match_curve", MID, "--mark", "swing,low"],
    "score_curve": ["chart", "score_curve", MID, "--inn", "1"],
    "wpa": ["chart", "wpa", "--player", "V Kohli", "--competition", "ipl"],
    "scout_innings": ["chart", "scout_innings", "--scouting", "smat2025", "--player", "Ankit Kumar"],
    "scout_rank": ["chart", "scout_rank", "--scouting", "smat2025", "--role", "bat", "--focus", "Ankit Kumar"],
}


def draw(args, tmp_path, *extra):
    match_reel.SIZES.clear()
    r = CliRunner().invoke(cli, [*args, "--png", str(tmp_path / "c.png"), *extra])
    assert r.exit_code == 0, r.output
    return list(match_reel.SIZES)  # [(text, px, is_tick, is_bold)]


@pytest.mark.parametrize("name", CHARTS)
def test_video_mode_big_text_no_source(tmp_path, name):
    got = draw(CHARTS[name], tmp_path, "--video", "--size", "960x760")
    assert got
    for text, px, tick, _ in got:
        assert px >= (32 if tick else 36), (text, px)
        assert "Source" not in text and "model estimate" not in text


@pytest.mark.parametrize("name", CHARTS)
def test_default_mode_keeps_source_line(tmp_path, name):
    assert any("Source" in t for t, *_ in draw(CHARTS[name], tmp_path))


@pytest.mark.parametrize("extra", [[], ["--video"]])
def test_match_curve_headline_is_bold(tmp_path, extra):
    got = draw(CHARTS["match_curve"], tmp_path, *extra)
    head = max(got, key=lambda t: t[1])
    assert head[0].endswith("%") and head[3] is True


def test_percent_tokens_one_decimal(tmp_path):
    import json

    out = tmp_path / "f.json"
    r = CliRunner().invoke(cli, ["facts", "--match", MID, "--out", str(out)])
    assert r.exit_code == 0, r.output
    d = json.loads(out.read_text(encoding="utf-8"))
    for k in ("hero.wpa_pct", "hero2.wpa_pct"):
        assert re.fullmatch(r"\d+\.\d", d["tokens"][k]), d["tokens"][k]
        assert isinstance(d["tokens_raw"][k], float)
    assert d["tokens"]["curve.swing.delta_pct"].isdigit()
