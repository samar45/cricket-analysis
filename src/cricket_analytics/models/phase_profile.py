"""Phase profile: how a player does in the powerplay / middle / death, shrunk and ranked among peers, plus a specialist tag.

Per role (bat / bowl) and phase, four metrics, each a mean of a per-row value x (so worth.fit_k / worth.shrink apply as they are):
  bowl  econ (runs conceded), wk (bowler wicket), dot, bnd (boundary)      rows = every delivery he bowled
  bat   sr (bat runs), out (dismissed), dot, bnd                          rows = balls faced (not wides)
Shrinkage: value = (sum x + k * league mean) / (n + k), k from worth.fit_k on IPL 2019+ player-season-phase cells (reliability 0.5 at k rows);
wickets / dismissals (wk, out) get k clamped to [WK_K_MIN, WK_K_MAX] because they are mostly luck over a few hundred balls.
Percentile: share of peers (players with >= MIN_BALLS legal balls in THAT phase, in the same scope) he beats, direction applied.
Composite per phase = percentile (among peers) of the plain average of his four metric percentiles.
Tag: a phase is "good" when he has >= MIN_BALLS there and composite >= GOOD_PCT. See `tag`.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..db import query
from ..sql import fragments as F
from ..sql.filters import Filters
from . import worth as W

MIN_BALLS = 60  # balls in the phase to count as a peer / to be "good" there
GOOD_PCT = 60  # composite percentile that counts as good
MAIN_SHARE = 0.5  # share of his balls that makes a phase "his" phase
WK_K_MIN, WK_K_MAX = 400.0, 1500.0
K_FIT_MIN_N = 30  # cell floor for the k fit
LABEL = {"powerplay": "Powerplay", "middle": "Middle", "death": "Death"}
SHORT = {"powerplay": "PP", "middle": "Middle", "death": "Death"}

_ind = lambda cond: f"CASE WHEN {cond} THEN 1 ELSE 0 END"  # noqa: E731
# metric -> (SQL of x, direction)
X = {
    "bowl": {"econ": (F.RUNS_CONCEDED, -1), "wk": (_ind(F.BOWLER_WICKET), 1), "dot": (_ind(F.IS_DOT), 1), "bnd": (_ind(f"{F.IS_FOUR} OR {F.IS_SIX}"), -1)},
    "bat": {"sr": ("d.runs_batter", 1), "out": (_ind(F.BATTER_OUT), -1), "dot": (_ind(F.IS_DOT), -1), "bnd": (_ind(f"{F.IS_FOUR} OR {F.IS_SIX}"), 1)},
}
ROLE_COL = {"bowl": "d.bowler", "bat": "d.batter"}
ROLE_ROWS = {"bowl": "1=1", "bat": F.BALL_FACED}
LABELS = {
    "bowl": {"econ": "Economy", "wk": "Balls per wicket", "dot": "Dot %", "bnd": "Boundary %"},
    "bat": {"sr": "Strike rate", "out": "Balls per dismissal", "dot": "Dot %", "bnd": "Boundary %"},
}


def _cells(role: str, f: Filters) -> pd.DataFrame:
    """Per (player, competition, season, phase): rows, legal balls and sum x / sum x^2 for each metric."""
    w, p = f.where(role)
    sums = ", ".join(f"SUM({x}) AS s_{k}, SUM(({x}) * ({x})) AS q_{k}" for k, (x, _) in X[role].items())
    sql = f"""SELECT {ROLE_COL[role]} AS player, m.competition, m.season, {F.phase_sql()} AS phase, COUNT(*)::DOUBLE AS n,
        COUNT(*) FILTER (WHERE {F.LEGAL_BALL})::DOUBLE AS legal,
        {sums}
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {w} AND {ROLE_ROWS[role]} GROUP BY ALL"""
    return query(sql, p)


@lru_cache(maxsize=4)
def _k_table(role: str) -> dict:
    """(metric, phase) -> k, fitted once on IPL 2019+ so every scope (one season, other leagues) uses the same reliability."""
    c = _cells(role, Filters(competition="ipl", season_from=2019))
    out = {}
    for ph in F.PHASES:
        cp = c[(c.phase == ph) & (c.n >= K_FIT_MIN_N)]
        for k in X[role]:
            kk, _ = W.fit_k(cp.assign(s1=cp[f"s_{k}"], s2=cp[f"q_{k}"]))
            if k in ("wk", "out"):  # luck-heavy: clamp the fitted k into a wide range (a failed fit means "almost all luck")
                kk = min(max(kk, WK_K_MIN), WK_K_MAX) if np.isfinite(kk) else WK_K_MAX
            out[(k, ph)] = kk if np.isfinite(kk) else 5000.0
    return out


def _pct(v: pd.Series, peers: pd.Series, direction: int) -> pd.Series:
    """Percentile (0-100, 100 = best) of v among the sorted peer values; ties count half."""
    s = np.sort(peers.to_numpy(float) * direction)
    x = v.to_numpy(float) * direction
    return pd.Series((np.searchsorted(s, x, "left") + np.searchsorted(s, x, "right")) / 2 / len(s) * 100, index=v.index)


@lru_cache(maxsize=16)
def table(role: str, competition: str | None, y0: int, y1: int | None) -> pd.DataFrame:
    """One row per (player, phase) in scope: balls, shrunk value + pctile per metric, composite pctile. All players, peers marked."""
    c = _cells(role, Filters(competition=competition, season_from=y0, season_to=y1))
    if c.empty:
        return c
    g = c.drop(columns=["competition", "season"]).groupby(["player", "phase"]).sum().reset_index()
    kt = _k_table(role)
    out = g[["player", "phase"]].copy()
    out["balls"] = g.n if role == "bat" else g.legal
    out["peer"] = out.balls >= MIN_BALLS
    out["cnt"] = g.s_sr if role == "bat" else g.s_wk  # runs scored / wickets taken
    pct_cols = []
    for ph in F.PHASES:
        s = g.phase == ph
        ratio = g.n[s].sum() / max(g.legal[s].sum(), 1.0)  # bowling rows include wides / no-balls; per-legal-ball displays scale by this
        for k, (_, direc) in X[role].items():
            mu = g[f"s_{k}"][s].sum() / g.n[s].sum()
            rate = (g[f"s_{k}"][s] + kt[(k, ph)] * mu) / (g.n[s] + kt[(k, ph)])
            r = rate * (ratio if role == "bowl" else 1.0)
            out.loc[s, k] = {"econ": r * 6, "sr": r * 100, "dot": r * 100, "bnd": r * 100, "wk": 1 / r.where(r > 0), "out": 1 / r.where(r > 0)}[k]
            out.loc[s, f"p_{k}"] = _pct(rate, rate[out.peer[s]], direc)
            pct_cols.append(f"p_{k}")
    pct_cols = list(dict.fromkeys(pct_cols))
    out["avg"] = out[pct_cols].mean(axis=1)
    out["comp"] = np.nan
    for ph in F.PHASES:
        s = out.phase == ph
        if (s & out.peer).any():
            out.loc[s, "comp"] = _pct(out.avg[s], out.avg[s & out.peer], 1)
    return out


def tag(balls: dict, comp: dict, role: str) -> str | None:
    """Specialist tag from balls and composite percentile per phase (dicts keyed by phase). None when he has no phase with MIN_BALLS."""
    tot = sum(balls.values())
    if not any(b >= MIN_BALLS for b in balls.values()):
        return None
    good = [p for p in F.PHASES if balls.get(p, 0) >= MIN_BALLS and comp.get(p, 0) >= GOOD_PCT]
    main = max(F.PHASES, key=lambda p: balls.get(p, 0))
    main_share = balls.get(main, 0) / tot
    if len(good) == 3:
        return "Complete"
    if len(good) == 2:
        return "Two-phase (" + "+".join(SHORT[p] for p in good) + ")"
    if len(good) == 1:
        p = good[0]
        if main_share >= MAIN_SHARE and p == main:
            return "Finisher" if (role == "bat" and p == "death") else f"{LABEL[p]}{'-overs' if p == 'middle' else ''} specialist"
        return f"Good in {LABEL[p].lower()}"
    return "Limited role" if main_share >= MAIN_SHARE else "No standout phase"


def profile(player: str, competition: str | None = "ipl", y0: int = 2023, y1: int | None = None, roles=("bowl", "bat")) -> dict:
    """{role: dict(tag, balls, share, comp, cnt, grid)}; grid = long DataFrame (metric, phase, value, pct) in display order.
    Roles where he has no rows are left out."""
    res = {}
    for role in roles:
        t = table(role, competition, y0, y1)
        if t.empty:
            continue
        mine = t[t.player == player].set_index("phase").reindex(F.PHASES)
        if mine.balls.fillna(0).sum() == 0:
            continue
        balls = mine.balls.fillna(0).astype(int).to_dict()
        comp = mine.comp.to_dict()
        rows = []
        for k in X[role]:
            for ph in F.PHASES:
                rows.append(dict(metric=LABELS[role][k], phase=ph, value=mine.loc[ph, k], pct=mine.loc[ph, f"p_{k}"]))
        res[role] = dict(
            tag=tag(balls, {p: (0 if pd.isna(v) else v) for p, v in comp.items()}, role), balls=balls,
            share={p: b / sum(balls.values()) for p, b in balls.items()}, comp=comp, cnt=mine.cnt.fillna(0).astype(int).to_dict(),
            grid=pd.DataFrame(rows),
        )
    return res
