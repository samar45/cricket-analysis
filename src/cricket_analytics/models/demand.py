"""M14: does auction price depend on DEMAND (which teams need the player and can pay)? Method and numbers: docs/VALUE_demand.md.

Replays each auction 2022-26 lot by lot (order = lot_no of the sold players) from the pre-auction squads (models/scarcity.py),
tracking per team the purse, squad places, overseas places and role holes. Demand features of a lot use only lots BEFORE it.
Then adds them to the shipped auction hurdle model (S1, target B) and compares out of sample. Nothing here changes
auction.py defaults.   Rebuild (a few seconds, read-only):  python -m cricket_analytics.models.demand
"""

import json

import numpy as np
import pandas as pd

from . import auction as A
from . import scarcity as S

DATA = A.DATA
FEAT_CSV, RESULT_JSON = DATA / "demand_features.csv", DATA / "demand_results.json"
MIN_SQUAD, MIN_COST = 18, 0.2  # IPL minimum squad; cheapest possible buy (cr)
QUOTA = pd.Series([r for _, r in S.SLOTS]).value_counts().to_dict()  # best-XII places per role
DEMAND = ["n_need", "n_afford", "n_hole", "lmax_spare", "lsecond_spare", "pos", "early", "no_role"]
SUBSET = ["n_need", "lmax_spare", "pos"]  # the small version tested next to the full set


def _lots(year: int) -> pd.DataFrame:
    """Players on the block with lot order. Sold lots have lot_no; unsold ones get a position from their set (2026) or base-price tier."""
    f = pd.read_csv(A.FEATURES)
    f = f[f.auction_year == year].copy()
    raw = pd.read_csv(A.REF / "ipl_auctions.csv")
    raw = raw[raw.auction_year == year].drop_duplicates("player")[["player", "set_no", "lot_no"]]
    f = f.merge(raw, on="player", how="left")
    f["sold"] = f.sold.astype(bool)
    f["set_no"] = pd.to_numeric(f.set_no, errors="coerce")
    # two sold 2025 lots lack lot_no: put them after the last lot of their set
    f["lot_no"] = f.lot_no.fillna(f.groupby("set_no").lot_no.transform("max") + 0.5)
    return f


def replay(year: int) -> pd.DataFrame:
    f = _lots(year)
    sq = S.squads_before()[year]
    feat = S.features(year)
    teams = sorted(set(sq.team) | set(f.team.dropna()))
    ti = {t: i for i, t in enumerate(teams)}
    W = {r: feat[f"w_{r}"] for r in S.ROLES}

    def can(key):  # roles the player can fill
        return [r for r in S.ROLES if key in feat.index and W[r].get(key, 0) >= S.CAN_FILL]

    purse = np.full(len(teams), float(S.PURSE[year]))
    size, ovs = np.zeros(len(teams)), np.zeros(len(teams))
    cnt = {r: np.zeros(len(teams)) for r in S.ROLES}
    for _, s in sq.iterrows():
        i = ti[s.team]
        purse[i] -= s.price_cr
        size[i] += 1
        ovs[i] += bool(s.overseas)
        for r in can(s.key):
            cnt[r][i] += 1
    purse = purse.clip(min=0)

    sold = f[f.sold].sort_values("lot_no").reset_index(drop=True)
    N = len(sold)
    snaps = []  # state before sold lot k (k = 0..N)
    for k in range(N + 1):
        snaps.append((purse.copy(), size.copy(), ovs.copy(), {r: c.copy() for r, c in cnt.items()}))
        if k == N:
            break
        s = sold.iloc[k]
        if s.team not in ti:
            continue
        i = ti[s.team]
        purse[i] = max(0.0, purse[i] - s.price_cr)
        size[i] += 1
        ovs[i] += bool(s.overseas)
        for r in can(s.pid):
            cnt[r][i] += 1

    # position k of each row: exact for sold rows; set median (2026) or base-tier median for unsold
    kpos = {sold.player[k]: k for k in range(N)}
    def guess(row):
        s = sold[sold.set_no == row.set_no] if pd.notna(row.set_no) else sold.iloc[0:0]
        if len(s) == 0:
            s = sold[(sold.base_price_cr - row.base_price_cr).abs() < 1e-9]
        return int(np.median(s.index)) if len(s) else N // 2

    rows = []
    for _, r in f.iterrows():
        k = kpos[r.player] if r.sold else guess(r)
        pu, sz, ov, ct = snaps[k]
        spare = pu - MIN_COST * np.maximum(0, MIN_SQUAD - 1 - sz)
        ok = (sz < S.SQUAD_MAX) & (spare >= r.base_price_cr - 1e-9)
        if bool(r.overseas) if pd.notna(r.overseas) else False:
            ok &= ov < S.OVERSEAS_MAX
        roles = can(r.pid)
        hole = np.zeros(len(teams), bool)
        for ro in roles:
            hole |= ct[ro] < QUOTA[ro]
        need = ok & hole
        sp = np.sort(spare[need])[::-1] if need.any() else np.array([0.0, 0.0])
        sp = np.append(sp, 0.0)
        tot = A.total_purse(year)
        rows.append({"auction_year": year, "player": r.player, "n_afford": int(ok.sum()), "n_need": int(need.sum()),
                     "n_hole": int(hole.sum()), "lmax_spare": np.log1p(sp[0] / tot * 100), "lsecond_spare": np.log1p(sp[1] / tot * 100),
                     "pos": k / max(N, 1), "early": int(k < 0.1 * N), "no_role": int(not roles), "pos_exact": bool(r.sold)})  # fmt: skip
    return pd.DataFrame(rows)


def build(write: bool = True) -> pd.DataFrame:
    f = pd.read_csv(A.FEATURES)
    d = pd.concat([replay(y) for y in A.YEARS])
    f = f.merge(d, on=["auction_year", "player"], how="left")
    if write:
        f.to_csv(FEAT_CSV, index=False)
    return f


# ---------------------------------------------------------------------------------------------- model
def _fit_predict(f, train_years, ev_year, extra: list[str]):
    """The shipped hurdle (S1, target B) plus `extra` columns in both parts. extra=[] reproduces the shipped model."""
    tr, ev = f[f.auction_year.isin(train_years)], f[f.auction_year == ev_year]
    ev = ev[ev.overseas.notna() | ev.sold]
    ev = ev.assign(overseas=A.tf(ev.overseas).fillna(0))

    def X(d, kind):
        x, s0 = A.design(d, kind, "B")
        return x[A.cols_for(s0, "S1")].assign(**{c: d[c].astype(float) for c in extra}).values.astype(float)

    sp = tr[tr.sold]
    Xa, ya, yr = X(sp, "price"), A.price_target(sp, "B"), sp.auction_year.values
    al = A.choose_hp(A.ridge_fit, A.lin_predict, A._mae, Xa, ya, yr)
    M = A.ridge_fit(Xa, ya, al)
    q50 = float(np.median(ya - A.loao(A.ridge_fit, A.lin_predict, Xa, ya, yr, al)))
    ss = tr[tr.overseas.notna()]
    Xs, ys = X(ss, "sold"), ss.sold.astype(float).values
    lam = A.choose_hp(A.logit_fit, A.logit_predict, A._ll, Xs, ys, ss.auction_year.values)
    L = A.logit_fit(Xs, ys, lam)
    p50 = np.maximum(A.to_cr(ev, A.lin_predict(M, X(ev, "price")) + q50, "B"), ev.base_price_cr.values)
    return ev.assign(p50=p50, p_sold=A.logit_predict(L, X(ev, "sold")))


def compare(f) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Folds: 2024 (train 2022-23), 2025 validation (train 2022-24), 2026 test (train 2022-25)."""
    out, errs = [], []
    for ev_year in (2024, 2025, 2026):
        tr = tuple(range(2022, ev_year))
        for name, extra in (("shipped S1", []), ("S1 + demand (small)", SUBSET), ("S1 + demand (all)", DEMAND)):
            p = _fit_predict(f, tr, ev_year, extra)
            s = p[p.sold]
            out.append({"year": ev_year, "model": name, "MAE_cr": np.abs(s.p50 - s.price_cr).mean(), "sold_AUC": A.auc(p.sold.astype(float).values, p.p_sold.values), "n_sold": len(s), "n": len(p)})  # fmt: skip
            errs.append(pd.DataFrame({"year": ev_year, "model": name, "player": s.player, "err": np.abs(s.p50 - s.price_cr)}))
        b = p[p.sold]
        out.append({"year": ev_year, "model": "price = base", "MAE_cr": np.abs(b.base_price_cr - b.price_cr).mean(), "sold_AUC": np.nan, "n_sold": len(b), "n": len(p)})  # fmt: skip
    return pd.DataFrame(out), pd.concat(errs)


def paired(errs: pd.DataFrame, model: str, draws: int = 2000, seed: int = 0) -> dict:
    """Mean (shipped - model) absolute error over all three folds' sold players, bootstrap over players. Positive = demand model better."""
    e = errs.pivot_table(index=["year", "player"], columns="model", values="err")
    d = (e["shipped S1"] - e[model]).values
    rng = np.random.default_rng(seed)
    bs = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(draws)]
    return {"model": model, "n": len(d), "mean_gain_cr": float(d.mean()), "lo90": float(np.quantile(bs, 0.05)), "hi90": float(np.quantile(bs, 0.95))}  # fmt: skip


# ---------------------------------------------------------------------------------------------- bidding-war check
def war_table(f: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Sold players: price / base against the number of teams with need and money. Also an OLS slope with base-tier and year controls."""
    s = f[f.sold & (f.base_price_cr > 0)].copy()
    s["ratio"] = s.price_cr / s.base_price_cr
    s["bin"] = pd.cut(s.n_need, [-1, 0, 2, 4, 6, 10], labels=["0", "1-2", "3-4", "5-6", "7+"])
    t = s.groupby("bin", observed=True).agg(players=("ratio", "size"), mean_ratio=("ratio", "mean"), median_ratio=("ratio", "median"),
                                             above_base=("ratio", lambda r: (r > 1.001).mean())).round(3)  # fmt: skip
    y = np.log(s.ratio).values
    tier = pd.get_dummies(pd.cut(s.base_price_cr, [0, 0.25, 0.5, 1, 1.5, 2.5, 5]), dtype=float)
    yr = pd.get_dummies(s.auction_year, dtype=float)
    def slope(extra):
        X = np.column_stack([np.ones(len(s)), s.n_need.values, tier.values[:, 1:], yr.values[:, 1:], *extra])
        b = np.linalg.lstsq(X, y, rcond=None)[0][1]
        rng, bs = np.random.default_rng(1), []
        for _ in range(1000):
            i = rng.integers(0, len(y), len(y))
            bs.append(np.linalg.lstsq(X[i], y[i], rcond=None)[0][1])
        return float(b), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))

    a, b = slope([]), slope([s.pos.values, s.overseas.astype(float).values, s.capped.astype(float).fillna(0).values])
    return t, {"n": len(s), "slope_base_year_controls": a, "slope_plus_position_overseas_capped": b,
               "spearman_need_ratio": A.spearman(s.n_need, s.ratio), "spearman_pos_need": A.spearman(s.pos, s.n_need)}  # fmt: skip


def main() -> None:
    f = build()
    res, errs = compare(f)
    t, slope = war_table(f)
    print(res.round(3).to_string(index=False))
    print(t)
    print(slope)
    gains = [paired(errs, m) for m in ("S1 + demand (small)", "S1 + demand (all)")]
    print(gains)
    RESULT_JSON.write_text(json.dumps({"folds": res.round(4).to_dict("records"), "paired": gains, "war_table": t.reset_index().astype({"bin": str}).to_dict("records"), "war_slope": slope}, indent=1, default=float))  # fmt: skip


if __name__ == "__main__":
    main()
