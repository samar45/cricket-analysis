"""Player value card: the few numbers a reel card shows for one player (the Player page's headline, as a flat table)."""

import pandas as pd

from ..models import player_card as PC
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters, explain_empty

COLS = ["section", "label", "value", "lo", "hi", "pctile", "n", "text"]


@module(
    id="player_card",
    title="Player value card (WAR v3, worth metrics, expected matches, best match)",
    category="advanced",
    description="One player, one table of long rows (section = header | war | worth | outlook | highlight): the headline of the Player page. "
    "Default scope IPL 2023 onwards. Reuses war, player_worth and player_outlook; see those modules for what each number means.",
    params=[ParamSpec("player", "player", required=True, help="Exact player name (use resolve first)"), *std("competition", "season", super_overs=False)],
    caveats=[
        "Needs one player. Competition defaults to the IPL and seasons to 2023 onwards; WAR is measured for the IPL only (no war rows elsewhere).",
        "war rows: label = season year or 'total' (all seasons in scope); value = batting + bowling WAR v3, lo / hi = its 10-90% range (bootstrap over his own matches). worth rows: the kept metrics of his main job with percentile among peers (100 = best) and balls.",
        "outlook: expected matches next IPL season with the 10-90% range of 2024-26 outcomes (lo, hi). highlight: his best single match against the rest of the match (value = runs above / saved).",
    ],
)
def player_card(f: Filters) -> pd.DataFrame:
    if not f.player:
        raise ValueError("player_card needs a player")
    y0 = f.season_from or (min(int(str(s)[:4]) for s in f.values("season")) if f.values("season") else 2023)
    y1 = f.season_to or (max(int(str(s)[:4]) for s in f.values("season")) if f.values("season") else None)
    c = PC.build(f.player, f.competition or "ipl", y0, y1)
    h, rows = c["header"], []
    rows.append(dict(section="header", label="player", text=f.player))
    rows.append(dict(section="header", label="role", text=h["role"]))
    for role, v in c["phase_profile"].items():
        if v["tag"]:
            rows.append(dict(section="header", label="tag", text=f"{role}: {v['tag']}"))
    rows.append(dict(section="header", label="team", text=(c["value"] or {}).get("team") or (h["teams"][0] if h["teams"] else "-")))
    for r in c["war"].sort_values("season").itertuples():
        rows.append(dict(section="war", label=str(int(r.season)), value=r.war, lo=r.war_lo, hi=r.war_hi))
    if len(c["war"]):
        rows.append(dict(section="war", label="total", value=c["war"].war.sum(), lo=c["war_total"]["lo"], hi=c["war_total"]["hi"], n=len(c["war"])))
    for role, w in c["worth"].items():
        for r in w.itertuples():
            rows.append(dict(section="worth", label=r.metric, value=r.value, pctile=r.pctile, n=r.n, text=role))
    if c["outlook"]:
        o = c["outlook"]
        rows.append(dict(section="outlook", label="expected matches", value=o["expected"], lo=o["lo"], hi=o["hi"], text=o["evidence"]))
    for role, hl in c["highlights"].items():
        for r in hl.head(1).itertuples():
            fig = f"{r.runs} off {r.balls}" if role == "batting" else f"{r.wickets}/{r.runs} in {r.balls / 6:.1f} ov"
            rows.append(dict(section="highlight", label=f"v {r.opposition}, {str(r.date)[:4]}", value=r.runs_vs_match, text=fig))
    if len(rows) <= 3:
        raise explain_empty(f, "player card")
    return pd.DataFrame(rows).reindex(columns=COLS)
