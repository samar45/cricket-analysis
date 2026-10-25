"""Fielding figures. Input: api.Result from run('fielding', ...)."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import empty, style

_PARTS = (
    ("catches", "Catches", C["primary"]),
    ("caught_and_bowled", "Caught & bowled", C["secondary"]),
    ("stumpings", "Stumpings", C["good"]),
    ("run_outs", "Run-outs", C["bad"]),
)


def figure(result):
    df = result.data
    if df.empty:
        return empty("No fielding data for these filters")
    by_season = "season" in df.columns
    if by_season:  # one fielder's seasons, oldest first
        d = df[df["fielder"] == df.groupby("fielder")["total_dismissals"].sum().idxmax()]
        x, orient, title = d["season"], "v", f"{d['fielder'].iloc[0]}: dismissals per season"
    else:
        d = df.sort_values("total_dismissals", ascending=False).head(15)
        x, orient, title = d["fielder"], "h", "Fielding dismissals"
    fig = go.Figure()
    for col, name, colour in _PARTS:
        fig.add_bar(
            name=name,
            x=x if orient == "v" else d[col],
            y=d[col] if orient == "v" else x,
            orientation=orient,
            marker_color=colour,
        )
    fig.update_layout(barmode="stack")
    if orient == "h":
        fig.update_yaxes(autorange="reversed")
    return style(fig, title, result, height=420 if by_season else 160 + 32 * len(d))
