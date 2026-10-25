"""Real pressure: ball_state (sql/state.py) and the `pressure` module + charts."""

import warnings
from pathlib import Path

import pytest

from cricket_analytics import api
from cricket_analytics.db import query
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.sql.filters import Filters
from cricket_analytics.sql.state import LEVELS, ball_state, pressure_cond
from cricket_analytics.viz import video
from cricket_analytics.viz import pressure as pviz
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")
FIX = Path(__file__).parent / "fixtures" / "cricsheet"
real = requires_real_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("p") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


def state(db, comp):
    sql, p = ball_state(Filters(competition=comp))
    return query(sql, p, db_path=db)


@pytest.mark.parametrize("comp,max_balls", [("ipl", 120), ("hundred", 100)])
def test_fixture_state_reconstruction(db, comp, max_balls):
    s = state(db, comp)
    raw = query("SELECT match_id, innings, SUM(runs_total) t FROM deliveries GROUP BY 1, 2", db_path=db)
    for (mid, inn), g in s.groupby(["match_id", "innings"]):
        g = g.sort_values("ball_seq")
        assert g.score_before.iloc[0] == 0 and g.wickets_before.iloc[0] == 0 and g.legal_before.iloc[0] == 0
        assert g.balls_remaining.iloc[0] == max_balls
        assert g.score_before.iloc[-1] + g.runs_total.iloc[-1] == raw[(raw.match_id == mid) & (raw.innings == inn)].t.iloc[0]
        assert g.score_before.is_monotonic_increasing and g.legal_before.is_monotonic_increasing
    c = s[s.innings == 2]
    first = s[s.innings == 1].runs_total.sum()
    if c.trusted.iloc[0]:
        assert (c.target == first + 1).all()
        r = c.iloc[10]
        assert r.runs_needed == first + 1 - r.score_before
        assert r.required_rr == pytest.approx(round(r.runs_needed * 6 / r.balls_remaining, 2))
    assert s[s.innings == 1].required_rr.isna().all() and s[s.innings == 1].target.isna().all()


def test_levels_and_rule(db):
    assert set(LEVELS) == {"high", "extreme", "collapse"}
    with pytest.raises(ValueError):
        pressure_cond("nope")
    s = state(db, "ipl")
    c = s[s.is_chase & s.trusted & (s.balls_remaining >= 1)]
    hi = (c.required_rr >= 10) | ((c.wickets_before >= 5) & (c.balls_remaining >= 30))
    q = query(f"WITH s AS ({ball_state(Filters(competition='ipl'))[0]}) SELECT COUNT(*) FROM s WHERE {pressure_cond('high')}",
              ball_state(Filters(competition="ipl"))[1], db_path=db).iloc[0, 0]
    assert q == hi.sum()


def test_fixture_module_and_charts(db):
    r = api.run("pressure", db_path=db, competition="ipl", min_balls=1)
    r2 = api.run("pressure", db_path=db, competition="ipl", role="bowling", min_balls=1, level="extreme")
    for res in (r, r2):
        pviz.figure(res)
        for a in ("9:16", "1:1"):
            video.video_figure("pressure", res, a)
    # every chase ball is pressure or calm: pressure + calm balls = faced balls of trusted chases
    if not r.data.empty:
        assert (r.data.pressure_balls + r.data.calm_balls).sum() <= len(state(db, "ipl"))


@real
def test_real_state_exact_for_every_innings():
    import cricket_analytics.competitions as C
    bad = n = 0
    for key in C.COMPETITIONS:
        sql, p = ball_state(Filters(competition=key))
        r = query(f"""WITH s AS ({sql}),
            l AS (SELECT match_id, innings, arg_max(score_before + runs_total, ball_seq) fin FROM s GROUP BY 1, 2),
            t AS (SELECT match_id, innings, SUM(runs_total) t FROM deliveries GROUP BY 1, 2)
            SELECT COUNT(*), COUNT(*) FILTER (WHERE fin <> t) FROM l JOIN t USING (match_id, innings)""", p)
        n += r.iloc[0, 0]
        bad += r.iloc[0, 1]
    assert n > 20000 and bad == 0


@real
def test_real_dhoni_kohli_ipl():
    d = api.run("pressure", player="MS Dhoni", competition="ipl").data.iloc[0]
    assert (d.pressure_balls, d.pressure_runs, d.pressure_outs, d.calm_balls) == (1046, 1606, 37, 667)
    k = api.run("pressure", player="V Kohli", competition="ipl").data.iloc[0]
    assert (k.pressure_balls, k.pressure_runs, k.pressure_outs, k.calm_balls) == (967, 1374, 49, 2162)
    assert d.pressure_sr > d.calm_sr


@real
def test_real_excluded_matches_are_not_in_chase_state():
    sql, p = ball_state(Filters(competition="ipl"))
    r = query(f"""WITH s AS ({sql}) SELECT COUNT(*) FROM s JOIN matches m USING (match_id)
                  WHERE m.outcome_method = 'D/L' AND s.required_rr IS NOT NULL""", p)
    assert r.iloc[0, 0] == 0
