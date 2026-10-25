"""Plotly figures, one file per module: `viz/<module_id>.py` has `figure(result) -> go.Figure`.

Only the dashboard imports this package. Importing it registers the one shared plotly template
("cricket") and makes it the default, so every figure gets the same dark-theme look:
transparent background, one font, PALETTE colours, a horizontal legend under the plot.

House rules for a figure (so charts stay readable at ~700 px wide):
- one or two panels; two panels are stacked (rows), never side by side
- at most ~15 bars/points, and the title says "top N by ..."
- bubbles go through `bubble()`, text labels only on the first few points
- axis titles carry the unit (runs, strike rate = runs per 100 balls, economy = runs per over)
- finish with `style(fig, title, result, note=...)`
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from .. import competitions

PALETTE = {
    "primary": "#2196F3",  # main series (runs, wickets)
    "secondary": "#FF9800",  # rolling average / second series
    "good": "#4CAF50",  # not out, wins, fours
    "bad": "#EF5350",  # out, losses, sixes
    "neutral": "#9E9E9E",  # dots, no result
    "light": "#90CAF9",
    "accent": "#E91E63",
    "phases": ["#2196F3", "#FF9800", "#F44336"],  # powerplay, middle, death
}

_TEXT, _MUTED, _GRID = "#E6EAF0", "#9AA4B2", "rgba(255,255,255,0.09)"
_AXIS = dict(
    automargin=True,
    gridcolor=_GRID,
    zerolinecolor=_GRID,
    linecolor=_GRID,
    title_standoff=8,
    title_font=dict(size=13),
)

pio.templates["cricket"] = go.layout.Template(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Source Sans Pro, sans-serif", size=13, color=_TEXT),
        colorway=[
            PALETTE[k]
            for k in ("primary", "secondary", "good", "bad", "accent", "light", "neutral")
        ],
        height=450,
        margin=dict(l=16, r=24, t=24, b=40),
        title=dict(
            x=0,
            xanchor="left",
            automargin=True,
            pad=dict(b=14),
            font=dict(size=18),
            subtitle=dict(font=dict(size=12, color=_MUTED)),
        ),
        # legend sits in the bottom margin, whatever the figure height is
        legend=dict(
            orientation="h",
            yref="container",
            y=0,
            yanchor="bottom",
            x=0.5,
            xanchor="center",
            title_text="",
            traceorder="normal",
        ),
        xaxis=_AXIS,
        yaxis=_AXIS,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(gridcolor=_GRID),
            angularaxis=dict(gridcolor=_GRID),
        ),
        annotationdefaults=dict(font=dict(size=13, color=_TEXT)),
        hoverlabel=dict(font_size=12),
    )
)
pio.templates.default = "plotly_dark+cricket"

_FILTERS = ("competition", "season", "team", "opposition", "venue", "phase", "player", "player2")


def subtitle(result) -> str:
    """'IPL, 2024, V Kohli': only the data filters the module ran with (no group_by / weights / flags).
    Without a competition filter it says so, so a chart never looks scope-less."""
    p = result.meta["params"]
    parts = [
        str(p[k]) for k in _FILTERS if p.get(k) not in (None, "") and not isinstance(p[k], bool)
    ]
    comp = p.get("competition")
    if comp in competitions.COMPETITIONS:
        parts[0] = competitions.COMPETITIONS[comp].label
    else:
        parts.insert(0, "All competitions (men's)")
    return ", ".join(parts)


def style(
    fig: go.Figure, title: str, result=None, note: str = "", height: int | None = None
) -> go.Figure:
    """Set the title (+ the filters as a grey subtitle line, + `note`), the height, and room for the legend."""
    sub = " | ".join(s for s in (subtitle(result) if result is not None else "", note) if s)
    fig.update_layout(title=dict(text=title, subtitle=dict(text=sub)))
    if height:
        fig.update_layout(height=height)
    if sum(t.showlegend is not False and bool(t.name) for t in fig.data) > 1:
        fig.update_layout(margin_b=80)  # the legend lives in the bottom margin
    return fig


def empty(message: str) -> go.Figure:
    """A figure that just says why there is nothing to draw."""
    fig = go.Figure().update_layout(title=message, height=240)
    return fig.update_xaxes(visible=False).update_yaxes(visible=False)


def bubble(sizes, max_px: int = 36, min_px: int = 6) -> dict:
    """Marker settings for sized dots: area proportional to `sizes`, the biggest dot is `max_px` wide."""
    s = pd.Series(sizes).astype(float).fillna(0)
    return dict(size=s, sizemode="area", sizeref=2 * max(s.max(), 1.0) / max_px**2, sizemin=min_px)


def labels(names, n: int = 5) -> list[str]:
    """Text for scatter points: the name for the first `n` (rows are sorted by importance), blank for the rest."""
    return [str(x) if i < n else "" for i, x in enumerate(names)]


def short(text: str, n: int = 24) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def bars_height(n: int, per: int = 26, extra: int = 170) -> int:
    """Height in px for a horizontal bar panel with n bars."""
    return max(300, extra + per * n)
