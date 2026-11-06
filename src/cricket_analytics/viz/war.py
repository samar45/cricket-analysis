"""Figure for the `war` module: top player-seasons by WAR (view=season) or by projected WAR for IPL 2027 (view=projected)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players for these filters")
    proj = "ipl_balls_2023_on" in d.columns
    val = next(c for c in ("pwar", "bat_pwar", "bowl_pwar", "war") if c in d.columns)
    t = d.head(TOP).iloc[::-1]  # horizontal bars fill from the bottom: the best ends up on top
    labels = [
        short(p, 18) if proj else f"{short(p, 18)} {s}"
        for p, s in zip(t.player, t.get("season", t.player))
    ]
    fig = go.Figure(
        go.Bar(
            x=t[val],
            y=labels,
            orientation="h",
            marker_color=[PALETTE["good"] if v >= 0 else PALETTE["bad"] for v in t[val]],
            text=[f"{v:+.2f}" for v in t[val]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:+.2f} wins<extra></extra>",
        )
    )
    fig.update_xaxes(
        title_text="Projected wins above replacement, IPL 2027"
        if proj
        else "Wins above replacement (1.0 = one win)"
    )
    fig.update_layout(margin_r=70)
    return style(
        fig,
        f"{'Projected WAR for IPL 2027' if proj else 'WAR'}: top {len(t)}",
        result,
        note="a prediction from earlier seasons, pulled toward the average"
        if proj
        else "about 100 runs added = one win in the 2023+ IPL",
        height=bars_height(len(t)),
    )
