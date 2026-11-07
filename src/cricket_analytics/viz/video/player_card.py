"""Player value card for video (9:16 or 1:1): name, role, team, WAR v3 (last 3 seasons + total), 3-4 worth metrics with percentile
bars, expected matches next season, best single match."""

from . import AMBER, FAINT, INK, MUTE, _text, message_card, new_fig, num, source_note, wrap


def _signed(v, dec=2) -> str:
    return ("+" if v > 0 else "\u2212" if v < 0 else "") + num(abs(v), dec)


def video_figure(result, aspect="9:16", focus=None):
    d, note = result.data, source_note(result)
    if d.empty:
        return message_card(aspect, "Player card", "No data for this player", note)
    hd = d[d.section == "header"].set_index("label").text
    war = d[d.section == "war"]
    seasons, total = war[war.label != "total"].tail(3), war[war.label == "total"]
    worth = d[d.section == "worth"].sort_values("pctile", ascending=False).head(4)
    out, hl = d[d.section == "outlook"], d[d.section == "highlight"]
    pr = result.meta["params"]
    scope = f"{(pr.get('competition') or 'ipl').upper()} since {pr.get('season_from') or 2023}"
    sub = f"{hd.get('role', '')} | {hd.get('team', '')} | {scope}"
    fig, fr = new_fig(aspect, hd.get("player", "Player card"), sub, note)
    tall = aspect == "9:16"
    y, x0, w = fr.y0 + 10, fr.x0, fr.pw

    def rule(yy):
        fig.add_shape(type="line", xref="paper", yref="paper", x0=fr.px(x0), x1=fr.px(x0 + w), y0=fr.py(yy), y1=fr.py(yy), line=dict(color=FAINT, width=3))

    def head(txt, yy):
        _text(fig, txt, fr.px(x0), fr.py(yy), 30, MUTE, "left")

    # WAR row: last 3 seasons + total
    head("WINS ABOVE REPLACEMENT (WAR v3)", y)
    cells = [(r.label, r.value) for r in seasons.itertuples()] + ([("TOTAL", total.value.iloc[0])] if len(total) else [])
    for i, (lab, v) in enumerate(cells):
        cx = x0 + (i + 0.5) * w / max(len(cells), 1)
        big = i == len(cells) - 1 and len(total) > 0
        _text(fig, _signed(v), fr.px(cx), fr.py(y + 85), 84 if tall else 64, AMBER if big else INK)
        _text(fig, lab, fr.px(cx), fr.py(y + 160), 34, MUTE)
    y += 215
    rule(y)
    # worth metrics with percentile bars
    y += 22
    head("PERCENTILE AMONG PEERS (100 = BEST)", y + 12)
    y += 50
    row = 86 if tall else 64
    for r in worth.itertuples():
        _text(fig, wrap(r.label, 32, int(w * 0.84), 1).upper(), fr.px(x0), fr.py(y + 18), 32, INK, "left")
        _text(fig, f"{r.pctile:.0f}", fr.px(x0 + w), fr.py(y + 18), 52, AMBER, "right")
        bx0, bx1, by = x0, x0 + w, y + 52
        fig.add_shape(type="rect", xref="paper", yref="paper", x0=fr.px(bx0), x1=fr.px(bx1), y0=fr.py(by), y1=fr.py(by + 16), fillcolor=FAINT, line_width=0)
        fig.add_shape(type="rect", xref="paper", yref="paper", x0=fr.px(bx0), x1=fr.px(bx0 + w * r.pctile / 100), y0=fr.py(by), y1=fr.py(by + 16), fillcolor=AMBER, line_width=0)
        y += row
    y += 10
    rule(y)
    if tall:
        y += 22
        if len(out):
            o = out.iloc[0]
            head("EXPECTED MATCHES NEXT IPL SEASON", y + 12)
            _text(fig, f"{o.value:.0f}", fr.px(x0), fr.py(y + 85), 84, INK, "left")
            _text(fig, f"range {o.lo:.0f} to {o.hi:.0f} | evidence: {o.text}", fr.px(x0 + 150), fr.py(y + 85), 34, MUTE, "left")
            y += 150
        if len(hl):
            h = hl.sort_values("value", ascending=False).iloc[0]
            rule(y)
            head("BEST MATCH", y + 34)
            _text(fig, f"{h.text} {h.label}".upper(), fr.px(x0), fr.py(y + 90), 40, INK, "left")
            _text(fig, f"{_signed(h.value, 1)} runs against the rest of the match", fr.px(x0), fr.py(y + 138), 32, MUTE, "left")
    else:  # 1:1: one line each
        line = []
        if len(out):
            line.append(f"expected matches {out.value.iloc[0]:.0f} ({out.lo.iloc[0]:.0f}-{out.hi.iloc[0]:.0f})")
        if len(hl):
            h = hl.sort_values("value", ascending=False).iloc[0]
            line.append(f"best: {h.text} {h.label}")
        _text(fig, " | ".join(line), fr.px(x0), fr.py(y + 40), 30, INK, "left")
    return fig
