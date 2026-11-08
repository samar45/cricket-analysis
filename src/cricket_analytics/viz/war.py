"""Figure for the `war` module: top player-seasons by WAR (view=season) or by projected WAR for IPL 2027 (view=projected)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15


def _err(t, val) -> dict:
    """10-90% range as error bars (war module, v3: war_lo / war_hi, main_war_lo / main_war_hi)."""
    lo, hi = f"{val}_lo", f"{val}_hi"
    if lo not in t or t[lo].isna().any():
        return {}
    return dict(error_x=dict(type="data", symmetric=False, array=(t[hi] - t[val]).clip(lower=0), arrayminus=(t[val] - t[lo]).clip(lower=0), thickness=1.5, width=3))


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players for these filters")
    proj = "ipl_balls_2023_on" in d.columns
    val = next(c for c in ("pwar", "bat_pwar", "bowl_pwar", "main_war", "war") if c in d.columns)
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
            text=[f"{v:+.2f}" for v in t[val]],  # the text sits right of the bar end; the range is in the error bar
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:+.2f} wins<extra></extra>",
            **_err(t, val),
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
        else "bars: 10-90% range over his own matches; about 100 runs added = one win in 2023+",
        height=bars_height(len(t)),
    )
