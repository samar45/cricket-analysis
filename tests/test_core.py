"""Core layer tests on the two-match fixture (tests/fixtures/cricsheet/): fragments, filters, registry, api."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from cricket_analytics import api, registry
from cricket_analytics.db import init_schema, query, use_db
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.sql import fragments as fx
from cricket_analytics.sql.filters import Filters

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
IPL, HUN = "1082591", "1252666"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("core") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


def q(db, sql, params=None):
    with use_db(db):
        return query(sql, params)


def raw(sub, mid):
    return pd.read_csv(FIX / sub / f"{mid}.csv")


# ── fragments: SQL runs and agrees with plain pandas on the raw CSV ──────────

def test_fragments_match_pandas(db):
    r = q(db, f"""SELECT count(*) FILTER (WHERE {fx.BALL_FACED}) AS faced,
                         count(*) FILTER (WHERE {fx.LEGAL_BALL}) AS legal,
                         sum({fx.RUNS_CONCEDED}) AS conceded,
                         count(*) FILTER (WHERE {fx.BOWLER_WICKET}) AS wkts,
                         count(*) FILTER (WHERE {fx.IS_DOT}) AS dots,
                         count(*) FILTER (WHERE {fx.IS_FOUR}) AS fours,
                         count(*) FILTER (WHERE {fx.IS_SIX}) AS sixes
                  FROM deliveries d WHERE match_id = ?""", [IPL]).iloc[0]
    df = raw("ipl", IPL).fillna({"wides": 0, "noballs": 0, "byes": 0, "legbyes": 0})
    assert r.faced == (df.wides == 0).sum()
    assert r.legal == ((df.wides == 0) & (df.noballs == 0)).sum()
    assert r.conceded == (df.runs_off_bat + df.wides + df.noballs).sum()
    assert r.wkts == (df.wicket_type.notna() & ~df.wicket_type.isin(["run out", "retired hurt", "retired out"])).sum()
    assert r.dots == ((df.runs_off_bat + df.extras == 0) & (df.wides == 0) & (df.noballs == 0)).sum()
    assert (r.fours, r.sixes) == ((df.runs_off_bat == 4).sum(), (df.runs_off_bat == 6).sum())
    assert df.wides.sum() > 0 and df.noballs.sum() > 0  # the fixture really exercises extras


def test_batter_out_counts_striker_dismissals(db):
    df = raw("ipl", IPL)
    n = q(db, f"SELECT count(*) AS n FROM deliveries d WHERE match_id = ? AND {fx.BATTER_OUT}", [IPL]).n[0]
    assert n == (df.player_dismissed == df.striker).sum() - (df.wicket_type == "retired hurt").sum()


def test_phase_sql_six_and_five_ball(db):
    ph = q(db, f"""SELECT m.competition AS comp, {fx.phase_sql()} AS phase, min(d.over_num) AS lo, max(d.over_num) AS hi,
                          count(*) FILTER (WHERE {fx.LEGAL_BALL}) AS legal
                   FROM deliveries d JOIN matches m USING (match_id) GROUP BY ALL""")
    got = {(r.comp, r.phase): (r.lo, r.hi) for r in ph.itertuples()}
    assert got[("ipl", "powerplay")] == (0, 5)
    assert got[("ipl", "middle")] == (6, 14)
    assert got[("ipl", "death")] == (15, 19)
    assert got[("hundred", "powerplay")] == (0, 4)
    assert got[("hundred", "middle")] == (5, 14)
    assert got[("hundred", "death")] == (15, 19)
    # Hundred: first 25 legal balls of an innings are powerplay
    pp = ph[(ph.comp == "hundred") & (ph.phase == "powerplay")].legal.iloc[0]
    assert pp == 50  # 25 balls x 2 innings


# ── filters ───────────────────────────────────────────────────────────────────

ALL_FILTERS = dict(competition="ipl", season=2017, team="T'eam; DROP TABLE x", opposition="Opp",
                   venue="Ven--ue", phase="death", player="P'l")


@pytest.mark.parametrize("side", ["bat", "bowl", "match"])
def test_filters_bind_every_value(side):
    sql, params = Filters(**ALL_FILTERS).where(side)
    assert sql.startswith("1=1")
    assert sql.count("?") == len(params)
    for v in ("DROP", "Ven--ue", "P'l", "Opp"):
        assert v not in sql
    assert " ILIKE " not in sql and " LIKE " not in sql


def test_filters_empty_is_men_only():
    sql, params = Filters().where("bat")
    assert sql == "1=1 AND m.gender = ? AND d.innings <= 2" and params == ["male"]  # super overs off by default
    assert Filters(include_super_overs=True).where("bat")[0] == "1=1 AND m.gender = ?"


def test_filters_sides():
    f = Filters(team="A", opposition="B", player="X")
    assert "d.batting_team = ?" in f.where("bat")[0] and "d.bowling_team = ?" in f.where("bat")[0]
    assert "d.batter = ?" in f.where("bat")[0] and "d.bowler" not in f.where("bat")[0]
    assert f.where("bowl")[1] == ["male", "A", "B", "X"]  # team -> bowling_team, opposition -> batting_team
    assert f.where("bowl")[0].index("d.bowling_team") < f.where("bowl")[0].index("d.batting_team")
    assert "team1" in f.where("match")[0] and "d.batter" not in f.where("match")[0]


def test_filters_rejects_bad_values():
    with pytest.raises(ValueError):
        Filters(competition="nope").where("bat")
    with pytest.raises(ValueError):
        Filters(phase="slog").where("bat")


def test_women_only_via_t20i_women():
    assert Filters(competition="t20i_women").where("match")[1] == ["t20i", "female"]
    assert Filters(competition="t20i").where("match")[1] == ["t20i", "male"]


def test_season_label_vs_year(tmp_path):
    path = tmp_path / "s.duckdb"
    init_schema(path)
    con = duckdb.connect(str(path))
    rows = [("a", "ipl", "2007/08", "2008-04-18"), ("b", "ipl", "2009", "2009-04-18"),
            ("c", "ipl", "2009/10", "2010-03-12"), ("d", "ipl", "2020/21", "2020-09-19"),
            ("e", "ipl", "2020/21", "2020-11-10"), ("f", "ipl", "2021", "2021-04-09"),
            ("g", "bbl", "2020/21", "2020-12-10")]
    for mid, comp, season, date in rows:
        con.execute("INSERT INTO matches (match_id, competition, gender, season, date) VALUES (?, ?, 'male', ?, ?)",
                    [mid, comp, season, date])
    con.close()

    def ids(**kw):
        sql, p = Filters(**kw).where("match")
        return sorted(q(path, f"SELECT match_id FROM matches m WHERE {sql}", p).match_id)

    assert ids(competition="ipl", season=2008) == ["a"]          # year -> '2007/08'
    assert ids(competition="ipl", season="2010") == ["c"]        # '2009/10' starts in 2010
    assert ids(competition="ipl", season=2009) == ["b"]
    assert ids(competition="ipl", season=2020) == ["d", "e"]     # '2020/21'
    assert ids(competition="ipl", season="2020/21") == ["d", "e"]  # exact label
    assert ids(season=2020) == ["d", "e", "g"]                   # all competitions


# ── db ─────────────────────────────────────────────────────────────────────────

def test_query_raises_and_reuses_connection(db):
    with use_db(db):
        with pytest.raises(duckdb.Error):
            query("SELECT nope FROM deliveries")
        from cricket_analytics import db as dbmod
        c1 = dbmod._reader(None)
        query("SELECT 1")
        assert dbmod._reader(None) is c1
    with pytest.raises(FileNotFoundError):
        query("SELECT 1", db_path=db.parent / "missing.duckdb")


# ── registry + api ────────────────────────────────────────────────────────────

def test_registry_discovers_batting():
    ids = [m.id for m in registry.all_modules()]
    assert "batting" in ids
    assert [m["id"] for m in api.list_modules()] == ids


def test_json_schema_shape():
    s = registry.json_schema("batting")
    assert s["type"] == "object" and s["additionalProperties"] is False
    props = s["properties"]
    assert "t20i_women" in props["competition"]["enum"] and "ipl" in props["competition"]["enum"]
    assert props["phase"]["enum"] == ["powerplay", "middle", "death"]
    assert props["group_by"]["enum"] == ["player", "season", "phase"]
    assert props["min_balls"]["type"] == "integer"
    assert props["season"]["type"] == ["string", "integer"]
    assert s["required"] == []
    tools = api.schema()
    assert tools[0]["name"] == "batting" and tools[0]["parameters"] == s


def test_paramspec_validates():
    with pytest.raises(ValueError):
        registry.ParamSpec("x", "weird")
    with pytest.raises(ValueError):
        registry.ParamSpec("x", "choice")


def test_run_batting_matches_pandas(db):
    r = api.run("batting", competition="ipl", db_path=db)
    df = raw("ipl", IPL)
    assert r.data.total_runs.sum() == df.runs_off_bat.sum()
    assert r.data.balls.sum() == (df.wides.fillna(0) == 0).sum()
    w = r.data[r.data.batter == "DA Warner"].iloc[0]
    wd = df[df.striker == "DA Warner"]
    assert w.total_runs == wd.runs_off_bat.sum()
    assert w.balls == (wd.wides.fillna(0) == 0).sum()
    assert w.innings == 1
    assert r.meta["module"] == "batting" and r.meta["source"].startswith("Cricsheet")
    assert r.meta["row_count"] == len(r.data) and r.meta["data_through"] == str(df.start_date.iloc[0])
    assert r.meta["params"] == {"competition": "ipl", "group_by": "player", "min_balls": 0}
    assert r.to_records()[0]["batter"] == r.data.batter.iloc[0]
    assert '"meta"' in r.to_json() and '"data"' in r.to_json()


def test_run_group_by_phase_and_season_sum_to_total(db):
    total = api.run("batting", competition="hundred", db_path=db).data.total_runs.sum()
    for g in ("phase", "season"):
        r = api.run("batting", competition="hundred", group_by=g, db_path=db)
        assert r.data.total_runs.sum() == total
    ph = api.run("batting", competition="hundred", group_by="phase", db_path=db).data
    assert set(ph.phase) == {"powerplay", "middle", "death"}
    pp = api.run("batting", competition="hundred", phase="powerplay", db_path=db).data
    assert pp.total_runs.sum() == ph[ph.phase == "powerplay"].total_runs.sum()


def test_run_min_balls_and_filters(db):
    all_ = api.run("batting", competition="ipl", db_path=db).data
    big = api.run("batting", competition="ipl", min_balls=20, db_path=db).data
    assert 0 < len(big) < len(all_) and (big.balls >= 20).all()
    assert api.run("batting", competition="ipl", team="Nobody FC", db_path=db).data.empty
    one = api.run("batting", competition="ipl", player="DA Warner", db_path=db).data
    assert list(one.batter) == ["DA Warner"]


def test_run_bad_input(db):
    with pytest.raises(ValueError, match="no param"):
        api.run("batting", plaer="x", db_path=db)
    with pytest.raises(ValueError, match="group_by"):
        api.run("batting", group_by="weekday", db_path=db)
    with pytest.raises(ValueError, match="Unknown competition"):
        api.run("batting", competition="xyz", db_path=db)
    with pytest.raises(ValueError, match="phase"):
        api.run("batting", phase="slog", db_path=db)
    with pytest.raises(ValueError, match="integer"):
        api.run("batting", min_balls="many", db_path=db)
    with pytest.raises(ValueError, match="Unknown module"):
        api.run("nothing", db_path=db)


def test_resolve_and_info(db):
    with use_db(db):
        top = api.resolve_player("warner", competition="ipl")[0]
        assert top["name"] == "DA Warner" and top["matches"] == 1
        assert api.resolve_player("DA Warner")[0]["score"] == 1.0
        assert api.resolve_player("da warner")[0]["score"] == 0.99
        assert api.resolve_team("sunrisers")[0]["name"] == "Sunrisers Hyderabad"
        info = api.data_info()
    assert {c["competition"] for c in info["competitions"]} == {"ipl", "hundred"}
