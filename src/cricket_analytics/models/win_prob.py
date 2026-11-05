"""Win probability (WP) for 6-ball T20 matches, fitted from our own ball-by-ball data with numpy only.

Two logistic models (fitted by Newton / IRLS, a small ridge keeps them stable), both read the state BEFORE a ball:
  chase  : P(chasing side wins | runs needed, balls left, wickets lost, competition group, era)       innings 2
  first  : P(side batting first wins | score vs par, wickets lost, balls left, competition group, era) innings 1
"Group" = ipl | t20i_men | t20i_women | league (BBL, Blast, CPL, PSL, SA20). "Era" = 1 from 2019 on (scoring jumped).
Ties count 0.5. Matches that are not `trusted` (D/L, awarded, short first innings), no-results and super overs are not used.
The Hundred (5-ball overs, 100 balls) is NOT modelled.

Fitted numbers live in models/data/win_prob.json; rebuild with `python -m cricket_analytics.models.win_prob`
(read-only on the DB; --validate prints the out-of-sample table, --write saves the JSON).

Innings break: the first-innings model is only used up to the last ball of innings 1; the WP after that ball is DEFINED as
1 - chase WP at ball 0 of the chase (target = total + 1), so the WP curve has no jump between the innings.
"""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .. import competitions
from ..db import query
from ..sql.filters import Filters
from ..sql.fragments import MATCH_OUTCOME
from ..sql.state import ball_state

DATA = Path(__file__).parent / "data" / "win_prob.json"
GROUPS = ("league", "ipl", "ipl_impact", "t20i_men", "t20i_women")  # first = baseline level
IMPACT_YEAR = 2023  # Impact Player rule: batting depth changes what a wicket costs
TRAIN_END, TEST_START = 2023, 2024
MAXB = 120
RIDGE = 1e-3
ERA_YEAR = 2019
CHASE_FEATURES = "chase_v2"
FIRST_FEATURES = "first_v1"


def group_of(competition: str, gender: str, year: int = 0) -> str:
    """'ipl_impact' = IPL from 2023 (Impact Player); 'ipl' = before."""
    if competition == "ipl":
        return "ipl_impact" if year >= IMPACT_YEAR else "ipl"
    if competition == "t20i":
        return "t20i_women" if gender == "female" else "t20i_men"
    return "league"


# ── features ─────────────────────────────────────────────────────────────────────────────────────────────────


def _design(
    base: np.ndarray, grp: np.ndarray, era: np.ndarray, slope: np.ndarray, slope2: np.ndarray
) -> np.ndarray:
    """base columns + group/era shifts of the intercept and of two slopes (`slope`: pace, `slope2`: wickets in hand)."""
    cols = [base]
    for g in GROUPS[1:]:
        ind = (grp == g).astype(float)
        # ipl_impact has only ~3 seasons: it shifts the level and the value of a wicket, but not the pace slope (it extrapolated badly)
        cols += [ind[:, None], (ind * slope2)[:, None]] + (
            [] if g == "ipl_impact" else [(ind * slope)[:, None]]
        )
    e = era.astype(float)
    cols += [e[:, None], (e * slope)[:, None], (e * slope2)[:, None]]
    return np.hstack(cols)


def chase_x(runs_needed, balls_left, wickets_lost, grp, era) -> np.ndarray:
    r = np.clip(np.asarray(runs_needed, float), 1, None)
    b = np.clip(np.asarray(balls_left, float), 1, MAXB)
    wh = 10 - np.asarray(wickets_lost, float)
    rrr = np.minimum(6 * r / b, 36) / 10  # required rate, per over / 10
    lr, lb = np.log(r), np.log(b)
    base = np.column_stack(
        [
            np.ones_like(r),
            rrr,
            rrr**2,
            lr,
            lb,
            wh / 10,
            (wh / 10) ** 2,
            rrr * wh / 10,
            lb * wh / 10,
            lr * wh / 10,
            (wh <= 2) * rrr,
            (wh <= 4) * (6 * r / b > 12),
            1.0 * (b <= 6) * rrr,
            1.0 * (b <= 18) * rrr,
            # late-innings shape: runs needed per sqrt(balls) is the natural scale when few balls are left
            r / np.sqrt(b),
            (r / np.sqrt(b)) ** 2,
            np.sqrt(b),
            r / np.sqrt(b) * wh / 10,
            np.sqrt(b) * wh / 10,
            r / 10 * (b <= 12),
            r / 10 * (b <= 6),
            r / 10 * (b <= 3),
            (r / 10) ** 2 * (b <= 12),
            r / 10 * lb,
        ]
    )
    return _design(base, np.asarray(grp), np.asarray(era), rrr, wh / 10)


def first_x(score, balls_left, wickets_lost, grp, era, par) -> np.ndarray:
    """`par` = expected final total of an average side from this state, minus the group's average final total."""
    b = np.clip(np.asarray(balls_left, float), 0, MAXB)
    wh = 10 - np.asarray(wickets_lost, float)
    sur = np.asarray(par, float) / 20  # runs ahead of par, in "20-run units"
    done = 1 - b / MAXB
    base = np.column_stack(
        [
            np.ones_like(sur),
            sur,
            sur * done,
            sur * done**2,
            sur**2 * done / 4,
            wh / 10,
            (wh / 10) * done,
            done,
        ]
    )
    return _design(base, np.asarray(grp), np.asarray(era), sur, wh / 10)


# ── fitting ──────────────────────────────────────────────────────────────────────────────────────────────────


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(X: np.ndarray, y: np.ndarray, ridge: float = RIDGE, iters: int = 40) -> dict:
    """Newton / IRLS on standardized columns. y may be 0, 0.5 or 1. Returns {coef, mean, std} on the ORIGINAL scale of X."""
    mu, sd = X.mean(0), X.std(0)
    mu[0], sd[0] = 0.0, 1.0  # column 0 is the intercept
    sd[sd < 1e-9] = 1.0
    Z = (X - mu) / sd
    n = len(y)
    beta = np.zeros(X.shape[1])
    pen = np.eye(X.shape[1]) * ridge * n
    pen[0, 0] = 0
    for _ in range(iters):
        p = _sigmoid(Z @ beta)
        g = Z.T @ (y - p) - pen @ beta
        H = (Z * (p * (1 - p))[:, None]).T @ Z + pen
        step = np.linalg.solve(H + 1e-9 * np.eye(len(beta)), g)
        beta += step
        if np.abs(step).max() < 1e-7:
            break
    return {"coef": beta.tolist(), "mean": mu.tolist(), "std": sd.tolist()}


def _apply(m: dict, X: np.ndarray) -> np.ndarray:
    return _sigmoid(((X - np.array(m["mean"])) / np.array(m["std"])) @ np.array(m["coef"]))


# ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────


def load_states(db_path=None) -> pd.DataFrame:
    """Every ball of every trusted 6-ball T20 match (innings 1-2, no super overs), with the state BEFORE the ball.

    Columns: match_id, innings, ball_seq, score_before, wickets_before, balls_remaining, runs_needed (chase only),
    group, year, bf_win (1 / 0 / 0.5 for the side that batted first, NaN when there is no result)."""
    parts = []
    for key, c in competitions.COMPETITIONS.items():
        if key == "hundred":
            continue
        st, sp = ball_state(Filters(competition=key))
        sql = f"""
        WITH s AS ({st}), mo AS ({MATCH_OUTCOME})
        SELECT s.match_id, s.innings, s.ball_seq, s.score_before, s.wickets_before, s.balls_remaining,
               s.runs_needed, s.target, year(m.date) AS year,
               CASE WHEN m.result = 'tie' THEN 0.5 WHEN mo.winner IS NULL THEN NULL
                    WHEN mo.winner = mo.bat_first THEN 1.0 ELSE 0.0 END AS bf_win
        FROM s JOIN matches m ON m.match_id = s.match_id JOIN mo ON mo.match_id = s.match_id
        WHERE s.trusted AND m.balls_per_over = 6 AND s.balls_remaining >= 1"""
        d = query(sql, sp, db_path=db_path)
        d["group"] = [group_of(c.competition, c.gender, y) for y in d.year]
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    return d[d.bf_win.notna()].reset_index(drop=True)


# ── par table: average runs still to come, by (over, wickets lost), scaled by competition group ──────────────


def _innings_totals(d: pd.DataFrame) -> pd.Series:
    """Final total of innings 1 per match (target - 1 from the innings-2 rows)."""
    return d[d.innings == 2].groupby("match_id").target.first() - 1


def make_par(d: pd.DataFrame) -> dict:
    tot = _innings_totals(d)
    i1 = d[(d.innings == 1) & d.match_id.isin(tot.index)].copy()
    i1["rem"] = i1.match_id.map(tot) - i1.score_before
    i1["ob"] = (i1.balls_remaining - 1) // 6  # 0..19: over index counted from the end
    i1["w"] = i1.wickets_before.clip(0, 9)
    g = i1.groupby(["ob", "w"]).rem.agg(["mean", "count"]).reset_index()
    table = np.full((20, 10), np.nan)
    for r in g.itertuples():
        if r.count >= 300:
            table[int(r.ob), int(r.w)] = r.mean
    for ob in range(20):  # thin cell: copy the cell with one more wicket in hand, else one fewer
        for w in range(10):
            if np.isnan(table[ob, w]):
                nb = [
                    table[ob, x]
                    for x in (w - 1, w + 1)
                    if 0 <= x < 10 and not np.isnan(table[ob, x])
                ]
                table[ob, w] = nb[0] if nb else 0.0
    grp = i1.drop_duplicates("match_id").set_index("match_id").group
    gt = {k: float(v) for k, v in tot.groupby(grp.reindex(tot.index)).mean().items()}
    return {"rem": np.round(table, 2).tolist(), "group_total": gt}


def par_surplus(par: dict, score, balls_left, wickets_lost, grp) -> np.ndarray:
    """Projected final total (score + average runs still to come) minus the group's average total."""
    tab = np.array(par["rem"])
    ob = np.clip((np.asarray(balls_left, int) - 1) // 6, 0, 19)
    ob = np.where(np.asarray(balls_left) <= 0, 0, ob)
    w = np.clip(np.asarray(wickets_lost, int), 0, 9)
    rem = np.where(np.asarray(balls_left) <= 0, 0.0, tab[ob, w])
    gt = np.array([par["group_total"][g] for g in np.asarray(grp)])
    return np.asarray(score, float) + rem - gt


# ── metrics ──────────────────────────────────────────────────────────────────────────────────────────────────


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration(p, y, bins: int = 10) -> pd.DataFrame:
    q = pd.cut(p, np.linspace(0, 1, bins + 1), include_lowest=True)
    t = (
        pd.DataFrame({"p": p, "y": y, "bin": q})
        .groupby("bin", observed=True)
        .agg(n=("p", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    )
    return t.round(3).reset_index()


# ── fit all, validate ────────────────────────────────────────────────────────────────────────────────────────


def _split(d):
    return d[d.year <= TRAIN_END], d[d.year >= TEST_START]


def _chase_frame(d):
    c = d[(d.innings == 2) & d.runs_needed.notna()]
    return c, 1 - c.bf_win.to_numpy()


def _first_frame(d, par):
    f = d[d.innings == 1]
    sur = par_surplus(par, f.score_before, f.balls_remaining, f.wickets_before, f.group)
    return f, f.bf_win.to_numpy(), sur


def _cx(c):
    return chase_x(c.runs_needed, c.balls_remaining, c.wickets_before, c.group, c.year >= ERA_YEAR)


LATE_B, LATE_R, LATE_K = 6, 40, 30


def _late_table(c: pd.DataFrame, y: np.ndarray, model: dict) -> dict:
    """With 6 balls or fewer left, one run is worth a lot and a smooth curve is too sharp, so each (balls, runs needed)
    cell gets its observed mean win rate; the model's prediction is moved toward it by n / (n + LATE_K)."""
    m = c.balls_remaining.to_numpy() <= LATE_B
    t = pd.DataFrame(
        {
            "b": c.balls_remaining.to_numpy()[m],
            "r": c.runs_needed.to_numpy()[m],
            "y": y[m],
            "p": _apply(model, _cx(c[m])),
        }
    )
    t = (
        t[t.r <= LATE_R]
        .groupby(["b", "r"])
        .agg(n=("y", "size"), y=("y", "mean"), p=("p", "mean"))
        .reset_index()
    )
    return {f"{int(r.b)},{int(r.r)}": [int(r.n), round(r.y - r.p, 4)] for r in t.itertuples()}


def _chase_raw(model: dict, r, b, w, grp, year) -> np.ndarray:
    """Logistic model plus the late-cell correction (no monotone fix)."""
    p = _apply(model["chase"], chase_x(r, b, w, grp, np.asarray(year) >= model["meta"]["era_year"]))
    late = model.get("late", {})
    if late:
        adj = np.zeros(len(p))
        for i in np.flatnonzero((b <= LATE_B) & (r <= LATE_R) & (b >= 1) & (r >= 1)):
            cell = late.get(f"{int(b[i])},{int(r[i])}")
            if cell:
                adj[i] = cell[0] / (cell[0] + LATE_K) * cell[1]
        p = np.clip(p + adj, 0.0, 1.0)
    return p


def _chase_predict(model: dict, r, b, w, grp, year) -> np.ndarray:
    """P(chasing side wins). In the last over the per-cell corrections are noisy, so the value is the lowest raw value
    over 1..r runs needed: more runs needed can never raise the chance."""
    r, b, w, grp, year = (np.asarray(x) for x in np.broadcast_arrays(r, b, w, grp, year))
    r, b, w = r.astype(float), b.astype(float), w.astype(float)
    p = _chase_raw(model, r, b, w, grp, year)
    idx = np.flatnonzero((b <= LATE_B) & (b >= 1) & (r >= 2) & (r <= LATE_R))
    if len(idx):
        lo = p[idx].copy()
        for k in range(1, LATE_R):
            lo = np.minimum(
                lo, _chase_raw(model, np.minimum(r[idx], k), b[idx], w[idx], grp[idx], year[idx])
            )
        p[idx] = lo
    return p


def fit_all(d: pd.DataFrame) -> dict:
    c, yc = _chase_frame(d)
    par = make_par(d)
    f, yf, sur = _first_frame(d, par)
    fx = first_x(
        f.score_before, f.balls_remaining, f.wickets_before, f.group, f.year >= ERA_YEAR, sur
    )
    chase = fit_logistic(_cx(c), yc)
    return {
        "chase": chase,
        "late": _late_table(c, yc, chase),
        "first": fit_logistic(fx, yf),
        "par": par,
        "meta": {
            "groups": list(GROUPS),
            "era_year": ERA_YEAR,
            "chase_features": CHASE_FEATURES,
            "first_features": FIRST_FEATURES,
            "n_chase_balls": int(len(c)),
            "n_first_balls": int(len(f)),
            "n_matches": int(d.match_id.nunique()),
            "data_through": str(d.year.max()),
        },
    }


def validate(d: pd.DataFrame) -> dict:
    """Fit on <= TRAIN_END, score on >= TEST_START. Returns metric tables and calibration tables."""
    tr, te = _split(d)
    model = fit_all(tr)
    out = {
        "n_test_matches": int(te.match_id.nunique()),
        "n_train_matches": int(tr.match_id.nunique()),
    }
    rows, cal = [], {}
    # chase
    ct, yt = _chase_frame(te)
    ctr, ytr = _chase_frame(tr)
    p = _chase_predict(
        model, ct.runs_needed, ct.balls_remaining, ct.wickets_before, ct.group, ct.year
    )
    rr = lambda x: 6 * x.runs_needed.to_numpy() / x.balls_remaining.to_numpy()  # noqa: E731
    base = fit_logistic(np.column_stack([np.ones(len(ctr)), np.minimum(rr(ctr), 36)]), ytr)
    pb = _apply(base, np.column_stack([np.ones(len(ct)), np.minimum(rr(ct), 36)]))
    for name, pp, sub in (
        ("chase model", p, None),
        ("required rate only", pb, None),
        ("50/50", np.full(len(yt), 0.5), None),
    ):
        rows.append(
            ("2nd innings (chase)", "all comps", name, len(yt), brier(pp, yt), logloss(pp, yt))
        )
    ipl = ct.group.str.startswith("ipl").to_numpy()
    for name, pp in (
        ("chase model", p),
        ("required rate only", pb),
        ("50/50", np.full(len(yt), 0.5)),
    ):
        rows.append(
            (
                "2nd innings (chase)",
                "IPL",
                name,
                int(ipl.sum()),
                brier(pp[ipl], yt[ipl]),
                logloss(pp[ipl], yt[ipl]),
            )
        )
    cal["chase"] = calibration(p, yt)
    cal["chase_ipl"] = calibration(p[ipl], yt[ipl])
    # first innings
    ft, yft, sur = _first_frame(te, model["par"])
    fx = first_x(
        ft.score_before, ft.balls_remaining, ft.wickets_before, ft.group, ft.year >= ERA_YEAR, sur
    )
    pf = _apply(model["first"], fx)
    ftr, yftr, _ = _first_frame(tr, model["par"])
    gr = ftr.groupby("group").apply(lambda x: x.bf_win.mean(), include_groups=False)
    pg = ft.group.map(gr).to_numpy()
    ipl1 = ft.group.str.startswith("ipl").to_numpy()
    for name, pp in (
        ("first-innings model", pf),
        ("group base rate", pg),
        ("50/50", np.full(len(yft), 0.5)),
    ):
        rows.append(("1st innings", "all comps", name, len(yft), brier(pp, yft), logloss(pp, yft)))
    for name, pp in (
        ("first-innings model", pf),
        ("group base rate", pg),
        ("50/50", np.full(len(yft), 0.5)),
    ):
        rows.append(
            (
                "1st innings",
                "IPL",
                name,
                int(ipl1.sum()),
                brier(pp[ipl1], yft[ipl1]),
                logloss(pp[ipl1], yft[ipl1]),
            )
        )
    cal["first"] = calibration(pf, yft)
    # innings break: first-innings model one ball before the end of innings 1 vs 1 - chase WP at ball 0 of the chase
    c0 = te[(te.innings == 2) & (te.balls_remaining == MAXB)].copy()
    c0["p_chase"] = _chase_predict(
        model, c0.runs_needed, c0.balls_remaining, c0.wickets_before, c0.group, c0.year
    )
    f1 = ft.assign(p_first=pf)[(ft.balls_remaining == 1).to_numpy()]
    j = f1[["match_id", "p_first"]].merge(c0[["match_id", "p_chase"]], on="match_id")
    pe, pc0 = j.p_first.to_numpy(), j.p_chase.to_numpy()
    both = j
    out["break_abs_diff"] = float(np.mean(np.abs(pe - (1 - pc0))))
    out["break_mean_sum"] = float(np.mean(pe + pc0))
    out["break_n"] = int(len(both))
    out["metrics"] = pd.DataFrame(
        rows, columns=["innings", "scope", "model", "n_balls", "brier", "log_loss"]
    ).round(4)
    out["calibration"] = cal
    # match-level: Brier at fixed points of the chase (ball 0 / 60 / 90 balls bowled) for context
    pts = []
    for lab, bl in (("ball 0", 120), ("10 overs", 60), ("15 overs", 30), ("18 overs", 12)):
        s = ct[ct.balls_remaining == bl]
        if len(s):
            ps = p[(ct.balls_remaining == bl).to_numpy()]
            ys = yt[(ct.balls_remaining == bl).to_numpy()]
            pts.append((lab, len(s), brier(ps, ys), brier(np.full(len(ys), 0.5), ys)))
    late = (ct.balls_remaining <= 6).to_numpy()
    pts.append(
        (
            "last over (all balls)",
            int(late.sum()),
            brier(p[late], yt[late]),
            brier(np.full(int(late.sum()), 0.5), yt[late]),
        )
    )
    out["chase_checkpoints"] = pd.DataFrame(
        pts, columns=["point", "matches", "brier_model", "brier_5050"]
    ).round(4)
    return out


# ── prediction API ───────────────────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(DATA.read_text())


def _era(year):
    return np.asarray(year) >= load()["meta"]["era_year"]


def chase_wp(runs_needed, balls_left, wickets_lost, group="league", year=2024) -> np.ndarray:
    """P(chasing side wins). Arrays or scalars. runs_needed <= 0 gives 1; no balls left (or 10 down) and runs still needed gives 0."""
    r, b, w = (np.atleast_1d(np.asarray(x, float)) for x in (runs_needed, balls_left, wickets_lost))
    r, b, w, g, y = np.broadcast_arrays(
        r, b, w, np.atleast_1d(np.asarray(group, object)), np.atleast_1d(np.asarray(year))
    )
    p = _chase_predict(load(), r, b, w, g, y)
    p = np.where((b <= 0) | (w >= 10), 0.0, p)
    return np.where(r <= 0, 1.0, p)


def first_wp(score, balls_left, wickets_lost, group="league", year=2024) -> np.ndarray:
    """P(side batting first wins), from the first-innings model (balls_left >= 1)."""
    s, b, w = (np.atleast_1d(np.asarray(x, float)) for x in (score, balls_left, wickets_lost))
    s, b, w, g, y = np.broadcast_arrays(
        s, b, w, np.atleast_1d(np.asarray(group, object)), np.atleast_1d(np.asarray(year))
    )
    sur = par_surplus(load()["par"], s, b, w, g)
    return _apply(load()["first"], first_x(s, b, w, g, _era(y), sur))


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--validate",
        action="store_true",
        help="print the out-of-sample table (fit <= 2023, test >= 2024)",
    )
    ap.add_argument(
        "--write", action="store_true", help="fit on ALL data and write models/data/win_prob.json"
    )
    a = ap.parse_args()
    d = load_states()
    print(f"{d.match_id.nunique()} matches, {len(d):,} balls")
    if a.validate or not a.write:
        v = validate(d)
        print(v["metrics"].to_string(index=False))
        print(v["chase_checkpoints"].to_string(index=False))
        for k, t in v["calibration"].items():
            print(f"\ncalibration: {k}\n{t.to_string(index=False)}")
        print(
            {
                k: v[k]
                for k in (
                    "break_abs_diff",
                    "break_mean_sum",
                    "break_n",
                    "n_train_matches",
                    "n_test_matches",
                )
            }
        )
    if a.write:
        DATA.write_text(json.dumps(fit_all(d)))
        load.cache_clear()
        print("wrote", DATA)


if __name__ == "__main__":
    main()
