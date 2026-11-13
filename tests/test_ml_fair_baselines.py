"""F-score (level-scaled resource table) and F-chase (logistic): prior-only, ordered, scale with the level, sane on toy states."""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml.baselines import FChase, LevelResource


def toy(n=500, seed=0):
    """n matches of a simple scoring process: per-ball runs ~ Poisson(level / 120), wicket chance 0.05 per ball. Levels 150 / 190."""
    r = np.random.default_rng(seed)
    rows = []
    for m in range(n):
        lvl = (150, 190)[m % 2]
        tot = {}
        for inn in (1, 2):
            runs = wk = 0
            tgt = tot[1] + 1 if inn == 2 else np.nan
            st = [(0, 0, 0)]
            for b in range(1, 121):
                runs += r.poisson(lvl / 120)
                wk += r.random() < 0.05
                st.append((b, runs, wk))
                if wk >= 10 or (inn == 2 and runs >= tgt):
                    break
            tot[inn] = runs
            for b, ru, w in st:
                rows.append((str(m), inn, b, ru, w, tgt, lvl))
            rows[-len(st):] = [x + (runs,) for x in rows[-len(st):]]
    d = pd.DataFrame(rows, columns=["match_id", "innings", "balls_bowled", "runs", "wickets", "target", "lvl_ew", "final_total"])
    d["competition"], d["reduced"], d["season_year"] = "ipl", False, 2020
    d["balls_left"] = 120 - d.balls_bowled
    d["runs_needed"] = d.target - d.runs
    d["chase_won"] = np.where(d.innings == 2, (d.final_total >= d.target).astype(float), np.nan)
    return d


@pytest.fixture(scope="module")
def fitted():
    d = toy()
    tab = LevelResource("ipl").fit(d)
    return d, tab, FChase(tab).fit(d)


def state(**kw):
    base = dict(innings=1, balls_bowled=60, runs=80, wickets=2, balls_left=60, lvl_ew=170.0, final_total=0.0, reduced=False, target=np.nan, runs_needed=np.nan)
    return pd.DataFrame([{**base, **kw}])


def test_f_score_ordered_and_sane(fitted):
    _, tab, _ = fitted
    q = tab.score(state())
    assert (q.q10 <= q.q50).all() and (q.q50 <= q.q90).all() and (q.q10 >= 80).all()
    assert 130 < q.q50.iloc[0] < 230  # 80/2 after 10 overs at level 170
    assert tab.score(state(wickets=7)).q50.iloc[0] < q.q50.iloc[0]  # more wickets down, lower total


def test_f_score_is_prior_only(fitted):
    d, tab, _ = fitted
    s = state()
    a = tab.score(s).q50.iloc[0]
    assert tab.score(s.drop(columns=["final_total"])).q50.iloc[0] == a  # no outcome column is read
    # the scale is the TRAIN mean first-innings total and the row's own prior level: nothing from the test fold
    assert tab.den == pytest.approx(d[(d.innings == 1) & (d.balls_bowled == 0)].final_total.mean())
    # remaining runs scale with the level ratio
    lo, hi = tab.score(state(lvl_ew=100.0)).q50.iloc[0] - 80, tab.score(state(lvl_ew=200.0)).q50.iloc[0] - 80
    assert hi == pytest.approx(2 * lo, rel=1e-6)


def test_conformal_calibration(fitted):
    d, tab, _ = fitted
    v = d[(d.innings == 1) & (d.balls_bowled % 6 == 0) & (d.balls_left > 0) & (d.wickets < 10)]
    w = LevelResource("ipl").fit(d).calibrate(v)
    assert set(w.delta) == {0, 1, 2, 3}  # one delta per over bucket
    a, b = tab.score(v), w.score(v)
    assert (b.q50 == a.q50).all()
    cov = ((v.final_total >= b.q10) & (v.final_total <= b.q90)).mean()
    assert 0.77 <= cov <= 0.9  # about 80% on the calibration data
    assert (b.q10 <= b.q50).all() and (b.q50 <= b.q90).all()


def test_f_chase_sane(fitted):
    _, _, ch = fitted
    easy = state(innings=2, balls_bowled=108, runs=160, wickets=2, balls_left=12, target=170.0, runs_needed=10.0)
    hard = state(innings=2, balls_bowled=108, runs=100, wickets=8, balls_left=12, target=200.0, runs_needed=100.0)
    pe, ph = ch.win(easy).iloc[0], ch.win(hard).iloc[0]
    assert 0 <= ph < 0.05 and pe > 0.7
    runs_needed = np.arange(10, 120, 10.0)
    p = ch.win(pd.concat([hard.assign(runs_needed=x, target=100 + x) for x in runs_needed], ignore_index=True)).to_numpy()
    assert (np.diff(p) <= 1e-9).all()  # more runs needed, lower win chance


def test_f_chase_does_not_read_outcomes(fitted):
    _, _, ch = fitted
    s = state(innings=2, runs=100, wickets=4, target=170.0, runs_needed=70.0)
    assert ch.win(s.assign(chase_won=1.0)).iloc[0] == ch.win(s.assign(chase_won=0.0)).iloc[0]
