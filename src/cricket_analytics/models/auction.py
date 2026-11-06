"""IPL auction price model (M4) and moneyball market check (M5). Method and numbers: docs/VALUE_m4.md.

Hurdle model per auction: (1) P(sold | player was put on the block) by ridge logistic, (2) price given sold by ridge on
log price. Every feature of auction Y uses data dated before Y only (IPL seasons and other T20 leagues with sy < Y, earlier
auctions and retentions). Split: train 2022-2024, validate 2025, test 2026 (fit on 2022-2025, run once).

Rebuild (about 1 minute, reads the DB, writes models/data/auction_*):  python -m cricket_analytics.models.auction
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..db import query
from . import war as W

DATA = Path(__file__).parent / "data"
REF = Path(__file__).parent.parent / "reference"
FEATURES, PREDS = DATA / "auction_features.csv", DATA / "auction_predictions.csv"
MODEL, MARKET = DATA / "auction_model.json", DATA / "auction_market_players.csv"

YEARS = (2022, 2023, 2024, 2025, 2026)
PURSE = {
    2022: 90,
    2023: 95,
    2024: 100,
    2025: 120,
    2026: 125,
}  # cr per team (docs/VALUE_auctions.md)
MEGA = {2022, 2025}
TEAMS = 10
TRAIN, VAL, TEST = (2022, 2023, 2024), 2025, 2026
ALPHAS = (0.3, 1, 3, 10, 30, 100, 300)
BAT_BALLS, BOWL_BALLS = 300, 288  # a regular's season, as in docs/VALUE_step3.md

# Cricsheet names for auction names the automatic mapping missed (checked against the players who actually played that IPL season)
NAME_FIX = {
    (2022, "Abhinav Manohar Sadarangani"): "A Manohar",
    (2022, "B. Sai Sudharshan"): "B Sai Sudharsan",
    (2022, "Rasikh Salam Dar"): "Rasikh Salam",
    (2023, "Litton Das"): "Liton Das",
    (2023, "Yudhvir Singh Charak"): "Yudhvir Singh",
    (2024, "Rasikh Dar"): "Rasikh Salam",
    (2024, "Shubham Dubey"): "SB Dubey",
    (2025, "Rasikh Salam Dar"): "Rasikh Salam",
    (2025, "Shubham Dubey"): "SB Dubey",
}
# automatic initials matches that joined different people (several auction names on one Cricsheet name): blanked
BAD_MAP = {
    "A Singh", "MP Yadav", "P Simran Singh", "R Vinay Kumar", "S Sharma", "S Singh", "SA Yadav",
}  # fmt: skip
BAD_MAP_ROWS = {(2023, "Upendra Yadav"), (2025, "Upendra Yadav"), (2022, "Mohammed Arshad Khan")}
# 2022 "retentions" that were the two new teams' draft picks, not retentions
DRAFT_2022 = {
    "Hardik Pandya",
    "Rashid Khan",
    "Shubman Gill",
    "KL Rahul",
    "Marcus Stoinis",
    "Ravi Bishnoi",
}


def tf(x: pd.Series) -> pd.Series:
    """True/False/'True'/blank -> 1.0 / 0.0 / NaN."""
    return x.astype(object).map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0}).astype(float)


def total_purse(year: int) -> float:
    return float(PURSE[year] * TEAMS)


# --------------------------------------------------------------------------------------------- inputs
def fix_names(a: pd.DataFrame) -> pd.DataFrame:
    """Blank the known wrong Cricsheet matches, then fill the known missing ones."""
    a = a.copy()
    bad = a.cricsheet_name.isin(BAD_MAP) | pd.Series(
        [(y, p) in BAD_MAP_ROWS for y, p in zip(a.auction_year, a.player)], index=a.index
    )
    a.loc[bad, "cricsheet_name"] = np.nan
    for (y, p), c in NAME_FIX.items():
        a.loc[
            (a.auction_year == y) & (a.player == p) & a.cricsheet_name.isna(), "cricsheet_name"
        ] = c
    return a


def load_auctions() -> pd.DataFrame:
    """Players put on the block (sold, or listed as on the block and unsold) with name fixes and a stable key `pid`."""
    a = fix_names(pd.read_csv(REF / "ipl_auctions.csv"))
    a = a[a.sold | (a.presented_on_block == True)].copy()  # noqa: E712 (blank = unknown, not True)
    a["pid"] = a.cricsheet_name.fillna(
        "~" + a.player.str.lower().str.replace(r"[^a-z ]", "", regex=True)
    )
    a["mega"] = a.auction_year.isin(MEGA).astype(int)
    a["total_purse"] = a.auction_year.map(total_purse)
    return a.reset_index(drop=True)


def contract_events() -> pd.DataFrame:
    """Every known price a player was paid: auction buys (order = year) and retentions (order = year - 0.5, before that auction)."""
    a = fix_names(pd.read_csv(REF / "ipl_auctions.csv"))
    a = a[a.sold]
    ev = [
        pd.DataFrame(
            {
                "pid": a.cricsheet_name.fillna(
                    "~" + a.player.str.lower().str.replace(r"[^a-z ]", "", regex=True)
                ),
                "order": a.auction_year.astype(float),
                "year": a.auction_year,
                "price": a.price_cr,
                "retained": 0,
            }
        )
    ]
    r = pd.read_csv(REF / "ipl_retentions.csv")
    r = r[~((r.cycle_year == 2022) & r.player.isin(DRAFT_2022))]
    ev.append(
        pd.DataFrame(
            {
                "pid": r.cricsheet_name.fillna(
                    "~" + r.player.str.lower().str.replace(r"[^a-z ]", "", regex=True)
                ),
                "order": r.cycle_year - 0.5,
                "year": r.cycle_year,
                "price": r.price_cr,
                "retained": 1,
            }
        )
    )
    return pd.concat(ev, ignore_index=True)


def prior_contract(pid: str, year: int, ev: pd.DataFrame):
    """(price, year of that deal, was a retention) of his latest deal that was agreed before auction `year`, or None."""
    e = ev[(ev.pid == pid) & (ev.order < year)]
    if e.empty:
        return None
    x = e.sort_values("order").iloc[-1]
    return float(x.price), int(x.year), int(x.retained)


# --------------------------------------------------------------------------------------------- features (the only DB-heavy part)
def _before(P: W.Panel, tag: str, role: str, col: str, y: int) -> pd.Series:
    cols = [c for c in P.years if c < y]
    return P.M[tag, role, col][cols].sum(axis=1)


SMAT_K = 600  # balls of shrinkage for the domestic (SMAT) rate difference; the league_translation factor is a constant scale, which the standardised ridge ignores


def smat_features(auction_date: str) -> pd.DataFrame:
    """Per player, from Syed Mushtaq Ali Trophy matches played before the auction date: shrunk batting runs-per-ball above the
    SMAT average, shrunk runs-per-ball saved by bowling, and the log of his SMAT balls. Empty if the DB has no SMAT."""
    sql = """SELECT {who} AS player, COUNT(*) AS balls, SUM({runs}) AS runs
    FROM deliveries d JOIN matches m USING (match_id)
    WHERE m.competition = 'smat' AND m.gender = 'male' AND d.innings <= 2 AND m.date < ?
      AND COALESCE(d.wides, 0) = 0 {extra} GROUP BY 1"""
    bat = query(sql.format(who="d.batter", runs="d.runs_batter", extra=""), [auction_date])
    bowl = query(sql.format(who="d.bowler", runs="d.runs_batter + COALESCE(d.noballs, 0)", extra="AND COALESCE(d.noballs, 0) = 0"), [auction_date])  # fmt: skip
    out = {}
    for name, t, sign in (("smat_bat", bat, 1), ("smat_bowl", bowl, -1)):
        if t.empty:
            out[name] = pd.Series(dtype=float)
            continue
        lg = t.runs.sum() / t.balls.sum()
        out[name] = sign * (t.runs / t.balls - lg) * t.balls / (t.balls + SMAT_K)
        out[name].index = t.player
    nb = (
        pd.concat([bat.set_index("player").balls, bowl.set_index("player").balls], axis=1)
        .fillna(0)
        .sum(axis=1)
    )
    out["smat_lb"] = np.log1p(nb)
    return pd.DataFrame(out).fillna(0.0)


def build_features(rows: dict | None = None) -> pd.DataFrame:
    """One row per player on the block, with every feature computed from data dated before that auction."""
    rows = rows or W.all_tables()[0]
    P, prm_file = W._panel(rows), W.load_params()
    war_ps = W.war_table(W.centre(rows["ipl"]), prm_file)
    ev = contract_events()
    a = load_auctions()
    out = []
    for y in YEARS:
        prm = W.fit_for(P, y)  # shrinkage constants learned on seasons < y only
        era = prm_file["era"][W.era_key(y)]
        pt = W.project_table(P, y, prm, prm_file["era"]).set_index("player")
        bat_v = (pt.bat_rate - era["repl"]["bat"]) / 100 * BAT_BALLS / era["rpw"]
        bowl_v = (pt.bowl_rate - era["repl"]["bowl"]) / 100 * BOWL_BALLS / era["rpw"]
        ipl_b = _before(P, "I", "bat", "balls", y) + _before(P, "I", "bowl", "balls", y)
        oth_b = _before(P, "O", "bat", "balls", y) + _before(P, "O", "bowl", "balls", y)
        bat_all = _before(P, "I", "bat", "balls", y) + _before(P, "O", "bat", "balls", y)
        bowl_all = _before(P, "I", "bowl", "balls", y) + _before(P, "O", "bowl", "balls", y)
        t20i = rows["t20i"]
        t20i_b = t20i[t20i.sy < y].groupby("player").balls.sum()
        w2 = war_ps[(war_ps.sy >= y - 2) & (war_ps.sy < y)].groupby("player").war.sum()
        d = a[a.auction_year == y].copy()
        sm = smat_features(str(d.auction_date.iloc[0]))
        for c in ("smat_bat", "smat_bowl", "smat_lb"):
            d[c] = d.cricsheet_name.map(sm[c]).fillna(0.0) if c in sm else 0.0
        names = d.cricsheet_name
        ok = names.isin(P.players)
        d["has_data"] = (ok & (names.map(ipl_b + oth_b).fillna(0) > 0)).astype(int)
        d["bat_val"] = names.map(bat_v).fillna(0.0) * d.has_data
        d["bowl_val"] = names.map(bowl_v).fillna(0.0) * d.has_data
        d["war2"] = names.map(w2).fillna(0.0)
        d["ipl_balls"] = names.map(ipl_b).fillna(0.0)
        d["t20_balls"] = names.map(ipl_b + oth_b).fillna(0.0)
        d["t20i_balls"] = names.map(t20i_b).fillna(0.0)
        bb, wb = names.map(bat_all).fillna(0.0), names.map(bowl_all).fillna(0.0)
        d["role_data"] = np.select([bb + wb == 0, wb < 60, bb < 60], ["unk", "bat", "bowl"], "ar")
        pr = [prior_contract(p, y, ev) for p in d.pid]
        d["prior_price"] = [x[0] if x else np.nan for x in pr]
        d["prior_year"] = [x[1] if x else np.nan for x in pr]
        d["prior_ret"] = [x[2] if x else 0 for x in pr]
        d["prior_total"] = d.prior_year.map(lambda v: total_purse(int(v)) if v == v else np.nan)
        out.append(d)
    f = pd.concat(out, ignore_index=True)
    f["role_src"] = f.role.fillna("")
    keep = [
        "auction_year", "auction_date", "player", "pid", "cricsheet_name", "country", "overseas", "capped", "role_src", "role_data",
        "base_price_cr", "sold", "price_cr", "team", "rtm", "mega", "total_purse", "has_data", "bat_val", "bowl_val",
        "war2", "smat_bat", "smat_bowl", "smat_lb", "ipl_balls", "t20_balls", "t20i_balls", "prior_price", "prior_year", "prior_ret", "prior_total",
    ]  # fmt: skip
    return f[keep]


# --------------------------------------------------------------------------------------------- design matrices
GROUPS = {  # cumulative feature sets for the ablation (S0 is the baseline everybody can know)
    "S0": [],
    "S1": ["has_prior", "log_prior", "prior_ret"],
    "S2": ["has_prior", "log_prior", "prior_ret", "has_data", "lb_ipl", "lb_t20"],
    "S3": ["has_prior", "log_prior", "prior_ret", "has_data", "lb_ipl", "lb_t20", "bat_val", "bowl_val", "war2"],
    "S4": ["has_prior", "log_prior", "prior_ret", "has_data", "lb_ipl", "lb_t20", "bat_val", "bowl_val", "war2", "smat_bat", "smat_bowl", "smat_lb"],
}  # fmt: skip
ABLATION = {
    "S0": "base, nationality, caps, role",
    "S1": "+ last price",
    "S2": "+ experience",
    "S3": "+ our WAR value",
    "S4": "+ domestic (SMAT) value",
}


def design(f: pd.DataFrame, kind: str, target: str = "A") -> tuple[pd.DataFrame, list[str]]:
    """Feature table for `kind` ('sold' or 'price') and target family ('A' = log rupees, 'B' = log share of the total purse).
    Returns (all columns, names of the S0 columns). Missing prior price = 0 with has_prior = 0."""
    x = pd.DataFrame(index=f.index)
    tot = f.total_purse
    base = f.base_price_cr
    if kind == "price" and target == "B":
        x["log_base"] = np.log(base / tot)
        x["log_prior"] = np.log(f.prior_price.fillna(1.0) / f.prior_total.fillna(1.0))
    else:
        x["log_base"] = np.log(base)
        x["log_prior"] = np.log(f.prior_price.fillna(1.0))
    x["has_prior"] = f.prior_price.notna().astype(int)
    x.loc[x.has_prior == 0, "log_prior"] = 0.0
    x["prior_ret"] = f.prior_ret.fillna(0)
    x["overseas"] = tf(f.overseas)
    x["mega"] = f.mega
    for c in ("has_data", "bat_val", "bowl_val", "war2", "smat_bat", "smat_bowl", "smat_lb"):
        x[c] = f[c]
    x["lb_ipl"], x["lb_t20"] = np.log1p(f.ipl_balls), np.log1p(f.t20_balls)
    if (
        kind == "sold"
    ):  # only data-derived caps and role, so sold and unsold rows are described the same way
        x["intl"] = (f.t20i_balls > 0).astype(int)
        for r in ("bat", "ar", "unk"):
            x[f"rd_{r}"] = (f.role_data == r).astype(int)
        s0 = ["log_base", "overseas", "intl", "rd_bat", "rd_ar", "rd_unk", "mega"]
    else:
        cap = tf(f.capped).fillna(0.0)
        x["capped"] = cap
        x["unc_indian"] = ((x.overseas == 0) & (cap == 0)).astype(int)
        role = f.role_src.where(
            f.role_src != "",
            f.role_data.map({"bat": "batter", "bowl": "bowler", "ar": "all-rounder"}),
        )
        for r, n in (("batter", "r_bat"), ("wicketkeeper", "r_wk"), ("all-rounder", "r_ar")):
            x[n] = (role == r).astype(int)
        s0 = ["log_base", "overseas", "capped", "unc_indian", "r_bat", "r_wk", "r_ar", "mega"]
        if target == "A":
            x["log_purse"] = np.log(tot)
            s0 = s0 + ["log_purse"]
    return x, s0


def cols_for(s0: list[str], group: str) -> list[str]:
    return s0 + GROUPS[group]


# --------------------------------------------------------------------------------------------- numpy ridge / logistic
class Std:
    def __init__(self, X: np.ndarray):
        self.m, self.s = X.mean(0), X.std(0)
        self.s[self.s < 1e-9] = 1.0

    def __call__(self, X):
        return (X - self.m) / self.s


def ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    sd = Std(X)
    Z = sd(X)
    ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return {"beta": beta, "b0": ym, "m": sd.m, "s": sd.s}


def lin_predict(M: dict, X: np.ndarray) -> np.ndarray:
    return M["b0"] + ((X - M["m"]) / M["s"]) @ M["beta"]


def logit_fit(X: np.ndarray, y: np.ndarray, lam: float, iters: int = 50) -> dict:
    sd = Std(X)
    Z = np.column_stack([np.ones(len(X)), sd(X)])
    pen = lam * np.eye(Z.shape[1])
    pen[0, 0] = 0.0
    b = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ b, -30, 30)))
        g = Z.T @ (p - y) + pen @ b
        H = (Z * (p * (1 - p))[:, None]).T @ Z + pen + 1e-8 * np.eye(Z.shape[1])
        step = np.linalg.solve(H, g)
        b = b - step
        if np.abs(step).max() < 1e-8:
            break
    return {"beta": b[1:], "b0": b[0], "m": sd.m, "s": sd.s}


def logit_predict(M: dict, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(M["b0"] + ((X - M["m"]) / M["s"]) @ M["beta"], -30, 30)))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    r = pd.Series(p).rank().values
    n1, n0 = y.sum(), len(y) - y.sum()
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) if n1 and n0 else float("nan")


def spearman(a, b) -> float:
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


# --------------------------------------------------------------------------------------------- fitting with leave-one-auction-out
def loao(fit, pred, X: np.ndarray, y: np.ndarray, yr: np.ndarray, hp: float) -> np.ndarray:
    """Out-of-fold predictions: each auction year predicted by a model fitted on the other years."""
    o = np.zeros(len(y))
    for v in np.unique(yr):
        m = yr == v
        o[m] = pred(fit(X[~m], y[~m], hp), X[m])
    return o


def choose_hp(fit, pred, loss, X, y, yr) -> float:
    return min(ALPHAS, key=lambda h: loss(y, loao(fit, pred, X, y, yr, h)))


def _ll(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def _mae(y, p):
    return float(np.abs(y - p).mean())


def price_target(f: pd.DataFrame, target: str) -> np.ndarray:
    return np.log(f.price_cr / (f.total_purse if target == "B" else 1.0)).values


def to_cr(f: pd.DataFrame, z: np.ndarray, target: str) -> np.ndarray:
    return np.exp(z) * (f.total_purse.values if target == "B" else 1.0)


class Hurdle:
    """Fitted two-part model for one (target, feature group, training years)."""

    def __init__(self, f: pd.DataFrame, years, target="A", group="S4", sold_group=None):
        self.target, self.group, self.years = target, group, tuple(years)
        self.sold_group = sold_group or group
        tr = f[f.auction_year.isin(years)]
        # price part: sold rows
        sp = tr[tr.sold]
        Xp, s0p = design(sp, "price", target)
        self.pcols = cols_for(s0p, group)
        Xa, ya, yr = (
            Xp[self.pcols].values.astype(float),
            price_target(sp, target),
            sp.auction_year.values,
        )
        self.alpha = choose_hp(ridge_fit, lin_predict, _mae, Xa, ya, yr)
        self.price = ridge_fit(Xa, ya, self.alpha)
        res = ya - loao(ridge_fit, lin_predict, Xa, ya, yr, self.alpha)  # honest residuals
        self.q = {
            k: float(np.quantile(res, v)) for k, v in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9))
        }
        self.resid_sd = float(res.std())
        # sold part: every row with a known nationality
        ss = tr[tr.overseas.notna()]
        Xs, s0s = design(ss, "sold")
        self.scols = cols_for(s0s, self.sold_group)
        Xb, yb = Xs[self.scols].values.astype(float), ss.sold.astype(float).values
        self.lam = choose_hp(logit_fit, logit_predict, _ll, Xb, yb, ss.auction_year.values)
        self.sold = logit_fit(Xb, yb, self.lam)

    def predict(self, f: pd.DataFrame) -> pd.DataFrame:
        """p_sold, p10 / p50 / p90 price in crore (never below the base price) for each row."""
        f = f.assign(
            overseas=tf(f.overseas).fillna(0)
        )  # unknown nationality (some unsold rows) counts as Indian
        out = pd.DataFrame(index=f.index)
        Xp, _ = design(f, "price", self.target)
        z = lin_predict(self.price, Xp[self.pcols].values.astype(float))
        base = f.base_price_cr.values
        for k, q in self.q.items():
            out[k] = np.maximum(to_cr(f, z + q, self.target), base)
        Xs, _ = design(f.assign(overseas=tf(f.overseas).fillna(0)), "sold")
        out["p_sold"] = logit_predict(self.sold, Xs[self.scols].values.astype(float))
        return out

    def contributions(self, f: pd.DataFrame) -> pd.DataFrame:
        """Each price feature's push on the predicted log price (beta x standardised value), for 'why' text."""
        Xp, _ = design(f, "price", self.target)
        Z = (
            (Xp[self.pcols].values.astype(float) - self.price["m"])
            / self.price["s"]
            * self.price["beta"]
        )
        return pd.DataFrame(Z, index=f.index, columns=self.pcols)

    def to_json(self) -> dict:
        def j(M, cols):
            return {"cols": cols, "b0": float(M["b0"]), "beta": [float(v) for v in M["beta"]], "m": [float(v) for v in M["m"]], "s": [float(v) for v in M["s"]]}  # fmt: skip

        return {"target": self.target, "group": self.group, "sold_group": self.sold_group, "train_years": list(self.years), "alpha": self.alpha, "lambda": self.lam, "quantiles_log": self.q, "resid_sd": self.resid_sd, "price": j(self.price, self.pcols), "sold": j(self.sold, self.scols)}  # fmt: skip


# --------------------------------------------------------------------------------------------- evaluation
def price_metrics(f: pd.DataFrame, p50, p10=None, p90=None) -> dict:
    s = f[f.sold]
    pr = pd.Series(p50, index=f.index)[s.index].values
    act = s.price_cr.values
    out = {
        "n": len(s),
        "MAE_cr": float(np.abs(pr - act).mean()),
        "medAPE_%": float(100 * np.median(np.abs(pr - act) / act)),
        "R2_log": float(1 - ((np.log(act) - np.log(pr)) ** 2).sum() / ((np.log(act) - np.log(act).mean()) ** 2).sum()),
        "spearman": spearman(pr, act),
    }  # fmt: skip
    if p10 is not None:
        lo, hi = (
            pd.Series(p10, index=f.index)[s.index].values,
            pd.Series(p90, index=f.index)[s.index].values,
        )
        out["cover_80"] = float(((act >= lo - 1e-9) & (act <= hi + 1e-9)).mean())
    return out


def sold_metrics(f: pd.DataFrame, p) -> dict:
    y = f.sold.astype(float).values
    return {"n": len(f), "sold_%": float(100 * y.mean()), "AUC": auc(y, np.asarray(p)), "Brier": float(((np.asarray(p) - y) ** 2).mean())}  # fmt: skip


def baselines(f_train: pd.DataFrame, f_eval: pd.DataFrame, target: str = "A") -> dict:
    """price = base; price = last price (rows with one); OLS on base + caps + nationality + role; sold-rate and base-only logistic."""
    out = {"base": price_metrics(f_eval, f_eval.base_price_cr.values)}
    has = f_eval.prior_price.notna()
    sub = f_eval[has]
    if sub.sold.sum() > 2:
        out["last_price"] = price_metrics(
            sub, np.maximum(sub.prior_price.values, sub.base_price_cr.values)
        )
        out["base_same_rows"] = price_metrics(sub, sub.base_price_cr.values)
    tr = f_train[f_train.sold]
    X, s0 = design(tr, "price", target)
    M = ridge_fit(X[s0].values.astype(float), price_target(tr, target), 1e-6)
    Xe, _ = design(f_eval, "price", target)
    out["ols_core"] = price_metrics(f_eval, np.maximum(to_cr(f_eval, lin_predict(M, Xe[s0].values.astype(float)), target), f_eval.base_price_cr.values))  # fmt: skip
    out["_sold_rate"] = sold_metrics(f_eval, np.full(len(f_eval), f_train.sold.mean()))
    return out


def evaluate(
    f: pd.DataFrame, train_years, eval_year, target="A", group="S4", sold_group=None
) -> dict:
    """Fit on train_years, score eval_year. Returns metrics for the hurdle model, the ablation ladder and the baselines."""
    tr, ev = f[f.auction_year.isin(train_years)], f[f.auction_year == eval_year]
    ev = ev[ev.overseas.notna() | ev.sold]
    H = Hurdle(f, train_years, target, group, sold_group)
    pr = H.predict(ev)
    res = {
        "model": {**price_metrics(ev, pr.p50, pr.p10, pr.p90), **{"sold_" + k: v for k, v in sold_metrics(ev, pr.p_sold).items() if k in ("AUC", "Brier")}},
        "alpha": H.alpha, "lambda": H.lam,
    }  # fmt: skip
    res["baselines"] = baselines(tr, ev, target)
    if "last_price" in res["baselines"]:
        sub = ev[ev.prior_price.notna()]
        res["model_on_last_price_rows"] = price_metrics(sub, pr.p50[sub.index])
    abl = {}
    for g in GROUPS:
        h = Hurdle(f, train_years, target, g)
        p = h.predict(ev)
        abl[g] = {**price_metrics(ev, p.p50, p.p10, p.p90), **{"sold_" + k: v for k, v in sold_metrics(ev, p.p_sold).items() if k in ("AUC", "Brier")}}  # fmt: skip
    res["ablation"] = abl
    return res


def predictions(
    f: pd.DataFrame, target: str, group: str, sold_group: str | None = None
) -> tuple[pd.DataFrame, "Hurdle"]:
    """Out-of-sample predictions for every row: 2022-24 leave-one-auction-out within the training years ('oof'),
    2025 from the 2022-24 fit ('validation'), 2026 from the 2022-25 fit ('test'). Also returns the final (2022-25) model."""
    parts = []
    for y in TRAIN:
        H = Hurdle(f, [t for t in TRAIN if t != y], target, group, sold_group)
        d = f[f.auction_year == y]
        parts.append(H.predict(d).assign(pred_kind="oof"))
    Hv = Hurdle(f, TRAIN, target, group, sold_group)
    parts.append(Hv.predict(f[f.auction_year == VAL]).assign(pred_kind="validation"))
    Hf = Hurdle(f, TRAIN + (VAL,), target, group, sold_group)
    parts.append(Hf.predict(f[f.auction_year == TEST]).assign(pred_kind="test"))
    return pd.concat(parts).sort_index(), Hf


NAMES = {"log_base": "base price", "overseas": "overseas", "capped": "capped", "unc_indian": "Indian uncapped", "r_bat": "batter", "r_wk": "keeper", "r_ar": "all-rounder", "mega": "mega auction", "log_purse": "purse", "has_prior": "has last price", "log_prior": "last price", "prior_ret": "was retained", "has_data": "has T20 data", "lb_ipl": "IPL experience", "lb_t20": "T20 experience", "bat_val": "batting value", "bowl_val": "bowling value", "war2": "recent WAR", "smat_bat": "SMAT batting", "smat_bowl": "SMAT bowling", "smat_lb": "SMAT balls"}  # fmt: skip


def lean_text(c: pd.Series) -> str:
    """The three features that push the predicted log price most (up or down), e.g. 'base price -1.04, overseas +0.20'."""
    r = c.drop(["mega", "log_purse"], errors="ignore")
    top = r.reindex(r.abs().sort_values(ascending=False).index)[:3]
    return ", ".join(f"{NAMES.get(k, k)} {v:+.2f}" for k, v in top.items())


def contributions_from_json(f: pd.DataFrame, mj: dict) -> pd.DataFrame:
    """Same as Hurdle.contributions, from the saved final_model block (so the module needs no refit)."""
    X, _ = design(f, "price", mj["target"])
    p = mj["price"]
    Z = (
        (X[p["cols"]].values.astype(float) - np.array(p["m"]))
        / np.array(p["s"])
        * np.array(p["beta"])
    )
    return pd.DataFrame(Z, index=f.index, columns=p["cols"])


def top_misses(
    f: pd.DataFrame, pred: pd.DataFrame, H: "Hurdle", year: int, n: int = 15
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sold players whose price was most above (market paid more) / below (market paid less) the model's median, by ratio."""
    m = f[(f.auction_year == year) & f.sold]
    c = H.contributions(m)
    d = m[
        [
            "player",
            "role_src",
            "overseas",
            "capped",
            "base_price_cr",
            "price_cr",
            "team",
            "prior_price",
            "war2",
            "bat_val",
            "bowl_val",
        ]
    ].copy()
    d["model_p50_cr"], d["model_p10_cr"], d["model_p90_cr"] = (
        pred.p50[m.index],
        pred.p10[m.index],
        pred.p90[m.index],
    )
    d["paid_vs_model"] = d.price_cr / d.model_p50_cr
    d["model_leans_on"] = [lean_text(c.loc[i]) for i in d.index]
    d = d.sort_values("paid_vs_model")
    return d.tail(n)[::-1].reset_index(drop=True), d.head(n).reset_index(drop=True)


# --------------------------------------------------------------------------------------------- M5: market check
def build_market(rows: dict | None = None) -> pd.DataFrame:
    """Every player bought at 2022-2026 auctions or retained in the 2022 and 2025 cycles, with his WAR in that IPL season."""
    rows = rows or W.all_tables()[0]
    war_ps = W.war_table(W.centre(rows["ipl"]), W.load_params())
    played = war_ps.set_index(["player", "sy"])
    t20i = rows["t20i"]
    a = fix_names(pd.read_csv(REF / "ipl_auctions.csv"))
    a = a[a.sold]
    b = pd.DataFrame({"year": a.auction_year, "player": a.player, "cs": a.cricsheet_name, "price": a.price_cr, "overseas": a.overseas.astype(bool), "capped": a.capped, "role": a.role, "source": "auction", "team": a.team})  # fmt: skip
    r = pd.read_csv(REF / "ipl_retentions.csv")
    r = r[r.cycle_year.isin((2022, 2025)) & ~((r.cycle_year == 2022) & r.player.isin(DRAFT_2022))]
    br = pd.DataFrame({"year": r.cycle_year, "player": r.player, "cs": r.cricsheet_name, "price": r.price_cr, "overseas": r.overseas.astype(bool), "capped": np.nan, "role": None, "source": "retained", "team": r.team})  # fmt: skip
    b = pd.concat([b, br], ignore_index=True)
    key = list(zip(b.cs, b.year))
    b["war"] = [float(played.war.get(k, 0.0)) if isinstance(k[0], str) else 0.0 for k in key]
    b["balls"] = [float(played.bat_balls.get(k, 0.0) + played.bowl_balls.get(k, 0.0)) if isinstance(k[0], str) else 0.0 for k in key]  # fmt: skip
    b["mapped"] = b.cs.notna()
    cap = tf(b.capped)
    first = t20i.groupby(
        "player"
    ).sy.min()  # proxy where the source has no caps flag: any T20I before the season
    proxy = [
        bool(first.get(c, 9999) < y) if isinstance(c, str) else False for c, y in zip(b.cs, b.year)
    ]
    b["capped_b"] = cap.fillna(pd.Series(proxy, index=b.index).astype(float)).astype(bool)
    b["type"] = np.where(
        b.overseas, "overseas", np.where(b.capped_b, "capped Indian", "uncapped Indian")
    )
    b["band"] = pd.cut(
        b.price, [0, 0.5, 2, 8, 100], labels=["to 0.5 cr", "0.5-2 cr", "2-8 cr", "over 8 cr"]
    ).astype(str)
    b["kind"] = np.where(
        b.source == "retained",
        "retained",
        np.where(b.year.isin(MEGA), "mega auction", "mini auction"),
    )
    b["role"] = b.role.fillna("unknown")
    return b


def bootstrap_ratio(
    war: np.ndarray, cr: np.ndarray, draws: int = 4000, seed: int = 11
) -> tuple[float, float, float]:
    """WAR per 10 crore as sum of WAR / sum of crore x 10, with a 95% bootstrap range over players."""
    rng = np.random.default_rng(seed)
    n = len(war)
    idx = rng.integers(0, n, (draws, n))
    s = war[idx].sum(1) / cr[idx].sum(1) * 10
    return (
        float(war.sum() / cr.sum() * 10),
        float(np.quantile(s, 0.025)),
        float(np.quantile(s, 0.975)),
    )


def market_table(
    b: pd.DataFrame, by, years=(2022, 2023, 2024, 2025), min_n: int = 20
) -> pd.DataFrame:
    """WAR per 10 crore by group (ratio of sums), mean surplus per player (WAR minus price / pooled crore-per-win), ranges, flags."""
    b = b[b.year.isin(years)]
    cr_per_win = b.price.sum() / b.war.sum() if b.war.sum() > 0 else np.nan
    rows = []
    for k, g in b.groupby(by):
        w, c = g.war.values, g.price.values
        est, lo, hi = bootstrap_ratio(w, c)
        sur = w - c / cr_per_win
        rng = np.random.default_rng(5)
        ms = [sur[rng.integers(0, len(sur), len(sur))].mean() for _ in range(2000)]
        rows.append(
            {
                "group": k if isinstance(k, str) else " | ".join(map(str, k)),
                "players": len(g), "crore_spent": round(c.sum(), 1), "war_total": round(w.sum(), 2),
                "war_per_10cr": round(est, 3), "lo": round(lo, 3), "hi": round(hi, 3),
                "mean_war_per_player": round(w.mean(), 3), "mean_surplus": round(sur.mean(), 3),
                "surplus_lo": round(float(np.quantile(ms, 0.025)), 3), "surplus_hi": round(float(np.quantile(ms, 0.975)), 3),
                "played_%": round(100 * (g.balls > 0).mean(), 0),
                "small_sample": len(g) < min_n,
            }
        )  # fmt: skip
    out = pd.DataFrame(rows)
    out.attrs["cr_per_win"] = cr_per_win
    return out


def diff_unc_vs_rest(
    b: pd.DataFrame, years=(2022, 2023, 2024, 2025), band: str | None = None, draws: int = 4000
) -> dict:
    """Bootstrap of (uncapped Indian WAR per 10 cr) minus (everybody else's), optionally inside one price band."""
    b = b[b.year.isin(years)]
    if band:
        b = b[b.band == band]
    u, o = b[b.type == "uncapped Indian"], b[b.type != "uncapped Indian"]
    rng = np.random.default_rng(3)
    d = []
    for _ in range(draws):
        iu, io = rng.integers(0, len(u), len(u)), rng.integers(0, len(o), len(o))
        d.append(u.war.values[iu].sum() / u.price.values[iu].sum() * 10 - o.war.values[io].sum() / o.price.values[io].sum() * 10)  # fmt: skip
    est = u.war.sum() / u.price.sum() * 10 - o.war.sum() / o.price.sum() * 10
    return {"n_unc": len(u), "n_rest": len(o), "diff": float(est), "lo": float(np.quantile(d, 0.025)), "hi": float(np.quantile(d, 0.975)), "p_positive": float(np.mean(np.array(d) > 0))}  # fmt: skip


# --------------------------------------------------------------------------------------------- saved-output readers
def load_model() -> dict:
    return json.loads(MODEL.read_text())


def load_predictions() -> pd.DataFrame:
    return pd.read_csv(PREDS)


def load_market() -> pd.DataFrame:
    return pd.read_csv(MARKET)


# --------------------------------------------------------------------------------------------- rebuild
def pick(f: pd.DataFrame, target: str, group: str | None = None) -> tuple[str, dict]:
    """Choose the feature group by validation MAE (price). A bigger group must beat the smaller one by 1% to be taken."""
    ev = evaluate(f, TRAIN, VAL, target, "S4")
    best, bm = "S0", ev["ablation"]["S0"]["MAE_cr"]
    for g in ("S1", "S2", "S3", "S4"):
        if ev["ablation"][g]["MAE_cr"] < bm * 0.99:
            best, bm = g, ev["ablation"][g]["MAE_cr"]
    return group or best, ev


def main() -> None:
    f = build_features()
    f.to_csv(FEATURES, index=False)
    print(f.groupby("auction_year").agg(n=("sold", "size"), sold=("sold", "sum"), has_data=("has_data", "sum"), has_prior=("prior_price", lambda s: s.notna().sum())))  # fmt: skip
    summary = {"validation": {}}
    chosen = {}
    for target in ("A", "B"):
        g, ev = pick(f, target)
        summary["validation"][target] = {"group_chosen": g, **ev}
        chosen[target] = g
    # target choice: lower validation MAE in crore (ties -> A)
    tgt = min(("A", "B"), key=lambda t: summary["validation"][t]["model"]["MAE_cr"])
    grp = chosen[tgt]
    summary.update(target=tgt, group=grp)
    test = evaluate(f, TRAIN + (VAL,), TEST, tgt, grp)
    test_other = {t: evaluate(f, TRAIN + (VAL,), TEST, t, chosen[t])["model"] for t in ("A", "B")}
    summary["test"], summary["test_both_targets"] = test, test_other
    pred, Hf = predictions(f, tgt, grp)
    out = f.join(pred)
    out.to_csv(PREDS, index=False)
    over, under = top_misses(f, pred, Hf, TEST)
    summary["test_over_paid"], summary["test_under_paid"] = (
        over.round(3).to_dict("records"),
        under.round(3).to_dict("records"),
    )
    summary["final_model"] = Hf.to_json()
    mk = build_market()
    mk.to_csv(MARKET, index=False)
    summary["market_unc_vs_rest"] = {"all": diff_unc_vs_rest(mk), **{bnd: diff_unc_vs_rest(mk, band=bnd) for bnd in ("to 0.5 cr", "0.5-2 cr", "2-8 cr")}}  # fmt: skip
    MODEL.write_text(json.dumps(summary, indent=1, default=float))
    print(
        json.dumps({k: summary[k] for k in ("target", "group")}),
        json.dumps(summary["test"]["model"]),
    )


if __name__ == "__main__":
    main()
