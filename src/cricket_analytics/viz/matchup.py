"""Matchup figures (moved from the old B4 plot). Input: api.Result from run('matchup', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import subtitle

_OUTCOMES = (("dots", "Dots", "#E0E0E0"), ("ones", "Singles", C["light"]), ("twos", "Twos", C["secondary"]),
             ("threes", "Threes", "#CE93D8"), ("fours", "Fours", C["good"]), ("sixes", "Sixes", C["bad"]))


def figure(result):
    df = result.data
    if df.empty:
        return go.Figure().update_layout(title="No balls between these players for these filters")
    top = df.head(12).copy()
    top["label"] = top["batter"] + " v " + top["bowler"]
    if len(top) == 1:
        r = top.iloc[0]
        fig = make_subplots(rows=1, cols=2, column_widths=[0.55, 0.45], specs=[[{"type": "domain"}, {"type": "xy"}]],
                            subplot_titles=["Scoring wheel (balls)", "Key numbers"])
        fig.add_trace(go.Pie(labels=[n for _, n, _ in _OUTCOMES], values=[int(r[c]) for c, _, _ in _OUTCOMES],
                             marker_colors=[c for _, _, c in _OUTCOMES], hole=0.5, textinfo="label+value"),
                      row=1, col=1)
        vals = [float(r[k] or 0) for k in ("runs", "balls", "strike_rate", "boundary_pct", "dot_pct")]
        fig.add_trace(go.Bar(y=["Runs", "Balls", "Strike rate", "Boundary %", "Dot %"], x=vals, orientation="h",
                             marker_color=C["primary"], showlegend=False, text=[str(v) for v in vals],
                             textposition="outside"), row=1, col=2)
        fig.update_layout(title=f"{r['batter']} v {r['bowler']}: {int(r['runs'])} off {int(r['balls'])}, "
                                f"{int(r['dismissals'])} dismissals", height=420)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        return fig
    fig = go.Figure()
    for col, name, colour in _OUTCOMES:
        fig.add_bar(name=name, y=top["label"], x=top[col], orientation="h", marker_color=colour)
    fig.update_layout(title=f"Head to head: balls by outcome ({subtitle(result)})", barmode="stack",
                      yaxis=dict(autorange="reversed"), xaxis_title="Balls", height=max(450, len(top) * 42),
                      legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"))
    return fig
