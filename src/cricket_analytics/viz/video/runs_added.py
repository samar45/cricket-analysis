"""Runs added for video: top-5 leaderboard of runs added (batters or bowlers). focus = 'rate' ranks by the per-ball rate
shown instead of the total."""

from . import hbars, message_card, num, scope_text, short_names, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(
            aspect, "Runs added", "No players with enough balls for these filters", note
        )
    bat = "batter" in df.columns
    who = "batter" if bat else "bowler"
    col = (
        ("runs_added_per_100_balls" if bat else "runs_added_per_24_balls")
        if focus == "rate"
        else "runs_added"
    )
    d = df.sort_values(col, ascending=False).head(5)
    what = (
        "runs added"
        if col == "runs_added"
        else f"runs added {'per 100 balls' if bat else 'per 24 balls'}"
    )
    return hbars(
        short_names(d[who]),
        d[col].clip(lower=0),
        f"{'Batters' if bat else 'Bowlers'}: most {what}",
        aspect,
        f"above an average player in the same situation | {scope_text(result)}",
        note,
        fmt=lambda v: "+" + num(v, 0 if col == "runs_added" else 1),
    )
