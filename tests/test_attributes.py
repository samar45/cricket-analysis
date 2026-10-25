"""Player attributes: the two reference CSVs, the SQL view, the builder and the player_profile module."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from cricket_analytics import api
from cricket_analytics.analysis import player_profile as pl
from cricket_analytics.db import query
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.reference import ATTRIBUTES_CSV, OVERRIDES_CSV, build_attributes as ba
from cricket_analytics.sql import attributes as at
from tests.conftest import requires_real_db
from tests.conftest import REAL_DB as REAL

FIX = Path(__file__).parent / "fixtures" / "cricsheet"


def read(p):
    return pd.read_csv(p, dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def gen():
    return read(ATTRIBUTES_CSV)


@pytest.fixture(scope="module")
def ovr():
    return read(OVERRIDES_CSV)


@pytest.fixture(scope="module")
def pa():
    """The merged view as a DataFrame, indexed by name (real CSVs, no DB needed)."""
    return (
        duckdb.connect()
        .execute(f"WITH {at.attributes_cte()} SELECT * FROM pa")
        .fetchdf()
        .set_index("name")
    )


def test_csvs_load_and_names_are_unique(gen, ovr):
    assert len(gen) > 5000 and len(ovr) > 200
    assert gen.name.is_unique and ovr.name.is_unique


def test_vocabulary_generated(gen):
    assert set(gen.role) <= set(at.ROLES)
    assert set(gen.role_source) == {"derived"}
    # everything derived except the broad role is a HINT: renamed so nothing can show it as a fact
    assert set(gen.hint_keeper) <= {"", *at.KEEPERS}
    assert set(gen.hint_bat_slot) <= set(at.BAT_SLOTS)
    assert set(gen.hint_bowl_phase_role) <= {"", *at.BOWL_PHASE_ROLES}
    assert set(gen.hint_bowl_kind) <= {"", *at.BOWL_KINDS}
    for c in (
        "role_confidence",
        "hint_bowl_kind_confidence",
        "hint_bat_slot_confidence",
        "hint_keeper_confidence",
    ):
        assert set(gen[c]) <= {"", *at.CONFIDENCES}, c
    for c in (
        "keeper",
        "bowl_kind",
        "bat_slot",
        "bowl_phase_role",
        "bat_position",
        "bowl_type",
        "bat_hand",
    ):
        assert c not in gen, c  # no un-prefixed guess, no hand-kept fact in the generated file
    assert (gen.hint_bowl_kind != "").eq(gen.hint_bowl_kind_confidence != "").all()


def test_vocabulary_overrides(ovr):
    assert set(ovr.bowl_type) <= {"", *at.BOWL_TYPES}
    assert set(ovr.bat_hand) <= {"", *at.BAT_HANDS}
    assert set(ovr.role) <= {"", *at.ROLES[:3]} and set(ovr.keeper) <= {"", *at.KEEPERS}
    assert (ovr.source != "").all()
    assert (
        (ovr.bowl_type != "").eq(ovr.bowl_type_confidence != "").all()
    )  # a type always carries its confidence
    assert (ovr.bat_hand != "").eq(ovr.bat_hand_confidence != "").all()
    assert set(ovr.bowl_type_confidence) <= {"", *at.CONFIDENCES} and set(
        ovr.bat_hand_confidence
    ) <= {"", *at.CONFIDENCES}
    assert (ovr.bowl_type != "").sum() >= 250


def test_overrides_win(tmp_path, monkeypatch, gen):
    rows = [
        {
            "name": "X One",
            "gender": "male",
            "matches": "50",
            "role": "bowler",
            "role_source": "derived",
            "hint_bowl_kind": "pace",
            "hint_bowl_kind_confidence": "low",
            "hint_bat_slot": "tail",
        },
        {
            "name": "X Two",
            "gender": "male",
            "matches": "50",
            "role": "batter",
            "role_source": "derived",
            "hint_keeper": "yes",
            "hint_bat_slot": "opener",
        },
    ]
    pd.DataFrame(rows, columns=gen.columns).fillna("").to_csv(tmp_path / "a.csv", index=False)
    (tmp_path / "o.csv").write_text(
        "name,bowl_type,bowl_type_confidence,bat_hand,bat_hand_confidence,role,keeper,source,note\n"
        "X One,right-arm off spin,medium,left,high,all-rounder,,manual,\n"
        "X Three,,,right,low,,,manual,only in overrides\n"
    )
    monkeypatch.setattr(at, "ATTRIBUTES_CSV", tmp_path / "a.csv")
    monkeypatch.setattr(at, "OVERRIDES_CSV", tmp_path / "o.csv")
    r = (
        duckdb.connect()
        .execute(f"WITH {at.attributes_cte()} SELECT * FROM pa")
        .fetchdf()
        .set_index("name")
    )
    one = r.loc["X One"]
    assert (one.bowl_kind, one.bowl_kind_source, one.bowl_kind_confidence) == (
        "spin",
        "manual",
        "medium",
    )  # from the type, not the hint
    assert (
        (one.role, one.role_source) == ("all-rounder", "manual")
        and one.bat_hand == "left"
        and one.hint_bat_slot == "tail"
    )
    two = r.loc["X Two"]
    assert (two.role, two.role_source) == ("batter", "derived") and two.bowl_type is None
    assert (
        pd.isna(two.keeper) and two.hint_keeper == "yes"
    )  # a derived keeper guess is a hint, never the keeper fact
    assert pd.isna(r.loc["X Three"].bowl_kind)  # no override type -> unknown, whatever a hint says
    assert r.loc["X Three"].bat_hand == "right" and len(r) == 3


def test_bowl_kind_matches_type_in_merged_view(pa):
    typed = pa[pa.bowl_type.notna()]
    assert (typed.bowl_kind == typed.bowl_type.map(at.bowl_kind_of)).all()
    assert typed.bowl_kind_source.notna().all()
    # pace/spin and keeper are facts only where the reviewed list has them; the derived guesses never leak in
    assert pa.bowl_kind[pa.bowl_type.isna()].isna().all()
    ovr_names = set(read(OVERRIDES_CSV).query("keeper != ''").name)
    assert set(pa.index[pa.keeper.notna()]) <= ovr_names
    assert (
        pa.hint_bowl_kind.notna().sum() > 3000 and pa.hint_keeper.notna().sum() > 50
    )  # the hints are still there for gap-finding


# Certain facts (Cricket knowledge, not circular: the derived columns come from ball-by-ball data)
@pytest.mark.parametrize(
    "name,col,expected",
    [
        ("V Kohli", "keeper", None),
        ("JJ Bumrah", "bowl_kind", "pace"),
        ("JJ Bumrah", "bowl_type", "right-arm fast"),
        ("YS Chahal", "bowl_kind", "spin"),
        ("R Ashwin", "bowl_type", "right-arm off spin"),
        ("Kuldeep Yadav", "bowl_type", "left-arm wrist spin"),
        ("RA Jadeja", "bowl_type", "left-arm orthodox"),
        ("Rashid Khan", "bowl_kind", "spin"),
        ("TA Boult", "bowl_type", "left-arm fast"),
        ("V Kohli", "role", "batter"),
        ("JJ Bumrah", "role", "bowler"),
        ("HH Pandya", "role", "all-rounder"),
        ("RA Jadeja", "role", "all-rounder"),
        ("AD Russell", "role", "all-rounder"),
        ("V Kohli", "hint_bat_slot", "top order"),
        ("JC Buttler", "hint_bat_slot", "opener"),
        ("JJ Bumrah", "hint_bat_slot", "tail"),
        ("YS Chahal", "hint_bowl_phase_role", "middle"),
        ("B Kumar", "hint_bowl_phase_role", "powerplay"),
    ],
)
def test_spot_checks(pa, name, col, expected):
    v = pa.loc[name, col]
    assert (None if pd.isna(v) else v) == expected


def test_keeper_hint_is_a_hint(pa):
    """The stumping-rate guess stays in the file for gap-finding but is not the keeper fact."""
    assert pa.loc["AB de Villiers", "hint_keeper"] in ("yes", "sometimes")
    assert pa.loc["KL Rahul", "hint_keeper"] == "sometimes"  # 9 stumpings in 223 matches
    assert pd.isna(pa.loc["V Kohli", "hint_keeper"]) and pd.isna(pa.loc["RG Sharma", "hint_keeper"])
    assert pd.isna(pa.loc["V Kohli", "keeper"]) and pd.isna(pa.loc["RG Sharma", "keeper"])


# ── builder and module on the 2-match fixture DB ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("attr") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


def test_builder_runs_on_fixture(db):
    con = duckdb.connect(str(db), read_only=True)
    out = ba.classify(ba.features(con))
    assert len(out) > 0 and out.name.is_unique
    assert set(out.role) <= set(at.ROLES) and set(out.hint_bat_slot) <= set(at.BAT_SLOTS)


def test_player_profile_one_player(db):
    con = duckdb.connect(str(db), read_only=True)
    who, runs = (
        con.execute("""SELECT d.batter, SUM(d.runs_batter) r FROM deliveries d JOIN matches m USING (match_id)
                               WHERE m.competition = 'ipl' AND d.innings <= 2 GROUP BY 1 ORDER BY r DESC LIMIT 1""").fetchone()
    )
    r = api.run("player_profile", player=who, competition="ipl", db_path=db).data
    assert len(r) == 1 and r.player[0] == who and r.competition[0] == "ipl"
    assert r.runs[0] == runs and r.matches[0] >= 1
    assert {
        "role",
        "keeper",
        "bat_hand",
        "bowl_type",
        "bowl_kind",
        "bowl_kind_source",
        "wickets",
        "balls_bowled",
    } <= set(r.columns)
    assert {
        "pos_1_2",
        "pct_pos_5_6",
        "usually_bats_at",
        "faced_death",
        "bowled_middle",
        "usually_bowls_in",
    } <= set(r.columns)
    assert not [
        c
        for c in r.columns
        if c.startswith("hint_") or c in ("bat_slot", "bowl_phase_role", "bat_position")
    ]
    n = r.iloc[0]
    assert (
        n.bat_innings
        == n[[f"pos_{i}" for i in range(1, 12)]].sum()
        == n.pos_1_2 + n.pos_3_4 + n.pos_5_6 + n.pos_7_plus
    )
    assert (
        n.faced_powerplay + n.faced_middle + n.faced_death == n.balls_faced
    )  # the fixture has no wides faced
    assert n.bowled_powerplay + n.bowled_middle + n.bowled_death == n.balls_bowled


def test_player_profile_list_filters(db):
    every = api.run("player_profile", min_matches=0, limit=10000, db_path=db).data
    assert len(every) > 100 and every.player.is_unique
    spin = api.run("player_profile", bowl_kind="spin", min_matches=0, limit=10000, db_path=db).data
    assert len(spin) > 0 and set(spin.bowl_kind) == {"spin"}
    scoped = api.run(
        "player_profile", competition="ipl", role="bowler", min_matches=0, limit=10000, db_path=db
    ).data
    assert set(scoped.role) == {"bowler"} and len(scoped) < len(every)
    with pytest.raises(ValueError):
        api.run("player_profile", role="goalkeeper", db_path=db)


def test_player_profile_list_sort_by_usage(db):
    d = api.run(
        "player_profile",
        competition="ipl",
        sort_by="death_bowled",
        min_matches=0,
        limit=50,
        db_path=db,
    ).data
    assert len(d) > 0 and d.bowled_death.is_monotonic_decreasing and (d.bowled_death > 0).all()
    assert {"faced_powerplay", "bowled_middle"} <= set(d.columns)
    with pytest.raises(ValueError):
        api.run("player_profile", sort_by="most_sixes", db_path=db)


def test_usage_of_hint_text():
    c = dict(
        pos_1_2=0,
        pos_3_4=74,
        pos_5_6=126,
        pos_7_plus=42,
        bat_innings=242,
        faced_powerplay=72,
        faced_middle=1903,
        faced_death=1982,
        bowled_powerplay=0,
        bowled_middle=0,
        bowled_death=0,
    )
    u = pl.usage_of(c)
    assert (
        u["usually_bats_at"] == "usually No.5–6 (52%)"
        and u["usually_faces_in"] == "usually death overs (50%)"
    )
    assert (
        u["usually_bowls_in"] is None and u["pct_bowled_death"] is None
    )  # nothing bowled -> no hint, not 0%
    assert (u["pct_pos_3_4"], u["pct_pos_7_plus"]) == (30.6, 17.4)


def test_charts_build_for_usage(db):
    from cricket_analytics.viz import player_profile as chart
    from cricket_analytics.viz.video import video_figure

    who = api.run(
        "player_profile", competition="ipl", sort_by="death_bowled", min_matches=0, db_path=db
    ).data.player[0]
    for kw in (
        dict(player=who, competition="ipl"),
        dict(competition="ipl", sort_by="death_bowled", min_matches=0),
    ):
        assert len(chart.figure(api.run("player_profile", db_path=db, **kw)).data) > 0
    r = api.run("player_profile", player=who, competition="ipl", db_path=db)
    for aspect in ("9:16", "1:1"):
        fig = video_figure("player_profile", r, aspect)
        assert any("USUALLY" in a.text.upper() for a in fig.layout.annotations)


# ── real DB: the lead's measured numbers ────────────────────────────────────────────────────────
real = requires_real_db
POS = [f"pos_{i}" for i in range(1, 12)]


@real
def test_real_dhoni_ipl_batting_position_mix():
    r = api.run("player_profile", player="MS Dhoni", competition="ipl", db_path=REAL).data
    assert len(r) == 1
    r = r.iloc[0]
    assert (
        list(r[POS]) == [0, 0, 8, 66, 74, 52, 25, 14, 3, 0, 0] and r.bat_innings == 242
    )  # lead's count: No.3 8 ... No.9 3
    assert (r.pos_1_2, r.pos_3_4, r.pos_5_6, r.pos_7_plus) == (0, 74, 126, 42)
    assert (r.pct_pos_3_4, r.pct_pos_5_6, r.pct_pos_7_plus) == (
        30.6,
        52.1,
        17.4,
    )  # roadmap: 31% / 52% / 17%
    assert r.usually_bats_at == "usually No.5–6 (52%)"
    assert (
        r.faced_powerplay + r.faced_middle + r.faced_death == r.balls_faced == 3957
        and r.usually_faces_in == "usually death overs (50%)"
    )
    assert (
        r.bowled_powerplay == r.bowled_middle == r.bowled_death == 0 and r.usually_bowls_in is None
    )
    assert r.bat_hand == "right"


@real
def test_real_dhoni_mix_follows_the_filters():
    def mix(**kw):
        return api.run(
            "player_profile", player="MS Dhoni", competition="ipl", db_path=REAL, **kw
        ).data.iloc[0]

    career, last3, y2010 = mix(), mix(last_n_years=3), mix(season=2010)
    assert career.usually_bats_at != last3.usually_bats_at  # No.5-6 for the career, No.7+ lately
    assert last3.pct_pos_7_plus > career.pct_pos_7_plus and last3.bat_innings < career.bat_innings
    assert (y2010.bat_innings, y2010.pos_3_4, y2010.pos_5_6, y2010.pos_7_plus) == (11, 5, 6, 0)
    # splitting the career at 2020 and adding the halves gives the career back (innings and balls)
    a, b = mix(season_to=2019), mix(season_from=2020)
    for c in (*POS, "bat_innings", "faced_powerplay", "faced_middle", "faced_death"):
        assert a[c] + b[c] == career[c], c
    assert mix(team="Chennai Super Kings").bat_innings <= career.bat_innings


@real
def test_real_kuldeep_ipl_bowling_phase_mix():
    r = api.run(
        "player_profile", player="Kuldeep Yadav", competition="ipl", db_path=REAL
    ).data.iloc[0]
    # LEGAL balls (no wides / no-balls), the project's one definition of 'balls bowled'
    assert (r.bowled_powerplay, r.bowled_middle, r.bowled_death) == (
        60,
        1856,
        370,
    ) and r.balls_bowled == 2286
    assert (r.pct_bowled_powerplay, r.pct_bowled_middle, r.pct_bowled_death) == (2.6, 81.2, 16.2)
    assert r.usually_bowls_in == "usually middle overs (81%)"
    # every delivery instead (the lead's "legal + illegal" count 64 / 1,885 / 387) differs only by wides and no-balls
    raw = query(
        """SELECT count(*) FILTER (WHERE over_num < 6) pp, count(*) FILTER (WHERE over_num BETWEEN 6 AND 14) mid,
                          count(*) FILTER (WHERE over_num >= 15) dth
                   FROM deliveries d JOIN matches m USING (match_id)
                   WHERE bowler = 'Kuldeep Yadav' AND competition = 'ipl' AND gender = 'male' AND innings <= 2""",
        db_path=REAL,
    )
    assert tuple(raw.iloc[0]) == (64, 1885, 387)
    assert (r.bowl_type, r.bowl_kind) == ("left-arm wrist spin", "spin")


@real
def test_real_facts_only_from_reviewed_list():
    ovr = read(OVERRIDES_CSV)
    # a player with no entry: everything unknown, no guess from the data
    x = api.run(
        "player_profile", player="A Aikenhead", competition="t20i_women", db_path=REAL
    ).data.iloc[0]
    assert (x.keeper, x.bowl_type, x.bowl_kind, x.bat_hand) == (
        "unknown",
    ) * 4 and "A Aikenhead" not in set(ovr.name)
    d = api.run(
        "player_profile", competition="ipl", sort_by="death_bowled", limit=5, db_path=REAL
    ).data
    assert (
        d.player[0] == "B Kumar"
        and d.bowled_death[0] == 1605
        and d.bowled_death.is_monotonic_decreasing
    )
    # list filters read the reviewed list only
    spin = api.run(
        "player_profile", bowl_kind="spin", min_matches=0, limit=10000, db_path=REAL
    ).data
    assert len(spin) > 50 and set(spin.player) <= set(
        ovr.name[ovr.bowl_type.str.contains("spin|orthodox")]
    )
    left = api.run("player_profile", bat_hand="left", min_matches=0, limit=10000, db_path=REAL).data
    assert len(left) > 20 and set(left.player) <= set(ovr.name[ovr.bat_hand == "left"])
