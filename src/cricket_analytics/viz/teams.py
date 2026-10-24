"""Team record figure. Input: api.Result from run('teams', ...)."""

import plotly.graph_objects as go

from . import PALETTE as C
from . import bars_height, empty, style

_RESULTS = (("won", "Won", C["good"]), ("lost", "Lost", C["bad"]), ("tied", "Tied", C["secondary"]),
            ("no_result", "No result", C["neutral"]))


def figure(result):
    df = result.data
    if df.empty:
        return empty("No team data for these filters")
    if "season" in df.columns and df["team"].nunique() > 1:   # many teams: win % per season for the six busiest
        label = df["competition"] + " " + df["season"] if df["competition"].nunique() > 1 else df["season"]
        df = df.assign(x=label)
        fig = go.Figure()
        for t in df.groupby("team")["played"].sum().nlargest(6).index:
            s = df[df["team"] == t]
            fig.add_scatter(x=s["x"], y=s["win_pct"], name=t, mode="lines+markers", customdata=s[["played"]].values,
                            hovertemplate=f"<b>{t}</b> %{{x}}<br>%{{y}}% of %{{customdata[0]}} matches<extra></extra>")
        fig.update_xaxes(type="category", tickangle=-45)
        fig.update_yaxes(title_text="Win % (wins / decided matches)")
        return style(fig, "Win % per season: the six busiest teams", result)
    fig = go.Figure()
    if "season" in df.columns:   # one team over the seasons
        x = df["competition"] + " " + df["season"] if df["competition"].nunique() > 1 else df["season"]
        for col, name, colour in _RESULTS:
            fig.add_bar(x=x, y=df[col], name=name, marker_color=colour)
        fig.update_xaxes(type="category", tickangle=-45)
        fig.update_yaxes(title_text="Matches")
        fig.update_layout(barmode="stack")
        return style(fig, f"{df['team'].iloc[0]}: results by season", result)
    top = df.nlargest(15, "played").sort_values("played")   # busiest 15, the busiest on top
    for col, name, colour in _RESULTS:
        fig.add_bar(y=top["team"], x=top[col], name=name, orientation="h", marker_color=colour)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Matches")
    return style(fig, f"Team records: top {len(top)} by matches played", result, height=bars_height(len(top)))
