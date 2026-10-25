"""Compare for video: butterfly (mirrored) bars, one player on each side, five rows. Each row is scaled on its own,
the winner of the row is amber, and the subtitle says who leads how many rows."""

from . import butterfly, message_card, num, scope_text, source_note

BAT = [
    ("Runs", "runs", False, 0),
    ("Average", "average", False, 1),
    ("Strike rate", "strike_rate", False, 0),
    ("Sixes", "sixes", False, 0),
    ("Hundreds", "hundreds", False, 0),
]
BOWL = [
    ("Wickets", "wickets", False, 0),
    ("Average", "average", True, 1),
    ("Economy", "economy", True, 1),
    ("Strike rate", "strike_rate", True, 1),
    ("Dot balls %", "dot_pct", False, 0),
]


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    o = df[df["scope"] == "overall"] if "scope" in df.columns else df
    if len(o) < 2:
        return message_card(aspect, "Head to head", "Need two players with data to compare", note)
    a, b = o.iloc[0], o.iloc[1]
    spec = BOWL if "wickets" in df.columns else BAT
    rows, wins = [], [0, 0]
    for label, col, low, dec in spec:
        x, y = float(a[col] if a[col] == a[col] else 0), float(b[col] if b[col] == b[col] else 0)
        rows.append((label, x, y, low, num(x, dec), num(y, dec)))
        if x != y:
            wins[0 if (x < y) == low else 1] += 1
    lead = a.player if wins[0] >= wins[1] else b.player
    sub = f"{lead} leads {max(wins)} of {len(spec)} | " + scope_text(result)
    if wins[0] == wins[1]:
        sub = f"level at {wins[0]} each | " + scope_text(result)
    return butterfly(rows, (a.player, b.player), "Head to head", aspect, sub, note)
