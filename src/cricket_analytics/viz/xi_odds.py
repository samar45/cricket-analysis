"""HTML page for the `xi_odds` module: headline numbers for your XI and the tool's best XII, details in expanders. Same look as the trade page."""

from html import escape as esc

from .trade import CSS, ROLE, _n, _rng


def _pct(m) -> str:
    return f"{100 * m[0]:.1f}<small>{_rng(100 * m[1], 100 * m[2], 0)}</small>"


def _block(title, x, tag="") -> str:
    ok = sum(q["ok"] for q in x["rules"])
    bad = f'<span class="tag">{len(x["rules"]) - ok} RULE{"S" if len(x["rules"]) - ok > 1 else ""} FAILED</span>' if ok < len(x["rules"]) else ""
    cells = [("XII VALUE", f"{_n(x['value'])}<small>{_rng(*x['range'], 1)}</small>"), ("WIN %", _pct(x["win"])),
             ("PLAYOFF %", _pct(x["playoff"])), ("TITLE %", _pct(x["title"])), ("RULES", f"{ok} / {len(x['rules'])}")]  # fmt: skip
    g = "".join(f"<div><span>{a}</span>{b}</div>" for a, b in cells)
    return f'<div class="rs"><h3>{esc(title)}{bad}{tag}</h3><div class="big">{100 * x["win"][0]:.1f}%</div><div class=g>{g}</div></div>'


def _players(x) -> str:
    rows = "".join(
        f"<tr><td>{esc(r['name'])}{' *' if r['outside'] else ''}</td><td>{ROLE.get(r['role'], '')}</td><td>{'OS' if r['os'] else ''}</td>"
        f"<td>{_n(r['war'])}</td><td>{r['slot']}</td></tr>"
        for r in x["rows"]
    )
    return f"<div class=s><table><tr><th>Player</th><th>Role</th><th>OS</th><th>WAR</th><th></th></tr>{rows}</table></div>"


def _rules(x) -> str:
    rows = "".join(
        f"<tr><td>{q['rule']}</td><td>{q['value']}</td><td class={'up' if q['ok'] else 'dn'}>{'pass' if q['ok'] else 'FAIL'}</td></tr>"
        for q in x["rules"]
    )
    return f"<div class=s><table><tr><th>Rule</th><th>Count</th><th></th></tr>{rows}</table></div>"


def html(result) -> str | None:
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return None
    blocks = (_block("Your XI", c["you"]) if c["custom"] else "") + _block("Tool's best XII", c["best"])
    return f"{CSS}<div class='tp v'>{blocks}</div>"


def details(result) -> list[tuple[str, str]]:
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return []
    side = [("Your XI", c["you"])] if c["custom"] else []
    side.append(("Tool's best XII", c["best"]))
    wrap = lambda body: f"{CSS}<div class=tp>{body}</div>"  # noqa: E731
    out = [("Rules check", wrap("".join(f"<div class=t><h3>{t}</h3>{_rules(x)}</div>" for t, x in side))),
           ("Players", wrap("".join(f"<div class=t><h3>{t}</h3>{_players(x)}</div>" for t, x in side)))]  # fmt: skip
    if any(r["outside"] for x in (c["you"], c["best"]) for r in x["rows"]):
        out[1] = (out[1][0], out[1][1] + wrap("<div class=t><small>* not in this team's 2027 squad (keeps his current price and value)</small></div>"))
    return out


def method_note(result) -> str:
    c = getattr(result.data, "attrs", {}).get("card")
    if not c:
        return ""
    bt = c["beta"]
    return (
        f"Value basis: {c['basis']}. Win % = logistic(slope x (XII value - {_n(c['avg'])}, the mean of the ten best XIIs)); slope {bt['beta']:.2f} "
        f"(10th to 90th percentile {_n(bt['lo'], 2)} to {_n(bt['hi'], 2)}, fitted on {bt['n']} IPL 2024-26 matches). Playoff and title % from "
        f"{c['seasons']:,} simulated seasons, other nine teams on their best XII. Ranges are 10th to 90th percentile over the slope and value uncertainty."
    )
