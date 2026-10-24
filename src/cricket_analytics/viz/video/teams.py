"""Teams for video. One team -> won / lost / no-result donut with the win % in the middle. By season (one team) ->
win % bars. Many teams -> top 8 by win % among teams with 30+ matches."""

from . import AMBER, INK, MUTE, RED, columns, donut, hbars, message_card, num, scope_text, season_label, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note, sub = result.data, source_note(result), scope_text(result, ("team",))
    if df.empty:
        return message_card(aspect, "Team record", "No team data for these filters", note)
    if "season" in df.columns:
        team = df.groupby("team")["played"].sum().idxmax()                # one team: the busiest
        d = df[df["team"] == team].tail(10)
        return columns([season_label(s) for s in d["season"]], d["win_pct"], f"{team}: win % per season", aspect,
                       f"last {len(d)} seasons | {sub}", note, fmt=lambda v: num(v, 0), suffix="%")
    if len(df) == 1:
        r = df.iloc[0]
        parts = [("Won", r.won, AMBER), ("Lost", r.lost, RED), ("Tied", r.tied, INK), ("No result", r.no_result, MUTE)]
        parts = [p for p in parts if p[1] > 0]
        return donut([p[0] for p in parts], [p[1] for p in parts], f"{r.team}: win, lose, draw", aspect, sub, note,
                     center=(f"{r.win_pct:.0f}%", "of decided matches won"), colors=[p[2] for p in parts])
    d = df[df["played"] >= 30]
    d = (d if not d.empty else df).sort_values("win_pct", ascending=False).head(8)
    return hbars(d["team"], d["win_pct"], "Who wins most", aspect, f"win % of decided matches | {sub}", note,
                 fmt=lambda v: num(v, 0), suffix="%")
