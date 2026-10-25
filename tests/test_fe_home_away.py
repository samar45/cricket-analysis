"""home_away: fixture DB (IPL 1082591 SRH v RCB at Hyderabad, Hundred 1252666 at The Oval) + real-DB golden checks."""

from pathlib import Path

import pytest

from cricket_analytics import api
from cricket_analytics.analysis.home_away import _reference, match_sides
from cricket_analytics.db import query, use_db
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.sql.filters import Filters
from cricket_analytics.viz import home_away as vha, video
from tests.conftest import requires_real_db

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
real = requires_real_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("ha") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


def test_reference_files_are_consistent():
    venues, teams = _reference()
    assert venues.duplicated(["venue", "city"]).sum() == 0
    assert (venues[["country", "region", "site"]] != "").all().all()
    for t, (kind, places, _) in teams.items():   # every franchise home site exists in the venue file
        if kind == "franchise":
            missing = places - set(venues["site"])
            assert missing <= {"Peshawar", "Quetta", "Hyderabad (Sindh)"}, (t, missing)


def test_sides_fixture(db):
    with use_db(db):
        s = match_sides(Filters(competition="ipl")).set_index("team")["location"]
        assert s["Sunrisers Hyderabad"] == "home" and s["Royal Challengers Bengaluru"] == "away"
        h = match_sides(Filters(competition="hundred")).set_index("team")["location"]
        assert h["Oval Invincibles"] == "home" and h["Manchester Originals"] == "away"


def test_player_and_team_rows_fixture(db):
    bat = api.run("home_away", db_path=db, competition="ipl", player="Yuvraj Singh").data   # Yuvraj played for SRH
    assert bat["location"].tolist() == ["home"]
    raw = api.run("batting", db_path=db, competition="ipl", player="Yuvraj Singh").data
    assert bat["total_runs"].sum() == raw["total_runs"].iloc[0] and bat["balls"].sum() == raw["balls"].iloc[0]
    bowl = api.run("home_away", db_path=db, competition="ipl", player="B Kumar", role="bowling").data
    assert bowl["location"].tolist() == ["home"]
    team = api.run("home_away", db_path=db, competition="ipl").data.set_index("team")
    assert team.loc["Sunrisers Hyderabad", "location"] == "home" and team.loc["Royal Challengers Bengaluru", "location"] == "away"
    assert team["matches"].sum() == 2 and team["won"].sum() == 1   # one winner, one loser


def test_charts_build(db):
    for kw in (dict(player="Yuvraj Singh"), dict(player="B Kumar", role="bowling"), {}):
        r = api.run("home_away", db_path=db, competition="ipl", **kw)
        vha.figure(r)
        for aspect in ("9:16", "1:1"):
            fig = video.video_figure("home_away", r, aspect)
            assert fig.layout.width == 1080


@real
def test_real_kohli_ipl_adds_up():
    d = api.run("home_away", player="V Kohli", competition="ipl").data
    assert d["total_runs"].sum() == 9336 and set(d["location"]) == {"home", "away", "neutral"}


@real
def test_real_csk_home_beats_away():
    d = api.run("home_away", team="Chennai Super Kings", competition="ipl").data.set_index("location")
    assert d.loc["home", "win_pct"] > d.loc["away", "win_pct"]
    assert d["matches"].sum() == api.run("teams", team="Chennai Super Kings", competition="ipl").data["played"].iloc[0]


@real
def test_real_every_venue_is_placed():
    venues, _ = _reference()
    m = query("SELECT DISTINCT venue, COALESCE(city, '') AS city FROM matches")
    assert m.merge(venues, on=["venue", "city"], how="left")["country"].isna().sum() == 0
