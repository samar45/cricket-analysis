"""Player attributes: the two reference CSVs, the SQL view, the builder and the player_profile module."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from cricket_analytics import api
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.reference import ATTRIBUTES_CSV, OVERRIDES_CSV, build_attributes as ba
from cricket_analytics.sql import attributes as at

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
    return duckdb.connect().execute(f"WITH {at.attributes_cte()} SELECT * FROM pa").fetchdf().set_index("name")


def test_csvs_load_and_names_are_unique(gen, ovr):
    assert len(gen) > 5000 and len(ovr) > 200
    assert gen.name.is_unique and ovr.name.is_unique


def test_vocabulary_generated(gen):
    assert set(gen.role) <= set(at.ROLES)
    assert set(gen.keeper) <= {"", *at.KEEPERS}
    assert set(gen.bat_slot) <= set(at.BAT_SLOTS)
    assert set(gen.bowl_phase_role) <= {"", *at.BOWL_PHASE_ROLES}
    assert set(gen.bowl_kind) <= {"", *at.BOWL_KINDS}
    for c in ("role_confidence", "bowl_kind_confidence", "bat_slot_confidence", "keeper_confidence"):
        assert set(gen[c]) <= {"", *at.CONFIDENCES}, c
    assert set(gen.role_source) == {"derived"}
    assert "bowl_type" not in gen and "bat_hand" not in gen   # hand-kept facts never live in the generated file
    assert (gen.bowl_kind != "").eq(gen.bowl_kind_source != "").all()


def test_vocabulary_overrides(ovr):
    assert set(ovr.bowl_type) <= {"", *at.BOWL_TYPES}
    assert set(ovr.bat_hand) <= {"", *at.BAT_HANDS}
    assert set(ovr.role) <= {"", *at.ROLES[:3]} and set(ovr.keeper) <= {"", *at.KEEPERS}
    assert (ovr.source != "").all()
    assert (ovr.bowl_type != "").eq(ovr.bowl_type_confidence != "").all()   # a type always carries its confidence
    assert (ovr.bat_hand != "").eq(ovr.bat_hand_confidence != "").all()
    assert set(ovr.bowl_type_confidence) <= {"", *at.CONFIDENCES} and set(ovr.bat_hand_confidence) <= {"", *at.CONFIDENCES}
    assert (ovr.bowl_type != "").sum() >= 250


def test_overrides_win(tmp_path, monkeypatch, gen):
    rows = [{"name": "X One", "gender": "male", "matches": "50", "role": "bowler", "role_source": "derived", "bowl_kind": "pace",
             "bowl_kind_source": "derived", "bowl_kind_confidence": "low", "bat_slot": "tail"},
            {"name": "X Two", "gender": "male", "matches": "50", "role": "batter", "role_source": "derived", "keeper": "yes",
             "keeper_source": "derived", "bat_slot": "opener"}]
    pd.DataFrame(rows, columns=gen.columns).fillna("").to_csv(tmp_path / "a.csv", index=False)
    (tmp_path / "o.csv").write_text(
        "name,bowl_type,bowl_type_confidence,bat_hand,bat_hand_confidence,role,keeper,source,note\n"
        "X One,right-arm off spin,medium,left,high,all-rounder,,manual,\n"
        "X Three,,,right,low,,,manual,only in overrides\n")
    monkeypatch.setattr(at, "ATTRIBUTES_CSV", tmp_path / "a.csv")
    monkeypatch.setattr(at, "OVERRIDES_CSV", tmp_path / "o.csv")
    r = duckdb.connect().execute(f"WITH {at.attributes_cte()} SELECT * FROM pa").fetchdf().set_index("name")
    one = r.loc["X One"]
    assert (one.bowl_kind, one.bowl_kind_source, one.bowl_kind_confidence) == ("spin", "manual", "medium")   # beats derived 'pace'
    assert (one.role, one.role_source) == ("all-rounder", "manual") and one.bat_hand == "left" and one.bat_slot == "tail"
    two = r.loc["X Two"]
    assert (two.role, two.role_source, two.keeper) == ("batter", "derived", "yes") and two.bowl_type is None
    assert r.loc["X Three"].bat_hand == "right" and len(r) == 3


def test_bowl_kind_matches_type_in_merged_view(pa):
    typed = pa[pa.bowl_type.notna()]
    assert (typed.bowl_kind == typed.bowl_type.map(at.bowl_kind_of)).all()
    assert (typed.bowl_kind_source == "manual-llm").all()


# Certain facts (Cricket knowledge, not circular: the derived columns come from ball-by-ball data)
@pytest.mark.parametrize("name,col,expected", [
    ("MS Dhoni", "keeper", "yes"), ("JC Buttler", "keeper", "yes"), ("RR Pant", "keeper", "yes"), ("Q de Kock", "keeper", "yes"),
    ("V Kohli", "keeper", None), ("JJ Bumrah", "bowl_kind", "pace"), ("JJ Bumrah", "bowl_type", "right-arm fast"),
    ("YS Chahal", "bowl_kind", "spin"), ("R Ashwin", "bowl_type", "right-arm off spin"), ("Kuldeep Yadav", "bowl_type", "left-arm wrist spin"),
    ("RA Jadeja", "bowl_type", "left-arm orthodox"), ("Rashid Khan", "bowl_kind", "spin"), ("TA Boult", "bowl_type", "left-arm fast"),
    ("V Kohli", "role", "batter"), ("JJ Bumrah", "role", "bowler"), ("HH Pandya", "role", "all-rounder"),
    ("RA Jadeja", "role", "all-rounder"), ("AD Russell", "role", "all-rounder"), ("V Kohli", "bat_slot", "top order"),
    ("JC Buttler", "bat_slot", "opener"), ("JJ Bumrah", "bat_slot", "tail"), ("YS Chahal", "bowl_phase_role", "middle"),
    ("B Kumar", "bowl_phase_role", "powerplay"),
])
def test_spot_checks(pa, name, col, expected):
    v = pa.loc[name, col]
    assert (None if pd.isna(v) else v) == expected


def test_part_time_keeper_is_not_full_keeper(pa):
    assert pa.loc["AB de Villiers", "keeper"] in ("yes", "sometimes")
    assert pa.loc["KL Rahul", "keeper"] == "sometimes"   # 9 stumpings in 223 matches
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
    assert set(out.role) <= set(at.ROLES) and set(out.bat_slot) <= set(at.BAT_SLOTS)


def test_player_profile_one_player(db):
    con = duckdb.connect(str(db), read_only=True)
    who, runs = con.execute("""SELECT d.batter, SUM(d.runs_batter) r FROM deliveries d JOIN matches m USING (match_id)
                               WHERE m.competition = 'ipl' AND d.innings <= 2 GROUP BY 1 ORDER BY r DESC LIMIT 1""").fetchone()
    r = api.run("player_profile", player=who, competition="ipl", db_path=db).data
    assert len(r) == 1 and r.player[0] == who and r.competition[0] == "ipl"
    assert r.runs[0] == runs and r.matches[0] >= 1
    assert {"role", "keeper", "bat_hand", "bowl_type", "bowl_kind", "bowl_kind_source", "wickets", "balls_bowled"} <= set(r.columns)


def test_player_profile_list_filters(db):
    every = api.run("player_profile", min_matches=0, limit=10000, db_path=db).data
    assert len(every) > 100 and every.player.is_unique
    spin = api.run("player_profile", bowl_kind="spin", min_matches=0, limit=10000, db_path=db).data
    assert len(spin) > 0 and set(spin.bowl_kind) == {"spin"}
    scoped = api.run("player_profile", competition="ipl", role="bowler", min_matches=0, limit=10000, db_path=db).data
    assert set(scoped.role) == {"bowler"} and len(scoped) < len(every)
    with pytest.raises(ValueError):
        api.run("player_profile", role="goalkeeper", db_path=db)
