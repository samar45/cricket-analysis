"""Innings list figure: one bar per innings (runs) or spell (wickets) in date order. Input: run('innings_list', ...)."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import empty, short, style


def figure(result):
    df = result.data
    p = result.meta["params"]
    if df.empty:
        return empty("No innings for these filters")
    df = df.sort_values(["date", "match_id", "innings"])
    bat = p.get("role", "batting") == "batting"
    col = "runs" if bat else "wickets"
    who = p.get("player") or "All players"
    x = [
        f"{pd_date:%d %b %y}<br>v {short(o, 14)}"
        for pd_date, o in zip(df["date"], df["opposition"])
    ]
    text = df["score"] if bat else df["figures"]
    colours = (
        [C["good"] if h == "not out" else C["primary"] for h in df["how_out"]]
        if bat
        else [C["secondary"] if w >= 3 else C["primary"] for w in df["wickets"]]
    )
    hover = (
        df["player"] + " | " + df["venue"].astype(str) + " | " + df["result"].astype(str)
    ).tolist()
    fig = go.Figure(
        go.Bar(
            x=x,
            y=df[col],
            text=text,
            textposition="outside",
            marker_color=colours,
            customdata=hover,
            hovertemplate="%{customdata}<br>%{text}<extra></extra>",
            cliponaxis=False,
        )
    )
    fig.update_yaxes(title_text="Runs" if bat else "Wickets")
    fig.update_layout(bargap=0.25, showlegend=False)
    order = {"first": "first", "last": "latest", "best": "best"}[p.get("order", "last")]
    return style(
        fig,
        f"{who}: {order} {len(df)} {'innings' if bat else 'spells'}",
        result,
        note="bars: green = not out" if bat else "bars: orange = 3+ wickets",
        height=420,
    )
