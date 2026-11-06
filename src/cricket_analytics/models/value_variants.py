"""Value variants tested against the flat Runs Added value with the backtest (docs/VALUE_backtest.md, M10).

1. Phase weighting: runs added in the powerplay / middle / death, each times a weight = wins per run in that phase (fitted on IPL
   seasons up to X only: slope of centred win-probability-added on runs added over player-season-phase cells, divided by the same
   slope for all phases pooled). A weight above 1 = a run in that phase moves the win chance more than the average run.
2. Indian / overseas replacement: replacement level (runs added per 100 balls of the players outside their team's top 11, next
   season) estimated separately for Indian and overseas players, WAR above the group's own replacement.

Both register backtest predictors (`ipl3_ph`, `ipl3_wpa`, `ipl3_grp`) and truths (`truth_wpa`, `truth_grp`). Nothing here changes an
existing module or CSV; a variant is wired into a product only if the backtest keeps it.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..analysis.wpa import ball_wpa
from ..reference import REFERENCE_DIR
from ..sql.filters import Filters
from . import war as W
from .backtest import K_SHRINK, _frame, auctions, player_year, predictor, tables  # noqa: F401

PHASES = ("powerplay", "middle", "death")
MIN_CELL = 30  # balls in a player-season-phase cell to enter the weight fit


# ------------------------------------------------------------------------------------------ win-probability table
@lru_cache(maxsize=1)
def wpa_table() -> pd.DataFrame:
    """IPL win probability added per player, role, season (calendar year), phase. Centred: the average player per ball in each
    role-season is 0 (WPA is not zero-sum between batting and bowling). Columns: player, role, sy, phase, n (balls credited), wpa."""
    d = ball_wpa(Filters(competition="ipl"))
    d["phase"] = np.where(d.over_num < 6, "powerplay", np.where(d.over_num < 15, "middle", "death"))
    out = []
    for role, who, col in (("bat", "bat_who", "bat_wpa"), ("bowl", "bowler", "bowl_wpa")):
        g = d.groupby([who, "year", "phase"]).agg(n=(col, "size"), wpa=(col, "sum")).reset_index()
        g.columns = ["player", "sy", "phase", "n", "wpa"]
        mu = g.groupby("sy").wpa.transform("sum") / g.groupby("sy").n.transform("sum")
        g["wpa"] = g.wpa - mu * g.n
        out.append(g.assign(role=role))
    return pd.concat(out, ignore_index=True)


def truth_wpa(T: pd.DataFrame, t: int) -> pd.DataFrame:
    """Backtest truth in win-probability points (x100): bat / bowl WPA of IPL season t, balls credited as the cut-off."""
    w = wpa_table()
    w = w[w.sy == t]
    cols = {}
    for r in ("bat", "bowl"):
        g = w[w.role == r].groupby("player")[["n", "wpa"]].sum()
        cols[r], cols[f"{r}_balls"], cols[f"{r}_rate"] = g.wpa * 100, g.n, g.wpa * 100 / g.n
    out = pd.DataFrame(cols)
    out[["bat", "bowl", "bat_balls", "bowl_balls"]] = out[["bat", "bowl", "bat_balls", "bowl_balls"]].fillna(0.0)
    return out


# ------------------------------------------------------------------------------------------ 1. phase weights
def phase_weights(T: pd.DataFrame, X: int) -> dict:
    """{role: {phase: weight}} fitted on IPL seasons <= X. weight = slope(phase) / slope(all phases pooled), slope = sum(wpa*ra) /
    sum(ra^2) over player-season cells (through the origin)."""
    ipl = T[(T.comp == "ipl") & (T.sy <= X)]
    w = wpa_table()
    w = w[w.sy <= X]
    out = {}
    for r in ("bat", "bowl"):
        ra = ipl[ipl.role == r].groupby(["player", "sy", "phase"]).ra.sum().rename("ra").reset_index()
        m = ra.merge(w[w.role == r], on=["player", "sy", "phase"])
        m = m[m.n >= MIN_CELL]
        s = {p: (g.wpa * g.ra).sum() / (g.ra**2).sum() for p, g in m.groupby("phase")}
        tot = m.groupby(["player", "sy"])[["wpa", "ra"]].sum()
        flat = (tot.wpa * tot.ra).sum() / (tot.ra**2).sum()
        out[r] = {p: float(s[p] / flat) for p in PHASES}
    return out


def _phase_value(T, X, weights: dict | None, years: int = 3) -> pd.DataFrame:
    lo = max(W.ERA_IPL, X - years + 1)
    d = T[(T.comp == "ipl") & (T.sy >= lo) & (T.sy <= X)]
    n = X - lo + 1
    cols = {}
    for r in ("bat", "bowl"):
        g = d[d.role == r].copy()
        g["v"] = g.ra * (g.phase.map(weights[r]) if weights else 1.0)
        s = g.groupby("player").agg(v=("v", "sum"), b=("balls", "sum"))
        cols[r], cols[f"{r}_rate"] = s.v / n, s.v / s.b
    return pd.DataFrame(cols)


@predictor("ipl3_ph", "rank")
def ipl3_ph(T, X, ctx):
    """ipl3 with phase-weighted runs added; weights fitted on seasons <= X."""
    return _phase_value(T, X, phase_weights(T, X))


@predictor("ipl3_dth", "rank")
def ipl3_dth(T, X, ctx):
    """Death-overs runs added only (not fitted: a test of 'death value repeats better')."""
    z = {"powerplay": 0.0, "middle": 0.0, "death": 1.0}
    return _phase_value(T, X, {"bat": z, "bowl": z})


@predictor("ipl3_wpa", "rank")
def ipl3_wpa(T, X, ctx):
    """Mean WPA (win-probability points) per season over the last 3 Impact-era IPL seasons: the 'just use WPA' baseline."""
    lo = max(W.ERA_IPL, X - 2)
    w = wpa_table()
    w = w[(w.sy >= lo) & (w.sy <= X)]
    cols = {}
    for r in ("bat", "bowl"):
        g = w[w.role == r].groupby("player")[["n", "wpa"]].sum()
        cols[r], cols[f"{r}_rate"] = g.wpa * 100 / (X - lo + 1), g.wpa * 100 / g.n
    return pd.DataFrame(cols)


# ------------------------------------------------------------------------------------------ 2. Indian / overseas replacement
@lru_cache(maxsize=1)
def overseas_map() -> pd.Series:
    """cricsheet_name -> True (overseas) / False (Indian), from the auction, contract and retention lists. Disagreements: overseas wins."""
    parts = []
    for f in ("ipl_auctions.csv", "ipl_contracts.csv", "ipl_retentions.csv"):
        d = pd.read_csv(REFERENCE_DIR / f)
        if "overseas" in d and "cricsheet_name" in d:
            parts.append(pd.DataFrame({"p": d.cricsheet_name, "o": d.overseas.astype(str).str.lower().map({"true": True, "false": False})}))
    a = pd.concat(parts).dropna()
    return a.groupby("p").o.max()


@lru_cache(maxsize=1)
def _apps() -> pd.DataFrame:
    return W.season_table("ipl")[1]


def replacement_by_group(T: pd.DataFrame, X: int, cut: int = 11) -> pd.DataFrame:
    """Runs added per 100 balls of players outside their team's top `cut` (by matches, then balls) the season before, taken from
    seasons <= X (lag 1, as war.replacement), split Indian / overseas. Impact-era seasons only. Rows: role x group."""
    ipl = T[(T.comp == "ipl") & (T.sy <= X)]
    apps = _apps()
    apps = apps[apps.sy <= X]
    a = W._usage_rank(ipl, apps)
    bench = a[(a.rk > cut) & (a.sy >= W.ERA_IPL - 1)].groupby(["sy", "player"]).size().rename("f").reset_index()
    ps = player_year(ipl, ["ipl"]).assign(sy=lambda d: d.sy - 1)
    om = overseas_map()
    rows = []
    for r in ("bat", "bowl"):
        z = ps[(ps.role == r) & (ps.sy >= W.ERA_IPL - 1)].merge(bench, on=["sy", "player"])
        z["os"] = z.player.map(om)
        for g, name in ((False, "indian"), (True, "overseas"), (None, "all")):
            q = z if g is None else z[z.os == g]
            rows.append(dict(role=r, group=name, per100=q.ra.sum() / q.balls.sum() * 100, balls=int(q.balls.sum()), players=len(q)))
    return pd.DataFrame(rows)


def _shift(repl: pd.DataFrame) -> dict:
    """(role, group) -> replacement per ball RELATIVE to the pooled replacement: only the Indian / overseas difference is applied,
    so the overall level (which the flat WAR already sets) does not change."""
    rt = {(r.role, r.group): r.per100 / 100 for r in repl.itertuples()}
    return {(r, g): v - rt[r, "all"] for (r, g), v in rt.items()}


def grp_value(T: pd.DataFrame, X: int, years: int = 3, repl: pd.DataFrame | None = None) -> pd.DataFrame:
    """Mean per season over the window of (runs added - group replacement shift x balls); the shift is the group's replacement minus
    the pooled one. Unknown nationality: no shift."""
    repl = replacement_by_group(T, X) if repl is None else repl
    rt = _shift(repl)
    lo = max(W.ERA_IPL, X - years + 1)
    d = T[(T.comp == "ipl") & (T.sy >= lo) & (T.sy <= X)]
    om = overseas_map()
    n = X - lo + 1
    cols = {}
    for r in ("bat", "bowl"):
        g = d[d.role == r].groupby("player")[["balls", "ra"]].sum()
        grp = g.index.map(om).map({False: "indian", True: "overseas"}).fillna("all")
        v = g.ra - np.array([rt[r, x] for x in grp]) * g.balls
        cols[r], cols[f"{r}_rate"] = v / n, v / g.balls
    return pd.DataFrame(cols)


@predictor("ipl3_grp", "rank")
def ipl3_grp(T, X, ctx):
    return grp_value(T, X)


def truth_grp(T: pd.DataFrame, t: int) -> pd.DataFrame:
    """Truth for the scarcity variant: IPL season t runs added minus the Indian / overseas replacement shift (fitted on seasons < t)."""
    repl = replacement_by_group(T[T.sy < t], t - 1)
    rt = _shift(repl)
    d = T[(T.comp == "ipl") & (T.sy == t)]
    om = overseas_map()
    cols = {}
    for r in ("bat", "bowl"):
        g = d[d.role == r].groupby("player")[["balls", "ra"]].sum()
        grp = g.index.map(om).map({False: "indian", True: "overseas"}).fillna("all")
        cols[r] = g.ra - np.array([rt[r, x] for x in grp]) * g.balls
        cols[f"{r}_balls"], cols[f"{r}_rate"] = g.balls, cols[r] / g.balls
    out = pd.DataFrame(cols)
    out[["bat", "bowl", "bat_balls", "bowl_balls"]] = out[["bat", "bowl", "bat_balls", "bowl_balls"]].fillna(0.0)
    return out


# ------------------------------------------------------------------------------------------ side-by-side for a few players
def compare(players, X: int = 2025, first: int = W.ERA_IPL, last: int = 2026) -> pd.DataFrame:
    """Per IPL season of each player: flat WAR (as war.py), phase-weighted WAR (weights fitted on seasons <= X) and WAR above the
    Indian / overseas replacement (replacement fitted on seasons <= X). Phase and group variants subtract the same kind of
    replacement x balls as the flat WAR, so only the weights / the replacement level differ. Optional views, not defaults."""
    T = tables()
    ipl = T[(T.comp == "ipl") & T.player.isin(list(players)) & (T.sy.between(first, last))]
    prm = W.load_params()
    wt, repl = phase_weights(T, X), _shift(replacement_by_group(T, X))
    om = overseas_map()
    rows = []
    for (p, sy), g in ipl.groupby(["player", "sy"]):
        e = prm["era"][W.era_key(sy)]
        grp = {False: "indian", True: "overseas"}.get(om.get(p), "all")
        row = dict(player=p, season=sy, group=grp)
        for tag in ("flat", "phase", "group"):
            row[f"war_{tag}"] = 0.0
        for r, b in g.groupby("role"):
            ra, balls = b.ra.sum(), b.balls.sum()
            wra = (b.ra * b.phase.map(wt[r])).sum()
            base = e["repl"][r] / 100
            row[f"{r}_balls"] = int(balls)
            row[f"{r}_ra"] = round(ra, 1)
            row["war_flat"] += (ra - base * balls) / e["rpw"]
            row["war_phase"] += (wra - base * balls) / e["rpw"]
            row["war_group"] += (ra - (base + repl[r, grp]) * balls) / e["rpw"]
        rows.append(row)
    return pd.DataFrame(rows).round(2)
