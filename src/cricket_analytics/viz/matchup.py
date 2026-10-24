"""Matchup figures. Input: api.Result from run('matchup', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import bars_height, empty, style

_OUTCOMES = (("dots", "Dots", "#E0E0E0"), ("ones", "Singles", C["light"]), ("twos", "Twos", C["secondary"]),
             ("threes", "Threes", "#CE93D8"), ("fours", "Fours", C["good"]), ("sixes", "Sixes", C["bad"]))


def figure(result):
    df = result.data
    if df.empty:
        return empty("No balls between these players for these filters")
    top = df.head(12).copy()
    if len(top) == 1:
        return _duel(top.iloc[0], result)
    # one batter against many bowlers (or the reverse): label by the side that varies
    one_batter = top["batter"].nunique() == 1
    top["label"] = top["bowler"] if one_batter else top["batter"] if top["bowler"].nunique() == 1 \
        else top["batter"] + " v " + top["bowler"]
    fig = go.Figure()
    for col, name, colour in _OUTCOMES:
        fig.add_bar(name=name, y=top["label"], x=top[col], orientation="h", marker_color=colour)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Balls faced")
    fig.update_yaxes(autorange="reversed")
    who = f"{top['batter'].iloc[0]} against" if one_batter else "Head to head:"
    return style(fig, f"{who} the {len(top)} most-faced: balls by outcome", result, height=bars_height(len(top), 30, 200))


def _duel(r, result):
    fig = make_subplots(rows=2, cols=1, row_heights=[0.55, 0.45], vertical_spacing=0.12,
                        specs=[[{"type": "domain"}], [{"type": "xy"}]],
                        subplot_titles=["Balls by outcome", "Key numbers"])
    fig.add_trace(go.Pie(labels=[n for _, n, _ in _OUTCOMES], values=[int(r[c]) for c, _, _ in _OUTCOMES],
                         marker_colors=[c for _, _, c in _OUTCOMES], hole=0.5, textinfo="label+value", textposition="outside", automargin=True,
                         showlegend=False, sort=False), row=1, col=1)
    vals = [float(r[k] or 0) for k in ("runs", "balls", "strike_rate", "boundary_pct", "dot_pct")]
    fig.add_trace(go.Bar(y=["Runs", "Balls", "Strike rate", "Boundary %", "Dot %"], x=vals, orientation="h",
                         marker_color=C["primary"], showlegend=False, text=[str(v) for v in vals],
                         textposition="outside", cliponaxis=False), row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    note = f"{int(r['runs'])} off {int(r['balls'])} balls, {int(r['dismissals'])} dismissals"
    return style(fig, f"{r['batter']} v {r['bowler']}", result, note=note, height=720)
