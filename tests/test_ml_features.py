"""Leak-free features: prior-only, shrinkage behaves, feature list frozen."""

import numpy as np
import pandas as pd

from cricket_analytics.ml import features as F


def _inn(n=60, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(n):
        d = pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(m // 2))  # two matches per date
        v = "A" if m % 3 else "B"
        t1, t2 = ("X", "Y") if m % 2 else ("Y", "X")
        tot = 150 + (30 if v == "B" else 0) + rng.normal(0, 15)
        for i, (bt, bw) in enumerate(((t1, t2), (t2, t1)), 1):
            rows.append(dict(match_id=str(m), innings=i, date=d, competition="ipl", gender="male", venue=v,
                             batting_team=bt, bowling_team=bw, season_year=2020, reduced=False, final_total=tot + 5 * i))
    return pd.DataFrame(rows)


def test_no_leakage_later_matches_do_not_change_earlier_rows():
    inn = _inn()
    cut = pd.Timestamp("2020-01-15")
    full = F.innings_features(inn).set_index(["match_id", "innings"])
    part = F.innings_features(inn[inn.date <= cut]).set_index(["match_id", "innings"])
    pd.testing.assert_frame_equal(full.loc[part.index], part)


def test_same_date_matches_do_not_see_each_other():
    inn = _inn()
    f = F.innings_features(inn).set_index(["match_id", "innings"])
    assert f.loc[("0", 1), "lvl_ew"] == f.loc[("1", 1), "lvl_ew"] == (F.PRIOR_MEAN)  # both on day 1, nothing earlier


def test_shrinkage_pulls_toward_zero_and_raw_is_larger():
    inn = _inn()
    sh = F.innings_features(inn, k_venue=50).venue_eff.abs()
    raw = F.innings_features(inn, k_venue=0).venue_eff.abs()
    assert sh.max() < raw.max()
    last = F.innings_features(inn, k_venue=15).groupby("match_id").venue_eff.first()
    assert last.iloc[-1] != 0  # learned something about the +30 ground


def test_feature_list_frozen():
    assert len(F.FEATURES) == 26 and F.FEATURES[0] == "balls_left" and F.FEATURES[-1] == "ns_faced"
    assert "lvl_ew" in F.FEATURES and set(F.FEATURE_SETS["none"]) < set(F.FEATURES)
