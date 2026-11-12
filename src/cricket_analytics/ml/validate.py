"""S5 part 1: head-to-head validation on identical states, bias audit, noise floor, tails, famous-match curves.

  python -m cricket_analytics.ml.validate [h2h bias noise tails curves lc] [--extra G1=data/external/ml/direct_pool_g1]

Models compared on the same (match_id, innings, balls_bowled) rows (IPL test 2022-25, checkpoints 0/6/10/15 overs):
resource-ipl (baseline), G0 (direct LightGBM, global pool), sim-B (ball simulator), ens (G0 + sim-B average) and any
`--extra name=prefix` (reads <prefix>_score.parquet and <prefix>_win.parquet in the direct.py format).
The 2026 holdout is never read here. Output is printed (markdown) and saved to data/external/ml/s5_part1.md.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from . import evaluate as ev
from .baselines import md as _md
from .dataset import OUT_DIR, load
from .sim_report import bootstrap  # paired bootstrap over matches, mean of 4 checkpoints

KEYS = ["match_id", "innings", "balls_bowled"]
CP = (0, 36, 60, 90)
QC = ["q10", "q50", "q90"]
BASE, G0, G1, SIM, ENS, ENS1 = "resource-ipl", "G0", "G1", "sim-B", "ens", "ens-G1"
REPORT = OUT_DIR / "s5_part1.md"


# ---------- loading and alignment ----------
def align(frames, keys=KEYS):
    """Keep only rows whose key is present in EVERY frame (dict name -> df), sorted by key so rows line up 1:1."""
    common = None
    for df in frames.values():
        k = pd.MultiIndex.from_frame(df[keys].drop_duplicates())
        common = k if common is None else common.intersection(k)
    out = {}
    for n, df in frames.items():
        d = df.set_index(keys).loc[common].reset_index().sort_values(keys).reset_index(drop=True)
        out[n] = d
    return out


def ensemble(a, b, kind, keys=KEYS):
    """Average two aligned prediction frames. Score: mean of quantiles, then sorted (so q10<=q50<=q90). Win: mean of p."""
    a, b = a.sort_values(keys).reset_index(drop=True), b.sort_values(keys).reset_index(drop=True)
    assert (a[keys].to_numpy() == b[keys].to_numpy()).all(), "ensemble inputs are not aligned"
    out = a.copy()
    if kind == "score":
        q = np.sort((a[QC].to_numpy() + b[QC].to_numpy()) / 2, axis=1)
        out[QC] = q
    else:
        out["p"] = (a.p.to_numpy() + b.p.to_numpy()) / 2
    return out


def _direct(prefix, name, kind):
    d = pd.read_parquet(OUT_DIR / f"{prefix}_{kind}.parquet" if not str(prefix).endswith(".parquet") else prefix)
    d = d[d.balls_bowled.isin(CP)]
    return d.assign(model=name)


def load_g1():
    """G1 (improved direct model, s4b.py): conformal-widened first-innings quantiles and chase probabilities at the checkpoints."""
    from .s4b import conformalise

    S, V, W = (pd.read_parquet(OUT_DIR / f"s4b_g1_{k}.parquet") for k in "SVW")
    S = conformalise(S, V, G1)
    return S[S.balls_bowled.isin(CP)].assign(model=G1), W[W.balls_bowled.isin(CP)].assign(model=G1)


def load_models(extra=None):
    """Returns (score, win, meta): dicts model -> aligned frames (innings 1 score; innings 2 win) and per-row meta."""
    s2 = pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet")
    st = {BASE: _direct("direct_baseline", BASE, "score"), G0: _direct("direct_pool_global", G0, "score"),
          SIM: s2[s2.innings == 1].assign(model=SIM)}
    wn = {BASE: _direct("direct_baseline", BASE, "win"), G0: _direct("direct_pool_global", G0, "win"),
          SIM: s2[s2.innings == 2].rename(columns={"win": "p"}).assign(model=SIM)}
    for spec in extra or []:
        n, pre = spec.split("=", 1)
        st[n], wn[n] = _direct(pre, n, "score"), _direct(pre, n, "win")
    if (OUT_DIR / "s4b_g1_S.parquet").exists() and G1 not in st:  # G1 = s4b "g1" + conformal widening (inner-fold deltas)
        st[G1], wn[G1] = load_g1()
    wn = {k: v[v.chase_won.notna()] for k, v in wn.items()}
    st, wn = align(st), align(wn)
    meta_src = pd.read_parquet(OUT_DIR / "direct_pool_global_score.parquet")
    meta_w = pd.read_parquet(OUT_DIR / "direct_pool_global_win.parquet")
    meta = pd.concat([meta_src, meta_w]).drop_duplicates(KEYS)[KEYS + ["venue", "batting_team", "date", "season_year"]]
    cols = ["match_id", "innings", "balls_bowled", "final_total", "chase_won", "q10", "q50", "q90", "p"]
    ens_s, ens_w = ensemble(st[G0], st[SIM], "score"), ensemble(wn[G0], wn[SIM], "win")
    st[ENS], wn[ENS] = ens_s.assign(model=ENS), ens_w.assign(model=ENS)
    if G1 in st:  # second ensemble: G1 + sim-B
        st[ENS1], wn[ENS1] = ensemble(st[G1], st[SIM], "score").assign(model=ENS1), ensemble(wn[G1], wn[SIM], "win").assign(model=ENS1)
    st = {k: v[[c for c in cols if c in v.columns]] for k, v in st.items()}
    wn = {k: v[[c for c in cols if c in v.columns]] for k, v in wn.items()}
    meta = add_context(meta)
    return st, wn, meta


def add_context(meta):
    """Add toss and target info (per match / row) to the meta frame."""
    from ..db import query

    t = query("select match_id, toss_winner, toss_decision from matches")
    meta = meta.merge(t, on="match_id", how="left")
    meta["toss_bat"] = np.where(meta.toss_decision == "bat", "toss winner bats first", "toss winner fields first")
    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet")[["match_id", "innings", "target", "first_total"]]
    meta = meta.merge(inn[inn.innings == 2][["match_id", "target"]], on="match_id", how="left")
    meta["tbucket"] = pd.cut(meta.target, [0, 159.5, 189.5, 219.5, 999], labels=["<160", "160-189", "190-219", "220+"]).astype(str)
    return meta


# ---------- head-to-head ----------
def per_checkpoint(frames, kind):
    rows = []
    for name, g in frames.items():
        cp = []
        for b in CP:
            s = g[g.balls_bowled == b]
            r = ev.score_metrics(s.final_total, s.q10, s.q50, s.q90) if kind == "score" else ev.win_metrics(s.chase_won, s.p)
            rows.append({"model": name, "cp": f"{b // 6} ov", "n": len(s), **r})
            cp.append(r)
        rows.append({"model": name, "cp": "mean of 4", "n": len(g), **{k: np.mean([c[k] for c in cp]) for k in cp[0]}})
    return pd.DataFrame(rows)


def best_of(tab, col):
    m = tab[tab.cp == "mean of 4"]
    return m.sort_values(col).model.iloc[0]


def md(df, nd=3):
    return _md(df, nd)


def h2h(st, wn, log):
    ts, tw = per_checkpoint(st, "score"), per_checkpoint(wn, "win")
    log("\n#### First-innings score (n = states per checkpoint)\n" + md(ts[ts.cp == "mean of 4"], 3))
    log("\nBy checkpoint:\n" + md(ts[ts.cp != "mean of 4"].pivot(index="model", columns="cp", values="mae").reset_index()[["model", "0 ov", "6 ov", "10 ov", "15 ov"]], 2).replace("\n", "\n"))
    log("\n#### Chase win probability\n" + md(tw[tw.cp == "mean of 4"], 3))
    log("\nBy checkpoint (log loss):\n" + md(tw[tw.cp != "mean of 4"].pivot(index="model", columns="cp", values="logloss").reset_index()[["model", "0 ov", "6 ov", "10 ov", "15 ov"]], 3))
    bs, bw = best_of(ts, "pinball"), best_of(tw, "logloss")
    log(f"\nBest of all models (ensembles included): score = {bs} (lowest mean-of-4 pinball), win = {bw} (lowest mean-of-4 log loss)")
    single = [m for m in (G0, G1, SIM) if m in st]
    bs1 = best_of(ts[ts.model.isin(single)], "pinball")
    pairs = [(G0, SIM)] + ([(G1, SIM), (G1, G0), (ENS1, bs1)] if G1 in st else []) + [(ENS, bs1), (bs, BASE)]
    pairs = list(dict.fromkeys(p for p in pairs if p[0] != p[1]))
    rows = []
    for a, b in pairs:
        r = {"comparison": f"{a} - {b}"}
        for kind, lab in (("mae", "MAE"), ("pinball", "pinball")):
            p = bootstrap(st[a], st[b], kind)
            r[lab] = f"{p[0]:+.2f} [{p[1]:+.2f}, {p[2]:+.2f}]"
        for kind, lab, fr in (("logloss", "log loss", wn), ("brier", "Brier", wn)):
            p = bootstrap(fr[a], fr[b], kind)
            r[lab] = f"{p[0]:+.3f} [{p[1]:+.3f}, {p[2]:+.3f}]"
        rows.append(r)
    log("\n#### Bootstrap over matches (2000 resamples, 5-95%, mean-of-4 difference; negative = first model better)\n" + pd.DataFrame(rows).pipe(md))
    return ts, tw, bs, bw


# ---------- bias audit ----------
def _boot_se(g, f, n=400, seed=0):
    """Bootstrap s.e. of f(rows) with matches resampled."""
    rng = np.random.default_rng(seed)
    m = g.match_id.to_numpy()
    um, inv = np.unique(m, return_inverse=True)
    idx = [np.flatnonzero(inv == i) for i in range(len(um))]
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(um), len(um))
        vals.append(f(g.iloc[np.concatenate([idx[i] for i in pick])]))
    return float(np.std(vals))


GROUPS = ["batting_team", "venue", "checkpoint", "season_year", "toss_bat", "tbucket"]


def audit(frames, meta, kind, model, min_matches=8, log=print):
    """Bias (score: median - actual in runs; win: mean p - win rate) and calibration by group; flag |bias| > 2 s.e."""
    g = frames[model].merge(meta.drop(columns=["season_year"], errors="ignore").drop_duplicates(KEYS), on=KEYS, how="left")
    g = g.merge(meta[KEYS + ["season_year"]].drop_duplicates(KEYS), on=KEYS, how="left")
    g["checkpoint"] = (g.balls_bowled // 6).astype(int).astype(str) + " ov"
    if kind == "score":
        g["err"], g["cov"] = g.q50 - g.final_total, ((g.final_total >= g.q10) & (g.final_total <= g.q90)).astype(float)
        fb = lambda d: d.err.mean()  # noqa: E731
        groups = [x for x in GROUPS if x != "tbucket"]
    else:
        g["err"] = g.p - g.chase_won
        g["ll"] = ev.log_loss(g.chase_won, g.p) if False else -(g.chase_won * np.log(g.p.clip(1e-6, 1 - 1e-6)) + (1 - g.chase_won) * np.log(1 - g.p.clip(1e-6, 1 - 1e-6)))
        fb = lambda d: d.err.mean()  # noqa: E731
        groups = GROUPS
    rows = []
    for col in groups:
        for val, d in g.groupby(col):
            nm = d.match_id.nunique()
            if col == "venue" and nm < min_matches:
                continue
            se = _boot_se(d, fb) if nm >= 5 else np.nan
            r = {"group": col, "value": val, "n_states": len(d), "n_matches": nm, "bias": fb(d), "se": se}
            r["flag"] = bool(se == se and abs(r["bias"]) > 2 * se and nm >= min_matches)
            if kind == "score":
                r["cov80"], r["mae"] = d["cov"].mean(), d.err.abs().mean()
            else:
                r["logloss"], r["obs_rate"] = d.ll.mean(), d.chase_won.mean()
            rows.append(r)
    out = pd.DataFrame(rows)
    return out


# ---------- noise floor ----------
def noise_floor(st, wn, best_s, best_w, log):
    s2 = pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet")
    s2 = s2[s2.innings == 1]
    rows = []
    for b in CP:
        d = st[best_s][st[best_s].balls_bowled == b].merge(s2[KEYS + ["sd", "mean"]], on=KEYS)
        var = d.final_total.var(ddof=0)
        mse = ((d.q50 - d.final_total) ** 2).mean()
        rows.append({"checkpoint": f"{b // 6} ov", "n": len(d), "SD of final totals": np.sqrt(var), f"RMSE {best_s}": np.sqrt(mse),
                     f"share explained {best_s}": 1 - mse / var, "sim mean SD": np.sqrt((d.sd ** 2).mean()),
                     "sim RMSE (its mean)": np.sqrt(((d["mean"] - d.final_total) ** 2).mean()),
                     "ceiling share (1 - sim var / var)": 1 - (d.sd ** 2).mean() / var})
    ns = pd.DataFrame(rows)
    log("\n#### Noise floor, first-innings final score\n" + md(ns, 3))
    w = wn[best_w]
    rows = []
    for b in CP:
        d = w[w.balls_bowled == b]
        p = d.p.clip(1e-6, 1 - 1e-6)
        ent = -(p * np.log(p) + (1 - p) * np.log(1 - p)).mean()
        rows.append({"checkpoint": f"{b // 6} ov", "n": len(d), "log loss": ev.log_loss(d.chase_won, d.p), "self-entropy (if probs were exact)": ent,
                     "coin flip": 0.693, "mean |p-0.5|": (d.p - 0.5).abs().mean()})
    log("\n#### Noise floor, chase win probability (best win model " + best_w + ")\n" + md(pd.DataFrame(rows), 3))
    return ns


# ---------- tails / upsets ----------
def match_info():
    inn = pd.read_parquet(OUT_DIR / "states_innings.parquet")
    inn = inn[(inn.competition == "ipl") & ~inn.reduced & inn.season_year.between(2022, 2025)]
    a, b = inn[inn.innings == 1], inn[inn.innings == 2]
    m = a[["match_id", "date", "venue", "batting_team", "final_total", "season_year"]].rename(columns={"batting_team": "team1", "final_total": "score1"})
    m = m.merge(b[["match_id", "batting_team", "final_total", "target", "chase_won", "winner"]].rename(columns={"batting_team": "chaser", "final_total": "score2"}), on="match_id")
    return m


def _ids(df):
    """balls.parquet keeps match_id as text; align to the int ids used elsewhere."""
    return df.assign(match_id=pd.to_numeric(df.match_id))


def tails(wn, model, log):
    """Under-10% chases that won / over-90% chases that lost, with expected counts, plus a ball-level G0 scan."""
    mi = match_info()
    w = wn[model].merge(mi[["match_id", "date", "chaser", "team1", "venue", "target"]], on="match_id")
    rows = []
    for lab, sel, obs, exp in (("p < 10%", w.p < 0.1, lambda d: d.chase_won.sum(), lambda d: d.p.sum()),
                               ("p > 90%", w.p > 0.9, lambda d: (1 - d.chase_won).sum(), lambda d: (1 - d.p).sum())):
        d = w[sel]
        rows.append({"model": model, "band": lab, "states": len(d), "matches": d.match_id.nunique(),
                     "surprises": float(obs(d)), "expected": float(exp(d))})
    log(f"\n#### Tails at the 4 checkpoints ({model}; surprise = chase won from <10% or lost from >90%)\n" + md(pd.DataFrame(rows), 2))
    lst = []
    for lab, d in (("won from <10%", w[(w.p < 0.1) & (w.chase_won == 1)]), ("lost from >90%", w[(w.p > 0.9) & (w.chase_won == 0)])):
        for r in d.itertuples():
            lst.append({"what": lab, "date": str(r.date)[:10], "match": f"{r.team1} v {r.chaser}", "target": int(r.target),
                        "state": f"{int(r.balls_bowled // 6)} ov", "p(chase wins)": round(r.p, 3)})
    lst = pd.DataFrame(lst).sort_values(["what", "p(chase wins)"])
    log("\nEvery surprise (checkpoint states):\n" + md(lst, 3))
    g = pd.read_parquet(OUT_DIR / "direct_pool_global_win.parquet")
    g = g[g.competition == "ipl"]
    mm = g.groupby("match_id").agg(minp=("p", "min"), maxp=("p", "max"), won=("chase_won", "first")).reset_index()
    log(f"\nG0 at ANY ball (n = {len(mm)} chases): min p < 10% and the chase won: {int(((mm.minp < .1) & (mm.won == 1)).sum())}; "
        f"max p > 90% and the chase lost: {int(((mm.maxp > .9) & (mm.won == 0)).sum())}; "
        f"(min p < 5% and won: {int(((mm.minp < .05) & (mm.won == 1)).sum())}; max p > 95% and lost: {int(((mm.maxp > .95) & (mm.won == 0)).sum())})")
    return lst, mm


def freak(log):
    """Overs with >=5 sixes or >=30 runs in test seasons, and what G0 said just before / after them."""
    from .ball_model import load_balls

    b = load_balls()
    b = b[(b.competition == "ipl") & b.season_year.between(2022, 2025) & ~b.reduced & (b.innings <= 2)]
    b = b.assign(six=(b.runs_batter == 6).astype(int))
    ov = b.groupby(["match_id", "innings", "over_n"]).agg(sixes=("six", "sum"), runs=("runs_total", "sum"), start=("balls_bowled", "min")).reset_index()
    ov["end"] = ov.groupby(["match_id", "innings"]).start.shift(-1)
    fr = ov[((ov.sixes >= 5) | (ov.runs >= 30)) & ov.end.notna()]
    sg = pd.read_parquet(OUT_DIR / "direct_pool_global_score.parquet")
    sg = sg[sg.competition == "ipl"].set_index(["match_id", "innings", "balls_bowled"])
    wg = pd.read_parquet(OUT_DIR / "direct_pool_global_win.parquet")
    wg = wg[wg.competition == "ipl"].set_index(["match_id", "innings", "balls_bowled"])
    rows = []
    for r in fr.itertuples():
        k0, k1 = (r.match_id, r.innings, float(r.start)), (r.match_id, r.innings, float(r.end))
        if r.innings == 1 and k0 in sg.index and k1 in sg.index:
            a, c = sg.loc[k0], sg.loc[k1]
            rows.append({"innings": 1, "shift": c.q50 - a.q50, "inside": float(a.q10 <= a.final_total <= a.q90), "dp": np.nan})
        elif r.innings == 2 and k0 in wg.index and k1 in wg.index:
            rows.append({"innings": 2, "shift": np.nan, "inside": np.nan, "dp": wg.loc[k1].p - wg.loc[k0].p})
    d = pd.DataFrame(rows)
    s1, s2 = d[d.innings == 1], d[d.innings == 2]
    log(f"\n#### Freak overs in IPL 2022-25 (>=5 sixes or >=30 runs): {len(fr)} overs ({int((fr.sixes >= 5).sum())} with >=5 sixes, {int((fr.runs >= 30).sum())} with >=30 runs); "
        f"{len(s1)} in innings 1 and {len(s2)} in chases had G0 states before and after")
    log(f"- innings 1: G0's median final-score forecast moved {s1['shift'].mean():+.1f} runs across the over on average; the final total was inside "
        f"the 10-90% range G0 gave just before the over in {s1.inside.mean():.0%} of cases (target 80%).")
    log(f"- chases: G0 win probability moved {s2.dp.mean():+.3f} on average over such an over (mean |move| {s2.dp.abs().mean():.3f}; "
        f"all overs: {typical_move(wg):.3f}).")
    return d


def typical_move(wg):
    d = wg.reset_index().sort_values(["match_id", "balls_bowled"])
    d = d[d.balls_bowled % 6 == 0]
    return d.groupby("match_id").p.diff().abs().mean()


def last_over(log):
    """Chases entering the 20th over needing 1-10: how often the defence held, vs G0."""
    from .dataset import load

    states, _ = load()
    s = states[(states.competition == "ipl") & (states.innings == 2) & (states.balls_bowled == 114) & states.runs_needed.between(1, 10)][["match_id", "runs_needed"]]
    g = pd.read_parquet(OUT_DIR / "direct_pool_global_win.parquet")
    g = g[(g.competition == "ipl") & (g.balls_bowled == 114)].merge(s, on="match_id")
    held = int((g.chase_won == 0).sum())
    g1p = OUT_DIR / "s4b_g1_W.parquet"
    if g1p.exists():
        h = pd.read_parquet(g1p)
        h = h[h.balls_bowled == 114].merge(g[["match_id"]], on="match_id")
        log(f"G1 on the same {len(h)} chases: expected holds {float((1 - h.p).sum()):.1f}")
    log(f"\n#### Last-over defences (IPL 2022-25, chases entering over 20 needing 1-10 runs, n = {len(g)}): "
        f"defender held {held} times; G0 expected {float((1 - g.p).sum()):.1f}")
    return g


# ---------- famous matches ----------
def pick_matches(mm):
    mi = match_info()
    ids = list(mi[mi.chase_won == 1].sort_values("target", ascending=False).match_id.iloc[:2])
    c = mm[(mm.won == 1) & ~mm.match_id.isin(ids)].sort_values("minp").match_id.iloc[0]
    k = mm[(mm.won == 0) & ~mm.match_id.isin(ids)].sort_values("maxp", ascending=False).match_id.iloc[0]
    why = [(ids[0], "highest successful chase"), (ids[1], "second-highest successful chase"),
           (c, "biggest comeback (lowest G0 win prob of a chase that won)"), (k, "biggest collapse (highest G0 win prob of a chase that lost)")]
    return mi.set_index("match_id").loc[[w[0] for w in why]].reset_index().assign(why=[w[1] for w in why])


def curves(mm, log, n_sims=600):
    import pickle

    from .ball_model import load_balls
    from .simulate import fill_missing_batter, simulate, start_states

    plt = ev._plt()
    sel = pick_matches(mm)
    balls_all = load_balls()
    g = pd.read_parquet(OUT_DIR / "direct_pool_global_win.parquet")
    g1p = OUT_DIR / "s4b_g1_W.parquet"
    g1 = pd.read_parquet(g1p) if g1p.exists() else None
    for r in sel.itertuples():
        with open(OUT_DIR / "models" / f"ball_B_ipl_{int(r.season_year)}.pkl", "rb") as f:
            model = pickle.load(f)
        bl = balls_all[balls_all.match_id == r.match_id]
        ps, ks = [], []
        for ov in range(20):
            st = start_states(bl, [(r.match_id, 2)], 6 * ov)
            if len(st) == 0:
                continue
            ps.append(float(simulate(model, fill_missing_batter(st, model), n=n_sims, seed=ov)["win"][0]))
            ks.append(ov)
        gg = g[(g.match_id == r.match_id) & (g.balls_bowled % 6 == 0) & (g.balls_bowled < 120)].sort_values("balls_bowled")
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.axhline(0.5, color="grey", ls=":")
        ax.plot(gg.balls_bowled / 6, gg.p, "o-", label="G0 (direct LightGBM)")
        ax.plot(ks, ps, "s-", label="sim B (ball simulator)")
        if g1 is not None:
            h = g1[(g1.match_id == r.match_id) & (g1.balls_bowled % 6 == 0) & (g1.balls_bowled < 120)].sort_values("balls_bowled")
            ax.plot(h.balls_bowled / 6, h.p, "^-", label="G1 (improved direct)", ms=4)
        res = "chase WON" if r.chase_won == 1 else "chase LOST"
        ax.set(xlabel="overs bowled in the chase", ylabel="P(chasing team wins)", ylim=(0, 1),
               title=f"{r.chaser} chasing {int(r.target)} v {r.team1}, {str(r.date)[:10]} ({res})\n{r.why}")
        ax.title.set_fontsize(9)
        ax.legend(loc="best", fontsize=8)
        p = ev.IMG_DIR / f"ml_curve_{r.match_id}.png"
        fig.savefig(p, dpi=110, bbox_inches="tight")
        plt.close(fig)
        log(f"- {r.match_id} ({str(r.date)[:10]}, {r.team1} {int(r.score1)} v {r.chaser} {int(r.score2)}, {res}; {r.why}): "
            f"G0 min/max {gg.p.min():.2f}/{gg.p.max():.2f}, sim min/max {min(ps):.2f}/{max(ps):.2f}")


# ---------- learning curve ----------
def learning_curve(log, test_year=2025):
    """Train G0 on the last N seasons (2/4/8/all) before test_year, test IPL test_year. Fixed config and iterations of that fold."""
    import json

    from . import direct as D
    from . import features as F
    from .baselines import usable

    states, inn = load()
    feat = D.prep(F.build_features(states, inn, 100.0, 10.0))
    tuned = json.loads((OUT_DIR / "direct_tuned.json").read_text())[str(test_year)]
    cols = F.FEATURE_SETS["full"]
    test = usable(feat[(feat.season_year == test_year) & (feat.competition == "ipl")])
    t1, t2 = test[test.innings == 1], D.win_rows(test)
    rows = []
    for N in (2, 4, 8, 99):
        tr, w = D.pool_rows(feat, "global", test_year)
        keep = (tr.season_year >= test_year - N).to_numpy()
        tr, w = tr[keep], w[keep]
        sm = D.fit_score(tr, w, cols, D.CONFIGS[tuned["score_cfg"]], rounds={q: tuned["score_iters"][str(q)] for q in D.QS})
        wm, _ = D.fit_win(tr, w, cols, D.CONFIGS[tuned["win_cfg"]], rounds=tuned["win_iters"])
        p = D.predict_score(sm, t1, cols)
        sc = ev.score_metrics(t1.final_total, p.q10, p.q50, p.q90, ev.match_weights(t1))
        d, _y = D.score_rows(tr[tr.competition == "ipl"])
        ptr = D.predict_score(sm, d, cols)
        rows.append({"train seasons": "all" if N == 99 else f"last {N}", "train rows": len(tr), "test MAE": sc["mae"], "test pinball": sc["pinball"],
                     "test bias": sc["bias"], "train MAE (IPL rows)": ev.mae(d.final_total, ptr.q50, ev.match_weights(d)),
                     "chase log loss": ev.log_loss(t2.chase_won, wm.predict(t2[cols]), ev.match_weights(t2))})
        log(f"learning curve {rows[-1]}")
    r = pd.DataFrame(rows)
    log(f"\n#### Learning curve for G0 (test IPL {test_year}, innings-weighted)\n" + md(r, 3))
    return r


# ---------- plots ----------
def plots(ts, tw, st, wn):
    plt = ev._plt()
    cps = ["0 ov", "6 ov", "10 ov", "15 ov"]
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    for i, (tab, col, ttl) in enumerate(((ts, "mae", "first-innings MAE (runs)"), (tw, "logloss", "chase log loss"))):
        for j, n in enumerate(st):
            ax[i].bar(np.arange(4) + (j - len(st) / 2 + 0.5) * 0.8 / len(st), [tab[(tab.model == n) & (tab.cp == c)][col].iloc[0] for c in cps], 0.8 / len(st), label=n)
        ax[i].set_xticks(range(4), cps)
        ax[i].set_title(ttl)
    ax[0].legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_s5_h2h.png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(4.8, 4.8))
    ax.plot([0, 1], [0, 1], "--", color="grey")
    for n in wn:
        t = ev.reliability_table(wn[n].chase_won, wn[n].p, 10)
        ax.plot(t.pred, t.obs, "o-", label=n, ms=4)
    ax.set(xlabel="predicted chase win prob", ylabel="observed win rate", title="reliability, same states")
    ax.legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_s5_reliability.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def plot_bias(meta, st, bs):
    plt = ev._plt()
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    for a, col in zip(ax, ["checkpoint", "season_year", "toss_bat"]):
        for j, m in enumerate(dict.fromkeys([BASE, G0, bs])):
            t = audit({m: st[m]}, meta, "score", m)
            t = t[t.group == col]
            a.errorbar(np.arange(len(t)) + j * 0.2 - 0.2, t.bias, yerr=2 * t.se, fmt="o", label=m, ms=4)
        a.axhline(0, color="grey", ls=":")
        a.set_xticks(range(len(t)), [str(v)[:14] for v in t.value], rotation=15, fontsize=7)
        a.set_title(f"bias by {col} (runs, +-2 s.e.)", fontsize=9)
    ax[0].legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_s5_bias.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def plot_noise(nf):
    plt = ev._plt()
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    x = [0, 6, 10, 15]
    ax.plot(x, nf.iloc[:, 4], "o-", label="best model: share of variance explained")
    ax.plot(x, nf.iloc[:, 7], "s--", label="ceiling implied by simulator spread")
    ax.set(xlabel="overs bowled", ylabel="share of final-score variance", ylim=(0, 1), title="how much of the final score is predictable")
    ax.legend(fontsize=7)
    fig.savefig(ev.IMG_DIR / "ml_s5_noise.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


def learning_plot(r):
    plt = ev._plt()
    fig, ax = plt.subplots(figsize=(5, 3.6))
    ax.plot(r["train seasons"], r["test MAE"], "o-", label="test MAE (2025)")
    ax.plot(r["train seasons"], r["train MAE (IPL rows)"], "s--", label="train MAE (IPL rows)")
    ax.set(ylabel="runs", title="G0 learning curve")
    ax.legend(fontsize=8)
    fig.savefig(ev.IMG_DIR / "ml_s5_learning.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


STEPS = ["h2h", "bias", "noise", "tails", "curves", "lc"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="*", default=STEPS)
    ap.add_argument("--extra", action="append", default=[], help="name=path prefix of a direct-format prediction pair (e.g. G1=...)")
    a = ap.parse_args()
    out = []

    def log(m):
        print(m, flush=True)
        out.append(m)

    st, wn, meta = load_models(a.extra)
    log(f"aligned rows: score {len(st[G0])} (innings 1), win {len(wn[G0])} (innings 2); models {list(st)}")
    ts, tw, bs, bw = h2h(st, wn, log)
    plots(ts, tw, st, wn)
    if "noise" in a.steps:
        plot_noise(noise_floor(st, wn, bs, bw, log))
    if "bias" in a.steps:
        for kind, fr, best in (("score", st, bs), ("win", wn, bw)):
            for m in dict.fromkeys([BASE, best]):
                t = audit(fr, meta, kind, m)
                log(f"\n#### Bias audit {kind}, {m}: flagged groups ({int(t.flag.sum())} of {len(t)}; about {0.05 * len(t):.0f} expected by chance at 2 s.e.)\n" + md(t[t.flag], 3))
                log(f"\nSeason / checkpoint / toss / target groups, {kind}, {m}:\n" + md(t[t.group.isin(["season_year", "checkpoint", "toss_bat", "tbucket"])].drop(columns="flag"), 3))
                t.to_csv(OUT_DIR / f"s5_audit_{kind}_{m}.csv", index=False)
        plot_bias(meta, st, bs)
    if "tails" in a.steps or "curves" in a.steps:
        lst, mm = tails(wn, bw, log)
        for m in dict.fromkeys([SIM, G1, ENS1, ENS]):
            if m != bw and m in wn:
                tails(wn, m, log)
        freak(log)
        last_over(log)
        if "curves" in a.steps:
            log("\n#### Famous matches (win-probability curves)")
            curves(mm, log)
    if "lc" in a.steps:
        learning_plot(learning_curve(log))
    REPORT.write_text("\n".join(out), encoding="utf-8")
