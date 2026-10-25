"""Batting figures. Input: api.Result from run('batting', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import bubble, empty, labels, style

_PHASES = ["powerplay", "middle", "death"]


def figure(result):
    df = result.data
    if df.empty:
        return empty("No batting data for these filters")
    if "phase" in df.columns:
        return _by_phase(df, result)
    if "season" in df.columns:
        return _by_season(df, result)
    for col in ("year", "venue", "opposition"):
        if col in df.columns:
            return _by_group(df, result, col)
    top = df.head(15)
    if len(top) == 1:
        return _single(top.iloc[0], result)

    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.55, 0.45],
        vertical_spacing=0.17,
        subplot_titles=[
            "Strike rate vs average (dot size = innings)",
            "Where the runs come from (top 10)",
        ],
    )
    fig.add_trace(
        go.Scatter(
            x=top["strike_rate"],
            y=top["average"],
            mode="markers+text",
            showlegend=False,
            marker=dict(
                **bubble(top["innings"]),
                color=C["primary"],
                opacity=0.75,
                line=dict(width=1, color="#0F131A"),
            ),
            text=labels(top["batter"]),
            textposition="top center",
            textfont=dict(size=11),
            customdata=top[["batter", "innings", "total_runs", "boundary_pct"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>SR %{x}, avg %{y}<br>%{customdata[1]} inns, %{customdata[2]} runs"
            "<br>boundary %{customdata[3]}%<extra></extra>",
        ),
        row=1,
        col=1,
    )
    t10 = top.head(10)
    for name, vals, colour in (
        ("Fours", t10["fours"] * 4, C["good"]),
        ("Sixes", t10["sixes"] * 6, C["bad"]),
        ("Other", t10["total_runs"] - t10["fours"] * 4 - t10["sixes"] * 6, C["light"]),
    ):
        fig.add_trace(
            go.Bar(name=name, y=t10["batter"], x=vals, orientation="h", marker_color=colour),
            row=2,
            col=1,
        )
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Strike rate (runs per 100 balls)", row=1, col=1)
    fig.update_yaxes(title_text="Batting average (runs per dismissal)", row=1, col=1)
    fig.update_xaxes(title_text="Runs", row=2, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    return style(fig, "Batting: top 15 by runs", result, height=900)


def _single(row, result):
    fig = make_subplots(
        rows=2,
        cols=1,
        row_heights=[0.5, 0.5],
        vertical_spacing=0.12,
        specs=[[{"type": "domain"}], [{"type": "xy"}]],
        subplot_titles=["Where the runs come from", "Key stats"],
    )
    r4, r6 = int(row["fours"]) * 4, int(row["sixes"]) * 6
    fig.add_trace(
        go.Pie(
            labels=["From 4s", "From 6s", "Running"],
            values=[r4, r6, int(row["total_runs"]) - r4 - r6],
            marker_colors=[C["good"], C["bad"], C["primary"]],
            hole=0.5,
            textinfo="label+percent",
            textposition="outside",
            automargin=True,
            showlegend=False,
        ),
        row=1,
        col=1,
    )
    vals = [float(row[k] or 0) for k in ("average", "strike_rate", "boundary_pct", "dot_pct")]
    fig.add_trace(
        go.Bar(
            y=["Average", "Strike rate", "Boundary %", "Dot %"],
            x=vals,
            orientation="h",
            marker_color=[C["good"], C["secondary"], C["accent"], C["neutral"]],
            text=[str(v) for v in vals],
            textposition="outside",
            cliponaxis=False,
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    note = (
        f"{int(row['total_runs'])} runs in {int(row['innings'])} innings, {int(row['not_outs'])} not out, "
        f"highest {int(row['highest'])}"
    )
    return style(fig, str(row["batter"]), result, note=note, height=720)


def _by_phase(df, result):
    if df["batter"].nunique() > 1:  # many players: a heatmap of strike rate, players x phases
        top = df.groupby("batter")["total_runs"].sum().nlargest(15).index
        piv = df[df["batter"].isin(top)].pivot_table(
            index="batter", columns="phase", values="strike_rate"
        )
        piv = piv.reindex(index=top, columns=_PHASES)
        fig = go.Figure(
            go.Heatmap(
                z=piv.values,
                x=["Powerplay", "Middle", "Death"],
                y=piv.index,
                text=piv.round(0).values,
                texttemplate="%{text:.0f}",
                colorscale=[[0, "#1B2A3D"], [1, C["primary"]]],
                showscale=False,
                xgap=3,
                ygap=3,
                hovertemplate="%{y}, %{x}: SR %{z}<extra></extra>",
            )
        )
        fig.update_yaxes(autorange="reversed")
        return style(
            fig,
            "Strike rate by phase: top 15 run-scorers",
            result,
            note="strike rate = runs per 100 balls; brighter = faster",
            height=170 + 28 * len(piv),
        )
    fig = make_subplots(
        rows=2,
        cols=1,
        vertical_spacing=0.16,
        subplot_titles=["Strike rate by phase", "Boundary % and dot % by phase"],
    )
    fig.add_trace(
        go.Bar(
            x=df["phase"].str.capitalize(),
            y=df["strike_rate"],
            marker_color=C["phases"][: len(df)],
            showlegend=False,
            text=df["strike_rate"],
            textposition="outside",
            cliponaxis=False,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            name="Boundary %",
            x=df["phase"].str.capitalize(),
            y=df["boundary_pct"],
            marker_color=C["accent"],
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            name="Dot %", x=df["phase"].str.capitalize(), y=df["dot_pct"], marker_color=C["neutral"]
        ),
        row=2,
        col=1,
    )
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="Strike rate", row=1, col=1)
    fig.update_yaxes(title_text="% of balls", row=2, col=1)
    return style(fig, "Batting by phase", result, height=700)


def _by_season(df, result):
    multi_comp = df["competition"].nunique() > 1
    df = df.assign(x=df["competition"] + " " + df["season"] if multi_comp else df["season"])
    if df["batter"].nunique() > 1:  # many players: runs per season for the six biggest run-scorers
        fig = go.Figure()
        for p in df.groupby("batter")["total_runs"].sum().nlargest(6).index:
            s = df[df["batter"] == p]
            fig.add_scatter(
                x=s["x"],
                y=s["total_runs"],
                name=p,
                mode="lines+markers",
                customdata=s[["strike_rate", "average"]].values,
                hovertemplate=f"<b>{p}</b> %{{x}}<br>%{{y}} runs, SR %{{customdata[0]}}, avg %{{customdata[1]}}<extra></extra>",
            )
        fig.update_xaxes(type="category", tickangle=-45)
        fig.update_yaxes(title_text="Runs in the season")
        return style(fig, "Runs per season: the six biggest run-scorers", result)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=df["x"], y=df["total_runs"], name="Runs", marker_color=C["primary"]),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["x"],
            y=df["strike_rate"],
            name="Strike rate",
            mode="lines+markers",
            line=dict(color=C["secondary"]),
        ),
        secondary_y=True,
    )
    fig.update_xaxes(type="category", tickangle=-45)
    fig.update_yaxes(title_text="Runs", secondary_y=False)
    fig.update_yaxes(
        title_text="Strike rate (runs per 100 balls)", secondary_y=True, showgrid=False
    )
    return style(fig, f"{df['batter'].iloc[0]}: runs and strike rate by season", result)


def _by_group(df, result, col):
    """group_by = year / venue / opposition: the season chart with that column on the x axis (top 15 groups for venue/opposition)."""
    if col != "year":
        keep = df.groupby(col)["total_runs"].sum().nlargest(15).index
        df = df[df[col].isin(keep)]
    df = df.assign(**{"season": df[col].astype(str), "competition": ""})
    fig = _by_season(df, result)
    fig.update_layout(
        title_text=fig.layout.title.text.replace("by season", f"by {col}").replace(
            "per season", f"per {col}"
        )
    )
    return fig
