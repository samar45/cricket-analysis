"""End-to-end checks of the 'value' chain (runs_added, wpa, war, matchup_predict, trade) on the real DB.

Raw DB -> saved models -> modules -> CLI -> dashboard -> reel PNG. All deterministic, read-only, skipped without the DB.
Written by the QA pass of 2026-11-06; findings in docs/E2E_value.md.
"""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner
from streamlit.testing.v1 import AppTest

from cricket_analytics import api, registry
from cricket_analytics.cli import cli
from tests.conftest import requires_real_db

pytestmark = requires_real_db
DATA = Path(__file__).parent.parent / "src" / "cricket_analytics" / "models" / "data"
APP = str(Path(__file__).parent.parent / "dashboard" / "app.py")
MI, RR, KKR = "Mumbai Indians", "Rajasthan Royals", "Kolkata Knight Riders"


def run(mod, **k):
    return api.run(mod, **k).data


def row(df, col, val):
    return df[df[col] == val].iloc[0]


@pytest.fixture(scope="module")
def prm():
    return json.loads((DATA / "war_params.json").read_text())


# ── golden numbers through the new modules ────────────────────────────────────────────────────────────────
def test_golden_raw_numbers_via_runs_added():
    k = row(
        run("runs_added", competition="ipl", season=2016, min_balls=1, top=500), "batter", "V Kohli"
    )
    assert k.runs == 973
    b = row(
        run("runs_added", competition="ipl", season=2022, min_balls=1, top=500),
        "batter",
        "JC Buttler",
    )
    assert b.runs == 863
    bu = row(
        run("runs_added", competition="ipl", season=2024, role="bowling", min_balls=1, top=500),
        "bowler",
        "JJ Bumrah",
    )
    assert (bu.legal_balls, bu.wickets) == (311, 20)


# ── WAR = (runs added - replacement x balls) / runs per win ───────────────────────────────────────────────
@pytest.mark.parametrize(
    "player,year,era",
    [("V Kohli", 2016, "pre"), ("JC Buttler", 2022, "pre"), ("JJ Bumrah", 2024, "2023")],
)
def test_war_formula_and_link_to_runs_added(prm, player, year, era):
    w = run("war", competition="ipl", season=year, player=player, min_balls=1).iloc[0]
    e = prm["era"][era]
    bat = (w.bat_runs_added - e["repl"]["bat"] / 100 * w.bat_balls) / e["rpw"]
    bowl = (w.bowl_runs_added - e["repl"]["bowl"] / 100 * w.bowl_balls) / e["rpw"]
    assert w.bat_war == pytest.approx(bat, abs=0.01) and w.bowl_war == pytest.approx(bowl, abs=0.01)
    assert w.war == pytest.approx(w.bat_war + w.bowl_war, abs=0.011)
    # WAR re-centres each league-season, so its runs differ a little from the runs_added module (finding F6)
    ra = run("runs_added", competition="ipl", season=year, player=player, min_balls=1)
    if len(ra):
        assert abs(ra.runs_added.iloc[0] - w.bat_runs_added) < 12


# ── trade card = weighted WAR seasons ─────────────────────────────────────────────────────────────────────
def test_trade_recent_value_is_the_weighted_war_seasons():
    sq = pd.concat([run("trade", team=t, view="squad") for t in (MI, KKR)])
    wars = {
        y: run("war", competition="ipl", season=y, min_balls=1, top=2000).set_index("player").war
        for y in (2023, 2024, 2025, 2026)
    }
    for name, key, first in (
        ("Sunil Narine", "SP Narine", 2023),
        ("Jasprit Bumrah", "JJ Bumrah", 2024),
    ):
        r = sq[sq.player == name].iloc[0]
        for y in wars:
            assert r[f"war_{y}"] == pytest.approx(float(wars[y].get(key, 0.0)), abs=0.011)
        wt = {2026: 4, 2025: 3, 2024: 2, 2023: 1}
        seasons = [y for y in wt if y >= first]
        exp = sum(wt[y] * float(wars[y].get(key, 0.0)) for y in seasons) / sum(
            wt[y] for y in seasons
        )
        assert r.recent_value == pytest.approx(exp, abs=0.01)


# ── WPA ───────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mid", [981019, 981017, 1473511])
def test_wpa_swings_sum_to_result_minus_start(mid):
    d = run("wpa", view="match", match_id=mid, top=1000)
    assert len(d) > 200
    res = 1.0 if d.winner.iloc[0] == d.bat_first.iloc[0] else 0.0
    assert d.swing.sum() == pytest.approx(res - d.wp_bf_before.iloc[0], abs=1e-6)
    assert d.wp_bat_first.iloc[-1] == pytest.approx(res)


def test_wpa_dl_final_raises_explained():
    with pytest.raises(ValueError, match="Duckworth"):  # 2023 final, rain-affected
        run("wpa", view="match", match_id=1370353)


# ── trade: rules and edge cases ───────────────────────────────────────────────────────────────────────────
def test_trade_hardik_must_play_matches_docs():
    d = run(
        "trade",
        team=MI,
        team2=RR,
        give="Hardik Pandya",
        get="Yashasvi Jaiswal",
        must_play="Hardik Pandya",
    )
    mi = d.iloc[0]
    assert (mi.xii_before, mi.xii_after) == (2.3, 2.69)
    assert 40 < mi.playoff_pct_before < 44 and mi.playoff_pts_change > 0


def test_trade_empty_give_get_is_a_noop():
    d = run("trade", team=MI, team2=RR)
    assert (d.change == 0).all() and (d.verdict == "no change to the best XII").all()


def test_trade_kkr_without_keeper_still_runs_and_says_so():
    d = run("trade", team=KKR, view="squad")
    assert len(d) >= 18
    r = api.run("trade", team=KKR, team2=MI, give=[d.player.iloc[0]])
    assert len(r.data) == 2


@pytest.mark.parametrize("comp", ["bbl", "t20i", "hundred"])
def test_trade_rejects_non_ipl(comp):
    with pytest.raises(ValueError, match="IPL only"):
        api.run("trade", competition=comp)


def test_trade_same_team_and_wrong_side_errors():
    with pytest.raises(ValueError, match="different teams"):
        api.run("trade", team=MI, team2=MI, give="Hardik Pandya")
    with pytest.raises(ValueError, match="not in the RR squad"):
        api.run("trade", team=MI, team2=RR, give="Hardik Pandya", get="Jos Buttler")


def test_war_ipl_only():
    with pytest.raises(ValueError, match="IPL only"):
        api.run("war", competition="hundred")


# ── edge: empty results and the Hundred ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mod", ["runs_added", "wpa", "war"])
def test_unknown_player_and_empty_season_raise_clear_error(mod):
    with pytest.raises(ValueError, match="No player named 'Zzz Nobody'"):
        run(mod, player="Zzz Nobody", competition="ipl")
    with pytest.raises(ValueError, match="No data"):
        run(mod, season=1999, competition="ipl")


def test_matchup_unknown_player_errors_clearly():
    with pytest.raises(ValueError, match="no balls"):
        api.run("matchup_predict", player="Zzz Nobody", player2="JJ Bumrah")


def test_runs_added_hundred_works_and_wpa_hundred_is_empty():
    d = run("runs_added", competition="hundred")
    assert len(d) == 40 and d.balls.min() >= 1
    with pytest.raises(ValueError, match="not The Hundred"):  # documented: no 100-ball model
        run("wpa", competition="hundred")


# ── matchup predictor ─────────────────────────────────────────────────────────────────────────────────────
def test_matchup_card_and_grid_probabilities_sum_to_one():
    c = run("matchup_predict", player="V Kohli", player2="JJ Bumrah", competition="ipl").iloc[0]
    tot = sum(c[f"p_{k}"] for k in ("dot", "1", "2", "3", "4", "6")) + c.p_out
    assert (
        0.98 < tot < 1.02 or abs(tot - 1) < 0.05
    )  # p_out overlaps a run outcome (run outs): loose
    assert 5 < c.exp_runs_per_6 < 12 and 0.01 < c.p_out < 0.10
    g = run(
        "matchup_predict", player="V Kohli", player2="JJ Bumrah", competition="ipl", view="grid"
    )
    assert len(g) > 5


# ── CLI ───────────────────────────────────────────────────────────────────────────────────────────────────
def _cli(*a):
    return CliRunner().invoke(cli, list(a))


@pytest.mark.parametrize(
    "args",
    [
        ("run", "runs_added", "--competition", "ipl", "--season", "2024", "--json"),
        ("run", "wpa", "--view", "match", "--match_id", "981019", "--json"),
        ("run", "war", "--view", "projected", "--json"),
        ("run", "matchup_predict", "--player", "V Kohli", "--player2", "JJ Bumrah", "--json"),
        ("run", "trade", "--view", "squad", "--team", KKR, "--json"),
        (
            "run",
            "trade",
            "--team",
            "Lucknow Super Giants",
            "--team2",
            "Delhi Capitals",
            "--give",
            "Rishabh Pant",
            "--get",
            "Kuldeep Yadav",
            "--baseline",
            "before_trades",
            "--json",
        ),
    ],
)
def test_cli_json(args):
    r = _cli(*args)
    assert r.exit_code == 0, r.output
    d = json.loads(r.output)
    assert d["meta"]["row_count"] == len(d["data"]) > 0


def test_cli_trade_non_ipl_exits_nonzero():
    r = _cli("run", "trade", "--competition", "bbl")
    assert r.exit_code != 0 and "IPL only" in r.output


@pytest.mark.parametrize(
    "mod,extra",
    [
        ("runs_added", ["--competition", "ipl", "--season", "2024"]),
        ("wpa", ["--view", "match", "--match_id", "981019"]),
        ("war", ["--view", "projected"]),
        ("matchup_predict", ["--player", "V Kohli", "--player2", "JJ Bumrah"]),
        (
            "trade",
            ["--team", MI, "--team2", RR, "--give", "Hardik Pandya", "--get", "Yashasvi Jaiswal"],
        ),
    ],
)
def test_cli_chart_png_is_1080x1920_with_content(mod, extra):
    from PIL import Image

    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "c.png"
        r = _cli("chart", mod, *extra, "--aspect", "9:16", "--png", str(p))
        assert r.exit_code == 0, r.output
        im = Image.open(p)
        assert im.size == (1080, 1920)
        assert (
            im.convert("RGBA").getchannel("A").getextrema()[1] > 0
        )  # something was drawn (bg is transparent by design)


# ── dashboard (AppTest) ───────────────────────────────────────────────────────────────────────────────────
def _open(mod):
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.radio(key="page").set_value("Explore").run()
    at.radio(key="category").set_value(registry.get(mod).category).run()
    return at.selectbox(key="module").set_value(mod).run()


def _clean(at):
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


NONDEFAULT = {  # one non-default param set per module: (widget getter, key, value)
    "runs_added": [
        ("selectbox", "p_competition", "ipl"),
        ("selectbox", "runs_added_role", "bowling"),
    ],
    "wpa": [("selectbox", "p_competition", "ipl"), ("selectbox", "wpa_view", "match")],
    "war": [("selectbox", "p_competition", "ipl"), ("selectbox", "war_view", "projected")],
    "matchup_predict": [
        ("selectbox", "p_competition", "ipl"),
        ("selectbox", "p_player", "V Kohli"),
        ("selectbox", "p_player2", "JJ Bumrah"),
        ("selectbox", "matchup_predict_view", "grid"),
    ],
}


@pytest.mark.parametrize("mod", ["runs_added", "wpa", "war", "trade"])
def test_dashboard_defaults(mod):
    _clean(_open(mod))


def test_dashboard_matchup_defaults_need_players():
    at = _open("matchup_predict")
    at.selectbox(key="p_competition").set_value("ipl").run()
    at.selectbox(key="p_player").set_value("V Kohli").run()
    at.selectbox(key="p_player2").set_value("JJ Bumrah").run()
    _clean(at)


@pytest.mark.parametrize("mod", ["runs_added", "wpa", "war", "matchup_predict"])
def test_dashboard_non_default(mod):
    at = _open(mod)
    for getter, key, val in NONDEFAULT[mod]:
        getattr(at, getter)(key=key).set_value(val).run()
    _clean(at)


def test_dashboard_trade_card_html_and_nondefault():
    at = _open("trade")
    _clean(at)
    assert at.get("html"), "trade card HTML missing with default params"
    at.selectbox(key="p_team").set_value(MI).run()
    at.selectbox(key="trade_team2").set_value(RR).run()
    at.multiselect(key="trade_give").set_value(["Hardik Pandya"]).run()
    at.multiselect(key="trade_get").set_value(["Yashasvi Jaiswal"]).run()
    at.multiselect(key="trade_must_play").set_value(["Hardik Pandya"]).run()
    _clean(at)
    body = "".join(h.proto.body for h in at.get("html"))
    assert "Hardik" in body and "Jaiswal" in body
    at.selectbox(key="trade_view").set_value("squad").run()
    _clean(at)
