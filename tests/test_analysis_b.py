"""Phase 2B modules: bowling, teams, venues, matchup, partnerships, form (+ batting fixes).

Fixture tests use the two-match DB (IPL 1082591, Hundred 1252666) and compare with pandas on the raw CSV.
Golden tests use the real DB (skipped when missing).
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from cricket_analytics import api, registry
from cricket_analytics.db import use_db
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.sql.filters import Filters
from cricket_analytics.viz import batting as vbat, bowling as vbowl, form as vform
from cricket_analytics.viz import (
    matchup as vmatch,
    partnerships as vpart,
    teams as vteams,
    venues as vven,
)
from tests.conftest import requires_real_db
from tests.conftest import REAL_DB as REAL

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
IPL = "1082591"
VIZ = {
    "batting": vbat,
    "bowling": vbowl,
    "teams": vteams,
    "venues": vven,
    "matchup": vmatch,
    "partnerships": vpart,
    "form": vform,
}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("b") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


@pytest.fixture(scope="module")
def raw():
    d = pd.read_csv(FIX / "ipl" / f"{IPL}.csv")
    for c in ("wides", "noballs", "byes", "legbyes", "penalty"):
        d[c] = d[c].fillna(0)
    return d


def run(db, mid, **kw):
    return api.run(mid, db_path=db, **kw)


# ── columns ──────────────────────────────────────────────────────────────────

COLS = {
    "bowling": [
        "bowler",
        "innings",
        "wickets",
        "runs_conceded",
        "balls",
        "economy",
        "average",
        "strike_rate",
        "dot_pct",
        "boundary_pct",
        "dots",
        "fours_conceded",
        "sixes_conceded",
        "wides",
        "no_balls",
        "three_plus",
        "five_plus",
        "best_figures",
    ],
    "teams": [
        "team",
        "played",
        "won",
        "lost",
        "tied",
        "no_result",
        "win_pct",
        "toss_won",
        "won_after_toss_win",
        "bat_first_matches",
        "bat_first_wins",
        "chase_matches",
        "chase_wins",
    ],
    "venues": [
        "venue",
        "city",
        "matches",
        "avg_1st_innings",
        "avg_2nd_innings",
        "highest_1st_innings",
        "highest_2nd_innings",
        "highest_total",
        "lowest_total",
        "decided",
        "bat_first_wins",
        "bat_first_win_pct",
    ],
    "partnerships": [
        "batter1",
        "batter2",
        "stands",
        "runs",
        "balls",
        "strike_rate",
        "highest_stand",
        "average_stand",
        "fifty_stands",
        "hundred_stands",
    ],
}


@pytest.mark.parametrize("mid", COLS)
def test_columns(db, mid):
    d = run(db, mid, competition="ipl").data
    assert list(d.columns) == COLS[mid] and len(d) > 0


def test_matchup_and_form_columns(db):
    m = run(db, "matchup", player="DA Warner", competition="ipl", min_balls=0).data
    assert list(m.columns)[:5] == ["batter", "bowler", "balls", "runs", "dismissals"] and len(m) > 0
    f = run(db, "form", player="DA Warner", competition="ipl").data
    assert list(f.columns) == [
        "innings_no",
        "match_id",
        "date",
        "season",
        "venue",
        "runs",
        "balls",
        "dismissed",
        "fours",
        "sixes",
        "strike_rate",
        "rolling_runs",
        "rolling_sr",
    ]
    fb = run(db, "form", player="TS Mills", role="bowler", competition="ipl").data
    assert list(fb.columns)[-2:] == ["rolling_wickets", "rolling_economy"]


def test_all_modules_registered_with_schema():
    for mid in [*COLS, "matchup", "form"]:
        s = registry.json_schema(mid)
        assert s["additionalProperties"] is False
    assert registry.json_schema("form")["required"] == ["player"]


# ── core fix: non-striker run out ────────────────────────────────────────────


def test_non_striker_run_out_counts_for_that_batter(db, raw):
    # YS Chahal faced balls, then was run out at the non-striker's end (ball 19.4, innings 2):
    # the old rule (player_out = batter on balls he faced) would have called him not out.
    last = raw[raw.player_dismissed == "YS Chahal"].iloc[0]
    assert last.striker != "YS Chahal" and last.wicket_type == "run out"
    b = run(db, "batting", player="YS Chahal", competition="ipl").data.iloc[0]
    assert (b.innings, b.not_outs, b.total_runs, b.ducks) == (
        1,
        0,
        raw[raw.striker == "YS Chahal"].runs_off_bat.sum(),
        0,
    )
    # total outs = every dismissal in the CSV (no retired hurt in this match)
    allb = run(db, "batting", competition="ipl").data
    assert (allb.innings - allb.not_outs).sum() == raw.player_dismissed.notna().sum() == 14


# ── bowling ──────────────────────────────────────────────────────────────────


def test_bowling_matches_pandas(db, raw):
    d = run(db, "bowling", competition="ipl").data
    assert d.runs_conceded.sum() == (raw.runs_off_bat + raw.wides + raw.noballs).sum()
    assert d.balls.sum() == ((raw.wides == 0) & (raw.noballs == 0)).sum()
    bowler_wk = raw.wicket_type.notna() & ~raw.wicket_type.isin(
        ["run out", "retired hurt", "retired out"]
    )
    assert d.wickets.sum() == bowler_wk.sum()
    tm = d[d.bowler == "TS Mills"].iloc[0]
    rm = raw[raw.bowler == "TS Mills"]
    legal = ((rm.wides == 0) & (rm.noballs == 0)).sum()
    conc = (rm.runs_off_bat + rm.wides + rm.noballs).sum()
    assert tm.balls == legal and tm.runs_conceded == conc
    assert tm.economy == round(conc * 6 / legal, 2)
    assert tm.wides == rm.wides.sum() and tm.no_balls == rm.noballs.sum()
    # best figures string is "wickets/runs" of his best innings
    best = max(
        (
            (g.wicket_type.notna() & ~g.wicket_type.isin(["run out"])).sum(),
            -(g.runs_off_bat + g.wides + g.noballs).sum(),
        )
        for _, g in rm.groupby("innings")
    )
    assert tm.best_figures == f"{best[0]}/{int(-best[1])}"


def test_bowling_groupings_sum_to_total(db):
    tot = run(db, "bowling", competition="hundred").data
    for g in ("season", "phase"):
        x = run(db, "bowling", competition="hundred", group_by=g).data
        assert (
            x.wickets.sum() == tot.wickets.sum()
            and x.runs_conceded.sum() == tot.runs_conceded.sum()
        )
    ph = run(db, "bowling", competition="hundred", group_by="phase").data
    assert set(ph.phase) == {"powerplay", "middle", "death"}


def test_bowling_filters_and_min_balls(db):
    all_ = run(db, "bowling", competition="ipl").data
    big = run(db, "bowling", competition="ipl", min_balls=20).data
    assert 0 < len(big) < len(all_) and (big.balls >= 20).all()
    srh = run(
        db, "bowling", competition="ipl", team="Sunrisers Hyderabad"
    ).data  # team = the bowler's own side
    assert "TS Mills" not in set(srh.bowler) and "B Kumar" in set(srh.bowler)
    assert run(db, "bowling", competition="ipl", team="Nobody FC").data.empty


# ── matchup ──────────────────────────────────────────────────────────────────


def test_matchup_one_batter_sums_to_his_runs(db, raw):
    m = run(db, "matchup", player="DA Warner", competition="ipl", min_balls=0).data
    w = raw[raw.striker == "DA Warner"]
    assert m.runs.sum() == w.runs_off_bat.sum() and m.balls.sum() == (w.wides == 0).sum()
    assert (m.batter == "DA Warner").all()
    # only bowler side: every row has that bowler
    b = run(db, "matchup", player2="TS Mills", competition="ipl", min_balls=0).data
    assert (b.bowler == "TS Mills").all()
    duel = run(db, "matchup", player="DA Warner", player2="TS Mills", competition="ipl").data
    assert len(duel) <= 1


def test_matchup_dismissals_are_bowler_credited(db, raw):
    m = run(db, "matchup", competition="ipl", player2="TS Mills", min_balls=0).data
    r = raw[
        (raw.bowler == "TS Mills")
        & raw.wicket_type.notna()
        & (raw.wicket_type != "run out")
        & (raw.player_dismissed == raw.striker)
    ]
    assert m.dismissals.sum() == len(r)


def test_matchup_needs_a_player(db):
    with pytest.raises(ValueError, match="needs player"):
        run(db, "matchup", competition="ipl")


# ── partnerships ─────────────────────────────────────────────────────────────


def test_partnership_stands_add_up_to_the_innings(db, raw):
    s = run(db, "partnerships", competition="ipl", group_by="stand", top=1000).data
    for inn, g in raw.groupby("innings"):
        g = g.assign(
            batting_team=g.batting_team.replace(
                {"Royal Challengers Bangalore": "Royal Challengers Bengaluru"}
            )
        )
        assert s[s.team == g.batting_team.iloc[0]].runs.sum() == (g.runs_off_bat + g.extras).sum()
        wk = g.player_dismissed.notna().sum()
        n = wk + (
            0 if wk == 10 else 1
        )  # a stand after each wicket, unless all out (no ball follows the 10th)
        assert (s.team == g.batting_team.iloc[0]).sum() == n
        assert sorted(s[s.team == g.batting_team.iloc[0]].wicket_no) == list(range(1, n + 1))
    assert (s.balls <= s.runs.add(60)).all()


def test_partnership_first_stand_is_the_openers(db):
    s = run(db, "partnerships", competition="ipl", group_by="stand", top=100).data
    first = s[(s.wicket_no == 1) & (s.team == "Sunrisers Hyderabad")].iloc[0]
    assert {first.batter1, first.batter2} == {"DA Warner", "S Dhawan"}


def test_partnerships_group_by_pair_player_and_wicket(db):
    pair = run(db, "partnerships", competition="ipl", top=1000).data
    stand = run(db, "partnerships", competition="ipl", group_by="stand", top=1000).data
    assert pair.runs.sum() == stand.runs.sum() and pair.stands.sum() == len(stand)
    wk = run(db, "partnerships", competition="ipl", group_by="wicket").data
    assert wk.runs.sum() == stand.runs.sum() and wk.wicket_no.is_monotonic_increasing
    one = run(db, "partnerships", competition="ipl", player="DA Warner").data
    assert ((one.batter1 == "DA Warner") | (one.batter2 == "DA Warner")).all() and len(one) >= 1


def test_partnerships_count_hundred_dismissal_wicket_numbers(db):
    s = run(db, "partnerships", competition="hundred", group_by="stand", top=1000).data
    assert len(s) > 2 and s.wicket_no.min() == 1


# ── teams / venues ───────────────────────────────────────────────────────────


def test_teams_record(db):
    t = run(db, "teams", competition="ipl").data
    assert t.played.sum() == 2 and set(t.team) == {
        "Sunrisers Hyderabad",
        "Royal Challengers Bengaluru",
    }
    assert ((t.won + t.lost + t.tied + t.no_result) == t.played).all()
    srh = t[t.team == "Sunrisers Hyderabad"].iloc[0]
    assert (srh.won, srh.lost, srh.win_pct) == (1, 0, 100.0)
    assert (srh.bat_first_matches, srh.bat_first_wins, srh.chase_matches) == (
        1,
        1,
        0,
    )  # batted first (innings 1) and won
    assert srh.toss_won == 0  # RCB won the toss
    rcb = t[t.team == "Royal Challengers Bengaluru"].iloc[0]
    assert (rcb.won, rcb.lost, rcb.toss_won, rcb.won_after_toss_win, rcb.chase_matches) == (
        0,
        1,
        1,
        0,
        1,
    )
    assert run(db, "teams", competition="ipl", team="Sunrisers Hyderabad").data.team.tolist() == [
        "Sunrisers Hyderabad"
    ]
    assert run(
        db, "teams", competition="ipl", opposition="Sunrisers Hyderabad"
    ).data.team.tolist() == ["Royal Challengers Bengaluru"]
    by_season = run(db, "teams", competition="ipl", group_by="season").data
    assert (
        list(by_season.columns[:3]) == ["team", "competition", "season"]
        and by_season.played.sum() == 2
    )


def test_venues(db, raw):
    v = run(db, "venues", competition="ipl").data
    assert len(v) == 1 and v.matches[0] == 1
    s1 = (raw[raw.innings == 1].runs_off_bat + raw[raw.innings == 1].extras).sum()
    s2 = (raw[raw.innings == 2].runs_off_bat + raw[raw.innings == 2].extras).sum()
    assert (v.avg_1st_innings[0], v.avg_2nd_innings[0]) == (s1, s2)
    assert v.bat_first_win_pct[0] == 100.0 and v.highest_total[0] == max(s1, s2)
    assert v.lowest_total[0] == min(s1, s2)  # both innings were complete (20 overs / all out)
    assert run(db, "venues", competition="ipl", group_by="season").data.season[0] == "2017"


# ── form ─────────────────────────────────────────────────────────────────────


def test_form_fixture_rows(db, raw):
    f = run(db, "form", player="DA Warner", competition="ipl", window=3).data
    w = raw[raw.striker == "DA Warner"]
    assert len(f) == 1 and (f.runs[0], f.balls[0], f.dismissed[0]) == (
        w.runs_off_bat.sum(),
        (w.wides == 0).sum(),
        1,
    )
    assert f.rolling_runs[0] == f.runs[0]  # window of one row so far
    h = run(db, "form", player="TS Mills", role="bowler", competition="ipl", window=2).data
    m = raw[raw.bowler == "TS Mills"]
    assert len(h) == 1 and h.runs_conceded[0] == (m.runs_off_bat + m.wides + m.noballs).sum()


def test_form_requires_player(db):
    with pytest.raises(ValueError, match="player"):
        run(db, "form", competition="ipl")


# ── viz smoke ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "mid,kw",
    [
        ("batting", {}),
        ("batting", {"player": "DA Warner"}),
        ("batting", {"group_by": "season"}),
        ("batting", {"group_by": "phase", "player": "DA Warner"}),
        ("bowling", {}),
        ("bowling", {"player": "TS Mills"}),
        ("bowling", {"group_by": "season"}),
        ("bowling", {"group_by": "phase", "player": "TS Mills"}),
        ("teams", {}),
        ("teams", {"group_by": "season"}),
        ("venues", {}),
        ("venues", {"group_by": "season"}),
        ("matchup", {"player": "DA Warner"}),
        ("matchup", {"player": "DA Warner", "player2": "TS Mills"}),
        ("partnerships", {}),
        ("partnerships", {"group_by": "stand"}),
        ("partnerships", {"group_by": "wicket"}),
        ("form", {"player": "DA Warner"}),
        ("form", {"player": "TS Mills", "role": "bowler"}),
    ],
)
def test_viz_returns_figure(db, mid, kw):
    r = run(db, mid, competition="ipl", **kw)
    assert isinstance(VIZ[mid].figure(r), go.Figure)


def test_viz_empty_result_is_still_a_figure(db):
    for mid in ("batting", "bowling", "teams", "venues", "matchup", "partnerships"):
        r = run(
            db,
            mid,
            competition="ipl",
            team="Nobody FC",
            **({"player": "Nobody"} if mid == "matchup" else {}),
        )
        assert r.data.empty and isinstance(VIZ[mid].figure(r), go.Figure)


# ── super overs ──────────────────────────────────────────────────────────────


def test_super_over_switch_in_sql():
    on, off = Filters(include_super_overs=True), Filters()
    assert "innings" not in on.where("bowl")[0] and "d.innings <= 2" in off.where("bowl")[0]
    assert on.innings_sql() == "1=1" and off.innings_sql("x") == "x.innings <= 2"


# ═════════════ golden numbers on the real DB ═════════════

real = requires_real_db


@real
def test_buttler_ipl_2022_863_runs():
    d = api.run("batting", player="JC Buttler", competition="ipl", season=2022, db_path=REAL).data
    assert (d.total_runs[0], d.hundreds[0]) == (863, 4)  # the 2022 Orange Cap season (known record)


@real
def test_zero_ball_non_striker_run_out_is_an_innings():
    # RG Sharma, match 501269: run out at the non-striker's end without facing a ball
    f = api.run("form", player="RG Sharma", competition="ipl", db_path=REAL).data
    r = f[f.match_id == "501269"].iloc[0]
    assert (r.runs, r.balls, r.dismissed) == (0, 0, 1)
    b = api.run("batting", player="RG Sharma", competition="ipl", db_path=REAL).data.iloc[0]
    assert (b.innings, b.not_outs, b.average) == (
        276,
        31,
        29.91,
    )  # 7329 runs / 245 outs; retired hurt is not an out


@real
def test_bumrah_ipl_wickets():
    d = api.run("bowling", player="JJ Bumrah", competition="ipl", db_path=REAL).data.iloc[0]
    assert (d.wickets, d.best_figures) == (
        187,
        "5/10",
    )  # best figures 5/10 v KKR 2022 is a known record
    s = api.run(
        "bowling", player="JJ Bumrah", competition="ipl", group_by="season", db_path=REAL
    ).data
    assert (
        s[s.season != "2026"].wickets.sum() == 183
    )  # measured; matches ESPNcricinfo's 183 after IPL 2025 (from memory)
    with use_db(REAL):  # super overs opted in: old B2 value
        assert (
            registry.get("bowling")
            .fn(Filters(player="JJ Bumrah", competition="ipl", include_super_overs=True))
            .wickets[0]
            == 190
        )


@real
def test_csk_ipl_wins():
    t = api.run("teams", competition="ipl", team="Chennai Super Kings", db_path=REAL).data.iloc[0]
    assert (t.played, t.won, t.lost, t.no_result) == (266, 148, 117, 1)  # measured; sums to played
    assert t.played == t.won + t.lost + t.tied + t.no_result


@real
def test_super_over_matches_get_a_winner():
    t = api.run("teams", competition="ipl", db_path=REAL).data
    assert (
        t.tied.sum() == 0
    )  # ingest stores every super-over winner (729315 too: Cricsheet says RR)
    assert (t.won.sum(), t.lost.sum()) == (
        t.lost.sum(),
        t.won.sum(),
    )  # every decided match has one winner and one loser


@real
def test_partnership_record_kohli_de_villiers_229():
    s = api.run("partnerships", competition="ipl", group_by="stand", top=1, db_path=REAL).data.iloc[
        0
    ]
    assert (s.runs, s.balls, {s.batter1, s.batter2}) == (
        229,
        97,
        {"V Kohli", "AB de Villiers"},
    )  # IPL record, 2016 v GL


@real
def test_real_partnerships_add_up_to_innings_totals():
    with use_db(REAL):
        from cricket_analytics.db import query

        tot = query(
            "SELECT sum(runs_total) AS r FROM deliveries d JOIN matches m USING (match_id) "
            "WHERE m.competition = 'ipl' AND m.gender = 'male' AND d.innings <= 2"
        ).r[0]
    s = api.run("partnerships", competition="ipl", group_by="wicket", db_path=REAL).data
    assert s.runs.sum() == tot


@real
def test_form_rolling_matches_pandas_on_real_data():
    f = api.run("form", player="V Kohli", competition="ipl", window=5, db_path=REAL).data
    assert len(f) >= 250 and f.date.is_monotonic_increasing
    ref = f.runs.rolling(5, min_periods=1).mean().round(1)
    assert (f.rolling_runs - ref).abs().max() < 0.11  # rounding only
    sr = (
        f.runs.rolling(5, min_periods=1).sum() * 100 / f.balls.rolling(5, min_periods=1).sum()
    ).round(1)
    assert (f.rolling_sr - sr).abs().max() < 0.11
    # the form rows add up to the batting module's career line
    b = api.run("batting", player="V Kohli", competition="ipl", db_path=REAL).data.iloc[0]
    assert (len(f), f.runs.sum(), f.dismissed.sum()) == (
        b.innings,
        b.total_runs,
        b.innings - b.not_outs,
    )


@real
def test_old_b2_vs_new_bowling():
    """Old B2 and new bowling differ only for known reasons (see docs/WORK_phase2.md, 2B)."""
    new = {
        p: api.run("bowling", player=p, competition="ipl", db_path=REAL).data.iloc[0]
        for p in ("JJ Bumrah", "YS Chahal", "R Ashwin")
    }
    # wickets/runs/innings: identical to old B2 except Bumrah (old included 3 super-over wickets / 28 runs)
    assert [new[p].wickets for p in new] == [187, 233, 187]
    assert [new[p].runs_conceded for p in new] == [4441, 5417, 5652]
    # economy is lower than old B2 because old B2 dropped balls with byes/leg-byes from the legal-ball count
    assert [new[p].economy for p in new] == [7.34, 8.05, 7.2]
