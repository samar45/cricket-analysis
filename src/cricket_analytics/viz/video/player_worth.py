"""Player worth for video: one player's percentile on each kept metric, a top-5 by average percentile, or the five best
single-match performances against the match."""

from . import hbars, message_card, num, scope_text, short_names, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Player worth", "No players with enough balls for these filters", note)
    sub = scope_text(result)
    if "runs_vs_match" in df.columns:
        who = "batter" if "batter" in df.columns else "bowler"
        d = df.head(5)
        labels = [f"{n} v {o}" for n, o in zip(short_names(d[who]), short_names(d.opposition))]
        return hbars(labels, d.runs_vs_match, "Best performances against the match", aspect, f"runs above / saved vs the rest of the match | {sub}", note, fmt=lambda v: "+" + num(v, 0))
    if "metric" not in df.columns:
        d = df.head(5)
        return hbars(short_names(d.player), d.avg_pctile, "Highest average percentile", aspect, f"on the kept worth metrics | {sub}", note, fmt=lambda v: num(v, 0))
    return hbars(list(df.metric), df.pctile, f"{df.player.iloc[0]}: percentile among peers", aspect, f"100 = best | {sub}", note, fmt=lambda v: num(v, 0))
