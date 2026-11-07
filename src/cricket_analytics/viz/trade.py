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



# ── HTML trade page (the dashboard shows it through the generic `html(result)` hook): numbers only, theme-neutral ──────────
MINUS = "−"
ROLE = {"batter": "BAT", "bowler": "BWL", "all-rounder": "AR", "wicketkeeper": "WK", "no IPL evidence": "NEW"}
CSS = """<style>
.tp{display:flex;flex-wrap:wrap;gap:16px;font:13px/1.3 system-ui,Segoe UI,sans-serif;font-variant-numeric:tabular-nums}
.tp .t{flex:1 1 340px;min-width:0}
.tp h3{margin:0 0 6px;font-size:15px;font-weight:700}
.tp h4{margin:12px 0 4px;font-size:11px;font-weight:600;letter-spacing:.08em;opacity:.65;text-transform:uppercase}
.tp .s{overflow-x:auto}
.tp table{width:100%;border-collapse:collapse}
.tp th,.tp td{padding:3px 6px;border-bottom:1px solid rgba(128,128,128,.28);text-align:right;white-space:nowrap}
.tp th{font-size:11px;font-weight:600;opacity:.65}
.tp th:first-child,.tp td:first-child{text-align:left}
.tp small{opacity:.6;font-size:10.5px;margin-left:3px}
.tp .up{color:#2e9e5b}.tp .dn{color:#e5534b}
.tp.v{gap:28px;margin:18px 0 8px}
.tp .tag{display:inline-block;margin-left:8px;padding:1px 6px;border-radius:4px;background:#e5534b;color:#fff;font-size:10.5px;font-weight:700;letter-spacing:.04em;vertical-align:middle}
.tp .big{font-size:30px;font-weight:700;line-height:1.1}
.tp .rs{flex:1 1 300px;border-top:3px solid rgba(128,128,128,.4);padding:10px 2px 0}
.tp .rs.up{border-color:#2e9e5b}.tp .rs.dn{border-color:#e5534b}
.tp .rs .g{display:flex;gap:22px;margin-top:8px;flex-wrap:wrap}
.tp .rs .g div{font-size:15px;font-weight:600}.tp .rs .g span{display:block;font-size:10.5px;font-weight:600;opacity:.6;letter-spacing:.06em}
.tp .diff{width:100%;font-size:15px;font-weight:600;margin-top:4px}
</style>"""


def _n(x, d=2, sign=False) -> str:
    return f"{x:+.{d}f}".replace("-", MINUS) if sign else f"{x:.{d}f}".replace("-", MINUS)


def _d(x, d=2, tint=True, inv=False, small="") -> str:
    """A change value: signed, green / red by sign (inv flips), optional small range."""
    c = "" if not tint or abs(x) < 0.5 * 10**-d else ("up" if (x > 0) != inv else "dn")
    return f'<span class="{c}">{_n(x, d, True)}</span>' + (f"<small>{small}</small>" if small else "")


def _rng(lo, hi, d=1, sign=False) -> str:
    return f"{_n(lo, d, sign)} / {_n(hi, d, sign)}"


def _row(label, b, a, delta) -> str:
    return f"<tr><td>{label}</td><td>{b}</td><td>{a}</td><td>{delta}</td></tr>"


def _metrics(t) -> str:
    (b0, bl, bh), (a1, al, ah), (ch, cl, chh) = (t["xii"][k] for k in ("before", "after", "change"))
    sig = not cl <= 0 <= chh  # tint only when the change's range excludes 0
    rows = [
        _row("XII value", f"{_n(b0)}<small>{_rng(bl, bh)}</small>", f"{_n(a1)}<small>{_rng(al, ah)}</small>",
             _d(ch, 2, sig, small=_rng(cl, chh, 1, True))),
    ]
    for key, label in (("playoff", "Playoff %"), ("title", "Title %")):
        o = t["odds"] and t["odds"][key]
        if o:
            sig = not o["diff"][1] <= 0 <= o["diff"][2]
            rows.append(_row(label, f"{o['before'][0]:.1f}<small>{_rng(o['before'][1], o['before'][2], 0)}</small>",
                             f"{o['after'][0]:.1f}<small>{_rng(o['after'][1], o['after'][2], 0)}</small>",
                             _d(o["diff"][0], 1, sig, small=_rng(o["diff"][1], o["diff"][2], 1, True))))
        else:
            rows.append(_row(label, "–", "–", "–"))
    rows.append(_row("Purse left, cr", _n(t["purse"][0]), _n(t["purse"][1]), _d(t["purse"][1] - t["purse"][0])))
    rows.append(_row("Squad salary, cr", _n(t["salary"][0]), _n(t["salary"][1]),
                     _d(t["salary"][1] - t["salary"][0], inv=True)))
    rows.append(_row("Net value, cr", "", "", _d(t["net_cr"], 1)))
    return (f"<tr><th></th><th>Before</th><th>After</th><th>Change</th></tr>{''.join(rows)}")


def _moving(t) -> str:
    rows = ""
    for p in t["receives"]:
        w = p.get("worth") or {}
        ms = w.get("metrics", [])
        cells = "".join(
            f"<td>{m['value']:.0f}<small>p{m['pctile']}</small></td>" if m["value"] >= 20
            else f"<td>{m['value']:.1f}<small>p{m['pctile']}</small></td>"
            for m in ms[:3]
        ) + "<td></td>" * (3 - len(ms[:3]))
        em = w.get("matches")
        rows += (
            f"<tr><td>{esc(p['name'])}</td><td>{ROLE.get(p['role'], '')}</td><td>{_n(p['price'])}</td>"
            f"<td>{_n(p['value'])}<small>{_rng(p['lo'], p['hi'], 1)}</small></td>{cells}"
            f"<td>{'' if not em else f'{em[0]:.0f}<small>{em[1]:.0f} / {em[2]:.0f}</small>'}</td></tr>"
        )
    if not rows:
        return ""
    labels = next((p["worth"]["metrics"] for p in t["receives"] if p.get("worth")), [])
    mh = "".join(f"<th>{esc(m['label'])}</th>" for m in labels[:3]) + "<th></th>" * (3 - len(labels[:3]))
    return (
        f"<h4>Arriving</h4><div class=s><table><tr><th>Player</th><th>Role</th><th>Cr</th><th>WAR</th>{mh}<th>Matches</th></tr>"
        f"{rows}</table></div>"
    )


def _xii(t) -> str:
    rows = "".join(
        f"<tr><td>{'<b>' if r['new'] else ''}{esc(r['name'])}{'</b>' if r['new'] else ''}</td><td>{ROLE.get(r['role'], '')}</td>"
        f"<td>{'OS' if r['os'] else ''}</td><td>{_n(r['war'])}</td><td>{r['slot']}</td></tr>"
        for r in t["xii_rows"]
    )
    return (
        f"<h4>XII after</h4><div class=s><table><tr><th>Player</th><th>Role</th><th>OS</th><th>WAR</th><th></th></tr>"
        f"{rows}</table></div>"
    )


def _gives(c, ab):
    """Players leaving team `ab` = what the other team receives."""
    other = c["order"][1] if ab == c["order"][0] else c["order"][0]
    return c["teams"][other]["receives"]


def _tot(ps):
    return {
        "price": sum(p["price"] for p in ps),
        "value": sum(p["value"] for p in ps),
        "m": sum(((p.get("worth") or {}).get("matches") or (0,))[0] for p in ps),
    }


def _compare_side(c, ab) -> str:
    ps = _gives(c, ab)
    rows = ""
    for p in ps:
        w = p.get("worth") or {}
        em = w.get("matches")
        ms = " · ".join(
            f"{m['value']:.0f} {esc(m['label'])}<small>p{m['pctile']}</small>" if m["value"] >= 20
            else f"{m['value']:.1f} {esc(m['label'])}<small>p{m['pctile']}</small>"
            for m in w.get("metrics", [])[:3]
        )
        mt = "" if not em else f"{em[0]:.0f}<small>{em[1]:.0f} / {em[2]:.0f}</small>"
        rows += (
            f"<tr><td>{esc(p['name'])}</td><td>{ROLE.get(p['role'], '')}</td><td>{_n(p['price'])}</td>"
            f"<td>{_n(p['value'])}<small>{_rng(p['lo'], p['hi'])}</small></td>"
            f"<td>{_n(p['value'] / p['price'], 3) if p['price'] else ''}</td>"
            f"<td>{mt}</td><td class=w style='text-align:left'>{ms}</td></tr>"
        )
    if len(ps) > 1:
        t = _tot(ps)
        rows += (
            f"<tr><td><b>Total</b></td><td></td><td><b>{_n(t['price'])}</b></td><td><b>{_n(t['value'])}</b></td>"
            f"<td><b>{_n(t['value'] / t['price'], 3) if t['price'] else ''}</b></td><td><b>{t['m']:.0f}</b></td><td></td></tr>"
        )
    return (
        f"<div class=t><h4>{esc(ab)} gives</h4><div class=s><table><tr><th>Player</th><th>Role</th><th>Cr</th><th>WAR</th>"
        f"<th>WAR/cr</th><th>Matches</th><th style='text-align:left'>Worth metrics</th></tr>"
        f"{rows or '<tr><td>–</td></tr>'}</table></div></div>"
    )


def _result(c, ab) -> str:
    t = c["teams"][ab]
    ch, cl, chh = t["xii"]["change"]
    cls = "up" if ch > 0.005 else "dn" if ch < -0.005 else ""
    tag = f'<span class="tag">PURSE {_n(t["purse"][1], 2, True)} cr</span>' if t["purse"][1] < 0 else ""
    o = t["odds"]
    cells = [("XII RANGE", _rng(cl, chh, 1, True))]
    for k, lab in (("playoff", "PLAYOFF PTS"), ("title", "TITLE PTS")):
        cells.append((lab, _d(o[k]["diff"][0], 1) if o else "–"))
    cells.append(("PURSE CR", _d(t["purse"][1] - t["purse"][0])))
    g = "".join(f"<div><span>{a}</span>{b}</div>" for a, b in cells)
    return (
        f'<div class="rs {cls}"><h3>{esc(ab)}{tag}</h3><div class="big {cls}">{_n(ch, 2, True)}</div>'
        f"<div class=g>{g}</div></div>"
    )


def html(result) -> str | None:
    """Top of the trade page: players swapped side by side, value difference, result strip (None for the squad view)."""
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return None
    a, b = c["order"]
    sides = f"<div class='tp v'>{_compare_side(c, a)}{_compare_side(c, b)}</div>"
    ta, tb = _tot(_gives(c, b)), _tot(_gives(c, a))  # what A gets, what A gives
    diff = (
        f"<div class=tp><div class=diff>{esc(a)} WAR diff {_d(ta['value'] - tb['value'])} | "
        f"salary diff {_d(ta['price'] - tb['price'], inv=True)} cr</div></div>"
        if _gives(c, a) or _gives(c, b)
        else ""
    )
    strip = f"<div class='tp v'>{_result(c, a)}{_result(c, b)}</div>"
    return f"{CSS}{sides}{diff}{strip}"


def _wrap(body) -> str:
    return f"{CSS}<div class=tp>{body}</div>"


def details(result) -> list[tuple[str, str]]:
    """Collapsed sections for the dashboard: [(expander title, html)]."""
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return []
    T = c["teams"]
    out = [
        (
            f"Team detail — {ab}",
            _wrap(f"<div class=t><h3>{esc(T[ab]['name'])}</h3><div class=s><table>{_metrics(T[ab])}</table></div>{_moving(T[ab])}</div>"),
        )
        for ab in c["order"]
    ]
    out.append(("Best XII after", _wrap("".join(f"<div class=t><h3>{esc(T[ab]['name'])}</h3>{_xii(T[ab])}</div>" for ab in c["order"]))))
    L = "style='text-align:left'"
    rows = "".join(
        f"<tr><td>{esc(T[ab]['name'])}</td>"
        + "".join(f"<td {L}>{esc(', '.join(T[ab][k]) or 'none')}</td>" for k in ("holes_after", "holes_created", "holes_filled"))
        + "</tr>"
        for ab in c["order"]
    )
    out.append(
        (
            "Slots",
            _wrap(
                f"<div class=t style='flex-basis:100%'><div class=s><table><tr><th>Team</th><th {L}>Weak now</th>"
                f"<th {L}>Created</th><th {L}>Filled</th></tr>{rows}</table></div></div>"
            ),
        )
    )
    return out


def method_note(result) -> str:
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return ""
    bt = c["beta"]
    note = (
        "No odds: simulation off."
        if bt is None
        else f"Odds from {c['seasons']:,} simulated IPL seasons. Win chance per game = logistic(slope x gap in XII value), slope {bt['beta']:.2f} per win a season "
        f"(10th to 90th percentile {_n(bt['lo'], 2)} to {_n(bt['hi'], 2)}, fitted on {bt['n']} IPL 2024-26 matches). Ranges are 10th to 90th percentile over that slope uncertainty. "
        f"Purse = {c['purse_cap']:g} cr cap (guess) minus squad salaries; {c['cr_per_win']:.1f} cr per win."
    )
    return note + (f" Must play: {', '.join(c['must_play'])}." if c["must_play"] else "")
