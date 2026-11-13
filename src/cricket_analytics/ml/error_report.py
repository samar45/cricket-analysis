"""Error analysis of the production in-play model (v1 ens-G1 = 50/50 of G1 and sim-B), out-of-sample only.

  python -m cricket_analytics.ml.error_report

Sources: IPL 2022-25 rolling caches (validate.load_models), IPL 2026 holdout caches (models trained <= 2025),
non-IPL fresh set (v2_fresh_*.parquet, model v1-ens; no baseline there). Writes docs/ML_ERRORS.md and two plots.
Read-only on the database; never writes a .duckdb.
"""

import numpy as np
import pandas as pd

from . import validate as V
from .dataset import OUT_DIR

DOCS = OUT_DIR.parents[2] / "docs"
CPS = (36, 60, 90)  # 6/10/15 overs for the pooled tables
TB = [0, 159.5, 189.5, 219.5, 999]
TL = ["<160", "160-189", "190-219", "220+"]


# ---------- maths (tested) ----------
def boot_ratio(df, num, den="n", reps=500, seed=0):
    """Mean of `num` per state with matches resampled: returns (value, s.e.)."""
    g = df.groupby("match_id").agg(a=(num, "sum"), b=(den, "sum"))
    a, b = g.a.to_numpy(float), g.b.to_numpy(float)
    val = a.sum() / b.sum()
    if len(g) < 3:
        return val, np.nan
    pick = np.random.default_rng(seed).integers(0, len(g), (reps, len(g)))
    return val, float((a[pick].sum(1) / b[pick].sum(1)).std())


def score_stats(d):
    """d has q50, final_total, match_id. Bias = pred - actual."""
    d = d.assign(err=d.q50 - d.final_total, n=1, w20=((d.q50 - d.final_total).abs() <= 20).astype(float))
    bias, se = boot_ratio(d, "err")
    return {"n_matches": d.match_id.nunique(), "MAE": d.err.abs().mean(), "bias": bias, "se": se, "within20": d.w20.mean(),
            "flag": bool(se == se and abs(bias) > 2 * se and d.match_id.nunique() >= 8)}


def win_stats(d):
    """d has p (chase wins), chase_won, match_id. gap = mean p - actual win rate."""
    p = d.p.clip(1e-6, 1 - 1e-6)
    d = d.assign(gapv=d.p - d.chase_won, n=1, ll=-(d.chase_won * np.log(p) + (1 - d.chase_won) * np.log(1 - p)),
                 ok=(((d.p > 0.5) == (d.chase_won == 1)) & (d.p != 0.5)).astype(float))
    gap, se = boot_ratio(d, "gapv")
    return {"n_matches": d.match_id.nunique(), "right%": d.ok.mean() * 100, "pred": d.p.mean(), "actual": d.chase_won.mean(),
            "gap": gap, "se": se, "logloss": d.ll.mean(), "flag": bool(se == se and abs(gap) > 2 * se and d.match_id.nunique() >= 8)}


def by_group(s, w, col, ss=None, ws=None, minm=1):
    """One row per value of `col`: first-innings stats (blend + baseline MAE) and chase stats. s, w are state frames."""
    rows = []
    for v in sorted(set(s[col].dropna()) | set(w[col].dropna()), key=str):
        a, b = s[s[col] == v], w[w[col] == v]
        if max(a.match_id.nunique(), b.match_id.nunique()) < minm:
            continue
        r = {"group": v}
        if len(a):
            x = score_stats(a)
            r.update({"1st n": x["n_matches"], "1st MAE": x["MAE"], "1st bias": x["bias"], "1st se": x["se"], "in +-20%": x["within20"] * 100, "1st flag": x["flag"]})
            if "base_q50" in a:
                r["base MAE"] = (a.base_q50 - a.final_total).abs().mean()
        if len(b):
            y = win_stats(b)
            r.update({"ch n": y["n_matches"], "right%": y["right%"], "pred": y["pred"], "actual": y["actual"], "gap": y["gap"], "gap se": y["se"], "ch logloss": y["logloss"], "ch flag": y["flag"]})
            if "base_p" in b:
                r["base logloss"] = win_stats(b.assign(p=b.base_p))["logloss"]
        rows.append(r)
    return pd.DataFrame(rows)


def playoff_flag(m):
    """m: one row per match with season_year, date, match_id -> True for the last 4 matches of each season."""
    m = m.sort_values(["season_year", "date", "match_id"])
    return m.groupby("season_year").cumcount(ascending=False) < 4


# ---------- data ----------
def _nid(df):
    return df.assign(match_id=df.match_id.astype(str).str.replace(r"\.0$", "", regex=True))


def _ctx_extra():
    """Per-match info: opponent, toss, target, playoffs flag."""
    inn = _nid(pd.read_parquet(OUT_DIR / "states_innings.parquet"))
    return inn


def build_ipl():
    st, wn, meta = V.load_models()
    m = _nid(meta).drop_duplicates(["match_id", "innings", "balls_bowled"])
    s, w = _nid(st[V.ENS1]), _nid(wn[V.ENS1])
    sb, wb = _nid(st[V.BASE]), _nid(wn[V.BASE])
    s = s.merge(sb[V.KEYS + ["q50"]].rename(columns={"q50": "base_q50"}), on=V.KEYS)
    w = w.merge(wb[V.KEYS + ["p"]].rename(columns={"p": "base_p"}), on=V.KEYS)
    s = s.merge(m[V.KEYS + ["venue", "batting_team", "date", "season_year", "toss_bat", "toss_decision", "toss_winner", "target"]], on=V.KEYS, how="left")
    w = w.merge(m[V.KEYS + ["venue", "batting_team", "date", "season_year", "toss_bat", "toss_decision", "toss_winner", "target"]], on=V.KEYS, how="left")
    return s, w


def build_2026():
    from ..db import query
    from .s4b import conformalise

    rd = lambda n: _nid(pd.read_parquet(OUT_DIR / n))  # noqa: E731
    gS, gW, sb = conformalise(rd("holdout_G1_S.parquet"), rd("holdout_G1_V.parquet"), "G1"), rd("holdout_G1_W.parquet"), rd("holdout_simB.parquet")
    bS, bW = rd("holdout_base_S.parquet"), rd("holdout_base_W.parquet")
    sb = sb.assign(p=sb.win)
    gS, gW = gS[gS.balls_bowled.isin(V.CP)].assign(balls_bowled=lambda d: d.balls_bowled.astype(int)), gW[gW.balls_bowled.isin(V.CP)].assign(balls_bowled=lambda d: d.balls_bowled.astype(int))
    meta = pd.concat([gS, gW])[V.KEYS + ["venue", "batting_team", "date", "season_year"]].drop_duplicates(V.KEYS)
    out = []
    for kind, g, b, bb_ in (("score", gS, sb[sb.innings == 1], bS), ("win", gW, sb[sb.innings == 2], bW)):
        g = g[V.KEYS + ["final_total", "chase_won"] + (V.QC if kind == "score" else ["p"])]
        b = b[V.KEYS + (V.QC if kind == "score" else ["p"])].assign(balls_bowled=lambda d: d.balls_bowled.astype(int))
        g = g.assign(balls_bowled=g.balls_bowled.astype(int))
        if kind == "win":
            g = g[g.chase_won.notna()]
        a = V.align({"g": g, "s": b})
        e = V.ensemble(a["g"], a["s"], kind)
        bb2 = bb_[bb_.balls_bowled.isin(V.CP)].assign(balls_bowled=lambda d: d.balls_bowled.astype(int))
        bb2 = bb2[V.KEYS + (["q50"] if kind == "score" else ["p"])].rename(columns={"q50": "base_q50", "p": "base_p"})
        e = e.merge(bb2, on=V.KEYS, how="left").merge(meta, on=V.KEYS, how="left")
        out.append(e)
    s, w = out
    t = query("select match_id, toss_winner, toss_decision from matches").assign(match_id=lambda d: d.match_id.astype(str))
    inn = _ctx_extra()
    tg = inn[inn.innings == 2][["match_id", "target"]]
    def ctx(x):
        x = x.merge(t, on="match_id", how="left").merge(tg, on="match_id", how="left")
        return x.assign(toss_bat=np.where(x.toss_decision == "bat", "toss winner bats first", "toss winner fields first"))

    s, w = ctx(s), ctx(w)
    return s, w




def build_fresh():
    rd = lambda n: _nid(pd.read_parquet(OUT_DIR / n))  # noqa: E731
    S, W = rd("v2_fresh_S.parquet"), rd("v2_fresh_W.parquet")
    S, W = S[S.model == "v1-ens"], W[W.model == "v1-ens"]
    inn = _ctx_extra()
    mi = inn[inn.innings == 1][["match_id", "venue", "batting_team", "date", "competition"]]
    mi2 = inn[inn.innings == 2][["match_id", "venue", "batting_team", "date", "competition", "target"]]
    S, W = S.merge(mi, on="match_id", how="left"), W.merge(mi2, on="match_id", how="left")
    return S.assign(target=S.match_id.map(inn[inn.innings == 2].set_index("match_id").target)), W


def finish(s, w):
    """Add checkpoint labels and bands."""
    for d in (s, w):
        d["cp"] = (d.balls_bowled // 6).astype(int).astype(str) + " ov"
        d["tbucket"] = pd.cut(d.target, TB, labels=TL).astype(str)
        d["date"] = pd.to_datetime(d.date)
    s["band"] = pd.cut(s.final_total, TB, labels=TL).astype(str)
    return s, w


def add_playoffs(s, w, cal):
    po = cal.assign(po=playoff_flag(cal)).set_index("match_id").po
    for d in (s, w):
        d["stage"] = np.where(d.match_id.map(po).fillna(False).astype(bool), "playoffs (last 4)", "league")
    return s, w


def ipl_calendar():
    inn = _ctx_extra()
    m = inn[(inn.competition == "ipl") & (inn.innings == 1) & inn.season_year.between(2022, 2026) & ~inn.reduced][["match_id", "date", "season_year"]]
    return m.assign(date=pd.to_datetime(m.date))


# ---------- report ----------
def f(df, nd=2):
    from .baselines import md

    df = df.copy()
    for c in df.columns:
        if df[c].dtype == bool:
            df[c] = np.where(df[c], "FLAG", "")
        elif df[c].dtype.kind == "f":
            df[c] = df[c].round(3 if c in ("pred", "actual", "gap", "gap se", "ch logloss", "base logloss", "p(chase wins)") else nd)
    return md(df, nd)


COLS = ["group", "1st n", "1st MAE", "base MAE", "1st bias", "1st se", "in +-20%", "1st flag", "ch n", "right%", "pred", "actual", "gap", "gap se", "ch logloss", "base logloss", "ch flag"]
REN = {"1st n": "n 1st", "1st MAE": "MAE", "1st bias": "bias", "1st se": "bias se", "in +-20%": "%+-20", "1st flag": "flag", "ch n": "n ch"}


def tab(s, w, col, **k):
    t = by_group(s, w, col, **k)
    return t[[c for c in COLS if c in t.columns]].rename(columns=REN | {"group": col})


def plot(t, col, fn, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = t.sort_values("bias")
    fig, ax = plt.subplots(1, 2, figsize=(11, max(4, 0.32 * len(t) + 1.5)), sharey=True)
    for a, b, e, fl, ttl in ((ax[0], "bias", "bias se", "flag", "1st innings bias, runs (pred - actual), +-2 s.e."),
                             (ax[1], "gap", "gap se", "ch flag", "Chase: predicted minus actual win rate, +-2 s.e.")):
        a.barh(t[col].astype(str).str[:34], t[b], xerr=2 * t[e], color=np.where(t[fl].astype(bool), "#c0392b", "#7f8c8d"), capsize=2)
        a.axvline(0, color="k", lw=.8)
        a.set_title(ttl, fontsize=9)
    fig.suptitle(title + " (red = more than 2 s.e. from zero)", fontsize=10)
    fig.tight_layout()
    fig.savefig(DOCS / "img" / fn, dpi=110)
    plt.close(fig)


def misses(s10, w, ft):
    a = s10.assign(miss=s10.q50 - s10.final_total)
    a = a.reindex(a.miss.abs().sort_values(ascending=False).index).head(10)
    t1 = pd.DataFrame({"date": a.date.dt.strftime("%Y-%m-%d"), "batting": a.batting_team, "venue": a.venue, "predicted": a.q50.round(0), "actual": a.final_total, "miss": a.miss.round(0)})
    w = w.assign(wrong=((w.p > .5) != (w.chase_won == 1)), conf=(w.p - .5).abs())
    b = w[w.wrong].sort_values("conf", ascending=False).drop_duplicates("match_id").head(10).merge(ft, on="match_id", how="left")
    t2 = pd.DataFrame({"date": b.date.dt.strftime("%Y-%m-%d"), "match": b.first_team + " v " + b.batting_team, "target": b.target.astype(int), "at": b.cp,
                       "p(chase wins)": b.p.round(3), "chase actually": np.where(b.chase_won == 1, "won", "lost")})
    return t1, t2


BULLETS = """- **Where to trust it.** From 10 overs on, the first-innings forecast is within 20 runs about 7 times in 10 (87% at 15 overs), and it beats the baseline in every season, at every checkpoint and at most venues (not at Chepauk; roughly level at Brabourne, Pune and DY Patil). Mid-range scores (160-219) are forecast well (MAE about 13).
- **Where not to trust it.** At the start of the innings (0 overs) only 44% of forecasts land within 20 runs (MAE 27.5): that is mostly cricket's own randomness, not a fixable bug. Treat the first-innings number as a range, not a point.
- **Extreme totals are the weak spot.** Totals under 160 are guessed about 16 runs too high and 220+ about 16 runs too low. Part of that is hindsight (we group by the final score), but the baseline is NOT as biased at the high end, and the model is worse than the baseline for the lowest totals (MAE 20.4 against 15.6). The model pulls toward the middle, so it will not 'see' a collapse or a 250 coming until it is under way.
- **Teams: no real problem.** No team is flagged on either measure. Teams differ by at most about 2.5 runs in first-innings bias and are all inside 2 s.e. The model does not seem to favour or punish any team.
- **Venues: mostly fine, one exception.** Chepauk (Chennai) is flagged: the model guesses about 9 runs too high on average, and the simple baseline actually beats it there (MAE 13.3 against 15.6). Guess: Chepauk is a slow ground whose pattern the model is not capturing. Lucknow (+4.7) and Mullanpur (+9.4, only 10 matches) lean high too, but inside the noise. Use extra caution at Chepauk.
- **Chase win chance.** Overall well calibrated 2022-25 (gap near zero each season). The favourite wins 72% of the time at 0 overs (close to a coin flip), 80% at 10 overs, 86% at 15 overs. IPL 2026 is the exception: chasers won 64%, the model said 57%, and that is flagged at 0, 6 and 15 overs. 2025 was the mirror image (model slightly too fond of chasers at 15 overs, flagged). So: when the league is in a 'chase-friendly' or 'defend-friendly' year, expect the model to lag by 5-10 points.
- **Non-IPL leagues (2026).** Calibration is good in all big leagues (gaps within about 7 points; CPL and PSL under-rate chasers a little). First-innings forecasts lean high in some (MLC +6, BPL +5, PSL +4, CPL +4) but only LPL (Sri Lanka, -8.5 runs, the Dambulla ground) is flagged. Small venues have 6-20 matches each, so read single venues with care. These leagues have no baseline cached, so 'better than baseline' is not shown here.
- **Toss and playoffs.** No clear effect. Playoff games (only 20 matches) look no worse than league games.
- **Biggest misses are freak scores.** At 10 overs the worst first-innings misses are 45-67 runs (CSK 216 in 2022 from a forecast of 149; RCB 254 and 250 and DC 264 in 2026). The most confident wrong chase calls are 'sure things' that collapsed: KKR chasing 112 against Punjab (99.6% to win at 6 overs, then lost) and LSG chasing 136 against GT in 2023 (97.7% at 10 overs, then lost). The model does give 99% calls and T20 collapses can still beat them; treat anything above 95% as 'very likely', not 'certain'.
- **Day vs night** could not be checked (no start times in the data).
"""


def cpkey(c):
    return c.str.split().str[0].astype(int)


def main():
    s1, w1 = build_ipl()
    s2, w2 = build_2026()
    s = pd.concat([s1.assign(src="2022-25 rolling"), s2.assign(src="2026 holdout")], ignore_index=True)
    w = pd.concat([w1.assign(src="2022-25 rolling"), w2.assign(src="2026 holdout")], ignore_index=True)
    s, w = finish(s, w)
    s, w = add_playoffs(s, w, ipl_calendar())
    pooled_s, pooled_w = s[s.balls_bowled.isin(CPS)], w[w.balls_bowled.isin(CPS)]
    s10 = s[s.balls_bowled == 60]
    inn = _ctx_extra()
    ft = inn[inn.innings == 1][["match_id", "batting_team"]].rename(columns={"batting_team": "first_team"})

    o = []
    A = o.append
    A("# Where the in-play model is good or bad (error analysis)\n")
    A("Model: **v1 ens-G1** (50/50 of the direct LightGBM model G1 and the ball simulator sim-B). Baseline: resource-ipl (a simple resource-table model). "
      "Only out-of-sample predictions are used: IPL 2022-25 (each season predicted by models trained on earlier seasons), IPL 2026 (models trained up to 2025), "
      "and non-IPL men's leagues from 2026 (the fresh holdout). Generated by `src/cricket_analytics/ml/error_report.py`.\n")
    A("How to read the tables:\n- **bias** = predicted minus actual, in runs (first innings). Positive = the model guessed too high.\n"
      "- **gap** = average predicted chase-win chance minus how often the chase really won. Negative = the model under-rates the chasing team.\n"
      "- **se** = bootstrap standard error (re-draw the matches many times to see how much the number wobbles). **FLAG** = more than 2 s.e. away from zero (and at least 8 matches). "
      "With about 20 groups in a table, about 1 flag is just luck.\n"
      "- `n 1st` / `n ch` = number of matches (not states). `%+-20` = share of first-innings forecasts within 20 runs. `right%` = share of chase states where the favourite won.\n"
      "- Numbers pool the 6, 10 and 15-over checkpoints (a match counts up to 3 times; the s.e. resamples whole matches so this is handled). The 0-over checkpoint is in the phase table.\n"
      "- `base MAE` / `base logloss` = baseline resource-ipl on the same states. Log loss: lower is better; 0.693 = coin flip.\n")
    A(f"Sample: IPL 2022-26, {s.match_id.nunique()} matches with a first innings, {w.match_id.nunique()} with a chase; reduced (rain) matches excluded.\n")

    tt = tab(pooled_s, pooled_w, "batting_team")
    A("## 1. By batting team (IPL 2022-26, 6/10/15 overs pooled)\nFirst-innings columns use the team batting first; chase columns use the chasing team.\n")
    A(f(tt))
    plot(tt.dropna(subset=["bias", "gap"]), "batting_team", "ml_err_team.png", "Bias by batting team (IPL 2022-26)")
    A("\n![team](img/ml_err_team.png)\n")

    keep = s.groupby("venue").match_id.nunique().pipe(lambda v: v[v >= 10].index)
    tv = tab(pooled_s[pooled_s.venue.isin(keep)], pooled_w[pooled_w.venue.isin(keep)], "venue")
    A("## 2. By venue (IPL venues with 10 or more matches in 2022-26)\n")
    A(f(tv))
    plot(tv.dropna(subset=["bias", "gap"]), "venue", "ml_err_venue.png", "Bias by venue (IPL 2022-26)")
    A("\n![venue](img/ml_err_venue.png)\n")
    try:
        sf, wf = finish(*build_fresh())
        sf, wf = sf[sf.balls_bowled.isin(CPS)], wf[wf.balls_bowled.isin(CPS)]
        A(f"### Non-IPL leagues, 2026 fresh set (v1 ens; {sf.match_id.nunique()} first innings, {wf.match_id.nunique()} chases; no baseline cached)\n")
        A("By competition:\n\n" + f(tab(sf, wf, "competition")))
        kf = sf.groupby("venue").match_id.nunique().pipe(lambda v: v[v >= 6].index)
        A("\nBy venue (6 or more matches; lower cut-off than the IPL because the sample is small):\n\n" + f(tab(sf[sf.venue.isin(kf)], wf[wf.venue.isin(kf)], "venue")))
    except Exception as e:  # noqa: BLE001
        A(f"\nNon-IPL fresh set: skipped ({e!r}).\n")

    A("\n## 3. By season and by phase checkpoint\n")
    A("By season (6/10/15 pooled):\n\n" + f(tab(pooled_s, pooled_w, "season_year")))
    A("\nBy checkpoint (all IPL 2022-26):\n\n" + f(tab(s, w, "cp").sort_values("cp", key=cpkey)))
    ss = pd.concat([tab(s[s.season_year == y], w[w.season_year == y], "cp").assign(season=y) for y in sorted(s.season_year.unique())])
    ss = ss.sort_values(["season", "cp"], key=lambda c: c if c.name == "season" else cpkey(c))
    A("\nSeason x checkpoint:\n\n" + f(ss[["season", "cp", "n 1st", "MAE", "bias", "flag", "n ch", "pred", "actual", "gap", "ch flag"]]))

    A("\n## 4. By type of match (6/10/15 pooled)\n")
    A("Target bucket (the target is known only after the first innings ends, so the chase columns are a fair split; the first-innings columns are a look-back):\n\n" + f(tab(pooled_s, pooled_w, "tbucket")))
    A("\nFirst-innings scoring band (by the FINAL total; this is hindsight, so a model that guesses near the average always looks 'too low' for big scores and 'too high' for small ones. "
      "Read it as how much the model shrinks toward the middle, not as a fixable bias):\n\n" + f(tab(pooled_s, pooled_w.iloc[:0].assign(band=None), "band")))
    A("\nToss decision (toss winner chose to bat or field):\n\n" + f(tab(pooled_s, pooled_w, "toss_bat")))
    A("\nPlayoffs (last 4 matches of each season, by date) vs league games:\n\n" + f(tab(pooled_s, pooled_w, "stage")))
    A("\nDay vs night: not derivable (the data has no start time), skipped.\n")

    t1, t2 = misses(s10, w, ft)
    A("## 5. Biggest misses\n")
    A("Top 10 first-innings misses at 10 overs (IPL 2022-26; miss = predicted minus actual):\n\n" + f(t1, 0))
    A("\nTop 10 most confident wrong chase calls (one per match; the most confident wrong state among 0/6/10/15 overs):\n\n" + f(t2, 3))

    A("\n## 6. What this means (plain language)\n\n" + BULLETS)
    txt = "\n".join(o)
    (DOCS / "ML_ERRORS.md").write_text(txt, encoding="utf-8")
    return txt


if __name__ == "__main__":
    main()
