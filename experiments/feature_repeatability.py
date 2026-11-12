"""Season-to-season repeatability of commentary features vs baselines (docs/EDA_commentary.md section 7).
Needs features_bat.csv / features_bowl.csv from commentary_features.build(). Run: .venv\\Scripts\\python experiments\\feature_repeatability.py"""
import numpy as np
import pandas as pd

OUT = "data/external/commentary"
MIN_N = 60  # balls per player-season (faced / bowled) in BOTH seasons


def rep(t: pd.DataFrame, cols, base: set) -> pd.DataFrame:
    t = t[t.n >= MIN_N].copy()
    for c in cols + ["ra", "wpa"]:  # season-demean: coverage drifts, league level moves
        t[c] = t[c] - t.groupby("year")[c].transform("mean")
    nxt = t.assign(year=t.year - 1)
    p = t.merge(nxt, on=["player", "year"], suffixes=("", "_next"))
    rows = []
    for c in cols:
        q = p[[c, c + "_next", "ra", "wpa", "ra_next", "wpa_next"]].dropna(subset=[c, c + "_next"])
        n = len(q)
        r = q[c].corr(q[c + "_next"]) if n > 5 else np.nan
        z = np.arctanh(r) if n > 5 else np.nan
        se = 1 / np.sqrt(n - 3) if n > 5 else np.nan
        rows.append({"feature": c, "baseline": c in base, "pairs": n, "r_repeat": r, "ci_lo": np.tanh(z - 1.96 * se), "ci_hi": np.tanh(z + 1.96 * se),
                     "r_ra_same": q[c].corr(q.ra), "r_wpa_same": q[c].corr(q.wpa), "r_ra_next": q[c].corr(q.ra_next), "r_wpa_next": q[c].corr(q.wpa_next)})
    return pd.DataFrame(rows).sort_values("r_repeat", ascending=False)


bat = pd.read_csv(f"{OUT}/features_bat.csv")
bowl = pd.read_csv(f"{OUT}/features_bowl.csv")
bc = ["false_pct", "miss_pct", "edge_pct", "mistime_pct", "edge_bnd_pct", "clean_bnd_pct", "edge_bnd_share", "sr_vs_short", "sr_vs_full", "sr_vs_good",
      "sr_vs_outside_off", "out_vs_short", "out_vs_full", "out_vs_good", "out_vs_outside_off", "sr", "bnd_pct", "out_pct"]
wc = ["false_pct", "miss_pct", "edge_pct", "mistime_pct", "yorker_pct", "short_pct", "death_fulltoss_pct", "death_yorker_pct", "len_entropy", "slower_pct",
      "econ_ball", "bnd_pct", "wk_pct"]
rb = rep(bat, bc, {"sr", "bnd_pct", "out_pct"})
rw = rep(bowl, wc, {"econ_ball", "bnd_pct", "wk_pct"})
rb.to_csv(f"{OUT}/repeatability_bat.csv", index=False)
rw.to_csv(f"{OUT}/repeatability_bowl.csv", index=False)
pd.set_option("display.width", 200)
print("BATTERS (min", MIN_N, "balls both seasons)\n", rb.round(2).to_string(index=False))
print("\nBOWLERS\n", rw.round(2).to_string(index=False))
