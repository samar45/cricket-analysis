import numpy as np
import pandas as pd

from cricket_analytics.ml.validate import KEYS, align, ensemble


def _frame(rows, **cols):
    return pd.DataFrame(rows, columns=KEYS).assign(**cols)


def test_align_keeps_common_rows_in_same_order():
    a = _frame([(1, 1, 0), (1, 1, 36), (2, 1, 0)], q50=[1.0, 2, 3])
    b = _frame([(2, 1, 0), (1, 1, 0)], q50=[30.0, 10])  # different order, missing (1,1,36)
    out = align({"a": a, "b": b})
    assert len(out["a"]) == len(out["b"]) == 2
    assert (out["a"][KEYS].to_numpy() == out["b"][KEYS].to_numpy()).all()
    assert out["b"].q50.tolist() == [10, 30]  # row (1,1,0) first, then (2,1,0), values stayed with their key


def test_ensemble_averages_and_keeps_quantile_order():
    k = [(1, 1, 0), (2, 1, 0)]
    a = _frame(k, q10=[100.0, 150], q50=[150.0, 160], q90=[200.0, 180])
    b = _frame(k, q10=[120.0, 90], q50=[140.0, 200], q90=[190.0, 230])
    e = ensemble(a, b, "score")
    assert np.allclose(e.q50, [145, 180])
    assert (e.q10 <= e.q50).all() and (e.q50 <= e.q90).all()
    crossed = _frame(k, q10=[100.0, 100], q50=[90.0, 100], q90=[80.0, 100])  # a model with crossing quantiles
    e2 = ensemble(crossed, crossed, "score")
    assert (e2.q10 <= e2.q50).all() and (e2.q50 <= e2.q90).all()


def test_ensemble_win_is_mean_of_p():
    k = [(1, 2, 6)]
    e = ensemble(_frame(k, p=[0.2]), _frame(k, p=[0.6]), "win")
    assert np.isclose(e.p.iloc[0], 0.4)
