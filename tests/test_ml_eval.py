import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import evaluate as ev


def test_holdout_guard():
    df = pd.DataFrame({"season_year": [2024, 2025, 2026], "x": [1, 2, 3]})
    with pytest.raises(ValueError):
        list(ev.rolling_splits(df, test_years=(2025, 2026)))
    (y, tr, te), = ev.rolling_splits(df, test_years=(2025,))
    assert y == 2025 and tr.season_year.max() == 2024 and (te.season_year == 2025).all()
    assert len(list(ev.rolling_splits(df, test_years=(2026,), allow_holdout=True))) == 1


def test_perfect_predictions_have_zero_error():
    y = np.array([150.0, 180, 200])
    assert ev.mae(y, y) == 0 and ev.pinball(y, y, 0.9) == 0
    assert ev.coverage(y, y - 1, y + 1) == 1
    assert ev.crps_samples(y, np.tile(y[:, None], (1, 5))) == pytest.approx(0)
    assert ev.log_loss([1, 0], [1, 0]) < 1e-5 and ev.brier([1, 0], [1, 0]) == 0


def test_ece_of_calibrated_synthetic_is_small():
    rng = np.random.default_rng(0)
    p = rng.uniform(size=200_000)
    y = rng.uniform(size=p.size) < p
    assert ev.ece(y, p) < 0.01
    assert ev.ece(y, np.clip(p + 0.2, 0, 1)) > 0.1  # a biased model is flagged


def test_crps_matches_brute_force():
    rng = np.random.default_rng(1)
    x, y = rng.normal(size=(3, 40)), rng.normal(size=3)
    brute = [np.abs(x[i] - y[i]).mean() - 0.5 * np.abs(x[i][:, None] - x[i][None]).mean() for i in range(3)]
    assert ev.crps_samples(y, x) == pytest.approx(np.mean(brute))


def test_match_weights_sum_to_one_per_innings():
    df = pd.DataFrame({"match_id": ["a"] * 3 + ["b"], "innings": [1] * 4})
    assert ev.match_weights(df).sum() == pytest.approx(2)
