"""Figure for the `trade` module: a before / after card for both teams (view=trade) or one squad's recent value with ranges (view=squad)."""

import textwrap
from html import escape as esc

import plotly.graph_objects as go

from . import PALETTE, bars_height, empty, short, style

TOP = 15
VERDICT_COLOUR = {
    "likely better": PALETTE["good"],
    "leans better": PALETTE["good"],
    "too close to call": PALETTE["neutral"],
    "no change to the best XII": PALETTE["neutral"],
    "leans worse": PALETTE["bad"],
    "likely worse": PALETTE["bad"],
}


def _squad(d) -> go.Figure:
    t = d.head(TOP).iloc[::-1]
    fig = go.Figure(
        go.Bar(
            x=t.recent_value,
            y=[short(p, 20) for p in t.player],
            orientation="h",
            marker_color=[PALETTE["primary"] if x else PALETTE["neutral"] for x in t.in_best_xii],
            error_x=dict(
                type="data",
                symmetric=False,
                array=(t.range_hi - t.recent_value).clip(lower=0),
                arrayminus=(t.recent_value - t.range_lo).clip(lower=0),
                color="rgba(255,255,255,0.45)",
            ),
            text=[f"{v:+.2f}" for v in t.recent_value],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}: %{x:+.2f} wins a season<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Recent value, wins above replacement a season (bar = best XII)")
    fig.update_layout(margin_r=70)
    return style(
        fig,
        f"Squad by recent value: top {len(t)}",
        None,
        note="whiskers = 10th-90th percentile; recent form, not a prediction",
        height=bars_height(len(t)),
    )


def _card(d) -> go.Figure:
    fig = go.Figure()
    fig.update_xaxes(visible=False, range=[0, 1]).update_yaxes(visible=False, range=[0, 1])
    n = len(d)
    for i, r in enumerate(d.itertuples()):
        x = (i + 0.5) / n
        colour = VERDICT_COLOUR.get(r.verdict, PALETTE["neutral"])
        lines = [
            f"<b>{r.team}</b>",
            f"gives: {r.gives}",
            f"gets: {r.gets}",
            "",
            f"Best XII value: <b>{r.xii_before:.2f}</b> to <b>{r.xii_after:.2f}</b>",
            f"range {r.before_lo:.2f} to {r.before_hi:.2f}  to  {r.after_lo:.2f} to {r.after_hi:.2f}",
            f"Change: <b>{r.change:+.2f}</b> ({r.change_lo:+.2f} to {r.change_hi:+.2f})",
            f"Squad salary: {r.squad_salary_before:.1f} to {r.squad_salary_after:.1f} cr "
            f"(purse {r.purse_freed_cr:+.1f} cr)",
            f"Net value of the swap: {r.net_value_cr:+.1f} cr",
            *(
                [
                    f"Playoff odds: {r.playoff_pct_before:.0f}% to {r.playoff_pct_after:.0f}% "
                    f"({r.playoff_pts_change:+.1f} pts, {r.playoff_pts_change_lo:+.1f} to {r.playoff_pts_change_hi:+.1f})"
                ]
                if hasattr(r, "playoff_pct_before")
                else []
            ),
            f"Value per crore: {r.value_per_cr_before:.3f} to {r.value_per_cr_after:.3f}",
            f"Weak slots created: {r.holes_created or 'none'}",
            f"Weak slots filled: {r.holes_filled or 'none'}",
        ]
        fig.add_annotation(
            x=x,
            y=0.97,
            xref="paper",
            yref="paper",
            xanchor="center",
            yanchor="top",
            text="<br>".join(lines),
            showarrow=False,
            align="left",
            font=dict(size=13),
        )
        fig.add_annotation(
            x=x,
            y=0.06,
            xref="paper",
            yref="paper",
            xanchor="center",
            yanchor="bottom",
            text="<b>"
            + "<br>".join(textwrap.wrap(r.verdict.upper(), 16))
            + "</b>",  # two cards sit side by side
            showarrow=False,
            font=dict(size=18, color=colour),
        )
    return fig


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No trade to show")
    if "verdict" not in d.columns:
        return _squad(d)
    fig = _card(d)
    return style(
        fig,
        "IPL trade check: best XII before and after",
        result,
        note="recent value, wins a season; not a forecast",
        height=500,
    )


# ── HTML trade card (the dashboard shows it through the generic `html(result)` hook; inline styles only, light card with its own
# background so it reads on the dark theme) ───────────────────────────────────────────────────────────────────────────────
TEAM_STYLE = {  # abbreviation -> (badge text colour, badge / bar colour)
    "CSK": ("#1b1b1b", "#F5C400"),
    "DC": ("#fff", "#1B4F9C"),
    "GT": ("#fff", "#1C2C5B"),
    "KKR": ("#fff", "#3A225D"),
    "LSG": ("#fff", "#00A3E0"),
    "MI": ("#fff", "#004BA0"),
    "PBKS": ("#fff", "#D71920"),
    "RR": ("#fff", "#EA1A85"),
    "RCB": ("#fff", "#C8102E"),
    "SRH": ("#fff", "#F26522"),
}
GREEN, RED, INK, MUTED, LINE, CARD = (
    "#1a8a4a",
    "#c62828",
    "#1d1d1f",
    "#6b6b73",
    "#e4e2dc",
    "#fbfaf7",
)
MINUS = "−"


def _n(x, d=2, sign=True) -> str:
    return f"{x:+.{d}f}".replace("-", MINUS) if sign else f"{x:.{d}f}".replace("-", MINUS)


def _tint(x, tol=0.0) -> str:
    return GREEN if x > tol else RED if x < -tol else INK


def _span(text, colour=INK, size="inherit", weight="normal") -> str:
    return f'<span style="color:{colour};font-size:{size};font-weight:{weight}">{text}</span>'


def _badge(ab, size=34) -> str:
    fg, bg = TEAM_STYLE[ab]
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;width:{size}px;height:{size}px;'
        f'border-radius:50%;background:{bg};color:{fg};font-size:{size * 0.32:.0f}px;font-weight:700">{esc(ab)}</span>'
    )


def _pct(t) -> str:
    return f"{t[0]:.0f}% ({t[1]:.0f}–{t[2]:.0f})"


def _pts(t) -> str:
    return f"{_n(t[0], 1)} pts ({_n(t[1], 1)} to {_n(t[2], 1)})"


def _player(p) -> str:
    sub = f"₹{p['price']:g} cr"
    if not p["evidence"]:
        sub += " · no IPL evidence"
    bowl = (
        f"<br>{_span('pWAR ' + _n(p['pwar_bowl']), MUTED, '11px')}"
        if p["pwar_bowl"] is not None
        else ""
    )
    w = p.get("worth")
    if w:  # headline worth metrics with percentile among IPL 2023+ peers (display only)
        bits = [f"{esc(m['label'])} {m['value']:.0f}" if m["value"] >= 20 else f"{esc(m['label'])} {m['value']:.1f}" for m in w["metrics"]]
        line = " · ".join(f"{b} (p{m['pctile']})" for b, m in zip(bits, w["metrics"]))
        if w["matches"]:
            line += f" · ~{w['matches'][0]:.0f} matches ({w['matches'][1]:.0f}-{w['matches'][2]:.0f})"
        extra = f"<br>{_span(line, MUTED, '11px')}"
    else:
        extra = ""
    return (
        f'<div style="display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid {LINE}">'
        f"<div><b>{esc(p['name'])}</b><br>{_span(esc(sub), MUTED, '12px')}{extra}</div>"
        f'<div style="text-align:right;white-space:nowrap"><b style="color:{_tint(p["value"])}">{_n(p["value"])}</b><br>'
        f"{_span(_n(p['lo']) + ' to ' + _n(p['hi']), MUTED, '11px')}{bowl}</div></div>"
    )


def _left(c) -> str:
    a, b = c["order"]
    cols = ""
    for ab in (a, b):
        t = c["teams"][ab]
        body = "".join(_player(p) for p in t["receives"]) or _span("nothing", MUTED)
        cols += (
            f'<div style="flex:1 1 150px;min-width:150px;padding:0 6px;display:flex;flex-direction:column">'
            f'<div style="font-size:11px;letter-spacing:.08em;color:{MUTED};padding-bottom:4px">'
            f"{esc(ab)} RECEIVES <span title='recent value, wins above replacement a season'>(RECENT WAR)</span></div>{body}"
            f'<div style="border-top:1px solid {LINE};margin-top:auto;padding-top:10px">'
            f"{_span('NET VALUE', MUTED, '11px')}<br>"
            f'<b style="font-size:28px;color:{_tint(t["net_cr"])}">{_n(t["net_cr"], 1)}</b> '
            f"{_span('cr', MUTED, '12px')}</div></div>"
        )
    bar = (
        f'<div style="display:flex;height:6px;margin:14px -18px -16px"><div style="flex:1;background:{TEAM_STYLE[a][1]}"></div>'
        f'<div style="flex:1;background:{TEAM_STYLE[b][1]}"></div></div>'
    )
    head = (
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;font-weight:600">{_badge(a)}'
        f"<span>{esc(c['teams'][a]['name'])} ⇄ {esc(c['teams'][b]['name'])}</span>{_badge(b)}</div>"
    )
    foot = (
        f'<div style="font-size:11px;color:{MUTED};margin-top:8px">RECENT WAR = wins above replacement a season in IPL 2023-26 '
        f"(recent seasons count more); small grey = 10th to 90th percentile. Net value = worth of who arrives minus who leaves, "
        f"in crore, at {c['cr_per_win']:.1f} cr per win (what squads paid on average).</div>"
    )
    return (
        f'<div style="{_CARD};flex:1 1 360px;min-width:300px;display:flex;flex-direction:column">{head}'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;flex:1">{cols}</div>'
        f"{foot}{bar}</div>"
    )


_CARD = f"background:{CARD};color:{INK};border-radius:12px;padding:16px 18px;box-sizing:border-box;font:14px/1.35 system-ui,Segoe UI,sans-serif;overflow:hidden"


def _verdict(c) -> str:
    a, b = c["order"]
    ta, tb = c["teams"][a], c["teams"][b]
    hi, lo = (ta, tb) if ta["net_cr"] >= tb["net_cr"] else (tb, ta)
    if abs(hi["net_cr"] - lo["net_cr"]) < 1:
        s = "Close to even on net value"
    else:
        s = f"{hi['name']} came out ahead on net value, {_n(hi['net_cr'], 1)} against {_n(lo['net_cr'], 1)} cr"
    if ta["odds"]:
        d = [t["odds"]["playoff"]["diff"] for t in (ta, tb)]
        tiny = all(x[1] <= 0 <= x[2] for x in d)
        s += (
            f". Playoff odds move by {_n(d[0][0], 1)} points for {a} and {_n(d[1][0], 1)} for {b}"
            + (": inside the range of luck, the season is mostly decided by chance" if tiny else "")
        )
    return s + "."


def _right(c) -> str:
    a, b = c["order"]
    A, B = c["teams"][a], c["teams"][b]
    th = f'style="text-align:right;padding:4px 6px;color:{MUTED};font-size:11px;font-weight:600"'
    td = 'style="text-align:right;padding:6px;border-top:1px solid ' + LINE + ';vertical-align:top"'
    lab = f'style="padding:6px;border-top:1px solid {LINE};color:{MUTED};font-size:11px;letter-spacing:.06em;vertical-align:top"'

    def cell(main, colour=INK, sub=""):
        return (
            f"<td {td}><b style='color:{colour}'>{main}</b>"
            + (f"<br>{_span(sub, MUTED, '11px')}" if sub else "")
            + "</td>"
        )

    def row(label, f):
        return f"<tr><td {lab}>{label}</td>{f(A)}{f(B)}</tr>"

    def xii(t):
        (b0, l0, h0), (a1, l1, h1), (ch, cl, chh) = (
            t["xii"][k] for k in ("before", "after", "change")
        )
        col = (
            INK if cl <= 0 <= chh else _tint(ch)
        )  # coloured only when the change's range excludes 0
        return cell(_n(b0, 2, False), INK, f"{_n(l0, 1, False)} to {_n(h0, 1, False)}") + cell(
            _n(a1, 2, False), col, f"{_n(l1, 1, False)} to {_n(h1, 1, False)}"
        )

    def odds(kind):
        def f(t):
            if not t["odds"]:
                return cell("–") * 2
            o = t["odds"][kind]
            col = INK if o["diff"][1] <= 0 <= o["diff"][2] else _tint(o["diff"][0])
            return cell(_pct(o["before"])) + cell(_pct(o["after"]), col, _pts(o["diff"]))

        return f

    def two(key, d, tint=True):
        return lambda t: (
            cell(_n(t[key][0], d, False))
            + cell(_n(t[key][1], d, False), _tint(t[key][1] - t[key][0]) if tint else INK)
        )

    def net(t):
        return cell("0.0") + cell(_n(t["net_cr"], 1), _tint(t["net_cr"]))

    heads = "".join(
        f'<th colspan="2" {th.replace("text-align:right", "text-align:center")}>{_badge(x, 22)} {esc(x)}</th>'
        for x in (a, b)
    )
    sub = f"<tr><th></th>{(f'<th {th}>BEFORE</th><th {th}>AFTER</th>') * 2}</tr>"
    body = "".join(
        [
            row("XII VALUE", xii),
            row("PLAYOFF ODDS", odds("playoff")),
            row("TITLE ODDS", odds("title")),
            row("PURSE ₹CR", two("purse", 1)),
            row("ASSETS ₹CR", two("assets", 1)),
            row("NET VALUE ₹CR", net),
        ]
    )
    bt = c["beta"]
    note = (
        "No odds: simulation off."
        if bt is None
        else f"Odds come from {c['seasons']:,} simulated IPL seasons. Win chance per game = logistic(slope x gap in XII value), "
        f"slope {bt['beta']:.2f} per win a season (10th to 90th percentile {_n(bt['lo'], 2)} to {_n(bt['hi'], 2)}, fitted on "
        f"{bt['n']} IPL 2024-26 matches). Brackets = 10th to 90th percentile over that slope uncertainty; a change is coloured "
        f"only when its range excludes 0. Purse = {c['purse_cap']:g} cr cap (guess) minus squad salaries; assets = XII value "
        f"x {c['cr_per_win']:.1f} cr per win; net value is the swap's gain."
    )
    mp = f" Must play: {esc(', '.join(c['must_play']))}." if c["must_play"] else ""
    return (
        f'<div style="{_CARD};flex:1.4 1 440px;min-width:320px">'
        f'<div style="font-size:11px;letter-spacing:.1em;color:{MUTED};margin-bottom:6px">BEFORE THE TRADE, AND AFTER</div>'
        f'<table style="width:100%;border-collapse:collapse"><tr><th></th>{heads}</tr>{sub}{body}</table>'
        f'<div style="font-size:11px;color:{MUTED};margin-top:8px">{note}{mp}</div>'
        f'<div style="margin-top:10px;font-weight:600">{esc(_verdict(c))}</div></div>'
    )


def _more(c) -> str:
    a, b = c["order"]
    A, B = c["teams"][a], c["teams"][b]
    th = f'style="text-align:left;padding:5px 8px;color:{MUTED};font-size:11px;border-bottom:1px solid {LINE}"'
    td = f'style="padding:5px 8px;border-bottom:1px solid {LINE};vertical-align:top"'

    def line(label, fa, fb):
        return f"<tr><td {td}>{label}</td><td {td}>{fa}</td><td {td}>{fb}</td></tr>"

    def both(f):
        return f(A), f(B)

    def xii(t):
        v = t["xii"]["change"]
        return f"{_n(v[0])} ({_n(v[1])} to {_n(v[2])})"

    def op(kind):
        return lambda t: _pts(t["odds"][kind]["diff"]) if t["odds"] else "–"

    rows = [
        line("Change in best XII (wins a season)", *both(xii)),
        line("Playoff probability points", *both(op("playoff"))),
        line("Title probability points", *both(op("title"))),
        line("Asset value ₹cr", *both(lambda t: _n(t["assets"][1] - t["assets"][0], 1))),
        line("Purse after ₹cr", *both(lambda t: _n(t["purse"][1], 1, False))),
        line("Net value ₹cr", *both(lambda t: _n(t["net_cr"], 1))),
    ]
    holes = "".join(
        f"<tr><td {td}>{esc(t['name'])}</td><td {td}>{esc(', '.join(t['holes_after']) or 'none')}</td>"
        f"<td {td}>{esc(', '.join(t['holes_created']) or 'none')}</td><td {td}>{esc(', '.join(t['holes_filled']) or 'none')}</td>"
        f"<td {td}>auction pool unknown until 17 Nov</td></tr>"
        for t in (A, B)
    )
    h = "font-weight:600;margin:12px 0 4px"
    return (
        f'<details style="{_CARD};margin-top:12px"><summary style="cursor:pointer;font-weight:600">More analysis</summary>'
        f'<div style="{h}">Where the value came from</div>'
        f'<table style="width:100%;border-collapse:collapse"><tr><th {th}></th><th {th}>{esc(A["name"])}</th><th {th}>{esc(B["name"])}</th></tr>'
        f"{''.join(rows)}</table>"
        f'<div style="{h}">Holes after the trade</div>'
        f'<table style="width:100%;border-collapse:collapse"><tr><th {th}>Team</th><th {th}>Weak slots now</th><th {th}>Created by the trade</th>'
        f"<th {th}>Filled by the trade</th><th {th}>Can the auction fix it?</th></tr>{holes}</table>"
        f'<div style="font-size:11px;color:{MUTED};margin-top:6px">A weak slot = the squad\'s best player there is below the league median. '
        f"Chances of filling a hole in the auction cannot be computed until retentions are known (17 Nov 2026); none are invented here.</div>"
        f"</details>"
    )


def html(result) -> str | None:
    """The trade card for the dashboard (None for the squad view or when the card data is missing)."""
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return None
    return f'<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:stretch">{_left(c)}{_right(c)}</div>{_more(c)}'
