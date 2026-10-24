"""Batting for video. One player -> big-number card (runs, average, strike rate); by season -> bars of the last
10 seasons with the best one amber; by phase -> strike-rate bars (powerplay / middle / death); many players ->
top-5 leaderboard. focus = a column name (total_runs, average, strike_rate, ...) for bars and the leaderboard."""

from . import big_number_card, columns, hbars, message_card, num, scope_text, season_label, source_note

NAMES = {"total_runs": "runs", "average": "average", "strike_rate": "strike rate", "sixes": "sixes", "fours": "fours",
         "hundreds": "hundreds", "fifties": "fifties", "highest": "highest score"}
PHASES = ["powerplay", "middle", "death"]


def video_figure(result, aspect="9:16", focus=None):
    df, note, sub = result.data, source_note(result), scope_text(result)
    if df.empty:
        return message_card(aspect, "Batting", "No batting data for these filters", note)
    metric = focus if focus in df.columns and focus in NAMES else "total_runs"
    what = NAMES[metric]
    if "season" in df.columns:
        who = df.groupby("batter")["total_runs"].sum().idxmax()      # one player: the biggest run-scorer
        d = df[df["batter"] == who].tail(10)
        return columns([season_label(s) for s in d["season"]], d[metric], f"{who}: {what} per season", aspect,
                       f"last {len(d)} seasons | {sub}", note, fmt=lambda v: num(v, 0 if metric == "total_runs" else 1))
    if "phase" in df.columns:                                        # all selected batters together
        g = df.groupby("phase")[["total_runs", "balls"]].sum().reindex(PHASES).dropna()
        who = df["batter"].iloc[0] if df["batter"].nunique() == 1 else "all batters"
        return columns(list(g.index), g["total_runs"] / g["balls"] * 100, f"{who}: strike rate by phase", aspect,
                       f"runs per 100 balls | {sub}", note, fmt=lambda v: num(v, 0))
    if len(df) == 1:
        r = df.iloc[0]
        label = scope_text(result, ("player", "season", "team", "opposition", "venue", "phase")).split(" | ")[0]
        stats = [(num(r.total_runs), f"{label} runs"), (num(r.average, 1), "batting average"),
                 (num(r.strike_rate, 0), "strike rate")]
        return big_number_card(stats, r.batter, aspect, sub, note)
    d = df.sort_values(metric, ascending=False).head(5)
    return hbars(d["batter"], d[metric], f"Top 5 batters: {what}", aspect, sub, note,
                 fmt=lambda v: num(v, 0 if metric == "total_runs" else 1))
