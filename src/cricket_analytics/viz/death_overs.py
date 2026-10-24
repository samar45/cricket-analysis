"""Figure for the `death_overs` module (batting or bowling, told apart by the columns)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, subtitle


def figure(result) -> go.Figure:
    d = result.data
    bat = "batter" in d.columns
    who, a, b, name = (("batter", "overall_sr", "death_sr", "strike rate") if bat
                       else ("bowler", "overall_economy", "death_economy", "economy"))
    top = d.head(15)
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Death-overs index (100 = same as overall)", f"Overall vs death {name}"])
    s = top.sort_values("death_index")
    fig.add_bar(y=s[who], x=s.death_index, orientation="h", showlegend=False, text=s.death_index, textposition="outside",
                marker_color=[PALETTE["good"] if v >= 100 else PALETTE["bad"] for v in s.death_index], row=1, col=1)
    fig.add_vline(x=100, line_dash="dash", line_color=PALETTE["neutral"], row=1, col=1)
    for r in top.itertuples():
        better = (getattr(r, b) >= getattr(r, a)) if bat else (getattr(r, b) <= getattr(r, a))
        c = PALETTE["good"] if better else PALETTE["bad"]
        fig.add_scatter(x=[getattr(r, a), getattr(r, b)], y=[getattr(r, who)] * 2, mode="lines+markers", showlegend=False,
                        line=dict(color=c, width=2.5), marker=dict(size=[7, 11], color=c, symbol=["circle", "diamond"]),
                        row=1, col=2)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    fig.update_xaxes(title_text="Index", row=1, col=1)
    fig.update_xaxes(title_text=f"{name.capitalize()} (circle = overall, diamond = death)", row=1, col=2)
    fig.update_layout(title=f"Death-overs index ({subtitle(result)})", height=max(500, len(top) * 32))
    return fig
