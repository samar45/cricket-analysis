"""Bowling figures. Input: api.Result from run('bowling', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import bubble, empty, labels, style

_PHASES = ["powerplay", "middle", "death"]


def figure(result):
    df = result.data
    if df.empty:
        return empty("No bowling data for these filters")
    if "phase" in df.columns:
        return _by_phase(df, result)
    if "season" in df.columns:
        return _by_season(df, result)
    top = df.head(15)
    if len(top) == 1:
        return _single(top.iloc[0], result)

    fig = make_subplots(rows=2, cols=1, row_heights=[0.55, 0.45], vertical_spacing=0.17,
                        subplot_titles=["Economy vs strike rate (dot size = wickets)", "Dot % and boundary % (top 10)"])
    fig.add_trace(go.Scatter(
        x=top["economy"], y=top["strike_rate"], mode="markers+text", showlegend=False,
        marker=dict(**bubble(top["wickets"]), color=C["primary"], opacity=0.75, line=dict(width=1, color="#0F131A")),
        text=labels(top["bowler"]), textposition="top center", textfont=dict(size=11),
        customdata=top[["bowler", "wickets", "innings", "dot_pct"]].values,
        hovertemplate="<b>%{customdata[0]}</b><br>economy %{x}, strike rate %{y}<br>%{customdata[1]} wickets, "
                      "%{customdata[2]} inns<br>dot %{customdata[3]}%<extra></extra>"), row=1, col=1)
    t10 = top.head(10)
    fig.add_trace(go.Bar(name="Dot %", y=t10["bowler"], x=t10["dot_pct"], orientation="h", marker_color=C["primary"]),
                  row=2, col=1)
    fig.add_trace(go.Bar(name="Boundary %", y=t10["bowler"], x=t10["boundary_pct"], orientation="h",
                         marker_color=C["bad"]), row=2, col=1)
    fig.update_layout(barmode="group")
    fig.update_xaxes(title_text="Economy (runs per over), lower is better", row=1, col=1)
    fig.update_yaxes(title_text="Strike rate (balls per wicket)", row=1, col=1)
    fig.update_xaxes(title_text="% of balls", row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    return style(fig, "Bowling: top 15 by wickets", result, height=960)


def _single(row, result):
    other = int(row["balls"]) - int(row["dots"]) - int(row["fours_conceded"]) - int(row["sixes_conceded"]) - int(row["wickets"])
    fig = make_subplots(rows=2, cols=1, row_heights=[0.5, 0.5], vertical_spacing=0.12,
                        specs=[[{"type": "domain"}], [{"type": "xy"}]],
                        subplot_titles=["Legal balls by outcome", "Key metrics"])
    fig.add_trace(go.Pie(labels=["Dots", "Fours", "Sixes", "Wickets", "Other"],
                         values=[int(row["dots"]), int(row["fours_conceded"]), int(row["sixes_conceded"]),
                                 int(row["wickets"]), max(other, 0)],
                         marker_colors=[C["light"], C["good"], C["bad"], C["secondary"], C["neutral"]],
                         hole=0.5, textinfo="label+percent", textposition="outside", automargin=True, showlegend=False), row=1, col=1)
    vals = [float(row[k] or 0) for k in ("economy", "average", "strike_rate", "dot_pct", "boundary_pct")]
    fig.add_trace(go.Bar(y=["Economy", "Average", "Strike rate", "Dot %", "Boundary %"], x=vals, orientation="h",
                         text=[str(v) for v in vals], textposition="outside", cliponaxis=False,
                         marker_color=C["primary"], showlegend=False), row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    note = f"{int(row['wickets'])} wickets in {int(row['innings'])} innings, economy {row['economy']}"
    return style(fig, str(row["bowler"]), result, note=note, height=720)


def _by_phase(df, result):
    if df["bowler"].nunique() > 1:   # many players: a heatmap of economy, players x phases
        top = df.groupby("bowler")["wickets"].sum().nlargest(15).index
        piv = df[df["bowler"].isin(top)].pivot_table(index="bowler", columns="phase", values="economy")
        piv = piv.reindex(index=top, columns=_PHASES)
        fig = go.Figure(go.Heatmap(z=piv.values, x=["Powerplay", "Middle", "Death"], y=piv.index, text=piv.round(1).values,
                                   texttemplate="%{text:.1f}", colorscale=[[0, C["primary"]], [1, "#1B2A3D"]],
                                   showscale=False, xgap=3, ygap=3,
                                   hovertemplate="%{y}, %{x}: economy %{z}<extra></extra>"))
        fig.update_yaxes(autorange="reversed")
        return style(fig, "Economy by phase: top 15 wicket-takers", result,
                     note="economy = runs per over; brighter = tighter", height=170 + 28 * len(piv))
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.16,
                        subplot_titles=["Economy by phase", "Dot % and boundary % by phase"])
    fig.add_trace(go.Bar(x=df["phase"].str.capitalize(), y=df["economy"], marker_color=C["phases"][: len(df)], showlegend=False,
                         text=df["economy"], textposition="outside", cliponaxis=False), row=1, col=1)
    fig.add_trace(go.Bar(name="Dot %", x=df["phase"].str.capitalize(), y=df["dot_pct"], marker_color=C["primary"]), row=2, col=1)
    fig.add_trace(go.Bar(name="Boundary %", x=df["phase"].str.capitalize(), y=df["boundary_pct"], marker_color=C["bad"]), row=2, col=1)
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="Economy (runs per over)", row=1, col=1)
    fig.update_yaxes(title_text="% of balls", row=2, col=1)
    return style(fig, "Bowling by phase", result, height=700)


def _by_season(df, result):
    multi_comp = df["competition"].nunique() > 1
    df = df.assign(x=df["competition"] + " " + df["season"] if multi_comp else df["season"])
    if df["bowler"].nunique() > 1:   # many players: wickets per season for the six biggest wicket-takers
        fig = go.Figure()
        for p in df.groupby("bowler")["wickets"].sum().nlargest(6).index:
            s = df[df["bowler"] == p]
            fig.add_scatter(x=s["x"], y=s["wickets"], name=p, mode="lines+markers", customdata=s[["economy"]].values,
                            hovertemplate=f"<b>{p}</b> %{{x}}<br>%{{y}} wickets, economy %{{customdata[0]}}<extra></extra>")
        fig.update_xaxes(type="category", tickangle=-45)
        fig.update_yaxes(title_text="Wickets in the season")
        return style(fig, "Wickets per season: the six biggest wicket-takers", result)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["x"], y=df["wickets"], name="Wickets", marker_color=C["primary"]), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["x"], y=df["economy"], name="Economy", mode="lines+markers",
                             line=dict(color=C["secondary"])), secondary_y=True)
    fig.update_xaxes(type="category", tickangle=-45)
    fig.update_yaxes(title_text="Wickets", secondary_y=False)
    fig.update_yaxes(title_text="Economy (runs per over)", secondary_y=True, showgrid=False)
    return style(fig, f"{df['bowler'].iloc[0]}: wickets and economy by season", result)
