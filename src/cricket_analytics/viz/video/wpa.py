"""WPA for video. Leaderboard: top 10 by Win Probability Added (bars). view=match: the win-probability curve of one match
with its biggest swing called out."""

import plotly.graph_objects as go

from . import (
    AMBER,
    INK,
    MUTE,
    hbars,
    message_card,
    new_fig,
    num,
    scope_text,
    short_name,
    source_note,
    wrap,
    _text,
)


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(
            aspect, "Win Probability Added", "No usable matches for these filters", note
        )
    if "wp_bat_first" in df.columns:
        return _curve(df, aspect, note)
    who = "batter" if "batter" in df.columns else "bowler"
    d = df.head(10 if aspect == "9:16" else 6)
    return hbars(
        [short_name(x) for x in d[who]],
        d["wpa_total"],
        "Biggest match-winners" if who == "batter" else "Best at turning games",
        aspect,
        f"win probability added (1.0 = one win) | {scope_text(result)}",
        note,
        fmt=lambda v: num(v, 2),
    )


def _curve(d, aspect, note):
    first, chase = d.bat_first.iloc[0], d.chasing_team.iloc[0]
    fig, fr = new_fig(aspect, f"{first} v {chase}", "win probability, ball by ball", note)
    n = len(d)
    xs = [0] + list(d.ball_no)
    ys = [d.wp_bf_before.iloc[0]] + list(d.wp_bat_first)
    fig.add_trace(
        go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=AMBER, width=10), hoverinfo="skip")
    )
    fig.add_hline(y=0.5, line=dict(color=MUTE, width=3, dash="dot"))
    fig.update_xaxes(range=[0, n * 1.0])
    fig.update_yaxes(range=[-0.12, 1.12])
    _text(fig, wrap(first, 40, fr.pw, 1), 0.02, 0.97, 40, INK, "left")
    _text(fig, wrap(chase, 40, fr.pw, 1), 0.02, 0.03, 40, INK, "left")
    top = d[d.swing_rank == 1]
    if len(top):
        r = top.iloc[0]
        fig.add_trace(
            go.Scatter(
                x=[r.ball_no],
                y=[r.wp_bat_first],
                mode="markers",
                marker=dict(size=34, color=INK, line=dict(color=AMBER, width=6)),
                hoverinfo="skip",
            )
        )
        above = r.wp_bat_first < 0.5
        _text(
            fig,
            wrap(f"{short_name(r.batter)} v {short_name(r.bowler)}: {r.event}", 44, fr.pw * 0.8, 3)
            + f"<br>{r.swing:+.0%}",
            0.5,
            0.78 if above else 0.22,
            44,
            INK,
        )
    return fig
