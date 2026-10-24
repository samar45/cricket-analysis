"""Figure for the `pace_vs_spin` module (EXPERIMENTAL: bowler type is guessed)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, bars_height, bubble, labels, style

_NOTE = "EXPERIMENTAL: bowler type is guessed from when he bowls"
_TYPES = (("Pace", PALETTE["bad"]), ("Spin", PALETTE["primary"]))


def figure(result) -> go.Figure:
    d = result.data
    if "pp_pct" in d.columns:   # bowler_classification
        top = d.head(30)        # busiest 30: enough to see the two clusters without a hairball
        fig = go.Figure()
        for t, c in _TYPES:
            s = top[top.bowler_type == t]
            fig.add_scatter(x=s.death_pct, y=s.mid_pct, mode="markers+text", name=t, text=labels(s.bowler, 6),
                            textposition="top center", textfont=dict(size=11), customdata=s[["bowler", "matches"]].values,
                            hovertemplate="<b>%{customdata[0]}</b><br>death %{x}%, middle %{y}%<br>%{customdata[1]} matches<extra></extra>",
                            marker=dict(**bubble(s.matches), color=c, opacity=0.75, line=dict(width=1, color="#0F131A")))
        fig.update_xaxes(title_text="Balls bowled in the death overs (%)")
        fig.update_yaxes(title_text="Balls bowled in the middle overs (%)")
        return style(fig, "Bowler types: top 30 by balls bowled", result, note=_NOTE + "; dot size = matches", height=520)
    key = "batter" if "batter" in d.columns else "team"
    piv = d[d.bowler_type.isin(["Pace", "Spin"])].pivot_table(
        index=key, columns="bowler_type", values=["strike_rate", "boundary_pct", "runs"], aggfunc="first")
    piv = piv.sort_values(("runs", "Pace"), ascending=False, na_position="last").head(12) if ("runs", "Pace") in piv.columns else piv.head(12)
    piv = piv.iloc[::-1]       # dot plots fill from the bottom: the biggest run-scorer ends up on top
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.16,
                        subplot_titles=["Strike rate: pace vs spin", "Boundary %: pace vs spin"])
    for j, col in enumerate(("strike_rate", "boundary_pct"), 1):
        for name in piv.index:   # the connecting line first, so the dots sit on top of it
            xs = [piv.loc[name, (col, t)] if (col, t) in piv.columns else None for t, _ in _TYPES]
            if all(v == v and v is not None for v in xs):
                fig.add_scatter(x=xs, y=[name, name], mode="lines", line=dict(color=PALETTE["neutral"], width=2),
                                showlegend=False, hoverinfo="skip", row=j, col=1)
        for t, c in _TYPES:
            if (col, t) in piv.columns:
                fig.add_scatter(name=f"vs {t}", y=piv.index, x=piv[(col, t)], mode="markers", marker=dict(size=12, color=c),
                                showlegend=(j == 1), row=j, col=1)
    fig.update_xaxes(title_text="Runs per 100 balls", row=1, col=1)
    fig.update_xaxes(title_text="Boundaries (% of balls)", row=2, col=1)
    who = "Batters" if key == "batter" else "Teams"
    return style(fig, f"{who}: pace vs spin, top {len(piv)} by runs against pace", result, note=_NOTE,
                 height=2 * bars_height(len(piv), 24, 0) + 230)
