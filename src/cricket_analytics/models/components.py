"""Component (Marcel-style) projection of player value, "controllable" value, and split-half stability (docs/VALUE_m2.md).

Runs added (RA) of a player-season is split exactly into
    base      what his phase mix is worth for an average player (about 0; unshrunk)
    s_<class> the value of his deviation from the league rate of each ball outcome class (dot, 1-3, four, six, out / wicket,
              wide+no-ball for bowlers), at the league value of that class in that phase
    R         what is left (value differences inside a class, non-striker run-outs, centring)
so base + sum(s) + R = the RA used by WAR (models/war.py). Each part is projected on its own: weighted recent seasons, other
leagues at weight a and strength s, divided by (evidence balls + mk x k_class) where k_class is the stability constant (balls at
which reliability is 0.5) estimated by method of moments from earlier seasons only. Total = sum of parts -> pWAR as in war.py.
"Controllable" value keeps the dot / 1-3 / four / six / extras parts and shrinks the wicket part (and R) hard.

Run:  python -m cricket_analytics.models.components [stability|validate|beta|build]
"""

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from ..db import query
from ..sql.filters import Filters
from . import war as W
from .run_expectancy import BALL_COLS, USABLE, load, ra_state

PARAMS = W.DATA / "components_params.json"
CLS = {
    "bat": ["dot", "one3", "four", "six", "out"],
    "bowl": ["dot", "one3", "four", "six", "wkt", "ext"],
}
WK = {"bat": "out", "bowl": "wkt"}  # the luck-heavy class
K_HUGE = 1e7
CTRL_WK_MULT = 4.0  # controllable value: the wicket part is shrunk with 4x its stability constant (a priori choice)


# --------------------------------------------------------------------------- ball level
def ball_frames(comp: str, db_path=None) -> dict:
    """{'bat': df, 'bowl': df} one row per ball: comp, sy, season, match_id, date, innings, lb, player, cell (phase x wickets-down bucket, 0-8), c (outcome class code into CLS), ra (runs added credit of that ball, uncentred, as
    in war.season_table), runs (bat runs / runs conceded), isn (1 if the ball counts as a ball faced / legal ball bowled)."""
    st, sp = ra_state(Filters(competition=comp))
    sql = (
        f"WITH d AS ({st}) SELECT {BALL_COLS}, d.legal_before AS lb, d.max_balls AS mx, m.date, m.season "
        f"FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE}"
    )
    rows = W._int_cols(query(sql, sp, db_path=db_path))
    a = load().annotate(rows)
    a["sy"] = a.season.map(a.groupby("season").date.max().dt.year).astype(int)
    ph = np.select(
        [a.lb / a.mx < 0.3, a.lb / a.mx < 0.8], [0, 1], 2
    )  # powerplay / middle / death (6 and 16 overs of 20)
    wb = np.select(
        [a.wickets_before <= 1, a.wickets_before <= 4], [0, 1], 2
    )  # wickets down: 0-1 / 2-4 / 5+
    a["cell"] = ph * 3 + wb
    out = {}
    b = a[(a.faced == 1) | (a.striker_out == 1)]
    r = b.runs_batter.values
    c = np.select([b.striker_out == 1, r == 0, r == 4, r == 6], [4, 0, 2, 3], 1)
    out["bat"] = pd.DataFrame(
        dict(
            comp=comp,
            sy=b.sy.values,
            season=b.season.values,
            match_id=b.match_id.values,
            date=b.date.values,
            innings=b.innings.values,
            lb=b.lb.values,
            player=b.batter.values,
            cell=b.cell.values,
            c=c,
            ra=(b.runs_batter + b.vf * (b.ball_part + b.wkt_part * b.striker_out) + b.bat_k).values,
            runs=r,
            isn=b.faced.values,
        )
    )
    leg = a.legal.values == 1
    r = a.conceded.values
    c = np.select([~leg, a.bowler_wk == 1, r == 0, r == 4, r == 6], [5, 4, 0, 2, 3], 1)
    out["bowl"] = pd.DataFrame(
        dict(
            comp=comp,
            sy=a.sy.values,
            season=a.season.values,
            match_id=a.match_id.values,
            date=a.date.values,
            innings=a.innings.values,
            lb=a.lb.values,
            player=a.bowler.values,
            cell=a.cell.values,
            c=c,
            ra=(-a.conceded - a.vf * (a.ball_part + a.wkt_part * a.bowler_wk) + a.bowl_k).values,
            runs=r,
            isn=a.legal.values,
        )
    )
    return out


@lru_cache(maxsize=1)
def all_frames(leagues: tuple = tuple(W.LEAGUES)) -> dict:
    """{'bat': df, 'bowl': df} over all men's leagues (about 40 s and 1 GB the first time)."""
    parts = [ball_frames(c) for c in leagues]
    return {k: pd.concat([p[k] for p in parts], ignore_index=True) for k in ("bat", "bowl")}


# --------------------------------------------------------------------------- player-season component table
def _league_tab(fr: pd.DataFrame, K: int) -> pd.DataFrame:
    """Per (comp, sy, cell): N (counted balls), e_k (share of balls in class k), V_k (mean RA of class k), base = sum e_k V_k."""
    n = fr[fr.isn == 1].groupby(["comp", "sy", "cell"]).size().rename("N")
    g = fr.groupby(["comp", "sy", "cell", "c"]).ra.agg(["size", "sum"]).reset_index()
    t = g.pivot_table(
        index=["comp", "sy", "cell"], columns="c", values=["size", "sum"], fill_value=0.0
    )
    out = n.to_frame()
    for k in range(K):
        sz = t["size"][k] if k in t["size"] else 0.0
        sm = t["sum"][k] if k in t["sum"] else 0.0
        out[f"e{k}"] = (sz / out.N).reindex(out.index).fillna(0.0)
        out[f"V{k}"] = (sm / np.maximum(sz, 1)).reindex(out.index).fillna(0.0)
    out["base"] = sum(out[f"e{k}"] * out[f"V{k}"] for k in range(K))
    tot = fr.groupby(["comp", "sy"]).ra.sum()
    nn = fr[fr.isn == 1].groupby(["comp", "sy"]).size()
    out["mu"] = (tot / nn).reindex(out.index.droplevel(2)).values
    return out.reset_index()


def season_components(
    fr: pd.DataFrame, role: str, rows: pd.DataFrame
) -> tuple[pd.DataFrame, float]:
    """Player-season table for one role: comp, sy, player, n, B, s_<c>, D_<c> (deviation in counts), E_<c> (expected count), R.
    `rows` = war.all_tables() rows (centred sc, wk) so that B + sum s + R = sc + wk exactly. Also returns the per-ball variance
    of a ball's RA inside its class (used for the R stability constant)."""
    cls = CLS[role]
    K = len(cls)
    lt = _league_tab(fr, K)
    pc = fr.groupby(["comp", "sy", "player", "cell", "c"]).size().unstack(fill_value=0)
    pc = pc.reindex(columns=range(K), fill_value=0).reset_index()
    pc["n"] = (
        fr[fr.isn == 1]
        .groupby(["comp", "sy", "player", "cell"])
        .size()
        .reindex(pd.MultiIndex.from_frame(pc[["comp", "sy", "player", "cell"]]))
        .fillna(0)
        .values
    )
    pc = pc.merge(lt, on=["comp", "sy", "cell"], how="left")
    out = pd.DataFrame({"comp": pc.comp, "sy": pc.sy, "player": pc.player, "n": pc.n})
    out["B"] = pc.n * (pc.base - pc.mu)
    for k, name in enumerate(cls):
        out[f"D_{name}"] = pc[k] - pc.n * pc[f"e{k}"]
        out[f"E_{name}"] = pc.n * pc[f"e{k}"]
        out[f"s_{name}"] = out[f"D_{name}"] * pc[f"V{k}"]
    key = ["comp", "sy", "player"]
    out = out.groupby(key, as_index=False).sum()
    # residual: what the parts do not explain, so that the sum is exactly the WAR input
    rr = rows[rows.role == role].groupby(key, as_index=False)[["balls", "sc", "wk"]].sum()
    out = out.merge(rr, on=key, how="outer").fillna(0.0)
    out["ra"] = out.sc + out.wk
    out["R"] = out.ra - out.B - sum(out[f"s_{c}"] for c in cls)
    # per-ball variance of RA inside a class (for the stability constant of R)
    v = fr.merge(
        lt[["comp", "sy", "cell"] + [f"V{k}" for k in range(K)]], on=["comp", "sy", "cell"]
    )
    vk = v[[f"V{k}" for k in range(K)]].values[np.arange(len(v)), v.c.values]
    sig2 = float(((v.ra.values - vk) ** 2).mean())
    return out.drop(columns=["sc", "wk"]), sig2


@lru_cache(maxsize=1)
def tables() -> tuple[dict, dict]:
    """({role: player-season component table}, {role: sigma2 of R per ball})."""
    rows, _ = W.all_tables()
    allrows = pd.concat(rows.values(), ignore_index=True)
    fr = all_frames()
    tab, sig = {}, {}
    for role in ("bat", "bowl"):
        tab[role], sig[role] = season_components(fr[role], role, allrows)
    return tab, sig


# --------------------------------------------------------------------------- stability constants (method of moments, earlier seasons)
def mom_k(n, x, sig2):
    """Between-player variance tau2 of per-ball rates x (n balls each, sampling variance sig2 per ball; sig2 may be an array)
    by method of moments (weights n); k = sig2 / tau2 = the number of balls at which reliability is 0.5. Returns (k, tau2)."""
    n, x, sig2 = (np.asarray(v, float) for v in (n, x, sig2))
    sig2 = np.broadcast_to(sig2, n.shape)
    N = n.sum()
    xb = (n * x).sum() / N
    q = (n * (x - xb) ** 2).sum()
    tau2 = (q - (sig2 * (1 - n / N)).sum()) / (N - (n**2).sum() / N)
    sbar = (n * sig2).sum() / N
    return (float(sbar / tau2) if tau2 > 0 else K_HUGE), float(tau2)


def k_table(t: int, tab=None, sig=None, minb=30) -> dict:
    """{role: {class: k, 'R': k}} from player-seasons before year t (all men's leagues)."""
    if tab is None:
        tab, sig = tables()
    out = {}
    for role, cls in CLS.items():
        d = tab[role]
        d = d[(d.sy < t) & (d.n >= minb)]
        ks = {}
        for c in cls:
            e = d[f"E_{c}"] / d.n
            ks[c] = mom_k(d.n, d[f"D_{c}"] / d.n, e * (1 - e))[0]
        ks["R"] = mom_k(d.n, d.R / d.n, sig[role])[0]
        out[role] = ks
    return out


# --------------------------------------------------------------------------- panel
class Panel2:
    """player x year matrices for IPL ('I') and the other leagues pooled ('O'): balls, B, s_<c>, R. Same interface as war.Panel for
    `.g()`, `.players`, `.years`, so war.fit_balls / exp_balls work on it."""

    def __init__(self, tab: dict, y0=2008, y1=2027):
        self.years = list(range(y0, y1 + 1))
        self.players = sorted(set().union(*[set(d.player) for d in tab.values()]))
        pi = {p: i for i, p in enumerate(self.players)}
        self.M = {}
        for role, d in tab.items():
            d = d[(d.sy >= y0) & (d.sy <= y1)]
            cols = ["B", "R"] + [f"s_{c}" for c in CLS[role]]
            for tag, sel in (("I", d.comp == "ipl"), ("O", d.comp != "ipl")):
                x = d[sel]
                ri, ci = x.player.map(pi).values, (x.sy - y0).values
                for name, col in [("balls", "n")] + [(c, c) for c in cols]:
                    m = np.zeros((len(self.players), len(self.years)))
                    np.add.at(m, (ri, ci), x[col].values)
                    self.M[tag, role, name] = m

    def g(self, tag, role, col, y):
        return self.M[tag, role, col][:, y - self.years[0]]


def _evidence(P, role, name, t, a, s, ef, rw):
    num = den = 0.0
    for y in range(max(P.years[0], t - W.WINDOW), t):
        w = (1.0 if y >= ef else 0.0) * rw ** (t - 1 - y)
        wo = rw ** (t - 1 - y)
        mult = 1.0 if name == "B" else s
        num = num + w * P.g("I", role, name, y) + a * mult * wo * P.g("O", role, name, y)
        den = den + w * P.g("I", role, "balls", y) + a * wo * P.g("O", role, "balls", y)
    return num, den


def project_parts(P, role, t, prm, ks, wk_mult=1.0) -> tuple[dict, np.ndarray]:
    """{'B', class names..., 'R'} projected RA per ball and the evidence balls. prm[role] = dict(a, s, mk, rw);
    wk_mult scales the stability constant of the wicket class (controllable value uses CTRL_WK_MULT)."""
    q = prm[role]
    ef = W.ipl_from_for(P, t, prm["ipl_from"])
    out = {}
    for name in ["B"] + CLS[role] + ["R"]:
        col = name if name in ("B", "R") else f"s_{name}"
        num, den = _evidence(P, role, col, t, q["a"], q["s"], ef, q["rw"])
        if name == "B":
            out[name] = np.where(den > 0, num / (den + 50.0), 0.0)
        else:
            k = ks[role][name] * q["mk"] * (wk_mult if name == WK[role] else 1.0)
            out[name] = num / (den + k)
    return out, den


def controllable(parts: dict, role: str) -> np.ndarray:
    """Base + every class part (wicket part included as given, R dropped). Call project_parts with wk_mult > 1 first."""
    return parts["B"] + sum(parts[c] for c in CLS[role])


def _has_history(P, role, t) -> np.ndarray:
    return _evidence(P, role, "B", t, 1.0, 1.0, P.years[0], 1.0)[1] > 0


A_GRID, S_GRID, MK_GRID, RW_GRID = (
    (0.0, 0.5, 1.0),
    (0.5, 1.0),
    (0.5, 1.0, 2.0, 4.0),
    (1.0, 0.7, 0.5),
)


def _target_loss(P, role, targets, prm, ks, minb=60) -> tuple[np.ndarray, np.ndarray]:
    err, wt = [], []
    for t in targets:
        n = P.g("I", role, "balls", t)
        parts, _ = project_parts(P, role, t, prm, ks)
        real = sum(P.g("I", role, c, t) for c in ["B", "R"] + [f"s_{c}" for c in CLS[role]])
        m = (n >= minb) & _has_history(P, role, t)
        y = real / np.where(n > 0, n, np.nan)
        err.append((((y - sum(parts.values())) ** 2) * n)[m])
        wt.append(n[m])
    return np.concatenate(err), np.concatenate(wt)


def fit_components(P: Panel2, t: int, ipl_from=W.ERA_IPL, tab=None, sig=None) -> dict:
    """Grid search of a, s, mk, rw on pseudo-targets LEARN_FROM..t-1 (stability constants k from seasons before t)."""
    ks = k_table(t, tab, sig)
    tg = range(W.LEARN_FROM, t)
    prm = {"ipl_from": ipl_from, "k": ks}
    for role in ("bat", "bowl"):
        best = None
        for a in A_GRID:
            for s in S_GRID if a > 0 else (1.0,):
                for mk in MK_GRID:
                    for rw in RW_GRID:
                        q = dict(a=a, s=s, mk=mk, rw=rw)
                        e, w = _target_loss(P, role, tg, {"ipl_from": ipl_from, role: q}, ks)
                        v = (e.sum() / w.sum()) ** 0.5
                        if best is None or v < best[0]:
                            best = (v, q)
        prm[role] = best[1]
    return prm


# --------------------------------------------------------------------------- split-half stability (task 1)
STAB_COLS = {
    "bat": [
        "dot %",
        "1-3 run %",
        "four %",
        "six %",
        "dismissal rate",
        "runs per ball",
        "runs added per ball",
    ],
    "bowl": [
        "dot %",
        "1-3 run %",
        "four %",
        "six %",
        "wicket rate",
        "wides+no-balls %",
        "runs per ball",
        "runs added per ball",
    ],
}


def _indicators(d: pd.DataFrame, role: str) -> np.ndarray:
    c = d.c.values
    cols = [c == 0, c == 1, c == 2, c == 3, c == 4]
    if role == "bowl":
        cols.append(c == 5)
    cols += [d.runs.values, d.ra.values]
    return np.column_stack(cols).astype(float)


def _split_rates(d: pd.DataFrame, role: str, ns, unit: str):
    """For each sample size n (balls): players with at least n balls, first n balls (rounded up to a whole match for unit='match'),
    split into two halves (alternate matches or alternate balls); returns {n: (rates half A, rates half B, mean total balls)}."""
    d = d.sort_values(["player", "date", "match_id", "innings", "lb"], kind="stable").reset_index(
        drop=True
    )
    X = _indicators(d, role)
    pl = d.player.values
    newp = np.r_[True, pl[1:] != pl[:-1]]
    start = np.maximum.accumulate(
        np.where(newp, np.arange(len(d)), 0)
    )  # first row of this row's player
    j = np.arange(len(d)) - start
    mid = d.match_id.values
    newm = newp | np.r_[True, mid[1:] != mid[:-1]]
    mc = np.cumsum(newm)
    par = ((mc - mc[start]) % 2) if unit == "match" else (j % 2)
    last = np.r_[newm[1:], True]  # last row of a match
    mend = np.minimum.accumulate(np.where(last, np.arange(len(d)), len(d))[::-1])[::-1]
    pad = lambda a: np.vstack([np.zeros((1, a.shape[1])), np.cumsum(a, axis=0)])  # noqa: E731
    C0, C1 = pad(X * (par == 0)[:, None]), pad(X * (par == 1)[:, None])
    N0, N1 = (
        pad((par == 0)[:, None].astype(float))[:, 0],
        pad((par == 1)[:, None].astype(float))[:, 0],
    )
    pstart = np.flatnonzero(newp)
    pcount = np.diff(np.r_[pstart, len(d)])
    out = {}
    for n in ns:
        ok = pcount >= n
        s = pstart[ok]
        cut = mend[s + n - 1] if unit == "match" else s + n - 1
        a0, a1 = N0[cut + 1] - N0[s], N1[cut + 1] - N1[s]
        g = (a0 > 0) & (a1 > 0)
        s, cut, a0, a1 = s[g], cut[g], a0[g], a1[g]
        out[n] = (
            (C0[cut + 1] - C0[s]) / a0[:, None],
            (C1[cut + 1] - C1[s]) / a1[:, None],
            float((cut - s + 1).mean()) if len(s) else np.nan,
        )
    return out


def _fit_k(n, R, w):
    """k in R = n / (n + k) by weighted least squares over a log grid."""
    ks = np.geomspace(5, 2e5, 600)
    pred = n[:, None] / (n[:, None] + ks[None, :])
    err = (w[:, None] * (R[:, None] - pred) ** 2).sum(0)
    return float(ks[np.argmin(err)])


def _corr_cols(A, B):
    a, b = A - A.mean(0), B - B.mean(0)
    den = np.sqrt((a**2).sum(0) * (b**2).sum(0))
    return np.where(den > 0, (a * b).sum(0) / np.where(den > 0, den, 1), 0.0)


def stability(frames: pd.DataFrame, role: str, ns, unit="match", boot=200, seed=0) -> pd.DataFrame:
    """Split-half reliability per component. Columns: component, n50 (balls at reliability 0.5, i.e. the shrinkage constant k),
    n50_lo / n50_hi (90% range, bootstrap over players), n70 (= 7/3 x n50), reached (largest sample with data), R at each n
    (Spearman-Brown stepped-up split-half correlation), players at each n. `frames` = one role's ball frame."""
    sp = _split_rates(frames, role, ns, unit)
    names = STAB_COLS[role]
    rng = np.random.default_rng(seed)
    rows = []
    # reliabilities per n and per bootstrap draw
    ns_ok = [n for n in ns if len(sp[n][0]) >= 30]
    tot = np.array([sp[n][2] for n in ns_ok])
    w = np.array([len(sp[n][0]) for n in ns_ok], float)

    def reliab(idx_fn):
        R = []
        for n in ns_ok:
            A, B, _ = sp[n]
            i = idx_fn(len(A))
            r = _corr_cols(A[i], B[i])
            R.append(np.where(r > 0, 2 * r / (1 + r), 0.0))
        return np.array(R)  # n x K

    R0 = reliab(lambda m: np.arange(m))
    ks0 = [_fit_k(tot, R0[:, c], w) for c in range(len(names))]
    ks_b = np.array(
        [
            [_fit_k(tot, Rb[:, c], w) for c in range(len(names))]
            for Rb in (reliab(lambda m: rng.integers(0, m, m)) for _ in range(boot))
        ]
    )
    for c, name in enumerate(names):
        row = dict(
            component=name,
            n50=ks0[c],
            n50_lo=np.percentile(ks_b[:, c], 5),
            n50_hi=np.percentile(ks_b[:, c], 95),
            n70=ks0[c] * 7 / 3,
        )
        row["reached"] = int(max(tot))
        for n, r in zip(ns_ok, R0[:, c]):
            row[f"R@{n}"] = r
        rows.append(row)
    out = pd.DataFrame(rows)
    for n in ns_ok:
        out[f"players@{n}"] = len(sp[n][0])
    return out


# --------------------------------------------------------------------------- projection table (pWAR and controllable WAR)
def project_table2(
    P: Panel2, t: int, prm: dict, era: dict, bcoef: dict, wk_mult=CTRL_WK_MULT
) -> pd.DataFrame:
    """Like war.project_table with the component projection. Per role: <role>_rate (runs added per 100 balls), _balls (expected),
    _pwar, _cwar (controllable: wicket part shrunk with wk_mult x its constant, R dropped), _ev (evidence balls)."""
    e = era[W.era_key(t)]
    out = pd.DataFrame({"player": P.players})
    for role in ("bat", "bowl"):
        parts, den = project_parts(P, role, t, prm, prm["k"])
        pc, _ = project_parts(P, role, t, prm, prm["k"], wk_mult)
        eb = W.exp_balls(P, role, t, bcoef[role], prm["ipl_from"])
        rate, crate = sum(parts.values()), controllable(pc, role)
        out[f"{role}_rate"] = rate * 100
        out[f"{role}_crate"] = crate * 100
        out[f"{role}_balls"] = eb
        out[f"{role}_pwar"] = (rate - e["repl"][role] / 100.0) * eb / e["rpw"]
        out[f"{role}_cwar"] = (crate - e["repl"][role] / 100.0) * eb / e["rpw"]
        out[f"{role}_ev"] = den
    out["pwar"] = out.bat_pwar + out.bowl_pwar
    out["cwar"] = out.bat_cwar + out.bowl_cwar
    return out


def fixed_params(ks: dict, ipl_from=W.ERA_IPL) -> dict:
    """The untuned setting: constants from the stability estimate as they are (mk 1), equal recency weights, other leagues as in war.py."""
    return {
        "ipl_from": ipl_from,
        "k": ks,
        "bat": dict(a=1.0, s=0.5, mk=1.0, rw=1.0),
        "bowl": dict(a=1.0, s=1.0, mk=1.0, rw=1.0),
    }


# --------------------------------------------------------------------------- validation (same protocol as war.validate_players)
def holdout(rows, prm_all, tab, sig, targets=(2024, 2025, 2026), minb=100) -> dict:
    """For each target year t (data before t only): realised WAR of players with >= minb balls in t and some IPL ball the year before,
    against every method's prediction. Returns {role: dict(arrays..., 'meta': per-row year)}. Methods: pwar (current),
    comp (tuned components), comp0 (untuned), ctrl / ctrl0 (controllable, tuned / untuned), last (last season WAR), zero."""
    P1, P2 = W._panel(rows), Panel2(tab)
    Wt = W.war_table(rows["ipl"], prm_all)
    ps = W.player_year(rows["ipl"])
    out = {
        r: {
            k: []
            for k in (
                "a",
                "pwar",
                "comp",
                "comp0",
                "ctrl",
                "ctrl0",
                "last",
                "lastraw",
                "year",
                "rate_real",
                "n",
            )
        }
        for r in ("bat", "bowl")
    }
    out["rate"] = {r: {} for r in ("bat", "bowl")}
    fits = {}
    for t in targets:
        pr1 = W.fit_for(P1, t)
        pr2 = fit_components(P2, t, tab=tab, sig=sig)
        fits[t] = pr2
        ks = pr2["k"]
        pt1 = W.project_table(P1, t, pr1, prm_all["era"]).set_index("player")
        pt2 = project_table2(P2, t, pr2, prm_all["era"], pr1["balls"]).set_index("player")
        pt0 = project_table2(P2, t, fixed_params(ks), prm_all["era"], pr1["balls"]).set_index(
            "player"
        )
        act, prev = Wt[Wt.sy == t].set_index("player"), Wt[Wt.sy == t - 1].set_index("player")
        py = ps[ps.sy == t - 1]
        for role in ("bat", "bowl"):
            pr = py[py.role == role].set_index("player")
            m = [
                x
                for x in act.index[act[f"{role}_balls"] >= minb]
                if x in prev.index and prev.loc[x, f"{role}_balls"] > 0
            ]
            o = out[role]
            o["a"].append(act.loc[m, f"{role}_war"].values)
            o["pwar"].append(pt1.loc[m, f"{role}_pwar"].values)
            o["comp"].append(pt2.loc[m, f"{role}_pwar"].values)
            o["comp0"].append(pt0.loc[m, f"{role}_pwar"].values)
            o["ctrl"].append(pt2.loc[m, f"{role}_cwar"].values)
            o["ctrl0"].append(pt0.loc[m, f"{role}_cwar"].values)
            o["last"].append(prev.loc[m, f"{role}_war"].values)
            o["lastraw"].append((pr.loc[m, "runs"] if role == "bat" else pr.loc[m, "wkts"]).values)
            o["year"].append(np.full(len(m), t))
            o["rate_real"].append(
                (act.loc[m, f"{role}_ra"] / act.loc[m, f"{role}_balls"] * 100).values
            )
            o["n"].append(act.loc[m, f"{role}_balls"].values)
            # rate-level losses on all players with 60+ IPL balls (ball-weighted RMSE of runs added per ball), as in war.loss
            e1, w1 = W._loss_terms(P1, role, [t], pr1)
            e2, w2 = _target_loss(P2, role, [t], pr2, ks)
            for nm, (e, w) in (("pwar", (e1, w1)), ("comp", (e2, w2))):
                d = out["rate"][role].setdefault(nm, [0.0, 0.0])
                d[0] += e.sum()
                d[1] += w.sum()
    for role in ("bat", "bowl"):
        for k in list(out[role]):
            out[role][k] = np.concatenate(out[role][k])
    out["fits"] = fits
    return out


def _r(x, y):
    return float(np.corrcoef(x, y)[0, 1])


def summarise(h: dict, boot=2000, seed=5, base="pwar") -> pd.DataFrame:
    """Per role and method: n, r, Spearman, MAE (wins), calibration slope of realised on predicted WAR; plus the bootstrap (over
    player-seasons) 95% range of r(method) - r(base) and MAE(method) - MAE(base)."""
    rng = np.random.default_rng(seed)
    rows = []
    for role in ("bat", "bowl"):
        o = h[role]
        a, n = o["a"], len(o["a"])
        idx = [rng.integers(0, n, n) for _ in range(boot)]
        for m in ("pwar", "comp", "comp0", "ctrl", "ctrl0", "last", "zero"):
            p = np.zeros(n) if m == "zero" else o[m]
            r = _r(p, a) if p.std() > 0 else 0.0
            d_r = [(_r(p[i], a[i]) if p[i].std() > 0 else 0.0) - _r(o[base][i], a[i]) for i in idx]
            d_m = [np.abs(a[i] - p[i]).mean() - np.abs(a[i] - o[base][i]).mean() for i in idx]
            rows.append(
                dict(
                    role=role,
                    method=m,
                    n=n,
                    r=r,
                    rho=float(pd.Series(p).rank().corr(pd.Series(a).rank()))
                    if p.std() > 0
                    else 0.0,
                    mae=float(np.abs(a - p).mean()),
                    slope=float(np.polyfit(p, a, 1)[0]) if p.std() > 0 else 0.0,
                    d_r=r - _r(o[base], a),
                    d_r_lo=float(np.percentile(d_r, 2.5)),
                    d_r_hi=float(np.percentile(d_r, 97.5)),
                    d_mae=float(np.abs(a - p).mean() - np.abs(a - o[base]).mean()),
                    d_mae_lo=float(np.percentile(d_m, 2.5)),
                    d_mae_hi=float(np.percentile(d_m, 97.5)),
                )
            )
    return pd.DataFrame(rows)


def component_holdout(
    rows, tab, sig, prm_by_year: dict, targets=(2024, 2025, 2026), minb=100
) -> pd.DataFrame:
    """Does each part repeat? Per role and part: r between the projection of the part (per ball, data before t) and the part realised
    in t, against last season's value of the same part, players with >= minb IPL balls in t and in t-1. Pooled over targets."""
    P2 = Panel2(tab)
    res = {}
    for t in targets:
        prm = prm_by_year[t]
        for role in ("bat", "bowl"):
            parts, _ = project_parts(P2, role, t, prm, prm["k"])
            n_t, n_p = P2.g("I", role, "balls", t), P2.g("I", role, "balls", t - 1)
            m = (n_t >= minb) & (n_p >= minb)
            for name in ["B"] + CLS[role] + ["R"]:
                col = name if name in ("B", "R") else f"s_{name}"
                real = (P2.g("I", role, col, t) / np.where(n_t > 0, n_t, 1))[m]
                last = (P2.g("I", role, col, t - 1) / np.where(n_p > 0, n_p, 1))[m]
                res.setdefault((role, name), []).append((parts[name][m], real, last))
    out = []
    for (role, name), v in res.items():
        pr, re, la = (np.concatenate([x[i] for x in v]) for i in range(3))
        out.append(
            dict(
                role=role,
                part=name,
                n=len(re),
                r_proj=_r(pr, re),
                r_last=_r(la, re),
                sd_real_per100=float(re.std() * 100),
            )
        )
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- errors in variables: refit the team slope with shrunk values
def beta_check(rows, prm_all, tab, sig, targets=(2024, 2025, 2026), db_path=None) -> pd.DataFrame:
    """Refit trade.fit_beta (logistic slope of the match result on the difference of the two XIs' summed value) when the player value
    is (a) trade's recent value (4/3/2/1 of past WAR, unshrunk), (b) current pWAR, (c) component pWAR, (d) controllable WAR; value of
    season t from data before t only. Reports beta, its 10-90 range, the same per one SD of the XI difference, and the leave-one-season-out
    log loss (0.693 = coin flip). trade.prior_values is swapped in memory only."""
    from . import trade as T

    P1, P2 = W._panel(rows), Panel2(tab)
    vals = {"pwar": {}, "comp": {}, "ctrl": {}}
    for t in targets:
        pr1 = W.fit_for(P1, t)
        pr2 = fit_components(P2, t, tab=tab, sig=sig)
        a = W.project_table(P1, t, pr1, prm_all["era"]).set_index("player").pwar
        b = project_table2(P2, t, pr2, prm_all["era"], pr1["balls"]).set_index("player")
        vals["pwar"][t], vals["comp"][t], vals["ctrl"][t] = a, b.pwar, b.cwar
    orig, out = T.prior_values, []
    try:
        for name in ("recent (trade tool)", "pwar", "comp", "ctrl"):
            if name != "recent (trade tool)":
                T.prior_values = lambda m, season, prm, name=name: vals[name][int(season)]
            else:
                T.prior_values = orig
            d = T.build_beta_matches(db_path)
            f = T.fit_beta(d)
            sd = float((d.x1 - d.x2).std())
            ll = []
            for t in targets:
                tr, te = d[d.sy != t], d[d.sy == t]
                b = T.fit_beta(tr, boot=1)["beta"]
                p = 1 / (1 + np.exp(-b * (te.x1 - te.x2)))
                ll.append(-(te.team1_won * np.log(p) + (1 - te.team1_won) * np.log(1 - p)).sum())
            out.append(
                dict(
                    value=name,
                    n=f["n"],
                    beta=f["beta"],
                    lo=f["lo"],
                    hi=f["hi"],
                    p_positive=f["p_positive"],
                    sd_xi_diff=sd,
                    beta_per_sd=f["beta"] * sd,
                    cv_logloss=float(sum(ll) / len(d)),
                )
            )
    finally:
        T.prior_values = orig
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- tables and outputs
def stability_tables() -> dict:
    """{'ipl2023': IPL 2023+ table, 'men_t20': all men's T20 leagues + T20I table}; n50 by alternate matches (main) and alternate balls."""
    fr = all_frames()
    out = {}
    for key, sel, ns in (
        (
            "ipl2023",
            lambda d: d[(d.comp == "ipl") & (d.sy >= W.ERA_IPL)],
            [100, 150, 200, 300, 400, 600, 800],
        ),
        ("men_t20", lambda d: d, [100, 200, 300, 500, 800, 1200, 1600, 2400, 3200]),
    ):
        parts = []
        for role in ("bat", "bowl"):
            d = sel(fr[role])
            t = stability(d, role, ns, "match")
            t["n50_ball_split"] = stability(d, role, ns, "ball", boot=1)["n50"].values
            parts.append(t.assign(role=role))
        out[key] = pd.concat(parts, ignore_index=True)
    return out


def add_controllable_csv(season: int = 2027) -> pd.DataFrame:
    """Add column `controllable_war` (+ `controllable_bat`, `controllable_bowl`) to models/data/pwar_ipl_<season>.csv. Untuned component
    projection (fixed_params), wicket part shrunk with CTRL_WK_MULT x its constant, R dropped. Other columns unchanged."""
    prm_all = W.load_params()
    tab, sig = tables()
    P2 = Panel2(tab)
    ks = k_table(season, tab, sig)
    pt = project_table2(
        P2, season, fixed_params(ks), prm_all["era"], prm_all["proj"]["balls"]
    ).set_index("player")
    f = W.DATA / f"pwar_ipl_{season}.csv"
    d = pd.read_csv(f).drop(
        columns=["controllable_war", "controllable_bat", "controllable_bowl"], errors="ignore"
    )
    d["controllable_war"] = d.cricsheet_name.map(pt.cwar).round(3)
    d["controllable_bat"] = d.cricsheet_name.map(pt.bat_cwar).round(3)
    d["controllable_bowl"] = d.cricsheet_name.map(pt.bowl_cwar).round(3)
    d.to_csv(f, index=False, lineterminator=chr(10))
    PARAMS.write_text(
        json.dumps(
            {"season": season, "k": ks, "fixed": fixed_params(ks), "ctrl_wk_mult": CTRL_WK_MULT},
            indent=1,
        )
    )
    return d


def main() -> None:
    import sys

    pd.set_option("display.width", 250, "display.max_columns", 40)
    what = sys.argv[1] if len(sys.argv) > 1 else "build"
    if what == "stability":
        for k, t in stability_tables().items():
            t.round(3).to_csv(W.DATA / f"stability_{k}.csv", index=False, lineterminator=chr(10))
            print(k)
            print(t.round(2).to_string())
    elif what == "validate":
        rows, _ = W.all_tables()
        tab, sig = tables()
        h = holdout(rows, W.load_params(), tab, sig)
        print(h["fits"])
        print(summarise(h).round(3).to_string())
        print(component_holdout(rows, tab, sig, h["fits"]).round(3).to_string())
    elif what == "beta":
        rows, _ = W.all_tables()
        tab, sig = tables()
        print(beta_check(rows, W.load_params(), tab, sig).round(4).to_string())
    else:
        print(add_controllable_csv().head(15).to_string())


if __name__ == "__main__":
    main()
