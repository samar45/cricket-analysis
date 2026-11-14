"""Reel PNGs for SMAT scouting: scout_innings (a player's innings in date order) and scout_rank (top 10 uncapped).
Transparent, 960x980 by default. palette = {bg, ink, a1, a2}: ink text, a1 highlight, a2 second series, bg text on a1 bars."""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from ..viz.video import AMBER, INK, MUTE, RED, num, short_name
from . import reels
from .smat2025 import ROOT

# Fonts: families are tried in order; TTFs live in Edit Pipeline/assets/fonts (not installed system-wide => fallback renders).
NUM_FONT = "Big Shoulders Stencil Display, Impact, 'Arial Narrow', sans-serif"
LAB_FONT = "IBM Plex Mono, Consolas, monospace"
DEFAULT = dict(bg="#111111", ink=INK, a1=AMBER, a2=RED)
CHARTS = ("scout_innings", "scout_rank")


def parse_palette(s: str | None) -> dict:
    p = {**DEFAULT, **(json.loads(s) if s else {})}
    bad = set(p) - set(DEFAULT)
    if bad:
        raise ValueError(f"palette keys must be bg, ink, a1, a2 (got {sorted(bad)})")
    return p


def parse_size(s: str | None) -> tuple[int, int]:
    try:
        return tuple(int(x) for x in s.lower().split("x")) if s else (960, 980)  # type: ignore
    except ValueError:
        raise ValueError(f"--size must look like 1080x1920, not {s!r}")


def _mute(c: str) -> str:
    return c if not c.startswith("#") or len(c) != 7 else f"rgba({int(c[1:3], 16)},{int(c[3:5], 16)},{int(c[5:7], 16)},0.55)"


def _base(w, h, pal, title, sub, big, big_label, note, bottom=70):
    """Header (title, subtitle, one big number) and footnote placed in pixels; returns (fig, txt) where txt(text, px_x, px_y, ...)."""
    k = w / 960
    mt, mb, mx = int(215 * k), int(bottom * k), int(40 * k)
    fig = go.Figure(layout=dict(width=w, height=h, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                font=dict(family=LAB_FONT, color=pal["ink"], size=30), showlegend=False, hovermode=False,
                                margin=dict(l=mx, r=mx, t=mt, b=mb), bargap=0.25))
    fig.update_xaxes(visible=False, fixedrange=True)
    fig.update_yaxes(visible=False, fixedrange=True)
    pw, ph = w - 2 * mx, h - mt - mb

    def txt(t, x, y, size, color, font, anchor="left", yanchor="top"):  # x, y = figure pixels
        fig.add_annotation(text=t, x=(x - mx) / pw, y=1 + (mt - y) / ph, xref="paper", yref="paper", xanchor=anchor,
                           yanchor=yanchor, showarrow=False, font=dict(size=int(size * k), color=color, family=font))
    txt(f"<b>{title.upper()}</b>", mx, 24, 46, pal["ink"], NUM_FONT)
    txt(sub, mx, 88, 28, pal["a1"], LAB_FONT)
    if big:
        txt(f"<b>{big}</b>", w - mx, 4, 120, pal["a1"], NUM_FONT, "right")
        txt(big_label, w - mx, 138, 24, _mute(pal["ink"]), LAB_FONT, "right")
    txt(note, mx, h - 14 * k, 20, _mute(pal["ink"]), LAB_FONT, "left", "bottom")
    return fig, txt


def innings(player: str, w=960, h=980, palette=None) -> go.Figure:
    pal = parse_palette(palette) if isinstance(palette, str) or palette is None else palette
    c = reels.resolve(player)
    role = c["role"]
    d = pd.read_parquet(ROOT / (("batting" if role == "bat" else "bowling") + ".parquet"))
    d = d[d.cricbuzz_id == c["cricbuzz_id"]].merge(reels._games()[["match_id", "date", "team1", "team2"]], on="match_id").sort_values("date")
    t = reels.table(role).set_index("cricbuzz_id").loc[c["cricbuzz_id"]]
    opp = [b if a == tm else a for a, b, tm in zip(d.team1, d.team2, d.team)]
    y = d.runs if role == "bat" else d.wickets
    best = int(y.values.argmax())
    if role == "bat":  # most runs, ties by strike rate (same rule as the facts file)
        best = list(d.index).index(d.assign(s=d.runs / d.balls.clip(lower=1)).sort_values(["runs", "s"]).index[-1])
    big = f"{int(t.runs)}" if role == "bat" else f"{int(t.wkts)}"
    lab = f"RUNS | SR {t.sr}" if role == "bat" else f"WICKETS | ECON {t.econ}"
    note = f"Source: Cricbuzz SMAT 2025-26 | data to {str(reels._games().date.max())[:10]}"
    fig, txt = _base(w, h, pal, c["name"], f"{t.team} | {'EVERY INNINGS' if role == 'bat' else 'EVERY SPELL'}", big, lab, note, bottom=110)
    x = list(range(len(d)))
    labels = [f"<b>{int(v)}</b>" for v in y]
    fig.add_bar(x=x, y=y, marker_color=[pal["a1"] if i == best else _mute(pal["ink"]) for i in x], text=labels, textposition="outside",
                textfont=dict(size=30, family=NUM_FONT, color=pal["ink"]), cliponaxis=False, width=0.7)
    for i, o in enumerate(opp):
        fig.add_annotation(text=short_name(o)[:3].upper(), x=i, y=0, yshift=-24, showarrow=False, font=dict(size=22, color=_mute(pal["ink"])))
    ymax = max(y.max(), 1) * 1.25
    if role == "bat":  # a league-average batter's runs off the same balls: dashed tick over each bar
        lg = reels.league()["sr"]
        for i, b in enumerate(d.balls):
            fig.add_shape(type="line", x0=i - 0.45, x1=i + 0.45, y0=lg * b / 100, y1=lg * b / 100, line=dict(color=pal["a2"], width=4, dash="dash"))
        ymax = max(ymax, max(lg * d.balls / 100) * 1.25)
        txt("- - average batter, same balls", 40 * w / 960, 130, 22, pal["a2"], LAB_FONT)
    fig.update_yaxes(range=[0, ymax])
    fig.update_xaxes(range=[-0.6, len(d) - 0.4])
    return fig


def rank(role: str, focus: str | None = None, w=960, h=980, palette=None, n: int = 10) -> go.Figure:
    pal = parse_palette(palette) if isinstance(palette, str) or palette is None else palette
    t = reels.table(role)
    t = t[t.t20i == "uncapped"]
    rows = t.head(n)
    big, lab = "", "RUNS ABOVE AVERAGE" if role == "bat" else "RUNS SAVED vs AVERAGE"
    f = None
    if focus:
        f = reels.resolve(focus)
        fr = t[t.cricbuzz_id == f["cricbuzz_id"]]
        if fr.empty:
            raise ValueError(f"{f['name']} is not in the uncapped {role} list")
        if f["cricbuzz_id"] not in set(rows.cricbuzz_id):
            rows = pd.concat([rows.head(n - 1), fr])
        big = f"#{int(fr.rank_uncapped.iloc[0])}"
    fig, _ = _base(w, h, pal, "Uncapped " + ("batters" if role == "bat" else "bowlers"), "SMAT 2025-26 | RANKED BY SCORE", big, f"OF {len(t)} UNCAPPED" if big else "", f"Source: Cricbuzz SMAT 2025-26 | {lab.lower()}")
    rows = rows.iloc[::-1]
    hl = [f is not None and i == f["cricbuzz_id"] for i in rows.cricbuzz_id]
    fig.add_bar(y=list(range(len(rows))), x=rows.score, orientation="h",
                marker_color=[pal["a1"] if x else _mute(pal["ink"]) for x in hl], text=[f"{num(v, 1)}" for v in rows.score], textposition="outside",
                textfont=dict(size=30, family=NUM_FONT, color=pal["ink"]), cliponaxis=False)
    for i, (r_, nm) in enumerate(zip(rows.rank_uncapped, rows["name"])):  # labels drawn by hand so the plot area stays aligned with the header
        fig.add_annotation(text=f"{int(r_)}. {short_name(nm)[:16]}", x=0.355, y=i, xref="paper", yref="y", xanchor="right", showarrow=False,
                           font=dict(size=26, family=LAB_FONT, color=pal["ink"]))
    fig.update_xaxes(domain=[0.36, 1])
    fig.update_xaxes(range=[0, rows.score.max() * 1.25])
    return fig


def render(chart: str, png: Path, size: str | None = None, palette: str | None = None, **kw):
    w, h = parse_size(size)
    pal = parse_palette(palette)
    if chart == "scout_innings":
        if not kw.get("player"):
            raise ValueError("scout_innings needs --player")
        fig = innings(kw["player"], w, h, pal)
    elif chart == "scout_rank":
        if kw.get("role") not in ("bat", "bowl"):
            raise ValueError("scout_rank needs --role bat|bowl")
        fig = rank(kw["role"], kw.get("focus"), w, h, pal)
    else:
        raise ValueError(f"unknown scouting chart {chart!r}; use {' or '.join(CHARTS)}")
    Path(png).parent.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(png), width=w, height=h, scale=1)
    return fig
