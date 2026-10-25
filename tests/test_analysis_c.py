"""Phase 2C modules (impact, true_performance, season_awards, compare, death_overs, pace_vs_spin).

Fixture tests: the two-match fixture DB (one IPL match, one Hundred match) against plain pandas on the raw CSV.
Real-DB tests: skipped when data/cricket_analytics.duckdb is missing.
"""

from pathlib import Path

import pandas as pd
import pytest

from cricket_analytics import api, registry
from cricket_analytics.ingest.cricsheet import load_to_db
from tests.conftest import requires_real_db
from tests.conftest import REAL_DB as REAL

FIX = Path(__file__).parent / "fixtures" / "cricsheet"
IDS = ["impact", "true_performance", "season_awards", "compare", "death_overs", "pace_vs_spin"]
NOT_BOWLER = [
    "run out",
    "retired hurt",
    "retired out",
    "retired not out",
    "obstructing the field",
    "hit the ball twice",
]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("c") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


@pytest.fixture(scope="module")
def ipl():
    """The raw IPL fixture ball by ball with the same helper columns the SQL fragments define."""
    df = pd.read_csv(FIX / "ipl" / "1082591.csv")
    for c in ("wides", "noballs", "byes", "legbyes"):
        df[c] = df[c].fillna(0)
    df["faced"] = df.wides == 0
    df["legal"] = (df.wides == 0) & (df.noballs == 0)
    df["conceded"] = df.runs_off_bat + df.wides + df.noballs
    df["wkt"] = df.wicket_type.notna() & ~df.wicket_type.isin(NOT_BOWLER)
    df["over"] = df.ball.astype(int)
    df["phase"] = pd.cut(df.over, [-1, 5, 14, 99], labels=["powerplay", "middle", "death"]).astype(
        str
    )
    return df


def bat(df, name, **kw):
    s = df[(df.striker == name) & (df.faced)]
    return s.runs_off_bat.sum(), len(s)


def bowl(df, name):
    s = df[df.bowler == name]
    return s.wkt.sum(), s.conceded.sum(), s.legal.sum()


# ── registry ──────────────────────────────────────────────────────────────────


def test_modules_registered_with_schema():
    for i in IDS:
        m = registry.get(i)
        assert registry.json_schema(i)["title"] == i and m.caveats
    assert registry.get("pace_vs_spin").spec("detail").kind == "bool"
    assert registry.get("compare").spec("player2").required
    assert "clutch" not in registry.get("death_overs").title.lower()


# ── impact ────────────────────────────────────────────────────────────────────


def test_impact_hand_calc(db, ipl):
    d = api.run("impact", competition="ipl", min_matches=1, top=100, db_path=db).data.set_index(
        "player"
    )
    runs, balls = bat(ipl, "Yuvraj Singh")
    wk, conc, legal = bowl(ipl, "TS Mills")
    assert d.loc["Yuvraj Singh", "bat_impact"] == pytest.approx(runs * runs / balls * 0.6, abs=0.1)
    expect = wk * 20 + max(8 - conc * 6 / legal, 0) * legal / 6 * 0.4
    assert d.loc["TS Mills", "bowl_impact"] == pytest.approx(expect, abs=0.1)
    assert (d.total_impact - (d.bat_impact + d.bowl_impact)).abs().max() < 0.11
    assert (
        d.bowl_impact.notna().all() and (d.bowl_impact >= 0).all()
    )  # F17: no NULL economy for tiny spells


def test_impact_weights_are_parameters(db):
    a = api.run("impact", competition="ipl", min_matches=1, db_path=db).data.set_index("player")
    b = api.run(
        "impact",
        competition="ipl",
        min_matches=1,
        bat_weight=1.2,
        wicket_points=0,
        econ_weight=0,
        db_path=db,
    ).data.set_index("player")
    assert (b.bat_impact - 2 * a.bat_impact).abs().max() < 0.2  # 120% / 60%, up to 1-dp rounding
    assert (b.bowl_impact == 0).all()
    assert api.run(
        "impact", competition="ipl", min_matches=2, db_path=db
    ).data.empty  # one match only


# ── true_performance ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("comp", ["ipl", "hundred"])
def test_true_performance_league_is_par(db, comp):
    """Summing the expected runs of every ball in the league gives back the actual runs (both roles)."""
    b = api.run("true_performance", competition=comp, min_balls=0, top=500, db_path=db).data
    assert (b.par_sr * b.total_balls / 100).sum() == pytest.approx(b.total_runs.sum(), abs=1.0)
    w = api.run(
        "true_performance", competition=comp, role="bowling", min_balls=0, top=500, db_path=db
    ).data
    assert (w.par_economy * w.balls / 6).sum() == pytest.approx(w.runs_conceded.sum(), abs=1.0)
    assert (b.true_sr >= 0).all() and (w.true_economy >= 0).all()


def test_true_performance_phase_columns_match_batting(db):
    t = api.run(
        "true_performance", competition="hundred", min_balls=0, top=500, db_path=db
    ).data.set_index("batter")
    ph = api.run("batting", competition="hundred", group_by="phase", db_path=db).data
    for r in ph.itertuples():
        assert t.loc[r.batter, f"sr_{r.phase}"] == pytest.approx(r.strike_rate, abs=0.01)


# ── season_awards ─────────────────────────────────────────────────────────────


def test_season_awards_phase_leaders(db, ipl):
    d = api.run("season_awards", competition="ipl", min_balls=1, top=2, db_path=db).data
    assert list(d.columns[:5]) == ["competition", "season", "phase", "rank", "player"]
    assert set(d.phase) == {"powerplay", "middle", "death"} and d["rank"].max() <= 2
    for p, g in d.groupby("phase"):
        s = ipl[(ipl.phase == p) & ipl.faced].groupby("striker").runs_off_bat.sum()
        assert g[g["rank"] == 1].runs.iloc[0] == s.max()
    one = api.run("season_awards", competition="ipl", phase="death", min_balls=1, db_path=db).data
    assert set(one.phase) == {"death"}


def test_season_awards_bowling_and_debutants(db, ipl):
    d = api.run(
        "season_awards", competition="ipl", role="bowling", min_balls=1, top=1, db_path=db
    ).data
    top = d[d.phase == "middle"].iloc[0]
    exp = ipl[ipl.phase == "middle"].groupby("bowler").wkt.sum()
    assert top.wickets == exp.max() and {"economy", "dot_pct", "balls"} <= set(d.columns)
    deb = api.run("season_awards", competition="ipl", award="debutants", min_balls=1, db_path=db)
    assert (
        deb.data.empty and "debut" not in deb.data.columns
    )  # one season only: the competition's first is skipped


# ── compare ───────────────────────────────────────────────────────────────────


def test_compare_batting_matches_batting_module(db):
    d = api.run(
        "compare", player="Yuvraj Singh", player2="S Dhawan", competition="ipl", db_path=db
    ).data
    assert list(d.player.unique()) == ["Yuvraj Singh", "S Dhawan"]  # first player first
    assert (d.groupby("player", sort=False).scope.first() == "overall").all()
    for name in ("Yuvraj Singh", "S Dhawan"):
        b = api.run("batting", player=name, competition="ipl", db_path=db).data.iloc[0]
        o = d[(d.player == name) & (d.scope == "overall")].iloc[0]
        assert (o.innings, o.runs, o.balls, o.strike_rate, o.fours, o.sixes) == (
            b.innings,
            b.total_runs,
            b.balls,
            b.strike_rate,
            b.fours,
            b.sixes,
        )
        assert (
            o.highest == b.highest and o.dot_pct == b.dot_pct and o.boundary_pct == b.boundary_pct
        )
        ph = d[(d.player == name) & (d.scope != "overall")]
        assert ph.runs.sum() == o.runs and ph.balls.sum() == o.balls and ph.outs.sum() == o.outs
        assert ph.highest.isna().all()
    with pytest.raises(ValueError):
        api.run("compare", player="S Dhawan", player2="S Dhawan", db_path=db)


def test_compare_bowling_matches_bowling_module(db, ipl):
    names = list(ipl[ipl.legal].bowler.value_counts().index[:2])
    d = api.run(
        "compare", player=names[0], player2=names[1], role="bowling", competition="ipl", db_path=db
    ).data
    for name in names:
        b = api.run("bowling", player=name, competition="ipl", db_path=db).data.iloc[0]
        o = d[(d.player == name) & (d.scope == "overall")].iloc[0]
        assert (
            o.wickets,
            o.runs_conceded,
            o.balls,
            o.economy,
            o.dot_pct,
            o.boundary_pct,
            o.innings,
        ) == (b.wickets, b.runs_conceded, b.balls, b.economy, b.dot_pct, b.boundary_pct, b.innings)
        assert d[(d.player == name) & (d.scope != "overall")].balls.sum() == o.balls


def test_compare_unknown_player_has_no_rows(db):
    d = api.run(
        "compare", player="Yuvraj Singh", player2="Nobody X", competition="ipl", db_path=db
    ).data
    assert set(d.player) == {"Yuvraj Singh"}


# ── death_overs ───────────────────────────────────────────────────────────────


def test_death_overs_batting(db, ipl):
    d = api.run("death_overs", competition="ipl", min_balls=1, db_path=db).data.set_index("batter")
    assert len(d) > 0
    for name, r in d.iterrows():
        s = ipl[(ipl.striker == name) & ipl.faced]
        dth = s[s.phase == "death"]
        assert r.death_balls == len(dth) and r.death_runs == dth.runs_off_bat.sum()
        assert r.death_index == pytest.approx(r.death_sr / r.overall_sr * 100, abs=0.2)


def test_death_overs_bowling(db, ipl):
    d = api.run(
        "death_overs", competition="ipl", role="bowling", min_balls=1, db_path=db
    ).data.set_index("bowler")
    assert len(d) > 0
    for name, r in d.iterrows():
        s = ipl[(ipl.bowler == name) & ipl.legal]
        assert r.death_balls == (s.phase == "death").sum()
        assert r.death_index == pytest.approx(r.overall_economy / r.death_economy * 100, abs=0.2)


# ── pace_vs_spin ──────────────────────────────────────────────────────────────


def test_pace_vs_spin_team_mode_uses_batting_side(db, ipl):
    d = api.run(
        "pace_vs_spin", competition="ipl", mode="team_vs_type", min_balls=1, db_path=db
    ).data
    assert set(d.level) == {"kind"} and set(d.bowler_type) <= {"Pace", "Spin", "Unknown"}
    got = d.groupby("team").runs.sum()
    exp = ipl.groupby(
        "batting_team"
    ).runs_off_bat.sum()  # (ingest renames Bangalore -> Bengaluru, so compare the numbers)
    assert (
        sorted(got) == sorted(exp) and len(got) == 2
    )  # F1: by the team that batted, not innings 1 = team1
    assert set(d.bowler_type) >= {"Pace", "Spin"}  # the fixture bowlers are in the attributes table
    assert d.groupby("team").pct_of_balls.sum().round(0).eq(100).all()


def test_pace_vs_spin_batter_mode_and_detail(db, ipl):
    d = api.run("pace_vs_spin", competition="ipl", min_balls=1, db_path=db).data
    runs, balls = bat(ipl, "Yuvraj Singh")
    y = d[d.batter == "Yuvraj Singh"]
    assert (y.runs.sum(), y.balls.sum()) == (runs, balls) and set(y.level) == {"kind"}
    assert y.dismissals.sum() == ipl[(ipl.striker == "Yuvraj Singh") & ipl.wkt].shape[0]
    assert y.pct_of_balls.sum().round(0) == 100
    # detail=true adds the bowling-type rows: the same balls again, split finer
    dd = api.run(
        "pace_vs_spin",
        competition="ipl",
        player="Yuvraj Singh",
        detail=True,
        min_balls=1,
        db_path=db,
    ).data
    k, t = dd[dd.level == "kind"], dd[dd.level == "type"]
    assert (k.runs.sum(), k.balls.sum()) == (t.runs.sum(), t.balls.sum()) == (runs, balls)
    assert set(dd.columns) >= {
        "runs",
        "balls",
        "strike_rate",
        "average",
        "dismissals",
        "dot_pct",
        "boundary_pct",
        "pct_of_balls",
    }
    assert not any(x in ("Pace", "Spin", "Unknown") for x in t.bowler_type)


def test_pace_vs_spin_bowler_types(db):
    d = api.run("pace_vs_spin", competition="ipl", mode="bowler_types", db_path=db).data
    assert {"bowler", "balls", "bowl_kind", "bowl_type", "kind_source", "kind_confidence"} <= set(
        d.columns
    )
    assert (
        d.balls.sum() > 0
        and d.balls.is_monotonic_decreasing
        and set(d.bowl_kind) <= {"pace", "spin", "unknown"}
    )


# ── real DB ───────────────────────────────────────────────────────────────────

real = requires_real_db


@real
def test_real_compare_kohli_rohit_ipl():
    d = api.run(
        "compare", player="V Kohli", player2="RG Sharma", competition="ipl", db_path=REAL
    ).data
    assert len(d) == 8
    for name in ("V Kohli", "RG Sharma"):
        b = api.run("batting", player=name, competition="ipl", db_path=REAL).data.iloc[0]
        o = d[(d.player == name) & (d.scope == "overall")].iloc[0]
        assert (o.runs, o.innings, o.average, o.strike_rate, o.hundreds) == (
            b.total_runs,
            b.innings,
            b.average,
            b.strike_rate,
            b.hundreds,
        )
        for ph in api.run(
            "batting", player=name, competition="ipl", group_by="phase", db_path=REAL
        ).data.itertuples():
            assert d[(d.player == name) & (d.scope == ph.phase)].runs.iloc[0] == ph.total_runs


@real
def test_real_impact_agrees_with_batting_and_bowling():
    i = api.run("impact", player="JJ Bumrah", competition="ipl", db_path=REAL).data.iloc[0]
    b = api.run("bowling", player="JJ Bumrah", competition="ipl", db_path=REAL).data.iloc[0]
    assert (i.total_wickets, i.economy) == (b.wickets, b.economy) and i.bowl_impact > 2000
    k = api.run("impact", player="V Kohli", competition="ipl", db_path=REAL).data.iloc[0]
    assert (
        k.total_runs
        == api.run("batting", player="V Kohli", competition="ipl", db_path=REAL).data.total_runs[0]
    )


@real
def test_real_true_performance_and_death_overs():
    t = api.run("true_performance", player="V Kohli", competition="ipl", db_path=REAL).data.iloc[0]
    ph = api.run(
        "batting", player="V Kohli", competition="ipl", group_by="phase", db_path=REAL
    ).data.set_index("phase")
    assert t.sr_death == ph.loc["death", "strike_rate"] and 100 < t.true_sr < 200
    d = api.run(
        "death_overs", player="JJ Bumrah", competition="ipl", role="bowling", db_path=REAL
    ).data.iloc[0]
    b = api.run(
        "bowling", player="JJ Bumrah", competition="ipl", group_by="phase", db_path=REAL
    ).data.set_index("phase")
    assert (
        d.death_economy == b.loc["death", "economy"]
        and d.death_wickets == b.loc["death", "wickets"]
    )
    a = api.run("death_overs", player="V Kohli", competition="ipl", db_path=REAL).data.iloc[0]
    assert a.death_sr == ph.loc["death", "strike_rate"] and a.death_index > 100


@real
def test_real_season_awards_and_pace_vs_spin():
    s = api.run(
        "season_awards", competition="ipl", season=2024, phase="powerplay", top=1, db_path=REAL
    ).data.iloc[0]
    b = api.run(
        "batting", player=s.player, competition="ipl", season=2024, phase="powerplay", db_path=REAL
    ).data.iloc[0]
    assert s.runs == b.total_runs
    deb = api.run(
        "season_awards", competition="ipl", season=2024, award="debutants", db_path=REAL
    ).data
    assert "J Fraser-McGurk" in set(deb.player)
    c = api.run(
        "pace_vs_spin", competition="ipl", mode="bowler_types", db_path=REAL
    ).data.set_index("bowler")
    assert (c.loc["R Ashwin", "bowl_kind"], c.loc["R Ashwin", "bowl_type"]) == (
        "spin",
        "right-arm off spin",
    )
    assert (c.loc["JJ Bumrah", "bowl_kind"], c.loc["JJ Bumrah", "bowl_type"]) == (
        "pace",
        "right-arm fast",
    )
    t = api.run(
        "pace_vs_spin",
        competition="ipl",
        season=2024,
        mode="team_vs_type",
        team="Royal Challengers Bengaluru",
        min_balls=1,
        db_path=REAL,
    ).data
    assert set(t.team) == {"Royal Challengers Bengaluru"}


@real
def test_real_pace_vs_spin_kohli_ipl_and_coverage():
    """Golden numbers (measured 2026-10-24 after the IPL tail was added, types from the override list only): Kohli IPL 9,336 runs =
    5,734 vs pace + 3,203 vs spin + 399 vs bowlers with no listed type."""
    d = api.run(
        "pace_vs_spin", player="V Kohli", competition="ipl", detail=True, min_balls=1, db_path=REAL
    ).data
    k = d[d.level == "kind"].set_index("bowler_type")
    # the split moves as the reviewed list grows, so check invariants, not exact pins
    assert k.loc["Unknown", "balls"] / k.balls.sum() < 0.05
    assert (
        k.loc["Spin", "strike_rate"] < k.loc["Pace", "strike_rate"]
    )  # Kohli scores slower vs spin
    assert (
        k.runs.sum()
        == 9336
        == api.run("batting", player="V Kohli", competition="ipl", db_path=REAL).data.total_runs[0]
    )
    t = d[d.level == "type"]
    assert t.runs.sum() == 9336 and "Left-arm orthodox" in set(t.bowler_type)
    assert (
        t[t.bowler_type == "Unknown type"].runs.iloc[0] == k.loc["Unknown", "runs"]
    )  # kind unknown == type unknown: no derived guess
    cov = {}
    for comp in ("ipl", "t20i"):
        c = api.run(
            "pace_vs_spin", competition=comp, mode="team_vs_type", min_balls=1, db_path=REAL
        ).data
        cov[comp] = c[c.bowler_type.isin(["Pace", "Spin"])].balls.sum() / c.balls.sum() * 100
    assert (
        cov["ipl"] >= 94 and cov["t20i"] >= 35
    )  # floors: coverage only grows as the reviewed list grows (98.1% IPL on 2026-10-25)
    # the rule: experimental while IPL coverage is under 90% (the manual list is expanded to change this)
    assert registry.get("pace_vs_spin").category == (
        "advanced" if cov["ipl"] >= 90 else "experimental"
    )


@real
def test_real_death_overs_min_balls_default():
    r = api.run("death_overs", competition="ipl", top=1000, db_path=REAL).data
    assert len(r) > 100 and r.death_balls.min() >= 60  # rankings hide tiny samples
    b = api.run("death_overs", competition="ipl", role="bowling", top=1000, db_path=REAL).data
    assert b.death_balls.min() >= 60
    one = api.run(
        "death_overs", player="V Kohli", competition="ipl", season=2024, db_path=REAL
    ).data
    assert len(one) == 1  # a named player is never hidden


# ── viz: every figure builds, also from an empty / tiny result ─────────────────

VIZ_CASES = [
    ("impact", dict(min_matches=1)),
    ("true_performance", dict(min_balls=0)),
    ("true_performance", dict(min_balls=0, role="bowling")),
    ("season_awards", dict(min_balls=1)),
    ("season_awards", dict(min_balls=1, role="bowling", phase="death")),
    ("season_awards", dict(award="debutants")),
    ("compare", dict(player="Yuvraj Singh", player2="S Dhawan")),
    ("compare", dict(player="TS Mills", player2="YS Chahal", role="bowling")),
    ("death_overs", dict(min_balls=1)),
    ("death_overs", dict(min_balls=1, role="bowling")),
    ("pace_vs_spin", dict(min_balls=1)),
    ("pace_vs_spin", dict(min_balls=1, mode="team_vs_type")),
    ("pace_vs_spin", dict(mode="bowler_types")),
    ("pace_vs_spin", dict(min_balls=1, detail=True)),
    ("pace_vs_spin", dict(min_balls=1, detail=True, player="Yuvraj Singh")),
    (
        "pace_vs_spin",
        dict(min_balls=1, mode="team_vs_type", detail=True, team="Sunrisers Hyderabad"),
    ),
    ("pace_vs_spin", dict(player="Nobody X")),
    ("death_overs", dict(player="Yuvraj Singh")),
    ("death_overs", dict(player="B Kumar", role="bowling")),
    ("death_overs", dict(player="Nobody X")),
    ("player_profile", dict(player="Yuvraj Singh")),
    ("player_profile", dict(min_matches=1)),
    ("player_profile", dict(player="Nobody X")),
]


@pytest.mark.parametrize(
    "mid,kw", VIZ_CASES, ids=[f"{m}-{i}" for i, (m, _) in enumerate(VIZ_CASES)]
)
def test_viz_figure_builds(db, mid, kw):
    import importlib

    fig = importlib.import_module(f"cricket_analytics.viz.{mid}").figure(
        api.run(mid, competition="ipl", db_path=db, **kw)
    )
    assert fig.layout.title.text
