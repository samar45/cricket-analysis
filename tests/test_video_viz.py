"""Video charts (viz/video): every module builds at 9:16 and 1:1 with the right size, a transparent background, no
legend, and no tiny text. Fixture DB (two matches) always; the real DB demo inputs when it exists."""

import sys
import warnings
from pathlib import Path

import pytest

from cricket_analytics import api, registry
from cricket_analytics.ingest.cricsheet import load_to_db
from cricket_analytics.viz import video

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent.parent
FIX = Path(__file__).parent / "fixtures" / "cricsheet"
REAL = ROOT / "data" / "cricket_analytics.duckdb"
SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080)}
IPL = dict(competition="ipl")
MIN_FONT = 30   # px at 1080 wide: anything smaller is unreadable on a phone

# fixture DB: one IPL match (1082591); many tables are legitimately empty, a figure must still build
FIXTURE_CASES = [
    ("batting", dict(IPL, player="Yuvraj Singh")), ("batting", IPL), ("batting", dict(IPL, group_by="phase")),
    ("batting", dict(IPL, player="Yuvraj Singh", group_by="season")),
    ("bowling", dict(IPL, player="B Kumar")), ("bowling", IPL), ("bowling", dict(IPL, group_by="phase")),
    ("teams", dict(IPL, team="Sunrisers Hyderabad")), ("teams", IPL),
    ("venues", IPL), ("matchup", dict(IPL, player="Yuvraj Singh")), ("partnerships", IPL),
    ("partnerships", dict(IPL, group_by="stand")), ("form", dict(IPL, player="Yuvraj Singh")),
    ("impact", IPL), ("true_performance", dict(IPL, min_balls=1)), ("season_awards", IPL),
    ("compare", dict(IPL, player="Yuvraj Singh", player2="S Dhawan")), ("death_overs", IPL),
    ("pace_vs_spin", IPL), ("pace_vs_spin", dict(IPL, mode="team_vs_type")),
    ("player_profile", dict(player="Yuvraj Singh")), ("player_profile", {}),
]


def check(fig, aspect):
    assert (fig.layout.width, fig.layout.height) == SIZES[aspect]
    eff = lambda k: getattr(fig.layout, k) or getattr(fig.layout.template.layout, k)   # figure value, else the reel template's
    assert eff("paper_bgcolor") == "rgba(0,0,0,0)" and eff("plot_bgcolor") == "rgba(0,0,0,0)"
    assert eff("showlegend") is False                          # direct labels, never a legend that can overflow
    assert not any(getattr(t, "showlegend", False) for t in fig.data)
    sizes = [a.font.size for a in fig.layout.annotations]
    assert sizes and min(sizes) >= MIN_FONT and max(sizes) >= 56   # a title of 56+ px is always there
    for t in fig.data:
        tf = getattr(t, "textfont", None)
        if tf is not None and tf.size:
            assert tf.size >= MIN_FONT


def build(module_id, result, aspect, focus=None):
    check(video.video_figure(module_id, result, aspect, focus), aspect)


def test_every_registered_module_has_a_video_chart():
    ids = set(video.module_ids())
    assert ids <= {m.id for m in registry.all_modules()}
    assert {"batting", "bowling", "teams", "venues", "matchup", "partnerships", "form", "impact", "true_performance",
            "season_awards", "compare", "death_overs", "pace_vs_spin", "player_profile"} <= ids


def test_bad_aspect_is_rejected():
    with pytest.raises(ValueError):
        video.new_fig("4:3", "x")


def test_big_number_card_sizes_and_numbers():
    for aspect in SIZES:
        for n in (1, 2, 3, 4):
            fig = video.big_number_card([("9,336", "runs")] * n, "V KOHLI", aspect)
            check(fig, aspect)
            assert max(a.font.size for a in fig.layout.annotations) >= 96   # the numbers themselves


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("v") / "t.duckdb"
    load_to_db("ipl", data_dir=FIX / "ipl", db_path=path)
    load_to_db("hundred", data_dir=FIX / "hundred", db_path=path)
    return path


@pytest.mark.parametrize("aspect", list(SIZES))
@pytest.mark.parametrize("module_id,params", FIXTURE_CASES, ids=[f"{m}-{i}" for i, (m, _) in enumerate(FIXTURE_CASES)])
def test_fixture_db_builds(fixture_db, module_id, params, aspect):
    build(module_id, api.run(module_id, db_path=fixture_db, **params), aspect)


def test_fixture_bowling_donut_counts_wickets(fixture_db):
    from cricket_analytics.viz.video.bowling import wicket_kinds
    r = api.run("bowling", db_path=fixture_db, **IPL)
    assert sum(wicket_kinds(r).values()) == int(r.data["wickets"].sum())   # donut total == module total


# ── real DB, the same demo inputs as the gallery ────────────────────────────────────────────────────────────
real = pytest.mark.skipif(not REAL.exists(), reason="real DB not built")


def _real_cases():
    sys.path.insert(0, str(ROOT / "experiments"))
    import video_gallery
    return video_gallery.CASES


@real
@pytest.mark.parametrize("aspect", list(SIZES))
def test_real_db_demo_inputs_build(aspect):
    for label, module_id, params, focus in _real_cases():
        build(module_id, api.run(module_id, db_path=REAL, **params), aspect, focus)


@real
def test_real_db_numbers_on_the_chart():
    """The first big number on Kohli's card is his IPL career runs (9,336, same as the golden test)."""
    r = api.run("batting", db_path=REAL, competition="ipl", player="V Kohli")
    fig = video.video_figure("batting", r, "9:16")
    assert "9,336" in [a.text for a in fig.layout.annotations]
    d = api.run("bowling", db_path=REAL, competition="ipl", player="JJ Bumrah")
    pie = video.video_figure("bowling", d, "9:16").data[0]
    assert sum(pie.values) == 187
