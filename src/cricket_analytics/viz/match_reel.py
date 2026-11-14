"""Reel charts for one match: `match_curve` (win % by over) and `score_curve` (projected vs actual score). Matplotlib, not the
plotly/kaleido path: kaleido only sees installed fonts, and the reel fonts are loaded here straight from their TTF files.
Transparent PNG, one message and one big number per chart, a source footnote."""

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402

DEFAULT_PALETTE = {"bg": "#111111", "ink": "#f3efe4", "a1": "#ffb000", "a2": "#d7262e"}  # = viz/video: cream ink, amber, red
FONT_DIR = Path(os.environ.get("CRICKET_FONT_DIR", r"D:\Claude projects\Edit Pipeline\assets\fonts"))
NUM_TTF, LABEL_TTF = "BigShouldersStencilDisplay.ttf", "IBMPlexMono-Bold.ttf"
PX = 72 / 100  # points per pixel at dpi=100


def _fonts(font_dir):
    """(number font, label font, status text). Falls back to the default font if a TTF is missing."""
    d, got, props = Path(font_dir or FONT_DIR), [], []
    for ttf, fam in ((NUM_TTF, "Big Shoulders Stencil Display"), (LABEL_TTF, "IBM Plex Mono Bold")):
        f = d / ttf
        if f.exists():
            fm.fontManager.addfont(str(f))
            props.append(fm.FontProperties(fname=str(f)))
            got.append(f"{fam} OK")
        else:
            props.append(fm.FontProperties(family="DejaVu Sans", weight="bold"))
            got.append(f"{fam} MISSING ({f}), fell back to DejaVu Sans")
    return props[0], props[1], "; ".join(got)


def _alpha(c, a):
    return matplotlib.colors.to_rgba(c, a)


def draw(kind, x, png, w, h, pal, team=None, marks=(), inn=1, upto=None, thru="", font_dir=None) -> str:
    """kind: match_curve | score_curve. x = matchreel.compute(). Returns the fonts status line."""
    from ..matchreel import _chase, _curve_facts

    num, lab, status = _fonts(font_dir)
    meta, rows = x["meta"], x["rows"]
    ink, a1, a2, bg = pal["ink"], pal["a1"], pal["a2"], pal["bg"]
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    fig.patch.set_alpha(0)
    ov = fig.add_axes([0, 0, 1, 1])  # whole-figure axes in pixels (y down) for the text
    ov.set_xlim(0, w), ov.set_ylim(h, 0), ov.axis("off"), ov.patch.set_alpha(0)
    pad, k = int(w * 0.06), min(w / 960, h / 980)
    ax_l = pad + 110 * k  # room for the y tick labels

    def text(px, py, s, size, font, color=ink, ha="left", va="top", **kw):
        ov.text(px, py, s, fontproperties=font, fontsize=size * k * PX, color=color, ha=ha, va=va, **kw)

    n_over = max(20, max(r["over"] for r in rows))
    if kind == "match_curve":
        side = team or x["chase"]
        if side not in (x["chase"], x["defend"]):
            raise ValueError(f"--team must be {x['chase']!r} or {x['defend']!r}")
        flip = side == x["defend"]
        pts = [(r["over"], (1 - r["win_pct"]) if flip else r["win_pct"]) for r in _chase(rows)]
        shown = [p for p in pts if upto is None or p[0] <= upto]
        if not shown:
            raise ValueError("--upto is before the first point")
        text(pad, 60 * k, f"{side.upper()} WIN CHANCE", 40, lab)
        text(pad, 112 * k, f"{x['defend']} v {x['chase']}, {meta['date']}", 28, lab, ink, alpha=0.6)
        big = f"{round(100 * shown[-1][1])}%"
        text(pad, 170 * k, big, 250, num, a1)
        text(pad + 20 * k, 480 * k, f"after over {shown[-1][0]}" if shown[-1][0] < pts[-1][0] else "at the end of the match", 30, lab, ink, alpha=0.7)
        top, bot = 560 * k, h - 190 * k
        ax = fig.add_axes([ax_l / w, 1 - bot / h, (w - pad - ax_l) / w, (bot - top) / h])
        ax.patch.set_alpha(0)
        ax.set_xlim(0, n_over), ax.set_ylim(0, 1)
        ax.axhline(0.5, color=ink, lw=2 * k, ls=(0, (4, 4)), alpha=0.55)
        # ponytail: the model has no band for win %, so none is drawn; add a1 @ 25% fill_between here if it ever does
        ax.plot([p[0] for p in shown], [p[1] for p in shown], color=a1, lw=9 * k, solid_capstyle="round", solid_joinstyle="round")
        ax.set_yticks([0, 0.5, 1], ["0%", "50%", "100%"])
        f = _curve_facts(x)
        sw, lo = (f.get(m) if m in marks else None for m in ("swing", "low"))
        sw = sw if sw and (upto is None or sw["over"] <= upto) else None
        lo = lo if lo and (upto is None or lo["over"] <= upto) else None
        chip = dict(boxstyle="round,pad=0.25", fc=bg, ec="none", alpha=0.9)  # hides the 50% guide behind a label
        o = lambda v: v * k * PX  # noqa: E731  (pixels -> points)
        same = bool(sw and lo and sw["over"] == lo["over"])
        if sw:
            px, py = sw["over"], (sw["to"] if not flip else 1 - sw["to"])
            ax.plot([px], [py], "o", ms=26 * k, mfc=bg, mec=a2, mew=6 * k, zorder=5)
            who = " v ".join(v.split()[-1] for v in (sw.get("bowler"), sw.get("batter")) if v)
            dy = -(78 if same else 16)  # shared over: the swing label sits under the LOW label
            ax.annotate(f"OVER {px}: {sw['delta_pct']} PTS\n{who}", (px, py), xytext=(o(34), o(dy)), textcoords="offset points", ha="left", va="top",
                        color=a2, fontproperties=lab, fontsize=30 * k * PX, bbox=chip, zorder=6)
        if lo:
            px, py = lo["over"], (lo["win_pct"] if lo["team"] == side else 1 - lo["win_pct"])
            if not same:
                ax.plot([px], [py], "o", ms=20 * k, mfc=bg, mec=ink, mew=5 * k, zorder=5)
            ax.annotate(f"LOW {lo['pct']}%", (px, py), xytext=(o(34), o(-16)), textcoords="offset points", ha="left", va="top",
                        color=ink, fontproperties=lab, fontsize=30 * k * PX, bbox=chip, zorder=6)
        xl = "OVERS"
    else:  # score_curve
        if inn not in (1, 2):
            raise ValueError("--inn must be 1 or 2")
        bat = meta["team1"] if inn == 1 else meta["team2"]
        pts = [r for r in rows if r["inn"] == inn]
        shown = [r for r in pts if upto is None or r["over"] <= upto]
        if not shown:
            raise ValueError("--upto is before the first point")
        text(pad, 60 * k, f"{bat.upper()} SCORE, INNINGS {inn}", 40, lab)
        text(pad, 112 * k, "projected final score vs actual", 28, lab, ink, alpha=0.6)
        last = shown[-1]
        text(pad, 170 * k, f"{last['score']}/{last['wkts']}", 250, num, a1)
        text(pad + 20 * k, 480 * k, f"after over {last['over']}" if last is not pts[-1] else "final score", 30, lab, ink, alpha=0.7)
        top, bot = 560 * k, h - 190 * k
        ax = fig.add_axes([ax_l / w, 1 - bot / h, (w - pad - ax_l) / w, (bot - top) / h])
        ax.patch.set_alpha(0)
        hi = max(max(r["score"], r.get("proj_p90", 0)) for r in pts)
        ax.set_xlim(0, n_over), ax.set_ylim(0, hi * 1.05)
        pj = [r for r in shown if "proj" in r]
        if pj:
            xs = [r["over"] for r in pj]
            ax.fill_between(xs, [r["proj_p10"] for r in pj], [r["proj_p90"] for r in pj], color=_alpha(a1, 0.25), lw=0)
            ax.plot(xs, [r["proj"] for r in pj], color=a2, lw=5 * k, ls=(0, (4, 3)))
        if inn == 2 and meta["target"]:
            ax.axhline(meta["target"], color=ink, lw=2 * k, ls=(0, (4, 4)), alpha=0.55)
            ax.annotate(f"TARGET {meta['target']}", (0.3, meta["target"]), xytext=(0, 8 * k), textcoords="offset points", color=ink,
                        fontproperties=lab, fontsize=26 * k * PX, alpha=0.8)
        ax.plot([r["over"] for r in shown], [r["score"] for r in shown], color=ink, lw=9 * k, solid_capstyle="round")
        xl = "OVERS"
    # shared axis styling: ink text, no box, plain over numbers
    ax.set_xticks(range(0, n_over + 1, 5))
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=ink, length=0, labelsize=28 * k * PX, pad=14 * k)
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_fontproperties(lab), t.set_fontsize(28 * k * PX), t.set_color(ink)
    text(w / 2, bot + 92 * k, xl, 24, lab, ink, "center", alpha=0.6)
    text(pad, h - 40 * k, f"Source: Cricsheet | data to {thru}", 22, lab, ink, va="bottom", alpha=0.6)
    text(pad, h - 12 * k, "model estimate" + (", trained on this match" if meta["in_sample"] else ""), 22, lab, ink, va="bottom", alpha=0.6)
    fig.savefig(png, dpi=100, transparent=True)
    plt.close(fig)
    return status


class Canvas:
    """A transparent figure of w x h pixels with the reel fonts: `text()` places text in pixels (y down), `axes()` makes a plot box.
    Shared by the match, scouting and wpa charts so every reel chart looks the same."""

    def __init__(self, w, h, pal=None, font_dir=None):
        self.w, self.h, self.pal = w, h, {**DEFAULT_PALETTE, **(pal or {})}
        self.k = min(w / 960, h / 980)
        self.num, self.lab, self.status = _fonts(font_dir)
        self.fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
        self.fig.patch.set_alpha(0)
        self.ov = self.fig.add_axes([0, 0, 1, 1])
        self.ov.set_xlim(0, w), self.ov.set_ylim(h, 0), self.ov.axis("off"), self.ov.patch.set_alpha(0)

    def text(self, x, y, s, size, font="lab", color=None, ha="left", va="top", alpha=1.0, **kw):
        """size in px at 960 wide; font 'num' (Big Shoulders) or 'lab' (IBM Plex Mono)."""
        self.ov.text(x, y, s, fontproperties=self.num if font == "num" else self.lab, fontsize=size * self.k * PX,
                     color=color or self.pal["ink"], ha=ha, va=va, alpha=alpha, **kw)

    def axes(self, l, t, r, b):
        """Plot box with pixel edges (left, top, right, bottom); no frame, no ticks."""
        ax = self.fig.add_axes([l / self.w, 1 - b / self.h, (r - l) / self.w, (b - t) / self.h])
        ax.patch.set_alpha(0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0, colors=self.pal["ink"])
        return ax

    def style_ticks(self, ax, size=28):
        for t in ax.get_xticklabels() + ax.get_yticklabels():
            t.set_fontproperties(self.lab), t.set_fontsize(size * self.k * PX), t.set_color(self.pal["ink"])

    def save(self, png):
        Path(png).parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(png, dpi=100, transparent=True)
        plt.close(self.fig)
        return self.status
