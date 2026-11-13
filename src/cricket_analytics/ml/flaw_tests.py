"""Flaw hunt, part A: event test battery. Where does a model's prediction go wrong in specific game situations?

  python -m cricket_analytics.ml.flaw_tests events      # build the event table (from the ball states) -> flaw_events.parquet
  python -m cricket_analytics.ml.flaw_tests report      # run the battery for G1 / sim-B / ens-G1, print the ranked table, save csv + plots

States are the ends of overs 3..17 (balls 18..102). For every event the bias (prediction - actual; innings 1: median final total in runs,
chase: mean win probability minus actual win, in probability points) is compared with NON-event states at the SAME overs
(weighted by the event's own over mix), so the phase is not confounded. Confidence = 5-95% bootstrap over MATCHES (states of one match
move together). Out-of-sample predictions only (rolling caches / holdout caches, never in-sample).
"""

import sys

import numpy as np
import pandas as pd

from . import evaluate as ev
from . import features as F
from .dataset import OUT_DIR, load

EVENTS_PQ = OUT_DIR / "flaw_events.parquet"
KEY = ["match_id", "innings", "balls_bowled"]
OVERS = np.arange(18, 103, 6)  # over ends 3..17
WINDOWS = (6, 12, 18, 24)
CHECKPOINTS = (36, 60, 90)  # sim-B exists only here


# ---------- events from ball states ----------
def venue_shift(inn, days=730, min_long=20, min_recent=8):
    """Per match (first innings row): recent-minus-long-run mean of (first-innings total - competition level) at the venue.
    Recent = previous `days` days, long run = all earlier matches; both strictly EARLIER dates. NaN when either history is too short."""
    f = F.innings_features(inn)[["match_id", "innings", "lvl_ew"]]
    d = inn[inn.innings == 1].merge(f, on=["match_id", "innings"])
    d = d.assign(res=d.final_total - d.lvl_ew)
    ok = d[~d.reduced].sort_values("date")
    out = pd.Series(np.nan, index=d.match_id.to_numpy())
    for (gen, ven), g in d.groupby(["gender", "venue"]):
        e = ok[(ok.gender == gen) & (ok.venue == ven)]
        dt, cs = e.date.to_numpy("datetime64[D]"), np.concatenate([[0.0], np.cumsum(e.res.to_numpy())])
        q = g.date.to_numpy("datetime64[D]")
        hi = np.searchsorted(dt, q, side="left")
        lo = np.searchsorted(dt, q - np.timedelta64(days, "D"), side="left")
        long_m = np.where(hi >= min_long, cs[hi] / np.maximum(hi, 1), np.nan)
        rec_m = np.where(hi - lo >= min_recent, (cs[hi] - cs[lo]) / np.maximum(hi - lo, 1), np.nan)
        out.loc[g.match_id.to_numpy()] = rec_m - long_m
    return out.rename("venue_dev").rename_axis("match_id").reset_index()


def event_columns(s, sf, nf):
    """Event inputs for EVERY row of a state table s (sorted by match, innings, balls; one row per legal ball).
    Returns a DataFrame aligned with s: window runs / wickets, pair set-ness, balls since a set batter fell, rrr, middle-overs rate."""
    out = {}
    for c, v in F.window_cols(s, WINDOWS).items():
        out[c] = v
    out["sf"], out["nf"] = sf, nf
    out["since_set_out"] = F.pair_cols(s, sf, nf)["since_set_out"]
    r36 = s.runs.where(s.balls_bowled == 36).groupby([s.match_id, s.innings], sort=False).transform("max")
    out["mid_rr"] = np.where(s.balls_bowled >= 42, (s.runs - r36) / (s.balls_bowled - 36).clip(lower=1) * 6, np.nan)
    out["rrr"] = np.where((s.innings == 2) & (s.balls_left > 0), (s.runs_needed / s.balls_left.clip(lower=1) * 6), np.nan)
    return pd.DataFrame(out, index=s.index)


def build_events():
    states, inn = load()
    s = states[states.gender == "male"].reset_index(drop=True)
    sf, nf = F._faced(s)
    ec = event_columns(s, sf, nf)
    keep = s[KEY + ["wickets", "runs", "competition", "season_year", "date", "gender"]].join(ec)
    keep = keep[keep.balls_bowled.isin(OVERS) & ~ev.fresh_holdout_mask(keep)].drop(columns="gender")
    keep = keep.merge(venue_shift(inn), on="match_id", how="left")
    keep["match_id"] = keep.match_id.astype(str)
    keep["innings"] = keep.innings.astype(int)
    keep["balls_bowled"] = keep.balls_bowled.astype(int)
    keep.to_parquet(EVENTS_PQ)
    return keep


def load_events():
    return pd.read_parquet(EVENTS_PQ)


def thresholds(e):
    """Burst threshold r_w = 90th percentile of runs in the last w balls (IPL 2022-26 over-end states, both innings)."""
    x = e[(e.competition == "ipl") & (e.season_year >= 2022)]
    return {w: float(np.percentile(x[f"runs_l{w}"], 90)) for w in (6, 12, 18)}


def event_defs(thr):
    """name -> (mask function over the event table, innings it applies to: 1, 2 or 0 = both)."""
    d = {}
    for w in WINDOWS:
        for k in (2, 3):
            d[f"collapse {k}wk/{w}b"] = (lambda e, w=w, k=k: e[f"wk_l{w}"] >= k, 0)
    for w in (6, 12, 18):
        d[f"burst >={thr[w]:.0f}r/{w}b"] = (lambda e, w=w: e[f"runs_l{w}"] >= thr[w], 0)
    d["new pair (both <6 faced)"] = (lambda e: (e.sf < 6) & (e.nf < 6), 0)
    d["set pair (both >20 faced)"] = (lambda e: (e.sf > 20) & (e.nf > 20), 0)
    d["set batter out (last 6b)"] = (lambda e: e.since_set_out <= 5, 0)
    d["late, >=7 wkts in hand"] = (lambda e: (e.balls_bowled >= 90) & (e.wickets <= 3), 0)
    d["late, <=4 wkts in hand"] = (lambda e: (e.balls_bowled >= 90) & (e.wickets >= 6), 0)
    d["chase rrr >= 13"] = (lambda e: e.rrr >= 13, 2)
    d["chase rrr <= 6"] = (lambda e: e.rrr <= 6, 2)
    d["death start, >=6 wkts in hand"] = (lambda e: (e.balls_bowled == 90) & (e.wickets <= 4), 0)
    d["slow middle (ov 7-12 < 7/over)"] = (lambda e: (e.balls_bowled >= 42) & (e.balls_bowled <= 72) & (e.mid_rr < 7), 0)
    d["venue hotter lately (>+10)"] = (lambda e: e.venue_dev > 10, 0)
    d["venue cooler lately (<-10)"] = (lambda e: e.venue_dev < -10, 0)
    return d


# ---------- prediction frames ----------
def _norm(d):
    d = d.copy()
    d["match_id"] = d.match_id.astype(str)
    d["innings"] = d.innings.astype(int)
    d["balls_bowled"] = d.balls_bowled.astype(int)
    return d


def group_of(e):
    return np.where(e.competition == "ipl", "IPL", "nonIPL")


def g_frames(name="g1r"):
    """G1-style caches of flaw_fit (g1r = the current G1 re-run on the same code path) -> (S, W)."""
    S, W = (_norm(pd.read_parquet(OUT_DIR / f"g2_{name}_{k}.parquet")) for k in "SW")
    return S, W


def simb_frames():
    """sim-B checkpoints 36/60/90: IPL 2022-25 (s2_preds_B_ipl), IPL 2026 holdout, non-IPL 2024-25 (men's pool)."""
    a = pd.read_parquet(OUT_DIR / "s2_preds_B_ipl.parquet").assign(competition="ipl")
    b = pd.read_parquet(OUT_DIR / "holdout_simB.parquet").assign(competition="ipl")
    c = pd.read_parquet(OUT_DIR / "s2_preds_B_men_nonipl.parquet")
    d = _norm(pd.concat([a, b, c], ignore_index=True))
    d = d[d.balls_bowled.isin(CHECKPOINTS)]
    S = d[d.innings == 1][KEY + ["final_total", "q10", "q50", "q90"]]
    W = d[(d.innings == 2) & d.chase_won.notna()][KEY + ["chase_won", "win"]].rename(columns={"win": "p"})
    return S, W


def blend(a, b, kind):
    """Average of two prediction frames on their common keys (score: mean of quantiles, sorted; win: mean p)."""
    m = a.merge(b, on=KEY, suffixes=("", "_b"))
    if kind == "score":
        m[["q10", "q50", "q90"]] = np.sort((m[["q10", "q50", "q90"]].to_numpy() + m[["q10_b", "q50_b", "q90_b"]].to_numpy()) / 2, axis=1)
    else:
        m["p"] = (m.p + m.p_b) / 2
    return m[[c for c in m.columns if not c.endswith("_b")]]


def models(g="g1r"):
    """name -> (S, W). Score frames carry final_total, q50; win frames chase_won, p. G1 on every state, sim-B / ens-G1 at checkpoints."""
    gs, gw = g_frames(g)
    ss, sw = simb_frames()
    keep_s, keep_w = KEY + ["final_total", "q10", "q50", "q90"], KEY + ["chase_won", "p"]
    gs, gw = gs[keep_s], gw[keep_w]
    cp = lambda d: d[d.balls_bowled.isin(CHECKPOINTS)]  # noqa: E731
    return {"G1": (gs, gw), "sim-B": (ss[keep_s], sw[keep_w]),
            "ens-G1": (blend(cp(gs), ss[keep_s], "score")[keep_s], blend(cp(gw), sw[keep_w], "win")[keep_w])}


# ---------- the test ----------
def _agg(vals, o, m, n_m, n_o=len(OVERS)):
    """Sum of vals per (match, over) -> (n_m, n_o) matrix."""
    M = np.zeros((n_m, n_o))
    np.add.at(M, (m, o), vals)
    return M


def excess(mask, err, extra, match_idx, over_idx, B=2000, seed=0):
    """Event minus matched non-event, for state arrays: mask (event), err (signed error), extra (a second loss, e.g. |err| or log loss).
    Matched = the non-event mean per over, averaged with the event's over mix. Returns a dict: n states / matches, event mean, matched
    non-event mean, difference with 5-95% bootstrap over matches (and a z score), for err ('bias_*') and extra ('loss_*')."""
    n_m = int(match_idx.max()) + 1
    out = {"n_states": int(mask.sum()), "n_matches": int(len(np.unique(match_idx[mask])))}
    N1, N0 = _agg(mask.astype(float), over_idx, match_idx, n_m), _agg((~mask).astype(float), over_idx, match_idx, n_m)
    c = np.random.default_rng(seed).multinomial(n_m, np.ones(n_m) / n_m, size=B).astype(float)
    for lab, v in (("bias", err), ("loss", extra)):
        S1, S0 = _agg(np.where(mask, v, 0.0), over_idx, match_idx, n_m), _agg(np.where(~mask, v, 0.0), over_idx, match_idx, n_m)

        def stat(w):
            n1, n0, s1, s0 = (w @ X for X in (N1, N0, S1, S0))
            ev_ = s1.sum(-1) / np.maximum(n1.sum(-1), 1)
            wt = n1 / np.maximum(n1.sum(-1, keepdims=True), 1)
            return ev_, (wt * s0 / np.maximum(n0, 1)).sum(-1)

        e0, r0 = stat(np.ones((1, n_m)))
        eb, rb = stat(c)
        d = eb - rb
        out.update({f"{lab}_event": float(e0[0]), f"{lab}_rest": float(r0[0]), f"{lab}_diff": float(e0[0] - r0[0]),
                    f"{lab}_lo": float(np.percentile(d, 5)), f"{lab}_hi": float(np.percentile(d, 95)),
                    f"{lab}_z": float((e0[0] - r0[0]) / (d.std() + 1e-12))})
    return out


def run_battery(model_frames, ev_tab, thr=None, min_matches=8, B=2000, groups=("IPL", "nonIPL")):
    """model_frames: name -> (S, W). Returns a long DataFrame: one row per (model, group, kind, event)."""
    thr = thr or thresholds(ev_tab)
    defs = event_defs(thr)
    et = ev_tab.assign(group=group_of(ev_tab))
    rows = []
    for mname, (S, W) in model_frames.items():
        for kind, P in (("inn1", S), ("chase", W)):
            m = P.merge(et, on=KEY, how="inner")
            m = m[m.innings == (1 if kind == "inn1" else 2)].reset_index(drop=True)
            if kind == "inn1":
                err = (m.q50 - m.final_total).to_numpy()
                extra = np.abs(err)
            else:
                p, y = np.clip(m.p.to_numpy(), 1e-6, 1 - 1e-6), m.chase_won.to_numpy()
                err, extra = p - y, -(y * np.log(p) + (1 - y) * np.log(1 - p))
            for g in groups:
                sel = (m.group == g).to_numpy()
                if not sel.any():
                    continue
                mm = m[sel]
                mi = pd.factorize(mm.match_id)[0]
                oi = ((mm.balls_bowled.to_numpy() - 18) // 6).astype(int)
                for en, (fn, inn_) in defs.items():
                    if inn_ and ((kind == "inn1") != (inn_ == 1)):
                        continue
                    mask = fn(mm).fillna(False).to_numpy().astype(bool)
                    if len(np.unique(mi[mask])) < min_matches:
                        continue
                    rows.append({"model": mname, "group": g, "kind": kind, "event": en, **excess(mask, err[sel], extra[sel], mi, oi, B)})
    return pd.DataFrame(rows)


def flaw_table(res, model="G1"):
    """One model's rows: significant biases (interval excludes 0) first, then by |z|."""
    r = res[res.model == model].copy()
    r["sig"] = (r.bias_lo > 0) | (r.bias_hi < 0)
    r["az"] = r.bias_z.abs()
    return r.sort_values(["sig", "az"], ascending=False)


def fmt(r):
    sc, u = (1, "runs") if r.kind == "inn1" else (100, "pp")
    return (f"{r.event} | {r.group} | {r.kind} | n={r.n_matches}m/{r.n_states}s | event {r.bias_event * sc:+.1f} vs rest {r.bias_rest * sc:+.1f} | "
            f"excess {r.bias_diff * sc:+.1f} [{r.bias_lo * sc:+.1f}, {r.bias_hi * sc:+.1f}] {u}")


def plot(res, path, model="G1"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axs = plt.subplots(1, 2, figsize=(13, 8))
    for ax, kind, sc, lab in ((axs[0], "inn1", 1, "runs (pred - actual final)"), (axs[1], "chase", 100, "win probability points (pred - actual)")):
        r = res[(res.model == model) & (res.kind == kind)]
        r = r.assign(lbl=r.event + " [" + r.group + "]").sort_values("bias_diff")
        ax.errorbar(r.bias_diff * sc, range(len(r)), xerr=[(r.bias_diff - r.bias_lo) * sc, (r.bias_hi - r.bias_diff) * sc], fmt="o", ms=3, lw=1)
        ax.axvline(0, color="grey", ls="--")
        ax.set_yticks(range(len(r)))
        ax.set_yticklabels(r.lbl, fontsize=6)
        ax.set(title=f"{model} {'first innings' if kind == 'inn1' else 'chase'}: event minus matched non-event", xlabel=lab)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def report(g="g1r", B=2000):
    e = load_events()
    res = run_battery(models(g), e, B=B)
    res.to_csv(OUT_DIR / "flaw_battery.csv", index=False)
    print(f"thresholds {thresholds(e)}")
    for m in ("G1", "sim-B", "ens-G1"):
        t = flaw_table(res, m)
        print(f"\n### {m}: significant first, by |z| (top 30 of {len(t)})")
        for r in t.head(30).itertuples():
            print(("* " if r.sig else "  ") + fmt(r))
    plot(res, ev.IMG_DIR / "ml_flaw_events_g1.png", "G1")
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["events"]:
        print(build_events().shape)
    elif a[:1] == ["report"]:
        report()
