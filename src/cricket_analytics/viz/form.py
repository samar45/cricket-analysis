"""Form figures (moved from the old I4 plot). Input: api.Result from run('form', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C


def figure(result):
    df = result.data
    p = result.meta["params"]
    window, who = p.get("window", 10), p.get("player", "")
    if df.empty:
        return go.Figure().update_layout(title="No innings for these filters")
    batter = p.get("role", "batter") == "batter"
    x = df["innings_no"] if batter else df["spell_no"]
    top, top_roll = ("runs", "rolling_runs") if batter else ("wickets", "rolling_wickets")
    bot, bot_roll = ("strike_rate", "rolling_sr") if batter else ("economy", "rolling_economy")
    unit = "innings" if batter else "spell"
    fig = make_subplots(rows=2, cols=1, row_heights=[0.65, 0.35], shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=[f"{top.title()} per {unit} ({window}-row rolling average)",
                                        bot.replace("_", " ").title()])
    colours = ([C["bad"] if o else C["good"] for o in df["dismissed"]] if batter
               else [C["secondary"] if w >= 3 else C["primary"] for w in df["wickets"]])
    fig.add_trace(go.Bar(name=top.title(), x=x, y=df[top], marker_color=colours,
                         customdata=df[["date", "venue"]].astype(str).values,
                         hovertemplate="#%{x} %{customdata[0]}<br>%{y}<br>%{customdata[1]}<extra></extra>"),
                  row=1, col=1)
    fig.add_trace(go.Scatter(name=f"{window}-row average", x=x, y=df[top_roll], mode="lines",
                             line=dict(color=C["secondary"], width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(name=bot.replace("_", " ").title(), x=x, y=df[bot], mode="lines", fill="tozeroy",
                             line=dict(color=C["primary"], width=2)), row=2, col=1)
    fig.add_trace(go.Scatter(name=f"{window}-row rolling", x=x, y=df[bot_roll], mode="lines",
                             line=dict(color=C["accent"], width=2, dash="dash")), row=2, col=1)
    note = "green = not out, red = out" if batter else "orange = 3+ wickets"
    fig.update_layout(title=f"{'Batting' if batter else 'Bowling'} form: {who} ({note})", height=550,
                      hovermode="x unified", legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"))
    fig.update_xaxes(title_text=f"{unit.title()} #", row=2, col=1)
    return fig
