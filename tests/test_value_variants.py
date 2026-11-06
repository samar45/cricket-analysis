"""Phase / group value variants (models/value_variants.py): the DB-free pieces."""

import pandas as pd
import pytest

from cricket_analytics.models import value_variants as V


def test_shift_is_relative_to_pooled_replacement():
    repl = pd.DataFrame(
        [("bat", "indian", -5.0), ("bat", "overseas", -1.0), ("bat", "all", -4.0)], columns=["role", "group", "per100"]
    )
    s = V._shift(repl)
    assert s["bat", "indian"] == pytest.approx(-0.01) and s["bat", "overseas"] == pytest.approx(0.03) and s["bat", "all"] == 0


def test_phase_value_applies_weights_per_phase():
    T = pd.DataFrame(
        dict(comp="ipl", sy=2025, player="A", role="bat", phase=["powerplay", "death"], balls=[10, 10], ra=[2.0, 2.0])
    )
    w = {"bat": {"powerplay": 1.0, "middle": 1.0, "death": 2.0}, "bowl": {}}
    out = V._phase_value(T, 2025, w, years=1)
    assert out.loc["A", "bat"] == pytest.approx(6.0) and out.loc["A", "bat_rate"] == pytest.approx(0.3)
