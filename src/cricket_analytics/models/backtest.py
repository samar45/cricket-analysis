"""Generic backtest: "data up to season X" -> "IPL season X+1 truth".

A predictor is one function `fn(T, X, ctx) -> DataFrame` indexed by player with any of the columns
    bat, bowl            expected IPL runs added in the target season (batting / bowling)
    bat_rate, bowl_rate  expected runs added per ball
    total                only when bat/bowl cannot be split (default: bat + bowl)
`T` is the league-season table (see `tables`) already cut to seasons with sy <= X, so a predictor CANNOT see the target
season (sy = calendar year the season ended; an early-2026 league counts as 2026, so it is left out of an IPL 2026 forecast: a
slightly conservative cut). Auction predictors get the auction table for that year through ctx["auctions"] (the Dec X auction,
auction_year X+1, is before IPL X+1). A new predictor = one function with @predictor("name", scale).

scale "runs" means the numbers are runs added, so MAE against the truth is meaningful; "rank" means only the ordering is meaningful.
Run: `cricket backtest`  or  `python -m cricket_analytics.models.backtest`.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..reference import REFERENCE_DIR
from . import trade as TR
from . import war as W

EXTRA_LEAGUES = ["ilt20", "mlc", "bpl", "lpl", "smat"]
LEAGUE_W = dict(t20i=0.9, sa20=0.85, ilt20=0.8, bbl=0.8, psl=0.8, mlc=0.75, hundred=0.75, cpl=0.7,
                blast=0.7, bpl=0.65, lpl=0.6, smat=0.6)  # fmt: skip  (the lead's hand-set league strengths, 2026-11-07)
K_SHRINK = {"bat": 2669, "bowl": 876}  # balls of average evidence (runs-added-per-ball stability n50, VALUE_m2)
MIN_BALLS = 60
PREDICTORS: dict = {}


def predictor(name: str, scale: str = "rank"):
    def deco(fn):
        PREDICTORS[name] = (fn, scale)
        return fn

    return deco


@lru_cache(maxsize=1)
def tables() -> pd.DataFrame:
    """Every league-season-player-role-phase row (war.season_table by_phase, league-season averages centred to 0, match-condition adjusted at W.MATCH_W).
    Columns: comp, sy, season, team, player, role (bat/bowl), balls, runs, wkts, sc, wk, phase; runs added = sc + wk."""
    rows = [W.season_table(c, by_phase=True)[0] for c in W.LEAGUES + EXTRA_LEAGUES]
    T = W.centre(pd.concat([r for r in rows if len(r)], ignore_index=True))
    T = W.match_adjust_rows(T, W.MATCH_W)  # WAR v3: runs added adjusted 25% for match conditions
    T["ra"] = T.sc + T.wk
    return T


def player_year(T: pd.DataFrame, comps=None) -> pd.DataFrame:
    d = T if comps is None else T[T.comp.isin(comps)]
    return d.groupby(["player", "role", "sy"], as_index=False)[["balls", "ra"]].sum()


def _wide(g: pd.DataFrame, role: str, col: str) -> pd.Series:
    return g[g.role == role].groupby("player")[col].sum()


def _frame(bat: pd.DataFrame, bowl: pd.DataFrame, scale_rate: float = 1.0) -> pd.DataFrame:
    """From two frames (index player; balls, ra) to bat/bowl totals and rates."""
    out = pd.DataFrame(index=bat.index.union(bowl.index))
    for role, f in (("bat", bat), ("bowl", bowl)):
        out[role] = f.ra.reindex(out.index)
        out[f"{role}_rate"] = (f.ra / f.balls.where(f.balls > 0)).reindex(out.index)
    return out


# ------------------------------------------------------------------------------------------------ predictors
@predictor("zero", "runs")
def zero(T, X, ctx):
    ipl = player_year(T, ["ipl"])
    idx = ipl[ipl.sy == X].player.unique()
    return pd.DataFrame(0.0, index=idx, columns=["bat", "bowl", "bat_rate", "bowl_rate"])


def _ipl_window(T, X, years: int) -> pd.DataFrame:
    """IPL runs added per season (mean over the window; a missed season counts 0) and per ball, from the Impact era on."""
    lo = max(W.ERA_IPL, X - years + 1)
    p = player_year(T, ["ipl"])
    p = p[(p.sy >= lo) & (p.sy <= X)]
    n = X - lo + 1
    g = {r: p[p.role == r].groupby("player")[["balls", "ra"]].sum() for r in ("bat", "bowl")}
    out = _frame(g["bat"], g["bowl"])
    out[["bat", "bowl"]] = out[["bat", "bowl"]] / n
    return out


@predictor("last_ipl", "runs")
def last_ipl(T, X, ctx):
    return _ipl_window(T, X, 1)


@predictor("ipl3", "runs")
def ipl3(T, X, ctx):
    return _ipl_window(T, X, 3)


@predictor("recent_value")
def recent_value(T, X, ctx):
    """The trade tool's recent value (weights 4/3/2/1 back from the season before, WAR per season)."""
    s = TR.prior_values(pd.read_csv(TR.MATCH_CSV), X + 1, W.load_params())
    return pd.DataFrame({"total": s})


@predictor("pwar", "rank")
def pwar(T, X, ctx, version: str = W.DEFAULT_VERSION):
    """War.py's projection (fit on seasons before the target, men's leagues + T20I), as pWAR (wins, bat + bowl). v3 = replacement -6, no fielding
    (the truth is bat + bowl runs added, match-adjusted); pwar_v1 = the original replacement levels."""
    t = X + 1
    pt = _pwar_table(T, t, version).set_index("player")
    return pd.DataFrame({"bat": pt.bat_pwar, "bowl": pt.bowl_pwar, "bat_rate": pt.bat_rate / 100, "bowl_rate": pt.bowl_rate / 100})  # fmt: skip


@predictor("pwar_v1", "rank")
def pwar_v1(T, X, ctx):
    return pwar(T, X, ctx, "v1")


@predictor("pwar_runs", "runs")
def pwar_runs(T, X, ctx):
    """The same projection in runs added (rate x expected balls, no replacement level subtracted)."""
    pt = _pwar_table(T, X + 1).set_index("player")
    return pd.DataFrame({"bat": pt.bat_rate / 100 * pt.bat_balls, "bowl": pt.bowl_rate / 100 * pt.bowl_balls, "bat_rate": pt.bat_rate / 100, "bowl_rate": pt.bowl_rate / 100})  # fmt: skip


_PW: dict = {}


def _pwar_table(T, t, version: str = W.DEFAULT_VERSION):
    if (t, version) not in _PW:
        d = T[T.sy < t]
        ipl, other = d[d.comp == "ipl"], d[d.comp.isin([c for c in W.LEAGUES if c != "ipl"])]
        P = W.Panel(ipl, other, y1=t)
        prm_all = W.load_params(version)
        _PW[t, version] = W.project_table(P, t, W.fit_for(P, t), prm_all["era"])
    return _PW[t, version]


def _league_weighted(T, X, with_ipl: bool, years: int = 3) -> pd.DataFrame:
    d = T[(T.sy >= X - years + 1) & (T.sy <= X)]
    w = d.comp.map(LEAGUE_W)
    if with_ipl:
        w = w.where(d.comp != "ipl", 1.0)
    d = d.assign(w=w).dropna(subset=["w"])
    d["wra"] = d.ra * d.w
    cols = {}
    for r in ("bat", "bowl"):
        g = d[d.role == r].groupby("player")[["balls", "wra"]].sum()
        cols[f"{r}_rate"] = g.wra / (g.balls + K_SHRINK[r])
        cols[r] = cols[f"{r}_rate"] * 100
    return pd.DataFrame(cols)  # a dict of Series is aligned on the union of players (bowlers who never bat stay)


@predictor("lw_other")
def lw_other(T, X, ctx):
    """Lead's overseas method: other leagues only, hand-set league strengths, shrunk toward 0, last 3 years."""
    return _league_weighted(T, X, False)


@predictor("lw_all")
def lw_all(T, X, ctx):
    """The same with the IPL counted at weight 1."""
    return _league_weighted(T, X, True)


@predictor("price")
def price(T, X, ctx):
    a = ctx["auctions"]
    a = a[(a.auction_year == X + 1) & a.sold]
    return pd.DataFrame({"total": a.groupby("cricsheet_name").price_cr.max()})


# ------------------------------------------------------------------------------------------------ worth (player_worth metrics)
_BF: dict = {}
WORTH_FIT_FROM, WORTH_LAM, WORTH_FRAME_FROM = 2019, 10.0, 2016  # first target season used to fit weights; ridge penalty; first IPL season in the ball frame


def _worth_feats(Xc: int, role: str) -> pd.DataFrame:
    """Shrunk kept worth metrics per player from IPL balls up to calendar year Xc (wide: one column per kept metric)."""
    from ..sql.filters import Filters
    from . import worth

    if "d" not in _BF:
        _BF["d"] = worth.ball_frame(Filters(competition="ipl", season_from=WORTH_FRAME_FROM))
        _BF["yr"] = pd.to_datetime(_BF["d"].date).dt.year
    if (Xc, role) not in _BF:
        pr = worth.profile(_BF["d"][_BF["yr"] <= Xc], role)
        _BF[Xc, role] = pr.pivot_table(index="player", columns="id", values="rate")
    return _BF[Xc, role]


@predictor("worth", "runs")
def worth_pred(T, X, ctx):
    """Kept player_worth metrics (shrunk, IPL data up to X) -> ridge per role -> expected runs added per ball next season.
    Weights are fitted on target seasons WORTH_FIT_FROM..X only (features cut at s-1, truth = T season s, 60+ balls): no leakage.
    Expected runs = rate x the IPL balls per season of the last three seasons (a missed season counts 0)."""
    p = player_year(T, ["ipl"])
    out = {}
    for role in ("bat", "bowl"):
        xs, ys = [], []
        for s in range(WORTH_FIT_FROM, X + 1):
            f = _worth_feats(s - 1, role)
            y = p[(p.sy == s) & (p.role == role) & (p.balls >= MIN_BALLS)].set_index("player")
            y = (y.ra / y.balls).reindex(f.index).dropna()
            xs.append(f.loc[y.index])
            ys.append(y)
        Xf, y = pd.concat(xs), pd.concat(ys)
        mu, sd = Xf.mean(), Xf.std().replace(0, 1)
        Z = ((Xf - mu) / sd).fillna(0.0)
        yc = y - y.mean()
        b = np.linalg.solve(Z.T @ Z + WORTH_LAM * np.eye(Z.shape[1]), Z.T @ yc)
        f = _worth_feats(X, role)
        out[f"{role}_rate"] = pd.Series(((f[Xf.columns] - mu) / sd).fillna(0.0).to_numpy() @ b + y.mean(), index=f.index)
        q = p[(p.sy > X - 3) & (p.role == role)].groupby("player").balls.sum() / 3
        out[f"{role}_q"] = q.reindex(f.index).fillna(0.0)  # expected balls next season
        out[role] = out[f"{role}_rate"] * out[f"{role}_q"]
    return pd.DataFrame(out)


# ------------------------------------------------------------------------------------------------ worth2 (phase-aware, wickets back)
K_RUNS, WK_K = 150.0, (400.0, 3000.0)  # balls of average evidence for runs-per-ball (SR / economy) in a phase cell; clamp for the fitted wicket k
_W2: dict = {}


def _wk_k(c: pd.DataFrame) -> float:
    """Wicket k by method of moments on player-season-phase cells (balls n, wickets w; within-variance = binomial p(1-p))."""
    n, w = c.balls.to_numpy(float), c.wkts.to_numpy(float)
    p = w.sum() / n.sum()
    m = w / n
    between = ((n * (m - p) ** 2).sum() - (len(c) - 1) * p * (1 - p)) / (n.sum() - (n**2).sum() / n.sum())
    return float(np.clip(p * (1 - p) / between, *WK_K)) if between > 1e-12 else WK_K[1]


def _worth2_feats(T: pd.DataFrame, Xc: int, role: str) -> pd.DataFrame:
    """Per player from IPL rows up to year Xc: three features (runs per ball = SR / economy, wicket rate, runs added per ball), each a
    mean over the phases of the shrunk phase rate (minus the league rate in that phase) weighted by the player's OWN share of balls in that phase (expected usage)."""
    if (Xc, role) in _W2:
        return _W2[Xc, role]
    d = T[(T.comp == "ipl") & (T.role == role) & (T.sy <= Xc) & (T.sy >= WORTH_FRAME_FROM)]
    ps = d.groupby(["player", "sy", "phase"], as_index=False)[["balls", "runs", "wkts", "ra"]].sum()
    ps = ps[ps.balls > 0]
    pp = ps.groupby(["player", "phase"])[["balls", "runs", "wkts", "ra"]].sum().reset_index()
    share = pp.balls / pp.groupby("player").balls.transform("sum")
    ks = {"runs": K_RUNS, "ra": K_SHRINK[role] / 3}
    out = pd.DataFrame(index=pp.player.unique())
    for col, name in (("runs", "rr"), ("wkts", "wk"), ("ra", "ra")):
        v = pd.Series(0.0, index=out.index)
        for ph, g in pp.groupby("phase"):
            k = _wk_k(ps[ps.phase == ph]) if col == "wkts" else ks[col]
            mu = g[col].sum() / g.balls.sum()
            sh = (g[col] + k * mu) / (g.balls + k) - mu  # relative to the league rate IN THAT PHASE: a death bowler is not penalised for death scoring
            v = v.add((sh * share[g.index]).set_axis(g.player.values), fill_value=0.0)
        out[name] = v
    _W2[Xc, role] = out
    return out


@predictor("worth2", "runs")
def worth2_pred(T, X, ctx):
    """worth v2: phase-weighted shrunk features (_worth2_feats) -> ridge per role -> expected runs added per ball next season, fitted on
    target seasons WORTH_FIT_FROM..X only, exactly like `worth`. Same expected balls (last three seasons)."""
    p = player_year(T, ["ipl"])
    out = {}
    for role in ("bat", "bowl"):
        xs, ys = [], []
        for s in range(WORTH_FIT_FROM, X + 1):
            f = _worth2_feats(T, s - 1, role)
            y = p[(p.sy == s) & (p.role == role) & (p.balls >= MIN_BALLS)].set_index("player")
            y = (y.ra / y.balls).reindex(f.index).dropna()
            xs.append(f.loc[y.index])
            ys.append(y)
        Xf, y = pd.concat(xs), pd.concat(ys)
        mu, sd = Xf.mean(), Xf.std().replace(0, 1)
        Z = ((Xf - mu) / sd).fillna(0.0)
        b = np.linalg.solve(Z.T @ Z + WORTH_LAM * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
        f = _worth2_feats(T, X, role)
        out[f"{role}_rate"] = pd.Series(((f[Xf.columns] - mu) / sd).fillna(0.0).to_numpy() @ b + y.mean(), index=f.index)
        q = p[(p.sy > X - 3) & (p.role == role)].groupby("player").balls.sum() / 3
        out[f"{role}_q"] = q.reindex(f.index).fillna(0.0)
        out[role] = out[f"{role}_rate"] * out[f"{role}_q"]
    return pd.DataFrame(out)


# ------------------------------------------------------------------------------------------------ truth + pools
def auctions() -> pd.DataFrame:
    a = pd.read_csv(REFERENCE_DIR / "ipl_auctions.csv")
    for c in ("sold", "overseas"):
        a[c] = a[c].astype(str).str.lower().eq("true")
    return a


def truth_runs(T: pd.DataFrame, t: int) -> pd.DataFrame:
    """IPL season t: bat / bowl runs added, balls, rates, per player."""
    p = player_year(T, ["ipl"])
    p = p[p.sy == t]
    cols = {}
    for r in ("bat", "bowl"):
        g = p[p.role == r].set_index("player")
        cols[r], cols[f"{r}_balls"] = g.ra, g.balls
        cols[f"{r}_rate"] = g.ra / g.balls.where(g.balls > 0)
    out = pd.DataFrame(cols)
    out[["bat", "bowl", "bat_balls", "bowl_balls"]] = out[["bat", "bowl", "bat_balls", "bowl_balls"]].fillna(0.0)
    return out.join(opportunity(t))


def opportunity(t: int) -> pd.DataFrame:
    """IPL season t opportunity per player who appeared: share = matches played / the median team's matches that season (capped
    at 1). With `balls` (balls faced + bowled) these are the backtest `what` = share / balls. Players with no appearance are not
    in the truth, except sold players in the auction pools, who count 0."""
    apps = W.season_table("ipl")[1]
    apps = apps[apps.sy == t]
    tm = apps.groupby("team").matches.max().median()
    return pd.DataFrame({"share": (apps.groupby("player").matches.sum() / tm).clip(upper=1.0)})


def _stats(x, y, runs_scale: bool, boot: int = 300, seed: int = 1) -> dict:
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    out = dict(n=n, spearman=np.nan, lo=np.nan, hi=np.nan, pearson=np.nan, mae=np.nan)
    if n >= 3 and x.std() > 0:
        rx, ry = pd.Series(x).rank().values, pd.Series(y).rank().values
        out["spearman"] = float(np.corrcoef(rx, ry)[0, 1])
        out["pearson"] = float(np.corrcoef(x, y)[0, 1])
        if n >= 8:
            rng = np.random.default_rng(seed)
            bs = []
            for _ in range(boot):
                i = rng.integers(0, n, n)
                a, b = pd.Series(x[i]).rank().values, pd.Series(y[i]).rank().values
                if a.std() > 0 and b.std() > 0:
                    bs.append(np.corrcoef(a, b)[0, 1])
            out["lo"], out["hi"] = (float(v) for v in np.percentile(bs, [5, 95]))
    if runs_scale and n:
        out["mae"] = float(np.abs(x - y).mean())
    return out


def _pairs(pred: pd.DataFrame, truth: pd.DataFrame, what: str, minb: int):
    """(x, y) arrays for one target: total / bat / bowl (runs) or bat_rate / bowl_rate."""
    role = what.split("_")[0]
    if what in ("share", "balls"):
        truth = truth.assign(balls=truth.bat_balls + truth.bowl_balls)
        pl = truth.index[truth.share.notna()]
        px = pred[what] if what in pred else pd.Series(dtype=float)
        y = truth[what]
    elif what == "total":
        pl = truth.index[(truth.bat_balls >= minb) | (truth.bowl_balls >= minb)]
        px = pred["total"] if "total" in pred else pred[["bat", "bowl"]].sum(axis=1, min_count=1)
        y = truth.bat + truth.bowl
    else:
        pl = truth.index[truth[f"{role}_balls"] >= minb]
        px = pred[what] if what in pred else pd.Series(dtype=float)
        y = truth[what]
    pl = pl.intersection(px.dropna().index) if len(px) else pl[:0]
    return px.reindex(pl).values.astype(float), y.reindex(pl).values.astype(float), list(pl)


POOLS = ("all", "common", "auction", "auction_os")


def run(
    names=("zero", "last_ipl", "ipl3", "recent_value", "pwar", "pwar_runs", "lw_other", "lw_all", "price"),
    targets=(2024, 2025, 2026),
    pool: str = "all",
    whats=("total", "bat", "bowl", "bat_rate", "bowl_rate"),
    truth_fn=truth_runs,
    minb: int = MIN_BALLS,
    T: pd.DataFrame | None = None,
    auction_table: pd.DataFrame | None = None,
    extra: dict | None = None,
) -> pd.DataFrame:
    """Backtest every predictor on every target year (+ a 'pooled' row). Long table: target, what, predictor, n, spearman,
    lo/hi (5-95% bootstrap), pearson, mae. pool: all = every IPL player with truth; common = only players every predictor
    except `zero` has a number for; auction = bought at that year's auction; auction_os = overseas buys only.
    extra = {name: (fn, scale)} adds ad-hoc predictors."""
    T = tables() if T is None else T
    reg = {**PREDICTORS, **(extra or {})}
    A = auctions() if auction_table is None else auction_table
    rows, acc = [], {}
    for t in targets:
        X = t - 1
        truth = truth_fn(T, t)
        preds = {n: reg[n][0](T[T.sy <= X], X, dict(auctions=A)) for n in names}
        keep = None
        if pool == "common":
            sets = [set(p.dropna(how="all").index) for n, p in preds.items() if n != "zero"]
            keep = set.intersection(*sets) if sets else set()
        elif pool.startswith("auction"):
            a = A[(A.auction_year == t) & A.sold]
            keep = set(a[a.overseas].cricsheet_name if pool == "auction_os" else a.cricsheet_name)
        for n in names:
            for what in whats:
                x, y, pl = _pairs(preds[n], truth, what, minb)
                if keep is not None and what in ("share", "balls") and pool.startswith("auction") and what in preds[n]:
                    pv = preds[n][what].dropna()  # sold but never played: truth 0
                    miss = [p for p in keep if p not in set(pl) and p in pv.index]
                    x, y, pl = np.append(x, pv.loc[miss].values), np.append(y, np.zeros(len(miss))), pl + miss
                if keep is not None:
                    m = np.array([p in keep for p in pl], dtype=bool)
                    x, y = x[m], y[m]
                rows.append(dict(target=t, what=what, predictor=n, **_stats(x, y, reg[n][1] == "runs")))
                acc.setdefault((what, n), ([], []))
                acc[what, n][0].append(x)
                acc[what, n][1].append(y)
    for (what, n), (xs, ys) in acc.items():
        x, y = np.concatenate(xs), np.concatenate(ys)
        rows.append(dict(target="pooled", what=what, predictor=n, **_stats(x, y, reg[n][1] == "runs")))
    out = pd.DataFrame(rows)
    return out.assign(pool=pool)


def table(res: pd.DataFrame, what: str = "total") -> pd.DataFrame:
    """Wide readable view: one row per predictor, columns per target year: 'rho (n)'."""
    d = res[res.what == what]
    f = lambda r: "-" if np.isnan(r.spearman) else f"{r.spearman:+.2f} ({int(r.n)})"  # noqa: E731
    d = d.assign(cell=d.apply(f, axis=1))
    w = d.pivot(index="predictor", columns="target", values="cell")
    order = [n for n in PREDICTORS if n in w.index]
    return w.reindex(order + [n for n in w.index if n not in order])


from . import availability, marcel, rapm, value_variants  # noqa: E402,F401  (registers ipl3_ph, ipl3_wpa, ipl3_grp, marcel*, share_*, balls_*, ropp_*)

DEFAULT = ("zero", "last_ipl", "ipl3", "recent_value", "pwar", "pwar_runs", "lw_other", "lw_all", "price")


def main(pool: str = "all", what: str = "total", targets=(2024, 2025, 2026), names=DEFAULT, minb: int = MIN_BALLS) -> str:
    """The text `cricket backtest` prints: rank correlation (n) per predictor and target year."""
    res = run(tuple(names), tuple(targets), pool, whats=(what,), minb=minb)
    return table(res, what).to_string()


if __name__ == "__main__":
    print(main())
