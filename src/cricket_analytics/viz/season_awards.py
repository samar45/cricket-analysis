"""Figure for the `season_awards` module: one panel per (phase, season), latest 4 seasons."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE

_MEDALS = ["#FFD700", "#C0C0C0", "#CD7F32", PALETTE["primary"], PALETTE["primary"]]


def _filters(result) -> str:
    """'ipl, 2024' - only the data filters, not the module's own knobs (weights, award, ...)."""
    keep = ("player", "competition", "season", "team", "opposition", "venue", "phase")
    return ", ".join(str(v) for k, v in result.meta["params"].items() if k in keep)


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return go.Figure().update_layout(title="No players matched")
    bat = "runs" in d.columns
    metric, extra = ("runs", "strike_rate") if bat else ("wickets", "economy")
    phases = list(d.phase.unique()) if "phase" in d.columns else [None]
    seasons = list(d.drop_duplicates(["competition", "season"])[["competition", "season"]].itertuples(index=False))[:4]
    fig = make_subplots(rows=len(phases), cols=len(seasons), horizontal_spacing=0.12,
                        subplot_titles=[f"{s.season}" + (f" {p}" if p else "") for p in phases for s in seasons])
    for i, p in enumerate(phases, 1):
        for j, s in enumerate(seasons, 1):
            sub = d[(d.season == s.season) & (d.competition == s.competition)]
            if p:
                sub = sub[sub.phase == p]
            fig.add_bar(y=sub.player, x=sub[metric], orientation="h", showlegend=False, marker_color=_MEDALS[:len(sub)],
                        text=[f"{m} ({e})" for m, e in zip(sub[metric], sub[extra])], textposition="outside", row=i, col=j)
            fig.update_yaxes(autorange="reversed", row=i, col=j)
    fig.update_layout(title=f"Top {'batters' if bat else 'bowlers'} by season ({_filters(result)})",
                      height=max(350, 260 * len(phases)), margin=dict(r=90))
    return fig
