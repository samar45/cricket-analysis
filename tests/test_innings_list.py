"""innings_list: fixture DB (IPL 1082591 SRH v RCB) + real-DB golden checks."""

import warnings
from pathlib import Path

import pytest

from cricket_analytics import api
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.viz import innings_list as viz, video
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")
FIX = Path(__file__).parent / "fixtures" / "cricsheet"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("il") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    return path


def test_fixture_batting_matches_batting_module(db):
    row = api.run("innings_list", db_path=db, competition="ipl", player="Yuvraj Singh", order="first", n=1).data.iloc[0]
    tot = api.run("batting", db_path=db, competition="ipl", player="Yuvraj Singh").data.iloc[0]
    assert row.runs == tot.total_runs and row.team != row.opposition and row.result in ("won", "lost")
    assert row.position >= 1 and row.score.rstrip("*") == str(row.runs)


def test_fixture_bowling_and_best_order(db):
    d = api.run("innings_list", db_path=db, competition="ipl", role="bowling", order="best", n=3).data
    assert d["wickets"].is_monotonic_decreasing and (d["figures"] == d["wickets"].astype(str) + "/" + d["runs"].astype(str)).all()
    b = api.run("innings_list", db_path=db, competition="ipl", order="best", n=5).data   # no player: best innings overall
    assert b["runs"].is_monotonic_decreasing and b["player"].nunique() > 1


def test_charts_build(db):
    for k in (dict(player="Yuvraj Singh", n=1, order="first"), dict(competition="ipl", n=5), dict(role="bowling", competition="ipl", n=4),
              dict(role="bowling", competition="ipl", n=1), dict(player="Nobody At All")):
        r = api.run("innings_list", db_path=db, **k)
        viz.figure(r)
        for aspect in ("9:16", "1:1"):
            video.video_figure("innings_list", r, aspect)


def test_bad_params(db):
    with pytest.raises(ValueError):
        api.run("innings_list", db_path=db, order="middle")


@requires_real_db
def test_golden_real_db():
    def run(**k):
        return api.run("innings_list", **k).data
    d = run(player="Naman Dhir", competition="ipl", order="first", n=1).iloc[0]
    assert (str(d.date)[:10], d.runs, d.balls, d.opposition) == ("2024-03-24", 20, 10, "Gujarat Titans")
    k = run(player="V Kohli", competition="ipl", order="first", n=1).iloc[0]
    assert (str(k.date)[:10], k.runs, k.balls, k.opposition) == ("2008-04-18", 1, 5, "Kolkata Knight Riders")
    last = run(player="V Kohli", competition="ipl", order="last", n=5)
    assert len(last) == 5 and last["date"].is_monotonic_decreasing and last.iloc[0].score == "75*"
    assert run(player="JJ Bumrah", competition="ipl", role="bowling", order="best", n=1).iloc[0].figures == "5/10"
    top = run(competition="ipl", venue="Wankhede Stadium", order="best", n=1).iloc[0]
    assert (top.player, top.runs) == ("AB de Villiers", 133)
