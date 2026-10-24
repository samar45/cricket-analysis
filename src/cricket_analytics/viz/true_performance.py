"""Figure for the `true_performance` module (batting or bowling, told apart by the columns)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, subtitle


def figure(result) -> go.Figure:
    d = result.data
    bat = "batter" in d.columns
    who, raw, true, adj, k = (("batter", "raw_sr", "true_sr", "sr_adjustment", "sr") if bat
                              else ("bowler", "raw_economy", "true_economy", "econ_adjustment", "econ"))
    unit = "strike rate" if bat else "economy"
    top = d.head(15)
    fig = make_subplots(rows=2, cols=2, row_heights=[0.55, 0.45], vertical_spacing=0.14, horizontal_spacing=0.12,
                        subplot_titles=[f"Raw vs true {unit}", f"{unit.capitalize()} adjustment (true - raw)",
                                        f"{unit.capitalize()} by phase (top 10)",
                                        f"True {unit} vs {'balls faced' if bat else 'wickets'}"])
    up_is_good = bat   # batting: a higher true value is a boost; bowling: a lower one is
    for r in top.itertuples():
        c = PALETTE["good"] if (getattr(r, true) > getattr(r, raw)) == up_is_good else PALETTE["bad"]
        fig.add_scatter(x=[getattr(r, raw), getattr(r, true)], y=[getattr(r, who)] * 2, mode="lines+markers",
                        line=dict(color=c, width=3), marker=dict(size=[6, 11], color=c, symbol=["circle", "diamond"]),
                        showlegend=False, row=1, col=1)
    a = top.sort_values(adj)
    fig.add_bar(y=a[who], x=a[adj], orientation="h", showlegend=False, row=1, col=2,
                marker_color=[PALETTE["good"] if (v > 0) == up_is_good else PALETTE["bad"] for v in a[adj]])
    t10 = d.head(10)
    for p, label, c in zip(("powerplay", "middle", "death"), ("Powerplay", "Middle", "Death"), PALETTE["phases"]):
        fig.add_bar(name=label, y=t10[who], x=t10[f"{k}_{p}"].fillna(0), orientation="h", marker_color=c, row=2, col=1)
    xcol = "total_balls" if bat else "wickets"
    fig.add_scatter(x=d[xcol], y=d[true], mode="markers+text", text=d[who].str.split().str[-1], textposition="top center",
                    textfont=dict(size=8), marker=dict(size=9, color=PALETTE["primary"]), showlegend=False, row=2, col=2)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    fig.update_layout(title=f"True {unit}, phase-adjusted ({subtitle(result)})", barmode="group", height=720,
                      legend=dict(orientation="h", y=-0.08))
    return fig
