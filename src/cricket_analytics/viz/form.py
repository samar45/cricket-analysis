"""Form figures: per-innings (or per-spell) bars with a rolling line. Input: api.Result from run('form', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import empty, style


def figure(result):
    df = result.data
    p = result.meta["params"]
    window, who = p.get("window", 10), p.get("player", "")
    if df.empty:
        return empty("No innings for these filters")
    batter = p.get("role", "batter") == "batter"
    x = df["innings_no"] if batter else df["spell_no"]
    top, top_roll = ("runs", "rolling_runs") if batter else ("wickets", "rolling_wickets")
    bot, bot_roll = ("strike_rate", "rolling_sr") if batter else ("economy", "rolling_economy")
    unit = "innings" if batter else "spell"
    bot_label = "Strike rate" if batter else "Economy"
    fig = make_subplots(rows=2, cols=1, row_heights=[0.62, 0.38], shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=[f"{top.title()} per {unit}", f"{bot_label} per {unit}"])
    colours = ([C["bad"] if o else C["good"] for o in df["dismissed"]] if batter
               else [C["secondary"] if w >= 3 else C["primary"] for w in df["wickets"]])
    fig.add_trace(go.Bar(name=top.title(), x=x, y=df[top], marker_color=colours, showlegend=False,
                         customdata=df[["date", "venue"]].astype(str).values,
                         hovertemplate="#%{x} %{customdata[0]}<br>%{y}<br>%{customdata[1]}<extra></extra>"),
                  row=1, col=1)
    fig.add_trace(go.Scatter(name=f"{window}-{unit} average", x=x, y=df[top_roll], mode="lines",
                             line=dict(color=C["secondary"], width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(name=bot_label, x=x, y=df[bot], mode="lines", fill="tozeroy", showlegend=False,
                             line=dict(color=C["primary"], width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(name=f"{window}-{unit} rolling {bot_label.lower()}", x=x, y=df[bot_roll], mode="lines",
                             line=dict(color=C["accent"], width=2.5, dash="dash")), row=2, col=1)
    note = "bars: green = not out, red = out" if batter else "bars: orange = 3+ wickets"
    fig.update_layout(hovermode="x unified", bargap=0.15)
    fig.update_yaxes(title_text="Runs" if batter else "Wickets", row=1, col=1)
    fig.update_yaxes(title_text="Runs per 100 balls" if batter else "Runs per over", row=2, col=1)
    fig.update_xaxes(title_text=f"{unit.title()} number", row=2, col=1)
    return style(fig, f"{'Batting' if batter else 'Bowling'} form: {who}", result, note=note, height=620)
