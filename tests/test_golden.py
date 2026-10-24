"""Golden numbers against the real DB (skipped when data/cricket_analytics.duckdb is missing).

Kohli 973 runs / 4 hundreds in IPL 2016 is the well-known record season. Super-over innings are excluded
by default (official records do): Kohli's IPL career is 9,336 (9,346 with the 10 super-over runs) and
8,661 before the 2026 season, which matches the ESPNcricinfo figure.
"""

import os
from pathlib import Path

import pytest

from cricket_analytics import api, registry
from cricket_analytics.db import query, use_db
from cricket_analytics.sql.filters import Filters

# CRICKET_TEST_DB=path points these tests at another DB file (e.g. a freshly built one)
DB = Path(os.environ.get("CRICKET_TEST_DB") or Path(__file__).parent.parent / "data" / "cricket_analytics.duckdb")
pytestmark = pytest.mark.skipif(not DB.exists(), reason="real DB not built")


def test_kohli_ipl_career_runs():
    d = api.run("batting", player="V Kohli", competition="ipl", db_path=DB).data
    assert list(d.total_runs) == [9336]
    with use_db(DB):  # opt in to super overs: +10 runs in two super-over innings
        d = registry.get("batting").fn(Filters(player="V Kohli", competition="ipl", include_super_overs=True))
    assert list(d.total_runs) == [9346]


def test_kohli_ipl_runs_before_2026():
    d = api.run("batting", player="V Kohli", competition="ipl", group_by="season", db_path=DB).data
    assert d.total_runs.sum() == 9336
    assert d[d.season != "2026"].total_runs.sum() == 8661


def test_kohli_2016_by_year_and_label():
    for season in (2016, "2016"):
        d = api.run("batting", player="V Kohli", competition="ipl", season=season, db_path=DB).data
        assert (d.total_runs[0], d.hundreds[0]) == (973, 4)


def test_ipl_2025_has_74_matches():
    where, p = Filters(competition="ipl", season=2025).where("match")
    assert query(f"SELECT count(*) AS n FROM matches m WHERE {where}", p, db_path=DB).n[0] == 74


def test_year_maps_to_cricsheet_label():
    # IPL 2008 is labelled '2007/08' in Cricsheet, IPL 2020 '2020/21'
    for year, label in ((2008, "2007/08"), (2020, "2020/21")):
        where, p = Filters(competition="ipl", season=year).where("match")
        seasons = query(f"SELECT DISTINCT season FROM matches m WHERE {where}", p, db_path=DB).season.tolist()
        assert seasons == [label]


def test_women_and_men_are_separate():
    counts = {}
    for key in ("t20i", "t20i_women"):
        where, p = Filters(competition=key).where("match")
        counts[key] = query(f"SELECT count(*) AS n FROM matches m WHERE {where}", p, db_path=DB).n[0]
    assert counts == {"t20i": 3627, "t20i_women": 2183}  # measured on the 2026-10-14 build; grows with updates


def test_hundred_phases_use_five_ball_sets():
    ph = api.run("batting", competition="hundred", group_by="phase", db_path=DB).data
    balls = ph.groupby("phase").balls.sum()
    # powerplay = first 25 of 100 balls (~26% incl. no-balls); death = last 25, a bit less (~22%) because
    # chases end early. With the old 0-5 / 15-19 over bounds powerplay would be ~30%.
    share = balls / balls.sum()
    assert 0.24 < share["powerplay"] < 0.29
    assert 0.18 < share["death"] < 0.26


def test_super_over_ties_store_their_winner():
    # 74 super-over ties (and 2 bowl-outs) keep result='tie' and carry the tie-break winner; 729315 KKR v RR 2014 -> RR
    n = query("SELECT count(*) AS n, count(winner) AS w FROM matches WHERE result = 'tie' "
              "AND outcome_method IN ('super over', 'bowl out')", db_path=DB)
    assert (n.n[0], n.w[0]) == (76, 76)
    assert query("SELECT winner FROM matches WHERE match_id = '729315'", db_path=DB).winner[0] == "Rajasthan Royals"
