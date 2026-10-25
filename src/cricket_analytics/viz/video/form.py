"""Form for video: a plain line of the last 15 innings (batters: runs; bowlers: economy per spell) with a dashed
average line, every point labelled. The last innings is the amber dot."""

from . import AMBER, INK, MUTE, _text, message_card, new_fig, num, scope_text, source_note

N = 15


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Form", "No innings for these filters", note)
    bat = "runs" in df.columns
    col = "runs" if bat else "economy"
    d = df.tail(N)
    who = result.meta["params"].get("player", "")
    # the plain mean of the shown values: easier to read than a not-out-aware average
    avg = float(d[col].mean())
    n = len(d)
    title = f"{who}: last {n} {'innings' if bat else 'spells'}" if who else f"Last {n}"
    sub = f"{'runs' if bat else 'economy, runs per over'} | {scope_text(result)}"
    fig, fr = new_fig(aspect, title, sub, note, pad_bottom=50)
    xs, ys = list(range(n)), [float(v) for v in d[col]]
    fig.add_scatter(
        x=xs,
        y=ys,
        mode="lines+markers+text",
        line=dict(color=INK, width=8),
        marker=dict(
            size=[34 if i == n - 1 else 22 for i in xs],
            color=[AMBER if i == n - 1 else INK for i in xs],
        ),
        text=[num(v, 0 if bat else 1) for v in ys],
        textposition="top center",
        cliponaxis=False,
        textfont=dict(size=36 if n <= 15 else 30, color=INK),
        hoverinfo="skip",
    )
    top = max(ys) * 1.22 or 1
    fig.add_shape(
        type="line",
        xref="x",
        yref="y",
        x0=-0.5,
        x1=n - 0.5,
        y0=avg,
        y1=avg,
        line=dict(color=AMBER, width=5, dash="dash"),
    )
    fig.update_xaxes(range=[-0.6, n - 0.4])
    fig.update_yaxes(range=[0, top])
    _text(
        fig,
        f"{n} INNINGS AGO" if bat else f"{n} SPELLS AGO",
        fr.px(fr.x0),
        fr.py(fr.y1 + 8),
        34,
        MUTE,
        "left",
        "top",
    )
    _text(fig, "LATEST", fr.px(fr.x1), fr.py(fr.y1 + 8), 34, AMBER, "right", "top")
    _text(
        fig,
        f"- - AVERAGE {num(avg, 1)}",
        fr.px((fr.x0 + fr.x1) / 2),
        fr.py(fr.y1 + 8),
        40,
        AMBER,
        "center",
        "top",
    )
    return fig
