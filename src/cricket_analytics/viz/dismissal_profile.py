"""Dismissal profile figures. Input: api.Result from run('dismissal_profile', ...)."""

import plotly.graph_objects as go

from ..analysis.dismissal_profile import KINDS
from . import empty, style

COLOUR = dict(zip(KINDS, ["#2196F3", "#EF5350", "#FF9800", "#FFC107", "#4CAF50", "#9E9E9E", "#E91E63", "#607D8B"]))


def figure(result):
    df = result.data
    if df.empty:
        return empty("No dismissals for these filters")
    grp = next((c for c in ("phase", "bowler_kind") if c in df.columns), None)
    if grp is None:   # one stacked bar per batter (top 12 by outs); % of his outs
        top = df.groupby("batter")["outs"].sum().nlargest(12).index
        d, y = df[df["batter"].isin(top)], "batter"
    else:             # pool the batters, one stacked bar per phase / bowler kind
        d = df.groupby([grp, "kind"], as_index=False)["outs"].sum()
        d["pct"] = (d["outs"] * 100 / d.groupby(grp)["outs"].transform("sum")).round(1)
        d, y = d, grp
    fig = go.Figure()
    for k in KINDS:
        s = d[d["kind"] == k]
        if not s.empty:
            fig.add_bar(name=k, y=s[y], x=s["pct"], orientation="h", marker_color=COLOUR[k], customdata=s["outs"],
                        hovertemplate="%{y}: %{customdata} outs (%{x}%)<extra>" + k + "</extra>")
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="% of dismissals", range=[0, 100])
    fig.update_yaxes(autorange="reversed")
    who = df["batter"].iloc[0] if df["batter"].nunique() == 1 else "batters"
    by = {None: "", "phase": " by phase", "bowler_kind": " by pace / spin"}[grp]
    return style(fig, f"How {who} gets out{by}", result, height=300 + 40 * d[y].nunique())
