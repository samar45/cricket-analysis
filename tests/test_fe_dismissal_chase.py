"""dismissal_profile and chase_vs_set: fixture-DB tests (tests/fixtures/cricsheet, IPL match 1082591) + real-DB golden checks."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from cricket_analytics import api, registry
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.viz import chase_vs_set as vchase, dismissal_profile as vdis, video

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
from tests.conftest import requires_real_db
from tests.conftest import REAL_DB as REAL
IPL = "1082591"
real = requires_real_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("fe") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    return path


@pytest.fixture(scope="module")
def raw():
    d = pd.read_csv(FIX / "ipl" / f"{IPL}.csv")
    for c in ("wides", "noballs"):
        d[c] = d[c].fillna(0)
    return d


def test_dismissal_kinds_match_csv(db, raw):
    d = api.run("dismissal_profile", db_path=db, competition="ipl").data
    w = raw[raw.player_dismissed.notna() & ~raw.wicket_type.isin(["retired hurt", "retired not out"])]
    assert d.outs.sum() == len(w)
    got = d.groupby("kind").outs.sum()
    assert got.get("run out", 0) == (w.wicket_type == "run out").sum()
    assert got.get("bowled", 0) == (w.wicket_type == "bowled").sum()
    caught = got.get("caught (fielder)", 0) + got.get("caught (keeper)", 0)
    assert caught == (w.wicket_type == "caught").sum()
    assert (d.groupby("batter").pct.sum().round(0) == 100).all()


@pytest.mark.parametrize("g", ["phase", "bowler_kind"])
def test_dismissal_splits_add_up(db, g):
    a = api.run("dismissal_profile", db_path=db, competition="ipl").data.outs.sum()
    d = api.run("dismissal_profile", db_path=db, competition="ipl", group_by=g).data
    assert d.outs.sum() == a and (d.groupby(["batter", g]).pct.sum().round(0) == 100).all()


def test_chase_vs_set_matches_csv(db, raw):
    d = api.run("chase_vs_set", db_path=db, competition="ipl").data
    bat = raw.groupby(["innings", "striker"]).runs_off_bat.sum()
    for r in d.itertuples():
        assert r.runs == bat[(1 if r.setting == "setting" else 2, r.player)]
    b = api.run("chase_vs_set", db_path=db, competition="ipl", role="bowling").data
    assert b.wickets.sum() == raw.wicket_type.isin(["bowled", "caught", "lbw", "stumped", "caught and bowled", "hit wicket"]).sum()
    assert set(b.setting) == {"setting", "chasing"}


def test_charts_build(db):
    for mid, role in (("dismissal_profile", None), ("chase_vs_set", "batting"), ("chase_vs_set", "bowling")):
        kw = {"role": role} if role else {}
        r = api.run(mid, db_path=db, competition="ipl", **kw)
        mod = vdis if mid == "dismissal_profile" else vchase
        assert isinstance(mod.figure(r), go.Figure)
        for aspect in ("9:16", "1:1"):
            assert isinstance(video.video_figure(mid, r, aspect), go.Figure)
    one = api.run("chase_vs_set", db_path=db, player=api.run("chase_vs_set", db_path=db, competition="ipl").data.player[0])
    assert isinstance(vchase.figure(one), go.Figure)


@real
def test_golden_kohli_ipl():
    d = api.run("dismissal_profile", player="V Kohli", competition="ipl").data
    b = api.run("batting", player="V Kohli", competition="ipl").data.iloc[0]
    assert d.outs.sum() == b.innings - b.not_outs == 231
    c = api.run("chase_vs_set", player="V Kohli", competition="ipl").data
    assert c.runs.sum() == b.total_runs == 9336 and c.innings.sum() == b.innings
    assert set(c.setting) == {"setting", "chasing"}
    for aspect in ("9:16", "1:1"):
        for focus in (None, "strike_rate", "win_pct"):
            video.video_figure("chase_vs_set", api.run("chase_vs_set", player="V Kohli", competition="ipl"), aspect, focus)
