"""Innings list for video. One batting row = a card (runs, balls, opponent, how out); one bowling row = the figures.
Several rows = bars in date order, labelled with the opposition's initials, the latest in amber."""

from . import big_number_card, columns, message_card, num, scope_text, short_name, source_note


def _abbr(team: str) -> str:
    w = str(team).split()
    return "".join(x[0] for x in w).upper() if len(w) > 1 else str(team)[:4].upper()


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    p = result.meta["params"]
    if df.empty:
        return message_card(aspect, "Innings", "No innings for these filters", note)
    bat = p.get("role", "batting") == "batting"
    df = df.sort_values(["date", "match_id", "innings"])
    who = short_name(df["player"].iloc[-1]) if p.get("player") else "Best"
    word = {"first": "debut" if len(df) == 1 else "first", "last": "latest", "best": "best"}[p.get("order", "last")]
    sub = scope_text(result)
    if len(df) == 1:
        r = df.iloc[0]
        if bat:
            stats = [(r.score, f"runs off {r.balls} balls"), (f"v {_abbr(r.opposition)}", f"{r.date:%d %b %Y}")]
            if r.fours or r.sixes:
                stats.append((f"{r.fours}x4  {r.sixes}x6", r.how_out if r.how_out == "not out" else f"{r.how_out} b {r.bowler}" if r.bowler else r.how_out))
        else:
            stats = [(r.figures, f"{r.overs} overs, economy {num(r.economy, 1)}"), (f"v {_abbr(r.opposition)}", f"{r.date:%d %b %Y}")]
        return big_number_card(stats, f"{who}: {word}", aspect, sub, note)
    n = len(df)
    labels = [f"{_abbr(o)}{'*' if bat and h == 'not out' else ''}" for o, h in zip(df["opposition"], df["how_out"])] if bat \
        else [_abbr(o) for o in df["opposition"]]
    vals = df["runs" if bat else "wickets"]
    return columns(labels, vals, f"{who}: {word} {n} {'innings' if bat else 'spells'}", aspect,
                   f"{'runs (* = not out)' if bat else 'wickets'} | {sub}", note,
                   highlight=[n - 1] if p.get("order", "last") != "best" else "max")
