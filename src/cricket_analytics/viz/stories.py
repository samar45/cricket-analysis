"""Figure for the `stories` module: hooks ranked by score, with the sentence behind each bar."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, style


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No hooks: not enough balls on both sides of any comparison")
    d = d.iloc[::-1]  # best on top
    fig = go.Figure(
        go.Bar(
            x=d["score"],
            y=[f"{r}. {t}" for r, t in zip(d["rank"], d["theme"])],
            orientation="h",
            marker_color=[
                PALETTE["accent"] if k == "record" else PALETTE["primary"] for k in d["kind"]
            ],
            text=d["metric"],
            textposition="auto",
            customdata=d["sentence"],
            hovertemplate="%{customdata}<br>score %{x}<extra></extra>",
        )
    )
    fig.update_layout(xaxis_title="score = relative gap x sample confidence (0-1)")
    who = result.meta["params"]["player"]
    return style(
        fig,
        f"{who}: story hooks, best first",
        result,
        note="hover a bar for the sentence; pink = record (no comparison)",
        height=bars_height(len(d), 34),
    )
