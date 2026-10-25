"""Impact for video: leaderboard of the top 10 by total impact score (horizontal bars, name above each bar)."""

from . import hbars, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(
            aspect, "Impact", "No players reach the minimum matches for these filters", note
        )
    d = df.sort_values("total_impact", ascending=False).head(10 if aspect == "9:16" else 6)
    return hbars(
        d["player"],
        d["total_impact"],
        "Most impactful players",
        aspect,
        f"impact score (our own formula) | {scope_text(result)}",
        note,
        fmt=lambda v: num(v, 0),
    )
