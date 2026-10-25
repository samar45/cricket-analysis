"""Figure for the `compare` module: radar of the overall numbers, then a per-phase bar panel below it."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, style

_COLORS = [PALETTE["primary"], PALETTE["bad"]]
_FILL = ["rgba(33,150,243,0.2)", "rgba(239,83,80,0.2)"]
_PHASES = ["powerplay", "middle", "death"]


def figure(result) -> go.Figure:
    d = result.data
    bat = "outs" in d.columns
    ov = d[d.scope == "overall"].set_index("player")
    present = [p for p in dict.fromkeys(d.player) if p in ov.index]
    # radar axes, all "higher = better"; each is scaled so the better of the two players = 100
    if bat:
        cats, phase_col, ylabel = (
            ["Average", "Strike rate", "Boundary %", "100 - dot %"],
            "strike_rate",
            "Strike rate (runs per 100 balls)",
        )
        raw = lambda r: [r.average, r.strike_rate, r.boundary_pct, 100 - r.dot_pct]  # noqa: E731
    else:
        cats, phase_col, ylabel = (
            ["Wickets / innings", "Dot %", "100 - boundary %", "100 - economy x 10"],
            "economy",
            "Economy (runs per over)",
        )

        def raw(r):
            return [
                r.wickets / max(r.innings, 1),
                r.dot_pct,
                100 - r.boundary_pct,
                max(0, 100 - r.economy * 10),
            ]

    vals = {p: [0 if v != v else v for v in raw(ov.loc[p])] for p in present}
    best = [max(max(v[i] for v in vals.values()), 1e-9) for i in range(4)]
    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.5, 0.5],
        vertical_spacing=0.14,
        specs=[[{"type": "polar"}], [{"type": "xy"}]],
        subplot_titles=[
            "Overall (the better of the two = 100)",
            ylabel.split(" (")[0] + " by phase",
        ],
    )
    for i, p in enumerate(present):
        r = [v / b * 100 for v, b in zip(vals[p], best)]
        fig.add_trace(
            go.Scatterpolar(
                r=r + r[:1],
                theta=cats + cats[:1],
                fill="toself",
                fillcolor=_FILL[i],
                line=dict(color=_COLORS[i], width=2),
                name=p,
            ),
            row=1,
            col=1,
        )
        ph = (
            d[(d.player == p) & (d.scope != "overall")]
            .set_index("scope")
            .reindex(_PHASES)[phase_col]
        )
        fig.add_bar(
            name=p,
            x=["Powerplay", "Middle", "Death"],
            y=ph.fillna(0),
            marker_color=_COLORS[i],
            text=[f"{v:.1f}" if v == v else "" for v in ph],
            textposition="outside",
            cliponaxis=False,
            showlegend=False,
            row=2,
            col=1,
        )
    fig.update_layout(
        barmode="group",
        polar=dict(
            radialaxis=dict(range=[0, 100], showticklabels=False, showline=False),
            angularaxis=dict(rotation=45),
            domain=dict(y=[0.52, 0.93], x=[0.1, 0.9]),
        ),
    )
    fig.update_yaxes(title_text=ylabel, row=2, col=1)
    return style(
        fig, " vs ".join(present) + (": batting" if bat else ": bowling"), result, height=900
    )
