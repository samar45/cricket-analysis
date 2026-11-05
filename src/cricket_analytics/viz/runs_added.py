"""Figure for the `runs_added` module: top players by runs added (batting or bowling, told apart by the columns)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players with enough balls for these filters")
    bat = "batter" in d.columns
    who, rate, unit, raw = (
        ("batter", "runs_added_per_100_balls", "per 100 balls", "strike_rate")
        if bat
        else ("bowler", "runs_added_per_24_balls", "per 24 balls", "economy")
    )
    t = d.head(TOP).iloc[
        ::-1
    ]  # horizontal bars fill from the bottom: the best player ends up on top
    fig = go.Figure(
        go.Bar(
            x=t.runs_added,
            y=[short(x, 20) for x in t[who]],
            orientation="h",
            marker_color=[PALETTE["good"] if v >= 0 else PALETTE["bad"] for v in t.runs_added],
            text=[f"{r:+.1f} ({q:+.1f} {unit})" for r, q in zip(t.runs_added, t[rate])],
            textposition="outside",
            customdata=t[[raw]],
            hovertemplate="%{y}<br>runs added %{x:.1f}<br>"
            + raw.replace("_", " ")
            + " %{customdata[0]}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Runs added (above an average player in the same situation)")
    fig.update_layout(margin_r=120)
    return style(
        fig,
        f"Runs added: top {len(t)} {'batters' if bat else 'bowlers'}",
        result,
        note="0 = average for league, era and ground; chases and first innings",
        height=bars_height(len(t)),
    )
