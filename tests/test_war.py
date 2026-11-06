"""WAR / pWAR (models/war.py, the `war` module, charts). Most tests use only the saved parameters, the saved pWAR file and
small synthetic panels (no DB); the season-level ones need the real DB (skipped in CI)."""

import warnings

import numpy as np
import pandas as pd
import pytest

from cricket_analytics import api, registry
from cricket_analytics.models import war as W
from cricket_analytics.viz import video
from cricket_analytics.viz import war as wviz
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")
real = requires_real_db


# ── saved numbers ─────────────────────────────────────────────────────────────────────────────────────────
def test_saved_params_are_sane():
    p = W.load_params()
    assert set(p["era"]) == {"2023", "pre"}
    for e in p["era"].values():
        assert 50 < e["rpw"] < 160  # runs per win: a T20 win costs roughly 100 runs added
        assert (
            e["repl"]["bat"] <= 0 and e["repl"]["bowl"] <= 0
        )  # replacement is never better than average
    d = p["detail"]
    assert d["rpw_now"]["lo"] < d["rpw_now"]["rpw"] < d["rpw_now"]["hi"]
    assert (
        abs(d["rpw_win_prob"] - d["rpw_now"]["rpw"]) < 25
    )  # the independent win-probability check agrees
    for role in ("bat", "bowl"):
        q = p["proj"][role]
        assert (
            all(k in W.KGRID for k in q["k"]) and q["a"] in W.AGRID and q["pre_w"] == 0.0
        )  # Impact era only
        assert len(p["proj"]["balls"][role]) == 3
    assert p["proj"]["ipl_from"] == W.ERA_IPL == 2023


def test_pwar_file_is_consistent():
    d = pd.read_csv(W.DATA / "pwar_ipl_2027.csv")
    assert list(d.columns)[:5] == ["cricsheet_name", "pwar", "bat", "bowl", "exp_balls_bat"]
    assert len(d) > 300 and d.cricsheet_name.is_unique and d.notna().all().all()
    assert (d.pwar - (d.bat + d.bowl)).abs().max() < 0.0021  # rounding only
    assert d.pwar.is_monotonic_decreasing
    assert (d[["exp_balls_bat", "exp_balls_bowl", "ipl_balls_2023_on"]] >= 0).all().all()
    assert (
        d.pwar.abs().max() < 1.5
    )  # a projection regressed to the mean never looks like a 2-win season
    assert (
        d.pwar[d.ipl_balls_2023_on == 0] == 0
    ).all()  # no Impact-era IPL history -> no expected balls -> 0


# ── projection logic on a synthetic panel ──────────────────────────────────────────────────────────────────
def _rows(spec):
    """spec: (player, sy, role, balls, sc, wk) -> a rows frame like season_table's."""
    return pd.DataFrame(
        [
            dict(
                comp="ipl",
                sy=sy,
                season=str(sy),
                team="T",
                player=p,
                role=r,
                balls=b,
                runs=0.0,
                wkts=0.0,
                sc=sc,
                wk=wk,
            )
            for p, sy, r, b, sc, wk in spec
        ]
    )


def _panel(spec_ipl, spec_other=()):
    other = _rows(spec_other) if spec_other else _rows([("zz", 2020, "bat", 1.0, 0.0, 0.0)])
    return W.Panel(_rows(spec_ipl), other)


def _prm(k=(1000, 1000), a=0.0, pre_w=0.0):
    return {
        "ipl_from": 2023,
        "bat": dict(a=a, s=1.0, pre_w=pre_w, k=list(k)),
        "bowl": dict(a=a, s=1.0, pre_w=pre_w, k=list(k)),
    }


def test_projection_shrinks_toward_zero_and_grows_with_evidence():
    # a batter who adds +20 runs per 100 balls: more balls -> closer to his own rate, never past it
    small = _panel([("A", 2025, "bat", 100, 20.0, 0.0)])
    big = _panel([("A", 2025, "bat", 1000, 200.0, 0.0)])
    r_small = W.project_rate(small, "bat", 2026, _prm())[0][small.players.index("A")] * 100
    r_big = W.project_rate(big, "bat", 2026, _prm())[0][big.players.index("A")] * 100
    assert 0 < r_small < r_big < 20
    assert r_small == pytest.approx(20 * 100 / 1100, rel=1e-6)  # n / (n + k) x own rate
    # huge k -> everybody is average
    assert W.project_rate(big, "bat", 2026, _prm(k=(1e12, 1e12)))[0][
        big.players.index("A")
    ] == pytest.approx(0, abs=1e-6)


def test_projection_uses_only_earlier_seasons():
    base = [("A", 2024, "bat", 300, 30.0, 0.0), ("B", 2025, "bat", 300, 5.0, 0.0)]
    changed = base + [
        ("A", 2026, "bat", 500, 400.0, 0.0),
        ("A", 2027, "bat", 500, 400.0, 0.0),
    ]  # target year and later
    for pa, pb in ((_panel(base), _panel(changed)),):
        a = W.project_rate(pa, "bat", 2026, _prm())
        b = W.project_rate(pb, "bat", 2026, _prm())
        assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1]) and np.allclose(a[2], b[2])


def test_impact_era_rule_and_pre_weight():
    spec = [("A", 2021, "bat", 500, 100.0, 0.0), ("A", 2024, "bat", 300, 0.0, 0.0)]
    P = _panel(spec)

    def i(pw):
        return W.project_rate(P, "bat", 2025, _prm(pre_w=pw))[0][P.players.index("A")]

    assert i(0.0) == 0.0  # 2021 is ignored by default (owner's rule)
    assert 0 < i(0.5) < i(1.0)  # ... and only counts when explicitly down-weighted


def test_other_leagues_only_count_with_weight_a():
    other = [("A", 2025, "bat", 600, 120.0, 0.0)]
    P = _panel([("A", 2025, "bat", 1, 0.0, 0.0)], other)
    i = P.players.index("A")
    assert (
        W.project_rate(P, "bat", 2026, _prm(a=0.0))[0][i]
        < W.project_rate(P, "bat", 2026, _prm(a=0.5))[0][i]
    )


def test_expected_balls_is_clipped_and_zero_without_history():
    P = _panel([("A", 2025, "bat", 300, 0.0, 0.0), ("B", 2020, "bat", 300, 0.0, 0.0)])
    e = W.exp_balls(P, "bat", 2026, [-50.0, 0.5, 0.2], 2023)
    assert (
        e[P.players.index("A")] == 100.0 and e[P.players.index("B")] == 0.0
    )  # B has no Impact-era balls
    e2 = W.exp_balls(P, "bat", 2026, [-500.0, 0.5, 0.2], 2023)
    assert (e2 >= 0).all()


def test_war_table_formula():
    prm = {
        "era": {
            "2023": dict(rpw=100.0, repl=dict(bat=-2.0, bowl=-4.0)),
            "pre": dict(rpw=80.0, repl=dict(bat=-3.0, bowl=-1.0)),
        }
    }
    rows = _rows(
        [
            ("A", 2024, "bat", 400, 30.0, 10.0),
            ("A", 2024, "bowl", 100, -5.0, 15.0),
            ("B", 2020, "bat", 100, 8.0, 0.0),
        ]
    )
    t = W.war_table(rows, prm).set_index(["player", "sy"])
    a = t.loc[("A", 2024)]
    assert a.bat_war == pytest.approx(
        (40.0 + 2.0 * 4) / 100
    )  # (runs added - replacement per ball x balls) / runs per win
    assert a.bowl_war == pytest.approx((10.0 + 4.0 * 1) / 100)
    assert a.war == pytest.approx(a.bat_war + a.bowl_war)
    assert t.loc[("B", 2020)].bat_war == pytest.approx(
        (8.0 + 3.0) / 80
    )  # older season: its own era's numbers


def test_runs_per_win_recovers_a_known_slope():
    rng = np.random.default_rng(0)
    n = 60
    ra = rng.normal(0, 60, n)
    ts = pd.DataFrame(
        {
            "yr": 2025,
            "team": [f"T{i}" for i in range(n)],
            "n": 14,
            "rd": ra / 14,
            "w": 0.5 + ra / 100 / 14,
        }
    )
    out = W.runs_per_win(ts, pd.DataFrame({"yr": 2025, "team": ts.team, "ra": ra}), [2025])
    assert out["rpw"] == pytest.approx(100.0, rel=1e-6) and out["lo"] <= 100.0 <= out["hi"]


def test_centre_makes_league_average_zero():
    rows = _rows(
        [
            ("A", 2024, "bat", 100, 10.0, 0.0),
            ("B", 2024, "bat", 300, 5.0, -3.0),
            ("C", 2024, "bowl", 100, 4.0, 0.0),
        ]
    )
    c = W.centre(rows)
    for role, g in c.groupby("role"):
        assert (g.sc.sum() + g.wk.sum()) == pytest.approx(0.0, abs=1e-9)


def test_module_registered_with_schema():
    s = registry.json_schema("war")
    assert s["additionalProperties"] is False
    assert s["properties"]["view"]["enum"] == ["season", "projected"] and s["properties"]["role"][
        "enum"
    ] == ["all", "batting", "bowling"]
    assert "war" in video.module_ids()


def test_projected_view_reads_the_saved_file():
    r = api.run("war", view="projected", top=10)
    d = r.data
    assert len(d) == 10 and d.pwar.is_monotonic_decreasing and "ipl_balls_2023_on" in d.columns
    wviz.figure(r)
    for aspect in ("9:16", "1:1"):
        assert video.video_figure("war", r, aspect).layout.width == 1080
    bow = api.run("war", view="projected", role="bowling", top=5).data
    assert bow.bowl_pwar.is_monotonic_decreasing and "bat_pwar" not in bow.columns
    with pytest.raises(ValueError):
        api.run("war", view="projected", season=2025)


# ── real DB ───────────────────────────────────────────────────────────────────────────────────────────────
@real
def test_shortened_matches_are_in_runs_added():
    k = api.run(
        "runs_added", competition="ipl", season=2016, role="batting", player="V Kohli"
    ).data.iloc[0]
    assert k.runs == 973  # includes the 113* in the D/L match
    b = api.run(
        "runs_added", competition="ipl", season=2024, role="bowling", player="JJ Bumrah"
    ).data.iloc[0]
    assert b.wickets == 20 and b.legal_balls >= 310


@real
@pytest.mark.parametrize(
    "player,year,role", [("JC Buttler", 2022, "batting"), ("JJ Bumrah", 2024, "bowling")]
)
def test_famous_seasons_are_top_3(player, year, role):
    d = api.run("war", competition="ipl", season=year, top=5).data
    assert player in list(d.player.head(3)), d.head(5)
    d2 = api.run("war", competition="ipl", season=year, role=role, top=3).data
    assert d2.player.iloc[0] == player  # and first in their own discipline


@real
def test_season_view_columns_filters_and_errors():
    d = api.run("war", competition="ipl", season=2025, top=500).data
    assert d.season.eq(2025).all() and d.war.is_monotonic_decreasing
    assert (d.war - (d.bat_war + d.bowl_war)).abs().max() < 0.011
    mi = api.run("war", competition="ipl", season=2025, team="Mumbai Indians", top=5).data
    assert mi.war.max() <= d.war.max() + 1e-9 and len(mi) == 5
    one = api.run("war", competition="ipl", player="V Kohli", role="batting").data
    assert one.season.is_unique and len(one) >= 17 and 2016 in set(one.season)
    comp = api.run(
        "war", competition="ipl", season=2024, role="bowling", components=True, top=5
    ).data
    assert {"scoring_part", "wicket_part"} <= set(comp.columns)
    assert ((comp.scoring_part + comp.wicket_part) - comp.runs_added).abs().max() < 0.2
    with pytest.raises(ValueError):
        api.run("war", competition="bbl")
    with pytest.raises(ValueError):
        api.run("war", competition="ipl", venue="Wankhede Stadium, Mumbai")
    wviz.figure(api.run("war", competition="ipl", season=2024))
    video.video_figure("war", api.run("war", competition="ipl", season=2024), "9:16")


@real
def test_league_average_player_is_zero_each_season():
    rows, _ = W.season_table("ipl")
    c = W.centre(rows)
    s = c.assign(ra=c.sc + c.wk).groupby(["sy", "role"]).ra.sum()
    assert s.abs().max() < 1e-6
