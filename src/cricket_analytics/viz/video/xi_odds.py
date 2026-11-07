"""XI odds for video: win %, playoff % and title % of the chosen XI (first row) as three big numbers."""

from . import big_number_card, message_card, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "XI odds", "No XI to show", note)
    r = df.iloc[0]
    return big_number_card(
        [(f"{r.win_pct:.0f}%", "win chance vs average XII"), (f"{r.playoff_pct:.0f}%", "playoffs"), (f"{r.title_pct:.0f}%", "title")],
        f"{r.team}: {r.xi}",
        aspect,
        f"XII value {r.xii_value:+.2f} wins a season ({r.value_lo:+.1f} to {r.value_hi:+.1f}) | not a forecast",
        note,
    )
