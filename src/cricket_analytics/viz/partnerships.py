"""Partnership figures (moved from the old I2 plot). Input: api.Result from run('partnerships', ...)."""

import plotly.express as px
import plotly.graph_objects as go

from . import subtitle


def figure(result):
    df = result.data
    if df.empty:
        return go.Figure().update_layout(title="No partnerships for these filters")
    if "batter1" not in df.columns:         # group_by=wicket
        return px.bar(df, x="wicket_no", y="average_stand", hover_data=["stands", "highest_stand", "runs"],
                      title=f"Average stand by wicket ({subtitle(result)})",
                      labels={"wicket_no": "Wicket", "average_stand": "Average stand (runs)"})
    top = df.head(15).copy()
    top["pair"] = top["batter1"] + " & " + top["batter2"]
    if "highest_stand" in top.columns:      # group_by=pair
        hover, title = ["stands", "highest_stand", "balls"], "Top partnerships by total runs"
    else:                                   # group_by=stand
        top["pair"] += " (" + top["date"].astype(str) + ")"
        hover, title = ["balls", "wicket_no", "team", "opposition"], "Highest individual stands"
    fig = px.bar(top, x="pair", y="runs", color="strike_rate", color_continuous_scale="Greens", hover_data=hover,
                 title=f"{title} ({subtitle(result)})",
                 labels={"pair": "Partnership", "runs": "Runs", "strike_rate": "SR"})
    fig.update_layout(xaxis_tickangle=-45, height=480)
    return fig
