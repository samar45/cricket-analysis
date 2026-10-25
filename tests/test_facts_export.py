"""`cricket facts` / `cricket chart` / `cricket update` wiring: fixture DB always, real DB golden when it exists."""

import json
import struct
import warnings
from pathlib import Path

import pytest
from click.testing import CliRunner

from cricket_analytics import api, facts, export
from cricket_analytics.cli import cli
from cricket_analytics.ingest.cricsheet import load_to_db

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent.parent
FIX = Path(__file__).parent / "fixtures" / "cricsheet"
from tests.conftest import requires_real_db
from tests.conftest import REAL_DB as REAL
real = requires_real_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("f") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    return path


def invoke(*args):
    return CliRunner().invoke(cli, [str(a) for a in args])


def test_facts_batter_keys_and_provenance(db):
    d = facts.build("Yuvraj Singh", "ipl", db_path=db)
    assert set(d) == {"meta", "facts", "tokens", "tokens_raw"}
    m = d["meta"]
    assert m["facts_version"] == 1 and m["source"].startswith("Cricsheet") and m["data_through"] and m["generated"]
    assert m["params"] == {"player": "Yuvraj Singh", "competition": "ipl"} and m["competition_note"] is None
    assert m["calls"] and all({"module", "params"} <= set(c) for c in m["calls"])
    c = d["facts"]["career"]
    assert c["runs"] == int(api.run("batting", player="Yuvraj Singh", competition="ipl", db_path=db).data["total_runs"].iloc[0])
    assert c["source"][0]["module"] == "batting"
    # every section names its module calls; sections without data are listed in meta.skipped, not present
    assert all(s["source"] for s in d["facts"].values())
    assert not set(d["facts"]) & {s["section"] for s in m["skipped"]}
    # tokens: same keys as raw, formatted strings
    assert d["tokens"].keys() == d["tokens_raw"].keys() and "career.runs" in d["tokens"]
    assert d["tokens"]["career.runs"] == f"{c['runs']:,}" and not any(k.endswith(".source") for k in d["tokens"])
    json.dumps(d)   # serialisable


def test_facts_default_competition_is_said(db):
    assert "all men's" in facts.build("Yuvraj Singh", db_path=db)["meta"]["competition_note"]


def test_facts_bowler_gets_bowling_career(db):
    d = facts.build("B Kumar", "ipl", db_path=db)
    assert d["meta"]["role"] == "bowling" and "wickets" in d["facts"]["career"] and "vs_pace_spin" not in d["facts"]


def test_facts_unknown_player_lists_candidates(db):
    with pytest.raises(facts.PlayerNotFound) as e:
        facts.build("Yuvraj", "ipl", db_path=db)
    assert e.value.candidates[0]["name"] == "Yuvraj Singh"


def test_cli_facts_exit_codes(db, tmp_path):
    out = tmp_path / "sub" / "f.json"
    ok = invoke("facts", "--player", "Yuvraj Singh", "--competition", "ipl", "--db", db, "--out", out)
    assert ok.exit_code == 0, ok.output
    assert json.loads(out.read_text(encoding="utf-8"))["meta"]["facts_version"] == 1
    bad = invoke("facts", "--player", "Yuvraj", "--competition", "ipl", "--db", db, "--out", tmp_path / "x.json")
    assert bad.exit_code != 0 and "Yuvraj Singh" in bad.output and not (tmp_path / "x.json").exists()
    assert invoke("facts", "--player", "Yuvraj Singh").exit_code != 0   # --out is required


def test_chart_empty_result_fails(db, tmp_path):
    with pytest.raises(export.EmptyResult):
        export.render("batting", png=tmp_path / "a.png", db_path=db, player="Nobody Here")
    r = invoke("chart", "batting", "--player", "Nobody Here", "--db", db, "--png", tmp_path / "a.png")
    assert r.exit_code != 0 and "no rows" in r.output and not (tmp_path / "a.png").exists()
    assert invoke("chart", "batting", "--db", db).exit_code != 0                       # needs --png or --html
    assert invoke("chart", "batting", "--aspect", "4:3", "--png", tmp_path / "b.png").exit_code != 0
    assert invoke("chart", "nope", "--png", tmp_path / "c.png").exit_code != 0         # unknown module


@pytest.mark.parametrize("aspect,size", [("9:16", (1080, 1920)), ("1:1", (1080, 1080))])
def test_chart_png_size(db, tmp_path, aspect, size):
    png, html = tmp_path / "c.png", tmp_path / "c.html"
    r = invoke("chart", "batting", "--player", "Yuvraj Singh", "--competition", "ipl", "--aspect", aspect,
               "--db", db, "--png", png, "--html", html)
    if r.exit_code != 0 and "kaleido" in r.output.lower():
        pytest.skip("kaleido / browser unavailable")
    assert r.exit_code == 0, r.output
    head = png.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", head[16:24]) == size
    assert html.stat().st_size > 10_000


def test_update_command_is_wired():
    r = invoke("update", "--help")
    assert r.exit_code == 0 and "--dry-run" in r.output and "--replace-changed" in r.output and "--no-download" in r.output


@real
def test_real_kohli_ipl_golden(tmp_path):
    out = tmp_path / "k.json"
    r = invoke("facts", "--player", "V Kohli", "--competition", "ipl", "--out", out)
    assert r.exit_code == 0, r.output
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["facts"]["career"]["runs"] == 9336 and d["tokens"]["career.runs"] == "9,336"
    assert d["facts"]["career"]["hundreds"] == 9 and d["tokens"]["career.average"] == "40.42"
    assert d["tokens"]["by_phase.death.strike_rate"] == "188.4"   # 100+ shows one decimal, as on the charts
