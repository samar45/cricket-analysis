"""Player worth: a short, prioritised metric set chosen by what the data says (docs/VALUE_worth.md).

Every candidate = (metric, phase, variant) per player-season, built from per-ball columns:
  metric   batting: sr, bnd (boundary %), six, dot, rot (1s/2s share of non-boundary balls), out, ra (runs added)
           bowling: econ, dot, bnd, wk, ra            (balls per boundary / six / dismissal / wicket = 1 / the rate)
  phase    all | powerplay | middle | death
  variant  abs | rel_match (minus everyone else in the same match and phase, both sides) | rel_team (minus same-innings
           teammates) | vs_pace / vs_spin / finer bowling types (batters), vs_lhb / vs_rhb (bowlers; types only from the
           reviewed list player_overrides.csv)
Each is a mean of a per-ball value x over the player's rows, so reliability has one definition: k = balls for reliability 0.5
(method of moments), shrunk value = (n*mean + k*league_mean) / (n + k)  (empirical Bayes).

CLI:  python -m cricket_analytics.models.worth select [--competition ipl --season-from 2023 --check bbl psl]
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from ..db import query
from ..sql.attributes import attributes_cte
from ..sql.filters import Filters
from ..sql.fragments import PHASES
from .run_expectancy import BALL_COLS, USABLE, batting_credit, bowling_credit, load, ra_state

DATA = Path(__file__).parent / "data"
SELECTED = DATA / "worth_selected.csv"
RETIRED = ["retired hurt", "retired not out"]
NOT_BOWLER = ["run out", "retired hurt", "retired out", "retired not out", "obstructing the field", "hit the ball twice"]
MIN_N = {"all": 100}  # per-candidate floor on the player-season's rows; 30 for a phase / type slice
MIN_N_SLICE = 30
PANEL_VARIANTS = ("abs", "vs_pace", "vs_spin", "vs_lhb", "vs_rhb")  # fine bowling-type slices and match-relative variants are ranked, not paneled
MIN_REL, MIN_RELEVANCE = 0.15, 0.25  # floors on pooled reliability and on |r with WPA| for a metric to be kept at all
MIN_PS, MIN_PAIRS = 100, 80  # a candidate needs this many player-seasons / season pairs in the home league to be eligible
R_REDUNDANT = 0.8  # |r| above this with an already kept metric = same cluster

# metric -> (mask, direction): direction +1 = higher is better for the player
BAT_METRICS = {"sr": 1, "bnd": 1, "six": 1, "dot": -1, "rot": 1, "out": -1, "ra": 1}
BOWL_METRICS = {"econ": -1, "dot": 1, "bnd": -1, "wk": 1, "ra": 1}
METRICS = {"bat": BAT_METRICS, "bowl": BOWL_METRICS}
SHOW = {  # id -> (label, unit scale shown to the reader)
    ("bat", "sr"): ("strike rate", 100.0), ("bat", "bnd"): ("balls per boundary", None), ("bat", "six"): ("balls per six", None),
    ("bat", "dot"): ("dot ball %", 100.0), ("bat", "rot"): ("rotation % (1s/2s of non-boundary balls)", 100.0),
    ("bat", "out"): ("balls per dismissal", None), ("bat", "ra"): ("runs added per 100 balls", 100.0),
    ("bowl", "econ"): ("economy", 6.0), ("bowl", "dot"): ("dot ball %", 100.0), ("bowl", "bnd"): ("balls per boundary conceded", None),
    ("bowl", "wk"): ("balls per wicket", None), ("bowl", "ra"): ("runs added per 24 balls", 24.0),
}  # scale None = reciprocal of the rate


# ---------------------------------------------------------------- per-ball data
def _ra(f: Filters) -> pd.DataFrame:
    """Runs-added credit per ball (batter and bowler side) keyed by match / innings / ball_seq."""
    st, sp = ra_state(f)
    rows = query(f"WITH d AS ({st}) SELECT d.ball_seq, {BALL_COLS} FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE}", sp)
    for c in ("wickets_before", "b", "score_before", "legal", "wk", "striker_out", "bowler_wk", "faced"):
        rows[c] = rows[c].astype("int64")
    a = load().annotate(rows)
    out = a[["match_id", "innings", "ball_seq"]].copy()
    out["match_id"] = out.match_id.astype(str)
    out["bat_ra"], out["bowl_ra"] = batting_credit(a).to_numpy(), bowling_credit(a).to_numpy()
    return out


def ball_frame(f: Filters) -> pd.DataFrame:
    """One row per ball (6-ball T20, trusted target and a result): WPA, runs added, season, phase, bowler / batter types."""
    from ..analysis.wpa import ball_wpa  # lazy: analysis imports models

    f = replace(f, player=None, team=None, opposition=None, phase=None)
    d = ball_wpa(f)
    if d.empty:
        return d
    d["match_id"] = d.match_id.astype(str)
    d = d.merge(_ra(f), how="left", on=["match_id", "innings", "ball_seq"])
    m = query("SELECT match_id, season FROM matches")
    d = d.merge(m.assign(match_id=m.match_id.astype(str)), on="match_id", how="left")
    first = d.groupby(["competition", "season"]).date.min().rank(method="dense").rename("srank").astype(int)
    d = d.merge(first.reset_index(), on=["competition", "season"])
    ph = np.where(d.over_num < 6, "powerplay", np.where(d.over_num < 15, "middle", "death"))
    d["phase"] = ph
    at = query(f"WITH {attributes_cte()} SELECT name, bowl_type, bat_hand FROM pa")
    d["bowl_type"] = d.bowler.map(dict(zip(at.name, at.bowl_type)))
    d["bat_hand"] = d.batter.map(dict(zip(at.name, at.bat_hand)))
    d["bowl_kind"] = np.where(d.bowl_type.isna(), None, np.where(d.bowl_type.fillna("").str.contains("spin|orthodox"), "spin", "pace"))
    return d


def role_frame(d: pd.DataFrame, role: str) -> pd.DataFrame:
    """Per-ball value columns for one role, indexed like d. Columns: player, x_<metric>, ok_<metric>, wpa, + keys."""
    keys = ["match_id", "innings", "competition", "srank", "phase", "bowl_type", "bowl_kind", "bat_hand", "date"]
    if role == "bat":
        b = d[d.wides == 0]
        o = pd.DataFrame({"player": b.batter, "team": b.batting_team}, index=b.index)
        r = b.runs_batter
        o["x_sr"], o["x_bnd"], o["x_six"] = r, r.isin([4, 6]), r == 6
        o["x_dot"] = (b.runs_total == 0) & (b.noballs == 0)
        o["x_rot"], o["ok_rot"] = r.isin([1, 2]), ~r.isin([4, 6])
        o["x_out"] = (b.player_out == b.batter) & ~b.wicket_type.isin(RETIRED)
        o["x_ra"] = b.bat_ra
        o["wpa"] = np.where(b.bat_who == b.batter, b.bat_wpa, 0.0)
    else:
        b = d
        o = pd.DataFrame({"player": b.bowler, "team": b.bowling_team}, index=b.index)
        o["x_econ"] = b.runs_batter + b.wides + b.noballs
        o["x_dot"] = (b.runs_total == 0) & (b.wides == 0) & (b.noballs == 0)
        o["x_bnd"] = b.runs_batter.isin([4, 6])
        o["x_wk"] = b.wicket_type.notna() & ~b.wicket_type.isin(NOT_BOWLER)
        o["x_ra"] = b.bowl_ra
        o["wpa"] = b.bowl_wpa
    for k in METRICS[role]:
        o[f"x_{k}"] = o[f"x_{k}"].astype(float)
        o["ok_" + k] = o[f"x_{k}"].notna() & (o["ok_rot"] if k == "rot" else True)
    return o.join(b[keys])


def _residual(o: pd.DataFrame, k: str, variant: str) -> pd.Series:
    """x minus the mean of the same metric over everyone else (rel_match: same match + phase; rel_team: + same innings and team)."""
    x, ok = o[f"x_{k}"].where(o["ok_" + k]), o["ok_" + k]
    g = ["match_id", "phase"] + (["innings", "team"] if variant == "rel_team" else [])
    gs, gn = x.groupby([o[c] for c in g]).transform("sum"), ok.groupby([o[c] for c in g]).transform("sum")
    p = ["player"] + g
    ps, pn = x.groupby([o[c] for c in p]).transform("sum"), ok.groupby([o[c] for c in p]).transform("sum")
    other_n = gn - pn
    return (x - (gs - ps) / other_n.where(other_n > 0)).where(ok)


def candidates(role: str) -> list[tuple]:
    """(metric, phase, variant) for every candidate of a role."""
    out = [(k, p, v) for k in METRICS[role] for p in ("all", *PHASES) for v in ("abs", "rel_match", "rel_team")]
    kinds = ("vs_pace", "vs_spin") if role == "bat" else ("vs_lhb", "vs_rhb")
    out += [(k, "all", v) for k in METRICS[role] for v in kinds]
    if role == "bat":  # finer bowling types, for the headline rates only
        from ..sql.attributes import BOWL_TYPES

        out += [(k, "all", "vs_" + t) for k in ("sr", "bnd", "out") for t in BOWL_TYPES]
    return out


def _slice(o: pd.DataFrame, variant: str) -> pd.Series:
    if variant.startswith("vs_"):
        t = variant[3:]
        return {"pace": o.bowl_kind == "pace", "spin": o.bowl_kind == "spin", "lhb": o.bat_hand == "left", "rhb": o.bat_hand == "right"}.get(t, o.bowl_type == t)
    return pd.Series(True, index=o.index)


def cells(o: pd.DataFrame, k: str, variant: str) -> pd.DataFrame:
    """Per (player, competition, season rank, phase): n, sum x, sum x^2, sum WPA over the rows of this candidate."""
    x = _residual(o, k, variant) if variant.startswith("rel_") else o[f"x_{k}"].where(o["ok_" + k])
    ok = x.notna() & _slice(o, variant)
    t = pd.DataFrame({"x": x[ok], "w": o.wpa[ok]}).join(o.loc[ok, ["player", "competition", "srank", "phase"]])
    t["x2"] = t.x**2
    return t.groupby(["player", "competition", "srank", "phase"]).agg(n=("x", "size"), s1=("x", "sum"), s2=("x2", "sum"), w=("w", "sum")).reset_index()


def to_phase(c: pd.DataFrame, phase: str) -> pd.DataFrame:
    c = c if phase == "all" else c[c.phase == phase]
    return c.groupby(["player", "competition", "srank"])[["n", "s1", "s2", "w"]].sum().reset_index()


def fit_k(c: pd.DataFrame) -> tuple[float, float]:
    """(k, league mean) by method of moments from player-season cells (columns n, s1, s2): k = within-var / between-var."""
    n, s1 = c.n.to_numpy(float), c.s1.to_numpy(float)
    mu = s1.sum() / n.sum()
    within = (c.s2.sum() - (s1**2 / n).sum()) / max(n.sum() - len(c), 1)
    m = s1 / n
    between = ((n * (m - mu) ** 2).sum() - (len(c) - 1) * within) / (n.sum() - (n**2).sum() / n.sum())
    return (within / between if between > 1e-12 and within > 0 else float("inf")), mu


def shrink(n, s1, k: float, mu: float):
    return (s1 + k * mu) / (n + k)


def _r(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    return float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 8 and a[ok].std() > 0 and b[ok].std() > 0 else float("nan")


def evaluate(role: str, d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Score every candidate. Returns (table, {id: player-season Series of shrunk value}) for the redundancy step."""
    o = role_frame(d, role)
    rows, vals = [], {}
    ytab = o.groupby(["player", "competition", "srank", "phase"]).agg(n=("wpa", "size"), w=("wpa", "sum")).reset_index()
    cache: dict = {}
    for k, ph, v in candidates(role):
        ck = (k, v)
        if ck not in cache:
            cache[ck] = cells(o, k, v)
        c = to_phase(cache[ck], ph)
        c = c[c.n >= (MIN_N.get(ph, MIN_N_SLICE) if not v.startswith("vs_") else MIN_N_SLICE)]
        cid = f"{k}|{ph}|{v}"
        if len(c) < 40:
            continue
        kk, mu = fit_k(c)
        y = to_phase(ytab.assign(s1=ytab.w, s2=0.0), ph).set_index(["player", "competition", "srank"])
        c = c.set_index(["player", "competition", "srank"])
        yw = (y.w / y.n)
        sh = shrink(c.n, c.s1, kk, mu) if np.isfinite(kk) else pd.Series(mu, index=c.index)
        raw = c.s1 / c.n
        s_next = raw.copy()
        s_next.index = pd.MultiIndex.from_arrays([c.index.get_level_values(0), c.index.get_level_values(1), c.index.get_level_values(2) - 1])
        pairs = raw.rename("t").to_frame().join(s_next.rename("t1"), how="inner")  # season t and t+1 of the same player
        nx = pairs.index.to_frame(index=False)
        wnext = yw.reindex(pd.MultiIndex.from_arrays([nx.iloc[:, 0], nx.iloc[:, 1], nx.iloc[:, 2] + 1]))
        r_wpa = _r(sh, yw.reindex(sh.index))
        ntyp = float(c.n.median())
        rel = ntyp / (ntyp + kk) if np.isfinite(kk) else 0.0
        rows.append(dict(id=cid, role=role, metric=k, phase=ph, variant=v, n_ps=len(c), n_median=ntyp, k=kk, r_s2s=_r(pairs.t, pairs.t1),
                         n_pairs=len(pairs), rel_typ=rel, r_wpa=r_wpa, r_next_wpa=_r(sh.reindex(pairs.index), wnext.to_numpy()),
                         direction=METRICS[role][k], score=rel * abs(r_wpa) if r_wpa == r_wpa else 0.0))
        vals[cid] = sh
    t = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    return t, vals


# ---------------------------------------------------------------- the module's engine
def panel(role: str) -> pd.DataFrame:
    """The kept metrics of a role (rows of worth_selected.csv with kept = True), best score first."""
    t = pd.read_csv(SELECTED)
    return t[(t.role == role) & t.kept].reset_index(drop=True)


def _display(role: str, metric: str, rate: pd.Series, ratio: float) -> pd.Series:
    label, scale = SHOW[(role, metric)]
    if scale is None:
        return 1.0 / rate.where(rate > 0)
    return rate * scale * (ratio if metric == "econ" else 1.0)  # bowling rows include wides: econ is per legal ball


def _floor(phase: str, variant: str) -> int:
    return MIN_N_SLICE if variant.startswith("vs_") else MIN_N.get(phase, MIN_N_SLICE)


def profile(d: pd.DataFrame, role: str, min_balls: int | None = None) -> pd.DataFrame:
    """Long table, one row per (player, kept metric) over every player in the frame d (seasons pooled): n, raw rate, shrunk
    rate, display value, percentile among peers (100 = best, direction applied), k used, share of the value that is his own."""
    o = role_frame(d, role)
    legal = float(((d.wides == 0) & (d.noballs == 0)).sum())
    ratio = len(d) / max(legal, 1.0)
    out = []
    for r in panel(role).itertuples():
        ps = to_phase(cells(o, r.metric, r.variant), r.phase)
        ok = ps[ps.n >= _floor(r.phase, r.variant)]
        k, mu = fit_k(ok) if len(ok) >= 40 else (np.inf, np.nan)
        if not np.isfinite(k):  # too few player-seasons here (small league / one season): reuse the IPL 2023+ constant
            k, mu = float(r.k), ps.s1.sum() / ps.n.sum()
        g = ps.groupby("player")[["n", "s1"]].sum()
        g = g[g.n >= (min_balls or _floor(r.phase, r.variant))]
        if g.empty:
            continue
        g["raw"], g["rate"] = g.s1 / g.n, shrink(g.n, g.s1, k, mu)
        g["value"] = _display(role, r.metric, g.rate, ratio)
        pr = g.rate.rank(pct=True)
        g["pctile"] = ((pr if r.direction > 0 else 1 - pr + 1 / len(g)) * 100).round(0)
        g["own_share"] = g.n / (g.n + k)
        lab = SHOW[(role, r.metric)][0] + ("" if r.phase == "all" else f" ({r.phase})") + ("" if r.variant == "abs" else " " + r.variant.replace("vs_", "vs ").replace("lhb", "left-handers").replace("rhb", "right-handers"))
        out.append(g.reset_index().assign(id=r.id, metric=lab, phase=r.phase, variant=r.variant, k=round(k, 1)))
    return pd.concat(out, ignore_index=True)


def highlights(d: pd.DataFrame, role: str, min_balls: int = 12) -> pd.DataFrame:
    """Best single-match performances against the match itself: batting = runs above what everyone else in the same match
    scored per ball in the same phases (both sides); bowling = runs saved vs the same yardstick (+ wickets)."""
    o = role_frame(d, role)
    k = "sr" if role == "bat" else "econ"
    o["res"], o["raw"] = _residual(o, k, "rel_match"), o[f"x_{k}"]
    o["wk"] = (o["x_wk"] if role == "bowl" else o["x_out"]).astype(int)
    g = o[o.res.notna()].groupby(["player", "match_id", "innings"]).agg(
        balls=("res", "size"), runs=("raw", "sum"), gap=("res", "sum"), wickets=("wk", "sum"), date=("date", "first"), team=("team", "first"))
    g = g[g.balls >= min_balls].reset_index()
    g["runs_vs_match"] = (g.gap if role == "bat" else -g.gap).round(1)
    opp = d.drop_duplicates(["match_id", "innings"]).set_index(["match_id", "innings"])["bowling_team" if role == "bat" else "batting_team"]
    g["opposition"] = opp.reindex(pd.MultiIndex.from_frame(g[["match_id", "innings"]])).to_numpy()
    g["runs"] = g.runs.astype(int)
    return g.sort_values("runs_vs_match", ascending=False).drop(columns="gap").reset_index(drop=True)


def ridge_check(role: str, d: pd.DataFrame, lam: float = 10.0) -> pd.DataFrame:
    """Incremental value of the kept metrics: ridge of player-season WPA per ball on the shrunk kept metrics (standardised)."""
    o = role_frame(d, role)
    y = o.groupby(["player", "competition", "srank"]).wpa.agg(["sum", "size"])
    cols = {}
    for r in panel(role).itertuples():
        ps = to_phase(cells(o, r.metric, r.variant), r.phase)
        ps = ps[ps.n >= _floor(r.phase, r.variant)]
        k, mu = fit_k(ps)
        cols[r.id] = shrink(ps.n, ps.s1, k, mu).set_axis(pd.MultiIndex.from_frame(ps[["player", "competition", "srank"]]))
    X = pd.DataFrame(cols).join((y["sum"] / y["size"]).rename("y"), how="inner").dropna()
    Z = (X - X.mean()) / X.std()
    A, t = Z.drop(columns="y"), Z.y
    b = np.linalg.solve(A.T @ A + lam * np.eye(A.shape[1]), A.T @ t)
    return pd.DataFrame({"id": A.columns, "std_beta": b, "n": len(Z), "r2": 1 - ((t - A @ b) ** 2).sum() / (t**2).sum()})


def pool(tabs: dict) -> pd.DataFrame:
    """Merge per-competition tables (first = the home league). pooled reliability = pair-weighted mean season-to-season r,
    pooled relevance = mean |r with WPA| weighted by player-seasons; score = reliability (floored at 0) x relevance."""
    home, *rest = tabs
    t = tabs[home].copy()
    for c, x in tabs.items():
        t = t.merge(x[["id", "r_s2s", "n_pairs", "r_wpa", "n_ps"]].add_suffix("_" + c).rename(columns={"id_" + c: "id"}), on="id", how="left") if c != home else t
    cs = list(tabs)
    def wmean(col, wcol, absval=False):
        num = sum((t[f"{col}_{c}"] if c != home else t[col]).abs().mul(t[f"{wcol}_{c}"] if c != home else t[wcol]).fillna(0) if absval else
                  (t[f"{col}_{c}"] if c != home else t[col]).mul(t[f"{wcol}_{c}"] if c != home else t[wcol]).fillna(0) for c in cs)
        den = sum(((t[f"{col}_{c}"] if c != home else t[col]).notna() * (t[f"{wcol}_{c}"] if c != home else t[wcol])).fillna(0) for c in cs)
        return num / den.where(den > 0)
    t["rel_pool"], t["relevance_pool"] = wmean("r_s2s", "n_pairs"), wmean("r_wpa", "n_ps", True)
    t["score_home"] = t.score
    t["score"] = t.rel_pool.clip(lower=0) * t.relevance_pool
    return t.dropna(subset=["score"]).sort_values("score", ascending=False).reset_index(drop=True)


def select(t: pd.DataFrame, vals: dict, top: int = 8) -> pd.DataFrame:
    """Season-level panel (match-relative variants are ranked but kept for the highlights, see the doc). Greedy: best score first; skip a candidate whose |r| with an already kept one exceeds R_REDUNDANT (same cluster)."""
    keep: list[str] = []
    why: dict = {}
    info = t.set_index("id")
    for cid in t[(t.n_ps >= MIN_PS) & (t.n_pairs >= MIN_PAIRS) & np.isfinite(t.k) & t.variant.isin(PANEL_VARIANTS) & (t.rel_pool >= MIN_REL) & (t.relevance_pool >= MIN_RELEVANCE)].id:
        if len(keep) >= top:
            break
        a = info.loc[cid]
        # one view per metric and variant: "all phases" and a single phase of the same metric are the same story
        if any((info.loc[q, "metric"], info.loc[q, "variant"]) == (a.metric, a.variant) and "all" in (info.loc[q, "phase"], a.phase) for q in keep):
            continue
        worst = max((abs(_r(vals[cid].reindex(vals[q].index), vals[q])) for q in keep), default=0.0, key=lambda z: 0 if z != z else z)
        if worst < R_REDUNDANT:
            keep.append(cid)
        else:
            why[cid] = worst
    t = t.copy()
    t["kept"] = t.id.isin(keep)
    t["max_r_kept"] = t.id.map(why)
    return t


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["select"])
    ap.add_argument("--competition", default="ipl")
    ap.add_argument("--season-from", type=int, default=2023)
    ap.add_argument("--check", nargs="*", default=["bbl", "psl"])
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--out", default=str(SELECTED))
    a = ap.parse_args()
    res = {r: {} for r in ("bat", "bowl")}
    vals = {}
    for comp, f in [(a.competition, Filters(competition=a.competition, season_from=a.season_from)),
                    *[(c, Filters(competition=c, last_n_years=4)) for c in a.check]]:
        d = ball_frame(f)
        for role in ("bat", "bowl"):
            t, v = evaluate(role, d)
            res[role][comp] = t
            if comp == a.competition:
                vals[role] = v
            print(comp, role, len(t), "candidates", flush=True)
    out = [select(pool(res[r]), vals[r], a.top) for r in ("bat", "bowl")]
    pd.concat(out).to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
