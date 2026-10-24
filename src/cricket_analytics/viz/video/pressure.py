"""Pressure for video: big numbers, the same player under pressure vs in a calm chase. focus = player name;
default = the top row (best pressure strike rate / lowest pressure economy)."""

from . import AMBER, INK, big_number_card, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Under pressure", "No players with enough pressure balls for these filters", note)
    bat = "batter" in df.columns
    who = "batter" if bat else "bowler"
    pick = df[df[who] == focus] if focus else df
    r = (pick if not pick.empty else df).iloc[0]
    if bat:
        stats = [(num(r.pressure_sr, 0), "strike rate under pressure"), (num(r.calm_sr, 0), "strike rate when calm"),
                 (f"{int(r.pressure_balls):,}", "balls under pressure")]
        sub = f"chases only | {scope_text(result)}"
    else:
        stats = [(num(r.pressure_economy, 2), "economy under pressure"), (num(r.calm_economy, 2), "economy when calm"),
                 (f"{int(r.pressure_wickets)}", "wickets under pressure")]
        sub = f"defending | {scope_text(result)}"
    return big_number_card(stats, f"{r[who]}: under pressure", aspect, sub, note, colors=[AMBER, INK, INK])
