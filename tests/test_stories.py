"""stories + underrated: fixture DB always (shape, thresholds, charts); real DB for numbers equal to the source modules."""

import warnings
from pathlib import Path

import pytest

from cricket_analytics import api, facts
from cricket_analytics.analysis import stories as st
from cricket_analytics.ingest.cricsheet import load_to_db
import importlib

from cricket_analytics.viz import video
from tests.conftest import requires_real_db

warnings.filterwarnings("ignore")
FIX = Path(__file__).parent / "fixtures" / "cricsheet"


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("s") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    return path


def test_hook_scoring_and_guards():
    src = [{"module": "x", "params": {}}]
    kw = dict(min_n=100, full_n=400, lower_better=False, src=src)
    h = st._hook("t", "strike rate", ("a", 150.0, 400), ("b", 100.0, 900), "balls", **kw)
    assert h["rel_gap"] == 0.333 and h["confidence"] == 1.0 and h["score"] == 0.333
    assert h["sentence"].startswith("strike rate: a 150.00 (400 balls) vs b 100.00 (900 balls)")
    # half the full sample -> confidence sqrt(0.25) = 0.5
    h = st._hook("t", "m", ("a", 150.0, 100), ("b", 100.0, 900), "balls", **kw)
    assert h["confidence"] == 0.5
    # too few balls, missing or zero numbers: no hook
    assert st._hook("t", "m", ("a", 150.0, 99), ("b", 100.0, 900), "balls", **kw) is None
    assert st._hook("t", "m", ("a", None, 500), ("b", 100.0, 900), "balls", **kw) is None
    assert st._hook("t", "m", ("a", 0.0, 500), ("b", 100.0, 900), "balls", **kw) is None
    # lower is better: the lower number is named first
    lo = st._hook(
        "t", "economy", ("a", 9.0, 500), ("b", 6.0, 500), "balls", **{**kw, "lower_better": True}
    )
    assert lo["sentence"].startswith("economy: b 6.00")


def test_fixture_stories_shape_and_ranking(db):
    r = api.run("stories", db_path=db, player="Yuvraj Singh", competition="ipl", min_balls=1)
    d = r.data
    assert list(d.columns) == st.COLUMNS and len(d) > 0
    assert d["score"].is_monotonic_decreasing and list(d["rank"]) == list(range(1, len(d) + 1))
    assert d["theme"].is_unique
    for srcs in d["source"]:  # every hook names the module calls behind it
        assert srcs and all({"module", "params"} <= set(s) for s in srcs)
    assert "record" in set(d["theme"])


def test_unknown_player_gives_empty(db):
    r = api.run("stories", db_path=db, player="Nobody Atall", competition="ipl")
    assert r.data.empty and list(r.data.columns) == st.COLUMNS


def test_fixture_underrated_shape_and_weights(db):
    r = api.run("underrated", db_path=db, competition="ipl", min_balls=1, top=50)
    d = r.data
    assert list(d.columns)[0] == "rank" and d["underrated_score"].is_monotonic_decreasing
    assert (
        d[["quality", "obscurity", "q_true", "o_career"]]
        .apply(lambda c: c.between(0, 1).all())
        .all()
    )
    # score = 100 x quality x obscurity (within rounding)
    assert ((100 * d["quality"] * d["obscurity"]) - d["underrated_score"]).abs().max() < 0.2
    # all weight on one part moves the quality column to that part
    only = api.run(
        "underrated",
        db_path=db,
        competition="ipl",
        min_balls=1,
        top=50,
        w_true=1,
        w_avg=0,
        w_impact=0,
    ).data
    assert (only["quality"] - only["q_true"]).abs().max() < 0.002
    b = api.run("underrated", db_path=db, competition="ipl", role="bowling", min_balls=1)
    assert "bowling" == b.meta["params"]["role"]


@pytest.mark.parametrize("aspect", ["9:16", "1:1"])
def test_charts_build(db, aspect):
    for mod, params in (
        ("stories", dict(player="Yuvraj Singh", competition="ipl", min_balls=1)),
        ("stories", dict(player="Nobody Atall", competition="ipl")),
        ("underrated", dict(competition="ipl", min_balls=1)),
        ("underrated", dict(competition="ipl", min_balls=10**6)),
    ):
        r = api.run(mod, db_path=db, **params)
        fig = video.video_figure(mod, r, aspect)
        assert (fig.layout.width, fig.layout.height) == (
            (1080, 1920) if aspect == "9:16" else (1080, 1080)
        )
        assert importlib.import_module(f"cricket_analytics.viz.{mod}").figure(r) is not None


def test_facts_has_stories_section(db):
    d = facts.build("Yuvraj Singh", "ipl", db_path=db)
    assert d["meta"]["facts_version"] == 2
    if "stories" in d["facts"]:  # tiny fixture: may have no hook with the default thresholds
        s = d["facts"]["stories"]
        assert s["source"][0]["module"] == "stories" and "1" in s
        assert d["tokens"]["stories.1.sentence"] == s["1"]["sentence"]


# ── real DB: the hook numbers equal what the source modules return ─────────────────────────────────────────────


@requires_real_db
def test_real_kohli_hooks_match_source_modules():
    d = api.run("stories", player="V Kohli", competition="ipl", top=20).data
    by = d.set_index("theme")
    assert {"pace_vs_spin", "home_away", "pressure", "death_overs", "recent", "record"} <= set(
        by.index
    )
    ps = api.run("pace_vs_spin", player="V Kohli", competition="ipl").data
    k = ps[ps["level"] == "kind"].set_index("bowler_type")
    h = by.loc["pace_vs_spin"]
    # whichever metric won, the two numbers are the module's pace and spin values
    col = "strike_rate" if h["metric"] == "strike rate" else "average"
    assert (h["value_a"], h["value_b"]) == (k.loc["Pace", col], k.loc["Spin", col])
    pr = api.run("pressure", player="V Kohli", competition="ipl").data.iloc[0]
    h = by.loc["pressure"]
    assert h["value_a"] == (
        pr["pressure_sr"] if h["metric"] == "strike rate" else pr["pressure_avg"]
    )
    assert by.loc["record", "value_a"] == 113  # Kohli's highest IPL score
    # every hook's own source calls reproduce its numbers' sample
    for srcs in d["source"]:
        for s in srcs:
            api.run(s["module"], **s["params"])  # replays without error


@requires_real_db
def test_real_bumrah_is_a_bowler_with_bowling_hooks():
    d = api.run("stories", player="JJ Bumrah", competition="ipl").data
    assert d["metric"].str.contains("economy|bowling average|best figures").all()
    rec = d[d["theme"] == "record"].iloc[0]
    assert rec["sentence"].startswith("best figures 5/10")
    c = api.run(
        "chase_vs_set", player="JJ Bumrah", competition="ipl", role="bowling"
    ).data.set_index("setting")
    h = d[d["theme"] == "chase_vs_set"]
    if len(h):
        col = "economy" if h.iloc[0]["metric"] == "economy" else "average"
        assert (h.iloc[0]["value_a"], h.iloc[0]["value_b"]) == (
            c.loc["setting", col],
            c.loc["chasing", col],
        )


@requires_real_db
def test_real_underrated_ipl_recent():
    for role in ("batting", "bowling"):
        d = api.run("underrated", competition="ipl", last_n_years=3, role=role, top=10).data
        assert len(d) == 10 and d["underrated_score"].is_monotonic_decreasing
        # the famous names are not at the top of an "underrated" list
        assert not {"V Kohli", "JJ Bumrah", "RG Sharma"} & set(d["player"])
