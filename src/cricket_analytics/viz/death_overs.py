"""Figures for the `death_overs` module (batting or bowling, told apart by the columns).

One player: two bars, overall vs the death overs, with the number of balls under each. Many players: the index as a
ranked bar chart that starts at 100 ("same as overall"), the two rates as small text."""

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, style

TOP = 15


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No players with enough death-over balls for these filters")
    bat = "batter" in d.columns
    who, a, b, name, unit = (("batter", "overall_sr", "death_sr", "Strike rate", "runs per 100 balls") if bat
                             else ("bowler", "overall_economy", "death_economy", "Economy", "runs per over"))
    if len(d) == 1 or result.meta["params"].get("player"):
        return _one(d.iloc[0], who, a, b, name, unit, bat, result)
    top = d.head(TOP).iloc[::-1]       # the module sorts by index, highest first; the horizontal axis draws the first row at the bottom
    gap = top.death_index - 100
    fig = go.Figure(go.Bar(
        y=top[who], x=gap, base=100, orientation="h", cliponaxis=False,
        marker_color=[PALETTE["good"] if g >= 0 else PALETTE["bad"] for g in gap],
        text=[f"{r.death_index:.0f}  ({getattr(r, a):.{0 if bat else 1}f} to {getattr(r, b):.{0 if bat else 1}f})" for r in top.itertuples()],
        textposition="outside", textfont=dict(size=11),
        customdata=top[[a, b, "death_balls", "death_index"]].values,
        hovertemplate=f"<b>%{{y}}</b><br>index %{{customdata[3]}}<br>overall {name.lower()} %{{customdata[0]}}, death %{{customdata[1]}}"
                      f"<br>%{{customdata[2]}} death-over balls<extra></extra>"))
    lo, hi = min(100, top.death_index.min()), max(100, top.death_index.max())
    pad = (hi - lo) * 0.5 + 10        # room for the text at the end of the longest bar
    fig.update_xaxes(title_text=f"Death-overs index (100 = same as overall {name.lower()})", range=[lo - 6, hi + pad])
    fig.add_vline(x=100, line=dict(color=PALETTE["neutral"], width=2, dash="dash"),
                  annotation=dict(text="same as overall", font=dict(size=11), yanchor="bottom"), annotation_position="top")
    return style(fig, f"Death-overs index: top {len(top)} by index", result,
                 note=f"label = index (overall {name.lower()} to death {name.lower()}); green = better at the death",
                 height=bars_height(len(top), 28, 190))


def _one(r, who, a, b, name, unit, bat, result) -> go.Figure:
    dec = 0 if bat else 1
    overall = f"Overall<br>{int(r.total_balls):,} balls" if bat else "Overall"
    vals = [float(r[a]), float(r[b])]
    fig = go.Figure(go.Bar(
        x=[overall, f"Death overs<br>{int(r.death_balls):,} balls"], y=vals, width=0.5, cliponaxis=False,
        marker_color=[PALETTE["neutral"], PALETTE["good"] if r.death_index >= 100 else PALETTE["bad"]],
        text=[f"{v:.{dec}f}" for v in vals], textposition="outside", textfont=dict(size=16)))
    fig.update_yaxes(title_text=f"{name} ({unit})", range=[0, max(vals) * 1.2])
    verdict = "better" if r.death_index >= 100 else "worse"
    return style(fig, f"{r[who]}: {name.lower()} overall vs death overs", result,
                 note=f"index {r.death_index:.0f} ({verdict} at the death than overall), {int(r.death_innings)} innings with death-over balls",
                 height=420)
