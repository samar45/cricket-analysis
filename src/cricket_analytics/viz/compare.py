"""Figure for the `compare` module: radar of the overall numbers plus a per-phase bar."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE

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
        cats, phase_col, ylabel = ["Average", "Strike rate", "Boundary %", "100 - dot %"], "strike_rate", "Strike rate"
        raw = lambda r: [r.average, r.strike_rate, r.boundary_pct, 100 - r.dot_pct]  # noqa: E731
    else:
        cats, phase_col, ylabel = ["Wickets / innings", "Dot %", "100 - boundary %", "100 - economy x 10"], "economy", "Economy"
        raw = lambda r: [r.wickets / max(r.innings, 1), r.dot_pct, 100 - r.boundary_pct, max(0, 100 - r.economy * 10)]  # noqa: E731
    vals = {p: [0 if v != v else v for v in raw(ov.loc[p])] for p in present}
    best = [max(max(v[i] for v in vals.values()), 1e-9) for i in range(4)]
    fig = make_subplots(rows=1, cols=2, column_widths=[0.45, 0.55], specs=[[{"type": "polar"}, {"type": "xy"}]],
                        subplot_titles=["Overall (better of the two = 100)", f"{ylabel} by phase"])
    for i, p in enumerate(present):
        r = [v / b * 100 for v, b in zip(vals[p], best)]
        fig.add_trace(go.Scatterpolar(r=r + r[:1], theta=cats + cats[:1], fill="toself", fillcolor=_FILL[i],
                                      line=dict(color=_COLORS[i], width=2), name=p), row=1, col=1)
        ph = d[(d.player == p) & (d.scope != "overall")].set_index("scope").reindex(_PHASES)[phase_col]
        fig.add_bar(name=p, x=["Powerplay", "Middle", "Death"], y=ph.fillna(0), marker_color=_COLORS[i],
                    text=[f"{v:.1f}" if v == v else "" for v in ph], textposition="outside", showlegend=False, row=1, col=2)
    fig.update_layout(title=" vs ".join(present) + (" - batting" if bat else " - bowling"), barmode="group", height=480,
                      polar=dict(radialaxis=dict(visible=True, range=[0, 100])), legend=dict(orientation="h", y=-0.1))
    fig.update_yaxes(title_text=ylabel, row=1, col=2)
    return fig
