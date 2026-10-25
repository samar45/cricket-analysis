"""Coordinate checks, length/line buckets, sanity checks and the demo. Usage: python -I derive.py <joined_men.csv.gz>"""

import sys
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
d = pd.read_csv(sys.argv[1])
d["speed"] = d.hk_ballSpeed.where(d.hk_ballSpeed > 0)  # -1 = missing (measured: ~20% of rows)
print("speed==-1 %:", round((d.hk_ballSpeed < 0).mean() * 100, 1))
t = d[d.hk_pitchX.notna()].copy()
t = t[~t.hk_extras.fillna("").str.contains("Wd|wd|W")]  # drop wides for line/length
print("tracked non-wide balls", len(t), "extras codes:", d.hk_extras.value_counts().to_dict())

print("\n-- coordinate system --")
print(
    "pitchY quantiles",
    t.hk_pitchY.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).round(2).to_dict(),
)
print(
    "pitchX by handedness (median, q25, q75):\n",
    t.groupby("hk_rightHandedBat")
    .hk_pitchX.describe(percentiles=[0.25, 0.5, 0.75])
    .round(2)
    .to_string(),
)
print(
    "stumpsX by RH/LH median:",
    t.groupby("hk_rightHandedBat").hk_stumpsX.median().round(2).to_dict(),
    "| stumpsY (height) q5/50/95:",
    t.hk_stumpsY.quantile([0.05, 0.5, 0.95]).round(2).tolist(),
)
print(
    "pitchY histogram (1 m bins):",
    np.histogram(t.hk_pitchY.clip(-3, 14), bins=range(-3, 15))[0].tolist(),
)
print(
    "pitchX histogram (0.25 m bins, -1.5..1.5):",
    np.histogram(t.hk_pitchX.clip(-1.5, 1.5), bins=np.arange(-1.5, 1.75, 0.25))[0].tolist(),
)
print("fieldX/Y range:", t[["hk_fieldX", "hk_fieldY"]].agg(["min", "max"]).to_dict())

# --- buckets: pitchY = metres from batter's stumps (guess, supported by histogram + death-over check below)
LEN_EDGES = [-99, 2, 6, 8, 99]
LEN_LAB = ["yorker/full toss <2m", "full 2-6m", "good 6-8m", "short >8m"]
t["length"] = pd.cut(t.hk_pitchY, LEN_EDGES, labels=LEN_LAB)
# line: pitchX is lateral. Sign convention tested above; stumps are +-0.114 m (9 in wide). Offside sign = flipped for LH if coords are absolute
OFFSET = 0.15  # GUESS: pitchX medians are RH -0.28 / LH +0.02 while stumpsX is mirrored (-0.16 / +0.15) -> pitchX looks shifted ~-0.15 m
t["off_m"] = np.where(
    t.hk_rightHandedBat, -(t.hk_pitchX + OFFSET), (t.hk_pitchX + OFFSET)
)  # + = off side of that batter
t["line"] = pd.cut(
    t.off_m,
    [-99, -0.114, 0.114, 0.35, 0.9, 99],
    labels=[
        "leg side",
        "on stumps",
        "off-stump line .11-.35m",
        "outside off .35-.9m",
        "wide of off >.9m",
    ],
)
t["phase"] = pd.cut(
    t.cs_over_num, [-1, 5, 14, 19], labels=["powerplay 1-6", "middle 7-15", "death 16-20"]
)
t["style"] = t.hk_bowlingStyle


def pct(s):
    return (100 * s.value_counts(normalize=True)).round(1)


print("\n== overall length / line (% of tracked non-wide balls) ==")
print(pd.concat([pct(t.length), pct(t.line)]).to_string())
print("\n== SANITY 1: length by phase (% of balls) ==")
print((100 * pd.crosstab(t.phase, t.length, normalize="index")).round(1).to_string())
print(
    "mean pitchY by phase:", t.groupby("phase", observed=True).hk_pitchY.mean().round(2).to_dict()
)
print("\n== SANITY 2: speed by bowling style (km/h, valid speeds) ==")
print(
    (
        t.groupby("style")
        .speed.agg(["count", "median"])
        .assign(kmh=lambda x: (x["median"] * 3.6).round(1))
    ).to_string()
)
print("\n== SANITY 3: wicket rate and strike-rate by length ==")
t["wkt"] = (
    t.cs_player_out.notna() & ~t.cs_wicket_type.isin(["run out", "retired hurt", "retired out"])
    if "cs_wicket_type" in t
    else t.cs_player_out.notna()
)
t["faced"] = ~t.hk_extras.fillna("").str.startswith(("Wd", "Nb"))
g = (
    t[t.faced]
    .groupby("length", observed=True)
    .agg(balls=("faced", "size"), runs=("cs_runs_batter", "sum"), wkts=("wkt", "sum"))
)
g["SR"] = (100 * g.runs / g.balls).round(1)
g["balls_per_wkt"] = (g.balls / g.wkts).round(0)
print(g.to_string())

print("\n== DEMO (experimental, unlicensed data, local only) ==")
k = t[(t.cs_batter == "V Kohli") & t.faced]
print(
    "V Kohli joined+tracked balls faced:",
    len(k),
    "seasons",
    sorted(k.cs_season.astype(str).unique())[:1],
    "..",
    sorted(k.cs_season.astype(str).unique())[-1:],
)
kk = k.groupby("length", observed=True).agg(
    balls=("faced", "size"), runs=("cs_runs_batter", "sum"), dismissals=("wkt", "sum")
)
kk["SR"] = (100 * kk.runs / kk.balls).round(1)
kk["balls/dismissal"] = (kk.balls / kk.dismissals.replace(0, np.nan)).round(0)
print(kk.to_string())
b = t[t.cs_bowler == "JJ Bumrah"]
print("\nJJ Bumrah tracked balls:", len(b), "| median speed km/h", round(b.speed.median() * 3.6, 1))
print(
    pd.concat(
        {
            "all": pct(b.length),
            "powerplay": pct(b[b.phase == "powerplay 1-6"].length),
            "death": pct(b[b.phase == "death 16-20"].length),
            "IPL all bowlers death": pct(t[t.phase == "death 16-20"].length),
        },
        axis=1,
    ).to_string()
)
print("Bumrah line:", pct(b.line).to_dict())
