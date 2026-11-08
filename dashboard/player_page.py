"""Player page: one player's header, WAR v3 by season, worth metrics, phase and matchup splits. Numbers only; details in expanders.

All numbers come from `models.player_card.build` (which reuses the war, player_worth, dismissal_profile and pace_vs_spin modules),
cached here; this file only lays them out.
"""

from html import escape as esc

import pandas as pd
import streamlit as st
import ui

from cricket_analytics import competitions
from cricket_analytics.models import phase_profile as PP
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
.pp .badge{display:inline-block;margin-left:8px;padding:1px 9px;border-radius:10px;font-size:12px;font-weight:600;background:rgba(224,168,0,.22);color:#e0a800;vertical-align:middle}
.pp .mb{display:inline-block;width:46px;height:6px;border-radius:3px;background:rgba(128,128,128,.25);vertical-align:middle;margin-left:6px;overflow:hidden}
.pp .mb i{display:block;height:100%;background:#e0a800}
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
    pp = c["phase_profile"]
    both = len(pp) > 1
    badges = "".join(f'<span class=badge>{"Bat: " if both and r == "batting" else "Bowl: " if both else ""}{esc(v["tag"])}</span>' for r, v in pp.items() if v["tag"])
    cells = [("Player", esc(c["player"]) + badges), ("Team", esc(" / ".join(h["teams"]) or "-")), ("Role", h["role"])]
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
    for role, p in c["phase_profile"].items():
        g, ph = p["grid"], list(p["balls"])
        cnt_label = "Runs" if role == "batting" else "Wickets"
        head = "<tr><th></th>" + "".join(f"<th>{PP.LABEL[x]}</th>" for x in ph) + "</tr>"
        top = [("Balls", [f"{p['balls'][x]}<small>{p['share'][x] * 100:.0f}%</small>" for x in ph]), (cnt_label, [f"{p['cnt'][x]:.0f}" for x in ph]),
               ("Phase score", [("-" if pd.isna(p["comp"][x]) else f"p{p['comp'][x]:.0f}") + ("" if p["balls"][x] >= PP.MIN_BALLS else "<small>few balls</small>") for x in ph])]
        rows = "".join(f"<tr><td>{a}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for a, vals in top)
        for m, gm in g.groupby("metric", sort=False):
            gm = gm.set_index("phase")
            cells = "".join(
                "<td>-</td>" if pd.isna(gm.value[x]) else f"<td>{gm.value[x]:.1f}<small>p{gm.pct[x]:.0f}</small><span class=mb><i style='width:{gm.pct[x]:.0f}%'></i></span></td>" for x in ph
            )
            rows += f"<tr><td>{m}</td>{cells}</tr>"
        show(f"<div class=pp><h4>Phase profile, {role}</h4><table>{head}{rows}</table></div>")
    if c["phase_profile"]:
        with st.expander("Method"):
            st.caption(
                f"Values are shrunk toward the league mean of that phase (empirical Bayes, k from season-to-season reliability; wickets and dismissals use a large k). "
                f"pNN = percentile among players with at least {PP.MIN_BALLS} balls in that phase in the same seasons. Phase score = percentile of the average of the four metric percentiles. "
                f"Tag: a phase is good with at least {PP.MIN_BALLS} balls and phase score of {PP.GOOD_PCT} or more; all three = Complete, two = Two-phase, one and over half his balls there = specialist "
                f"(batter death = Finisher), otherwise Limited role. Percentages beside Balls are his share of balls per phase."
            )


def _splits(c: dict) -> None:
    for title, t in c["splits"].items():
        if len(t):
            show(f"<div class=pp><h4>{title}</h4></div>" + table(t))


def page() -> None:
    st.title("Player")
    a, d = st.columns([4, 2])
    comp = d.selectbox("Competition", list(competitions.COMPETITIONS), index=list(competitions.COMPETITIONS).index("ipl"), format_func=ui.comp_label, key="pl_comp")
    who = a.selectbox("Player", ui.choices("player", comp, None), index=None, placeholder="Type to search a name, e.g. Bumrah", key="pl_who")
    if who is None:
        st.info("Pick a player.")
        return
    years = sorted({int(str(s)[:4]) for s in ui.choices("season", comp, None)})
    y0, y1 = st.select_slider("Seasons", years, value=(max(min(years), 2023) if comp == "ipl" else years[max(len(years) - 4, 0)], years[-1]), key="pl_years")
    sel = ui.gate("player", [who, comp, y0, y1])
    if sel is None:
        return
    with st.container(key="res_player"):
        _body(*sel)


def _body(who, comp, y0, y1) -> None:
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
