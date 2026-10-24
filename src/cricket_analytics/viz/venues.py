"""Venue figures (moved from the old B6 plot). Input: api.Result from run('venues', ...)."""

import plotly.express as px
import plotly.graph_objects as go

from . import PALETTE as C
from . import subtitle


def figure(result):
    df = result.data
    if df.empty:
        return go.Figure().update_layout(title="No venue data for these filters")
    if "season" in df.columns:
        x = df["season"].astype(str)
        fig = go.Figure()
        fig.add_bar(x=x, y=df["avg_1st_innings"], name="Avg 1st innings", marker_color=C["primary"])
        fig.add_bar(x=x, y=df["avg_2nd_innings"], name="Avg 2nd innings", marker_color=C["secondary"])
        fig.update_layout(title=f"Average innings scores by season ({subtitle(result)})", barmode="group",
                          xaxis_title="Season", yaxis_title="Runs", height=400)
        return fig
    return px.scatter(df.head(25), x="avg_1st_innings", y="bat_first_win_pct", size="matches", hover_name="venue",
                      color="avg_1st_innings", color_continuous_scale="RdYlGn",
                      title=f"Venues: average 1st innings score vs bat-first win % ({subtitle(result)})",
                      labels={"avg_1st_innings": "Avg 1st innings", "bat_first_win_pct": "Bat-first win %"})
