"""Figure for the `death_overs` module (batting or bowling, told apart by the columns)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, style


def figure(result) -> go.Figure:
    d = result.data
    bat = "batter" in d.columns
    who, a, b, name, unit = (("batter", "overall_sr", "death_sr", "Strike rate", "runs per 100 balls") if bat
                             else ("bowler", "overall_economy", "death_economy", "Economy", "runs per over"))
    top = d.head(15).sort_values("death_index")      # ascending: the biggest index ends up at the top
    fig = go.Figure()
    for r in top.itertuples():
        better = r.death_index >= 100                 # index is built so that >= 100 always means "better at the death"
        c = PALETTE["good"] if better else PALETTE["bad"]
        fig.add_scatter(x=[getattr(r, a), getattr(r, b)], y=[getattr(r, who)] * 2, mode="lines+markers", showlegend=False,
                        line=dict(color=c, width=3), marker=dict(size=[8, 12], color=c, symbol=["circle", "diamond"], line=dict(width=0)),
                        hovertemplate=f"<b>{getattr(r, who)}</b><br>overall {getattr(r, a)}, death {getattr(r, b)}"
                                      f"<br>index {r.death_index}<extra></extra>")
    for label, symbol in (("Overall", "circle"), ("Death overs", "diamond")):   # legend keys only
        fig.add_scatter(x=[None], y=[None], mode="markers", name=label,
                        marker=dict(size=10, color=PALETTE["neutral"], symbol=symbol))
    fig.update_xaxes(title_text=f"{name} ({unit})")
    return style(fig, f"Death overs vs overall {name.lower()}: top {len(top)} by index", result,
                 note="green = better at the death, red = worse; index 100 = same as overall",
                 height=bars_height(len(top)))
