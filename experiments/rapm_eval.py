"""RAPM vs WAR v3: tests (a) team-season fit, (b) season-to-season repeatability. Run: .venv\Scripts\python experiments/rapm_eval.py"""
import numpy as np, pandas as pd
from cricket_analytics.models import rapm, war as W

LB, LW = 1000.0, 500.0  # from rapm.cv_lambda on IPL 2023-26 (docs/VALUE_rapm.md)
REPL, RPW = -0.06, 99.3


def era_fit(d):  # opponent effects fitted per era (pre-2023 / 2023+), as the run-expectancy tables are
    out = []
    for lo, hi in ((2008, 2022), (2023, 2026)):
        g = d[(d.sy >= lo) & (d.sy <= hi)].reset_index(drop=True)
        b, w = rapm.fit(g, LB, LW)
        out.append(rapm.opp_delta(g, b, w, 0) .assign(_=0))
    return out


def variants():
    d = rapm.frames(["ipl"])
    v3 = W.all_tables(("ipl",), match_w=0.25)[0]["ipl"]
    v0 = W.all_tables(("ipl",), match_w=0.0)[0]["ipl"]
    S = rapm.seasonal(d, LB, LW)
    app = v3[["comp", "sy", "season", "team", "player", "role"]]
    # A: season ridge, put into the v3 row layout (team = the team of the season's most balls; summed per team-season below)
    tm = v3.sort_values("balls", ascending=False).drop_duplicates(["sy", "player", "role"])[["sy", "player", "role", "team", "season"]]
    A = S.rename(columns={"index": "player", "level_0": "player"}).merge(tm, on=["sy", "player", "role"], how="left")
    A = A.assign(sc=A.ra, wk=0.0, runs=0, wkts=0)[["comp", "sy", "season", "team", "player", "role", "balls", "runs", "wkts", "sc", "wk"]]
    out = {"v3": v3, "A_season_ridge": A}
    for h in (0, 24):
        dl = pd.concat([x.drop(columns="_") for x in (lambda: [rapm.opp_delta(g, *rapm.fit(g, LB, LW), h) .assign(_=0) for g in
                       [d[(d.sy >= lo) & (d.sy <= hi)].reset_index(drop=True) for lo, hi in ((2008, 2022), (2023, 2026))]])()])
        out[f"B_v3_plus_opp(h={h})"] = rapm.apply_delta(v3, dl)
        if h == 0:
            out["B0_nomatchadj_plus_opp"] = rapm.apply_delta(v0, dl)
    return out


def team_fit(rows, ts, years=range(2023, 2027)):
    t = rows.assign(ra=rows.sc + rows.wk, rep=REPL * rows.balls).groupby(["sy", "team"], as_index=False)[["ra", "rep"]].sum()
    s = ts[ts.yr.isin(list(years))].merge(t.rename(columns={"sy": "yr"}), on=["yr", "team"])
    x, y = (s.ra - s.rep) / RPW, (s.w - 0.5) * s.n
    sl, ic = np.polyfit(x, y, 1)
    return dict(n=len(s), r=np.corrcoef(x, y)[0, 1], slope=sl, mae=np.abs(sl * x + ic - y).mean())


def repeat(rows, years, minb={"bat": 150, "bowl": 100}):
    p = rows.assign(ra=rows.sc + rows.wk).groupby(["role", "player", "sy"], as_index=False)[["balls", "ra"]].sum()
    out = {}
    for role in ("bat", "bowl"):
        q = p[(p.role == role) & (p.balls >= minb[role]) & p.sy.isin(list(years))]
        j = q.merge(q.assign(sy=q.sy - 1), on=["player", "sy"])
        out[role] = (np.corrcoef(j.ra_x / j.balls_x, j.ra_y / j.balls_y)[0, 1], len(j))
    return out


if __name__ == "__main__":
    from cricket_analytics.models.war import team_seasons
    ts = team_seasons()
    V = variants()
    rows = []
    for n, r in V.items():
        a, b1, b2 = team_fit(r, ts), repeat(r, range(2008, 2027)), repeat(r, range(2023, 2027))
        rows.append(dict(variant=n, team_r=a["r"], slope=a["slope"], mae=a["mae"], bat_all=b1["bat"][0], bowl_all=b1["bowl"][0],
                         bat_2326=b2["bat"][0], bowl_2326=b2["bowl"][0], n_bat=b1["bat"][1], n_bowl=b1["bowl"][1]))
    res = pd.DataFrame(rows).round(3)
    print(res.to_string())
    res.to_csv("scratch_rapm_ab.csv", index=False)
