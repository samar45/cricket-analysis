"""Figure for the `scarcity` module: scarcity index per role (bars), or purse left per team (view=team_needs)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, style


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No scarcity data")
    if "role" not in d.columns:  # team_needs
        t = d.sort_values("purse_left_cr")
        fig = go.Figure(
            go.Bar(
                x=t.purse_left_cr,
                y=t.team,
                orientation="h",
                marker_color=PALETTE["primary"],
                customdata=t[["open_spots", "need_total_raw"]].values,
                hovertemplate="%{y}: %{x:.1f} cr left, %{customdata[0]} open places, %{customdata[1]:.0f} weak slots<extra></extra>",
            )
        )
        fig.update_xaxes(title_text="Purse left before the auction (crore)")
        return style(
            fig, "Teams before the auction: purse left", result, height=bars_height(len(t))
        )
    col = "scarcity_index" if "scarcity_index" in d.columns else "index"
    t = d.sort_values(col)
    fig = go.Figure(
        go.Bar(
            x=t[col],
            y=t.role,
            orientation="h",
            marker_color=PALETTE["secondary"],
            text=[f"{x:.2f}" for x in t[col]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: index %{x:.2f}<extra></extra>",
        )
    )
    fig.update_xaxes(
        title_text="Scarcity index (purse-weighted demand per quality player on the block + 1)"
    )
    fig.update_layout(margin_r=60)
    return style(
        fig,
        "Scarcity by role",
        result,
        note="higher = more teams chasing fewer good players",
        height=bars_height(len(t)),
    )
