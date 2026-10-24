"""Figure for the `impact` module."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE


def _filters(result) -> str:
    """'ipl, 2024' - only the data filters, not the module's own knobs (weights, award, ...)."""
    keep = ("player", "competition", "season", "team", "opposition", "venue", "phase")
    return ", ".join(str(v) for k, v in result.meta["params"].items() if k in keep)


def figure(result) -> go.Figure:
    top = result.data.head(15)
    fig = make_subplots(rows=1, cols=2, column_widths=[0.55, 0.45],
                        subplot_titles=["Total impact: batting vs bowling", "Average impact per match"])
    fig.add_bar(name="Batting impact", y=top.player, x=top.bat_impact, orientation="h",
                marker_color=PALETTE["good"], row=1, col=1)
    fig.add_bar(name="Bowling impact", y=top.player, x=top.bowl_impact, orientation="h",
                marker_color=PALETTE["primary"], row=1, col=1)
    avg = top.sort_values("avg_impact")
    fig.add_scatter(x=avg.avg_impact, y=avg.player, mode="markers+text", text=[f"{v:.1f}" for v in avg.avg_impact],
                    textposition="middle right", marker=dict(size=11, color=PALETTE["secondary"]),
                    showlegend=False, row=1, col=2)
    fig.update_layout(title="Player impact score " + f"({_filters(result)})", barmode="stack",
                      height=max(500, len(top) * 35), legend=dict(orientation="h", y=-0.12))
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    return fig
