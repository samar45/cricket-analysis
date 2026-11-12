"""Auction demand replay (models/demand.py). DB-free: saved features, usage file and reference CSVs."""

import numpy as np

from cricket_analytics.models import demand as D


def test_replay_state_rules():
    d = D.replay(2026)
    assert len(d) == 156 and d.n_need.le(d.n_afford).all() and d.n_afford.le(10).all()
    assert d.pos.between(0, 1).all() and d.n_hole.ge(d.n_need).all()
    sold = d[d.pos_exact].sort_values("pos")
    assert sold.pos.is_monotonic_increasing


def test_shipped_model_reproduced():
    f = D.build(write=False)
    p = D._fit_predict(f, (2022, 2023, 2024), 2025, [])
    s = p[p.sold]
    assert abs(np.abs(s.p50 - s.price_cr).mean() - 2.08) < 0.02  # docs/VALUE_m4.md validation MAE
