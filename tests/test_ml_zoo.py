"""Model-zoo wrappers on synthetic data: ordered quantiles, 0 <= p <= 1, GRU forward shape."""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import model_zoo as Z


def synth(n=1500, seed=0):
    r = np.random.default_rng(seed)
    d = pd.DataFrame({c: r.normal(size=n) for c in Z.WCOLS})
    d["comp_code"] = r.integers(0, Z.CMAX, n)
    y = d.runs * 2 + r.normal(size=n)
    return d, y.to_numpy(float), (y > 0).astype(float), np.ones(n)


@pytest.mark.parametrize("fam", [Z.XGB(), Z.Cat(), Z.Forest(False), Z.Forest(True), Z.HGB()])
def test_family_outputs(fam):
    d, y, yb, w = synth()
    cols = Z.WCOLS
    X = fam.X(d, cols)
    cfg = fam.grid("score")[0]
    n = {"XGBoost": 20, "CatBoost": 20, "HistGradientBoosting": [20, 20, 20]}.get(fam.name, 0)
    m, n = fam.fit("score", X, y, w, cfg, n=n)
    q = fam.predict("score", m, X, n)
    if fam.quantile:
        q = np.sort(q, axis=1)  # the runner sorts, as G2 does
        assert q.shape == (len(d), 3) and (q[:, 0] <= q[:, 1]).all() and (q[:, 1] <= q[:, 2]).all()
    else:
        assert q.shape == (len(d),)
    n = {"XGBoost": 20, "CatBoost": 20, "HistGradientBoosting": [20]}.get(fam.name, 0)
    m, n = fam.fit("win", X, yb, w, fam.grid("win")[0], n=n)
    p = fam.predict("win", m, X, n)
    assert p.shape == (len(d),) and (p >= 0).all() and (p <= 1).all()


def test_gru_shapes():
    torch = pytest.importorskip("torch")
    for kind, last in (("score", 3), ("win", None)):
        net = Z._net(kind)
        out = net(torch.zeros(4, 30, 7), torch.zeros(4, 2 + Z.CMAX))
        assert out.shape == ((4, 30, 3) if last else (4, 30))
        if last:
            assert (out[..., 0] <= out[..., 1]).all() and (out[..., 1] <= out[..., 2]).all()
