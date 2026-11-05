"""Run expectancy tables (models/run_expectancy.py) and the `runs_added` module + charts."""

import warnings
from pathlib import Path

import numpy as np
import pytest

from cricket_analytics import api
from cricket_analytics.db import query
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.models import run_expectancy as RE
from cricket_analytics.sql.filters import Filters
from cricket_analytics.viz import runs_added as rviz
from cricket_analytics.viz import video
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")
FIX = Path(__file__).parent / "fixtures" / "cricsheet"
real = requires_real_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("ra") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


def test_pava_makes_monotone_and_keeps_weighted_mean():
    y = np.array([1.0, 3.0, 2.0, 2.0, 5.0, 4.0])
    out = RE._pava(y, np.ones(6))
    assert (np.diff(out) >= 0).all() and out.mean() == pytest.approx(y.mean())


def test_smooth_table_on_synthetic_data_is_monotone_and_close():
    rng = np.random.default_rng(1)
    b = np.arange(0, 121)
    truth = np.array([1.4 * b * (1 - 0.09 * w) for w in range(10)])
    n = np.where(rng.random(truth.shape) < 0.9, 40.0 / (1 + np.arange(10))[:, None], 0.0)
    n[:, 0] = 0
    s = n * (truth + rng.normal(0, 3, truth.shape))
    est = RE.smooth_table(n, s)
    assert (np.diff(est, axis=1) >= -1e-9).all() and (np.diff(est, axis=0) <= 1e-9).all()
    assert est[:, 0].max() == 0 and abs(est[0, 120] - truth[0, 120]) < 6


@pytest.mark.parametrize("key", sorted(RE.load().tables))
def test_shipped_tables_are_monotone(key):
    r = RE.load().tables[key]
    assert r.shape[0] == 11 and (r[10] == 0).all() and (r[:, 0] == 0).all()
    assert (np.diff(r, axis=1) >= -1e-9).all()  # more balls left -> more runs
    assert (np.diff(r, axis=0) <= 1e-9).all()  # more wickets lost -> fewer runs


def test_start_state_equals_average_first_innings_total():
    m = RE.load()
    for row in m.adj.itertuples():
        start = m.re_at(row.grp, row.era_from, 0, m.tables[(row.grp, row.era_from)].shape[1] - 1)
        assert start == pytest.approx(row.avg_first_total, abs=3), (row.grp, row.era_from)


def test_ipl_eras_and_hundred_length():
    m = RE.load()
    assert RE.era_of("ipl_male", 2022) == 0 and RE.era_of("ipl_male", 2023) == 2023
    assert (
        m.tables[("hundred_male", 0)].shape[1] == 101 and m.tables[("ipl_male", 0)].shape[1] == 121
    )
    assert m.re_at("ipl_male", 2023, 0, 120) > m.re_at("ipl_male", 0, 0, 120) + 15  # scoring jumped


def test_fixture_module_and_charts(db):
    for role in ("batting", "bowling"):
        r = api.run("runs_added", db_path=db, competition="ipl", role=role, min_balls=1)
        assert not r.data.empty and r.data.runs_added.notna().all()
        rviz.figure(r)
        for a in ("9:16", "1:1"):
            video.video_figure("runs_added", r, a)
            video.video_figure("runs_added", r, a, focus="rate")
    e = api.run("runs_added", db_path=db, competition="hundred", min_balls=1)
    assert not e.data.empty


@real
def test_real_batting_credit_sums_to_about_zero_per_first_innings():
    f = Filters(competition="ipl")
    rows = RE._query_balls(f, None, "d.innings = 1", [])
    a = RE.load().annotate(rows)
    sel = a[(a.faced == 1) | (a.striker_out == 1)]
    ns = a[(a.wk == 1) & (a.striker_out == 0)]
    total = RE.batting_credit(sel).sum() + (ns.vf * ns.wkt_part).sum()
    n_inn = a.match_id.nunique()
    assert (
        abs(total / n_inn) < 0.5
    )  # runs per innings, by construction ~0 (offsets fitted on the same data)
    bowl = RE.bowling_credit(a).sum() / n_inn
    assert abs(bowl) < 0.5


@real
def test_real_module_sanity():
    d = api.run("runs_added", competition="ipl", season=2025, top=10).data
    assert (d.runs_added.diff().dropna() <= 0).all() and d.runs_added.iloc[0] > 50
    assert (d.balls >= 100).all()
    k = api.run("runs_added", competition="ipl", player="V Kohli").data.iloc[0]
    assert (
        k.balls > 4000
        and k.runs_added > 0
        and k.runs_added_per_100_balls == pytest.approx(k.runs_added * 100 / k.balls, abs=0.02)
    )
    b = api.run("runs_added", competition="ipl", role="bowling", player="JJ Bumrah").data.iloc[0]
    assert b.runs_added > 0 and b.wickets > 100


@real
def test_real_non_striker_run_out_is_charged_to_the_dismissed_player():
    sql = """SELECT d.match_id, d.innings, d.player_out p, m.season FROM deliveries d JOIN matches m USING (match_id)
             WHERE m.competition = 'ipl' AND d.wicket_type = 'run out' AND d.player_out <> d.batter AND d.innings = 1 LIMIT 1"""
    r = query(sql).iloc[0]
    one = api.run("runs_added", competition="ipl", player=r.p, season=r.season, min_balls=0).data
    assert not one.empty
