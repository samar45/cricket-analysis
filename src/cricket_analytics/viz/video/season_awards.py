"""Season awards for video: a podium of the top 3 in ONE phase of the newest season in the result.
focus = phase name (powerplay / middle / death); default = the first phase in the data."""

from . import message_card, podium, scope_text, short_names, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty or not {"phase", "rank", "player"} <= set(df.columns):
        return message_card(aspect, "Season awards", "Podium needs the phase-leaders table", note)
    d = df[df["season"] == df["season"].iloc[0]]  # newest season first
    phase = focus if focus in set(d["phase"]) else d["phase"].iloc[0]
    d = d[d["phase"] == phase].sort_values("rank").head(3)
    bat = "runs" in d.columns
    metric = "runs" if bat else "wickets"
    names = short_names(list(d["player"]))
    title = f"{phase} {'batters' if bat else 'bowlers'}: top {len(d)}"
    sub = (
        f"{d['competition'].iloc[0].upper()} {d['season'].iloc[0]}"
        if "competition" in d
        else scope_text(result)
    )
    return podium(names, list(d[metric]), title, aspect, sub, note, unit=metric)
