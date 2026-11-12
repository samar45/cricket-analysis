import numpy as np
import pandas as pd

from cricket_analytics.models.death_execution import add_execution, pair_stats, shrink


def test_shrink_limits():
    assert shrink(0, 0, 50, 0.4) == 0.4
    assert abs(shrink(1000, 2000, 50, 0.1) - 0.5) < 0.03


def test_pair_stats_signal():
    rng = np.random.default_rng(0)
    rows = []
    for b in range(150):
        skill = rng.normal()
        for yr in (2020, 2021):
            rows.append(dict(bowler=b, year=yr, death_balls=60, y=rng.binomial(40, 0.5 + 0.1 * np.tanh(skill)), ft=0,
                             econ_death=9 - skill + rng.normal(0, .5)))
    t = pd.DataFrame(rows)
    t["ft"] = 40 - t.y
    t = add_execution(t)
    s = pair_stats(t)
    assert s["n_pairs"] == 150 and s["repeat_execution_shrunk"] > 0.3 and s["r2_gain"] >= 0
