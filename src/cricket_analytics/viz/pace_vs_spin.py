"""Figures for the `pace_vs_spin` module (bowling-type matchups).

- bowler_types: the busiest bowlers, bar length = balls bowled, colour = pace / spin, text = bowling type.
- one batter or team: strike rate by pace / spin, boundary and dot %, and (detail=true) strike rate by bowling type.
- many batters or teams: the old dot plot, strike rate and boundary % against pace and against spin.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import PALETTE, bars_height, empty, short, style

_KINDS = (("Pace", PALETTE["bad"]), ("Spin", PALETTE["primary"]))
_COLOR = dict(_KINDS, Unknown=PALETTE["neutral"])


def _type_color(name: str) -> str:
    if name == "Unknown type":
        return PALETTE["neutral"]
    return _COLOR["Spin"] if ("spin" in name or "orthodox" in name) else _COLOR["Pace"]


def _known_share(d: pd.DataFrame, key: str) -> float | None:
    """Share of the subjects' balls whose bowler has a pace/spin label (pct_of_balls is relative to ALL balls, also hidden rows)."""
    k = d[d.level == "kind"]
    if k.empty or "pct_of_balls" not in k:
        return None
    big = k.loc[k.groupby(key).balls.idxmax()].set_index(key)   # the biggest row of each subject has the least rounding error
    total = big.balls * 100 / big.pct_of_balls
    known = k[k.bowler_type.isin(["Pace", "Spin"])].groupby(key).balls.sum()
    return float(known.sum() / total.loc[known.index].sum() * 100) if len(known) else None


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No balls for these filters")
    if "bowl_kind" in d.columns:
        return _bowlers(d, result)
    key = "batter" if "batter" in d.columns else "team"
    share = _known_share(d, key)
    note = "" if share is None else f"pace/spin known for {share:.0f}% of these balls"
    if d[key].nunique() == 1:
        return _one(d, key, result, note)
    return _many(d, key, result, note)


def _bowlers(d, result):
    top = d.head(15).iloc[::-1]
    fig = go.Figure()
    for kind, c in (*_KINDS, ("unknown", PALETTE["neutral"])):
        s = top[top.bowl_kind == kind.lower()]
        fig.add_bar(y=s.bowler, x=s.balls, name=kind, orientation="h", marker_color=c, cliponaxis=False,
                    text=[f"{t or 'type unknown'} ({src or 'no source'})" for t, src in zip(s.bowl_type, s.kind_source)],
                    textposition="outside", textfont=dict(size=11))
    fig.update_xaxes(title_text="Legal balls bowled", range=[0, top.balls.max() * 1.6])
    return style(fig, f"Bowlers and their labels: top {len(top)} by balls", result,
                 note="text = bowling type (where the label came from); grey = no label", height=bars_height(len(top), 28, 200))


def _one(d, key, result, note):
    who = d[key].iloc[0]
    kinds = d[(d.level == "kind") & d.bowler_type.isin(["Pace", "Spin"])].set_index("bowler_type").reindex(["Pace", "Spin"]).dropna(subset=["balls"])
    types = d[d.level == "type"].sort_values("strike_rate")
    if kinds.empty:
        return empty("No balls against bowlers with a pace / spin label for these filters")
    rows = 3 if len(types) else 2
    fig = make_subplots(rows=rows, cols=1, vertical_spacing=0.14, row_heights=[1, 1, 2][:rows],
                        subplot_titles=["Strike rate (runs per 100 balls)", "Boundary % and dot % of balls",
                                        "Strike rate by bowling type (balls faced in brackets)"][:rows])
    fig.add_bar(y=kinds.index, x=kinds.strike_rate, orientation="h", row=1, col=1, showlegend=False, cliponaxis=False,
                marker_color=[_COLOR[k] for k in kinds.index], textposition="outside",
                text=[f"{r.strike_rate:.0f}  ({int(r.runs)} off {int(r.balls)})" for r in kinds.itertuples()])
    for col, name, c in (("boundary_pct", "Boundary %", PALETTE["good"]), ("dot_pct", "Dot %", PALETTE["neutral"])):
        fig.add_bar(y=kinds.index, x=kinds[col], name=name, orientation="h", row=2, col=1, marker_color=c, cliponaxis=False,
                    text=[f"{v:.0f}%" for v in kinds[col]], textposition="outside")
    fig.update_yaxes(autorange="reversed", row=1, col=1)
    fig.update_yaxes(autorange="reversed", row=2, col=1)
    fig.update_xaxes(range=[0, kinds.strike_rate.max() * 1.45], row=1, col=1)
    fig.update_xaxes(range=[0, max(kinds.boundary_pct.max(), kinds.dot_pct.max()) * 1.3], row=2, col=1)
    fig.update_layout(barmode="group")
    if rows == 3:
        fig.add_bar(y=[f"{short(t, 22)} ({int(b)})" for t, b in zip(types.bowler_type, types.balls)], x=types.strike_rate,
                    orientation="h", row=3, col=1, showlegend=False, cliponaxis=False,
                    marker_color=[_type_color(t) for t in types.bowler_type],
                    text=[f"{v:.0f}" for v in types.strike_rate], textposition="outside")
        fig.update_xaxes(range=[0, types.strike_rate.max() * 1.2], row=3, col=1)
    extra = "; red = pace, blue = spin" if rows == 3 else ""
    return style(fig, f"{who} against pace and spin", result, note=note + extra,
                 height=(560 if rows == 2 else 560 + bars_height(len(types), 26, 0)))


def _many(d, key, result, note):
    piv = d[(d.level == "kind") & d.bowler_type.isin(["Pace", "Spin"])].pivot_table(
        index=key, columns="bowler_type", values=["strike_rate", "boundary_pct", "runs"], aggfunc="first")
    if piv.empty:
        return empty("No balls against bowlers with a pace / spin label for these filters")
    piv = piv.sort_values(("runs", "Pace"), ascending=False, na_position="last").head(12) if ("runs", "Pace") in piv.columns else piv.head(12)
    piv = piv.iloc[::-1]       # dot plots fill from the bottom: the biggest run-scorer ends up on top
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.16,
                        subplot_titles=["Strike rate: pace vs spin", "Boundary %: pace vs spin"])
    for j, col in enumerate(("strike_rate", "boundary_pct"), 1):
        for name in piv.index:   # the connecting line first, so the dots sit on top of it
            xs = [piv.loc[name, (col, t)] if (col, t) in piv.columns else None for t, _ in _KINDS]
            if all(v == v and v is not None for v in xs):
                fig.add_scatter(x=xs, y=[name, name], mode="lines", line=dict(color=PALETTE["neutral"], width=2),
                                showlegend=False, hoverinfo="skip", row=j, col=1)
        for t, c in _KINDS:
            if (col, t) in piv.columns:
                fig.add_scatter(name=f"vs {t}", y=piv.index, x=piv[(col, t)], mode="markers", marker=dict(size=12, color=c),
                                showlegend=(j == 1), row=j, col=1)
    fig.update_xaxes(title_text="Runs per 100 balls", row=1, col=1)
    fig.update_xaxes(title_text="Boundaries (% of balls)", row=2, col=1)
    who = "Batters" if key == "batter" else "Teams"
    return style(fig, f"{who}: pace vs spin, top {len(piv)} by runs against pace", result, note=note,
                 height=2 * bars_height(len(piv), 24, 0) + 230)
