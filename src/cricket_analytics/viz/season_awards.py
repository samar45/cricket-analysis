"""Figure for the `season_awards` module: top players of the latest 3 seasons, one phase at a time (buttons)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, style

_MEDALS = ["#FFD700", "#C0C0C0", "#CD7F32", PALETTE["primary"], PALETTE["primary"]]


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players matched")
    bat = "runs" in d.columns
    metric, extra, extra_name = ("runs", "strike_rate", "SR") if bat else ("wickets", "economy", "econ")
    phases = list(d.phase.unique()) if "phase" in d.columns else [None]
    multi_comp = d.competition.nunique() > 1
    d = d.assign(label=d.competition + " " + d.season.astype(str) if multi_comp else d.season.astype(str))
    seasons = list(dict.fromkeys(d.label))[:3]       # rows come newest season first
    sub_max = d[d.label.isin(seasons)][metric].max()
    fig = go.Figure()
    for p in phases:
        sub = d[d.label.isin(seasons)] if p is None else d[d.label.isin(seasons) & (d.phase == p)]
        fig.add_bar(name=str(p), y=[sub.label, sub.player], x=sub[metric], orientation="h", showlegend=False,
                    marker_color=[_MEDALS[min(int(r) - 1, 4)] for r in sub["rank"]],
                    text=[f"{m}  ({extra_name} {e})" for m, e in zip(sub[metric], sub[extra])], textposition="outside",
                    cliponaxis=False, visible=p is phases[0])
    fig.update_xaxes(title_text=metric.capitalize(), range=[0, sub_max * 1.4])
    fig.update_yaxes(autorange="reversed")
    if len(phases) > 1:   # one panel, a button per phase
        fig.update_layout(updatemenus=[dict(
            type="buttons", direction="right", x=0, xanchor="left", y=1.0, yanchor="bottom", showactive=True,
            bgcolor="#C9D1DC", bordercolor="#C9D1DC", font=dict(color="#0F131A", size=12),
            buttons=[dict(label=str(p).capitalize(), method="update", args=[{"visible": [q is p for q in phases]}])
                     for p in phases])])
    first = phases[0]
    n = len(d[d.label.isin(seasons) & ((d.phase == first) if first else True)])
    return style(fig, f"Top {'batters' if bat else 'bowlers'}, " + (f"latest {len(seasons)} seasons" if len(seasons) > 1 else seasons[0]), result,
                 note="gold / silver / bronze = rank" + ("; use the buttons to switch phase" if len(phases) > 1 else ""),
                 height=bars_height(n, 28, 200))
