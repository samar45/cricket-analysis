"""fielding: fixture-DB tests (IPL match 1082591, compared with the raw CSV) + real-DB golden checks."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from cricket_analytics import api
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.viz import fielding as vfield, video
from tests.conftest import requires_real_db

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
real = requires_real_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("field") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    return path


@pytest.fixture(scope="module")
def raw():
    return pd.read_csv(FIX / "ipl" / "1082591.csv")


def test_matches_csv(db, raw):
    d = api.run("fielding", db_path=db, competition="ipl").data.set_index("fielder")
    w = raw[raw.wicket_type.notna()]
    assert d.catches.sum() == (w.wicket_type == "caught").sum()
    assert d.caught_and_bowled.sum() == (w.wicket_type == "caught and bowled").sum()
    assert d.stumpings.sum() == (w.wicket_type == "stumped").sum()
    ro = w[w.wicket_type == "run out"]
    names = pd.concat([ro.fielder_1, ro.fielder_2, ro.fielder_3]).dropna()
    assert d.run_outs.sum() == len(names)
    assert d.run_outs_direct.sum() == (ro.fielder_1.notna() & ro.fielder_2.isna()).sum()
    for p, n in names.value_counts().items():
        assert d.loc[p, "run_outs"] == n
    cb = w[w.wicket_type == "caught and bowled"].bowler.value_counts()
    for p, n in cb.items():
        assert d.loc[p, "caught_and_bowled"] == n
    t = d.catches + d.caught_and_bowled + d.stumpings + d.run_outs
    assert (d.total_dismissals == t).all() and (d.matches == 1).all()


def test_options(db):
    all_ = api.run("fielding", db_path=db, competition="ipl").data
    top = api.run("fielding", db_path=db, competition="ipl", top=3).data
    assert len(top) == 3 and top.total_dismissals.is_monotonic_decreasing
    s = api.run("fielding", db_path=db, competition="ipl", group_by="season").data
    assert s.total_dismissals.sum() == all_.total_dismissals.sum() and "season" in s
    k = api.run("fielding", db_path=db, competition="ipl", role="keeper").data
    o = api.run("fielding", db_path=db, competition="ipl", role="outfield").data
    assert len(k) + len(o) == len(all_)
    one = api.run("fielding", db_path=db, player=all_.fielder.iloc[0]).data
    assert len(one) == 1
    assert api.run("fielding", db_path=db, competition="ipl", min_matches=2).data.empty


def test_charts_build(db):
    for kw in ({}, {"group_by": "season"}, {"top": 1}, {"player": "A Choudhary"}):
        r = api.run("fielding", db_path=db, competition="ipl", **kw)
        assert isinstance(vfield.figure(r), go.Figure)
        for aspect in ("9:16", "1:1"):
            assert isinstance(video.video_figure("fielding", r, aspect), go.Figure)
    r = api.run("fielding", db_path=db, competition="ipl", team="Nonexistent FC")
    assert r.data.empty and isinstance(video.video_figure("fielding", r), go.Figure)


@real
def test_golden_ipl():
    d = api.run("fielding", competition="ipl").data.set_index("fielder")
    m = d.loc["MS Dhoni"]
    assert (m.catches, m.stumpings, m.matches) == (158, 47, 265) and m.catches_keeper == 158
    ks = api.run("fielding", competition="ipl", role="outfield", top=1).data.iloc[0]
    assert ks.fielder == "AB de Villiers"  # most total dismissals by a non-keeper in the list
    o = api.run("fielding", competition="ipl", role="outfield").data
    assert d.catches.idxmax() == "MS Dhoni" and o.loc[o.catches.idxmax(), "fielder"] == "V Kohli"
    assert o.catches.max() == 126
    # every caught dismissal is a catch or a caught-and-bowled
    caught = api.run("dismissal_profile", competition="ipl").data
    caught = caught[caught.kind.str.startswith("caught")].outs.sum()
    assert caught == d.catches.sum() + d.caught_and_bowled.sum() == 9720
    for aspect in ("9:16", "1:1"):
        for p in ("MS Dhoni", None):
            r = api.run("fielding", competition="ipl", **({"player": p} if p else {"top": 8}))
            video.video_figure("fielding", r, aspect)
