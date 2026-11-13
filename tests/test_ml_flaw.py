"""Flaw hunt: window / pair features are prior-only inside the innings, events are detected correctly, the matched-baseline test is sane."""

import numpy as np
import pandas as pd

from cricket_analytics.ml import features as F
from cricket_analytics.ml import flaw_tests as T


def synth(n=45, fall=(36, 38, 40)):
    """One innings, one run a ball. Batter A faces balls 1-35 and is out on ball 36 (set: 35 balls faced); later wickets at 38, 40."""
    b = np.arange(n + 1)
    wk = np.array([sum(t >= f for f in fall) for t in b])
    striker = np.where(b < 36, "A", np.where(b < 38, "C", np.where(b < 40, "D", "E")))
    return pd.DataFrame({"match_id": "m", "innings": 1, "balls_bowled": b.astype(float), "runs": b.astype(float), "wickets": wk.astype(float),
                         "striker": striker, "non_striker": "B", "balls_left": 120.0 - b, "runs_needed": np.nan})


def test_windows_are_prior_only():
    s = synth()
    full = F.window_cols(s, (6, 12))
    cut = F.window_cols(s.iloc[:30].reset_index(drop=True), (6, 12))  # later balls removed -> earlier rows unchanged
    assert np.array_equal(full["runs_l6"][:30], cut["runs_l6"])
    assert full["runs_l6"][20] == 6 and full["runs_l12"][5] == 5  # short innings: window starts at ball 0
    assert full["wk_l6"][38] == 2 and full["wk_l6"][37] == 1  # wickets at 36 and 38 both inside the last 6 balls at row 38? (36 yes, 38 yes)


def test_pair_and_set_out():
    s = synth()
    sf, nf = F._faced(s)
    assert sf[35] == 35  # A has faced 35 balls before row 35
    pc = F.pair_cols(s, sf, nf)
    assert pc["since_set_out"][35] == F.SINCE_CAP and pc["since_set_out"][36] == 0 and pc["since_set_out"][39] == 3
    assert pc["pair_balls"][36] == 0 and pc["pair_balls"][37] == 1 and pc["pair_runs"][37] == 1
    assert pc["pair_balls"][20] == 20  # before the first wicket: whole innings
    fell, set_out = F.dismissals(s, sf, nf)
    assert fell.sum() == 3 and set_out.sum() == 1 and set_out[36]  # only A (35 balls) counts as set; C and D faced 2 balls each


def test_event_mask_and_matched_baseline():
    e = pd.DataFrame({"wk_l12": [0, 3, 2, 0], "wk_l6": 0, "wk_l18": 0, "wk_l24": 0, "runs_l6": 0, "runs_l12": 0, "runs_l18": 0})
    defs = T.event_defs({6: 16.0, 12: 28.0, 18: 39.0})
    assert defs["collapse 3wk/12b"][0](e).tolist() == [False, True, False, False]
    assert defs["collapse 2wk/12b"][0](e).tolist() == [False, True, True, False]
    # event states are 5 runs too high at every over; non-event states are unbiased -> excess +5, tight interval
    rng = np.random.default_rng(0)
    n = 400
    mi = np.repeat(np.arange(n // 2), 2)
    oi = np.tile([0, 1], n // 2)
    mask = np.tile([True, False], n // 2)
    err = np.where(mask, 5.0, 0.0) + rng.normal(0, 1, n)
    r = T.excess(mask, err, np.abs(err), mi, oi, B=300)
    assert abs(r["bias_diff"] - 5) < 0.3 and r["bias_lo"] > 4 and r["n_matches"] == n // 2
