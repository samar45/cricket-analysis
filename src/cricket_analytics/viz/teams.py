"""Team record figure (moved from the old B3 plot). Input: api.Result from run('teams', ...)."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import subtitle


def figure(result):
    df = result.data
    if df.empty:
        return go.Figure().update_layout(title="No team data for these filters")
    x = df["season"] if "season" in df.columns else df["team"]
    fig = go.Figure()
    for col, name, colour in (("won", "Won", C["good"]), ("lost", "Lost", C["bad"]),
                              ("tied", "Tied", C["secondary"]), ("no_result", "No result", C["neutral"])):
        fig.add_bar(x=x, y=df[col], name=name, marker_color=colour)
    fig.update_layout(title=f"Team records ({subtitle(result)})", barmode="stack", xaxis_tickangle=-45,
                      yaxis_title="Matches")
    return fig
