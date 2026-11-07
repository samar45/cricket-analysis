"""Player page: one player's header, WAR v3 by season, worth metrics, phase and matchup splits. Numbers only; details in expanders.

All numbers come from `models.player_card.build` (which reuses the war, player_worth, dismissal_profile and pace_vs_spin modules),
cached here; this file only lays them out.
"""

from html import escape as esc

import pandas as pd
import streamlit as st
import ui

from cricket_analytics import api, competitions
from cricket_analytics.models import player_card as PC

CSS = """<style>
.pp{font:13px/1.3 system-ui,Segoe UI,sans-serif;font-variant-numeric:tabular-nums}
.pp h4{margin:14px 0 4px;font-size:11px;font-weight:600;letter-spacing:.08em;opacity:.65;text-transform:uppercase}
.pp table{width:100%;border-collapse:collapse}
.pp th,.pp td{padding:3px 8px;border-bottom:1px solid rgba(128,128,128,.28);text-align:right;white-space:nowrap}
.pp th{font-size:11px;font-weight:600;opacity:.65}.pp th:first-child,.pp td:first-child{text-align:left}
.pp small{opacity:.6;font-size:10.5px;margin-left:3px}
.pp .up{color:#2e9e5b}.pp .dn{color:#e5534b}
.pp .hd{display:flex;gap:26px;flex-wrap:wrap;margin:6px 0 4px}
.pp .hd div{font-size:15px;font-weight:600}.pp .hd .l{display:block;font-size:10.5px;font-weight:600;opacity:.6;letter-spacing:.06em}
.pp .big,.pp .big span{font-size:30px;font-weight:700;line-height:1.1}
.pp .bar{display:inline-block;width:110px;height:8px;border-radius:4px;background:rgba(128,128,128,.25);vertical-align:middle;margin-left:8px;overflow:hidden}
.pp .bar i{display:block;height:100%;background:#e0a800}
</style>"""
M = "−"


def n(x, d=2, sign=False) -> str:
    return "-" if x is None or pd.isna(x) else (f"{x:+.{d}f}" if sign else f"{x:.{d}f}").replace("-", M)


def tint(x, d=2) -> str:
    return f'<span class="{"up" if x > 0.004 else "dn" if x < -0.004 else ""}">{n(x, d, True)}</span>'


def table(df: pd.DataFrame, fmt: dict | None = None) -> str:
    fmt = fmt or {}
    head = "".join(f"<th>{esc(str(c).replace('_', ' '))}</th>" for c in df.columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{fmt[c](v) if c in fmt else ('-' if pd.isna(v) else esc(str(v)))}</td>" for c, v in r.items()) + "</tr>"
        for _, r in df.iterrows()
    )
    return f"<div class=pp><table><tr>{head}</tr>{rows}</table></div>"


def show(html: str) -> None:
    st.markdown(CSS + html, unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner="Building the player card...")
def card(player: str, competition: str | None, y0: int, y1: int | None) -> dict:
    return PC.build(player, competition, y0, y1)


def _header(c: dict) -> None:
    h, v, o = c["header"], c["value"], c["outlook"]
    cells = [("Player", esc(c["player"])), ("Team", esc(" / ".join(h["teams"]) or "-")), ("Role", h["role"])]
    if h["role"] != "bowler":
        cells.append(("Bats", h["bat_hand"]))
    if h["role"] != "batter":
        cells.append(("Bowls", h["bowl_type"]))
    if h["keeper"] in ("yes", "sometimes"):
        cells.append(("Keeper", h["keeper"]))
    cells.append(("Age", "-" if h["age"] is None else f"{h['age']:.0f}"))
    show("<div class=pp><div class=hd>" + "".join(f"<div><span class=l>{a.upper()}</span>{b}</div>" for a, b in cells) + "</div></div>")


def _war(c: dict) -> None:
    w, v, o = c["war"], c["value"], c["outlook"]
    cells = []
    if len(w):
        cells.append(("WAR v3 total", f"<b class=big>{tint(w.war.sum())}</b>"))
        cells.append(("Main-job WAR", tint(w.main_war.sum())))
    if v:
        cells.append((f"Recent value, {v['team']} 2027", f"{tint(v['value'])}<small>{n(v['lo'], 1)} / {n(v['hi'], 1)}</small>"))
        cells.append(("Salary, cr", n(v["salary"])))
    if o:
        cells.append(("Expected matches", f"{o['expected']:.0f}<small>{o['lo']:.0f} / {o['hi']:.0f}</small>"))
    if cells:
        show("<div class=pp><div class=hd>" + "".join(f"<div><span class=l>{a.upper()}</span>{b}</div>" for a, b in cells) + "</div></div>")
    if len(w):
        t = w.sort_values("season")[["season", "bat_balls", "bowl_balls", "bat_war", "bowl_war", "war", "main_war"]]
        t = t.rename(columns={"bat_war": "bat", "bowl_war": "bowl", "war": "total", "main_war": "main"})
        show("<div class=pp><h4>WAR v3 by season</h4></div>" + table(t, {"season": lambda v: str(int(v)), "bat_balls": lambda v: f"{v:.0f}", "bowl_balls": lambda v: f"{v:.0f}",
                                                                          "bat": tint, "bowl": tint, "total": tint, "main": tint}))
    elif c["competition"] == "ipl":
        st.caption("No IPL WAR in these seasons.")
    else:
        st.caption("WAR is measured for the IPL only.")


def _worth(c: dict) -> None:
    for role, w in c["worth"].items():
        if w.empty:
            continue
        rows = "".join(
            f"<tr><td>{esc(r.metric)}</td><td>{r.value:.1f}</td><td>{r.pctile:.0f}<span class=bar><i style='width:{r.pctile:.0f}%'></i></span></td><td>{r.n}</td></tr>"
            for r in w.itertuples()
        )
        show(f"<div class=pp><h4>Player worth, {role}</h4><table><tr><th>Metric</th><th>Value</th><th>Percentile</th><th>Balls</th></tr>{rows}</table></div>")


def _phases(c: dict) -> None:
    for role, t in c["phases"].items():
        if len(t):
            show(f"<div class=pp><h4>Phases, {role}</h4></div>" + table(t))


def _splits(c: dict) -> None:
    for title, t in c["splits"].items():
        if len(t):
            show(f"<div class=pp><h4>{title}</h4></div>" + table(t))


def page() -> None:
    st.title("Player")
    a, b, d = st.columns([2, 2, 2])
    comp = d.selectbox("Competition", list(competitions.COMPETITIONS), index=list(competitions.COMPETITIONS).index("ipl"), format_func=ui.comp_label, key="pl_comp")
    q = a.text_input("Search a name", key="pl_q", placeholder="e.g. bumrah")
    names = [r["name"] for r in api.resolve_player(q, comp, limit=15)] if q.strip() else ui.choices("player", comp, None)[:500]
    if not names:
        st.info("No player found.")
        return
    who = b.selectbox("Player", names, key="pl_who", index=0)
    years = sorted({int(str(s)[:4]) for s in ui.choices("season", comp, None)})
    y0, y1 = st.select_slider("Seasons", years, value=(max(min(years), 2023) if comp == "ipl" else years[max(len(years) - 4, 0)], years[-1]), key="pl_years")
    try:
        c = card(who, comp, y0, y1)
    except ValueError as e:
        st.warning(str(e))
        return
    _header(c)
    _war(c)
    _worth(c)
    _phases(c)
    _splits(c)
    for role, h in c["highlights"].items():
        if len(h):
            with st.expander(f"Best matches, {role}"):
                show(table(h.drop(columns=["match_id", "innings"]).assign(date=lambda x: x.date.astype(str).str[:10])))
    if len(c["dismissals"]):
        with st.expander("How he gets out"):
            show(table(c["dismissals"].drop(columns=["batter"])))
