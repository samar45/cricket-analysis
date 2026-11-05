"""Figures for the `wpa` module: a leaderboard of WPA totals, or (view=match) the win-probability curve of one match."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No WPA for these filters (needs 6-ball T20 matches with a result)")
    return _curve(result, d) if "wp_bat_first" in d.columns else _board(result, d)


def _board(result, d) -> go.Figure:
    bat = "batter" in d.columns
    who = "batter" if bat else "bowler"
    t = d.head(TOP)
    raw = (
        [f"{r.runs} runs, SR {r.strike_rate}" for r in t.itertuples()]
        if bat
        else [f"{r.wickets} wkts, econ {r.economy}" for r in t.itertuples()]
    )
    fig = go.Figure(
        go.Bar(
            y=[short(x, 22) for x in t[who]],
            x=t.wpa_total,
            orientation="h",
            marker_color=[PALETTE["good"] if v >= 0 else PALETTE["bad"] for v in t.wpa_total],
            text=[f"{v:+.2f}  ({r})" for v, r in zip(t.wpa_total, raw)],
            textposition="outside",
            cliponaxis=False,
            customdata=t[["matches", "wpa_per_match"]],
            hovertemplate="%{y}: %{x:+.2f} over %{customdata[0]} matches (%{customdata[1]:+.3f} per match)<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title_text="Win Probability Added (1.0 = one whole win's worth of chance)")
    return style(
        fig,
        f"Win Probability Added: top {len(t)} {'batters' if bat else 'bowlers'}",
        result,
        note="our own win-probability model",
        height=bars_height(len(t)),
    )


def _curve(result, d) -> go.Figure:
    first, chase = d.bat_first.iloc[0], d.chasing_team.iloc[0]
    x0 = [0] + list(d.ball_no)
    y0 = [d.wp_bf_before.iloc[0]] + list(d.wp_bat_first)
    fig = go.Figure(
        go.Scatter(
            x=x0,
            y=y0,
            mode="lines",
            line=dict(color=PALETTE["primary"], width=3),
            name=first,
            hovertemplate="ball %{x}: %{y:.0%} <extra></extra>",
        )
    )
    fig.add_hline(y=0.5, line=dict(color=PALETTE["neutral"], dash="dot", width=1))
    n1 = int((d.innings == 1).sum())
    fig.add_vline(
        x=n1,
        line=dict(color=PALETTE["neutral"], dash="dash", width=1),
        annotation_text="innings break",
    )
    for r in d[d.swing_rank > 0].sort_values("swing_rank").itertuples():
        fig.add_annotation(
            x=r.ball_no,
            y=r.wp_bat_first,
            text=f"{r.swing_rank}. {short(r.batter, 14)} v {short(r.bowler, 14)}: {r.event} ({r.swing:+.0%})",
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-40 if r.swing_rank % 2 else 40,
            font=dict(size=11),
        )
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title_text=f"{first} win probability")
    fig.update_xaxes(title_text="Ball of the match (innings 1, then innings 2)")
    won = d.winner.iloc[0]
    return style(
        fig,
        f"{first} v {chase}: win probability, ball by ball",
        None,
        note=f"{d.date.iloc[0]:%d %b %Y} | won by {won if won == won and won else 'nobody (tie / no result)'} | 5 biggest swings marked",
        height=480,
    )
