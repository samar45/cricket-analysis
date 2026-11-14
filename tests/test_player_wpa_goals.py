"""Goal tests for reels request C: player WPA section in `cricket facts --player` and `cricket chart wpa`. Frozen."""

import json

import pytest
from click.testing import CliRunner
from PIL import Image

from cricket_analytics.cli import cli

PLAYER = "V Kohli"


def run(*args):
    return CliRunner().invoke(cli, list(args))


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    out = tmp_path_factory.mktemp("w") / "f.json"
    r = run("facts", "--player", PLAYER, "--competition", "ipl", "--out", str(out))
    assert r.exit_code == 0, r.output
    return json.loads(out.read_text(encoding="utf-8"))


def test_wpa_section_and_tokens(facts):
    w = facts["facts"]["wpa"]
    assert {"total", "per_match", "rank", "of", "min_matches", "matches"} <= set(w)
    assert 1 <= w["rank"] <= w["of"] and w["matches"] >= w["min_matches"]
    assert facts["meta"]["wpa_min_matches"] == w["min_matches"] and "wpa_definition" in facts["meta"]
    assert set(facts["tokens"]) == set(facts["tokens_raw"])
    assert "wpa.top.1.wpa" in facts["tokens"] and "wpa.total" in facts["tokens"]


def test_top_matches_are_his_best_and_unlocked(facts):
    import pandas as pd

    from cricket_analytics.analysis.wpa import ball_wpa
    from cricket_analytics.sql.filters import Filters

    d = ball_wpa(Filters(competition="ipl"))
    d = d[pd.to_datetime(d.date) < pd.Timestamp("2026-10-15")]
    per = (d[d.bat_who == PLAYER].groupby("match_id").bat_wpa.sum()
           .add(d[d.bowler == PLAYER].groupby("match_id").bowl_wpa.sum(), fill_value=0))
    top = facts["facts"]["wpa"]["top"]
    assert abs(top["1"]["wpa"] - per.max()) < 1e-3
    assert top["1"]["wpa"] >= top["2"]["wpa"] >= top["3"]["wpa"]
    assert abs(facts["facts"]["wpa"]["total"] - per.sum()) < 1e-2
    assert {"match_id", "date", "opponent", "wpa", "result"} <= set(top["1"])
    assert all(t["date"] < "2026-10-15" for t in top.values())


@pytest.mark.parametrize("extra,size", [([], (960, 980)), (["--size", "540x600"], (540, 600))])
def test_wpa_chart_png(tmp_path, extra, size):
    p = tmp_path / "w.png"
    r = run("chart", "wpa", "--player", PLAYER, "--competition", "ipl", "--png", str(p), *extra)
    assert r.exit_code == 0, r.output
    im = Image.open(p)
    assert im.size == size and im.mode == "RGBA" and im.getpixel((2, 2))[3] == 0
