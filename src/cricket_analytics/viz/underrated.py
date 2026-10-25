"""Figure for the `underrated` module: quality vs obscurity, the top-right corner is the target."""

import plotly.graph_objects as go

from . import PALETTE, empty, labels, style


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players pass the minimum balls for these filters")
    fig = go.Figure(
        go.Scatter(
            x=d["obscurity"],
            y=d["quality"],
            mode="markers+text",
            text=labels(d["player"], 8),
            textposition="top center",
            marker=dict(size=12, color=PALETTE["secondary"]),
            customdata=d[["underrated_score", "matches", "fame_matches"]],
            hovertemplate="%{text}<br>score %{customdata[0]}<br>%{customdata[1]} matches in scope, "
            "%{customdata[2]} in the fame league<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis_title="Obscurity (1 = fewest matches)", yaxis_title="Quality (1 = best numbers)"
    )
    return style(
        fig,
        f"Underrated {result.meta['params']['role']}: top {len(d)} (heuristic)",
        result,
        note="score = 100 x quality x obscurity",
        height=560,
    )
