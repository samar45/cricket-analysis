"""Figure for the `trade` module: a before / after card for both teams (view=trade) or one squad's recent value with ranges (view=squad)."""

import textwrap
import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15
VERDICT_COLOUR = {
    "likely better": PALETTE["good"],
    "leans better": PALETTE["good"],
    "too close to call": PALETTE["neutral"],
    "no change to the best XII": PALETTE["neutral"],
    "leans worse": PALETTE["bad"],
    "likely worse": PALETTE["bad"],
}


def _squad(d) -> go.Figure:
    t = d.head(TOP).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=t.recent_value,
            y=[short(p, 20) for p in t.player],
            orientation="h",
            marker_color=[PALETTE["primary"] if x else PALETTE["neutral"] for x in t.in_best_xii],
            error_x=dict(
                type="data",
                symmetric=False,
                array=(t.range_hi - t.recent_value).clip(lower=0),
                arrayminus=(t.recent_value - t.range_lo).clip(lower=0),
                color="rgba(255,255,255,0.45)",
            ),
            text=[f"{v:+.2f}" for v in t.recent_value],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:+.2f} wins a season<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Recent value, wins above replacement a season (bar = best XII)")
    fig.update_layout(margin_r=70)
    return style(
        fig,
        f"Squad by recent value: top {len(t)}",
        None,
        note="whiskers = 10th-90th percentile; recent form, not a prediction",
        height=bars_height(len(t)),
    )


def _card(d) -> go.Figure:
    fig = go.Figure()
    fig.update_xaxes(visible=False, range=[0, 1]).update_yaxes(visible=False, range=[0, 1])
    n = len(d)
    for i, r in enumerate(d.itertuples()):
        x = (i + 0.5) / n
        colour = VERDICT_COLOUR.get(r.verdict, PALETTE["neutral"])
        lines = [
            f"<b>{r.team}</b>",
            f"gives: {r.gives}",
            f"gets: {r.gets}",
            "",
            f"Best XII value: <b>{r.xii_before:.2f}</b> to <b>{r.xii_after:.2f}</b>",
            f"range {r.before_lo:.2f} to {r.before_hi:.2f}  to  {r.after_lo:.2f} to {r.after_hi:.2f}",
            f"Change: <b>{r.change:+.2f}</b> ({r.change_lo:+.2f} to {r.change_hi:+.2f})",
            f"Squad salary: {r.squad_salary_before:.1f} to {r.squad_salary_after:.1f} cr "
            f"(purse {r.purse_freed_cr:+.1f} cr)",
            f"Net value of the swap: {r.net_value_cr:+.1f} cr",
            f"Value per crore: {r.value_per_cr_before:.3f} to {r.value_per_cr_after:.3f}",
            f"Weak slots created: {r.holes_created or 'none'}",
            f"Weak slots filled: {r.holes_filled or 'none'}",
        ]
        fig.add_annotation(
            x=x,
            y=0.97,
            xref="paper",
            yref="paper",
            xanchor="center",
            yanchor="top",
            text="<br>".join(lines),
            showarrow=False,
            align="left",
            font=dict(size=13),
        )
        fig.add_annotation(
            x=x,
            y=0.06,
            xref="paper",
            yref="paper",
            xanchor="center",
            yanchor="bottom",
            text="<b>"
            + "<br>".join(textwrap.wrap(r.verdict.upper(), 16))
            + "</b>",  # two cards sit side by side
            showarrow=False,
            font=dict(size=18, color=colour),
        )
    return fig


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No trade to show")
    if "verdict" not in d.columns:
        return _squad(d)
    fig = _card(d)
    return style(
        fig,
        "IPL trade check: best XII before and after",
        result,
        note="recent value, wins a season; not a forecast",
        height=500,
    )
