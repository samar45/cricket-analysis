"""Venues for video: batting first vs chasing, as a donut over all rows in the result (one venue, or everything the
filters select). The middle number is the bat-first win %."""

from . import AMBER, INK, donut, message_card, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note, sub = result.data, source_note(result), scope_text(result, ("venue",))
    if df.empty or df["decided"].sum() == 0:
        return message_card(
            aspect, "Bat first or chase?", "No decided matches for these filters", note
        )
    decided, first = int(df["decided"].sum()), int(df["bat_first_wins"].sum())
    where = df["venue"].iloc[0] if "venue" in df.columns and df["venue"].nunique() == 1 else None
    return donut(
        ["Batting first won", "Chasing won"],
        [first, decided - first],
        f"{where}: bat first or chase?" if where else "Bat first or chase?",
        aspect,
        f"{decided} decided matches | {sub}",
        note,
        center=(f"{first / decided * 100:.0f}%", "bat-first wins"),
        colors=[AMBER, INK],
    )
