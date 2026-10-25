"""True performance for video: two bars, raw vs adjusted (strike rate for batters, economy for bowlers).
focus = player name; default = the top row (best true rate)."""

from . import columns, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(
            aspect, "True performance", "No players with enough balls for these filters", note
        )
    bat = "batter" in df.columns
    who_col, a, b = (
        ("batter", "raw_sr", "true_sr") if bat else ("bowler", "raw_economy", "true_economy")
    )
    pick = df[df[who_col] == focus] if focus else df
    r = (pick if not pick.empty else df).iloc[0]
    sub = f"{'strike rate' if bat else 'economy'}, judged against the league in the same phases | {scope_text(result)}"
    dec = 0 if bat else 2
    return columns(
        ["Raw", "Adjusted"],
        [r[a], r[b]],
        f"{r[who_col]}: raw vs adjusted",
        aspect,
        sub,
        note,
        highlight=[1],
        fmt=lambda v: num(v, dec),
    )
