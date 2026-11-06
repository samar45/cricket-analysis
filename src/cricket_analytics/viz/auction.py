"""Figure for the `auction` module: predicted price range vs paid (view=predict), WAR per 10 crore with ranges (view=market)."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("Nothing to show for these filters")
    if "war_per_10cr" in d.columns:
        key = d.columns[0]
        t = d.iloc[::-1]
        fig = go.Figure(
            go.Bar(
                x=t.war_per_10cr,
                y=[f"{short(str(g), 28)} (n={n})" for g, n in zip(t[key], t.players)],
                orientation="h",
                marker_color=[
                    PALETTE["good"] if v >= 0 else PALETTE["bad"] for v in t.war_per_10cr
                ],
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=t.hi - t.war_per_10cr,
                    arrayminus=t.war_per_10cr - t.lo,
                ),
                hovertemplate="%{y}: %{x:+.3f} WAR per 10 cr<extra></extra>",
            )
        )
        fig.update_xaxes(title_text="Wins above replacement per 10 crore spent (bars: 95% range)")
        return style(
            fig,
            "Which buys paid off",
            result,
            note="one season of WAR after the auction; mostly luck",
            height=bars_height(len(t)),
        )
    if "auction" not in d.columns:
        t = d.head(TOP).iloc[::-1]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=t.p50_cr,
                y=t.player,
                mode="markers",
                name="model median",
                marker=dict(color=PALETTE["primary"], size=10),
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=t.p90_cr - t.p50_cr,
                    arrayminus=t.p50_cr - t.p10_cr,
                ),
            )
        )
        paid = t[t.paid_cr.notna()]
        fig.add_trace(
            go.Scatter(
                x=paid.paid_cr,
                y=paid.player,
                mode="markers",
                name="paid",
                marker=dict(color=PALETTE["secondary"], size=11, symbol="diamond"),
            )
        )
        fig.update_xaxes(title_text="Price, crore (bars: 10th to 90th percentile)")
        return style(
            fig,
            f"Top {len(t)} by model median price",
            result,
            note="every row predicted from information before the auction",
            height=bars_height(len(t)),
        )
    t = d.iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=t.p50_cr,
            y=[f"{short(p, 18)} {a}" for p, a in zip(t.player, t.auction)],
            orientation="h",
            marker_color=PALETTE["primary"],
        )
    )
    fig.update_xaxes(title_text="Model median price, crore")
    return style(fig, "Player estimate", result, height=bars_height(len(t)))
