"""S2 ball-outcome model: per-delivery classifier, trained on seasons < test year only.

Classes (index): 0:0 runs, 1:1, 2:2, 3:3, 4:4 (5 -> 4), 5:6 (7+ -> 6), 6:wicket, 7:wide/no-ball (extra ball, +1 run).
Byes / leg-byes count as runs. Every feature is CAUSAL: player strength, scoring level and venue effect use only
matches with date strictly before the match (so train and test rows are built the same way).
Features are private to this file (another worker owns ml/features.py).

  python -m cricket_analytics.ml.ball_model        # builds data/external/ml/balls.parquet
"""

import numpy as np
import pandas as pd

from ..db import query
from .dataset import OUT_DIR, load

RUNS = np.array([0, 1, 2, 3, 4, 6, 0, 1])  # runs added by class (wicket / extra get small extras in the simulator)
WK, EX = 6, 7
BALLS_FILE = OUT_DIR / "balls.parquet"
MODEL_DIR = OUT_DIR / "models"
K_BAT_RUNS, K_BAT_OUT, K_BOWL_RUNS, K_BOWL_WK, K_VENUE = 60.0, 120.0, 120.0, 240.0, 8.0
HL_SLOW, HL_FAST = 100, 25  # half-lives of the scoring level, in matches of the same competition
RETIRED = ("retired hurt", "retired not out", "retired out")
NOT_BOWLER_WK = RETIRED + ("run out", "obstructing the field")

A = ["over_n", "ball_in_over", "balls_bowled", "wickets", "innings", "crr", "crr_rel", "target", "runs_needed", "rrr",
     "rrr_rel", "lvl_slow", "lvl_fast", "comp"]
B = A + ["bat_rpb", "bat_out", "bat_exp", "bat_faced", "bow_rpb", "bow_wk"]
C = B + ["venue_eff"]
VARIANTS = {"A": A, "B": B, "C": C}


# ---------- causal helpers ----------
def prior_sums(agg, key, cols):
    """agg: one row per (key, date). Returns the same rows with `cols` = sums over STRICTLY earlier dates."""
    agg = agg.sort_values([key, "date"]).reset_index(drop=True)
    pri = agg.groupby(key)[cols].cumsum() - agg[cols]
    return pd.concat([agg[[key, "date"]], pri.add_prefix("p_")], axis=1)


def ew_level(m, hl):
    """m: one competition, sorted by date; column v. Exponentially weighted mean (half-life hl matches) of v over
    matches strictly before each row's date. NaN when there are none."""
    n = len(m)
    idx = np.arange(n)
    d, v = m.date.to_numpy(), m.v.to_numpy()
    w = 0.5 ** ((idx[:, None] - idx[None, :]) / hl) * (d[None, :] < d[:, None])
    s = w.sum(1)
    return np.where(s > 0, (w @ v) / np.where(s > 0, s, 1), np.nan)


def match_levels(inn):
    """Per match: lvl_slow, lvl_fast (runs per over, first innings of earlier matches in the competition) and the
    shrunk venue effect (rpo above the competition level at that venue, earlier matches only)."""
    f = inn[(inn.innings == 1) & ~inn.reduced & (inn.gender == "male")].copy()
    f["v"] = f.final_total / f.legal_balls * 6
    f = f.sort_values(["date", "match_id"]).reset_index(drop=True)
    for name, hl in (("lvl_slow", HL_SLOW), ("lvl_fast", HL_FAST), ("lvl_h50", 50), ("lvl_h12", 12), ("lvl_h400", 400)):
        f[name] = np.nan
        for c, g in f.groupby("competition"):
            f.loc[g.index, name] = ew_level(g, hl)
    f["res"] = f.v - f.lvl_slow
    # venue effect: earlier-dates residual sum / (n + K)
    ag = f.dropna(subset=["res"]).groupby(["venue", "date"], as_index=False).agg(res=("res", "sum"), n=("res", "size"))
    pv = prior_sums(ag, "venue", ["res", "n"])
    f = f.merge(pv, on=["venue", "date"], how="left")
    f["venue_eff"] = (f.p_res.fillna(0) / (f.p_n.fillna(0) + K_VENUE)).astype(float)
    return f[["match_id", "lvl_slow", "lvl_fast", "lvl_h50", "lvl_h12", "lvl_h400", "venue_eff"]]


# ---------- ball table ----------
def build_balls(write=True):
    """One row per delivery (men's T20, innings 1-2, non-reduced matches only for training use, flag kept)."""
    _, inn = load()
    inn = inn.copy()
    lv = match_levels(inn)
    d = query(
        "SELECT d.match_id, d.innings, d.ball_seq, d.batter, d.non_striker, d.bowler, d.runs_batter, d.runs_total, "
        "d.wides, d.noballs, d.byes, d.legbyes, d.wicket_type, d.player_out FROM deliveries d JOIN matches m USING (match_id) "
        "WHERE m.gender = 'male' AND d.innings <= 2"
    )
    d = d.merge(inn[["match_id", "innings", "date", "competition", "season_year", "venue", "target", "max_balls", "reduced"]],
                on=["match_id", "innings"]).merge(lv, on="match_id", how="left")
    d = d.sort_values(["match_id", "innings", "ball_seq"]).reset_index(drop=True)
    legal = ((d.wides == 0) & (d.noballs == 0)).astype(int)
    wk = (d.player_out.notna() & ~d.wicket_type.fillna("").isin(RETIRED)).astype(int)
    ri = d.runs_total.clip(upper=7).to_numpy()
    cls = np.select([legal == 0, wk == 1], [EX, WK], np.array([0, 1, 2, 3, 4, 4, 5, 5])[ri])
    d["cls"] = cls.astype(np.int8)
    g = [d.match_id, d.innings]
    d["runs"] = d.runs_total.groupby(g).cumsum() - d.runs_total
    d["balls_bowled"] = legal.groupby(g).cumsum() - legal
    d["wickets"] = wk.groupby(g).cumsum() - wk
    # striker's balls faced / runs so far this innings (wides are not faced)
    faced = (d.wides == 0).astype(int)
    gb = [d.match_id, d.innings, d.batter]
    d["bat_faced"] = faced.groupby(gb).cumsum() - faced
    d["bat_runs"] = d.runs_batter.where(d.wides == 0, 0).groupby(gb).cumsum() - d.runs_batter.where(d.wides == 0, 0)
    d["over_n"] = d.balls_bowled // 6
    d["ball_in_over"] = d.balls_bowled % 6
    d["innings"] = d.innings.astype(int)
    d["balls_left"] = d.max_balls - d.balls_bowled
    d["wk_flag"], d["legal"] = wk, legal

    # --- player strength from strictly earlier dates (all men's matches) ---
    # *_a columns: runs rescaled to a reference era (x 8 / competition level of that match) so strength does not carry the era
    era = 8.0 / d.lvl_slow.fillna(8.0)
    bat = d.assign(f=faced, r=d.runs_batter.where(d.wides == 0, 0), o=((wk == 1) & (d.player_out == d.batter)).astype(int))
    bat["ra"] = bat.r * era
    ba = bat.groupby(["batter", "date"], as_index=False).agg(f=("f", "sum"), r=("r", "sum"), ra=("ra", "sum"), o=("o", "sum"))
    bwl = d.assign(bl=legal, br=d.runs_total - d.byes - d.legbyes,
                   bw=((wk == 1) & ~d.wicket_type.fillna("").isin(NOT_BOWLER_WK)).astype(int))
    bwl["bra"] = bwl.br * era
    bo = bwl.groupby(["bowler", "date"], as_index=False).agg(bl=("bl", "sum"), br=("br", "sum"), bra=("bra", "sum"), bw=("bw", "sum"))
    day = ba.groupby("date", as_index=False)[["f", "r", "ra", "o"]].sum().merge(
        bo.groupby("date", as_index=False)[["bl", "br", "bra", "bw"]].sum(), on="date").assign(k=0)
    pg = prior_sums(day, "k", ["f", "r", "ra", "o", "bl", "br", "bra", "bw"]).drop(columns="k")
    pb = prior_sums(ba, "batter", ["f", "r", "ra", "o"]).rename(columns={"p_f": "b_f", "p_r": "b_r", "p_ra": "b_ra", "p_o": "b_o"})
    po = prior_sums(bo, "bowler", ["bl", "br", "bra", "bw"]).rename(columns={"p_bl": "o_bl", "p_br": "o_br", "p_bra": "o_bra", "p_bw": "o_bw"})
    d = d.merge(pg, on="date", how="left").merge(pb, on=["batter", "date"], how="left").merge(po, on=["bowler", "date"], how="left")
    gf = d.p_f.where(d.p_f > 0)
    g_rpb, g_out = (d.p_r / gf).fillna(1.2), (d.p_o / gf).fillna(0.05)
    g_brpb, g_bwk = (d.p_br / d.p_bl.where(d.p_bl > 0)).fillna(1.2), (d.p_bw / d.p_bl.where(d.p_bl > 0)).fillna(0.04)
    bf, bl = d.b_f.fillna(0), d.o_bl.fillna(0)
    gra, gbra = (d.p_ra / gf).fillna(1.2), (d.p_bra / d.p_bl.where(d.p_bl > 0)).fillna(1.2)
    d["bat_rpa"] = (d.b_ra.fillna(0) + K_BAT_RUNS * gra) / (bf + K_BAT_RUNS)
    d["bow_rpa"] = (d.o_bra.fillna(0) + K_BOWL_RUNS * gbra) / (bl + K_BOWL_RUNS)
    d["bat_rpb"] = (d.b_r.fillna(0) + K_BAT_RUNS * g_rpb) / (bf + K_BAT_RUNS)
    d["bat_out"] = (d.b_o.fillna(0) + K_BAT_OUT * g_out) / (bf + K_BAT_OUT)
    d["bat_exp"] = np.log1p(bf)
    d["bow_rpb"] = (d.o_br.fillna(0) + K_BOWL_RUNS * g_brpb) / (bl + K_BOWL_RUNS)
    d["bow_wk"] = (d.o_bw.fillna(0) + K_BOWL_WK * g_bwk) / (bl + K_BOWL_WK)
    d = d.drop(columns=[c for c in d.columns if c[:2] in ("p_", "b_", "o_")])

    # --- derived state features ---
    tl = d.balls_bowled.clip(lower=1)
    d["crr"] = np.where(d.balls_bowled > 0, d.runs / tl * 6, np.nan)
    d["runs_needed"] = d.target - d.runs
    d["rrr"] = np.where(d.innings == 2, d.runs_needed / d.balls_left.clip(lower=1) * 6, np.nan)
    d["rrr_rel"] = d.rrr - d.lvl_slow
    d["crr_rel"] = d.crr - d.lvl_slow
    comps = sorted(inn.competition.unique())
    d["comp"] = d.competition.map({c: i for i, c in enumerate(comps)}).astype(int)
    d["match_date"] = d.date
    num = d.select_dtypes("float64").columns
    d[num] = d[num].astype("float32")
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        d.to_parquet(BALLS_FILE, index=False)
    return d


def load_balls():
    return pd.read_parquet(BALLS_FILE)


if __name__ == "__main__":
    b = build_balls()
    print(len(b), "deliveries;", b.cls.value_counts(normalize=True).sort_index().round(4).to_dict())
    print(b.groupby("competition").size().to_dict())
    print(b[["lvl_slow", "lvl_fast", "venue_eff", "bat_rpb", "bat_out", "bow_rpb", "bow_wk"]].describe().round(3).T)
    ip = b[(b.competition == "ipl") & (b.innings == 1) & (b.balls_bowled == 0) & (b.ball_in_over == 0)]
    print(ip.groupby("season_year")[["lvl_slow", "lvl_fast"]].mean().round(2).T.to_string())


# ---------- the model ----------
def _offset_feats(over_n, lvl_slow, lvl_fast, log=False):
    """Linear-in-level part: (level - 8) x phase (3) for both levels, plus the phase dummies.
    log=True uses 8 * log(level / 8) (a ratio, so the same relative change counts the same at any level)."""
    ov = np.asarray(over_n)
    ph = np.stack([ov < 6, (ov >= 6) & (ov < 16), ov >= 16], 1).astype(float)
    lv = np.stack([np.asarray(lvl_slow, float), np.asarray(lvl_fast, float)], 1)
    lv = 8 * np.log(lv / 8) if log else lv - 8
    return np.concatenate([(lv[:, :, None] * ph[:, None, :]).reshape(len(ov), -1), ph], 1)


def _softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


class BallModel:
    """P(class | features) = softmax( linear(level, phase) + boosted trees(state, players, venue) ).

    The scoring level enters ONLY through the linear part, because trees cannot extrapolate: IPL levels after 2022
    are higher than anything in the training years. `variant` picks the tree features: A state only, B + batter and
    bowler strength, C + venue effect. `generic` tables (new batter by wicket, bowler by over) are used by the simulator.
    """

    lvl_cols, lvl_log, lvl_shrink, season_neutral = ("lvl_slow", "lvl_fast"), False, 1.0, False  # defaults for older pickles
    TREE_BASE = ["over_n", "ball_in_over", "balls_bowled", "wickets", "innings", "crr", "target", "runs_needed", "rrr", "comp"]
    PARAMS = dict(objective="multiclass", num_class=8, learning_rate=0.08, num_leaves=31, min_data_in_leaf=200,
                  feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=5)

    def __init__(self, variant="B", params=None, lvl_cols=("lvl_slow", "lvl_fast"), lvl_log=False,
                 lvl_shrink=1.0, season_neutral=False):
        """season_neutral: while fitting the trees, a per-(competition, season, phase) shift is added to the offset so that
        the offset matches that season's average runs; the trees then cannot learn the season-level scoring (era), and
        the shift is NOT used at prediction time.
        lvl_cols: which two level columns feed the linear part. lvl_log: level as 8*log(level/8).
        lvl_shrink: fitted level coefficients are multiplied by this before the trees are fitted (1 = off)."""
        self.variant, self.lvl_cols, self.lvl_log, self.lvl_shrink = variant, tuple(lvl_cols), lvl_log, lvl_shrink
        self.season_neutral = season_neutral
        self.feats = self.TREE_BASE + (["bat_rpb", "bat_out", "bat_exp", "bat_faced", "bow_rpb", "bow_wk"] if variant >= "B" else []) \
            + (["venue_eff"] if variant == "C" else [])
        self.params = {**self.PARAMS, **(params or {})}

    def _off(self, d):
        o = _offset_feats(d["over_n"], d[self.lvl_cols[0]], d[self.lvl_cols[1]], self.lvl_log)
        return o @ self.lr_coef.T + self.lr_b

    def _season_shift(self, d):
        """Tilt (shift of the logits along the runs-per-class direction) per (competition, season, phase) so that the
        offset's mean runs per ball equals the actual mean in that group. Returns an (n, 8) array."""
        z = self._off(d)
        R = RUNS.astype(float)
        ph = np.where(d.over_n < 6, 0, np.where(d.over_n < 16, 1, 2))
        g = pd.factorize(pd.Series(d.competition.astype(str).to_numpy() + "|" + d.season_year.astype(str).to_numpy() + "|" + ph.astype(str)))[0]
        ng = g.max() + 1
        cnt = np.bincount(g, minlength=ng)
        target = np.bincount(g, weights=R[d.cls.to_numpy()], minlength=ng) / cnt
        lo, hi = np.full(ng, -1.5), np.full(ng, 1.5)
        for _ in range(25):
            lam = (lo + hi) / 2
            pr = _softmax(z + lam[g][:, None] * R)
            f = np.bincount(g, weights=pr @ R, minlength=ng) / cnt - target
            lo, hi = np.where(f < 0, lam, lo), np.where(f < 0, hi, lam)
        return ((lo + hi) / 2)[g][:, None] * R

    def _x(self, d):
        return np.column_stack([np.asarray(d[c], dtype="float32") for c in self.feats])

    def fit(self, train, valid, rounds=1000, n_rounds=None):
        """train/valid: ball tables. valid is the inner time fold used for early stopping (None + n_rounds = no stop)."""
        import lightgbm as lgb
        from sklearn.linear_model import LogisticRegression

        lr = LogisticRegression(C=10, max_iter=300).fit(
            _offset_feats(train.over_n, train[self.lvl_cols[0]], train[self.lvl_cols[1]], self.lvl_log), train.cls)
        self.lr_coef, self.lr_b = lr.coef_.copy(), lr.intercept_
        if self.lvl_shrink != 1.0:  # shrink only the level columns (first 6), keep phase dummies
            self.lr_coef[:, :6] *= self.lvl_shrink
        off = (lambda d: self._off(d) + self._season_shift(d)) if self.season_neutral else self._off
        ds = lambda d, ref=None: lgb.Dataset(self._x(d), d.cls.to_numpy(), init_score=off(d), feature_name=self.feats,  # noqa: E731
                                              categorical_feature=["comp"], reference=ref)
        dt = ds(train)
        if n_rounds is None:
            m = lgb.train(self.params, dt, rounds, valid_sets=[ds(valid, dt)], callbacks=[lgb.early_stopping(30, verbose=False)])
            self.best_iter = m.best_iteration
        else:
            m = lgb.train(self.params, dt, n_rounds)
            self.best_iter = n_rounds
        self.booster = m
        self._generic(train)
        t = train
        self.wk_runs = float(t[t.cls == WK].runs_total.mean())
        self.ex_extra = float((t[t.cls == EX].runs_total - 1).clip(lower=0).mean())
        return self

    def _generic(self, t):
        """Strength of an unknown incoming batter (by wickets down) and unknown bowler (by over), from train data."""
        nb = t[t.bat_faced == 0].groupby("wickets")[["bat_rpb", "bat_out", "bat_exp"]].mean().reindex(range(11)).ffill().bfill()
        self.gen_bat = nb.to_numpy()
        ob = t.groupby(t.over_n.clip(upper=19))[["bow_rpb", "bow_wk"]].mean().reindex(range(20)).ffill().bfill()
        self.gen_bowl = ob.to_numpy()

    def proba(self, d):
        """d: mapping name -> array (or DataFrame) of feature columns. Returns (n, 8) probabilities."""
        z = self.booster.predict(self._x(d), raw_score=True, num_iteration=self.best_iter) + self._off(d)
        return _softmax(z)

    def save(self, name):
        import pickle

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(MODEL_DIR / f"{name}.pkl", "wb") as f:
            pickle.dump(self, f)
