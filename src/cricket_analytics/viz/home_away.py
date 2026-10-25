"""Home vs away vs neutral. Input: api.Result from run('home_away', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import empty, style

LOC_COLOUR = {"home": C["good"], "away": C["bad"], "neutral": C["neutral"], "unknown": C["light"]}
# metric -> axis title, per kind of rows
METRICS = {
    "batter": [
        ("average", "Batting average (runs per dismissal)"),
        ("strike_rate", "Strike rate (runs per 100 balls)"),
    ],
    "bowler": [
        ("economy", "Economy (runs per over)"),
        ("strike_rate", "Bowling strike rate (balls per wicket)"),
    ],
    "team": [
        ("win_pct", "Win % (of decided matches)"),
        ("avg_runs_for", "Average runs scored per innings"),
    ],
}


def entity_col(df) -> str:
    return next(c for c in ("batter", "bowler", "team") if c in df.columns)


def figure(result):
    df = result.data
    if df.empty:
        return empty("No home/away data for these filters")
    ent = entity_col(df)
    names = df.groupby(ent)["matches"].sum().sort_values(ascending=False).index[:10]
    if len(names) == 1:
        d = df[df[ent] == names[0]]
        metrics = METRICS[ent]
        fig = make_subplots(
            rows=len(metrics), cols=1, vertical_spacing=0.2, subplot_titles=[t for _, t in metrics]
        )
        for i, (col, _) in enumerate(metrics, 1):
            fig.add_trace(
                go.Bar(
                    x=d["location"],
                    y=d[col],
                    marker_color=[LOC_COLOUR[loc] for loc in d["location"]],
                    text=[f"{v}  ({n} matches)" for v, n in zip(d[col], d["matches"])],
                    textposition="outside",
                    cliponaxis=False,
                    showlegend=False,
                ),
                row=i,
                col=1,
            )
        return style(
            fig, f"{names[0]}: home vs away vs neutral", result, height=330 * len(metrics) + 120
        )
    col = METRICS[ent][0][0]
    fig = go.Figure()
    for loc in ("home", "away", "neutral"):
        d = df[(df["location"] == loc) & df[ent].isin(names)].set_index(ent).reindex(names)
        fig.add_trace(
            go.Bar(
                name=loc.title(),
                x=names,
                y=d[col],
                marker_color=LOC_COLOUR[loc],
                customdata=d["matches"],
                hovertemplate="%{x}: %{y} (%{customdata} matches)<extra>" + loc + "</extra>",
            )
        )
    fig.update_layout(barmode="group", yaxis_title=METRICS[ent][0][1])
    return style(fig, f"Home vs away vs neutral: top {len(names)} by matches", result, height=520)
