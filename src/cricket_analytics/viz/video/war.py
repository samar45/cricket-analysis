"""WAR for video: top-5 leaderboard of WAR (view=season) or projected WAR for IPL 2027 (view=projected)."""

from . import hbars, message_card, num, scope_text, short_names, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Wins above replacement", "No players for these filters", note)
    proj = "ipl_balls_2023_on" in df.columns
    col = next(c for c in ("pwar", "bat_pwar", "bowl_pwar", "main_war", "war") if c in df.columns)
    d = df.sort_values(col, ascending=False).head(5)
    names = (
        short_names(d.player)
        if proj
        else [f"{n} {s}" for n, s in zip(short_names(d.player), d.season)]
    )
    return hbars(
        names,
        d[col].clip(lower=0),
        "Projected wins, IPL 2027" if proj else "Most wins above replacement",
        aspect,
        ("a prediction from earlier seasons | " if proj else "about 100 runs added = 1 win | ")
        + scope_text(result, default="IPL"),
        note,
        fmt=lambda v: "+" + num(v, 2),
    )
