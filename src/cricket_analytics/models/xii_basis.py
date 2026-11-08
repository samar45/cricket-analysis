"""Value basis for the XII pick: recent (WAR 2023-26 weighted 4/3/2/1) vs worth (expected next-season WAR from the player_worth
ridge) vs blend. Builds models/data/worth_value_2027.csv and runs the XII-level backtest (docs/VALUE_xii_basis.md).

Rebuild + test: python -m cricket_analytics.models.xii_basis   (reads the DB read-only, a few minutes)
"""

import numpy as np
import pandas as pd

from . import backtest as B
from . import trade as TR
from . import war as W

VALUE_CSV = TR.WORTHVAL_CSV
TEST_CSV = W.DATA / "xii_basis_backtest.csv"
_WW: dict = {}


def worth_war(T: pd.DataFrame, X: int, which: str = "worth") -> pd.DataFrame:
    """Expected WAR next season per player (bat_war, bowl_war) from the worth predictor fitted on data up to calendar year X:
    (expected runs added per ball - replacement per ball) x expected balls (last-3-season average, a missed season = 0) / runs per win."""
    if (which, X) not in _WW:
        e = W.load_params()["era"]["2023"]
        p = B.PREDICTORS[which][0](T[T.sy <= X], X, {})
        _WW[which, X] = pd.DataFrame(
            {r: (p[f"{r}_rate"] - e["repl"][r] / 100.0) * p[f"{r}_q"] / e["rpw"] for r in ("bat", "bowl")}
        ).rename(columns=lambda c: f"{c}_war")
    return _WW[which, X]


def prior_worth(sy: int, which: str = "worth") -> pd.Series:
    """Worth-basis value (WAR) of every player for IPL season sy, from data before it (used to fit the beta of that basis)."""
    return worth_war(B.tables(), sy - 1, which).sum(axis=1)


def blend_pred(a: float):
    """Backtest predictor: a x recent value + (1 - a) x worth WAR (a missing one counts 0)."""

    def fn(T, X, ctx):
        r = TR.prior_values(pd.read_csv(TR.MATCH_CSV), X + 1, W.load_params())
        w = worth_war(T, X).sum(axis=1)
        j = pd.concat([r.rename("r"), w.rename("w")], axis=1).fillna(0.0)
        return pd.DataFrame({"total": a * j.r + (1 - a) * j.w})

    return fn


def pick_blend(grid=np.linspace(0, 1, 11)) -> pd.DataFrame:
    """Pooled player-level spearman (IPL 2024-26 targets, runs-added truth) for each weight a on recent value."""
    extra = {f"blend{a:.1f}": (blend_pred(a), "rank") for a in grid}
    r = B.run(names=tuple(extra), whats=("total",), extra=extra)
    r = r[r.target == "pooled"].assign(a=lambda d: d.predictor.str[5:].astype(float))
    return r[["a", "n", "spearman"]].reset_index(drop=True)


def xii_test(a: float, targets=(2024, 2025, 2026)) -> pd.DataFrame:
    """Per team-season: each basis picks the 11 best-valued players among those who played 3+ matches for the team that season,
    using only data before the season. Rows: season, team, wins, and per basis the XII value it assigns and the XII's actual WAR
    that season (no rules applied: the same pool and the same top-11 rule for every basis)."""
    from ..db import query

    T, m, prm = B.tables(), pd.read_csv(TR.MATCH_CSV), W.load_params()
    e = prm["era"]["2023"]
    ap = W.season_table("ipl")[1]
    wins = query(
        "SELECT year(date) AS sy, winner AS team, count(*) AS wins FROM matches WHERE competition='ipl' AND date >= '2024-01-01' "
        "AND winner IS NOT NULL GROUP BY ALL", [])  # fmt: skip
    ra = T[T.comp == "ipl"].assign(war=lambda d: (d.ra - d.role.map({r: e["repl"][r] / 100 for r in ("bat", "bowl")}) * d.balls) / e["rpw"])
    actual = ra.groupby(["sy", "player"]).war.sum()
    rows = []
    for t in targets:
        rec = TR.prior_values(m, t, prm)
        wv = worth_war(T, t - 1).sum(axis=1)
        j = pd.concat([rec.rename("r"), wv.rename("w"), worth_war(T, t - 1, "worth2").sum(axis=1).rename("w2")], axis=1).fillna(0.0)
        j["b"] = a * j.r + (1 - a) * j.w
        for team, g in ap[(ap.sy == t) & (ap.matches >= 3)].groupby("team"):
            row = dict(sy=t, team=team)
            for basis, col in (("recent", "r"), ("worth", "w"), ("worth2", "w2"), ("blend", "b")):
                v = j[col].reindex(g.player).fillna(0.0)
                top = v.sort_values(ascending=False).index[:11]
                row[f"{basis}_value"] = float(v[top].sum())
                row[f"{basis}_actual"] = float(actual.reindex([(t, p) for p in top]).fillna(0.0).sum())
            rows.append(row)
    d = pd.DataFrame(rows).merge(wins, on=["sy", "team"], how="left").fillna({"wins": 0})
    return d


def summary(d: pd.DataFrame) -> pd.DataFrame:
    out = []
    for b in ("recent", "worth", "worth2", "blend"):
        for tag in ("value", "actual"):
            x, y = d[f"{b}_{tag}"], d.wins
            out.append(dict(basis=b, what=tag, n=len(d), pearson=x.corr(y), spearman=x.rank().corr(y.rank())))
    return pd.DataFrame(out).round(3)


def build_values(which: str = "worth") -> pd.DataFrame:
    w = worth_war(B.tables(), 2026, which)
    w.index.name = "player"
    return w.round(5).reset_index()


def main() -> None:
    g = pick_blend()
    print(g.round(4).to_string(index=False))
    a = float(g.loc[g.spearman.idxmax(), "a"])
    d = xii_test(a)
    s = summary(d)
    print(f"blend weight on recent value a = {a:.1f}\n", s.to_string(index=False))
    build_values().to_csv(VALUE_CSV, index=False)
    build_values("worth2").to_csv(TR.WORTH2VAL_CSV, index=False)
    s.assign(blend_a=a).to_csv(TEST_CSV, index=False)


if __name__ == "__main__":
    main()
