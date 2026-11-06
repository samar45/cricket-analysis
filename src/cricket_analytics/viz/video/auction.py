"""Auction module for video: top-5 by model median price, or WAR per 10 crore by buy type."""

from . import hbars, message_card, num, scope_text, short_names, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "IPL auction", "Nothing to show for these filters", note)
    if "war_per_10cr" in df.columns:
        d = df.sort_values("war_per_10cr", ascending=False).head(5)
        return hbars(
            [str(x) for x in d[df.columns[0]]],
            d.war_per_10cr.clip(lower=0),
            "Wins per 10 crore spent",
            aspect,
            "one season of WAR after the auction | mostly luck",
            note,
            fmt=lambda v: num(v, 2),
        )
    d = df.sort_values("p50_cr", ascending=False).head(5)
    return hbars(
        short_names(d.player),
        d.p50_cr,
        "Model median auction price (crore)",
        aspect,
        "a weak prediction, made before the auction | " + scope_text(result),
        note,
        fmt=lambda v: num(v, 1),
    )
