"""Scarcity module for video: the five scarcest roles in an auction (1.0 = the auction's average role)."""

from . import hbars, message_card, num, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty or "relative" not in df.columns:
        return message_card(
            aspect, "IPL auction: scarce roles", "Pick the auction view to see scarce roles", note
        )
    d = df.sort_values("relative", ascending=False).head(5)
    return hbars(
        [str(r) for r in d.role],
        d.relative,
        "Scarcest roles (1.0 = average)",
        aspect,
        "teams needing it vs good players on offer | scarcity did not move prices 2022-26",
        note,
        fmt=lambda v: num(v, 1),
    )
