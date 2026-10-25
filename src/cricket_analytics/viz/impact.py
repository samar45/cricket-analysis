"""Figure for the `impact` module: total impact (batting + bowling), then the per-match average for the same players."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, style


def figure(result) -> go.Figure:
    top = result.data.head(12)
    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.55, 0.45],
        vertical_spacing=0.14,
        subplot_titles=[
            "Total impact: batting + bowling points",
            "Average impact per match (same players)",
        ],
    )
    fig.add_bar(
        name="Batting points",
        y=top.player,
        x=top.bat_impact,
        orientation="h",
        marker_color=PALETTE["good"],
        row=1,
        col=1,
    )
    fig.add_bar(
        name="Bowling points",
        y=top.player,
        x=top.bowl_impact,
        orientation="h",
        marker_color=PALETTE["primary"],
        row=1,
        col=1,
    )
    fig.add_bar(
        y=top.player,
        x=top.avg_impact,
        orientation="h",
        marker_color=PALETTE["secondary"],
        showlegend=False,
        text=[f"{v:.1f}" for v in top.avg_impact],
        textposition="outside",
        cliponaxis=False,
        row=2,
        col=1,
    )
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Impact points", row=1, col=1)
    fig.update_xaxes(title_text="Points per match", row=2, col=1)
    fig.update_yaxes(autorange="reversed")
    return style(
        fig,
        f"Player impact: top {len(top)} by total points",
        result,
        height=170 + 2 * 26 * len(top) + 150,
    )
