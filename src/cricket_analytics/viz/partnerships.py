"""Partnership figures. Input: api.Result from run('partnerships', ...)."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import bars_height, empty, style


def figure(result):
    df = result.data
    if df.empty:
        return empty("No partnerships for these filters")
    if "batter1" not in df.columns:  # group_by=wicket
        fig = go.Figure(
            go.Bar(
                x=df["wicket_no"].astype(str),
                y=df["average_stand"],
                marker_color=C["primary"],
                text=df["average_stand"],
                textposition="outside",
                cliponaxis=False,
                customdata=df[["stands", "highest_stand", "runs"]].values,
                hovertemplate="wicket %{x}<br>average %{y}<br>%{customdata[0]} stands, highest "
                "%{customdata[1]}<extra></extra>",
            )
        )
        fig.update_xaxes(title_text="Wicket that ended the stand")
        fig.update_yaxes(
            title_text="Average stand (runs)", range=[0, df["average_stand"].max() * 1.15]
        )
        return style(fig, "Average partnership by wicket", result)
    top = df.head(12).copy()
    top["pair"] = top["batter1"] + " & " + top["batter2"]
    if "highest_stand" in top.columns:  # group_by=pair
        title, cd = "Top 12 partnerships by total runs", ["stands", "highest_stand", "balls"]
        hover = (
            "%{customdata[0]} stands together, highest %{customdata[1]}<br>%{customdata[2]} balls"
        )
    else:  # group_by=stand
        top["pair"] += "<br>" + top["date"].astype(str) + " v " + top["opposition"]
        title, cd = "Top 12 individual partnerships", ["balls", "wicket_no", "team"]
        hover = "%{customdata[0]} balls, wicket %{customdata[1]}<br>%{customdata[2]}"
    fig = go.Figure(
        go.Bar(
            y=top["pair"],
            x=top["runs"],
            orientation="h",
            marker_color=C["primary"],
            customdata=top[cd].values,
            text=[f"{r}  (SR {s:.0f})" for r, s in zip(top["runs"], top["strike_rate"])],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x} runs<br>" + hover + "<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Runs together", range=[0, top["runs"].max() * 1.3])
    fig.update_yaxes(autorange="reversed")
    return style(
        fig,
        title,
        result,
        note="label = runs (strike rate)",
        height=bars_height(len(top), 34 if "date" in top else 28),
    )
