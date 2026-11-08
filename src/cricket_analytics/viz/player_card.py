"""Figure for `player_card`: the player's percentile on each kept worth metric."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, style


def figure(result) -> go.Figure:
    t = result.data.query("section == 'worth'").iloc[::-1]
    if t.empty:
        return empty("No worth metrics for this player and scope")
    fig = go.Figure(go.Bar(x=t.pctile, y=list(t.label), orientation="h", marker_color=[PALETTE["good"] if x >= 50 else PALETTE["bad"] for x in t.pctile],
                           text=[f"{v:.1f} ({int(n)} balls)" for v, n in zip(t.value, t.n)], textposition="outside"))
    fig.add_vline(x=50, line_dash="dot")
    fig.update_xaxes(title_text="Percentile among peers (100 = best)", range=[0, 100])
    fig.update_layout(margin_r=150)
    tags = ", ".join(result.data.query("section == 'header' and label == 'tag'").text.str.split(": ").str[-1])
    return style(fig, "Player card: worth metrics" + (f" ({tags})" if tags else ""), result, height=bars_height(len(t)))
