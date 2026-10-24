"""Home vs away for video: two big numbers, home on top. One player or team (the busiest if several).
`focus` picks the metric (e.g. 'strike_rate', 'win_pct'); the default is the module's headline number."""

from . import big_number_card, message_card, num, scope_text, source_note

HEADLINE = {"batter": ("average", "batting average"), "bowler": ("economy", "economy"), "team": ("win_pct", "win %")}
LABELS = {"average": "batting average", "strike_rate": "strike rate", "economy": "economy", "win_pct": "win %",
          "avg_runs_for": "runs per innings", "wickets": "wickets", "total_runs": "runs"}


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Home vs away", "No home/away data for these filters", note)
    ent = next(c for c in ("batter", "bowler", "team") if c in df.columns)
    who = df.groupby(ent)["matches"].sum().idxmax()
    d = df[df[ent] == who].set_index("location")
    col = focus if focus in df.columns else HEADLINE[ent][0]
    if "home" not in d.index or "away" not in d.index:
        return message_card(aspect, f"{who}: home vs away", "Needs both home and away matches", note)
    suffix = "%" if col == "win_pct" else ""
    stats = [(num(d.loc[loc, col]) + suffix, f"{loc} {LABELS.get(col, col)} ({d.loc[loc, 'matches']} matches)") for loc in ("home", "away")]
    neutral = f" | neutral {num(d.loc['neutral', col])}{suffix}" if "neutral" in d.index else ""
    return big_number_card(stats, f"{who}: home vs away", aspect, scope_text(result, ("player", "team")) + neutral, note)
