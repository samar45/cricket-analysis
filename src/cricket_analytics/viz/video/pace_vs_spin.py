"""Pace vs spin for video: two bars of strike rate, vs pace and vs spin, summed over every row in the result (one
batter, one team, or the whole league). Only the pace / spin level is used (detail rows and unknown bowlers are left out)."""

from . import columns, message_card, num, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty or not {"bowler_type", "level", "runs", "balls"} <= set(df.columns):
        return message_card(aspect, "Pace vs spin", "This mode has no pace / spin split to show", note)
    if focus:
        key = next((c for c in ("batter", "team") if c in df.columns), None)
        df = df[df[key] == focus] if key else df
    g = df[(df["level"] == "kind") & df["bowler_type"].isin(["Pace", "Spin"])].groupby("bowler_type")[["runs", "balls"]].sum()
    g = g[g["balls"] > 0]
    if g.empty:
        return message_card(aspect, "Pace vs spin", "No balls for these filters", note)
    who = focus or next((df[c].iloc[0] for c in ("batter", "team") if c in df.columns and df[c].nunique() == 1), "All batters")
    sr = g["runs"] / g["balls"] * 100
    return columns([f"vs {t}" for t in g.index], sr, f"{who}: pace vs spin", aspect,
                   f"strike rate, runs per 100 balls | {scope_text(result)}", note, fmt=lambda v: num(v, 0))
