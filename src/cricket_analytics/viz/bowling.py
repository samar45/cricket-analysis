"""Bowling figures (moved from the old B2 plot). Input: api.Result from run('bowling', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import subtitle


def figure(result):
    df = result.data
    if df.empty:
        return go.Figure().update_layout(title="No bowling data for these filters")
    if "phase" in df.columns:
        return _by_phase(df, result)
    if "season" in df.columns:
        return _by_season(df, result)
    top = df.head(15)
    if len(top) == 1:
        return _single(top.iloc[0])

    fig = make_subplots(rows=1, cols=2, column_widths=[0.55, 0.45],
                        subplot_titles=["Economy vs strike rate (size = wickets)", "Dot % vs boundary % (top 10)"])
    fig.add_trace(go.Scatter(
        x=top["economy"], y=top["strike_rate"], mode="markers+text", showlegend=False,
        marker=dict(size=top["wickets"].clip(lower=3) * 1.2, color=top["dot_pct"], colorscale="Blues", showscale=True,
                    colorbar=dict(title="Dot %", x=0.47, len=0.8), line=dict(width=1, color="#333")),
        text=top["bowler"].str.split().str[-1], textposition="top center", textfont=dict(size=9)), row=1, col=1)
    t10 = top.head(10)
    fig.add_trace(go.Bar(name="Dot %", y=t10["bowler"], x=t10["dot_pct"], orientation="h", marker_color=C["primary"]),
                  row=1, col=2)
    fig.add_trace(go.Bar(name="Boundary %", y=t10["bowler"], x=-t10["boundary_pct"], orientation="h",
                         marker_color=C["bad"]), row=1, col=2)
    fig.update_layout(title=f"Bowling stats ({subtitle(result)})", barmode="overlay", height=550,
                      legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"))
    fig.update_xaxes(title_text="Economy", row=1, col=1)
    fig.update_yaxes(title_text="Bowling strike rate", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    return fig


def _single(row):
    other = int(row["balls"]) - int(row["dots"]) - int(row["fours_conceded"]) - int(row["sixes_conceded"]) - int(row["wickets"])
    fig = make_subplots(rows=1, cols=2, column_widths=[0.45, 0.55], specs=[[{"type": "domain"}, {"type": "xy"}]],
                        subplot_titles=["Legal balls by outcome", "Key metrics"])
    fig.add_trace(go.Pie(labels=["Dots", "Fours", "Sixes", "Wickets", "Other"],
                         values=[int(row["dots"]), int(row["fours_conceded"]), int(row["sixes_conceded"]),
                                 int(row["wickets"]), max(other, 0)],
                         marker_colors=[C["light"], C["good"], C["bad"], C["secondary"], C["neutral"]],
                         hole=0.45, textinfo="label+percent"), row=1, col=1)
    vals = [float(row[k] or 0) for k in ("economy", "average", "strike_rate", "dot_pct", "boundary_pct")]
    fig.add_trace(go.Bar(y=["Economy", "Average", "Strike rate", "Dot %", "Boundary %"], x=vals, orientation="h",
                         text=[str(v) for v in vals], textposition="outside", marker_color=C["primary"],
                         showlegend=False), row=1, col=2)
    fig.update_layout(title=f"{row['bowler']}: {int(row['wickets'])} wkts, econ {row['economy']}, "
                            f"{int(row['innings'])} inns", height=400)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    return fig


def _by_phase(df, result):
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Economy by phase", "Dot % vs boundary %"])
    fig.add_trace(go.Bar(x=df["phase"], y=df["economy"], marker_color=C["phases"][: len(df)], showlegend=False),
                  row=1, col=1)
    fig.add_trace(go.Bar(name="Dot %", x=df["phase"], y=df["dot_pct"], marker_color=C["primary"]), row=1, col=2)
    fig.add_trace(go.Bar(name="Boundary %", x=df["phase"], y=df["boundary_pct"], marker_color=C["bad"]), row=1, col=2)
    fig.update_layout(title=f"Bowling by phase ({subtitle(result)})", barmode="group", height=420)
    return fig


def _by_season(df, result):
    x = df["competition"] + " " + df["season"] if df["competition"].nunique() > 1 else df["season"]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=x, y=df["wickets"], name="Wickets", marker_color=C["primary"]), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=df["economy"], name="Economy", mode="lines+markers",
                             line=dict(color=C["secondary"])), secondary_y=True)
    fig.update_layout(title=f"Bowling by season ({subtitle(result)})", height=420)
    return fig
