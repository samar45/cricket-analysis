"""Video-ready charts for the Reels pipeline: `viz/video/<module_id>.py` has
`video_figure(result, aspect="9:16", focus=None) -> go.Figure`.

The dashboard charts (`viz/<module_id>.py`) are for reading on a laptop; these are for 1-2 seconds on a phone.
Rules (the "reel" template + the helpers below enforce them):
- ONE message per chart, and the title says it. A different chart type per feature, never one style for all.
- transparent background (the reel supplies the background), the reels' scoreboard colours, no gridlines,
  no legend (direct labels instead), no hover-only information (every number is printed on the chart).
- big type for a 1080 px wide phone frame: title 60 px, numbers 96-300 px, labels >= 34 px.
- 9:16 = 1080x1920 keeps the Instagram safe zone (nothing in the top 250 px or the bottom 420 px);
  1:1 = 1080x1080.
- Figures are 1080 px wide at 100 % scale; the plotly "scale" option only matters for PNG export.

Importing this package does not change plotly's default template; every figure sets the "reel" one itself.
"""

import importlib
import pkgutil
import textwrap
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

from ... import competitions

# House colours (Edit Pipeline "scoreboard" theme): cream ink, amber bulbs, red stamps. The chart sits on the
# reel's own dark background, so these only need to read on dark.
INK, AMBER, RED = "#f3efe4", "#ffb000", "#d7262e"
DARK = "#111111"                     # text on a cream/amber shape
MUTE = "rgba(243,239,228,0.55)"      # "the other bar"
FAINT = "rgba(243,239,228,0.28)"
SKY = "#6fb1d6"                      # 4th colour, only for donuts with 4 slices
SERIES = [AMBER, RED, INK, SKY]

FONT = "Impact, 'Arial Narrow', sans-serif"   # change here if the font installed for PNG export differs
TITLE, SUB, NOTE, LABEL = 60, 38, 30, 44      # px at 1080 wide

ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080)}

REEL = go.layout.Template(layout=dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=FONT, size=LABEL, color=INK),
    colorway=SERIES, showlegend=False, hovermode=False, dragmode=False, bargap=0.3,
    xaxis=dict(visible=False, showgrid=False, zeroline=False, fixedrange=True),
    yaxis=dict(visible=False, showgrid=False, zeroline=False, fixedrange=True),
))


# ── layout ───────────────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class Frame:
    """Pixel boxes of one figure. `x0..x1` / `y0..y1` is the plot area, between the title block and the footnote."""
    w: int
    h: int
    x0: int
    x1: int
    y0: int       # top of the plot area (below the title block)
    y1: int       # bottom of the plot area (above the footnote)
    note_y: int   # bottom edge of the footnote

    @property
    def pw(self) -> int:
        return self.x1 - self.x0

    @property
    def ph(self) -> int:
        return self.y1 - self.y0

    def px(self, x: float) -> float:   # figure pixel -> plotly "paper" fraction (paper = the plot area, not the figure)
        return (x - self.x0) / self.pw

    def py(self, y: float) -> float:
        return 1 - (y - self.y0) / self.ph


def wrap(text: str, size: int, width: int, max_lines: int = 2) -> str:
    """Upper-case, wrapped to `width` px for a condensed bold font (about 0.52 em per character)."""
    chars = max(8, int(width / (size * 0.52)))
    lines = textwrap.wrap(str(text).upper(), chars) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(1, chars - 1)].rstrip() + "…"
    return "<br>".join(lines)


def num(x, dec: int | None = None) -> str:
    """'9,336' for whole numbers, '134.8' for decimals (dec forces the digits)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "-"
    if dec is None:
        dec = 0 if float(x) == int(x) else (1 if abs(x) >= 100 else 2)
    return f"{x:,.{dec}f}"


def scope_text(result, skip=("player", "player2")) -> str:
    """'IPL 2024' / 'IPL, Mumbai Indians': the data filters, minus what the title already says."""
    p = result.meta["params"]
    comp = p.get("competition")
    parts = [competitions.COMPETITIONS[comp].label if comp in competitions.COMPETITIONS else "All men's T20"]
    for k in ("season", "team", "opposition", "venue", "phase"):
        v = p.get(k)
        if k not in skip and v not in (None, "", [], ()):
            parts.append(", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v))
    return " | ".join(parts)


def source_note(result) -> str:
    thru = str(result.meta.get("data_through", ""))[:10]
    return "Source: Cricsheet ball-by-ball" + (f" | data to {thru}" if thru else "")


def short_name(name: str) -> str:
    """'AB de Villiers' -> 'de Villiers', 'V Kohli' -> 'Kohli': drop leading initials (<= 3 capital letters)."""
    toks = str(name).split()
    while len(toks) > 1 and len(toks[0]) <= 3 and toks[0].isupper():
        toks = toks[1:]
    return " ".join(toks)


def short_names(names) -> list[str]:
    """short_name for each, falling back to the full name where two short names would collide."""
    s = [short_name(n) for n in names]
    return [x if s.count(x) == 1 else n for n, x in zip(names, s)]


def season_label(s) -> str:
    """'2024' -> '2024', '2007/08' -> '07/08' (Cricsheet's label; IPL 2008 is '2007/08')."""
    s = str(s)
    return s if len(s) == 4 else s[2:]


def new_fig(aspect: str, title: str, subtitle: str = "", note: str = "", pad_bottom: int = 0) -> tuple[go.Figure, Frame]:
    """A blank reel figure with the title block and footnote drawn. Returns (fig, frame of the plot area).
    pad_bottom = room under the plot for axis tick labels."""
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of {', '.join(ASPECTS)}, not {aspect!r}")
    w, h = ASPECTS[aspect]
    side = 60
    top, bottom_edge = (270, h - 420) if aspect == "9:16" else (50, h - 40)   # Instagram's UI covers the rest
    t = wrap(title, TITLE, w - 2 * side)
    s = wrap(subtitle, SUB, w - 2 * side) if subtitle else ""
    t_h = t.count("<br>") * 68 + 70 + 12
    s_h = (s.count("<br>") * 46 + 46 + 10) if s else 0
    note_y = bottom_edge
    fr = Frame(w, h, side, w - side, top + t_h + s_h + 30, note_y - NOTE - 24 - pad_bottom, note_y)
    fig = go.Figure(layout=dict(template=REEL, width=w, height=h,
                                margin=dict(l=fr.x0, r=w - fr.x1, t=fr.y0, b=h - fr.y1)))
    fig.add_annotation(text=t, x=fr.px(side), y=fr.py(top), xref="paper", yref="paper", xanchor="left",
                       yanchor="top", align="left", showarrow=False, font=dict(size=TITLE, color=INK))
    if s:
        fig.add_annotation(text=s, x=fr.px(side), y=fr.py(top + t_h), xref="paper", yref="paper", xanchor="left",
                           yanchor="top", align="left", showarrow=False, font=dict(size=SUB, color=AMBER))
    if note:
        fig.add_annotation(text=note, x=fr.px(side), y=fr.py(note_y), xref="paper", yref="paper", xanchor="left",
                           yanchor="bottom", align="left", showarrow=False, font=dict(size=NOTE, color=MUTE))
    return fig, fr


def _text(fig, text, x, y, size, color=INK, anchor="center", yanchor="middle"):
    """A text label at paper coordinates (fractions)."""
    fig.add_annotation(text=text, x=x, y=y, xref="paper", yref="paper", xanchor=anchor, yanchor=yanchor,
                       showarrow=False, align=anchor if anchor != "center" else "center", font=dict(size=size, color=color))


# ── chart kinds ──────────────────────────────────────────────────────────────────────────────────────────────

def message_card(aspect: str, title: str, message: str, note: str = "") -> go.Figure:
    """Shown instead of a chart when there is nothing to draw (still the right size, still transparent)."""
    fig, fr = new_fig(aspect, title, note=note)
    _text(fig, wrap(message, 64, fr.pw, 4), 0.5, fr.py((fr.y0 + fr.y1) / 2), 64, MUTE)
    return fig


def big_number_card(stats: list[tuple[str, str]], title: str, aspect: str = "9:16", subtitle: str = "",
                    note: str = "", colors: list[str] | None = None) -> go.Figure:
    """1-4 huge numbers with a label under each. `stats` = [("9,336", "IPL runs"), ...]. The first is amber.

    9:16 stacks them (one number per beat reads best); 1:1 stacks up to 3 and uses a 2x2 grid for 4."""
    stats = stats[:4]
    n = len(stats)
    fig, fr = new_fig(aspect, title, subtitle, note)
    cols = 2 if (aspect == "1:1" and n == 4) else 1
    rows = -(-n // cols)
    rh, cw = fr.ph / rows, fr.pw / cols
    colors = colors or [AMBER] + [INK] * 3
    for i, (value, label) in enumerate(stats):
        r, c = divmod(i, cols)
        top = fr.y0 + r * rh
        cx = fr.x0 + (c + 0.5) * cw
        size = int(min(rh * 0.60, 300, cw / (max(len(value), 2) * 0.50)))
        lsize = max(40, min(56, int(size * 0.30)))
        _text(fig, value, fr.px(cx), fr.py(top + rh * 0.40), size, colors[i % len(colors)])
        _text(fig, wrap(label, lsize, cw - 40, 1), fr.px(cx), fr.py(top + rh * 0.40 + size * 0.50 + lsize * 0.75), lsize, INK)
        if r < rows - 1:   # thin rule between rows
            y = fr.py(top + rh)
            fig.add_shape(type="line", xref="paper", yref="paper", x0=fr.px(fr.x0 + 40), x1=fr.px(fr.x1 - 40), y0=y, y1=y,
                          line=dict(color=FAINT, width=3))
    return fig


def columns(labels, values, title: str, aspect: str = "9:16", subtitle: str = "", note: str = "", fmt=num,
            highlight="max", suffix: str = "") -> go.Figure:
    """Vertical bars, label under each, value printed above. 2-3 bars get huge type; 10 bars still fit.

    highlight: 'max' | 'min' | list of indexes | None. The highlighted bars are amber, the rest muted cream."""
    n = len(values)
    fig, fr = new_fig(aspect, title, subtitle, note, pad_bottom=70)
    big = n <= 3
    vs, ls = (130, 56) if big else (64, 44) if n <= 6 else (44, 36)
    vals = [float(v) for v in values]
    if highlight == "max":
        hi = {max(range(n), key=vals.__getitem__)}
    elif highlight == "min":
        hi = {min(range(n), key=vals.__getitem__)}
    else:
        hi = set(highlight or [])
    fig.add_bar(x=list(range(n)), y=vals, marker_color=[AMBER if i in hi else MUTE for i in range(n)],
                text=[fmt(v) + suffix for v in vals], textposition="outside", cliponaxis=False,
                textfont=dict(size=vs, color=INK), hoverinfo="skip", width=0.62 if big else 0.7)
    fig.update_xaxes(visible=True, type="linear", tickmode="array", tickvals=list(range(n)),
                     ticktext=[str(x).upper() for x in labels], tickfont=dict(size=ls, color=INK), ticks="", showline=False,
                     range=[-0.55, n - 0.45], automargin=True)
    fig.update_yaxes(range=[0, max(max(vals), 1e-9) * (1.30 if big else 1.18)])
    return fig


def hbars(labels, values, title: str, aspect: str = "9:16", subtitle: str = "", note: str = "", fmt=num,
          highlight=(0,), suffix: str = "") -> go.Figure:
    """Horizontal leaderboard: the label sits above its bar (full width, so names never get cut), value at the bar end."""
    n = len(values)
    fig, fr = new_fig(aspect, title, subtitle, note)
    row = fr.ph / n
    ls = 44 if n <= 6 else 40
    vs = 60 if n <= 6 else 48
    bar = min(80, row * 0.42)
    vals = [float(v) for v in values]
    ymax = max(max(vals), 1e-9)
    ys = [i + 0.12 for i in range(n)]
    fig.add_bar(x=vals, y=ys, orientation="h", width=bar / row, hoverinfo="skip",
                marker_color=[AMBER if i in highlight else MUTE for i in range(n)],
                text=[fmt(v) + suffix for v in vals], textposition="outside", cliponaxis=False,
                textfont=dict(size=vs, color=INK))
    for i, lab in enumerate(labels):   # label sits just above its bar
        fig.add_annotation(text=str(lab).upper(), x=0, y=ys[i] - bar / row / 2 - 0.03, xref="x", yref="y",
                           xanchor="left", yanchor="bottom", showarrow=False, font=dict(size=ls, color=INK))
    fig.update_xaxes(range=[0, ymax * 1.28])
    fig.update_yaxes(range=[n - 0.5, -0.5])
    return fig


def donut(labels, values, title: str, aspect: str = "9:16", subtitle: str = "", note: str = "",
          center: tuple[str, str] | None = None, colors: list[str] | None = None) -> go.Figure:
    """Donut with the percentage inside each slice, a centre number, and a printed key under it (no legend)."""
    n = len(values)
    fig, fr = new_fig(aspect, title, subtitle, note)
    colors = (colors or SERIES)[:n]
    total = float(sum(values)) or 1.0
    pct = [v / total * 100 for v in values]
    key_h = 58 if n <= 4 else 50
    key_rows = n
    d = int(min(fr.pw, fr.ph - key_rows * key_h - 20))
    cx, cy = (fr.x0 + fr.x1) / 2, fr.y0 + d / 2
    dark_on = {AMBER, INK}
    fig.add_pie(labels=[str(x).upper() for x in labels], values=list(values), hole=0.56, sort=False, direction="clockwise",
                rotation=0, marker=dict(colors=colors, line=dict(color="rgba(0,0,0,0)", width=0)),
                text=[f"{p:.0f}%" if p >= 7 else "" for p in pct], textinfo="text", textposition="inside",
                insidetextorientation="horizontal", hoverinfo="skip",
                textfont=dict(size=58, color=[DARK if c in dark_on else INK for c in colors]),
                domain=dict(x=[fr.px(cx - d / 2), fr.px(cx + d / 2)], y=[fr.py(cy + d / 2), fr.py(cy - d / 2)]))
    if center:
        _text(fig, center[0], fr.px(cx), fr.py(cy - 50), 130 if len(center[0]) <= 4 else 96, AMBER)
        _text(fig, wrap(center[1], 42, d * 0.5, 2), fr.px(cx), fr.py(cy + 70), 42, INK)
    # printed key: coloured square + label + count, one row per slice
    kx0, ky0 = fr.x0 + 40, fr.y0 + d + 24
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = kx0
        y = ky0 + i * key_h + key_h / 2
        _text(fig, "■", fr.px(x), fr.py(y), 46, colors[i], "left")
        _text(fig, f"{str(lab).upper()}  {num(v)}  ({pct[i]:.0f}%)", fr.px(x + 56), fr.py(y), 42, INK, "left")
    return fig


def podium(names, values, title: str, aspect: str = "9:16", subtitle: str = "", note: str = "", unit: str = "",
           fmt=num) -> go.Figure:
    """Top 3 as a podium: 2nd | 1st | 3rd, steps of fixed height (the value is printed, the step shows only the rank)."""
    fig, fr = new_fig(aspect, title, subtitle, note)
    order = [1, 0, 2][: len(names)] if len(names) == 3 else list(range(len(names)))
    steps = {0: 1.0, 1: 0.74, 2: 0.55}
    name_room = 150
    h = fr.ph - name_room
    shades = {0: AMBER, 1: INK, 2: MUTE}
    for x, k in enumerate(order):
        fig.add_bar(x=[x], y=[steps[k] * h], width=0.94, marker_color=shades[k], hoverinfo="skip")
        top = fr.y1 - steps[k] * h
        cx = fr.x0 + (x + 0.5) * fr.pw / len(order)
        cw = fr.pw / len(order)
        _text(fig, wrap(names[k], 42, cw - 10, 2), fr.px(cx), fr.py(top - 14), 42, INK, yanchor="bottom")
        small = fr.ph < 900   # square format: shorter steps, smaller type
        _text(fig, str(k + 1), fr.px(cx), fr.py(top + (62 if small else 120)), 100 if small else 190, DARK)
        _text(fig, fmt(values[k]), fr.px(cx), fr.py(top + (150 if small else 270)),
              80 if small or len(fmt(values[k])) > 4 else 96, DARK)
        if unit:
            _text(fig, unit.upper(), fr.px(cx), fr.py(top + (205 if small else 340)), 38, DARK)
    fig.update_xaxes(range=[-0.5, len(order) - 0.5])
    fig.update_yaxes(range=[0, h + name_room])
    return fig


def butterfly(rows, names: tuple[str, str], title: str, aspect: str = "9:16", subtitle: str = "", note: str = "",
              ) -> go.Figure:
    """Mirrored bars. rows = [(label, left_value, right_value, lower_is_better, formatted_left, formatted_right)].
    Each row is scaled on its own (the longer side fills its half); the winner of the row is amber."""
    n = len(rows)
    fig, fr = new_fig(aspect, title, subtitle, note)
    head = 70
    row = (fr.ph - head) / n
    bar = min(70, row * 0.36)
    ys = [i + 0.2 for i in range(n)]
    left, right, lc, rc, lt, rt = [], [], [], [], [], []
    for lab, a, b, low, fa, fb in rows:
        m = max(abs(a), abs(b)) or 1
        a_wins = (a < b) if low else (a > b)
        tie = a == b
        left.append(-a / m)
        right.append(b / m)
        lc.append(AMBER if a_wins or tie else MUTE)
        rc.append(AMBER if (not a_wins) or tie else MUTE)
        lt.append(fa)
        rt.append(fb)
    kw = dict(orientation="h", width=bar / row, hoverinfo="skip", textposition="outside", cliponaxis=False,
              textfont=dict(size=52, color=INK))
    fig.add_bar(x=left, y=ys, marker_color=lc, text=lt, **kw)
    fig.add_bar(x=right, y=ys, marker_color=rc, text=rt, **kw)
    for i, r in enumerate(rows):
        fig.add_annotation(text=r[0].upper(), x=0, y=ys[i] - bar / row / 2 - 0.04, xref="x", yref="y", xanchor="center",
                           yanchor="bottom", showarrow=False, font=dict(size=40, color=MUTE))
    for side, nm in zip((-1, 1), names):   # player names over each half
        fig.add_annotation(text=wrap(nm, 56, fr.pw / 2 - 20, 1), x=side * 0.5 * 1.45, y=-0.5 - head / row * 0.6, xref="x", yref="y",
                           xanchor="center", yanchor="middle", showarrow=False, font=dict(size=56, color=INK))
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(range=[-1.45, 1.45])
    fig.update_yaxes(range=[n - 0.5, -0.5 - head / row])
    return fig


# ── registry ─────────────────────────────────────────────────────────────────────────────────────────────────

def module_ids() -> list[str]:
    """Modules that have a video chart (one file per module in this package)."""
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))


def video_figure(module_id: str, result, aspect: str = "9:16", focus: str | None = None) -> go.Figure:
    """The video chart for a module's `api.Result`. `focus` picks a sub-view (a metric, a player, a phase); see each file."""
    return importlib.import_module(f"{__name__}.{module_id}").video_figure(result, aspect, focus)
