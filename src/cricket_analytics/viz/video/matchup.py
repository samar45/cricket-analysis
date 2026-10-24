"""Matchup for video: a head-to-head "duel" card for batter v bowler: balls, runs, times out, strike rate.
With only one player given, the duel is against the opponent they met most (first row). focus = opponent name."""

from . import AMBER, INK, RED, big_number_card, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Head to head", "These two never met in this data", note)
    pick = df[(df["bowler"] == focus) | (df["batter"] == focus)] if focus else df
    r = (pick if not pick.empty else df).iloc[0]
    sub = f"{int(r.matches)} matches | " + scope_text(result)
    stats = [(num(r.balls), "balls faced"), (num(r.runs), "runs scored"), (num(r.dismissals), "times out"),
             (num(r.strike_rate, 0), "strike rate")]
    return big_number_card(stats, f"{r.batter} vs {r.bowler}", aspect, sub, note, colors=[INK, AMBER, RED, INK])
