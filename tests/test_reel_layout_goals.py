"""Goal tests for reel chart layout: no subtitle in --video, every glyph exists in the fonts, every label inside the figure. Frozen."""

import pytest
from click.testing import CliRunner
from fontTools.ttLib import TTFont
from matplotlib.text import Text

from cricket_analytics.cli import cli
from cricket_analytics.viz import match_reel

MID = "1535464"
CHARTS = {
    "match_curve": ["chart", "match_curve", MID, "--mark", "swing,low"],
    "score_curve": ["chart", "score_curve", MID, "--inn", "1"],
    "wpa": ["chart", "wpa", "--player", "V Kohli", "--competition", "ipl"],
    "scout_innings": ["chart", "scout_innings", "--scouting", "smat2025", "--player", "Ankit Kumar"],
    "scout_rank": ["chart", "scout_rank", "--scouting", "smat2025", "--role", "bat", "--focus", "Ankit Kumar"],
}
SUBTITLES = ("|", "EVERY INNINGS", "EVERY MATCH", "EVERY SPELL", "projected final score", "RANKED BY SCORE", "average batter", "SMAT 2025-26")


def draw(name, tmp_path, *extra):
    match_reel.DRAWN.clear(), match_reel.LAST_FIG.clear()
    r = CliRunner().invoke(cli, [*CHARTS[name], "--png", str(tmp_path / "c.png"), "--size", "960x760", *extra])
    assert r.exit_code == 0, r.output
    return match_reel.LAST_FIG[0]


def label_boxes(fig):
    """(text, bbox) of every drawn label: overlay text, axes text/annotations, and tick labels whose tick is in view."""
    rend = fig.canvas.get_renderer()
    out = [(t.get_text(), t.get_window_extent(rend)) for t in fig.findobj(Text)
           if t.get_text().strip() and t.get_visible() and t.axes is not None and t not in t.axes.get_xticklabels() + t.axes.get_yticklabels()]
    for ax in fig.axes:
        for axis, lim in ((ax.xaxis, ax.get_xlim()), (ax.yaxis, ax.get_ylim())):
            lo, hi = min(lim), max(lim)
            for loc, t in zip(axis.get_majorticklocs(), axis.get_ticklabels()):
                if lo <= loc <= hi and t.get_text().strip():
                    out.append((t.get_text(), t.get_window_extent(rend)))
    return out


@pytest.mark.parametrize("name", CHARTS)
def test_video_has_no_subtitle(tmp_path, name):
    draw(name, tmp_path, "--video")
    for s in match_reel.DRAWN:
        assert not any(sub in s for sub in SUBTITLES), s


@pytest.mark.parametrize("name", CHARTS)
@pytest.mark.parametrize("extra", [[], ["--video"]])
def test_every_label_inside_figure_and_glyphs_exist(tmp_path, name, extra):
    fig = draw(name, tmp_path, *extra)
    w, h = fig.get_size_inches() * fig.dpi
    boxes = label_boxes(fig)
    assert boxes
    for s, bb in boxes:
        assert bb.x0 >= -1 and bb.y0 >= -1 and bb.x1 <= w + 1 and bb.y1 <= h + 1, (s, bb.bounds, (w, h))
    have = set()
    for f in ("BigShouldersStencilDisplay.ttf", "IBMPlexMono-Bold.ttf"):
        have |= set(TTFont(match_reel.FONT_DIR / f).getBestCmap())
    for s in match_reel.DRAWN:
        assert all(c == "\n" or ord(c) in have for c in s), s
