"""Matchup predictor: what happens per ball when batter X faces bowler Y (or bowling type T) in phase P at match state S.

Seven outcomes of a ball the batter faces (wides excluded): dot, 1, 2, 3 (5s folded in), 4, 6, wicket (the STRIKER is out,
any way). Everything is a probability vector over those 7 classes.

Method (empirical Bayes, one multiplicative layer at a time, broad -> specific). Start from the league probability of the
(era, phase) cell. Each layer then looks at a group of balls (e.g. "this batter", "this batter v this type") and compares
what really happened (O_c balls of class c) with what the layers before it predicted for those same balls (E_c). The
group's class ratio is shrunk toward 1:
        ratio_c = (O_c + k * pbar_c) / (E_c + k * pbar_c)       pbar_c = E_c / n   (n = balls in the group)
i.e. k "pseudo-balls" that behaved exactly as predicted (a Dirichlet prior). Then p_c <- p_c * ratio_c, renormalised.
Multiplying ratios and renormalising is the odds-ratio (log5-style) way of combining a batter effect and a bowler effect:
log-probabilities add, so a good batter against a good bowler does not double count, and a rare class cannot go above 1.
Two strengths per layer: k_run for the 6 run classes and k_w for the wicket class (wickets are rare, so they need their own).

Layers: league cell (era x phase) -> match state (innings 1 / chase, wickets down, required-rate band) -> bowl kind (pace /
spin) -> bowl type x batter hand -> batter -> bowler -> batter in this phase -> bowler in this phase -> batter v kind ->
batter v type -> bowler v batter hand -> batter v this exact bowler. Bowling type and batting hand come ONLY from the
hand-kept list (sql/attributes.py); unknown stays unknown and that layer is skipped (ratio 1).

Each k pair is chosen by walk-forward validation: for each year t in the training years, estimate from balls before t and
score year t; pick the k pair with the lowest total log loss. No hand picks (grid in K_GRID; 1e6 = layer switched off).

Rebuild (fits k on IPL balls up to 2024, validates on 2025-26, writes models/data/matchup_k.json):
    python -m cricket_analytics.models.matchup_model
"""

import json
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ..db import current_db_path, query
from ..sql.attributes import BOWL_TYPES, attributes_cte
from ..sql.filters import Filters
from ..sql.fragments import BALL_FACED, DISMISSAL, PHASES, phase_sql
from ..sql.state import ball_state
from .run_expectancy import era_of

K_JSON = Path(__file__).parent / "data" / "matchup_k.json"
CLASSES = ("dot", "1", "2", "3", "4", "6", "W")
NC = 7
TRAIN_END, FIRST_FOLD = 2024, 2016
SKIP_FOLDS = (
    2023,
)  # first year of the IPL impact-player era: no earlier ball of that era to learn from
K_GRID = (5, 15, 45, 135, 400, 1200, 3600, 10800, 1e6)
LEAGUE = ("state", "kind", "type_hand")  # league layers: keyed by era, never weighted
LAMBDAS, OMEGAS = (0.0, 0.1, 0.25, 0.5), (0.0, 0.25, 0.5, 1.0)
MIN_CELL = 300  # an (era, phase) cell with fewer balls borrows the phase's all-era distribution
RAD = 1 << 16
# (name, key columns). Order matters: each layer is measured against the prediction of the layers before it.
LAYERS = (
    ("state", ("era", "phase", "state")),
    ("kind", ("era", "phase", "kind")),
    ("type_hand", ("era", "phase", "type", "hand")),
    ("bat", ("batter",)),
    ("bowl", ("bowler",)),
    ("bat_phase", ("batter", "phase")),
    ("bowl_phase", ("bowler", "phase")),
    ("bat_kind", ("batter", "kind")),
    ("bat_type", ("batter", "type")),
    ("bowl_hand", ("bowler", "hand")),
    ("pair", ("batter", "bowler")),
)
WK_BANDS = ("0-2", "3-5", "6+")
RR_BANDS = ("low", "mid", "high")  # chase required rate: < 8, 8-11, 11+ runs per over
N_STATES = 12  # 3 first-innings wicket bands + 3 wicket bands x 3 required-rate bands in a chase


# ── data ─────────────────────────────────────────────────────────────────────────────────────────────────────


def load_balls(f: Filters, db_path=None) -> pd.DataFrame:
    """One row per ball the batter faced, with the context columns the model needs."""
    base = replace(f, team=None, opposition=None, player=None, phase=None)
    st, sp = ball_state(base)
    dis = f"{DISMISSAL} AND d.player_out = d.batter"
    cls = (
        f"CASE WHEN {dis} THEN 6 WHEN d.runs_batter = 0 THEN 0 WHEN d.runs_batter = 1 THEN 1 "
        "WHEN d.runs_batter = 2 THEN 2 WHEN d.runs_batter = 4 THEN 4 WHEN d.runs_batter = 6 THEN 5 ELSE 3 END"
    )
    sql = f"""
    WITH {attributes_cte("pa")}, d AS ({st})
    SELECT m.competition || '_' || m.gender AS grp, year(m.date) AS yr, d.batter, d.bowler, d.innings,
           {phase_sql("d", "m")} AS phase, d.wickets_before AS wk, d.required_rr AS rrr,
           bt.bat_hand AS hand, bw.bowl_type AS bowl_type, {cls} AS cls, d.runs_batter AS runs
    FROM d JOIN matches m ON d.match_id = m.match_id
    LEFT JOIN pa bt ON bt.name = d.batter LEFT JOIN pa bw ON bw.name = d.bowler
    WHERE {BALL_FACED}"""
    return query(sql, sp, db_path=db_path)


@dataclass
class Vocab:
    """Names <-> ids, and the reviewed attributes of each player id (-1 = unknown)."""

    names: list
    hand_of: np.ndarray  # batting hand code of player id
    type_of: np.ndarray  # bowling type code of player id
    kind_of: np.ndarray  # 0 pace, 1 spin

    def id(self, name: str | None) -> int:
        return self._ix.get(name, -1) if name else -1

    def __post_init__(self):
        self._ix = {n: i for i, n in enumerate(self.names)}


def encode(df: pd.DataFrame) -> tuple[dict, Vocab]:
    """Integer codes for every column the layers key on (-1 = unknown / not applicable)."""
    ids, names = pd.factorize(pd.concat([df.batter, df.bowler], ignore_index=True))
    n = len(df)
    bat, bowl = ids[:n].astype(np.int64), ids[n:].astype(np.int64)
    ty = (
        df.bowl_type.map({t: i for i, t in enumerate(BOWL_TYPES)})
        .fillna(-1)
        .astype(np.int64)
        .to_numpy()
    )
    kind = np.where(
        ty < 0, -1, np.where(df.bowl_type.fillna("").str.contains("spin|orthodox"), 1, 0)
    )
    hand = df.hand.map({"right": 0, "left": 1}).fillna(-1).astype(np.int64).to_numpy()
    wb = np.minimum(df.wk.to_numpy() // 3, 2)
    rr = df.rrr.to_numpy(dtype=float)
    band = np.where(np.isnan(rr), 1, np.where(rr < 8, 0, np.where(rr < 11, 1, 2)))
    state = np.where(df.innings.to_numpy() == 2, 3 + wb * 3 + band, wb)
    emap = {
        (g, y): int(era_of(g, y) > 0)
        for g, y in df[["grp", "yr"]].drop_duplicates().itertuples(index=False)
    }
    era = np.array([emap[k] for k in zip(df.grp, df.yr)])
    codes = dict(
        yr=df.yr.to_numpy(),
        era=era.astype(np.int64),
        phase=df.phase.map({p: i for i, p in enumerate(PHASES)}).to_numpy().astype(np.int64),
        state=state.astype(np.int64),
        kind=kind.astype(np.int64),
        type=ty,
        hand=hand,
        batter=bat,
        bowler=bowl,
        cls=df.cls.to_numpy().astype(np.int64),
        runs=df.runs.to_numpy().astype(float),
    )
    hand_of = np.full(len(names), -1, np.int64)
    type_of = np.full(len(names), -1, np.int64)
    kind_of = np.full(len(names), -1, np.int64)
    hand_of[bat] = hand
    type_of[bowl] = ty
    kind_of[bowl] = kind
    return codes, Vocab(list(names), hand_of, type_of, kind_of)


def _take(codes: dict, mask) -> dict:
    return {k: v[mask] for k, v in codes.items()}


# ── layers ───────────────────────────────────────────────────────────────────────────────────────────────────


def key_of(codes: dict, comps: tuple) -> np.ndarray:
    """Group key per row (-1 when any component is unknown)."""
    key = np.zeros(len(codes["cls"]), np.int64)
    bad = np.zeros(len(key), bool)
    for c in comps:
        v = codes[c]
        bad |= v < 0
        key = key * RAD + v
    return np.where(bad, -1, key)


def class_sums(gid: np.ndarray, G: int, w: np.ndarray) -> np.ndarray:
    """Per group, per class: sum of w[:, c] over rows (gid >= 0)."""
    ok = gid >= 0
    return np.stack(
        [np.bincount(gid[ok], weights=w[ok, c], minlength=G) for c in range(NC)], axis=1
    )


def ratios(obs: np.ndarray, E: np.ndarray, k_run: float, k_w: float) -> np.ndarray:
    """Shrunk class ratios (see module docstring). A group with no balls has ratio 1."""
    n = np.maximum(E.sum(axis=1, keepdims=True), 1e-12)
    pr = np.array([k_run] * 6 + [k_w]) * (E / n)
    den = E + pr
    return np.where(den > 0, (obs + pr) / np.where(den > 0, den, 1), 1.0)


def norm(P: np.ndarray) -> np.ndarray:
    return P / P.sum(axis=1, keepdims=True)


def onehot(cls: np.ndarray) -> np.ndarray:
    return np.eye(NC)[cls]


def base_table(codes: dict) -> tuple[np.ndarray, np.ndarray]:
    """League probabilities per (era, phase): shape (2, 3, 7), and the ball counts per (era, phase, state)."""
    cnt = np.zeros((2, 3, NC))
    cell = np.zeros((2, 3, N_STATES))
    for e in (0, 1):
        for p in range(3):
            m = (codes["era"] == e) & (codes["phase"] == p)
            cnt[e, p] = np.bincount(codes["cls"][m], minlength=NC)
            cell[e, p] = np.bincount(codes["state"][m], minlength=N_STATES)
    pooled = cnt.sum(axis=0)  # per phase, all eras
    g = cnt.sum(axis=(0, 1)) / max(cnt.sum(), 1)
    out = np.zeros_like(cnt)
    for e in (0, 1):
        for p in range(3):
            c = cnt[e, p] if cnt[e, p].sum() >= MIN_CELL else pooled[p]
            out[e, p] = (c + 2 * g) / (c.sum() + 2)
    return out, cell


@dataclass
class Layer:
    name: str
    comps: tuple
    keys: np.ndarray  # sorted group keys seen in training
    R: np.ndarray  # (G + 1, 7) ratios; the last row (all ones) is for unseen / unknown groups
    n: np.ndarray  # balls per group (+ trailing 0)
    obs: np.ndarray  # class counts per group (+ trailing zeros)

    def gid(self, codes: dict) -> np.ndarray:
        key = key_of(codes, self.comps)
        if len(self.keys) == 0:
            return np.full(len(key), -1)
        ix = np.minimum(np.searchsorted(self.keys, key), len(self.keys) - 1)
        return np.where((key >= 0) & (self.keys[ix] == key), ix, -1)


@dataclass
class Fit:
    base: np.ndarray  # (2, 3, 7)
    cell: np.ndarray  # (2, 3, 12) ball counts
    layers: list
    ks: dict
    rmean: np.ndarray  # mean bat runs per class
    era_now: int  # era code of the newest training ball

    def apply(self, codes: dict, upto: int | None = None, keep: bool = False):
        """Probabilities (n, 7) after the first `upto` layers (None = all). keep=True also returns the list after each stage."""
        P = self.base[codes["era"], codes["phase"]]
        stages = [P]
        for L in self.layers[:upto]:
            g = L.gid(codes)
            P = norm(P * L.R[np.where(g < 0, len(L.R) - 1, g)])
            stages.append(P)
        return stages if keep else P

    def layer(self, name: str) -> Layer:
        return next(L for L in self.layers if L.name == name)

    def exp_runs(self, P: np.ndarray) -> np.ndarray:
        return P @ self.rmean


def weights(codes: dict, t_ref: int, era_ref: int, lam: float, omega: float) -> np.ndarray:
    """Weight of each ball for the PLAYER layers when predicting year t_ref: exp(-lam * years back), times omega for a ball
    from the other era. lam = omega = 0 is "isolated": only balls of the target era, all equal. Balls from t_ref on get 0."""
    age = np.maximum(t_ref - 1 - codes["yr"], 0)
    w = np.exp(-lam * age) * np.where(codes["era"] == era_ref, 1.0, omega)
    return np.where(codes["yr"] < t_ref, w, 0.0)


def fit_chain(codes: dict, ks: dict, w: np.ndarray | None = None) -> Fit:
    """Fit every layer in order on `codes` (in-sample chain: each layer sees the predictions of the layers before it)."""
    base, cell = base_table(codes)
    P = base[codes["era"], codes["phase"]]
    Y = onehot(codes["cls"])
    w = np.ones(len(Y)) if w is None else w
    layers = []
    for name, comps in LAYERS:
        key = key_of(codes, comps)
        ok = key >= 0
        keys, inv = np.unique(key[ok], return_inverse=True)
        gid = np.full(len(key), -1)
        gid[ok] = inv
        G = len(keys)
        wm = np.ones(len(Y)) if name in LEAGUE else w
        obs, E = class_sums(gid, G, Y * wm[:, None]), class_sums(gid, G, P * wm[:, None])
        gu = np.where(
            wm > 0, gid, -1
        )  # evidence shown to the user = balls that really feed the layer
        raw = class_sums(gu, G, Y)
        kr, kw = ks[name]
        R = np.vstack([ratios(obs, E, kr, kw), np.ones((1, NC))])
        layers.append(
            Layer(
                name,
                comps,
                keys,
                R,
                np.append(raw.sum(axis=1), 0.0),
                np.vstack([raw, np.zeros((1, NC))]),
            )
        )
        P = norm(P * R[np.where(gid < 0, G, gid)])
    era_now = int(codes["era"][codes["yr"].argmax()])
    rmean = np.array(
        [
            codes["runs"][m].mean()
            if (m := (codes["cls"] == c) & (codes["era"] == era_now)).any()
            else 0.0
            for c in range(NC)
        ]
    )
    last = codes["yr"].argmax()
    return Fit(base, cell, layers, ks, rmean, int(codes["era"][last]))


# ── choosing k ───────────────────────────────────────────────────────────────────────────────────────────────


def tune(codes: dict, lam: float = 0.0, omega: float = 0.0, log=print) -> tuple[dict, dict, dict]:
    """Walk-forward choice of (k_run, k_w) per layer, for one weighting (lam, omega: see weights()).
    Returns ({layer: [k_run, k_w]}, {layer: gain per 1000 test balls}, {"total": log loss over all folds, "fold_2024": ..., "n": balls})."""
    yr, Y = codes["yr"], onehot(codes["cls"])
    train = yr <= TRAIN_END
    folds = [t for t in range(FIRST_FOLD, TRAIN_END + 1) if t not in SKIP_FOLDS and (yr == t).any()]
    st = []
    for t in folds:
        h, v = np.where(train & (yr < t))[0], np.where(yr == t)[0]
        base, _ = base_table(_take(codes, h))
        e_t = int(codes["era"][v[0]])
        st.append(
            dict(
                t=t,
                h=h,
                v=v,
                wh=weights(_take(codes, h), t, e_t, lam, omega),
                Ph=base[codes["era"][h], codes["phase"][h]],
                Pv=base[codes["era"][v], codes["phase"][v]],
            )
        )
    n_test = sum(len(s["v"]) for s in st)
    ks, gain = {}, {}
    for name, comps in LAYERS:
        key = key_of(codes, comps)
        ok = key >= 0
        _, inv = np.unique(key[ok], return_inverse=True)
        gid = np.full(len(key), -1)
        gid[ok] = inv
        G = int(inv.max()) + 1 if ok.any() else 0
        loss = np.zeros((len(K_GRID), len(K_GRID)))
        prep = []
        for s in st:
            wm = np.ones(len(s["h"])) if name in LEAGUE else s["wh"]
            sums = (
                class_sums(gid[s["h"]], G, Y[s["h"]] * wm[:, None]),
                class_sums(gid[s["h"]], G, s["Ph"] * wm[:, None]),
            )
            s["sums"] = sums
            gv = gid[s["v"]]
            tv = gv >= 0
            tg, tinv = np.unique(gv[tv], return_inverse=True)
            prep.append((sums[0][tg], sums[1][tg], tinv, s["Pv"][tv], Y[s["v"]][tv]))
        for i, kr in enumerate(K_GRID):
            for j, kw in enumerate(K_GRID):
                for obs, E, tinv, Pv, Yv in prep:
                    Q = norm(Pv * ratios(obs, E, kr, kw)[tinv])
                    loss[i, j] -= np.log(np.maximum((Q * Yv).sum(axis=1), 1e-9)).sum()
        i, j = np.unravel_index(loss.argmin(), loss.shape)
        ks[name] = [K_GRID[i], K_GRID[j]]
        gain[name] = float((loss[-1, -1] - loss[i, j]) / n_test * 1000)
        for s in st:
            R = np.vstack([ratios(*s["sums"], *ks[name]), np.ones((1, NC))])
            for rows, P in (("h", "Ph"), ("v", "Pv")):
                gg = gid[s[rows]]
                s[P] = norm(s[P] * R[np.where(gg < 0, G, gg)])
        log(
            f"  {name:10s} k_run={ks[name][0]:>9g} k_w={ks[name][1]:>9g}  gain {gain[name]:+.3f} nats/1000 balls"
        )
    per = {
        s["t"]: float(-np.log(np.maximum((s["Pv"] * Y[s["v"]]).sum(axis=1), 1e-9)).sum())
        for s in st
    }
    return ks, gain, dict(total=sum(per.values()), fold_2024=per.get(2024), n=n_test)


# ── validation ───────────────────────────────────────────────────────────────────────────────────────────────

G5 = [[0], [1, 2, 3], [4], [5], [6]]  # dot / 1-3 / 4 / 6 / wicket


def _five(P):
    return np.stack([P[:, g].sum(axis=1) for g in G5], axis=1)


def metrics(P: np.ndarray, cls: np.ndarray) -> dict:
    Y = onehot(cls)
    P = np.clip(P, 1e-9, 1)
    P5, Y5 = _five(P), _five(Y)
    pw, yw = P[:, 6], Y[:, 6]
    return dict(
        logloss7=float(-np.log((P * Y).sum(axis=1)).mean()),
        logloss5=float(-np.log((P5 * Y5).sum(axis=1)).mean()),
        brier5=float(((P5 - Y5) ** 2).sum(axis=1).mean()),
        out_logloss=float(-(yw * np.log(pw) + (1 - yw) * np.log(1 - pw)).mean()),
        out_brier=float(((pw - yw) ** 2).mean()),
    )


def _raw(fit: Fit, name: str, codes: dict, P0: np.ndarray, eps: float = 0.5):
    """Raw rate of a group (counts, almost unsmoothed) with the league prediction P0 as the fallback; also the group's balls."""
    L = fit.layer(name)
    g = L.gid(codes)
    obs, n = L.obs[np.where(g < 0, len(L.R) - 1, g)], L.n[np.where(g < 0, len(L.R) - 1, g)]
    return (obs + eps * P0) / (n + eps)[:, None], n


def validate(codes: dict, ks: dict, lam: float = 0.0, omega: float = 0.0) -> dict:
    train, test = _take(codes, codes["yr"] <= TRAIN_END), _take(codes, codes["yr"] > TRAIN_END)
    fit = fit_chain(train, ks, weights(train, TRAIN_END + 1, int(test["era"].max()), lam, omega))
    stages = fit.apply(test, keep=True)
    P_model, cls = stages[-1], test["cls"]
    P_lg = stages[0]
    P_bat, _ = _raw(fit, "bat", test, P_lg)
    P_pair_raw, n_pair = _raw(fit, "pair", test, P_bat)
    P_pair_raw = np.where((n_pair >= 1)[:, None], P_pair_raw, P_bat)
    out = dict(n_test=int(len(cls)), n_train=int(len(train["cls"])))
    out["all"] = {
        "league phase average": metrics(P_lg, cls),
        "batter raw career rate": metrics(P_bat, cls),
        "raw head-to-head (else batter raw)": metrics(P_pair_raw, cls),
        "model": metrics(P_model, cls),
    }
    sub = n_pair >= 6
    out["pair_ge6"] = {"n_balls": int(sub.sum())} | {
        k: metrics(P, cls[sub])
        for k, P in {
            "league phase average": P_lg[sub],
            "batter raw career rate": P_bat[sub],
            "raw head-to-head": _raw(fit, "pair", test, P_bat)[0][sub],
            "model": P_model[sub],
        }.items()
    }
    out["ablation"] = {
        nm: metrics(P, cls) for nm, P in zip(("base",) + tuple(n for n, _ in LAYERS), stages)
    }
    # expected-runs MAE per pair with >= 12 test balls
    er = {
        "league phase average": fit.exp_runs(P_lg),
        "batter raw career rate": fit.exp_runs(P_bat),
        "raw head-to-head (else batter raw)": fit.exp_runs(P_pair_raw),
        "model": fit.exp_runs(P_model),
    }
    d = pd.DataFrame({"b": test["batter"], "w": test["bowler"], "runs": test["runs"], **er})
    g = d.groupby(["b", "w"]).agg(
        n=("runs", "size"), act=("runs", "mean"), **{k: (k, "mean") for k in er}
    )
    g = g[g.n >= 12]
    out["mae_runs_per_ball"] = {"pairs": int(len(g))} | {
        k: float((g[k] - g.act).abs().mean()) for k in er
    }
    out["rmse_runs_per_ball"] = {k: float(np.sqrt(((g[k] - g.act) ** 2).mean())) for k in er}
    # calibration of P(out), 8 equal-count bins
    q = pd.qcut(P_model[:, 6], 8, duplicates="drop")
    cal = (
        pd.DataFrame({"q": q, "p": P_model[:, 6], "y": (cls == 6).astype(float)})
        .groupby("q", observed=True)
        .agg(balls=("y", "size"), predicted=("p", "mean"), actual=("y", "mean"))
    )
    out["calibration"] = [
        dict(lo=float(i.left), hi=float(i.right), **r._asdict())
        for i, r in zip(cal.index, cal.itertuples(index=False))
    ]
    # by evidence: balls of prior head-to-head
    bt = fit.layer("bat_type").gid(test)
    n_type = fit.layer("bat_type").n[np.where(bt < 0, -1, bt)]
    lab = np.where(
        n_pair >= 30,
        "pair>=30",
        np.where(n_pair >= 12, "pair 12-29", np.where(n_pair >= 1, "pair 1-11", "no pair")),
    )
    ev = {}
    for L in ("pair>=30", "pair 12-29", "pair 1-11", "no pair"):
        m = lab == L
        if m.any():
            ev[L] = dict(
                balls=int(m.sum()),
                model=metrics(P_model[m], cls[m])["logloss7"],
                league=metrics(P_lg[m], cls[m])["logloss7"],
                batter=metrics(stages[4][m], cls[m])["logloss7"],
                out_model=metrics(P_model[m], cls[m])["out_logloss"],
                out_league=metrics(P_lg[m], cls[m])["out_logloss"],
            )
    out["by_pair_evidence"] = ev
    ty = np.where(n_type >= 150, "type>=150", np.where(n_type >= 50, "type 50-149", "type<50"))
    out["by_type_evidence"] = {
        L: dict(
            balls=int((ty == L).sum()),
            model=metrics(P_model[ty == L], cls[ty == L])["logloss7"],
            league=metrics(P_lg[ty == L], cls[ty == L])["logloss7"],
            batter=metrics(stages[4][ty == L], cls[ty == L])["logloss7"],
        )
        for L in ("type>=150", "type 50-149", "type<50")
        if (ty == L).any()
    }
    return out


# ── prediction ───────────────────────────────────────────────────────────────────────────────────────────────


def _codes(n: int, **kw) -> dict:
    c = {
        k: np.full(n, -1, np.int64)
        for k in ("era", "phase", "state", "kind", "type", "hand", "batter", "bowler")
    }
    c["cls"] = np.zeros(n, np.int64)
    c.update({k: np.asarray(v) for k, v in kw.items()})
    return c


def state_cells(
    wickets_down: str | None, innings: str | None, required_rate: str | None
) -> list[int]:
    wbs = [WK_BANDS.index(wickets_down)] if wickets_down else [0, 1, 2]
    out = []
    if innings in (None, "first"):
        out += wbs
    if innings in (None, "chase"):
        bands = [RR_BANDS.index(required_rate)] if required_rate else [0, 1, 2]
        out += [3 + w * 3 + b for w in wbs for b in bands]
    return out


def predict(
    fit: Fit,
    vocab: Vocab,
    batter: str,
    bowler: str | None = None,
    bowl_type: str | None = None,
    phase: str | None = None,
    wickets_down: str | None = None,
    innings: str | None = None,
    required_rate: str | None = None,
) -> dict:
    """Probabilities for one situation (a weighted mix over every phase / state cell the question leaves open) and the evidence."""
    bi, wi = vocab.id(batter), vocab.id(bowler)
    ty = (
        BOWL_TYPES.index(bowl_type)
        if bowl_type in BOWL_TYPES
        else (int(vocab.type_of[wi]) if wi >= 0 else -1)
    )
    kind = (
        {"pace": 0, "spin": 1}.get(bowl_type, -1)
        if bowl_type not in BOWL_TYPES
        else (1 if "spin" in bowl_type or "orthodox" in bowl_type else 0)
    )
    if bowl_type is None and wi >= 0:
        kind = int(vocab.kind_of[wi])
    hand = int(vocab.hand_of[bi]) if bi >= 0 else -1
    phases = [PHASES.index(phase)] if phase else [0, 1, 2]
    cells = [(p, s) for p in phases for s in state_cells(wickets_down, innings, required_rate)]
    w = np.array([fit.cell[fit.era_now, p, s] for p, s in cells], float) + 1e-9
    if not phase and bi >= 0:  # weight phases the way this batter really faces them
        bp = fit.layer("bat_phase")
        gp = [bp.gid(_codes(1, batter=[bi], phase=[p]))[0] for p in range(3)]
        nph = np.array([bp.n[g] if g >= 0 else 0 for g in gp])
        lg = fit.cell[fit.era_now].sum(axis=1)
        if nph.sum() >= 50:
            w *= np.array([(nph[p] / nph.sum()) / (lg[p] / lg.sum()) for p, _ in cells])
    w /= w.sum()
    c = _codes(
        len(cells),
        era=[fit.era_now] * len(cells),
        phase=[p for p, _ in cells],
        state=[s for _, s in cells],
        kind=[kind] * len(cells),
        type=[ty] * len(cells),
        hand=[hand] * len(cells),
        batter=[bi] * len(cells),
        bowler=[wi if (wi >= 0 and bowl_type is None) else -1] * len(cells),
    )
    stages = fit.apply(c, keep=True)
    mix = lambda P: (w[:, None] * P).sum(axis=0)  # noqa: E731
    names = ["base"] + [n for n, _ in LAYERS]
    out = dict(
        P=mix(stages[-1]),
        P_league=mix(stages[names.index("state")]),
        P_type=mix(stages[names.index("type_hand")]),
    )
    ev = {}
    for L in fit.layers:
        g = L.gid(c)[-1] if len(cells) else -1
        if L.name in ("bat", "bowl", "bat_kind", "bat_type", "bowl_hand", "pair"):
            ev[L.name] = int(L.n[g]) if g >= 0 else 0
    if phase:
        for L in ("bat_phase", "bowl_phase"):
            g = fit.layer(L).gid(c)[0]
            ev[L] = int(fit.layer(L).n[g]) if g >= 0 else 0
    # raw rate of the most specific group with balls
    for L in ("pair", "bat_type", "bat_kind", "bat"):
        g = fit.layer(L).gid(c)[0]
        if g >= 0 and fit.layer(L).n[g] > 0:
            obs = fit.layer(L).obs[g]
            ev["raw_level"], ev["raw_balls"] = L, int(obs.sum())
            ev["raw_runs_per_ball"], ev["raw_out_pct"] = (
                float(obs @ fit.rmean / obs.sum()),
                float(100 * obs[6] / obs.sum()),
            )
            break
    # balls at the level the question asks about (this type if the type is known, else this kind): what the confidence rests on
    lvl = "bat_type" if ty >= 0 else "bat_kind"
    g = fit.layer(lvl).gid(c)[0] if kind >= 0 or ty >= 0 else -1
    ev["ask_balls"] = int(fit.layer(lvl).n[g]) if g >= 0 else 0
    ev["league_balls"] = int(sum(fit.cell[fit.era_now, p, s] for p, s in cells))
    out["evidence"] = ev
    out["type"] = ty
    out["kind"] = kind
    out["hand"] = hand
    return out


def confidence(ev: dict, bowler: str | None, has_type: bool) -> str:
    """strong / medium / thin from the balls behind the matchup. Thresholds are a judgement, checked in docs/VALUE_step4.md."""
    if bowler:
        if ev.get("pair", 0) >= 30:
            return "strong"
        if ev.get("pair", 0) >= 12 or ev.get("bat_type", 0) >= 150:
            return "medium"
        return "thin"
    if has_type:
        t = ev.get("ask_balls", ev.get("bat_type", 0))
        return "strong" if t >= 150 else "medium" if t >= 50 else "thin"
    return "medium" if ev.get("bat", 0) >= 300 else "thin"


# ── production fit (cached) and CLI ──────────────────────────────────────────────────────────────────────────


MODES = ("isolated", "decayed")


def load_meta() -> dict:
    if not K_JSON.exists():
        raise FileNotFoundError(
            f"{K_JSON} is missing: run  python -m cricket_analytics.models.matchup_model"
        )
    return json.loads(K_JSON.read_text())


def default_mode() -> str:
    return load_meta()["default"] if K_JSON.exists() else "isolated"


@lru_cache(maxsize=8)
def _cached(db: str, mtime: float, comp: str, seasons: tuple, mode: str) -> tuple[Fit, Vocab]:
    f = Filters(
        competition=comp,
        season=list(seasons[0]) or None,
        season_from=seasons[1],
        season_to=seasons[2],
        last_n_years=seasons[3],
    )
    codes, vocab = encode(load_balls(f))
    if len(codes["cls"]) == 0:
        raise ValueError("no balls for these filters")
    m = load_meta()["modes"][mode]
    # target era = era of the newest ball; isolated: only balls of that era (equal weight); decayed: see weights()
    w = weights(
        codes,
        int(codes["yr"].max()) + 1,
        int(codes["era"][codes["yr"].argmax()]),
        m["lambda"],
        m["omega"],
    )
    return fit_chain(codes, m["ks"], w), vocab


def get_fit(f: Filters, mode: str | None = None) -> tuple[Fit, Vocab]:
    """The fitted model for a competition (default IPL) and season filter, cached per database file version."""
    p = current_db_path()
    seasons = (tuple(map(str, f.values("season"))), f.season_from, f.season_to, f.last_n_years)
    return _cached(
        str(p), Path(p).stat().st_mtime, f.competition or "ipl", seasons, mode or default_mode()
    )


def main(db_path=None) -> dict:
    t0 = time.time()
    df = load_balls(Filters(competition="ipl"), db_path)
    codes, _ = encode(df)
    print(
        f"{len(df):,} IPL balls faced, {df.yr.min()}-{df.yr.max()} ({time.time() - t0:.0f}s). Tuning k on <= {TRAIN_END}:"
    )
    modes = {}
    print("isolated (only the target era's balls feed the player layers):")
    ks, gain, tl = tune(codes, 0.0, 0.0)
    modes["isolated"] = dict(ks=ks, gain=gain, tune=tl, **{"lambda": 0.0, "omega": 0.0})
    best = (tl["total"], 0.0, 0.0)
    grid = {}
    for lam in LAMBDAS:
        for om in OMEGAS:
            if (lam, om) == (0.0, 0.0):
                grid[f"{lam},{om}"] = tl
                continue
            k2, g2, t2 = tune(codes, lam, om, log=lambda *_: None)
            grid[f"{lam},{om}"] = t2
            print(
                f"  lambda={lam} omega={om}: walk-forward loss {t2['total']:.1f} (2024 fold {t2['fold_2024']:.1f}) vs isolated {tl['total']:.1f}"
            )
            if t2["total"] < best[0]:
                best, modes["decayed"] = (
                    (t2["total"], lam, om),
                    dict(ks=k2, gain=g2, tune=t2, **{"lambda": lam, "omega": om}),
                )
    if "decayed" not in modes:
        modes["decayed"] = dict(modes["isolated"])
    for m, v in modes.items():
        v["validation"] = validate(codes, v["ks"], v["lambda"], v["omega"])
        a = v["validation"]["all"]["model"]
        print(
            f"{m}: lambda={v['lambda']} omega={v['omega']}  test logloss7 {a['logloss7']:.5f}  out_logloss {a['out_logloss']:.5f}"
        )
    vi, vd = (modes[m]["validation"] for m in MODES)
    # decayed is the default only if clearly better on test: log loss lower by >= 0.002 nats, wicket log loss and MAE not worse
    better = (
        vi["all"]["model"]["logloss7"] - vd["all"]["model"]["logloss7"] >= 0.002
        and vd["all"]["model"]["out_logloss"] <= vi["all"]["model"]["out_logloss"]
        and vd["mae_runs_per_ball"]["model"] <= vi["mae_runs_per_ball"]["model"]
    )
    out = dict(
        default="decayed" if better else "isolated",
        train_end=TRAIN_END,
        classes=CLASSES,
        modes=modes,
        weight_grid=grid,
    )
    K_JSON.write_text(json.dumps(out, indent=1))
    print(f"default mode: {out['default']}; wrote {K_JSON} ({time.time() - t0:.0f}s)")
    return out


if __name__ == "__main__":
    main()
