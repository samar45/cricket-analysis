"""Underrated for video: top 10 by underrated score (a heuristic, said in the subtitle)."""

from . import hbars, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Underrated", "No players pass the minimum balls", note)
    p = result.meta["params"]
    d = df.head(10 if aspect == "9:16" else 6)
    return hbars(
        d["player"],
        d["underrated_score"],
        f"Underrated {p['role'].replace('ing', 'ers')}",
        aspect,
        f"strong numbers, few matches (our own score) | {scope_text(result, ())}",
        note,
        fmt=lambda v: num(v, 0),
    )
