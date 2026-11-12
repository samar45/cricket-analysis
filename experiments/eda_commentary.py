"""EDA of parsed commentary -> markdown tables on stdout + docs/img/eda_*.png.
Needs data/external/commentary/frame.pkl (d from commentary_features.build(), pickled).
Run: .venv\\Scripts\\python experiments\\eda_commentary.py > data\\external\\commentary\\eda_out.md"""
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

d = pd.read_pickle("data/external/commentary/frame.pkl")


def md(t):
    return "```\n" + t.round(3).to_string() + "\n```\n"


d["era"] = pd.cut(d.year, [2016, 2019, 2022, 2026], labels=["2017-19", "2020-22", "2023-26"])
d["sp_ok"] = d.speed.where(d.speed.between(50, 160))
d["boundary"], d["wk"] = d.runs_batter.isin([4, 6]), d.wicket_type.notna()
fld = ["length", "line", "shot", "contact", "delivery", "sp_ok"]


def cov(g):
    gr = d.groupby(g, observed=True)
    return gr[fld].agg(lambda s: s.notna().mean() * 100).round(1).assign(balls=gr.size())


print("## 1 Coverage (% of balls with the field)\n")
for g in ["year", "era", "phase", "bowl_kind"]:
    print(f"**by {g}**\n")
    print(md(cov(g)))
print("## 2 Distributions\n")
print("speed (kph) by bowler type\n")
print(md(d.groupby("bowl_kind").sp_ok.describe(percentiles=[.05, .5, .95])))
leg = d[d.wides == 0]
for f in ["length", "line"]:
    print(f"{f} mix by phase (% of known)\n")
    print(md(pd.crosstab(leg.phase, leg[f], normalize="index") * 100))
print("shot mix (% of known) by bowler type\n")
print(md(pd.crosstab(d.bowl_kind, d.shot, normalize="index") * 100))
print("## 3 Outcome by category (balls faced)\n")


def out(col):
    t = leg.groupby(col).agg(
        balls=("boundary", "size"), runs_ball=("runs_batter", "mean"), bnd_pct=("boundary", "mean"),
        six_pct=("runs_batter", lambda s: (s == 6).mean()), wk_pct=("wk", "mean"), ra_bat=("bat_ra", "mean"))
    t[["bnd_pct", "six_pct", "wk_pct"]] *= 100
    return t


for c in ["length", "line", "contact", "delivery", "bowl_kind"]:
    print(f"by {c}\n")
    print(md(out(c)))
print("## 4 Missing-not-at-random: P(field present) by outcome class\n")
leg = leg.assign(outcome=np.select([leg.wk, leg.runs_batter == 6, leg.runs_batter == 4, leg.runs_batter == 0],
                                   ["wicket", "six", "four", "dot"], "1-3 runs"))
gr = leg.groupby("outcome")
print(md(gr[fld].agg(lambda s: s.notna().mean() * 100).assign(balls=gr.size())))
F5 = ["length", "line", "contact", "shot", "delivery"]
for f in F5:  # relative to season-phase rate, removes coverage drift
    p = leg[f].notna() * 1.0
    leg["r_" + f] = p / p.groupby([leg.year, leg.phase]).transform("mean")
rel = leg.groupby("outcome")[[f"r_{f}" for f in F5]].mean().loc[["dot", "1-3 runs", "four", "six", "wicket"]]
print("relative coverage by outcome (1.00 = season-phase average)\n")
print(md(rel))
print("## 5 Sanity checks\n")
S = []


def chk(name, bad, tot, note=""):
    S.append((name, int(bad), int(tot), round(100 * bad / max(tot, 1), 2), note))


ov = leg.boundary.mean() * 100
y = leg[leg.length == "yorker"]
chk("yorker -> six", (y.runs_batter == 6).sum(), len(y), f"all balls {100 * (leg.runs_batter == 6).mean():.1f}% sixes")
chk("yorker -> four", (y.runs_batter == 4).sum(), len(y), f"all balls {100 * (leg.runs_batter == 4).mean():.1f}%")
sp = d[(d.bowl_kind == "spin") & d.sp_ok.notna()]
chk("spinner speed outside 70-100", (~sp.sp_ok.between(70, 100)).sum(), len(sp))
pc = d[(d.bowl_kind == "pace") & d.sp_ok.notna()]
chk("pacer speed outside 120-155", (~pc.sp_ok.between(120, 155)).sum(), len(pc))
chk("quoted speed outside 50-160 (parse error)", (d.speed.notna() & d.sp_ok.isna()).sum(), d.speed.notna().sum())
chk("pacer quoted speed < 100", (pc.sp_ok < 100).sum(), len(pc))
e = leg[leg.contact.isin(["edge", "inside edge", "top edge", "leading edge", "bottom edge"])]
chk("edge -> boundary", e.boundary.sum(), len(e), f"overall {ov:.1f}%; runs/ball edge {e.runs_batter.mean():.2f} vs {leg.runs_batter.mean():.2f}")
ie = leg[leg.contact == "inside edge"]
chk("inside edge -> six", (ie.runs_batter == 6).sum(), len(ie))
mi = leg[leg.contact == "miss"]
chk("miss (beaten) -> runs off bat > 0", (mi.runs_batter > 0).sum(), len(mi), "text can say miss then edge-run")
wd = d[d.wides > 0]
chk("Cricsheet wide with line other than wide", (wd.line.notna() & (wd.line != "wide")).sum(), wd.line.notna().sum(), f"line missing on {wd.line.isna().sum()} of {len(wd)} wides")
lw = d[d.line == "wide"]
chk("line=wide but not a Cricsheet wide", (lw.wides == 0).sum(), len(lw), "wide of off but played is legal")
ev = d.cb_event.fillna("")
chk("Cricbuzz FOUR, Cricsheet runs_batter != 4", (d[ev.str.contains("FOUR")].runs_batter != 4).sum(), ev.str.contains("FOUR").sum(), "byes / overthrow boundaries")
chk("Cricbuzz SIX, runs_batter != 6", (d[ev.str.contains("SIX")].runs_batter != 6).sum(), ev.str.contains("SIX").sum())
chk("Cricbuzz WICKET, no Cricsheet wicket", d[ev.str.contains("WICKET")].wicket_type.isna().sum(), ev.str.contains("WICKET").sum())
wk = d[d.wicket_type.notna() & ~d.wicket_type.isin(["run out", "retired hurt"])]
chk("Cricsheet wicket (not run out) without Cricbuzz WICKET", (~wk.cb_event.fillna("").str.contains("WICKET")).sum(), len(wk))
lv = d[d.shot == "leave"]
chk("shot=leave, runs off bat > 0", (lv.runs_batter > 0).sum(), len(lv))
spd = {"googly", "leg break", "off break", "carrom", "arm ball", "flipper", "topspinner", "back of the hand"}
a = d[d.delivery.isin(spd) & d.bowl_kind.notna()]
chk("spin-type delivery, reviewed-pace bowler", (a.bowl_kind == "pace").sum(), len(a))
a = d[d.delivery.isin({"inswinger", "outswinger"}) & d.bowl_kind.notna()]
chk("swing delivery, reviewed-spin bowler", (a.bowl_kind == "spin").sum(), len(a))
for k in ("bouncer", "yorker"):
    a = d[(d.length == k) & d.bowl_kind.notna()]
    chk(f"{k}, reviewed-spin bowler", (a.bowl_kind == "spin").sum(), len(a))
print(md(pd.DataFrame(S, columns=["check", "flagged", "of", "%", "note"])))
# charts
plt.rcParams.update({"figure.facecolor": "#111", "axes.facecolor": "#111", "text.color": "#ddd", "axes.labelcolor": "#ddd",
                     "xtick.color": "#ddd", "ytick.color": "#ddd", "axes.edgecolor": "#555", "legend.facecolor": "#222"})
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
d.groupby("year")[fld].agg(lambda s: s.notna().mean() * 100).plot(ax=ax[0], marker="o")
ax[0].set_title("Coverage by season (% of balls)")
for k, c in (("pace", "#4cc9f0"), ("spin", "#f72585")):
    ax[1].hist(d[d.bowl_kind == k].sp_ok.dropna(), bins=np.arange(50, 160, 2), alpha=.7, label=k, color=c)
ax[1].set_title("Quoted speed (kph) by bowler type")
ax[1].legend()
plt.tight_layout()
plt.savefig("docs/img/eda_coverage_speed.png", dpi=110)
plt.close()
fig, ax = plt.subplots(1, 3, figsize=(13, 4))
t = out("length").loc[["yorker", "full toss", "full", "length", "back of a length", "short of length", "short", "bouncer"]]
t.runs_ball.plot.bar(ax=ax[0], color="#4cc9f0")
ax[0].set_title("Runs per ball by length")
t.wk_pct.plot.bar(ax=ax[1], color="#f72585")
ax[1].set_title("Wicket % by length")
out("line").loc[["outside off", "middle", "leg", "body", "wide"]].runs_ball.plot.bar(ax=ax[2], color="#b5e48c")
ax[2].set_title("Runs per ball by line")
plt.tight_layout()
plt.savefig("docs/img/eda_outcome.png", dpi=110)
plt.close()
fig, ax = plt.subplots(figsize=(7, 4))
rel.columns = [c[2:] for c in rel.columns]
rel.plot.bar(ax=ax)
ax.axhline(1, color="#888", lw=.8)
ax.set_title("Relative coverage by outcome (1 = average)")
plt.tight_layout()
plt.savefig("docs/img/eda_mnar.png", dpi=110)
