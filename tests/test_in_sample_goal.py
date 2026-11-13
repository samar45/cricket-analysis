"""Goal test: the in_sample flag follows the training cutoff recorded in production_meta.json."""

import json

import pandas as pd
import pytest

from cricket_analytics.ml import predict as P

META = P.MODEL_DIR / "production_meta.json"
pytestmark = pytest.mark.skipif(not META.exists(), reason="production_meta.json not built")


def test_non_ipl_2026_match_before_cutoff_is_in_sample():
    assert P.is_in_sample(pd.Timestamp("2026-06-01"), "t20i_men") is True


def test_match_after_cutoff_is_not_in_sample():
    cutoff = pd.Timestamp(json.loads(META.read_text())["cutoff"])
    assert P.is_in_sample(cutoff, "ipl") is True
    assert P.is_in_sample(cutoff + pd.Timedelta(days=1), "ipl") is False
    assert P.is_in_sample(cutoff + pd.Timedelta(days=1), "t20i_men") is False
