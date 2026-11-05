"""Figures for `matchup_predict`: a card (this matchup against the league, per ball) or, for view=grid, a heat-map of
expected runs per over by bowling type and phase."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import empty, style
from ..sql.fragments import PHASES


def _who(r) -> str:
    vs = r["bowler"] or (r["bowl_type"] if r["bowl_type_source"] != "none" else "a typical bowler")
    return f"{r['batter']} v {vs}"


def figure(result):
    df = result.data
    if df.empty:
        return empty("No prediction for these filters")
    if len(df) > 1:
        return _heatmap(df, result)
    r = df.iloc[0]
    cats = ["Dot", "Four", "Six", "Wicket"]
    mine = [r.dot_pct, r.four_pct, r.six_pct, r.out_pct]
    lg = [r.league_dot_pct, r.league_four_pct, r.league_six_pct, r.league_out_pct]
    fig = go.Figure()
    for name, vals, col in (
        ("This matchup", mine, C["primary"]),
        ("League, same phase and state", lg, C["neutral"]),
    ):
        fig.add_bar(
            name=name,
            x=cats,
            y=vals,
            marker_color=col,
            text=[f"{v:.1f}%" for v in vals],
            textposition="outside",
        )
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="Chance on one ball (%)")
    when = f"{r.phase} overs" if r.phase != "all" else "all phases"
    note = (
        f"{r.exp_runs_per_6:.1f} runs an over ({r.vs_typical_runs_per_6:+.1f} v league), wicket every {r.balls_per_dismissal:.0f} balls | "
        f"confidence {r.confidence}: {int(r.pair_balls)} balls v him, {int(r.batter_type_balls)} v this type, {int(r.batter_balls)} overall"
    )
    return style(fig, f"{_who(r)}, {when}: per-ball chances", result, note=note, height=470)


def _heatmap(df, result):
    d = df[df.phase.isin(PHASES)]
    z = d.pivot(index="bowl_type", columns="phase", values="exp_runs_per_6")[list(PHASES)]
    out = d.pivot(index="bowl_type", columns="phase", values="out_pct")[list(PHASES)]
    mid = float(d.league_exp_runs_per_6.mean())
    fig = go.Figure(
        go.Heatmap(
            z=z.values,
            x=[p.capitalize() for p in PHASES],
            y=list(z.index),
            zmid=mid,
            colorscale=[[0, C["bad"]], [0.5, "#2B313C"], [1, C["good"]]],
            text=[
                [f"{a:.1f} runs | {b:.1f}% out" for a, b in zip(ra, rb)]
                for ra, rb in zip(z.values, out.values)
            ],
            texttemplate="%{text}",
            hovertemplate="%{y}, %{x}<br>%{text}<extra></extra>",
            colorbar=dict(title="runs / over"),
        )
    )
    fig.update_yaxes(autorange="reversed")
    note = "Expected runs per over, chance of a wicket per ball | green = above the league average of the same cells"
    return style(
        fig, f"{df.batter.iloc[0]} against each bowling type", result, note=note, height=520
    )
