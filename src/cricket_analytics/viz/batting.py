"""Batting figures (moved from the old B1 plot). Input: api.Result from run('batting', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import subtitle


def figure(result):
    df = result.data
    if df.empty:
        return go.Figure().update_layout(title="No batting data for these filters")
    if "phase" in df.columns:
        return _by_phase(df, result)
    if "season" in df.columns:
        return _by_season(df, result)
    top = df.head(15)
    if len(top) == 1:
        return _single(top.iloc[0])

    fig = make_subplots(rows=1, cols=2, column_widths=[0.55, 0.45],
                        subplot_titles=["Strike rate vs average (size = innings)", "Where the runs come from (top 10)"])
    fig.add_trace(go.Scatter(
        x=top["strike_rate"], y=top["average"], mode="markers+text", showlegend=False,
        marker=dict(size=top["innings"].clip(lower=3) * 2, color=top["boundary_pct"], colorscale="YlOrRd",
                    showscale=True, colorbar=dict(title="Boundary %", x=0.47, len=0.8), line=dict(width=1, color="#333")),
        text=top["batter"].str.split().str[-1], textposition="top center", textfont=dict(size=9)), row=1, col=1)
    t10 = top.head(10)
    for name, vals, colour in (("Fours", t10["fours"] * 4, C["good"]), ("Sixes", t10["sixes"] * 6, C["bad"]),
                               ("Other", t10["total_runs"] - t10["fours"] * 4 - t10["sixes"] * 6, C["light"])):
        fig.add_trace(go.Bar(name=name, y=t10["batter"], x=vals, orientation="h", marker_color=colour), row=1, col=2)
    fig.update_layout(title=f"Batting stats ({subtitle(result)})", barmode="stack", height=550,
                      legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"))
    fig.update_xaxes(title_text="Strike rate", row=1, col=1)
    fig.update_yaxes(title_text="Average", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    return fig


def _single(row):
    fig = make_subplots(rows=1, cols=2, column_widths=[0.45, 0.55], specs=[[{"type": "domain"}, {"type": "xy"}]],
                        subplot_titles=["Run sources", "Key stats"])
    r4, r6 = int(row["fours"]) * 4, int(row["sixes"]) * 6
    fig.add_trace(go.Pie(labels=["From 4s", "From 6s", "Running"], values=[r4, r6, int(row["total_runs"]) - r4 - r6],
                         marker_colors=[C["good"], C["bad"], C["primary"]], hole=0.45, textinfo="label+percent"),
                  row=1, col=1)
    vals = [float(row[k] or 0) for k in ("average", "strike_rate", "boundary_pct", "dot_pct")]
    fig.add_trace(go.Bar(y=["Average", "Strike rate", "Boundary %", "Dot %"], x=vals, orientation="h",
                         marker_color=[C["good"], C["secondary"], C["accent"], C["neutral"]],
                         text=[str(v) for v in vals], textposition="outside", showlegend=False), row=1, col=2)
    fig.update_layout(title=f"{row['batter']}: {int(row['total_runs'])} runs, {int(row['innings'])} inns, "
                            f"{int(row['not_outs'])} NO, HS {int(row['highest'])}", height=400)
    fig.update_yaxes(autorange="reversed", row=1, col=2)
    return fig


def _by_phase(df, result):
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Strike rate by phase", "Boundary % vs dot %"])
    fig.add_trace(go.Bar(x=df["phase"], y=df["strike_rate"], marker_color=C["phases"][: len(df)], showlegend=False),
                  row=1, col=1)
    fig.add_trace(go.Bar(name="Boundary %", x=df["phase"], y=df["boundary_pct"], marker_color=C["accent"]), row=1, col=2)
    fig.add_trace(go.Bar(name="Dot %", x=df["phase"], y=df["dot_pct"], marker_color=C["neutral"]), row=1, col=2)
    fig.update_layout(title=f"Batting by phase ({subtitle(result)})", barmode="group", height=420)
    return fig


def _by_season(df, result):
    x = df["competition"] + " " + df["season"] if df["competition"].nunique() > 1 else df["season"]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=x, y=df["total_runs"], name="Runs", marker_color=C["primary"]), secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=df["strike_rate"], name="Strike rate", mode="lines+markers",
                             line=dict(color=C["secondary"])), secondary_y=True)
    fig.update_layout(title=f"Batting by season ({subtitle(result)})", height=420)
    return fig
