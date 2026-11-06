"""Run expectancy (RE) and the ball-by-ball "runs added" credit built on it.

RE(group, era, wickets_lost, balls_left) = average runs a side scores from that state to the end of a FIRST innings.
Fitted only on trusted first innings (full length or all out; D/L and awarded matches out; super overs out), per
competition-group ("ipl_male", "t20i_female", "hundred_male" ...) and era (see ERA_FROM).

Smoothing: raw cell means are thin for many wickets / many balls left, so each wicket row is smoothed along balls_left with
a local-linear kernel (no bias at the innings start), thin cells are filled from the row above, then the surface is forced
to be monotone: more balls left -> more runs, more wickets lost -> fewer runs (weighted isotonic regression).

Ball value (runs added):  v = runs on the ball + RE(after) - RE(before). It is split into
    ball_part   = RE(wkts, balls_left - legal) - RE(wkts, balls_left)       what using up the ball cost
    wicket_part = RE(wkts + wicket, balls_after) - RE(wkts, balls_after)    what a wicket cost (negative)
Second innings use the same table, with RE capped by the runs still needed (nobody can add more than the target needs).
A venue factor f (shrunk venue/era scoring ratio) scales both parts. Constant offsets bat_k / bowl_k make the average
credit per ball exactly 0 on the fit sample (extras are not the batter's, byes not the bowler's).

Rebuild:  python -m cricket_analytics.models.run_expectancy
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .. import competitions
from ..db import query
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, BOWLER_WICKET, DISMISSAL, LEGAL_BALL, RUNS_CONCEDED
from ..sql.state import ball_state


def ra_state(f: Filters) -> tuple[str, list]:
    """`ball_state(f)` with the trust rule widened so rain-shortened matches count (used by runs added and WAR; the
    run-expectancy FIT keeps the strict rule). Overrides trusted / balls_remaining / target, adds inn_len.

    Length of an innings = the balls the side had. Complete first innings (all overs or all out): the full length.
    Otherwise the first innings stopped early: its length is the balls actually bowled, and in a match with no D/L
    label the chase had the same length and the plain target (first total + 1), so both innings count. A D/L match with
    an incomplete first innings: only that first innings counts (the chase target was reset and is not stored; the
    innings length is known only after the fact, a small look-ahead). Second innings of D/L and awarded matches,
    washed-out matches (no second innings) and chases longer than the first innings stay out."""
    sql, p = ball_state(f)
    lg = f"CASE WHEN {LEGAL_BALL} THEN 1 ELSE 0 END"
    wk = f"CASE WHEN {DISMISSAL} THEN 1 ELSE 0 END"
    out = f"""
    SELECT x.* REPLACE (
        CASE WHEN x.trusted_ra THEN x.inn_len - x.legal_before END AS balls_remaining,
        x.trusted_ra AS trusted,
        CASE WHEN x.innings = 2 AND x.trusted_ra THEN x.first_total + 1 END AS target)
    FROM (
        SELECT y.*, y.inn_len - y.legal_before >= 1 AND CASE
              WHEN y.meth = 'Awarded' THEN FALSE
              WHEN y.meth = 'D/L' THEN y.innings = 1
              WHEN y.complete1 THEN TRUE
              ELSE COALESCE(y.res, '') <> 'no result' AND y.len2 > 0 AND y.len2 <= y.first_legal_ END AS trusted_ra
        FROM (
            SELECT z.*, COALESCE(mm.outcome_method, '') AS meth, mm.result AS res,
                   (z.first_legal_ >= z.max_balls OR z.first_wkts_ >= 10) AS complete1,
                   CASE WHEN z.first_legal_ >= z.max_balls OR z.first_wkts_ >= 10 THEN z.max_balls ELSE z.first_legal_ END AS inn_len
            FROM (
                SELECT d.*,
                       SUM(CASE WHEN d.innings = 1 THEN {lg} END) OVER (PARTITION BY d.match_id) AS first_legal_,
                       SUM(CASE WHEN d.innings = 1 THEN {wk} END) OVER (PARTITION BY d.match_id) AS first_wkts_,
                       COALESCE(SUM(CASE WHEN d.innings = 2 THEN {lg} END) OVER (PARTITION BY d.match_id), 0) AS len2
                FROM ({sql}) d
            ) z JOIN matches mm ON mm.match_id = z.match_id
        ) y
    ) x"""
    return out, p


DATA = Path(__file__).parent / "data"
# first year of the later era; a group not listed here has one era. Chosen from measured average first-innings
# totals per season (docs/VALUE_step1.md): IPL jumped from ~163 (2008-22) to 183+ (2023, impact player); Blast ~168 -> ~177.
ERA_FROM = {"ipl_male": 2023, "blast_male": 2022}
VENUE_K = 10  # shrinkage: a venue with 10 first innings is half-way to 1.0
MIN_WEIGHT = 15.0  # effective balls needed to trust a smoothed cell
_MAXW = 10

# Columns for one row per ball. Use as `WITH d AS ({ball_state sql}) SELECT {BALL_COLS} FROM d JOIN matches m ON d.match_id = m.match_id`
BALL_COLS = f"""d.match_id, d.innings, d.batter, d.bowler, d.player_out,
       m.competition || '_' || m.gender AS grp, year(m.date) AS yr, m.venue,
       d.score_before, d.wickets_before, d.balls_remaining AS b, d.target, d.first_total, d.runs_total, d.runs_batter,
       CASE WHEN {LEGAL_BALL} THEN 1 ELSE 0 END AS legal,
       CASE WHEN {DISMISSAL} THEN 1 ELSE 0 END AS wk,
       CASE WHEN {DISMISSAL} AND d.player_out = d.batter THEN 1 ELSE 0 END AS striker_out,
       CASE WHEN {BOWLER_WICKET} THEN 1 ELSE 0 END AS bowler_wk,
       {RUNS_CONCEDED} AS conceded,
       CASE WHEN {BALL_FACED} THEN 1 ELSE 0 END AS faced"""
USABLE = "d.trusted AND d.balls_remaining >= 1"


def _pava(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted isotonic regression, non-decreasing."""
    vals, wts, cnt = [], [], []
    for yi, wi in zip(y, w):
        vals.append(float(yi))
        wts.append(float(wi))
        cnt.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            tw = wts[-2] + wts[-1]
            vals[-2] = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / tw
            wts[-2] = tw
            cnt[-2] += cnt[-1]
            vals.pop(), wts.pop(), cnt.pop()
    return np.repeat(vals, cnt)


def smooth_table(n: np.ndarray, s: np.ndarray) -> np.ndarray:
    """n, s: [wickets 0..9, balls_left 0..B] counts and sums of remaining runs. Returns the smoothed RE surface (same shape)."""
    nw, b1 = n.shape
    x = np.arange(b1, dtype=float)
    est = np.full((nw, b1), np.nan)
    den = np.zeros((nw, b1))
    for w in range(nw):
        sigma = 3.0 + 1.5 * w
        for b0 in range(1, b1):
            k = np.exp(-0.5 * ((x - b0) / sigma) ** 2)
            k[0] = 0
            dx = x - b0
            nk = n[w] * k
            s0, s1, s2 = nk.sum(), (nk * dx).sum(), (nk * dx * dx).sum()
            t0, t1 = (s[w] * k).sum(), (s[w] * k * dx).sum()
            den[w, b0] = s0
            if s0 < MIN_WEIGHT:
                continue
            det = s0 * s2 - s1 * s1
            est[w, b0] = (s2 * t0 - s1 * t1) / det if det > 1e-9 * s0 * s2 else t0 / s0
    est = np.clip(est, 0, None)
    # fill thin cells (states that almost never happen): copy the shape of a neighbouring wicket row, scaled to match
    # at the nearest well-measured balls_left of this row; a row with no good cell at all = 0.6 x the row above (guess)
    for _ in range(2 * nw):
        todo = np.argwhere(np.isnan(est[:, 1:])) + [0, 1]
        if len(todo) == 0:
            break
        for w, b0 in todo:
            good = np.where(~np.isnan(est[w]))[0]
            good = good[good > 0]
            for w2 in (w + 1, w - 1):
                if not 0 <= w2 < nw or np.isnan(est[w2, b0]):
                    continue
                ok = good[~np.isnan(est[w2, good])]
                if len(ok):
                    bg = ok[np.argmin(np.abs(ok - b0))]
                    est[w, b0] = est[w2, b0] * est[w, bg] / max(est[w2, bg], 1e-9)
                    break
                if len(good) == 0 and w2 == w - 1:
                    est[w, b0] = 0.6 * est[w2, b0]
                    break
    if np.isnan(est[:, 1:]).any():
        raise ValueError("could not fill the run-expectancy table")
    est[:, 0] = 0
    wt = np.maximum(den, 1e-3)
    for _ in range(20):  # alternate the two monotone projections, then make it exact
        for w in range(nw):  # more balls left -> more runs
            est[w, 1:] = _pava(est[w, 1:], wt[w, 1:])
        for b0 in range(1, b1):  # more wickets lost -> fewer runs
            est[:, b0] = -_pava(-est[:, b0], wt[:, b0])
    est = np.maximum.accumulate(est, axis=1)
    est = np.minimum.accumulate(
        est, axis=0
    )  # a pointwise min of balls-monotone rows stays balls-monotone
    return est


def era_of(grp: str, yr: int) -> int:
    """First year of the era a match in year `yr` belongs to (0 = the single era)."""
    e = ERA_FROM.get(grp, 0)
    return e if yr >= e else 0


class Model:
    """The fitted tables, loaded from models/data/*.csv."""

    def __init__(self, re_df: pd.DataFrame, adj: pd.DataFrame, ven: pd.DataFrame):
        self.re_df, self.adj, self.ven = re_df, adj, ven
        self.tables: dict[tuple[str, int], np.ndarray] = {}
        for (g, e), t in re_df.groupby(["grp", "era_from"]):
            r = np.zeros((_MAXW + 1, int(t.balls_left.max()) + 1))
            r[t.wickets.values, t.balls_left.values] = t.re.values
            self.tables[(g, int(e))] = r

    def re_at(self, grp: str, era: int, wickets: int, balls_left: int) -> float:
        return float(self.tables[(grp, era)][wickets, balls_left])

    def annotate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add era, vf (venue factor), ball_part, wkt_part (unscaled), bat_k, bowl_k to a BALL_COLS frame."""
        df = df.copy()
        df["era_from"] = [era_of(g, y) for g, y in zip(df.grp, df.yr)]
        df = df.merge(self.ven, how="left", on=["grp", "era_from", "venue"])
        df = df.merge(
            self.adj[["grp", "era_from", "bat_k", "bowl_k"]], how="left", on=["grp", "era_from"]
        )
        df["vf"] = df["vf"].fillna(1.0)
        bp, wp = np.zeros(len(df)), np.zeros(len(df))
        for (g, e), idx in df.groupby(["grp", "era_from"]).indices.items():
            if (g, e) not in self.tables:
                raise ValueError(f"no run-expectancy table for {g} era {e}; rerun the fit")
            r, s = self.tables[(g, e)], df.iloc[idx]
            w = np.clip(s.wickets_before.values, 0, 9)
            b = np.clip(s.b.values, 1, r.shape[1] - 1)
            b2 = np.clip(b - s.legal.values, 0, None)
            w2 = np.minimum(w + s.wk.values, _MAXW)
            need0 = np.where(s.innings.values == 2, s.target.values - s.score_before.values, np.inf)
            need1 = need0 - s.runs_total.values
            cap0, cap1 = np.maximum(need0, 0), np.maximum(need1, 0)
            a = np.minimum(r[w, b], cap0)
            bb = np.minimum(r[w, b2], cap1)
            c = np.minimum(r[w2, b2], cap1)
            bp[idx], wp[idx] = bb - a, c - bb
        df["ball_part"], df["wkt_part"] = bp, wp
        return df


def _bat_raw(df):  # batter credit without the constant offset, for rows he faced (or was out on)
    return df.runs_batter + df.vf * (df.ball_part + df.wkt_part * df.striker_out)


def _bowl_raw(df):
    return -(df.conceded + df.vf * (df.ball_part + df.wkt_part * df.bowler_wk))


def _query_balls(f: Filters, db_path, where: str, params: list, wide: bool = False) -> pd.DataFrame:
    st, sp = (ra_state if wide else ball_state)(f)
    sql = f"WITH d AS ({st}) SELECT {BALL_COLS} FROM d JOIN matches m ON d.match_id = m.match_id WHERE {USABLE} AND {where}"
    df = query(sql, sp + params, db_path=db_path)
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


def fit(db_path=None, out_dir: Path = DATA) -> dict:
    """Rebuild the three CSVs from the DB. Returns a small summary dict per (group, era)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    re_rows, adj_rows, ven_rows, summary = [], [], [], {}
    seen = set()
    for key, comp in competitions.COMPETITIONS.items():
        grp = f"{comp.competition}_{comp.gender}"
        if grp in seen:
            continue
        seen.add(grp)
        df = _query_balls(Filters(competition=key), db_path, "d.innings = 1", [])
        if df.empty:
            continue
        df["era_from"] = [era_of(grp, y) for y in df.yr]
        df["rem"] = df.first_total - df.score_before
        df["wickets_before"] = df.wickets_before.clip(0, 9)
        prelim = []
        for era, e in df.groupby("era_from"):
            bmax = int(e.b.max())
            n = np.zeros((_MAXW, bmax + 1))
            s = np.zeros_like(n)
            np.add.at(n, (e.wickets_before.values, e.b.values), 1)
            np.add.at(s, (e.wickets_before.values, e.b.values), e.rem.values)
            re = smooth_table(n, s)
            for w in range(_MAXW):
                for b in range(1, bmax + 1):
                    re_rows.append((grp, era, w, b, round(float(re[w, b]), 4), int(n[w, b])))
            tot = e.drop_duplicates("match_id")
            prelim.append((era, tot.first_total.mean(), len(tot)))
            # venue factors (shrunk toward 1)
            v = tot.groupby("venue").first_total.agg(["mean", "size"])
            ratio = v["mean"] / tot.first_total.mean()
            vf = (v["size"] * ratio + VENUE_K) / (v["size"] + VENUE_K)
            for name, val in vf.items():
                ven_rows.append((grp, era, name, int(v.loc[name, "size"]), round(float(val), 4)))
        # centring offsets: need the tables in place, so build a temporary model first
        tmp_adj = pd.DataFrame([(grp, e, 0.0, 0.0, m, n_) for e, m, n_ in prelim], columns=ADJ_COLS)
        re_df = pd.DataFrame(re_rows, columns=RE_COLS)
        ven_df = pd.DataFrame(ven_rows, columns=VEN_COLS).rename(columns={"factor": "vf"})
        mdl = Model(re_df, tmp_adj, ven_df[["grp", "era_from", "venue", "vf"]])
        ann = mdl.annotate(df)
        for era, e in ann.groupby("era_from"):
            m = [p for p in prelim if p[0] == era][0]
            sel = e[(e.faced == 1) | (e.striker_out == 1)]
            ns = _nonstriker_out(e)
            bat_k = -(_bat_raw(sel).sum() + ns) / max(len(sel), 1)
            bowl_k = -_bowl_raw(e).mean()
            adj_rows.append(
                (
                    grp,
                    era,
                    round(float(bat_k), 5),
                    round(float(bowl_k), 5),
                    round(float(m[1]), 2),
                    m[2],
                )
            )
            summary[(grp, era)] = dict(
                first_innings=m[2], avg_total=m[1], bat_k=bat_k, bowl_k=bowl_k
            )
    pd.DataFrame(re_rows, columns=RE_COLS).to_csv(out_dir / "run_expectancy.csv", index=False)
    pd.DataFrame(adj_rows, columns=ADJ_COLS).to_csv(out_dir / "adjust.csv", index=False)
    pd.DataFrame(ven_rows, columns=VEN_COLS).to_csv(out_dir / "venue_factor.csv", index=False)
    load.cache_clear()
    return summary


def _nonstriker_out(e: pd.DataFrame) -> float:
    ns = e[(e.wk == 1) & (e.striker_out == 0)]
    return float((ns.vf * ns.wkt_part).sum())


RE_COLS = ["grp", "era_from", "wickets", "balls_left", "re", "n"]
ADJ_COLS = ["grp", "era_from", "bat_k", "bowl_k", "avg_first_total", "first_innings"]
VEN_COLS = ["grp", "era_from", "venue", "matches", "factor"]


@lru_cache(maxsize=1)
def load() -> Model:
    re_df = pd.read_csv(DATA / "run_expectancy.csv")
    adj = pd.read_csv(DATA / "adjust.csv")
    ven = pd.read_csv(DATA / "venue_factor.csv").rename(columns={"factor": "vf"})
    return Model(re_df, adj, ven[["grp", "era_from", "venue", "vf"]])


def batting_credit(df: pd.DataFrame) -> pd.Series:
    """Batter runs added per row of an annotated frame (striker rows: he faced it or was out on it)."""
    return _bat_raw(df) + df.bat_k


def bowling_credit(df: pd.DataFrame) -> pd.Series:
    return _bowl_raw(df) + df.bowl_k


if __name__ == "__main__":
    for k, v in fit().items():
        print(k, {a: round(b, 3) for a, b in v.items()})
