"""Player profile for video: how he is USED under the filters. Title = the player, subtitle = the facts we have on the reviewed
list (role, hand, bowling type; unknown ones are left out, never guessed), then up to three blocks, each a line like
"BATS: USUALLY NO.5-6 (52%)" over a few columns of the full mix: batting order (No.1-2 / 3-4 / 5-6 / 7+), balls faced by phase,
balls bowled by phase. Numbers are summed over every row in the result (the competitions selected).
Without `player` the module returns a list, which has no single-message chart."""

import pandas as pd

from ...analysis.player_profile import BOWLED, COUNTS, FACED, POS_BUCKETS, usage_of
from . import AMBER, FAINT, INK, MUTE, _text, message_card, new_fig, scope_text, source_note, wrap


def _val(r, k):
    v = r.get(k)
    return None if v is None or pd.isna(v) or v == "unknown" else v


def _block(fig, fr, top, h, header, items):
    """A header line over len(items) columns; the tallest column is amber. items = [(label, pct)]."""
    _text(
        fig,
        wrap(header, 40, fr.pw, 1),
        fr.px(fr.x0),
        fr.py(top),
        40,
        AMBER,
        anchor="left",
        yanchor="top",
    )
    n, cw = len(items), fr.pw / len(items)
    base = top + h - 46  # bottom of the columns; labels sit under it
    bar_max = max(30, h - 52 - 50 - 46 - 12)
    tallest = max((p or 0) for _, p in items) or 1
    best = max(range(n), key=lambda i: items[i][1] or 0)
    for i, (label, pct) in enumerate(items):
        pct = pct or 0
        x0, bh = fr.x0 + i * cw + cw * 0.12, max(4, bar_max * pct / tallest)
        color = AMBER if i == best else MUTE
        fig.add_shape(
            type="rect",
            xref="paper",
            yref="paper",
            x0=fr.px(x0),
            x1=fr.px(x0 + cw * 0.76),
            y0=fr.py(base),
            y1=fr.py(base - bh),
            fillcolor=color,
            line=dict(width=0),
        )
        _text(fig, f"{pct:.0f}%", fr.px(fr.x0 + (i + 0.5) * cw), fr.py(base - bh - 28), 44, INK)
        _text(fig, label.upper(), fr.px(fr.x0 + (i + 0.5) * cw), fr.py(base + 24), 34, INK)
    fig.add_shape(
        type="line",
        xref="paper",
        yref="paper",
        x0=fr.px(fr.x0),
        x1=fr.px(fr.x1),
        y0=fr.py(base),
        y1=fr.py(base),
        line=dict(color=FAINT, width=3),
    )


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty or df["player"].nunique() != 1 or "pos_1_2" not in df.columns:
        return message_card(aspect, "Player profile", "Pick one player to get a profile card", note)
    r = df.iloc[0]
    tot = df[COUNTS].sum()
    u = usage_of(tot)
    role = _val(r, "role")
    bats, bowls = (
        role != "bowler",
        role != "batter",
    )  # a batter's card has no bowling block and the other way round
    pos = [(lab, u[f"pct_{k}"]) for k, lab in POS_BUCKETS.items()]
    ph = lambda group: [(k.split("_", 1)[1], u[f"pct_{k}"]) for k in group]  # noqa: E731
    blocks = []
    if bats and tot.bat_innings:
        blocks += [
            (f"Bats: {u['usually_bats_at']}", pos),
            (f"Faces: {u['usually_faces_in']}", ph(FACED)),
        ]
    if bowls and u["usually_bowls_in"]:
        blocks.append((f"Bowls: {u['usually_bowls_in']}", ph(BOWLED)))
    if not blocks:  # role unknown / odd filters: show whatever has data
        blocks = [
            (f"{w}: {u[h]}", items)
            for w, h, items in (
                ("Bats", "usually_bats_at", pos),
                ("Faces", "usually_faces_in", ph(FACED)),
                ("Bowls", "usually_bowls_in", ph(BOWLED)),
            )
            if u[h]
        ]
    if not blocks:
        return message_card(aspect, str(r["player"]), "No balls or innings for these filters", note)
    if aspect != "9:16" and len(blocks) > 2:
        blocks = [blocks[0], blocks[-1]]
    facts = [
        x
        for x in (
            role,
            f"{_val(r, 'bat_hand')}-hand bat" if _val(r, "bat_hand") else None,
            _val(r, "bowl_type"),
            "keeper" if _val(r, "keeper") else None,
        )
        if x
    ]
    sub = " | ".join(facts + [scope_text(result)])
    fig, fr = new_fig(aspect, str(r["player"]), sub, note)
    h = fr.ph / len(blocks)
    for i, (header, items) in enumerate(blocks):
        _block(fig, fr, fr.y0 + i * h + 8, h - 16, header, items)
    return fig
