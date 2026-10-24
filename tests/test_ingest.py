"""Loader tests on 2 real Cricsheet matches (tests/fixtures/cricsheet/).

Expected numbers were computed once from the fixture CSVs with pandas
(runs = sum(runs_off_bat + extras) per innings, wickets = rows with wicket_type);
test_fixture_numbers re-checks them so the fixture can't drift silently.
"""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from ingestion.cricsheet import load_to_db

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
IPL, HUN = "1082591", "1252666"

# match_id -> (deliveries, {innings: runs}, dismissal rows, batting team of innings 1)
EXPECTED = {
    IPL: (248, {1: 207, 2: 172}, 14, "Sunrisers Hyderabad"),
    HUN: (207, {1: 145, 2: 136}, 15, "Oval Invincibles"),
}


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    db = tmp_path_factory.mktemp("ingest") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=db)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=db)
    c = duckdb.connect(str(db), read_only=True)
    yield c
    c.close()


def q(con, sql, *params):
    return con.execute(sql, list(params)).fetchall()


def test_fixture_numbers():
    for sub, mid in (("ipl", IPL), ("hundred", HUN)):
        df = pd.read_csv(FIX / sub / f"{mid}.csv")
        n, runs, wkts, team = EXPECTED[mid]
        assert len(df) == n
        assert (df.runs_off_bat + df.extras).groupby(df.innings).sum().to_dict() == runs
        assert df.wicket_type.notna().sum() == wkts
        assert df[df.innings == 1].batting_team.iloc[0] == team


def test_two_matches_and_all_matches_skipped(con):
    ids = {r[0] for r in q(con, "SELECT match_id FROM matches")}
    assert ids == {IPL, HUN}
    assert q(con, "SELECT count(*) FROM deliveries WHERE match_id = '999999'")[0][0] == 0


@pytest.mark.parametrize("mid", [IPL, HUN])
def test_counts_and_runs(con, mid):
    n, runs, wkts, team = EXPECTED[mid]
    assert q(con, "SELECT count(*) FROM deliveries WHERE match_id=?", mid)[0][0] == n
    got = dict(q(con, "SELECT innings, sum(runs_total) FROM deliveries WHERE match_id=? GROUP BY 1", mid))
    assert {k: int(v) for k, v in got.items()} == runs
    assert q(con, "SELECT count(*) FROM deliveries WHERE match_id=? AND wicket_type IS NOT NULL", mid)[0][0] == wkts
    assert q(con, "SELECT min(batting_team) FROM deliveries WHERE match_id=? AND innings=1", mid)[0][0] == team


def test_team_never_null(con):
    assert q(con, "SELECT count(*) FROM deliveries WHERE batting_team IS NULL OR bowling_team IS NULL")[0][0] == 0


def test_extras_columns(con):
    # IPL fixture has 8 wide balls and 2 no-ball balls
    assert q(con, "SELECT count(*) FROM deliveries WHERE match_id=? AND wides > 0", IPL)[0][0] == 8
    assert q(con, "SELECT count(*) FROM deliveries WHERE match_id=? AND noballs > 0", IPL)[0][0] == 2


def test_fielder_on_caught_ball(con):
    # IPL innings 1, ball 1.5: DA Warner caught by Mandeep Singh
    row = q(con, "SELECT wicket_type, player_out, fielder FROM deliveries "
                 "WHERE match_id=? AND innings=1 AND over_num=1 AND ball_num=5", IPL)
    assert row == [("caught", "DA Warner", "Mandeep Singh")]


def test_match_labels(con):
    rows = {r[0]: r[1:] for r in q(
        con, "SELECT match_id, competition, gender, team_type, match_type, balls_per_over FROM matches")}
    assert rows[IPL] == ("ipl", "male", "club", "T20", 6)
    assert rows[HUN] == ("hundred", "male", "club", "T20", 5)
    assert "Indian Premier League" in q(con, "SELECT event FROM matches WHERE match_id=?", IPL)[0][0]


def test_primary_keys_unique(con):
    assert q(con, "SELECT count(*) - count(DISTINCT match_id) FROM matches")[0][0] == 0
    assert q(con, "SELECT count(*) - count(DISTINCT (match_id, innings, ball_seq)) FROM deliveries")[0][0] == 0
    assert q(con, "SELECT count(*) FROM deliveries WHERE ball_seq IS NULL")[0][0] == 0


def test_players_table(con):
    n, = q(con, "SELECT count(*) FROM players")[0]
    assert n > 0
    assert q(con, "SELECT count(*) FROM players WHERE name = 'DA Warner'")[0][0] == 1
