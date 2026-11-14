"""Goal tests for the reels-facing SMAT 2025-26 scouting commands (resolve, facts, list, charts). Frozen."""
import json

import pandas as pd
import pytest
from click.testing import CliRunner

from cricket_analytics.cli import cli
from cricket_analytics.scouting import smat2025 as s

pytestmark = pytest.mark.skipif(
    not (s.ROOT / "scouting_batters.csv").exists(), reason="SMAT scouting tables not saved locally"
)


def run(*args):
    return CliRunner().invoke(cli, list(args))


@pytest.fixture(scope="module")
def ankit(tmp_path_factory):
    f = tmp_path_factory.mktemp("f") / "f.json"
    r = run("facts", "--scouting", "smat2025", "--player", "Ankit Kumar", "--out", str(f))
    assert r.exit_code == 0, r.output
    return json.loads(f.read_text(encoding="utf-8"))


def test_ankit_headline_numbers(ankit):
    t = ankit["tokens_raw"]
    assert (t["scout.runs"], t["scout.balls"], t["scout.inns"]) == (448, 260, 11)
    assert ankit["meta"]["source"] and ankit["meta"]["data_through"]


def test_tokens_and_raw_have_same_keys(ankit):
    assert set(ankit["tokens"]) == set(ankit["tokens_raw"])
    assert all(isinstance(v, str) for v in ankit["tokens"].values())


def test_best_innings_is_his_max(ankit):
    b = pd.read_parquet(s.ROOT / "batting.parquet")
    mx = b[b.cricbuzz_id == 14438].runs.max()
    t = ankit["tokens_raw"]
    assert t["best.1.runs"] == mx
    assert t["best.1.runs"] >= t["best.2.runs"] >= t["best.3.runs"]
    for k in ("balls", "fours", "sixes", "opponent", "date", "venue", "result", "match_id"):
        assert f"best.1.{k}" in t


def test_inexact_name_exits_1_with_candidates():
    r = run("facts", "--scouting", "smat2025", "--player", "Ankit Kumr", "--out", "x.json")
    assert r.exit_code == 1 and "Ankit Kumar" in r.output
    r = run("resolve", "--scouting", "smat2025", "Ankit")
    assert r.exit_code == 1 and "Ankit Kumar" in r.output
    r = run("resolve", "--scouting", "smat2025", "Ankit Kumar")
    assert r.exit_code == 0 and "14438" in r.output


def test_list_uncapped_no_ipl():
    r = run("scouting", "list", "smat2025", "--uncapped", "--no-ipl", "--role", "bat", "--json")
    assert r.exit_code == 0, r.output
    rows = json.loads(r.output)["data"]
    assert rows and all(x["ipl_status"] == "no IPL record" and x["t20i"] == "uncapped" for x in rows)


@pytest.mark.parametrize("size,want", [(None, (960, 980)), ("700x800", (700, 800))])
def test_chart_png_size_and_transparency(tmp_path, size, want):
    from PIL import Image

    p = tmp_path / "c.png"
    args = ["chart", "scout_innings", "--scouting", "smat2025", "--player", "Ankit Kumar", "--png", str(p)]
    r = run(*args, *(["--size", size] if size else []))
    assert r.exit_code == 0, r.output
    im = Image.open(p)
    assert im.size == want and im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 0


def test_rank_chart_with_palette(tmp_path):
    p = tmp_path / "r.png"
    r = run("chart", "scout_rank", "--scouting", "smat2025", "--role", "bat", "--focus", "Ankit Kumar",
            "--png", str(p), "--palette", '{"bg":"#01411c","ink":"#f5f3ea","a1":"#8bd450","a2":"#e8b923"}')
    assert r.exit_code == 0, r.output
    assert p.stat().st_size > 5000
