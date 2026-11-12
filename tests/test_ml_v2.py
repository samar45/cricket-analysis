"""v2 checks: the fresh-holdout lock, monotone chase model, stacking weights, prior-only chase features."""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import direct as D
from cricket_analytics.ml import evaluate as ev
from cricket_analytics.ml import features as F
from cricket_analytics.ml import v2


def _rows(comp, date, gender="male", n=3, season=2025):
    return pd.DataFrame({"gender": gender, "competition": comp, "date": pd.Timestamp(date), "season_year": season,
                         "balls_bowled": np.arange(n) * 2})


def test_fresh_mask_and_guard():
    df = pd.concat([_rows("bbl", "2026-01-05"), _rows("ipl", "2026-04-01"), _rows("bbl", "2025-12-31"), _rows("bbl", "2026-02-01", gender="female")])
    m = ev.fresh_holdout_mask(df)
    assert m.sum() == 3 and m[:3].all() and not m[3:].any()  # only men's non-IPL dated >= 2026-01-01
    with pytest.raises(ValueError):
        ev.assert_no_fresh(df, "test")
    ev.assert_no_fresh(df.iloc[3:], "test")  # IPL 2026, 2025 and women's rows are fine
    assert len(ev.assert_no_fresh(df, "test", allow_fresh=True)) == len(df)


def test_split_raises_on_locked_rows():
    feat = pd.concat([_rows("ipl", "2024-04-01", season=2024), _rows("ipl", "2025-04-01", season=2025), _rows("bbl", "2023-01-05", season=2023)], ignore_index=True)
    ok = lambda f: (f.competition == "ipl") & (f.season_year == 2025)  # noqa: E731
    val = lambda f: (f.competition == "ipl") & (f.season_year == 2024)  # noqa: E731
    tr, w, itr, iw, v, te = v2.split(feat, 2025, ok, val)
    assert len(te) == 3 and len(tr) > 0
    bad = pd.concat([feat, _rows("psl", "2026-03-01", season=2026)], ignore_index=True)
    fresh_test = lambda f: f.competition == "psl"  # noqa: E731
    with pytest.raises(ValueError):
        v2.split(bad, 2025, fresh_test, val)  # locked rows in the test set
    v2.split(bad, 2025, fresh_test, val, allow_fresh=True)  # only the explicit flag opens the test set ...
    with pytest.raises(ValueError):
        v2.split(bad, 2027, ok, val, allow_fresh=True)  # ... and training on locked rows is refused even then


def test_monotone_direction_on_grid():
    rng = np.random.default_rng(0)
    cols = v2.WIN["w1"][0]
    n = 6000
    X = pd.DataFrame(rng.normal(size=(n, len(cols))), columns=cols)
    # outcome driven in the right directions plus noise, and some wrong-direction noise features the model must not follow
    z = -X.runs_needed + X.balls_left - X.wickets - X.rrr - X.req_vs_exp + 0.5 * X.crr + rng.normal(scale=1.5, size=n) + 0.8 * X.runs_l30 * np.sign(X.wickets)
    X["chase_won"] = (z > 0).astype(float)
    X["reduced"], X["innings"] = False, 2
    X["balls_left"] = X.balls_left + 10.0
    X["wickets"] = X.wickets.abs().clip(upper=9)
    X["runs_needed"] = X.runs_needed + 5.0
    X["rrr"] = X.rrr.abs()
    cfg = dict(num_leaves=15, min_child_samples=30)
    model, _ = D.fit_win(X, np.ones(n), cols, cfg, rounds=60, extra={"monotone_constraints": v2.mono_list(cols)})
    base = X.sample(60, random_state=1)
    for col, sign in v2.MONO.items():
        grid = np.linspace(X[col].min(), X[col].max(), 25)
        p = np.stack([model.predict(base[cols].assign(**{col: g})) for g in grid])  # (grid, rows)
        assert (np.diff(p, axis=0) * sign >= -1e-9).all(), f"P(win) is not monotone in {col}"


def _pair(rng, n, off=0.0):
    keys = pd.DataFrame({"match_id": np.repeat(np.arange(n // 4), 4).astype(str), "innings": 1, "balls_bowled": np.tile([0, 36, 60, 90], n // 4)})
    y = rng.binomial(1, 0.5, n)
    base = np.clip(0.5 + 0.3 * (y - 0.5) + rng.normal(0, 0.1, n), 0.05, 0.95)
    tot = rng.normal(180, 30, n)
    q = lambda c: np.column_stack([tot + c - 25, tot + c, tot + c + 25])  # noqa: E731
    sd = keys.assign(final_total=tot, **dict(zip(v2.QC, q(0).T)))
    ss = keys.assign(final_total=tot, **dict(zip(v2.QC, q(off).T)))
    wd = keys.assign(chase_won=y, p=base)
    ws = keys.assign(chase_won=y, p=np.clip(base + rng.normal(0, 0.05, n), 0.02, 0.98))
    return sd, ss, wd, ws


def test_stacking_weights_finite():
    rng = np.random.default_rng(3)
    pairs = [_pair(rng, 400, off=5.0) for _ in range(3)]
    for mode in ("global", "cp", "lin"):
        w = v2.fit_weights(pairs, mode)
        vals = list(w["win"].values()) + [x for d in w["score"].values() for x in d.values()]
        assert len(vals) and np.isfinite(vals).all() and all(0.0 <= v <= 1.0 for v in vals)
        sd, ss, wd, ws = pairs[0]
        s = v2.stack_score(sd, ss, w)
        assert (np.diff(s[v2.QC].to_numpy(), axis=1) >= 0).all()
        p = v2.stack_win(wd, ws, w).p
        assert p.between(0, 1).all() and np.isfinite(p).all()


def test_chase_features_are_prior_only():
    d = pd.date_range("2024-01-01", periods=12, freq="D")
    inn = pd.DataFrame({"match_id": [str(i) for i in range(12)], "innings": 2, "date": d, "competition": "x", "gender": "male",
                        "season_year": 2024, "reduced": False, "chase_won": [1.0, 0.0] * 6})
    inn.loc[5, "date"] = inn.loc[4, "date"]  # two matches on one day must not see each other
    a = F.chase_features(inn, 5.0)
    b = F.chase_features(inn[inn.match_id.astype(int) <= 7], 5.0)  # deleting later matches changes nothing before them
    m = a.merge(b, on="match_id")
    assert np.allclose(m.chase_lr_x, m.chase_lr_y) and np.allclose(m.chase_season_x, m.chase_season_y)
    r = a.set_index("match_id")
    assert r.loc["4", "chase_season"] == r.loc["5", "chase_season"]
    assert r.loc["0", "chase_season"] == 0.5  # first match: prior only
