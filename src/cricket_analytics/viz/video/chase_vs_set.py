"""Setting vs chasing for video: two big numbers (setting | chasing). Many players are pooled.
focus = average / strike_rate / win_pct (batting), economy / wickets / win_pct (bowling); default average / economy."""

from . import AMBER, INK, big_number_card, message_card, num, scope_text, source_note

LABEL = {
    "average": "batting average",
    "strike_rate": "strike rate",
    "economy": "economy",
    "wickets": "wickets",
    "runs": "runs",
    "win_pct": "team win % in big games",
}


def _pool(g, bowling, metric):
    s = g.sum(numeric_only=True)
    if metric == "average":
        return s.runs_conceded / s.wickets if bowling else s.runs / (s.innings - s.not_outs)
    if metric == "strike_rate":
        return s.runs * 100 / s.balls
    if metric == "economy":
        return s.runs_conceded * 6 / s.balls
    if metric == "win_pct":
        return s.big_wins * 100 / s.big_decided if s.big_decided else float("nan")
    return s[metric]


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    df = df[df["setting"].isin(["setting", "chasing"])]
    if df.empty:
        return message_card(aspect, "Setting vs chasing", "No innings for these filters", note)
    bowling = "economy" in df.columns
    metric = (
        focus if focus in LABEL and focus in df.columns else ("economy" if bowling else "average")
    )
    who = df["player"].iloc[0] if df["player"].nunique() == 1 else "all players"
    vals = {s: _pool(df[df["setting"] == s], bowling, metric) for s in ("setting", "chasing")}
    dec = 0 if metric in ("wickets", "runs", "win_pct") else 1
    fmt = lambda v: num(v, dec) + ("%" if metric == "win_pct" else "")  # noqa: E731
    colors = None
    if not (vals["setting"] != vals["setting"] or vals["chasing"] != vals["chasing"]):
        best_chasing = (
            (vals["chasing"] < vals["setting"])
            if metric == "economy"
            else (vals["chasing"] > vals["setting"])
        )
        colors = [INK, AMBER] if best_chasing else [AMBER, INK]
    return big_number_card(
        [
            (fmt(vals["setting"]), f"{LABEL[metric]} setting"),
            (fmt(vals["chasing"]), f"{LABEL[metric]} chasing"),
        ],
        f"{who}: setting vs chasing",
        aspect,
        scope_text(result, ("player",)),
        note,
        colors=colors,
    )
