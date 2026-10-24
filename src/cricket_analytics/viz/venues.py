"""Venue figures. Input: api.Result from run('venues', ...)."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import bubble, empty, labels, short, style


def figure(result):
    df = result.data
    if df.empty:
        return empty("No venue data for these filters")
    if "season" in df.columns:   # one row per venue x season: average over venues, weighted by matches
        df = df.assign(x=df["competition"] + " " + df["season"] if df["competition"].nunique() > 1 else df["season"])
        g = df.groupby("x", sort=False)
        w = lambda c: g.apply(lambda s: (s[c] * s["matches"]).sum() / s["matches"].sum(), include_groups=False)  # noqa: E731
        first, second = w("avg_1st_innings").round(1), w("avg_2nd_innings").round(1)
        fig = go.Figure()
        fig.add_scatter(x=first.index, y=first, name="1st innings", mode="lines+markers", line=dict(color=C["primary"]))
        fig.add_scatter(x=second.index, y=second, name="2nd innings", mode="lines+markers", line=dict(color=C["secondary"]))
        fig.update_xaxes(type="category", tickangle=-45)
        fig.update_yaxes(title_text="Average innings score (runs)")
        return style(fig, "Average score by season", result, note="all venues, weighted by matches played")
    top = df.head(15)
    fig = go.Figure(go.Scatter(
        x=top["avg_1st_innings"], y=top["bat_first_win_pct"], mode="markers+text", showlegend=False,
        marker=dict(**bubble(top["matches"]), color=C["primary"], opacity=0.75, line=dict(width=1, color="#0F131A")),
        text=labels([short(v, 20) for v in top["venue"]], 5), textposition="top center", textfont=dict(size=11),
        customdata=top[["venue", "matches"]].values,
        hovertemplate="<b>%{customdata[0]}</b><br>average 1st innings %{x}<br>bat-first win %{y}%"
                      "<br>%{customdata[1]} matches<extra></extra>"))
    fig.add_hline(y=50, line_dash="dash", line_color=C["neutral"], annotation_text="even", annotation_position="bottom right")
    fig.update_xaxes(title_text="Average 1st-innings score (runs)")
    fig.update_yaxes(title_text="Bat-first win %")
    return style(fig, f"Venues: top {len(top)} by matches played", result, note="dot size = matches", height=500)
