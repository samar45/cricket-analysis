"""Trade tool for video: two big numbers (each team's change in best-XII value, with the verdict) or a top-5 squad bar chart."""

from ...models.trade import FULL_TO_ABBR
from . import AMBER, RED, INK, big_number_card, hbars, message_card, num, short_names, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Trade check", "No trade to show", note)
    if "verdict" not in df.columns:
        d = df.head(5)
        return hbars(
            short_names(d.player),
            d.recent_value.clip(lower=0),
            "Most valuable players, recent form",
            aspect,
            "wins above replacement a season, IPL 2023-26 | not a forecast",
            note,
            fmt=lambda v: "+" + num(v, 2),
        )
    a, b = (FULL_TO_ABBR.get(t, t) for t in df.team)
    stats, colours = [], []
    for r in df.itertuples():
        stats.append((f"{r.change:+.2f}", f"{FULL_TO_ABBR.get(r.team, r.team)}: {r.verdict}"))
        colours.append(AMBER if r.change > 0 else RED if r.change < 0 else INK)
    return big_number_card(
        stats,
        f"Trade check: {a} v {b}",
        aspect,
        "change in best-XII value, wins a season | "
        + " | ".join(
            f"{FULL_TO_ABBR.get(r.team, r.team)} range {r.change_lo:+.1f} to {r.change_hi:+.1f}"
            for r in df.itertuples()
        ),
        note,
        colors=colours,
    )
