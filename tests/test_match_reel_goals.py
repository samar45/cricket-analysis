"""Goal tests for reels request 2: match win-probability / projected-score curves via the CLI. Frozen.
Match 1535464 = IPL 2026-05-29, RR 214/6, GT won chasing 215 (219/3)."""

import json

import pytest
from click.testing import CliRunner
from PIL import Image

from cricket_analytics.cli import cli

MID = "1535464"
LOCKED = "1529234"  # India v West Indies 2026-10-17: men's, >= 2026-10-15, full members = fresh set #3


def run(*args):
    return CliRunner().invoke(cli, list(args))


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    out = tmp_path_factory.mktemp("f") / "f.json"
    r = run("facts", "--match", MID, "--out", str(out))
    assert r.exit_code == 0, r.output
    return json.loads(out.read_text(encoding="utf-8"))


def test_match_facts_basics(facts):
    m = facts["facts"]["match"]
    assert m["winner"] == "Gujarat Titans" and m["target"] == 215 and m["date"] == "2026-05-29"
    assert set(facts["meta"]) >= {"data_through", "source", "in_sample", "model_version", "wpa_definition"}
    assert isinstance(facts["meta"]["in_sample"], bool)
    assert facts["facts"]["curve"]["low"]["team"] == "Gujarat Titans"


def test_series_and_swing(facts):
    rows = facts["facts"]["series"]["overs"]
    chase = [r for r in rows if r["inn"] == 2]
    assert chase and all(0 <= r["win_pct"] <= 1 for r in chase)
    assert chase[-1]["win_pct"] > 0.9
    assert all("win_pct" not in r for r in rows if r["inn"] == 1)
    steps = [abs(b["win_pct"] - a["win_pct"]) for a, b in zip(chase, chase[1:])]
    sw = facts["facts"]["curve"]["swing"]
    assert abs(abs(sw["delta"]) - max(steps)) < 1e-6
    assert {"over", "from", "to", "bowler", "batter"} <= set(sw)


def test_tokens_same_keys_and_extras(facts):
    assert set(facts["tokens"]) == set(facts["tokens_raw"]) and facts["tokens"]
    assert "hero" in facts["facts"] and "player" in facts["facts"]["hero"]
    assert "player" in facts["facts"]["hero2"] and "wpa" in facts["facts"]["hero2"]
    pm = facts["facts"]["pre_match"]
    assert isinstance(pm["out_of_sample"], bool)
    assert pm["out_of_sample"] or "win_pct" not in pm  # never a pre-match number for an in-sample match


def test_locked_match_exits_1(tmp_path):
    out = tmp_path / "x.json"
    r = run("facts", "--match", LOCKED, "--out", str(out))
    assert r.exit_code == 1 and "locked: fresh set #3" in r.output and not out.exists()
    r = run("chart", "match_curve", LOCKED, "--png", str(tmp_path / "x.png"))
    assert r.exit_code == 1 and "locked: fresh set #3" in r.output


@pytest.mark.parametrize("args,size", [(["match_curve", MID, "--mark", "swing,low"], (960, 980)),
                                       (["score_curve", MID, "--inn", "1"], (960, 980)),
                                       (["match_curve", MID, "--upto", "10", "--size", "540x600"], (540, 600))])
def test_chart_png_transparent_and_sized(tmp_path, args, size):
    p = tmp_path / "c.png"
    r = run("chart", *args, "--png", str(p))
    assert r.exit_code == 0, r.output
    im = Image.open(p)
    assert im.size == size and im.mode == "RGBA" and im.getpixel((2, 2))[3] == 0


def test_match_find():
    r = run("match", "find", "--team", "Rajasthan Royals", "--opponent", "Gujarat Titans", "--season", "2026", "--competition", "ipl", "--json")
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)
    assert any(x["match_id"] == MID and x["result"] for x in rows) and {"date", "teams", "venue"} <= set(rows[0])
    bad = run("match", "find", "--team", "Rajasthan Royal", "--json")
    assert bad.exit_code == 1 and "Rajasthan Royals" in bad.output
