"""Wins Above Replacement (WAR) and projected WAR (pWAR) from Runs Added.

Per player, season, league: batting and bowling Runs Added (models/run_expectancy.py, shortened matches included), each split
into a scoring part (runs and balls used up) and a wicket part. WAR = (runs added - replacement rate x balls) / runs per win.
Replacement rate, runs per win, and the projection settings are fitted and kept in models/data/war_params.json.

Rebuild:  python -m cricket_analytics.models.war            (fit + write pwar CSV)
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ..db import query
from ..sql.filters import Filters
from ..sql.fragments import phase_sql
from .run_expectancy import BALL_COLS, USABLE, load, ra_state

DATA = Path(__file__).parent / "data"
PARAMS = DATA / "war_params.json"
PARAMS_V2 = DATA / "war_params_v2.json"
PARAMS_V3 = DATA / "war_params_v3.json"
PARAMS_V4 = DATA / "war_params_v4.json"
DEFAULT_VERSION = "v3"  # v3 = batting + bowling only (no fielding), runs added adjusted 25% for match conditions (docs/VALUE_war_v3.md)
MATCH_W = 0.25  # share of the match-condition adjustment (models/match_adjust.py) applied to runs added in v3
# WAR v2 fielding (docs/VALUE_war_fix.md): share of a catch / stumping wicket value moved from the bowler to the fielder (a
# convention: no drop or chance data exists; the bowler's year-to-year repeatability rises with the share), and the share of a
# run-out's wicket value given to the fielders named on it (split equally; v1 charged the batter and credited nobody).
FIELD_SHARES = dict(catch=0.2, stump=0.2, runout=1.0)
# men's leagues + men's T20Is feed the projection (a league's own average is 0 by construction)
ERA_IPL = 2023  # Impact Player era: IPL numbers for the current game use these seasons only
LEAGUES = ["ipl", "bbl", "psl", "cpl", "sa20", "hundred", "blast", "t20i"]
SEASON_COLS = [
    "comp",
    "sy",
    "season",
    "team",
    "player",
    "role",
    "balls",
    "runs",
    "wkts",
    "sc",
    "wk",
]


def _int_cols(df):
    for c in (
        "wickets_before",
        "b",
        "score_before",
        "legal",
        "wk",
        "striker_out",
        "bowler_wk",
        "faced",
    ):
        df[c] = df[c].astype("int64")
    return df


def _fielding(a: pd.DataFrame, sh: dict, by_phase: bool):
    """(multiplier on the bowler's wicket credit, fielder rows) for WAR v2. A catch by a named fielder (not the bowler) and a
    stumping move share `catch` / `stump` of the wicket value from the bowler to the fielder; a run-out gives share `runout` of
    its value to the fielders named (equal split). Wicket value = -vf * wkt_part (positive)."""
    wv = -a.vf * a.wkt_part
    wt = a.wicket_type
    isc = (wt == "caught") & a.fielder.notna() & (a.bowler_wk == 1)
    iss = (wt == "stumped") & a.fielder.notna() & (a.bowler_wk == 1)
    isr = (wt == "run out") & (a.wk == 1)
    keep = 1.0 - np.where(isc, sh["catch"], 0.0) - np.where(iss, sh["stump"], 0.0)
    nf = a[["fielder", "fielder_2", "fielder_3"]].notna().sum(axis=1).clip(lower=1)
    parts = [(isc, "fielder", wv * sh["catch"], 1), (iss, "fielder", wv * sh["stump"], 1)] + [
        (isr & a[c].notna(), c, wv * sh["runout"] / nf, 0) for c in ("fielder", "fielder_2", "fielder_3")
    ]
    out = []
    for m, col, val, is_cs in parts:
        x = a[m]
        out.append(
            pd.DataFrame(
                dict(
                    **({"match_id": x.match_id} if "match_id" in x else {}),
                    sy=x.sy,
                    **({"phase": x.phase} if by_phase else {}),
                    season=x.season,
                    team=x.bowling_team,
                    player=x[col],
                    role="field",
                    balls=0,
                    runs=0,
                    wkts=is_cs,  # field rows: 1 = a catch / stumping (so catches can be counted), 0 = run-out
                    sc=val[m] if is_cs else 0.0,  # catch / stumping credit here, run-out credit in wk (sc + wk = credit)
                    wk=0.0 if is_cs else val[m],
                    comp=x.comp,
                )
            )
        )
    return keep, pd.concat(out)


def season_table(
    comp: str, db_path=None, by_phase: bool = False, fielding: dict | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player-season-team rows, appearances) for one competition key.

    Rows: comp, sy (calendar year the season ended), season (label), team, player, role (bat/bowl), balls (faced / legal
    bowled), runs (off the bat / conceded), sc (scoring part of runs added), wk (wicket part), with sc + wk = runs added.
    Appearances: comp, sy, team, player, matches (matches in which he batted, was non-striker, or bowled).
    by_phase=True adds a `phase` column (powerplay / middle / death) to the rows; summing over it gives the default table.
    fielding=FIELD_SHARES (WAR v2) moves part of each catch / stumping from the bowler to the fielder, gives run-outs to the
    fielders, and adds rows with role "field" (balls 0, wk = credit, team = fielding side). Default None = v1, unchanged."""
    f = Filters(competition=comp)
    st, sp = ra_state(f)
    sql = (
        f"WITH d AS ({st}) SELECT {BALL_COLS}, d.batting_team, d.bowling_team, d.non_striker, m.date, m.season"
        f"{', d.wicket_type, d.fielder, d.fielder_2, d.fielder_3' if fielding else ''}"
        f"{', ' + phase_sql() + ' AS phase' if by_phase else ''} "
        f"FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE}"
    )
    rows = _int_cols(query(sql, sp, db_path=db_path))
    if rows.empty:
        return pd.DataFrame(columns=SEASON_COLS), pd.DataFrame(
            columns=["comp", "sy", "team", "player", "matches"]
        )
    a = load().annotate(rows)
    sy = a.groupby("season").date.max().dt.year
    a["sy"] = a.season.map(sy).astype(int)
    key = ["comp", "sy", "season", "team", "player", "role"] + (["phase"] if by_phase else [])
    a["comp"] = comp
    keep, fld = _fielding(a, fielding, by_phase) if fielding else (1.0, None)
    s = (a.faced == 1) | (a.striker_out == 1)
    bs = a[s]
    bat_s = pd.DataFrame(
        dict(
            comp=comp,
            sy=bs.sy,
            **({'phase': bs.phase} if by_phase else {}),
            season=bs.season,
            team=bs.batting_team,
            player=bs.batter,
            role="bat",
            balls=bs.faced,
            runs=bs.runs_batter * bs.faced,
            wkts=0,
            sc=bs.runs_batter + bs.vf * bs.ball_part + bs.bat_k,
            wk=bs.vf * bs.wkt_part * bs.striker_out,
        )
    )
    ns = a[(a.wk == 1) & (a.striker_out == 0)]
    bat_n = pd.DataFrame(
        dict(
            comp=comp,
            sy=ns.sy,
            **({'phase': ns.phase} if by_phase else {}),
            season=ns.season,
            team=ns.batting_team,
            player=ns.player_out,
            role="bat",
            balls=0,
            runs=0,
            wkts=0,
            sc=0.0,
            wk=ns.vf * ns.wkt_part,
        )
    )
    bow = pd.DataFrame(
        dict(
            comp=comp,
            sy=a.sy,
            **({'phase': a.phase} if by_phase else {}),
            season=a.season,
            team=a.bowling_team,
            player=a.bowler,
            role="bowl",
            balls=a.legal,
            runs=a.conceded,
            wkts=a.bowler_wk,
            sc=-a.conceded - a.vf * a.ball_part + a.bowl_k,
            wk=-a.vf * a.wkt_part * a.bowler_wk * keep,
        )
    )
    out = (
        pd.concat([bat_s, bat_n, bow] + ([] if fld is None else [fld]))
        .groupby(key, as_index=False)[["balls", "runs", "wkts", "sc", "wk"]]
        .sum()
    )
    pres = pd.concat(
        [
            a[["match_id", "sy", "batting_team", "batter"]].set_axis(
                ["match_id", "sy", "team", "player"], axis=1
            ),
            a[["match_id", "sy", "batting_team", "non_striker"]].set_axis(
                ["match_id", "sy", "team", "player"], axis=1
            ),
            a[["match_id", "sy", "bowling_team", "bowler"]].set_axis(
                ["match_id", "sy", "team", "player"], axis=1
            ),
        ]
    ).drop_duplicates()
    app = (
        pres.groupby(["sy", "team", "player"], as_index=False)
        .size()
        .rename(columns={"size": "matches"})
    )
    app.insert(0, "comp", comp)
    return out[SEASON_COLS + (['phase'] if by_phase else [])], app


# --------------------------------------------------------------------------- tables
def centre(rows: pd.DataFrame) -> pd.DataFrame:
    """Make the league-season average player exactly 0 per ball (batting and bowling separately): the shipped offsets are fitted
    on first innings; chases, short matches and other leagues leave a small drift (up to 3 runs per 100 balls in T20Is).
    With fielding rows (WAR v2) the bowling side is centred together with its fielding credit, so the credit created by
    run-outs is not extra."""
    g = rows.groupby(["comp", "sy", "role"])
    tot = g.sc.transform("sum") + g.wk.transform("sum")
    if (rows.role == "field").any():
        fs = (rows.sc + rows.wk)[rows.role == "field"].groupby([rows.comp, rows.sy]).sum()
        add = pd.Series(list(zip(rows.comp, rows.sy)), index=rows.index).map(fs).fillna(0.0)
        tot = tot + np.where(rows.role == "bowl", add, 0.0)
    mu = tot / g.balls.transform("sum").replace(0, np.nan)
    out = rows.copy()
    out["sc"] = out.sc - (mu * out.balls).fillna(0.0)
    return out


def match_adjust_rows(rows: pd.DataFrame, w: float) -> pd.DataFrame:
    """WAR v3: add w x (match-condition adjustment) to the scoring part `sc` of centred rows (batting and bowling rows only).
    The adjustment per (season, team, player, role[, phase]) is ra_adj - ra from models/match_adjust.py (leave-one-player-out
    mean of the other players in the same match, phase and role; re-centred so the league-season average player stays 0).
    A league whose match rows cannot be built keeps its raw values."""
    from .match_adjust import adjusted, match_rows

    key = ["comp", "sy", "season", "team", "player", "role"] + (["phase"] if "phase" in rows else [])
    parts = []
    for comp, d in rows.groupby("comp", sort=False):
        try:
            r = adjusted(match_rows(comp), w)
        except Exception:  # ponytail: a league that fails to load keeps its raw values
            parts.append(d)
            continue
        g = r.assign(delta=r.ra_adj - r.ra).groupby(key, as_index=False).delta.sum()
        m = d.merge(g, on=key, how="left")
        parts.append(m.assign(sc=m.sc + m.delta.fillna(0.0)).drop(columns="delta"))
    return pd.concat(parts, ignore_index=True)


def all_tables(leagues: tuple = tuple(LEAGUES), fielding: dict | None = None, match_w: float = MATCH_W):
    """{comp: centred rows}, {comp: appearances}. About 15 s for all leagues (plus the match rows when match_w > 0).
    fielding=FIELD_SHARES adds WAR v2 field rows; match_w = share of the match-condition adjustment (v3 = MATCH_W, 0 = off)."""
    return _all_tables(tuple(leagues), tuple(sorted(fielding.items())) if fielding else None, float(match_w))


@lru_cache(maxsize=2)
def _all_tables(leagues: tuple, fielding: tuple | None, match_w: float):
    rows, apps = {}, {}
    for c in leagues:
        r, a = season_table(c, fielding=dict(fielding) if fielding else None)
        rows[c], apps[c] = r, a
    cen = centre(pd.concat(rows.values(), ignore_index=True))
    if match_w:
        cen = match_adjust_rows(cen, match_w)
    return {c: g for c, g in cen.groupby("comp")}, apps


def player_year(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.groupby(["role", "player", "sy"], as_index=False)[
        ["balls", "runs", "wkts", "sc", "wk"]
    ].sum()


class Panel:
    """Wide matrices (player x year) of balls / sc / wk for IPL (`I`) and every other league pooled (`O`)."""

    def __init__(self, ipl: pd.DataFrame, other: pd.DataFrame, y0=2008, y1=2027):
        self.years = list(range(y0, y1 + 1))
        ip, op = player_year(ipl), player_year(other)
        self.players = sorted(set(ip.player) | set(op.player))
        self.M, self._ev = {}, {}
        for tag, df in (("I", ip), ("O", op)):
            for role in ("bat", "bowl"):
                d = df[df.role == role]
                for col in ("balls", "runs", "wkts", "sc", "wk"):
                    x = (
                        d.pivot(index="player", columns="sy", values=col)
                        if len(d)
                        else pd.DataFrame()
                    )
                    self.M[tag, role, col] = x.reindex(
                        index=self.players, columns=self.years
                    ).fillna(0.0)

    def g(self, tag, role, col, y):
        return self.M[tag, role, col][y].values


LEARN_FROM = 2018  # first pseudo-target season for the shrinkage constants (they are noise-to-signal ratios, learned from all history up to t - 1)
KGRID = (200, 400, 800, 1600, 3000, 6000, 12000)
AGRID, SGRID = (0.0, 0.25, 0.5, 1.0), (0.5, 1.0)
WINDOW = 5


def ipl_from_for(P: Panel, t: int, ipl_from: int) -> int:
    """First IPL year whose evidence counts at full weight for target t. For t after `ipl_from` (the Impact Player era) only
    that era counts (owner's rule). For pseudo-targets up to ipl_from (used only to learn shrinkage constants) all IPL years count."""
    return ipl_from if t > ipl_from else P.years[0]


def evidence(P: Panel, role: str, col: str, t: int, a: float, s: float, ef: int, pre_w: float):
    """(sum of col, balls) over the WINDOW seasons before t: IPL years >= ef at weight 1, earlier IPL years at pre_w, other leagues at
    weight a (their rate multiplied by league-strength factor s)."""
    key = (role, col, t, a, s, ef, pre_w)
    if key not in P._ev:
        num, den = 0.0, 0.0
        for y in range(max(P.years[0], t - WINDOW), t):
            wy = 1.0 if y >= ef else pre_w
            num = num + wy * P.g("I", role, col, y) + a * s * P.g("O", role, col, y)
            den = den + wy * P.g("I", role, "balls", y) + a * P.g("O", role, "balls", y)
        P._ev[key] = (num, den)
    return P._ev[key]


def project_rate(
    P: Panel, role: str, t: int, prm: dict
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Projected (scoring, wicket) runs added per ball for season t from earlier seasons only, and the evidence balls.
    prm: {ipl_from, role: {a, s, pre_w, k: [k_scoring, k_wicket]}}."""
    q = prm[role]
    ef = ipl_from_for(P, t, prm["ipl_from"])
    nsc, den = evidence(P, role, "sc", t, q["a"], q["s"], ef, q["pre_w"])
    pw = q.get(
        "pre_w_wk", q["pre_w"]
    )  # the wicket part may lean on older IPL seasons more than the scoring part (tested, not used)
    nwk, dwk = evidence(P, role, "wk", t, q["a"], q["s"], ef, pw)
    return nsc / (den + q["k"][0]), nwk / (dwk + q["k"][1]), den


def _loss_terms(P: Panel, role: str, targets, prm: dict, minb=60):
    """Squared error of the projected rate (per ball) against the realised rate, one entry per player-season, with balls as weight."""
    err, wt = [], []
    for t in targets:
        n = P.g("I", role, "balls", t)
        sc, wk, den = project_rate(P, role, t, prm)
        m = (n >= minb) & (
            evidence(P, role, "sc", t, 1.0, 1.0, P.years[0], 1.0)[1] > 0
        )  # anybody with any earlier T20 balls
        y = (P.g("I", role, "sc", t) + P.g("I", role, "wk", t)) / np.where(n > 0, n, np.nan)
        err.append((((y - sc - wk) ** 2) * n)[m])
        wt.append(n[m])
    return np.concatenate(err), np.concatenate(wt)


def loss(P: Panel, role: str, targets, prm: dict, minb=60) -> float:
    """Ball-weighted RMSE (runs added per ball) of the projection over player-seasons with at least minb balls."""
    e, w = _loss_terms(P, role, targets, prm, minb)
    return float((e.sum() / w.sum()) ** 0.5)


def fit_proj_over(P: Panel, role: str, targets, a_grid, ipl_from: int = ERA_IPL, pre_w=0.0) -> dict:
    """Grid search of a (weight of other leagues), s (their strength) and the two shrinkage constants k on `targets`."""
    best = None
    for a in a_grid:
        for s in SGRID if a > 0 else (1.0,):
            for k1 in KGRID:
                for k2 in KGRID:
                    q = dict(a=a, s=s, pre_w=pre_w, k=[k1, k2])
                    v = loss(P, role, targets, {"ipl_from": ipl_from, role: q})
                    if best is None or v < best[0]:
                        best = (v, q)
    return best[1]


def fit_proj(P: Panel, role: str, targets, ipl_from: int = ERA_IPL, pre_w=0.0) -> dict:
    return fit_proj_over(P, role, targets, AGRID, ipl_from, pre_w)


# expected balls: OLS of balls in season t on [1, last season's balls, mean of the two seasons before], players with any IPL balls in those 3 seasons
def _prior_balls(P: Panel, role: str, t: int, ef: int) -> np.ndarray:
    return np.column_stack(
        [
            P.g("I", role, "balls", t - L)
            if (t - L >= ef and t - L >= P.years[0])
            else np.zeros(len(P.players))
            for L in (1, 2, 3)
        ]
    )


def fit_balls(P: Panel, role: str, targets, ipl_from: int) -> list:
    X, y = [], []
    for t in targets:
        b = _prior_balls(P, role, t, ipl_from_for(P, t, ipl_from))
        m = b.sum(1) > 0
        X.append(np.column_stack([np.ones(m.sum()), b[m, 0], b[m, 1:].mean(1)]))
        y.append(P.g("I", role, "balls", t)[m])
    coef, *_ = np.linalg.lstsq(np.vstack(X), np.concatenate(y), rcond=None)
    return coef.tolist()


def exp_balls(P: Panel, role: str, t: int, coef, ipl_from: int) -> np.ndarray:
    b = _prior_balls(P, role, t, ipl_from_for(P, t, ipl_from))
    e = coef[0] + coef[1] * b[:, 0] + coef[2] * b[:, 1:].mean(1)
    return np.where(b.sum(1) > 0, np.clip(e, 0, None), 0.0)


def fit_for(P: Panel, t: int, ipl_from=ERA_IPL) -> dict:
    """Projection settings for target season t using pseudo-targets LEARN_FROM .. t - 1 only."""
    tg = range(LEARN_FROM, t)
    prm = {"ipl_from": ipl_from, "balls": {}}
    for role in ("bat", "bowl"):
        prm[role] = fit_proj(P, role, tg, ipl_from)
        prm["balls"][role] = fit_balls(P, role, tg, ipl_from)
    return prm


# --------------------------------------------------------------------------- runs per win, replacement, WAR
IPL_PRE_LABEL, IPL_NOW_LABEL = "pre", "2023"


def era_key(sy) -> str:
    return IPL_NOW_LABEL if sy >= ERA_IPL else IPL_PRE_LABEL


def team_seasons(db_path=None) -> pd.DataFrame:
    """One row per IPL team-season: matches decided (no D/L, ties, no result), win share w, and rd = mean run margin per match
    with every innings scaled to 120 balls (cross-check only; the main runs-per-win uses team runs added instead)."""
    df = query(
        """SELECT m.match_id, year(m.date) yr, m.winner, d.innings, d.batting_team bt, SUM(d.runs_total) runs,
                  SUM(CASE WHEN d.wides = 0 AND d.noballs = 0 THEN 1 ELSE 0 END) lb
           FROM deliveries d JOIN matches m ON d.match_id = m.match_id
           WHERE m.competition = 'ipl' AND m.gender = 'male' AND d.innings <= 2 AND m.result IN ('runs', 'wickets')
             AND COALESCE(m.outcome_method, '') <> 'D/L' GROUP BY ALL""",
        db_path=db_path,
    )
    df["runs"] = df.runs * 120 / df.lb.clip(lower=1)
    p = df.pivot_table(
        index=["match_id", "yr", "winner"],
        columns="innings",
        values=["runs", "bt"],
        aggfunc="first",
    ).reset_index()
    p.columns = ["match_id", "yr", "winner", "bt1", "bt2", "r1", "r2"]
    a = pd.DataFrame(
        {"yr": p.yr, "team": p.bt1, "rd": p.r1 - p.r2, "win": (p.winner == p.bt1).astype(int)}
    )
    b = pd.DataFrame(
        {"yr": p.yr, "team": p.bt2, "rd": p.r2 - p.r1, "win": (p.winner == p.bt2).astype(int)}
    )
    return (
        pd.concat([a, b])
        .groupby(["yr", "team"], as_index=False)
        .agg(n=("win", "size"), rd=("rd", "mean"), w=("win", "mean"))
    )


def team_ra(ipl_rows: pd.DataFrame) -> pd.DataFrame:
    """Total runs added by everybody on a team in a season (batting + bowling, all players), keyed (yr, team)."""
    t = (
        ipl_rows.assign(ra=ipl_rows.sc + ipl_rows.wk)
        .groupby(["sy", "team"], as_index=False)
        .ra.sum()
    )
    return t.rename(columns={"sy": "yr"})


def runs_per_win(ts: pd.DataFrame, ra: pd.DataFrame, years) -> dict:
    """Runs per win = how many runs added (summed over a team's players) go with one extra win.
    Fit: wins above half = (win share - 0.5) x matches, regressed on the team's total runs added through the origin
    (it is a league of equals, so zero runs added = 0.5), weighted equally per team-season; rpw = 1 / slope.
    Bootstrap over team-seasons gives a 95% range. `cross` = the same with the mean run margin per match (x matches) instead of runs added."""
    s = ts[ts.yr.isin(list(years))].merge(ra, on=["yr", "team"])
    y = (s.w.values - 0.5) * s.n.values
    rng = np.random.default_rng(0)

    def fit(x):
        def sl(i):
            return (x[i] * y[i]).sum() / (x[i] ** 2).sum()

        bs = [sl(rng.integers(0, len(s), len(s))) for _ in range(1000)]
        return dict(
            rpw=float(1 / sl(np.arange(len(s)))),
            lo=float(1 / np.percentile(bs, 97.5)),
            hi=float(1 / np.percentile(bs, 2.5)),
            r2=float(np.corrcoef(x, y)[0, 1] ** 2),
        )

    out = fit(s.ra.values)
    out["team_seasons"] = int(len(s))
    out["cross_margin"] = fit(s.rd.values * s.n.values)
    return out


def rpw_from_win_prob() -> float:
    """Cross-check from the step-2 win-probability model: at the start of an IPL (2023+) chase, a side's win chance moves by
    d per run of target; 1 / d runs per +1.0 win share (so per win once summed over matches), read where the chance is 50%."""
    from . import win_prob as wp

    r = np.arange(120, 260)
    p = wp.chase_wp(r, 120, 0, "ipl_impact", 2025)
    i = int(np.argmin(np.abs(p - 0.5)))
    d = (p[i - 5] - p[i + 5]) / 10.0
    return float(1 / d)


def _usage_rank(r: pd.DataFrame, app: pd.DataFrame) -> pd.DataFrame:
    u = (
        r.groupby(["sy", "team", "player"], as_index=False)
        .balls.sum()
        .rename(columns={"balls": "b_all"})
    )
    a = app.merge(u, on=["sy", "team", "player"], how="left").fillna({"b_all": 0})
    a = a.sort_values(["sy", "team", "matches", "b_all"], ascending=[True, True, False, False])
    a["rk"] = a.groupby(["sy", "team"]).cumcount() + 1
    return a


def replacement(r: pd.DataFrame, app: pd.DataFrame, prior_years, cut=11, lag=1) -> dict:
    """Runs added per 100 balls (batting per ball faced, bowling per ball bowled) in the NEXT season of the players who were
    outside their team's top `cut` (by matches, then balls) in a year of `prior_years`. Using the next season (lag=1) keeps the
    group from being picked by the very results being measured, but only players who got another IPL season show up (flatters them);
    lag=0 uses the same season (includes players dropped for playing badly: too low). The truth lies between.
    Returns rate, balls, and a bootstrap SE."""
    a = _usage_rank(r, app)
    fr = a[a.rk > cut].groupby(["sy", "player"]).size().rename("f").reset_index()
    ps = player_year(r)
    out, rng = {}, np.random.default_rng(1)
    for role in ("bat", "bowl"):
        q = ps[ps.role == role].copy()
        q["sy"] -= lag
        z = q[q.sy.isin(list(prior_years))].merge(fr, on=["sy", "player"])
        ra, n = (z.sc + z.wk).values, z.balls.values
        bs = [
            ra[i].sum() / n[i].sum() * 100
            for i in (rng.integers(0, len(z), len(z)) for _ in range(300))
        ]
        out[role] = dict(
            per100=float(ra.sum() / n.sum() * 100),
            se=float(np.std(bs)),
            balls=int(n.sum()),
            players=int(len(z)),
        )
    return out


def load_params(version: str = DEFAULT_VERSION) -> dict:
    """v3 (default) = war_params_v3.json (bat + bowl only, match_w 0.25, replacement -6); v2 = war_params_v2.json (fielding
    shares, replacement -6); v1 = the original war_params.json. See docs/VALUE_war_v3.md and docs/VALUE_war_fix.md."""
    return json.loads({"v1": PARAMS, "v2": PARAMS_V2, "v3": PARAMS_V3, "v4": PARAMS_V4}[version].read_text())


REF = Path(__file__).parent.parent / "reference"
ROLE_CUT = 0.2  # bowling share of (bat balls + bowl balls): < 0.2 batter, > 0.8 bowler, between = all-rounder (see docs/VALUE_role_field.md)


@lru_cache(maxsize=1)
def keepers() -> frozenset:
    """Players marked keeper (yes / sometimes) in the reviewed list reference/player_overrides.csv; nothing else is used."""
    d = pd.read_csv(REF / "player_overrides.csv", usecols=["name", "keeper"])
    return frozenset(d.name[d.keeper.notna()])


def main_role(bat_balls, bowl_balls):
    """batter / bowler / all-rounder from the share of a player-season's balls spent bowling."""
    b = pd.Series(bowl_balls, dtype=float)
    share = (b / (pd.Series(bat_balls, dtype=float).values + b).replace(0, np.nan)).fillna(0.0)
    return pd.Series(np.select([share < ROLE_CUT, share > 1 - ROLE_CUT], ["batter", "bowler"], "all-rounder"), index=b.index)


def fair_field(f: pd.DataFrame, apps: pd.DataFrame, fair: dict) -> pd.DataFrame:
    """Fielding credit relative to the fielder's group (WAR v2 'fair fielding'). f = player-year field rows (wkts = catches +
    stumpings, sc = their credit, wk = run-out credit); apps = appearances (matches). Keepers are compared with keepers
    (per season), everybody else with everybody else, per match played. Each part is then shrunk toward 0 by its reliability:
    catches / stumpings w = m / (m + k) (k = matches of noise-equal-to-signal, fitted per group), run-outs a constant ro_w."""
    m = apps.groupby(["player", "sy"]).matches.sum()
    f = f.assign(m=pd.MultiIndex.from_frame(f[["player", "sy"]]).map(m).fillna(0.0), keeper=f.player.isin(keepers()))
    for col, grp in (("sc", ["sy", "keeper"]), ("wk", ["sy"])):
        g = f.groupby(grp)
        f[col] = f[col] - g[col].transform("sum") / g.m.transform("sum").replace(0, np.nan) * f.m
    k = f.keeper.map({True: fair["k_keeper"], False: fair["k_other"]})
    f["sc"] = (f.sc * f.m / (f.m + k)).fillna(0.0)
    f["wk"] = (f.wk * fair["ro_w"]).fillna(0.0)
    return f.drop(columns=["m", "keeper"])


def war_table(r: pd.DataFrame, prm: dict, apps: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per player-season (all teams together): batting and bowling runs added and WAR, total WAR.
    WAR = (runs added - replacement per ball x balls) / runs per win of that era.
    Columns: player, sy, then bat_* / bowl_* for balls, ra, war, repl_runs, runs, wkts, sc, wk; and war (bat + bowl + field).
    apps (appearances) + prm["field_fair"] switch fielding to the fair version (fair_field); without apps it is the raw credit."""
    ps = player_year(r)
    if apps is not None and "field_fair" in prm and (ps.role == "field").any():
        fl = ps.role == "field"
        ps = pd.concat([ps[~fl], fair_field(ps[fl], apps, prm["field_fair"])], ignore_index=True)
    out = []
    for role in ("bat", "bowl") + (("field",) if (ps.role == "field").any() else ()):
        d = ps[ps.role == role].copy()
        e = d.sy.map(era_key)
        repl = e.map({k: v["repl"].get(role, 0.0) for k, v in prm["era"].items()}) / 100.0
        rpw = e.map({k: v["rpw"] for k, v in prm["era"].items()})
        d["ra"] = d.sc + d.wk
        d["war"] = (d.ra - repl * d.balls) / rpw
        d["repl_runs"] = repl * d.balls
        out.append(d.assign(role=role))
    b = pd.concat(out)
    w = b.pivot_table(
        index=["player", "sy"],
        columns="role",
        values=["balls", "ra", "war", "repl_runs", "runs", "wkts", "sc", "wk"],
        fill_value=0.0,
    )
    w.columns = [f"{c[1]}_{c[0]}" for c in w.columns]
    w = w.reset_index()
    w["war"] = w.bat_war + w.bowl_war + (w.field_war if "field_war" in w else 0.0)
    return w


# --------------------------------------------------------------------------- projection
def project_table(P: Panel, t: int, prm: dict, era: dict) -> pd.DataFrame:
    """pWAR for season t for every player with history: per role projected rate (runs added per 100 balls), expected balls, pWAR.
    era = {era label: {rpw, repl}} (the shipped params' "era" block)."""
    e = era[era_key(t)]
    out = pd.DataFrame({"player": P.players})
    for role in ("bat", "bowl"):
        sc, wk, den = project_rate(P, role, t, prm)
        eb = exp_balls(P, role, t, prm["balls"][role], prm["ipl_from"])
        rate = sc + wk
        out[f"{role}_rate"] = rate * 100
        out[f"{role}_balls"] = eb
        out[f"{role}_pwar"] = (rate - e["repl"][role] / 100.0) * eb / e["rpw"]
        out[f"{role}_ev"] = den
    out["pwar"] = out.bat_pwar + out.bowl_pwar
    return out


def _panel(rows: dict) -> Panel:
    return Panel(rows["ipl"], pd.concat([rows[c] for c in rows if c != "ipl"]))


def fit_all(db_path=None) -> dict:
    """Fit runs per win, replacement level, projection constants (for season 2027). Seasons used (see docs/VALUE_step3.md):
    'now' era numbers: IPL 2023-2026 only; 'pre' era numbers (display of old seasons only): IPL 2008-2022."""
    rows, apps = all_tables()
    ts, ra = team_seasons(db_path), team_ra(rows["ipl"])
    rp_now = runs_per_win(ts, ra, range(ERA_IPL, 2027))
    rp_pre = runs_per_win(ts, ra, range(2008, ERA_IPL))
    rep_now = replacement(rows["ipl"], apps["ipl"], range(ERA_IPL, 2026))
    rep_pre = replacement(rows["ipl"], apps["ipl"], range(2008, ERA_IPL - 1))

    def cap(d):  # replacement is never better than the average player
        return {k: min(v["per100"], 0.0) for k, v in d.items()}

    prm = fit_for(_panel(rows), 2027)
    return dict(
        era={
            IPL_NOW_LABEL: dict(rpw=rp_now["rpw"], repl=cap(rep_now)),
            IPL_PRE_LABEL: dict(rpw=rp_pre["rpw"], repl=cap(rep_pre)),
        },
        proj=prm,
        detail=dict(
            rpw_now=rp_now,
            rpw_pre=rp_pre,
            rpw_win_prob=rpw_from_win_prob(),
            repl_now=rep_now,
            repl_pre=rep_pre,
        ),
    )


def field_prior(wt: pd.DataFrame, t: int) -> pd.Series:
    """Fielding WAR expected in season t: IPL 2023+ fielding WAR of seasons t-3..t-1 weighted 1/2/3 over 6 (a missed season counts 0)."""
    g = wt.set_index(["player", "sy"]).field_war.unstack(fill_value=0.0)
    wts = {t - 3: 1, t - 2: 2, t - 1: 3}
    return sum(g[y] * v for y, v in wts.items() if y >= ERA_IPL and y in g) / 6.0 if len(g) else pd.Series(dtype=float)


def fit_field_k(wt: pd.DataFrame, targets=(2024, 2025, 2026)) -> float:
    """Shrink of the fielding projection: slope through 0 of actual fielding WAR in t on field_prior(t), targets pooled
    (players with a prior or an actual value), clipped to [0, 1]. Fitted on earlier seasons only for each t."""
    a = wt.set_index(["player", "sy"]).field_war.unstack(fill_value=0.0)
    xs, ys = [], []
    for t in targets:
        x = field_prior(wt, t)
        y = a[t] if t in a else pd.Series(dtype=float)
        ix = x.index.union(y.index)
        xs.append(x.reindex(ix).fillna(0.0).values)
        ys.append(y.reindex(ix).fillna(0.0).values)
    x, y = np.concatenate(xs), np.concatenate(ys)
    return float(np.clip((x * y).sum() / (x * x).sum(), 0.0, 1.0))


def fit_field_fair(rows: pd.DataFrame, apps: pd.DataFrame, min_m: int = 6) -> dict:
    """Reliability of fielding from season to season (IPL, players with >= min_m matches in both seasons).
    Catches + stumpings per match are counts, so noise per match is about their mean; signal = covariance between consecutive
    seasons (weighted by the smaller number of matches); k = mean / signal = matches at which noise equals signal, per group
    (keepers, others). Run-outs: the same-season-pair correlation of run-out credit per match (clipped at 0) = one season's weight."""
    f = rows[rows.role == "field"].groupby(["player", "sy"])[["wkts", "sc", "wk"]].sum().reset_index()
    m = apps.groupby(["player", "sy"]).matches.sum().reset_index()
    f = f.merge(m, on=["player", "sy"], how="outer").fillna(0.0)
    f = f[f.matches >= min_m].assign(keeper=lambda d: d.player.isin(keepers()), cpm=lambda d: d.wkts / d.matches, rom=lambda d: d.wk / d.matches)
    a = f.merge(f.assign(sy=f.sy - 1), on=["player", "sy", "keeper"])
    out, wt = {}, np.minimum(a.matches_x, a.matches_y)
    for kp, name in ((True, "k_keeper"), (False, "k_other")):
        g, w_ = a[a.keeper == kp], wt[a.keeper == kp]
        x, y = g.cpm_x, g.cpm_y
        mx = np.average(x, weights=w_)
        cov = np.average((x - mx) * (y - np.average(y, weights=w_)), weights=w_)
        out[name] = float(mx / cov)
        out[f"n_{name[2:]}"] = int(len(g))
        out[f"r_catch_{name[2:]}"] = float(np.corrcoef(x, y)[0, 1])
    out["ro_w"] = float(np.clip(np.corrcoef(a.rom_x, a.rom_y)[0, 1], 0.0, 1.0))
    return out


def fit_v2(db_path=None) -> dict:
    """WAR v2 params: era block as shipped in war_params_v2.json (rpw unchanged, replacement -6), projection constants refit on
    fielding-adjusted bat / bowl rates (the bowler's wicket credit loses the fielders' share), fielding shrink k."""
    prm = load_params("v2")
    rows, apps = all_tables(fielding=prm["fielding"])
    prm["proj"] = fit_for(_panel(rows), 2027)
    prm["field_k"] = fit_field_k(war_table(rows["ipl"], prm))
    prm["field_fair"] = fit_field_fair(rows["ipl"], apps["ipl"])
    return prm


def fit_v3(db_path=None) -> dict:
    """WAR v3 params: no fielding; runs added adjusted for match conditions at MATCH_W; replacement -6 and runs per win as v2
    unless the refit (on the adjusted team runs added, 40 IPL 2023-26 team-seasons) is reported to change them (docs/VALUE_war_v3.md).
    Projection constants are refit on the adjusted bat / bowl rates; the refit runs-per-win goes into `detail`."""
    prm = load_params("v2")
    for k in ("fielding", "field_k", "field_fair"):
        prm.pop(k, None)
    rows, apps = all_tables(match_w=MATCH_W)
    ts, ra = team_seasons(db_path), team_ra(rows["ipl"])
    prm["detail"]["rpw_now"] = runs_per_win(ts, ra, range(ERA_IPL, 2027))
    prm["detail"]["rpw_pre"] = runs_per_win(ts, ra, range(2008, ERA_IPL))
    prm["proj"] = fit_for(_panel(rows), 2027)
    prm["version"], prm["match_w"] = "v3", MATCH_W
    prm["note"] = (
        "v3: batting + bowling only (no fielding; bowler keeps full credit for catches and stumpings, run-outs credit nobody), "
        "runs added adjusted 25% for match conditions (models/match_adjust.py), replacement -6 runs/100 balls both roles. "
        "proj refit on the adjusted rates."
    )
    return prm


def projections(prm_all: dict, season: int = 2027) -> pd.DataFrame:
    rows, _ = all_tables(fielding=prm_all.get("fielding"), match_w=prm_all.get("match_w", 0.0))
    return project_table(_panel(rows), season, prm_all["proj"], prm_all["era"])


def write_pwar_csv(prm_all: dict, season: int = 2027) -> pd.DataFrame:
    """Players with T20 balls in the last two seasons (any league), ranked by pWAR.
    cricsheet_name, pwar (bat + bowl), bat, bowl, exp_balls_bat / bowl (expected IPL balls), bat_rate / bowl_rate (projected runs
    added per 100 balls), ipl_balls_2023_on (0 = no IPL history in the Impact era: expected balls are then 0 and pwar is 0)."""
    rows, _ = all_tables(fielding=prm_all.get("fielding"), match_w=prm_all.get("match_w", 0.0))
    P = _panel(rows)
    p = project_table(P, season, prm_all["proj"], prm_all["era"])
    fp = 0.0
    if "field_k" in prm_all:  # WAR v2: fielding credit, shrunk past fielding WAR
        fp = p.player.map(field_prior(war_table(rows["ipl"], prm_all), season) * prm_all["field_k"]).fillna(0.0)
    p["pwar"] = p.bat_pwar + p.bowl_pwar + fp
    p["field_pwar"] = fp
    recent = pd.concat(rows.values())
    recent = recent[recent.sy >= season - 2].groupby("player").balls.sum()
    recent = recent[recent > 0]  # fielding-only rows have no balls
    ib = sum(P.M["I", r, "balls"].loc[:, ERA_IPL : season - 1].sum(1) for r in ("bat", "bowl"))
    p = p[p.player.isin(recent.index)]
    out = pd.DataFrame(
        {
            "cricsheet_name": p.player,
            "pwar": p.pwar.round(3),
            "bat": p.bat_pwar.round(3),
            "bowl": p.bowl_pwar.round(3),
            "exp_balls_bat": p.bat_balls.round(0).astype(int),
            "exp_balls_bowl": p.bowl_balls.round(0).astype(int),
            "bat_rate": p.bat_rate.round(2),
            "bowl_rate": p.bowl_rate.round(2),
            "ipl_balls_2023_on": ib.reindex(p.player).values.astype(int),
        }
    )
    if "field_k" in prm_all:  # v2 only
        out.insert(4, "field", p.field_pwar.round(3).values)
    out = out.sort_values(["pwar", "cricsheet_name"], ascending=[False, True])
    out.to_csv(DATA / f"pwar_ipl_{season}.csv", index=False)
    return out


# --------------------------------------------------------------------------- validation (all out of sample: year t uses data before t)
def _metrics(a, pred, prev_war, prev_raw):
    """a = actual WAR, pred = pWAR, prev_war = last season's WAR, prev_raw = last season's runs (batters) / wickets (bowlers)."""
    k = (prev_war * a).sum() / (
        prev_war**2
    ).sum()  # best possible rescaling of last season's WAR (in sample, flatters the baseline)

    def r(x):
        return float(np.corrcoef(x, a)[0, 1])

    def sp(x):
        return float(pd.Series(x).rank().corr(pd.Series(a).rank()))

    def mae(x):
        return float(np.abs(a - x).mean())

    return dict(
        n=len(a),
        r_pwar=r(pred),
        r_last_war=r(prev_war),
        r_last_raw=r(prev_raw),
        rho_pwar=sp(pred),
        rho_last_war=sp(prev_war),
        rho_last_raw=sp(prev_raw),
        mae_pwar=mae(pred),
        mae_last_war=mae(prev_war),
        mae_last_war_scaled=mae(k * prev_war),
        mae_zero=mae(0 * a),
        scale=float(k),
    )


def validate_players(rows, prm_all, targets=(2024, 2025, 2026), minb=100):
    """For each target year t: fit the projection constants on pseudo-targets before t, project t from earlier data, compare with the
    realised WAR of players with at least minb balls in t who also had IPL balls the season before.
    Returns (per-role pooled metrics, per-year r, rate-level r)."""
    P = _panel(rows)
    W = war_table(rows["ipl"], prm_all)
    ps = player_year(rows["ipl"])
    res, per_year, rate = [], [], []
    for role in ("bat", "bowl"):
        A, PR, LW, LR = [], [], [], []
        for t in targets:
            prm = fit_for(P, t)
            pt = project_table(P, t, prm, prm_all["era"]).set_index("player")
            act = W[W.sy == t].set_index("player")
            prev = W[W.sy == t - 1].set_index("player")
            pr = ps[(ps.role == role) & (ps.sy == t - 1)].set_index("player")
            m = [
                x
                for x in act.index[act[f"{role}_balls"] >= minb]
                if x in prev.index and prev.loc[x, f"{role}_balls"] > 0
            ]
            a = act.loc[m, f"{role}_war"].values
            pw = pt.loc[m, f"{role}_pwar"].values
            lw = prev.loc[m, f"{role}_war"].values
            lr = (pr.loc[m, "runs"] if role == "bat" else pr.loc[m, "wkts"]).values
            A.append(a)
            PR.append(pw)
            LW.append(lw)
            LR.append(lr)
            d = _metrics(a, pw, lw, lr)
            per_year.append(
                dict(
                    role=role,
                    year=t,
                    n=d["n"],
                    r_pwar=d["r_pwar"],
                    r_last_war=d["r_last_war"],
                    r_last_raw=d["r_last_raw"],
                )
            )
            ar = (act.loc[m, f"{role}_ra"] / act.loc[m, f"{role}_balls"] * 100).values
            prate = pt.loc[m, f"{role}_rate"].values
            raw = (
                pr.loc[m, "runs"] / pr.loc[m, "balls"] * (100 if role == "bat" else -6)
            ).values  # strike rate, or minus economy
            rate.append(
                dict(
                    role=role,
                    year=t,
                    n=len(m),
                    r_proj_rate=float(np.corrcoef(prate, ar)[0, 1]),
                    r_last_sr_or_econ=float(np.corrcoef(raw, ar)[0, 1]),
                    proj_sd=float(prate.std()),
                    actual_sd=float(ar.std()),
                )
            )
        res.append(dict(role=role, **_metrics(*(np.concatenate(x) for x in (A, PR, LW, LR)))))
    return pd.DataFrame(res), pd.DataFrame(per_year), pd.DataFrame(rate)


def validate_teams(rows, apps, prm_all, ts, targets):
    """Team level: the sum of pWAR (projected from data before the season) of each team's most-used XI that season (by matches, then
    balls) against that team's actual win share. Baselines: the same XI's summed raw WAR the season before, and the team's own win
    share the season before (teams whose name is unchanged). Ceiling: the XI's summed realised WAR that season."""
    P = _panel(rows)
    W = war_table(rows["ipl"], prm_all)
    u = _usage_rank(rows["ipl"], apps["ipl"])
    out = []
    for t in targets:
        prm = fit_for(P, t)
        pt = project_table(P, t, prm, prm_all["era"]).set_index("player").pwar
        xi = u[(u.sy == t) & (u.rk <= 11)]
        w_t = W[W.sy == t].set_index("player").war
        w_p = W[W.sy == t - 1].set_index("player").war
        g = xi.assign(
            pwar=xi.player.map(pt).fillna(0.0),
            last=xi.player.map(w_p).fillna(0.0),
            real=xi.player.map(w_t).fillna(0.0),
        )
        g = g.groupby("team", as_index=False)[["pwar", "last", "real"]].sum()
        g["yr"] = t
        out.append(g)
    g = pd.concat(out).merge(
        ts.rename(columns={"w": "win"})[["yr", "team", "win"]], on=["yr", "team"]
    )
    prev = ts.assign(yr=ts.yr + 1).rename(columns={"w": "prev_win"})[["yr", "team", "prev_win"]]
    g = g.merge(prev, on=["yr", "team"], how="left")
    res = {}
    for name, col in (
        ("pwar (XI)", "pwar"),
        ("last season WAR (XI)", "last"),
        ("previous win share", "prev_win"),
        ("realised WAR (XI), ceiling", "real"),
    ):
        d = g.dropna(subset=[col])
        r = np.corrcoef(d[col], d.win)[0, 1]
        sl = np.polyfit(
            d[col], d.win, 1
        )  # straight line fitted on the same points (in sample, flatters every row equally)
        res[name] = dict(
            n=len(d),
            r=float(r),
            r2=float(r**2),
            rmse_win=float(np.sqrt(((np.polyval(sl, d[col]) - d.win) ** 2).mean())),
            slope=float(sl[0]),
        )
    res["constant (mean)"] = dict(
        n=len(g), r=0.0, r2=0.0, rmse_win=float(g.win.std(ddof=0)), slope=0.0
    )
    return pd.DataFrame(res).T, g


def pre_w_test(rows, targets=(2024, 2025, 2026), grid=(0.0, 0.25, 0.5, 1.0)):
    """Do IPL seasons before 2023 help as down-weighted evidence? Same grid search of the other constants for each pre_w; paired
    bootstrap of the loss difference vs pre_w = 0 over player-seasons (95% range; negative = older seasons help)."""
    P = _panel(rows)
    rng = np.random.default_rng(3)
    out = []
    for role in ("bat", "bowl"):
        base = None
        for pw in grid:
            q = fit_proj(P, role, targets, pre_w=pw)
            e, w = _loss_terms(P, role, targets, {"ipl_from": ERA_IPL, role: q})
            base = base or (e, w)
            n = len(e)
            ds = []
            for _ in range(400):
                i = rng.integers(0, n, n)
                ds.append(
                    (e[i].sum() / w[i].sum()) ** 0.5 - (base[0][i].sum() / base[1][i].sum()) ** 0.5
                )
            cur, ref = (e.sum() / w.sum()) ** 0.5, (base[0].sum() / base[1].sum()) ** 0.5
            out.append(
                dict(
                    role=role,
                    pre_w=pw,
                    rmse=float(cur),
                    diff_vs_0=float(cur - ref),
                    lo=float(np.percentile(ds, 2.5)),
                    hi=float(np.percentile(ds, 97.5)),
                    a=q["a"],
                    s=q["s"],
                    k=q["k"],
                )
            )
    return pd.DataFrame(out)


def variants_test(rows, targets=(2024, 2025, 2026)):
    """Loss of the projection (ball-weighted RMSE of runs added per ball, 2024-26) when parts are switched off; constants refitted each time."""
    P = _panel(rows)
    out = []
    for role in ("bat", "bowl"):
        zero = loss(
            P, role, targets, {"ipl_from": ERA_IPL, role: dict(a=0, s=1, pre_w=0, k=[1e12, 1e12])}
        )
        for name, ag in (("IPL 2023+ only", (0.0,)), ("+ other leagues", AGRID)):
            q = fit_proj_over(P, role, targets, ag)
            out.append(
                dict(
                    role=role,
                    variant=name,
                    rmse=loss(P, role, targets, {"ipl_from": ERA_IPL, role: q}),
                    a=q["a"],
                    s=q["s"],
                    k=q["k"],
                    zero=zero,
                )
            )
        for pw in (
            0.5,
            1.0,
        ):  # wicket part leans on older IPL seasons (its own longer-run dismissal record)
            best = min(
                (
                    loss(
                        P,
                        role,
                        targets,
                        {
                            "ipl_from": ERA_IPL,
                            role: dict(a=0.25, s=1.0, pre_w=0.0, pre_w_wk=pw, k=[k1, k2]),
                        },
                    ),
                    k1,
                    k2,
                )
                for k1 in KGRID
                for k2 in KGRID
            )
            out.append(
                dict(
                    role=role,
                    variant=f"wicket part also uses IPL before 2023 at weight {pw}",
                    rmse=best[0],
                    a=0.25,
                    s=1.0,
                    k=list(best[1:]),
                    zero=zero,
                )
            )
    return pd.DataFrame(out)


def sensitivity(rows, apps, prm_all):
    """Replacement-level variants: runs added per 100 balls (bat per ball faced, bowl per ball bowled) and what each would do to the WAR of
    a typical regular (400 balls batting, 288 bowling) = rate x balls / runs per win of the 2023 era."""
    rpw = prm_all["era"][IPL_NOW_LABEL]["rpw"]
    out = []
    for name, kw in (
        ("next season, outside top 11 (used)", dict(cut=11, lag=1)),
        ("next season, outside top 13", dict(cut=13, lag=1)),
        ("same season, outside top 11", dict(cut=11, lag=0)),
        ("same season, outside top 13", dict(cut=13, lag=0)),
    ):
        for era, yrs in (
            ("2023+", range(ERA_IPL, 2026 if kw["lag"] else 2027)),
            ("pre-2023", range(2008, ERA_IPL - (1 if kw["lag"] else 0))),
        ):
            d = replacement(rows["ipl"], apps["ipl"], yrs, **kw)
            for role, nb in (("bat", 400), ("bowl", 288)):
                out.append(
                    dict(
                        variant=name,
                        era=era,
                        role=role,
                        per100=d[role]["per100"],
                        se=d[role]["se"],
                        balls=d[role]["balls"],
                        war_per_regular=d[role]["per100"] / 100 * nb / rpw,
                    )
                )
    return pd.DataFrame(out)


def main() -> None:
    import sys

    if "--validate" in sys.argv:
        prm = load_params()
        rows, apps = all_tables(match_w=prm.get("match_w", 0.0))
        pd.set_option("display.width", 250, "display.max_columns", 30)
        ts = team_seasons()
        print(sensitivity(rows, apps, prm).round(3).to_string())
        print(variants_test(rows).round(5).to_string())
        print(pre_w_test(rows).round(5).to_string())
        for name, tg in (("2024-26", (2024, 2025, 2026)), ("2020-26", tuple(range(2020, 2027)))):
            t, g = validate_teams(rows, apps, prm, ts, tg)
            print("TEAM", name, len(g))
            print(t.round(3).to_string())
        for x in validate_players(rows, prm):
            print(x.round(3).to_string())
        return
    if "--v1" in sys.argv:  # the original fit (replacement from the next-season bench); writes war_params.json only
        PARAMS.write_text(json.dumps(fit_all(), indent=1))
        return
    if "--v2" in sys.argv:
        prm = fit_v2()
        PARAMS_V2.write_text(json.dumps(prm, indent=1))
        return
    prm = fit_v3()
    PARAMS_V3.write_text(json.dumps(prm, indent=1))
    print(json.dumps(prm["era"]), json.dumps(prm["proj"]), json.dumps(prm["detail"]["rpw_now"]))
    print(write_pwar_csv(prm).head(25).to_string())


if __name__ == "__main__":
    main()
