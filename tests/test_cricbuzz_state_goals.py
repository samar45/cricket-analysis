"""Goal tests for the Indian state T20 leagues from Cricbuzz (no network; one saved match fixture). Frozen.

Fixture tests/fixtures/cricbuzz_state/171243: Shere-e-Punjab T20 Cup 2026, Final (Amritsar Soormas v Ludhiana Lions).
Cricsheet has no state leagues, so there is nothing to compare with: verify must say `no_cricsheet_source`, not `waiting`.
"""
import shutil
from pathlib import Path

import pandas as pd
import pytest

from cricket_analytics.ingest import cricbuzz_series as cb
from cricket_analytics.ingest import cricbuzz_sync as sy

F = Path(__file__).parent / "fixtures" / "cricbuzz_state"

NAMES = {
    "Shere-e-Punjab T20 Cup 2026": "state_spl", "Sher-e-Punjab T20 League 2026": "state_spl",
    "Uttar Pradesh Premier League 2025": "state_upt20", "UP T20 League 2026": "state_upt20",
    "Tamil Nadu Premier League 2025": "state_tnpl", "TNPL 2026": "state_tnpl",
    "Delhi Premier League 2026": "state_dpl", "Maharaja Trophy KSCA T20 2025": "state_maharaja",
    "T20 Mumbai 2026": "state_mumbai", "Mumbai T20 League 2026": "state_mumbai",
    "Bengal Pro T20 League 2025": "state_bengal", "Saurashtra Premier League 2023": "state_saurashtra",
}


@pytest.mark.parametrize("name,key", NAMES.items())
def test_series_name_maps_to_state_key(name, key):
    assert sy.classify(dict(id=1, slug="x", name=name, section="DOMESTIC", descs=[])) == key


def test_womens_editions_and_untracked_stay_out():
    for name, section in (("Women's Delhi Premier League 2026", "WOMEN"), ("Tamil Nadu Premier League Women 2026", "DOMESTIC"),
                          ("Maharaja Trophy KSCA T20 U19 2025", "DOMESTIC")):
        assert sy.classify(dict(id=1, slug="x", name=name, section=section, descs=[])) is None
    assert sy.classify(dict(id=1, slug="x", name="Ranji Trophy Elite 2026-27", section="DOMESTIC", descs=[])) is None


def test_archive_page_yields_state_series_only():
    page = "".join(f'<a href="/cricket-series/{i}/{slug}/matches">x</a>' for i, slug in (
        (1, "tamil-nadu-premier-league-2024"), (2, "womens-premier-league-2024"), (3, "sher-e-punjab-t20-league-2026"), (4, "ranji-trophy-elite-2024-25")))
    kept, _, _ = sy.discover(page)
    assert {(s["id"], s["comp"]) for s in kept} == {(1, "state_tnpl"), (3, "state_spl")}
    assert {s["comp"] for s in sy.state_series(kept)} <= {c for c in NAMES.values()}


def test_finished_matches_count_whatever_the_state_case():
    ms = [dict(matchId=i, seriesId=1, state=s, matchFormat="T20", matchDesc="x") for i, s in ((1, "complete"), (2, "Complete"), (3, "upcoming"))]
    assert [m["matchId"] for m in sy.wanted(ms, "state_tnpl")] == [1, 2]


@pytest.fixture(scope="module")
def parsed():
    return cb.parse_match("171243", dict(desc="Final"), {}, root=F)


def test_batting_runs_plus_extras_equal_innings_total(parsed):
    assert len(parsed["innings"]) == 2
    for inn in parsed["innings"]:
        runs = sum(b["runs"] for b in parsed["batting"] if b["innings"] == inn["innings"])
        assert runs + inn["extras"] == inn["runs"]
        assert inn["wickets"] <= 10


def test_complete_ball_by_ball_adds_up_to_the_scorecard(parsed):
    for inn in parsed["innings"]:
        assert sum(d["runs_total"] for d in parsed["deliveries"] if d["innings"] == inn["innings"]) == inn["runs"]


def test_state_league_match_has_no_cricsheet_source(parsed):
    row = sy.verify_one(parsed["match"], pd.DataFrame(parsed["innings"]), pd.DataFrame(parsed["batting"]), None, "state_spl", {}, {}, set())
    assert row["status"] == "no_cricsheet_source"
    assert row["cricsheet_match_id"] == ""


def test_player_link_is_name_only_and_never_guessed(tmp_path, parsed):
    d = tmp_path / "state_spl" / "1"
    shutil.copytree(F, d)
    one = parsed["batting"][0]["name"]
    pool = {cb._short(one), "Z Nobody"}
    sy.parse_series("state_spl", 1, tmp_path, pool=pool)
    bat = pd.read_parquet(d / "batting.parquet")
    hit = bat[bat.name == one]
    assert (hit.cricsheet_name == cb._short(one)).all() and (hit.link == "name_only").all()
    assert (bat[bat.name != one].cricsheet_name == "").all()  # nobody else is linked
    assert (bat[bat.name != one].link == "").all()
