"""Buying-strategy simulation on the 2023-26 IPL auctions (docs/VALUE_moneyball_v2.md, M13).

For auction year Y the buyer only sees leagues up to calendar year Y-1 (the backtest cut; the Dec auctions come after them).
Each team gets the same budget, overseas cap and squad-slot cap as its actual buys; the rule picks from the whole auction pool
(sold at the actual price, unsold at the base price). Teams are simulated independently (two rule buyers may pick the same
player: this is "what if I had bought him at his price", not a full auction). Value = IPL season Y runs above replacement (runs added minus the era's replacement level x balls, bat + bowl,
0 if he did not play) summed over the buys; compared per crore. Random baseline = same teams, same caps, random first-fit.
Run: python -m cricket_analytics.models.strategy
"""

import numpy as np
import pandas as pd

from . import backtest as B
from . import war as W

YEARS = (2023, 2024, 2025, 2026)


def pool(A: pd.DataFrame, Y: int) -> pd.DataFrame:
    """Auction players of year Y matched to a Cricsheet name: name, team, overseas, sold, cost (price if sold else base)."""
    a = A[(A.auction_year == Y) & A.cricsheet_name.notna()].drop_duplicates("cricsheet_name").copy()
    a["cost"] = np.where(a.sold, a.price_cr, a.base_price_cr)
    return a.rename(columns={"cricsheet_name": "name"})[["name", "team", "overseas", "sold", "cost", "role"]].reset_index(drop=True)


def pick(df: pd.DataFrame, order, budget: float, n_max: int, os_max: int) -> list[int]:
    """Row positions taken in `order` while cost <= budget left, picks < n_max and overseas picks < os_max (first fit)."""
    got, left, nos = [], budget, 0
    for i in order:
        c, o = df.cost.iat[i], bool(df.overseas.iat[i])
        if len(got) >= n_max:
            break
        if c <= left + 1e-9 and (not o or nos < os_max):
            got.append(i)
            left -= c
            nos += o
    return got


def team_caps(A: pd.DataFrame, Y: int) -> pd.DataFrame:
    """Per team: spend, number of players, overseas count of its actual auction buys in year Y (all sold rows, matched or not)."""
    s = A[(A.auction_year == Y) & A.sold]
    return s.groupby("team").agg(budget=("price_cr", "sum"), n=("player", "size"), os=("overseas", "sum"))


def repl_per_ball(Y: int) -> dict:
    """Replacement level (runs added per ball) by role in the era of season Y (war.py's fitted parameters)."""
    e = W.load_params()["era"][W.era_key(Y)]["repl"]
    return {r: e[r] / 100 for r in ("bat", "bowl")}


def rar(df: pd.DataFrame, Y: int) -> pd.Series:
    """Runs above replacement from a frame with bat, bowl (runs added) and bat_balls, bowl_balls."""
    rp = repl_per_ball(Y)
    return sum(df[r].fillna(0.0) - rp[r] * df[f"{r}_balls"].fillna(0.0) for r in ("bat", "bowl"))


def predicted_value(T, X, ctx) -> pd.Series:
    """Predicted IPL runs above replacement: marcel_ipl for players with IPL history, the all-league marcel for the others."""
    tot = lambda f: rar(f, X + 1)[f[["bat", "bowl"]].notna().any(axis=1)]  # noqa: E731
    a, b = tot(B.PREDICTORS["marcel_ipl"][0](T, X, ctx)), tot(B.PREDICTORS["marcel"][0](T, X, ctx))
    return a.combine_first(b).dropna()


def simulate(T=None, A=None, years=YEARS, draws: int = 1000, seed: int = 7) -> dict:
    """Returns dict(rows = per year x method table, dist = random-draw ratios per random kind, totals = pooled summary)."""
    T = B.tables() if T is None else T
    A = B.auctions() if A is None else A
    rng = np.random.default_rng(seed)
    meths = ("actual", "rule_vpc", "rule_top")
    runs = {m: 0.0 for m in meths}
    spend = {m: 0.0 for m in meths}
    rand = {k: np.zeros((draws, 2)) for k in ("all", "predictable")}  # sum runs, sum cost over years
    rows = []
    for Y in years:
        pr = predicted_value(T[T.sy <= Y - 1], Y - 1, dict(auctions=A))
        tr = B.truth_runs(T, Y)
        val = rar(tr, Y)
        P = pool(A, Y)
        P["pred"] = P.name.map(pr)
        P["real"] = P.name.map(val).fillna(0.0)
        caps = team_caps(A, Y)
        sold_all = A[(A.auction_year == Y) & A.sold]
        cand = P[P.pred > 0]
        for tm, c in caps.iterrows():
            acts = sold_all[sold_all.team == tm]
            m = P[(P.team == tm) & P.sold]  # matched part of the actual buys; unmatched ones count 0 runs
            res = {"actual": (m.real.sum(), acts.price_cr.sum())}
            for name, key in (("rule_vpc", cand.pred / cand.cost), ("rule_top", cand.pred)):
                o = np.argsort(-key.values)
                g = pick(cand.reset_index(drop=True), o, c.budget, int(c.n), int(c.os))
                cc = cand.reset_index(drop=True).iloc[g]
                res[name] = (cc.real.sum(), cc.cost.sum())
            for m_ in meths:
                runs[m_] += res[m_][0]
                spend[m_] += res[m_][1]
                rows.append(dict(year=Y, team=tm, method=m_, runs=res[m_][0], cost=res[m_][1]))
            for kind, src in (("all", P), ("predictable", P[P.pred.notna()])):
                src = src.reset_index(drop=True)
                for d in range(draws):
                    g = pick(src, rng.permutation(len(src)), c.budget, int(c.n), int(c.os))
                    rand[kind][d] += (src.real.iloc[g].sum(), src.cost.iloc[g].sum())
    tot = pd.DataFrame({"runs": runs, "cost": spend})
    tot["runs_per_cr"] = tot.runs / tot.cost
    out = dict(rows=pd.DataFrame(rows), totals=tot, rand={k: v[:, 0] / v[:, 1] for k, v in rand.items()}, rand_runs={k: v[:, 0] for k, v in rand.items()}, rand_cost={k: v[:, 1] for k, v in rand.items()})  # fmt: skip
    return out


def percentile(x: float, dist: np.ndarray) -> float:
    """Share of random draws below x (0-100)."""
    return float((np.asarray(dist) < x).mean() * 100)


# ------------------------------------------------------------------------------------------ simple rules
def rule_groups(T=None, A=None, years=YEARS, hot_cost: float = 3.0, max_older: int = 1) -> pd.DataFrame:
    """One row per auction player (matched, all four years): year, name, cost, sold, real (IPL Y runs added), history flags.
    cheap_bowler: 1000+ bowl balls over seasons X-2..X (all leagues), cost <= that year's median sold price.
    hot_batter: bat runs added in season X in the top quartile of IPL batters (60+ balls), at most one other IPL batting season of 60+
    balls in X-2..X-1, cost >= hot_cost."""
    T = B.tables() if T is None else T
    A = B.auctions() if A is None else A
    out = []
    for Y in years:
        X = Y - 1
        P = pool(A, Y)
        med = A[(A.auction_year == Y) & A.sold].price_cr.median()
        tr = B.truth_runs(T, Y)
        P["real"] = P.name.map(rar(tr, Y)).fillna(0.0)
        w = T[(T.sy <= X) & (T.sy >= X - 2)]
        bb = w[w.role == "bowl"].groupby("player").balls.sum()
        P["bowl_balls3"] = P.name.map(bb).fillna(0.0)
        ipl = B.player_year(T[T.sy <= X], ["ipl"])
        bat = ipl[(ipl.role == "bat") & (ipl.balls >= 60)]
        last = bat[bat.sy == X].set_index("player").ra
        q75 = last.quantile(0.75)
        older = bat[bat.sy.between(X - 2, X - 1)].groupby("player").size()
        P["hot"] = P.name.map(last).ge(q75) & P.name.map(older).fillna(0).le(max_older)
        P["year"], P["med"] = Y, med
        out.append(P)
    d = pd.concat(out, ignore_index=True)
    d["cheap_bowler"] = (d.bowl_balls3 >= 1000) & (d.cost <= d.med)
    d["hot_batter"] = d.hot & (d.cost >= hot_cost) & d.role.isin(["batter", "wicketkeeper"])
    return d


def group_vs_random(d: pd.DataFrame, flag: str, base: pd.Series, draws: int = 1000, seed: int = 3) -> dict:
    """runs per crore of d[flag] players vs the same number of players drawn at random from d[base]; percentile of the group."""
    g, pool_ = d[d[flag]], d[base]
    rng = np.random.default_rng(seed)
    n = len(g)
    ratios = np.array([(lambda s: s.real.sum() / s.cost.sum())(pool_.iloc[rng.choice(len(pool_), n, replace=False)]) for _ in range(draws)])  # fmt: skip
    r = g.real.sum() / g.cost.sum()
    return dict(n=n, runs_per_cr=r, pool_runs_per_cr=pool_.real.sum() / pool_.cost.sum(), random_mean=ratios.mean(), pct=percentile(r, ratios))  # fmt: skip


if __name__ == "__main__":
    s = simulate()
    print(s["totals"].round(2))
    for k in s["rand"]:
        r = s["rand"][k]
        print(k, "random runs/cr mean %.2f  5-95%%: %.2f-%.2f" % (r.mean(), *np.percentile(r, [5, 95])))
        for m in s["totals"].index:
            print("  ", m, "percentile", round(percentile(s["totals"].runs_per_cr[m], r), 1))
    d = rule_groups()
    print(group_vs_random(d, "cheap_bowler", d.sold & (d.cost <= d.med)))
    print(group_vs_random(d, "hot_batter", d.sold & (d.cost >= 3.0) & d.role.isin(["batter", "wicketkeeper"])))
