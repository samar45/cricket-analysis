"""Death-over execution score from Cricbuzz length tags (docs/VALUE_execution_drops.md).

Per bowler-season, overs 16-20, legal balls with a known length:
  execution = yorker / (yorker + full toss)   (a full toss is a missed yorker), shrunk to the league rate (empirical Bayes)
Also runs per ball on yorkers / full tosses / other lengths. Missing length is "not mentioned", never imputed.
"""

import numpy as np
import pandas as pd

from .commentary_features import OUT, _k, ball_features, fill, load_frame


def shrink(n, d, k: float, mu: float):
    """Beta-binomial posterior mean of a rate n/d with prior strength k balls at league rate mu."""
    return (n + k * mu) / (d + k)


def season_table(d: pd.DataFrame) -> pd.DataFrame:
    """One row per (bowler, year) from a ball_features frame: death balls, yorkers, full tosses, runs per ball by type."""
    g = d[(d.legal == 1) & (d.phase == "death")].copy()
    g["runs"] = g.runs_batter + g.wides + g.noballs
    g["kind"] = np.where(g.f_yorker == 1, "y", np.where(g.f_fulltoss == 1, "ft", np.where(g.known_len == 1, "oth", "unk")))
    t = g.groupby(["bowler", "year"]).agg(death_balls=("runs", "size"), death_runs=("runs", "sum"), known=("known_len", "sum"),
                                          y=("f_yorker", "sum"), ft=("f_fulltoss", "sum")).reset_index()
    for k in ("y", "ft", "oth"):
        s = g[g.kind == k].groupby(["bowler", "year"]).runs.agg(["sum", "size"])
        t = t.merge(s["sum"].rename(f"runs_{k}").reset_index(), how="left").merge(s["size"].rename(f"n_{k}").reset_index(), how="left")
    t = t.fillna({"runs_y": 0, "runs_ft": 0, "runs_oth": 0, "n_oth": 0})
    t["n_oth"] = t.n_oth.fillna(0)
    t["econ_death"] = t.death_runs / t.death_balls
    t["rpb_yorker"], t["rpb_fulltoss"], t["rpb_other"] = (t.runs_y / t.y).where(t.y > 0), (t.runs_ft / t.ft).where(t.ft > 0), (t.runs_oth / t.n_oth).where(t.n_oth > 0)
    return t


def add_execution(t: pd.DataFrame, k: float | None = None) -> pd.DataFrame:
    """Adds raw `exec_raw` (needs y+ft > 0), shrunk `execution`, and the league rate / k used."""
    t = t.copy()
    n, dd = t.y, t.y + t.ft
    mu = n.sum() / dd.sum()
    k = _k(n, dd) if k is None else k
    t["exec_raw"] = (n / dd).where(dd > 0)
    t["execution"] = shrink(n, dd, k, mu)
    t.attrs.update(mu=mu, k=k)
    return t


def pair_stats(t: pd.DataFrame, min_balls: int = 30) -> dict:
    """Repeatability and t -> t+1 prediction. Pairs need >= min_balls death balls in both seasons."""
    a = t.assign(year=t.year + 1)
    p = t.merge(a, on=["bowler", "year"], suffixes=("_next", "_prev"))
    p = p[(p.death_balls_prev >= min_balls) & (p.death_balls_next >= min_balls)].dropna(subset=["execution_prev"])
    out = {"n_pairs": len(p),
           "repeat_execution_shrunk": p.execution_prev.corr(p.execution_next),
           "repeat_economy": p.econ_death_prev.corr(p.econ_death_next)}
    r = p.dropna(subset=["exec_raw_prev", "exec_raw_next"])
    out["n_pairs_raw"], out["repeat_exec_raw"] = len(r), r.exec_raw_prev.corr(r.exec_raw_next)
    y = p.econ_death_next.to_numpy()
    X0 = np.column_stack([np.ones(len(p)), p.econ_death_prev])
    X1 = np.column_stack([X0, p.execution_prev - p.execution_prev.mean()])
    def fit(X):
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        res = y - X @ b
        r2 = 1 - res.var() / y.var()
        cov = res @ res / (len(y) - X.shape[1]) * np.linalg.inv(X.T @ X)
        return b, r2, np.sqrt(np.diag(cov))
    b0, r0, _ = fit(X0)
    b1, r1, se = fit(X1)
    out.update(r2_econ_only=r0, r2_with_exec=r1, r2_gain=r1 - r0, coef_exec=b1[2], se_exec=se[2], coef_econ=b1[1])
    # partial correlation of exec_t with econ_{t+1}, controlling for econ_t
    ex = p.execution_prev - np.polyval(np.polyfit(p.econ_death_prev, p.execution_prev, 1), p.econ_death_prev)
    ey = y - np.polyval(np.polyfit(p.econ_death_prev, y, 1), p.econ_death_prev)
    out["partial_corr"] = np.corrcoef(ex, ey)[0, 1]
    return out


def build(save: bool = True):
    d = ball_features(fill(load_frame(2017)))
    t = add_execution(season_table(d))
    if save:
        t.to_csv(f"{OUT}/death_execution.csv", index=False)
    return t


def ranking(t: pd.DataFrame, y0: int = 2024, y1: int = 2026, min_known: int = 20) -> pd.DataFrame:
    """Pooled y0..y1 shrunk execution per bowler (same league mu and k), needs >= min_known death balls with a tag."""
    p = t[t.year.between(y0, y1)].groupby("bowler")[["death_balls", "known", "y", "ft", "death_runs"]].sum()
    p = p[p.known >= min_known]
    mu, k = t.attrs["mu"], t.attrs["k"]
    p["execution"] = shrink(p.y, p.y + p.ft, k, mu)
    p["exec_raw"] = p.y / (p.y + p.ft)
    p["econ_death"] = p.death_runs / p.death_balls
    return p.sort_values("execution", ascending=False)
