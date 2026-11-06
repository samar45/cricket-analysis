"""Marcel-style stable-skill predictors for the backtest (docs/VALUE_moneyball_v2.md, M11).

Last 3 seasons weighted 5/4/3; each runs-added part (base, dot, 1-3, four, six, wicket/out, extras, rest) is divided by
(weighted balls + k_part), k = the part's own stability constant (components.k_table: method of moments, seasons <= X only, the
M2 numbers), then the parts are added up to a runs-added-per-ball rate. Expected balls = the 5/4/3-weighted mean of his IPL balls.
Other leagues count at weight OTHER_W (hand-set; 0 for `marcel_ipl`). `marcel_skill` drops the wicket and rest parts.
"""

import numpy as np
import pandas as pd

from . import components as C
from .backtest import predictor

WEIGHTS = (5, 4, 3)  # X, X-1, X-2
OTHER_W = 0.5


def marcel_frame(tab, ks, X, other_w=OTHER_W, skill_only=False, weights=WEIGHTS) -> pd.DataFrame:
    """tab/ks from components.tables()/k_table. Returns bat, bowl (expected runs added), bat_rate, bowl_rate."""
    cols = {}
    for role in ("bat", "bowl"):
        d = tab[role]
        d = d[(d.sy <= X) & (d.sy > X - len(weights))].copy()
        w = d.sy.map({X - i: float(v) for i, v in enumerate(weights)})
        ipl = d.comp == "ipl"
        lw = w * np.where(ipl, 1.0, other_w)
        parts = {"B": 50.0}  # base is shrunk with a fixed 50 balls as in components.project_parts
        names = [c for c in C.CLS[role] if not (skill_only and c == C.WK[role])]
        parts.update({f"s_{c}": ks[role][c] for c in names})
        if not skill_only:
            parts["R"] = ks[role]["R"]
        den = (lw * d.n).groupby(d.player).sum()
        rate = sum(((lw * d[p]).groupby(d.player).sum()) / (den + k) for p, k in parts.items())
        rate = rate.where(den > 0)
        wi = (w * d.n).where(ipl, 0.0).groupby(d.player).sum() / sum(weights)  # missed season counts 0 balls
        cols[f"{role}_rate"], cols[role] = rate, rate * wi
    return pd.DataFrame(cols)


def _mk(**kw):
    def fn(T, X, ctx):
        tab, sig = C.tables()
        f = marcel_frame(tab, C.k_table(X + 1, tab, sig), X, **kw)
        return f[f[["bat", "bowl"]].notna().any(axis=1)]

    return fn


predictor("marcel", "runs")(_mk())
predictor("marcel_ipl", "runs")(_mk(other_w=0.0))
predictor("marcel_skill", "runs")(_mk(skill_only=True))
