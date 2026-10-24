"""Death overs for video: two bars, the same player overall vs in the death overs (strike rate for batters,
economy for bowlers). focus = player name; default = the top row (highest death index)."""

from . import columns, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Death overs", "No players with enough death-over balls for these filters", note)
    bat = "batter" in df.columns
    who_col, a, b = ("batter", "overall_sr", "death_sr") if bat else ("bowler", "overall_economy", "death_economy")
    pick = df[df[who_col] == focus] if focus else df
    r = (pick if not pick.empty else df).iloc[0]
    sub = f"{'strike rate' if bat else 'economy, runs per over'} | {int(r.death_balls)} death-over balls | {scope_text(result)}"
    dec = 0 if bat else 1
    return columns(["All overs", "Death overs"], [r[a], r[b]], f"{r[who_col]}: overall vs death overs", aspect, sub, note,
                   highlight=[1], fmt=lambda v: num(v, dec))
