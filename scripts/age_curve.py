"""Age curve: mean change in runs_added per 100 balls from season X to X+1, by age in season X.
Players pooled across IPL + big T20 leagues per calendar year. Run: .venv/Scripts/python scripts/age_curve.py"""
import pandas as pd
from cricket_analytics import api
LG = ["ipl", "bbl", "psl", "cpl", "sa20", "hundred", "blast"]
MIN = 100  # balls per season to count
dob = pd.read_csv("src/cricket_analytics/reference/player_dob.csv").dropna(subset=["dob"]).drop_duplicates("cricsheet_name").set_index("cricsheet_name").dob
dob = pd.to_datetime(dob)
rows = []
for role, pc, bc in [("batting", "batter", "balls"), ("bowling", "bowler", "legal_balls")]:
    for y in range(2014, 2027):
        for lg in LG:
            try:
                d = api.run("runs_added", competition=lg, role=role, season_from=y, season_to=y, min_balls=1, top=5000).data
            except Exception:
                continue
            if len(d): rows.append(d.rename(columns={pc: "p", bc: "b"})[["p", "b", "runs_added"]].assign(role=role, year=y))
a = pd.concat(rows).groupby(["role", "year", "p"], as_index=False).sum()
a = a[a.b >= MIN]; a["rpb"] = 100 * a.runs_added / a.b
nxt = a.assign(year=a.year - 1)[["role", "year", "p", "rpb", "b"]]
m = a.merge(nxt, on=["role", "year", "p"], suffixes=("", "_n"))
m["dob"] = m.p.map(dob); m = m.dropna(subset=["dob"])
m["age"] = (m.year - m.dob.dt.year).astype(int)
m["d"] = m.rpb_n - m.rpb
m["bucket"] = pd.cut(m.age, [0, 22, 24, 26, 28, 30, 32, 34, 50], labels=["<=22", "23-24", "25-26", "27-28", "29-30", "31-32", "33-34", "35+"])
g = m.groupby(["role", "bucket"], observed=True).d.agg(["count", "mean", "sem"]).round(2)
print(g.to_string())
tot = a.groupby("role").p.count(); cov = a.assign(h=a.p.isin(dob.index)).groupby("role").h.mean().round(3)
print("player-seasons", dict(tot), "with DOB", dict(cov), "pairs used", m.groupby("role").size().to_dict())
