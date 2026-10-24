"""Partnerships for video: top 8 stands as horizontal bars. Pairs (default) -> total runs together; single stands ->
the biggest stands with the year; by wicket -> average stand per wicket as bars."""

from . import columns, hbars, message_card, num, scope_text, short_name, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note, sub = result.data, source_note(result), scope_text(result)
    if df.empty:
        return message_card(aspect, "Partnerships", "No partnerships for these filters", note)
    if "match_id" in df.columns:        # group_by=stand: one row per stand
        d = df.sort_values("runs", ascending=False).head(8)
        labels = [f"{short_name(a)} + {short_name(b)}  {str(dt)[:4]}" for a, b, dt in zip(d.batter1, d.batter2, d.date)]
        return hbars(labels, d["runs"], "Biggest stands", aspect, sub, note, fmt=lambda v: num(v, 0))
    if "wicket_no" in df.columns:       # group_by=wicket
        return columns([f"{int(w)}" for w in df["wicket_no"]], df["average_stand"], "Average stand by wicket", aspect,
                       f"runs per stand, wicket 1 to {int(df['wicket_no'].max())} | {sub}", note, fmt=lambda v: num(v, 0))
    d = df.sort_values("runs", ascending=False).head(8)
    labels = [f"{short_name(a)} + {short_name(b)}" for a, b in zip(d.batter1, d.batter2)]
    return hbars(labels, d["runs"], "Best batting pairs", aspect, f"runs scored together | {sub}", note,
                 fmt=lambda v: num(v, 0))
