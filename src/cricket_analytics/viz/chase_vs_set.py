"""Setting vs chasing figures. Input: api.Result from run('chase_vs_set', ...)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE as C
from . import empty, style

SET, CHASE = "setting", "chasing"


def _bars(fig, d, x, y, row=None, col=None, fmt="%{y}"):
    for s, colour in ((SET, C["primary"]), (CHASE, C["secondary"])):
        t = d[d["setting"] == s]
        fig.add_bar(
            name=s,
            x=t[x],
            y=t[y],
            marker_color=colour,
            text=t[y],
            textposition="outside",
            cliponaxis=False,
            showlegend=row in (None, 1),
            legendgroup=s,
            row=row,
            col=col,
        )


def figure(result):
    df = result.data
    if df.empty:
        return empty("No innings for these filters")
    bowling = "economy" in df.columns
    df = df[df["setting"].isin([SET, CHASE])]
    first = "economy" if bowling else "average"
    if df["player"].nunique() == 1:  # three panels: the two headline numbers and the win %
        panels = [first, "wickets" if bowling else "strike_rate", "win_pct"]
        names = [
            "Economy (runs per over)" if bowling else "Average (runs per dismissal)",
            "Wickets" if bowling else "Strike rate (runs per 100 balls)",
            f"Team win % in big games ({'2+ wickets' if bowling else '30+ runs'})",
        ]
        fig = make_subplots(rows=1, cols=3, subplot_titles=names, horizontal_spacing=0.09)
        for i, m in enumerate(panels, 1):
            _bars(fig, df.assign(x=m), "x", m, row=1, col=i)
            fig.update_xaxes(visible=False, row=1, col=i)
        fig.update_layout(barmode="group")
        return style(
            fig,
            f"{df['player'].iloc[0]}: setting vs chasing",
            result,
            note="setting = 1st innings, chasing = 2nd",
            height=420,
        )
    top = (
        df.groupby("player")["innings"].sum().nlargest(10).index
    )  # many players: one metric, grouped by player
    d = df[df["player"].isin(top)]
    fig = go.Figure()
    _bars(fig, d, "player", first)
    fig.update_layout(barmode="group")
    fig.update_yaxes(
        title_text="Economy (runs per over)" if bowling else "Average (runs per dismissal)"
    )
    return style(
        fig,
        f"{'Economy' if bowling else 'Average'}: setting vs chasing (top 10 by innings)",
        result,
    )
