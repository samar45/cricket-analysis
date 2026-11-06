"""IPL trade tool (models/trade.py, the `trade` module, charts). Everything except the last block runs without the DB: it uses the
saved per-match file, the saved WAR parameters and the contracts / reviewed-list CSVs."""

import warnings

import numpy as np
import pandas as pd
import pytest

from cricket_analytics import api, registry
from cricket_analytics.analysis import trade as atrade
from cricket_analytics.models import trade as T
from cricket_analytics.models import war as W
from cricket_analytics.viz import trade as vtrade
from cricket_analytics.viz import video
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def tab():
    return T.player_table(T.squads(), T.values())


def _fake(n=16, **over):
    """A synthetic squad: first 6 players are the best and all overseas."""
    d = pd.DataFrame(
        {
            "value": np.linspace(1.0, -0.5, n),
            "overseas": [True] * 6 + [False] * (n - 6),
            "keeper": False,
            "keeper_some": False,
            "overs": 3.0,
            "is_bowler": True,
            "bat_pos": 4.0,
            "bat_matches": 20,
        },
        index=[f"p{i}" for i in range(n)],
    )
    d.loc[f"p{n - 1}", "keeper"] = True
    for k, v in over.items():
        d[k] = v
    return d


# ── rules ──────────────────────────────────────────────────────────────────────────────────────────────
def test_synthetic_squad_obeys_overseas_and_keeper():
    d = _fake()
    p = T.pick_xii(d)
    xi = d.loc[p["xi"]]
    assert len(xi) == 11 and len(set(p["xi"])) == 11
    assert xi.overseas.sum() <= T.MAX_OS_XI  # six overseas are the best players, only four may play
    assert xi.keeper.any()  # the keeper is the worst player: the rule still forces him in
    if p["impact"]:
        assert d.loc[p["impact"], "overseas"] == False  # noqa: E712  (XI already has 4 overseas)


def test_no_reviewed_keeper_drops_the_rule_and_says_so():
    d = _fake()
    d["keeper"] = False
    p = T.pick_xii(d)
    assert any("no keeper" in f for f in p["flags"])


def test_impact_player_counts_half_and_only_if_positive():
    d = _fake(value=-0.1)
    assert T.pick_xii(d)["impact"] is None
    d = _fake()
    p = T.pick_xii(d)
    got = d.loc[p["xi"], "value"].sum() + (
        T.IMPACT_WEIGHT * d.loc[p["impact"], "value"] if p["impact"] else 0
    )
    assert p["value"] == pytest.approx(got)


def test_small_squad_is_an_error():
    with pytest.raises(ValueError, match="at least 11"):
        T.pick_xii(_fake(10))


def test_every_real_squad_gives_a_legal_xii(tab):
    for ab, g in tab.groupby("team"):
        p = T.pick_xii(g)
        xi, rows = p["xi"], g.loc[p["xi"]]
        assert len(xi) == 11 and rows.overseas.sum() <= 4, ab
        assert g.loc[xi + ([p["impact"]] if p["impact"] else []), "overseas"].sum() <= 5, ab
        assert p["penalty"] == 0, (
            ab,
            p["flags"],
        )  # every squad can meet the bowling / batting rules
        reviewed = g.keeper.any() or g.keeper_some.any()
        assert (rows.keeper | rows.keeper_some).any() or not reviewed, (
            ab
        )  # a reviewed keeper plays when there is one
        assert rows.overs.sum() >= T.MIN_OVERS and rows.is_bowler.sum() >= T.MIN_BOWLERS, ab


def test_losing_a_player_never_raises_the_xii_value(tab):
    for ab in ("MI", "DC", "RR"):
        g = tab[tab.team == ab]
        base = T.pick_xii(g)
        for k in base["xi"][:4]:
            assert T.pick_xii(g.drop(index=k))["value"] <= base["value"] + 1e-9, (ab, k)


# ── values and ranges ─────────────────────────────────────────────────────────────────────────────────
def test_values_are_weighted_recent_war_and_ranges_bracket_them():
    v = T.values()
    t = v.table
    assert set(T.SEASONS) == {2023, 2024, 2025, 2026} and sum(T.WEIGHTS.values()) == 10
    assert (t.value - (t.bat_value + t.bowl_value)).abs().max() < 1e-9
    d = v.bat_draws + v.bowl_draws
    lo, hi = np.percentile(d, 10, axis=1), np.percentile(d, 90, axis=1)
    inside = ((t.value.values >= lo - 0.05) & (t.value.values <= hi + 0.05)).mean()
    assert inside > 0.95  # the point value sits inside its own bootstrap range
    assert v.debut_pool.mean() == pytest.approx(0, abs=1e-9)


def test_one_season_player_value_equals_that_season_war():
    m = pd.DataFrame(
        {
            "match_id": ["a", "b", "a", "b"],
            "sy": [2026] * 4,
            "player": ["X", "X", "X", "X"],
            "role": ["bat", "bat", "bowl", "bowl"],
            "balls": [10, 20, 6, 12],
            "ra": [3.0, -1.0, 2.0, 4.0],
            "pos": [3, 3, np.nan, np.nan],
        }
    )
    prm = W.load_params()
    e = prm["era"]["2023"]
    v = T.compute_values(m, prm, draws=50)
    bat = (2.0 - e["repl"]["bat"] / 100 * 30) / e["rpw"]
    bowl = (6.0 - e["repl"]["bowl"] / 100 * 18) / e["rpw"]
    assert v.table.loc["X", "value"] == pytest.approx(
        bat + bowl
    )  # a first-season player is not shrunk by missing years


def test_unknown_player_has_zero_value_and_a_flag(tab):
    new = tab[~tab.has_evidence]
    assert len(new) > 10 and (new.value == 0).all() and (new.matches_ipl_2023_on == 0).all()


def test_market_fit_is_reported_with_its_quality(tab):
    f = T.market_fit(tab)
    assert f["n"] > 100 and 0 <= f["r2"] < 0.5  # salary is only loosely tied to recent value
    assert 20 < f["cr_per_win_ratio"] < 80


# ── squads and trades ─────────────────────────────────────────────────────────────────────────────────
def test_squads_baselines():
    cur, pre = T.squads(), T.squads(baseline="before_trades")
    assert "Rishabh Pant" in set(cur[cur.team == "DC"].player) and "Rishabh Pant" in set(
        pre[pre.team == "LSG"].player
    )
    only = T.squads(baseline="before_trades", only=["Rishabh Pant"])
    assert "Rishabh Pant" in set(only[only.team == "LSG"].player)
    assert "T Natarajan" in set(
        only[only.team == "SRH"].player
    )  # the other announced trade stays in place
    assert not T.squads().withdrawn_2026.any()
    with pytest.raises(ValueError):
        T.squads(baseline="nope")


def test_salaries_sum_correctly():
    c = T.load_contracts()
    r = T.evaluate("Mumbai Indians", "Rajasthan Royals", ["Hardik Pandya"], ["Yashasvi Jaiswal"])
    mi, rr = r["teams"]["MI"], r["teams"]["RR"]
    sq = T.squads(c)
    sal = lambda ab: sq[sq.team == ab].price_cr.sum()  # noqa: E731
    assert mi["before"]["squad_salary"] == pytest.approx(sal("MI"))
    assert mi["after"]["squad_salary"] == pytest.approx(sal("MI") - 16.35 + 18.0)
    assert rr["after"]["squad_salary"] == pytest.approx(sal("RR") + 16.35 - 18.0)
    assert mi["purse_change"] == pytest.approx(-rr["purse_change"])  # money just moves


def test_real_trade_uses_the_new_price():
    r = T.evaluate("LSG", "DC", ["Rishabh Pant"], ["Kuldeep Yadav"], baseline="before_trades")
    lsg, dc = r["teams"]["LSG"], r["teams"]["DC"]
    assert lsg["before"]["squad_salary"] - lsg["after"]["squad_salary"] == pytest.approx(
        27.0 - 13.25
    )
    assert (
        dc["after"]["table"].loc["RR Pant", "salary"] == 15.0
    )  # the announced price, not his old 27


def test_no_trade_changes_nothing():
    r = T.evaluate("MI", "RR")
    for x in r["teams"].values():
        assert x["delta"] == 0 and x["p_better"] == 0 and x["purse_change"] == 0
        assert x["verdict"] == "no change to the best XII" and x["net_value_cr"] == 0


def test_unknown_names_and_same_team_are_clear_errors():
    with pytest.raises(ValueError, match="not in the MI squad.*Valid names"):
        T.evaluate("MI", "RR", ["Nobody Atall"], [])
    with pytest.raises(ValueError, match="not in the RR squad"):
        T.evaluate("MI", "RR", [], ["Hardik Pandya"])  # he is MI's, not RR's
    with pytest.raises(ValueError, match="different teams"):
        T.evaluate("MI", "MI")
    with pytest.raises(ValueError, match="Unknown IPL team"):
        T.team_abbr("Mars XI")
    assert T.team_abbr("Royal Challengers Bangalore") == "RCB" and T.team_abbr("mi") == "MI"


def test_names_resolve_from_contract_or_cricsheet_name(tab):
    mi = tab[tab.team == "MI"]
    assert (
        T.resolve(mi, ["hardik pandya"], "MI")
        == T.resolve(mi, ["HH Pandya"], "MI")
        == ["HH Pandya"]
    )
    with pytest.raises(ValueError, match="twice"):
        T.resolve(mi, ["Hardik Pandya", "HH Pandya"], "MI")


def test_verdict_words():
    assert T.verdict(0.0, 0.0, 0.0) == "no change to the best XII"
    assert T.verdict(0.5, -0.2, 0.3) == "too close to call"
    assert (
        T.verdict(0.9, 0.1, 0.5) == "likely better"
        and T.verdict(0.05, -0.5, -0.1) == "likely worse"
    )
    assert (
        T.verdict(0.75, -0.1, 0.5) == "leans better" and T.verdict(0.25, -0.5, 0.1) == "leans worse"
    )


def test_holes_are_slots_below_the_league_median(tab):
    ref = T.league_slot_means(tab)
    h = T.holes(tab[tab.team == "MI"], ref)
    assert set(h) <= {s[0] for s in T.SLOTS}
    sv = T.slot_values(tab[tab.team == "MI"])
    assert all(sv[s] is None or sv[s] < ref[s] for s in h)


# ── module, schema, charts ────────────────────────────────────────────────────────────────────────────
def test_registered_with_player_lists_and_fixed_teams():
    s = registry.json_schema("trade")["properties"]
    assert s["give"]["type"] == "array" and s["get"]["type"] == "array"
    assert set(s["team"]["enum"]) == set(T.TEAMS.values()) == set(s["team2"]["enum"])
    assert "trade" in video.module_ids()


def _frame():
    return atrade._trade_frame(
        T.evaluate("MI", "RR", ["Hardik Pandya"], ["Yashasvi Jaiswal", "Yash Raj Punja"])
    )


def test_trade_frame_and_charts_build_without_the_db():
    d = _frame()
    assert len(d) == 2 and set(d.verdict) <= set(vtrade.VERDICT_COLOUR)
    meta = {"params": {"team": "Mumbai Indians"}, "data_through": "2026-05-31"}
    r = api.Result(d, meta)
    assert len(vtrade.figure(r).layout.annotations) >= 4
    for aspect, size in (("9:16", (1080, 1920)), ("1:1", (1080, 1080))):
        fig = video.video_figure("trade", r, aspect)
        assert (fig.layout.width, fig.layout.height) == size
    sq = T.squad_view("Mumbai Indians")
    assert (sq.recent_value.diff().dropna() <= 1e-9).all() and set(sq.in_best_xii) == {
        "",
        "XI",
        "impact",
    }
    rs = api.Result(sq, meta)
    assert len(vtrade.figure(rs).data) == 1
    assert video.video_figure("trade", rs, "9:16").layout.width == 1080
    assert vtrade.figure(api.Result(d.iloc[:0], meta)).layout.title.text


# ── needs the real DB ─────────────────────────────────────────────────────────────────────────────────
@requires_real_db
def test_match_table_reproduces_season_war():
    prm = W.load_params()
    r = W.centre(W.season_table("ipl")[0])
    wt = W.war_table(r, prm)
    m = pd.read_csv(T.MATCH_CSV)
    e = prm["era"]["2023"]
    g = m.groupby(["player", "role", "sy"])[["balls", "ra"]].sum().reset_index()
    g["war"] = (
        g.ra - g.role.map({"bat": e["repl"]["bat"], "bowl": e["repl"]["bowl"]}) / 100 * g.balls
    ) / e["rpw"]
    k = g[(g.player == "JJ Bumrah") & (g.sy == 2024) & (g.role == "bowl")].war.iloc[0]
    ref = wt[(wt.player == "JJ Bumrah") & (wt.sy == 2024)].bowl_war.iloc[0]
    assert k == pytest.approx(ref, abs=1e-4) and k > 1.5


@requires_real_db
def test_api_run_both_views_and_bad_input():
    r = api.run(
        "trade",
        team="Mumbai Indians",
        team2="Rajasthan Royals",
        give=["Hardik Pandya"],
        get="Yashasvi Jaiswal",
    )
    assert len(r.data) == 2 and r.meta["module"] == "trade"
    assert len(api.run("trade", team="Delhi Capitals", view="squad").data) >= 20
    with pytest.raises(ValueError, match="not in the MI squad"):
        api.run("trade", team="Mumbai Indians", give=["Nobody Atall"])
    with pytest.raises(ValueError):
        api.run("trade", competition="bbl")


@requires_real_db
def test_api_passes_team_through_filters():
    # "team" is a Filters field; the module must still use the team the caller picked (bug found 2026-11-06).
    r = api.run(
        "trade",
        team="Lucknow Super Giants",
        team2="Delhi Capitals",
        give=["Rishabh Pant"],
        get=["Kuldeep Yadav"],
        baseline="before_trades",
    )
    assert r.data["team"].iloc[0] == "Lucknow Super Giants"
