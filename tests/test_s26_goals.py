"""Goal tests for the S26 mask (SMAT 2026 live test set, docs/ML_PREDICTION.md Amendment 2). Frozen."""
import pandas as pd

from cricket_analytics.ml import evaluate as ev


def _df():
    rows = [
        ("male", "smat", "2026-11-20"),    # S26
        ("male", "smat", "2026-10-15"),    # S26 (boundary)
        ("male", "smat", "2026-10-14"),    # before
        ("male", "smat", "2024-12-01"),    # old SMAT
        ("female", "smat", "2026-11-20"),  # not men's
        ("male", "ipl", "2026-11-20"),     # other competition
        ("male", "bbl", "2026-11-20"),     # fresh3 but not S26
    ]
    return pd.DataFrame(rows, columns=["gender", "competition", "date"]).assign(batting_team="A", bowling_team="B")


def test_constant():
    assert ev.S26_FROM == "2026-10-15"


def test_s26_mask_rows():
    assert ev.s26_mask(_df()).tolist() == [True, True, False, False, False, False, False]


def test_s26_inside_fresh3():
    df = _df()
    s, f = ev.s26_mask(df), ev.fresh3_mask(df)
    assert s.any() and (f[s]).all()


def test_scoring_mask_excludes_s26():
    df = _df()
    got = ev.fresh3_scoring_mask(df)
    assert (got == (ev.fresh3_mask(df) & ~ev.s26_mask(df))).all()
    assert got.tolist() == [False, False, False, False, False, True, True]
