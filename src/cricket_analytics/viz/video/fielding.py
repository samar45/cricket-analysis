"""Fielding for video. One fielder -> big-number card (catches, run-outs, stumpings; catches include caught and bowled).
Several fielders -> top-5 leaderboard by total dismissals (focus = a column name to rank by instead). By season ->
dismissals-per-season columns for the top fielder."""

from . import (
    big_number_card,
    columns,
    hbars,
    message_card,
    num,
    scope_text,
    season_label,
    source_note,
)


def video_figure(result, aspect="9:16", focus=None):
    df, note, sub = result.data, source_note(result), scope_text(result, ("player",))
    if df.empty:
        return message_card(aspect, "Fielding", "No fielding data for these filters", note)
    if "season" in df.columns:
        who = df.groupby("fielder")["total_dismissals"].sum().idxmax()
        d = df[df["fielder"] == who].tail(10)
        return columns(
            [season_label(s) for s in d["season"]],
            d["total_dismissals"],
            f"{who}: dismissals per season",
            aspect,
            f"last {len(d)} seasons | {sub}",
            note,
        )
    if len(df) == 1:
        r = df.iloc[0]
        return big_number_card(
            [
                (num(int(r["catches"] + r["caught_and_bowled"])), "catches"),
                (num(int(r["run_outs"])), "run-outs"),
                (num(int(r["stumpings"])), "stumpings"),
            ],
            f"{r['fielder']} in the field",
            aspect,
            sub,
            note,
        )
    m = focus if focus in df.columns and focus != "fielder" else "total_dismissals"
    d = df.sort_values(m, ascending=False).head(5)
    return hbars(
        d["fielder"],
        d[m],
        f"Top 5 fielders: {m.replace('_', ' ')}",
        aspect,
        sub,
        note,
        fmt=lambda v: num(v, 0 if m != "per_match" else 2),
    )
