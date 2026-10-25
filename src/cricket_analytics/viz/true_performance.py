"""Figure for the `true_performance` module (batting or bowling, told apart by the columns)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, bars_height, style


def figure(result) -> go.Figure:
    d = result.data
    bat = "batter" in d.columns
    who, raw, true, k = (
        ("batter", "raw_sr", "true_sr", "sr")
        if bat
        else ("bowler", "raw_economy", "true_economy", "econ")
    )
    name, unit = ("Strike rate", "runs per 100 balls") if bat else ("Economy", "runs per over")
    top = d.head(15).iloc[::-1]  # dot plots fill from the bottom: the best player ends up on top
    t10 = d.head(10).iloc[::-1]
    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.13,
        subplot_titles=[
            f"Raw vs phase-adjusted {name.lower()}",
            f"{name} by phase (top {len(t10)})",
        ],
    )
    up_is_good = bat  # batting: a higher true value is a boost; bowling: a lower one is
    for r in top.itertuples():
        c = (
            PALETTE["good"]
            if (getattr(r, true) > getattr(r, raw)) == up_is_good
            else PALETTE["bad"]
        )
        fig.add_scatter(
            x=[getattr(r, raw), getattr(r, true)],
            y=[getattr(r, who)] * 2,
            mode="lines+markers",
            line=dict(color=c, width=3),
            marker=dict(size=[8, 12], color=c, symbol=["circle", "diamond"], line=dict(width=0)),
            showlegend=False,
            row=1,
            col=1,
        )
    for p, label, c in zip(
        ("powerplay", "middle", "death"), ("Powerplay", "Middle", "Death"), PALETTE["phases"]
    ):
        fig.add_scatter(
            name=label,
            y=t10[who],
            x=t10[f"{k}_{p}"],
            mode="markers",
            marker=dict(size=11, color=c),
            row=2,
            col=1,
        )
    fig.update_xaxes(title_text=f"{name} ({unit})", row=1, col=1)
    fig.update_xaxes(title_text=f"{name} ({unit})", row=2, col=1)
    return style(
        fig,
        f"True {name.lower()}, phase-adjusted: top {len(top)}",
        result,
        note="circle = raw, diamond = adjusted; green = boosted by the adjustment, red = lowered",
        height=bars_height(len(top), 24, 0) + bars_height(len(t10), 24, 0) + 330,
    )
