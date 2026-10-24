"""Figure for the `pace_vs_spin` module (EXPERIMENTAL: bowler type is guessed)."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE

_NOTE = "EXPERIMENTAL: bowler type is guessed from when he bowls"
_TYPES = (("Pace", PALETTE["bad"]), ("Spin", PALETTE["primary"]))


def figure(result) -> go.Figure:
    d = result.data
    if "pp_pct" in d.columns:   # bowler_classification
        fig = go.Figure()
        for t, c in _TYPES:
            s = d[d.bowler_type == t]
            fig.add_scatter(x=s.death_pct, y=s.mid_pct, mode="markers+text", name=t, text=s.bowler.str.split().str[-1],
                            textposition="top center", textfont=dict(size=8),
                            marker=dict(size=s.matches.clip(lower=5) * 0.8, color=c))
        fig.update_layout(title=f"Bowler classification ({_NOTE})", xaxis_title="Death-over % (higher = pace)",
                          yaxis_title="Middle-over % (higher = spin)", height=500)
        return fig
    key = "batter" if "batter" in d.columns else "team"
    piv = d[d.bowler_type.isin(["Pace", "Spin"])].pivot_table(
        index=key, columns="bowler_type", values=["strike_rate", "boundary_pct", "runs"], aggfunc="first")
    piv = piv.sort_values(("runs", "Pace"), ascending=False, na_position="last").head(15) if ("runs", "Pace") in piv.columns else piv.head(15)
    fig = make_subplots(rows=1, cols=2, subplot_titles=["Strike rate: pace vs spin", "Boundary %: pace vs spin"])
    for j, col in enumerate(("strike_rate", "boundary_pct"), 1):
        for t, c in _TYPES:
            if (col, t) in piv.columns:
                fig.add_bar(name=f"vs {t}", y=piv.index, x=piv[(col, t)].fillna(0), orientation="h", marker_color=c,
                            showlegend=(j == 1), row=1, col=j)
        fig.update_yaxes(autorange="reversed", row=1, col=j)
    fig.update_layout(title=f"{'Batters' if key == 'batter' else 'Teams'}: pace vs spin ({_NOTE})", barmode="group",
                      height=max(450, len(piv) * 35), legend=dict(orientation="h", y=-0.1))
    return fig
