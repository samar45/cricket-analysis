"""Figure for `player_worth`: a player's percentile on each kept metric, a leaderboard, or the best match performances."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players with enough balls for these filters")
    if "runs_vs_match" in d.columns:
        who = "batter" if "batter" in d.columns else "bowler"
        t = d.head(15).iloc[::-1]
        fig = go.Figure(
            go.Bar(
                x=t.runs_vs_match,
                y=[f"{short(a, 16)} v {short(b, 14)}" for a, b in zip(t[who], t.opposition)],
                orientation="h",
                marker_color=PALETTE["good"],
                text=[f"{r} off {b}, {w} wk" for r, b, w in zip(t.runs, t.balls, t.wickets)],
                textposition="outside",
            )
        )
        fig.update_xaxes(title_text="Runs above (batting) / saved against (bowling) the rest of the same match")
        fig.update_layout(margin_r=140)
        return style(fig, "Best performances against the match", result, height=bars_height(len(t)))
    if "metric" not in d.columns:
        t = d.head(15).iloc[::-1]
        fig = go.Figure(go.Bar(x=t.avg_pctile, y=[short(x, 20) for x in t.player], orientation="h", marker_color=PALETTE["good"]))
        fig.update_xaxes(title_text="Average percentile on the kept metrics", range=[0, 100])
        return style(fig, "Player worth: best average percentile", result, height=bars_height(len(t)))
    t = d.iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=t.pctile,
            y=list(t.metric),
            orientation="h",
            marker_color=[PALETTE["good"] if x >= 50 else PALETTE["bad"] for x in t.pctile],
            text=[f"{v:.1f} ({int(n)} balls)" for v, n in zip(t.value, t.n)],
            textposition="outside",
        )
    )
    fig.add_vline(x=50, line_dash="dot")
    fig.update_xaxes(title_text="Percentile among peers (100 = best)", range=[0, 100])
    fig.update_layout(margin_r=150)
    return style(fig, f"{t.player.iloc[0]}: worth profile", result, height=bars_height(len(t)))
