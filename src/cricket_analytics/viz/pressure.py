"""Figures for the `pressure` module: grouped bars, under pressure vs calm chase balls (batting or bowling, told apart by columns).

Many players: one pair of bars per player (strike rate or economy). One player: a pair for the rate and a pair for the average / wickets per 100 balls is
too busy, so it shows the rate and the average side by side."""

import plotly.graph_objects as go

from . import PALETTE, empty, short, style

TOP = 12


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players with enough pressure balls for these filters")
    bat = "batter" in d.columns
    who, p, c, name, dec = (("batter", "pressure_sr", "calm_sr", "Strike rate", 0) if bat
                            else ("bowler", "pressure_economy", "calm_economy", "Economy", 2))
    level = result.meta["params"].get("level", "high")
    if len(d) == 1 or result.meta["params"].get("player"):
        r = d.iloc[0]
        pb, cb = (r.pressure_balls, r.calm_balls) if bat else (r.pressure_legal_balls, r.calm_legal_balls)
        if bat:
            cats, pv, cv = ["Strike rate", "Average"], [r.pressure_sr, r.pressure_avg], [r.calm_sr, r.calm_avg]
        else:
            cats, pv, cv = ["Economy"], [r.pressure_economy], [r.calm_economy]
        title = f"{r[who]}: under pressure vs calm chase balls"
        note = f"{int(pb):,} pressure balls, {int(cb):,} calm balls; pressure level: {level}"
        height = 420
    else:
        t = d.head(TOP)
        cats, pv, cv = [short(x, 16) for x in t[who]], list(t[p]), list(t[c])
        title = f"{name} under pressure vs calm: top {len(t)} by pressure {name.lower()}" if bat else f"Economy under pressure vs calm: best {len(t)}"
        note = f"pressure level: {level}; chases only, D/L and shortened matches left out"
        height = 480
    fig = go.Figure([
        go.Bar(name="Under pressure", x=cats, y=pv, marker_color=PALETTE["bad"], text=[_t(v, dec) for v in pv], textposition="outside"),
        go.Bar(name="Calm chase", x=cats, y=cv, marker_color=PALETTE["neutral"], text=[_t(v, dec) for v in cv], textposition="outside"),
    ])
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_yaxes(title_text=("Strike rate (runs per 100 balls) / average" if bat and len(cats) == 2 and cats[0] == "Strike rate" else
                                 "Strike rate (runs per 100 balls)" if bat else "Economy (runs per over)"))
    return style(fig, title, result, note=note, height=height)


def _t(v, dec):
    return "" if v != v or v is None else f"{v:.{dec}f}"
