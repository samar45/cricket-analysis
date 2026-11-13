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


# ---------- sim-R: real batters still to come, real bowlers' overs left ----------
from types import SimpleNamespace  # noqa: E402

from cricket_analytics.ml import resources as R  # noqa: E402
from cricket_analytics.ml import simfix as SF  # noqa: E402
from cricket_analytics.ml.simulate import order_batters, schedule_bowlers  # noqa: E402


class Spy(Fixed):
    """Every ball a wicket; records the striker's bat_rpb and the bowler's bow_rpb seen at each ball of path 0."""

    def __init__(self):
        super().__init__([0, 0, 0, 0, 0, 0, 1, 0])
        self.bat, self.bowl = [], []

    def proba(self, f):
        self.bat.append(float(f["bat_rpb"][0]))
        self.bowl.append(float(f["bow_rpb"][0]))
        return super().proba(f)


def test_wickets_bring_in_the_queue_in_order():
    q = np.full((1, 11, 3), np.nan)
    q[0, :4] = [[5, .1, 1], [6, .1, 1], [7, .1, 1], [8, .1, 1]]
    m = Spy()
    simulate(m, state(wickets=3, s_rpb=2.0), n=1, plan={"bat_q": q, "bow_s": np.full((1, 20, 2), np.nan)})
    assert m.bat[:5] == [2.0, 5.0, 6.0, 7.0, 8.0]  # then the generic batter (1.0) once the queue is empty


def test_plan_none_is_the_old_simulator():
    a = simulate(one_run(), state(runs=3), n=5, seed=2)
    b = simulate(one_run(), state(runs=3), n=5, seed=2, plan={"bat_q": np.full((1, 11, 3), np.nan), "bow_s": np.full((1, 20, 2), np.nan)})
    assert (a["final"] == b["final"]).all()


def test_bowler_schedule_respects_four_overs_and_no_back_to_back():
    pool = {c: (1.0 + i / 10, 0.05) for i, c in enumerate("ABCDE")}
    for k, cur, done in ((0, "A", {}), (60, "C", {"A": 2, "B": 3, "C": 1, "D": 3, "E": 1}), (90, "E", {"A": 4, "B": 3, "C": 2, "D": 3, "E": 3})):
        cap = {c: 4 - done.get(c, 0) for c in pool}
        out, plan = schedule_bowlers(pool, cap, cur, k)
        seq = [cur] + [plan.get(j) for j in range(k // 6 + 1, 20)]
        used = {c: seq.count(c) + done.get(c, 0) for c in pool}
        assert max(used.values()) <= 4
        assert all(a != b for a, b in zip(seq, seq[1:]) if a and b)
        assert not np.isnan(out[k // 6 + 1:]).all(axis=1).any() or sum(cap.values()) < 20 - k // 6


def test_simulated_innings_uses_scheduled_bowlers():
    pool = {c: (1.0 + i, 0.05) for i, c in enumerate("ABCDE")}
    out, plan = schedule_bowlers(pool, {c: 4 for c in pool}, "A", 0)
    m = Spy()
    m.p = np.array([0, 1, 0, 0, 0, 0, 0, 0.0])
    simulate(m, state(), n=1, plan={"bat_q": np.full((1, 11, 3), np.nan), "bow_s": out[None]})
    per_over = [m.bowl[i * 6] for i in range(1, 20)]
    assert per_over == [out[j, 0] for j in range(1, 20)]


def test_batter_order_ignores_insertion_order():
    left = {"x": (9.0, (1, 1, 1)), "y": (4.0, (2, 2, 2)), "z": (6.5, (3, 3, 3))}
    assert order_batters(left)[:3, 0].tolist() == [2, 3, 1] and order_batters(dict(reversed(left.items())))[:3, 0].tolist() == [2, 3, 1]


def test_build_plan_reads_only_the_state_so_far():
    """Shuffling who bats / bowls AFTER the checkpoint must not change the plan (XI and prior strengths are what count)."""
    rows = []
    bats = ["a", "b", "c", "d", "e", "f"]
    for j in range(60):
        rows.append(dict(match_id="m", innings=1, ball_seq=j, balls_bowled=j, legal=1, batter=bats[0 if j < 40 else 2], non_striker=bats[1],
                         bowler="pq"[(j // 6) % 2], bat_rpb=1.0, bat_out=.05, bat_exp=3.0, bow_rpb=1.2, bow_wk=.05, match_date=pd.Timestamp("2025-04-01")))
    old = [dict(rows[0], match_id="m0", batter=x, non_striker=x, ball_seq=i, match_date=pd.Timestamp("2025-03-01")) for i, x in enumerate("def")]
    b = pd.concat([pd.DataFrame(rows), pd.DataFrame(old)], ignore_index=True)
    ctx = SF.PlanCtx.__new__(SF.PlanCtx)
    ctx.R, ctx.dates = R, {"m": pd.Timestamp("2025-04-01")}
    ctx.S = SimpleNamespace(bat=lambda k, d: (0.5, 1.0, {"c": 5.0, "d": 4.0, "e": 8.0, "f": 7.0}.get(k[0], 3.0)), bowl=lambda k, d: (1, 1, 1, 0.9))
    ctx.teams = pd.DataFrame({"batting_team": ["T1"], "bowling_team": ["T2"]}, index=pd.MultiIndex.from_tuples([("m", 1)]))
    ctx.side = {("m", "T1"): pd.DataFrame({"player": bats}), ("m", "T2"): pd.DataFrame({"player": ["p", "q", "r", "s", "t"]})}
    ctx.bat0 = SF.PlanCtx._first(b.assign(batter=b.batter), "batter", ["bat_rpb", "bat_out", "bat_exp"])
    ctx.bowl0 = SF.PlanCtx._first(b, "bowler", ["bow_rpb", "bow_wk"])
    st = pd.DataFrame({"match_id": ["m"], "innings": [1], "balls_bowled": [30]})
    p1 = SF.build_plan(ctx, st, b[b.match_id == "m"])
    # at ball 30: a (striker) and b are in; c batted from ball 40 on (future) -> still "to come", and d, e, f too, ordered by prior position (d, c, f, e)
    assert int((~np.isnan(p1["bat_q"][0, :, 0])).sum()) == 4
    b2 = b.copy()
    b2.loc[(b2.match_id == "m") & (b2.balls_bowled > 30), "batter"] = "f"  # change the future batting
    b2.loc[(b2.match_id == "m") & (b2.balls_bowled > 30), "bowler"] = "r"
    p2 = SF.build_plan(ctx, st, b2[b2.match_id == "m"])
    assert np.allclose(p1["bat_q"], p2["bat_q"], equal_nan=True)
    assert np.isnan(p1["bat_q"][0, 4:]).all()
