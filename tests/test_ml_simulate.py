"""Simulator and ball-model contract tests (no database needed)."""

import numpy as np
import pandas as pd

from cricket_analytics.ml import ball_model as bm
from cricket_analytics.ml.simulate import simulate, summarize


class Fixed:
    """Fake ball model: the same class probabilities everywhere."""

    gen_bat = np.ones((11, 3))
    gen_bowl = np.ones((20, 2))
    wk_runs = ex_extra = 0.0

    def __init__(self, p):
        self.p = np.asarray(p, float)

    def proba(self, f):
        return np.tile(self.p, (len(f["balls_bowled"]), 1))


def state(**kw):
    d = dict(runs=0, wickets=0, balls_bowled=0, innings=1, target=np.nan, max_balls=120, lvl_slow=8.0, lvl_fast=8.0,
             comp=0, venue_eff=0.0, s_rpb=1.2, s_out=0.05, s_exp=4.0, s_faced=0, n_rpb=1.2, n_out=0.05, n_exp=4.0,
             n_faced=0, bow_rpb=1.2, bow_wk=0.05)
    return pd.DataFrame([{**d, **kw}])


def one_run():
    return Fixed([0, 1, 0, 0, 0, 0, 0, 0])


def test_always_one_run_exact_total():
    r = simulate(one_run(), state(runs=30, balls_bowled=18), n=50)
    assert (r["final"] == 30 + 102).all() and (r["wickets"] == 0).all()


def test_every_ball_a_wicket_ends_at_ten():
    r = simulate(Fixed([0, 0, 0, 0, 0, 0, 1, 0]), state(runs=5, wickets=3), n=20)
    assert (r["final"] == 5).all() and (r["wickets"] == 10).all()


def test_wides_add_runs_without_using_balls():
    # half the balls are wides (+1), half dots: expected innings > 120 runs but the legal balls still end at 120
    r = simulate(Fixed([0.5, 0, 0, 0, 0, 0, 0, 0.5]), state(), n=300, seed=1)
    assert r["final"].mean() > 100 and (r["final"] >= 1).all()


def test_win_probability_one_when_target_reached():
    st = state(innings=2, runs=150, balls_bowled=60, target=150.0)
    assert simulate(one_run(), st, n=10)["win"][0] == 1.0


def test_chase_exact_and_tie_half():
    # one run a ball: needs 60 from 60 balls -> reaches target on the last ball; needs 61 -> lose by 1? (tie at target-1)
    won = simulate(one_run(), state(innings=2, runs=60, balls_bowled=60, target=120.0), n=10)["win"][0]
    tie = simulate(one_run(), state(innings=2, runs=60, balls_bowled=60, target=121.0), n=10)["win"][0]
    lost = simulate(one_run(), state(innings=2, runs=60, balls_bowled=60, target=125.0), n=10)["win"][0]
    assert (won, tie, lost) == (1.0, 0.5, 0.0)


def test_innings_one_win_is_nan_and_summary_quantiles():
    r = simulate(one_run(), state(), n=5)
    assert np.isnan(r["win"][0]) and summarize(r["final"]).q50[0] == 120


def test_ball_model_probabilities_sum_to_one_and_level_effect():
    rng = np.random.default_rng(0)
    n = 6000
    d = pd.DataFrame({"over_n": rng.integers(0, 20, n), "lvl_slow": rng.uniform(7, 9, n), "lvl_fast": rng.uniform(7, 9, n)})
    d["cls"] = np.where(rng.random(n) < 0.1 + 0.05 * (d.lvl_slow - 7), 5, rng.integers(0, 8, n))
    for c in BM_COLS:
        d[c] = rng.random(n)
    d["comp"], d["runs_total"] = 0, 1
    m = bm.BallModel("A", {"num_threads": 2, "min_data_in_leaf": 20}).fit(d, d.iloc[:1000], rounds=20)
    p = m.proba(d)
    assert p.shape == (n, 8) and np.allclose(p.sum(1), 1)
    hi, lo = d.assign(lvl_slow=9.0, lvl_fast=9.0), d.assign(lvl_slow=7.0, lvl_fast=7.0)
    assert m.proba(hi)[:, 5].mean() > m.proba(lo)[:, 5].mean()  # six-probability rises with the scoring level


BM_COLS = ["bat_faced", "bat_rpb", "bat_out", "bat_exp", "bow_rpb", "bow_wk", "ball_in_over", "balls_bowled", "wickets", "innings", "crr", "target", "runs_needed", "rrr"]
