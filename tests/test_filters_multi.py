"""Multi-value and range filters: SQL binding, season rules, schema arrays, CLI flags, and golden numbers on the real DB."""

import json

import duckdb
import pytest
from click.testing import CliRunner

from cricket_analytics import api, registry
from cricket_analytics.cli import _parse_extra, _split_commas, cli
from cricket_analytics.db import init_schema, query, use_db
from cricket_analytics.sql.filters import Filters

from tests.conftest import requires_real_db

needs_real = requires_real_db


# -- SQL binding ---------------------------------------------------------------


@pytest.mark.parametrize("side", ["bat", "bowl", "match"])
def test_lists_are_bound_not_interpolated(side):
    f = Filters(
        venue=["V1'; DROP", "V2"],
        team=["A", "B"],
        opposition=["C", "D", "E"],
        season=["2019", "2020/21"],
    )
    sql, p = f.where(side)
    assert sql.count("?") == len(p)
    assert "DROP" not in sql and "V2" not in sql
    assert "m.venue IN (?, ?)" in sql
    assert p.count("V1'; DROP") == 1 and "E" in p


def test_one_value_list_equals_scalar_and_empty_is_no_filter():
    assert Filters(venue=["X"]).where("bat") == Filters(venue="X").where("bat")
    assert Filters(venue=[], team=(), season=[], opposition=[""]).where("bat") == Filters().where(
        "bat"
    )
    assert Filters(team=["A", "B"]).where("bowl")[1] == ["male", "A", "B"]
    assert "(m.team1 IN (?, ?) OR m.team2 IN (?, ?))" in Filters(team=["A", "B"]).where("match")[0]


def test_bad_ranges_are_rejected():
    with pytest.raises(ValueError, match="season_from"):
        Filters(season_from=2024, season_to=2020).where("match")
    with pytest.raises(ValueError, match="last_n_years"):
        Filters(last_n_years=0).where("match")


# -- season rules on a tiny DB -------------------------------------------------


@pytest.fixture(scope="module")
def seasons_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("seasons") / "s.duckdb"
    init_schema(path)
    con = duckdb.connect(str(path))
    rows = [
        ("a", "ipl", "2007/08", "2008-04-18"),
        ("b", "ipl", "2009", "2009-04-18"),
        ("c", "ipl", "2009/10", "2010-03-12"),
        ("c2", "ipl", "2009/10", "2010-03-20"),
        ("d", "ipl", "2020/21", "2020-09-19"),
        ("e", "ipl", "2020/21", "2020-11-10"),
        ("f", "ipl", "2021", "2021-04-09"),
        ("g", "bbl", "2020/21", "2020-12-10"),
        ("h", "bbl", "2021/22", "2021-12-10"),
        ("i", "bbl", "2022/23", "2022-12-10"),
    ]
    for mid, comp, season, date in rows:
        con.execute(
            "INSERT INTO matches (match_id, competition, gender, season, date) VALUES (?, ?, 'male', ?, ?)",
            [mid, comp, season, date],
        )
    con.execute(
        "INSERT INTO matches (match_id, competition, gender, season, date) "
        "VALUES ('w', 'ipl', 'female', '2023', '2023-03-01')"
    )
    con.close()
    return path


def ids(path, **kw):
    sql, p = Filters(**kw).where("match")
    with use_db(path):
        return sorted(query(f"SELECT match_id FROM matches m WHERE {sql}", p).match_id)


def test_season_list_mixes_labels_and_years(seasons_db):
    assert ids(seasons_db, competition="ipl", season=[2008, "2009/10"]) == [
        "a",
        "c",
        "c2",
    ]  # 2008 -> '2007/08'
    assert ids(seasons_db, competition="ipl", season=["2009", "2021"]) == [
        "b",
        "f",
    ]  # a 4-digit value is also a label
    assert ids(seasons_db, competition="ipl", season=["2020/21", "2021"]) == ["d", "e", "f"]
    assert ids(seasons_db, competition="ipl", season=2020) == ["d", "e"]  # single value still works


def test_season_range_uses_first_match_year(seasons_db):
    assert ids(seasons_db, competition="ipl", season_from=2009, season_to=2010) == ["b", "c", "c2"]
    assert ids(seasons_db, competition="ipl", season_from=2021) == ["f"]  # '2020/21' starts in 2020
    assert ids(seasons_db, competition="ipl", season_to=2008) == ["a"]
    assert ids(seasons_db, season_from=2021, season_to=2021) == ["f", "h"]  # all competitions


def test_last_n_years_counts_seasons_per_competition(seasons_db):
    assert ids(seasons_db, competition="ipl", last_n_years=1) == ["f"]
    assert ids(seasons_db, competition="ipl", last_n_years=2) == ["d", "e", "f"]
    assert ids(seasons_db, competition="bbl", last_n_years=2) == ["h", "i"]
    assert ids(seasons_db, last_n_years=1) == ["f", "i"]  # each competition's own latest season
    assert ids(seasons_db, competition="ipl", last_n_years=99) == ids(seasons_db, competition="ipl")
    assert "w" not in ids(
        seasons_db, competition="ipl", last_n_years=3
    )  # women's rows never count in men's ranks


def test_season_conditions_combine_with_and(seasons_db):
    assert ids(seasons_db, competition="ipl", last_n_years=2, season_to=2020) == ["d", "e"]
    assert ids(seasons_db, competition="ipl", season=[2008], last_n_years=2) == []


# -- registry, api, CLI --------------------------------------------------------


def test_std_gives_multi_and_range_params_in_one_place():
    spec = {p.name: p for p in registry.get("batting").params}
    assert all(spec[n].multi for n in ("season", "venue", "team", "opposition"))
    assert not spec["player"].multi and not spec["competition"].multi
    assert all(spec[n].kind == "int" for n in ("season_from", "season_to", "last_n_years"))
    with pytest.raises(ValueError, match="multi"):
        registry.ParamSpec("x", "int", multi=True)


def test_every_module_with_season_has_the_range_params_and_array_schema():
    for m in registry.all_modules():
        names = {p.name for p in m.params}
        if "season" in names:
            assert {"season_from", "season_to", "last_n_years"} <= names, m.id
        props = registry.json_schema(m.id)["properties"]
        for p in m.params:
            if p.multi:
                assert props[p.name]["type"] == "array" and props[p.name]["items"]["type"], (
                    m.id,
                    p.name,
                )


def test_coerce_accepts_scalar_or_list():
    v = registry.ParamSpec("venue", "venue", multi=True)
    assert api._coerce(v, "A") == "A" and api._coerce(v, ["A", "B"]) == ["A", "B"]
    s = registry.ParamSpec("season", "season", multi=True)
    assert api._coerce(s, [2008, "2009/10"]) == [2008, "2009/10"]
    with pytest.raises(ValueError, match="integer"):
        api._coerce(registry.ParamSpec("n", "int"), "x")


def test_parse_extra_repeated_flags_and_comma_split():
    got = _parse_extra(
        [
            "--venue",
            "Wankhede Stadium, Mumbai",
            "--venue",
            "Eden Gardens",
            "--team",
            "A, B",
            "--player",
            "X",
        ]
    )
    assert got["venue"] == ["Wankhede Stadium, Mumbai", "Eden Gardens"]
    got = _split_commas("batting", got)
    assert got["venue"] == [
        "Wankhede Stadium, Mumbai",
        "Eden Gardens",
    ]  # venues are never split on commas
    assert got["team"] == ["A", "B"] and got["player"] == "X"
    assert _split_commas("batting", {"opposition": ["A, B", "C"], "season": "2019,2020"}) == {
        "opposition": ["A", "B", "C"],
        "season": ["2019", "2020"],
    }


@needs_real
def test_cli_repeated_flags_end_to_end():
    out = CliRunner().invoke(
        cli,
        [
            "run",
            "batting",
            "--player",
            "V Kohli",
            "--competition",
            "ipl",
            "--venue",
            "M Chinnaswamy Stadium",
            "--venue",
            "Wankhede Stadium",
            "--json",
        ],
    )
    assert out.exit_code == 0, out.output
    r = json.loads(out.output)
    assert r["meta"]["params"]["venue"] == ["M Chinnaswamy Stadium", "Wankhede Stadium"]
    assert r["data"][0]["total_runs"] > 0
    bad = CliRunner().invoke(cli, ["run", "batting", "--last_n_years", "many"])
    assert bad.exit_code != 0 and "integer" in bad.output


# -- golden numbers on the real DB ---------------------------------------------


def runs(**kw) -> int:
    return int(api.run("batting", player="V Kohli", competition="ipl", **kw).data.total_runs.sum())


@needs_real
def test_golden_kohli_last_5_seasons_equals_season_rows():
    by_season = api.run("batting", player="V Kohli", competition="ipl", group_by="season").data
    last5 = by_season[
        by_season.season.isin(["2022", "2023", "2024", "2025", "2026"])
    ]  # the 5 newest IPL seasons
    assert len(last5) == 5
    got = api.run("batting", player="V Kohli", competition="ipl", last_n_years=5).data.iloc[0]
    assert got.total_runs == last5.total_runs.sum() == 3053
    assert got.innings == last5.innings.sum() and got.balls == last5.balls.sum()
    assert got.fours == last5.fours.sum() and got.sixes == last5.sixes.sum()
    assert got.highest == last5.highest.max()
    # the same window written as a range and as a list of years
    assert (
        runs(season_from=2022, season_to=2026)
        == runs(season=[2022, 2023, 2024, 2025, 2026])
        == 3053
    )
    yearly = api.run(
        "batting", player="V Kohli", competition="ipl", last_n_years=5, group_by="year"
    ).data
    assert list(yearly.year) == [2022, 2023, 2024, 2025, 2026] and yearly.total_runs.sum() == 3053


@needs_real
def test_golden_kohli_two_venues_equal_sum_of_single_venue_runs():
    a, b = "M Chinnaswamy Stadium", "Wankhede Stadium"
    assert {a, b} <= set(api.choices("venue", "ipl"))
    both = api.run("batting", player="V Kohli", competition="ipl", venue=[a, b]).data.iloc[0]
    one, two = (
        api.run("batting", player="V Kohli", competition="ipl", venue=v).data.iloc[0]
        for v in (a, b)
    )
    assert both.total_runs == one.total_runs + two.total_runs == 4139
    assert both.innings == one.innings + two.innings and both.balls == one.balls + two.balls
    by_venue = api.run(
        "batting", player="V Kohli", competition="ipl", venue=[a, b], group_by="venue"
    ).data
    assert sorted(by_venue.venue) == [a, b] and by_venue.total_runs.sum() == 4139


@needs_real
def test_group_by_opposition_and_multi_team_sum_up():
    tot = api.run("bowling", player="JJ Bumrah", competition="ipl").data.wickets.iloc[0]
    by_opp = api.run("bowling", player="JJ Bumrah", competition="ipl", group_by="opposition").data
    assert by_opp.wickets.sum() == tot
    pair = ["Chennai Super Kings", "Kolkata Knight Riders"]
    two = api.run(
        "bowling", player="JJ Bumrah", competition="ipl", group_by="opposition", opposition=pair
    ).data
    assert sorted(two.opposition) == pair
    assert two.wickets.sum() == by_opp[by_opp.opposition.isin(pair)].wickets.sum()
    t = api.run("teams", competition="ipl", team=["Chennai Super Kings", "Mumbai Indians"]).data
    assert sorted(t.team) == ["Chennai Super Kings", "Mumbai Indians"]
