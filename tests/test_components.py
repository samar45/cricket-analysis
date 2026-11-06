"""Component projection, controllable value and stability (models/components.py). Synthetic tests need no DB; the identity test
needs the real DB (skipped in CI)."""

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.models import components as C
from cricket_analytics.models import war as W
from tests.conftest import requires_real_db


def test_mom_k_recovers_known_constant():
    rng = np.random.default_rng(0)
    p, m = 0.3, 4000
    tau2 = 0.02**2
    true = p + rng.normal(0, tau2**0.5, m)
    n = rng.integers(100, 800, m)
    x = rng.binomial(n, true) / n
    k, t2 = C.mom_k(n, x, p * (1 - p))
    assert 0.6 * p * (1 - p) / tau2 < k < 1.6 * p * (1 - p) / tau2
    assert t2 == pytest.approx(tau2, rel=0.4)
    # pure noise -> no signal: k is huge, not negative or NaN
    k0, _ = C.mom_k(n, rng.binomial(n, np.full(m, p)) / n, p * (1 - p))
    assert k0 > 20 * k


def _fake_frames(role, players=300, balls=700, seed=1):
    """Ball frames where each player has his own dot probability (talent sd 0.05 around 0.35)."""
    rng = np.random.default_rng(seed)
    talent = np.clip(0.35 + rng.normal(0, 0.05, players), 0.05, 0.9)
    rows = []
    for i, p in enumerate(talent):
        dot = rng.random(balls) < p
        rows.append(
            pd.DataFrame(
                dict(
                    player=f"p{i}",
                    date=pd.Timestamp("2024-01-01")
                    + pd.to_timedelta(np.arange(balls) // 24, unit="D"),
                    match_id=np.arange(balls) // 24 + 1000 * i,
                    innings=1,
                    lb=np.arange(balls) % 24,
                    c=np.where(dot, 0, 1),
                    runs=np.where(dot, 0, 1),
                    ra=0.0,
                )
            )
        )
    return pd.concat(rows, ignore_index=True), talent


def test_stability_matches_the_known_answer():
    d, talent = _fake_frames("bat")
    t = C.stability(d, "bat", [100, 200, 400, 600], boot=20).set_index("component")
    p = 0.35
    k_true = p * (1 - p) / talent.var()  # balls at which reliability is 0.5
    assert 0.6 * k_true < t.loc["dot %", "n50"] < 1.6 * k_true
    assert t.loc["dot %", "n50_lo"] < t.loc["dot %", "n50"] < t.loc["dot %", "n50_hi"]
    assert t.loc["dot %", "n70"] == pytest.approx(t.loc["dot %", "n50"] * 7 / 3)
    assert t.loc["dot %", "R@600"] > t.loc["dot %", "R@100"]  # reliability grows with the sample
    assert t.loc["six %", "R@600"] < 0.2  # no six in the fake data, nothing to repeat


def _panel(n_players=4):
    """Two-year toy panel: player 0 has a big, well-measured dot-ball surplus; player 1 the same surplus on 10 balls."""
    tab = {}
    for role, cls in C.CLS.items():
        rows = []
        for y in (2024, 2025):
            for i, (n, s) in enumerate([(500, 50.0), (10, 1.0), (400, 0.0), (0, 0.0)][:n_players]):
                r = dict(comp="ipl", sy=y, player=f"q{i}", n=float(n), B=0.0, R=0.0)
                r.update({f"s_{c}": (s if c == "dot" else 0.0) for c in cls})
                rows.append(r)
        tab[role] = pd.DataFrame(rows)
    return C.Panel2(tab, y0=2020, y1=2027)


def test_parts_are_shrunk_by_evidence_and_by_k():
    P = _panel()
    ks = {r: {**{c: 100.0 for c in C.CLS[r]}, "R": 100.0} for r in C.CLS}
    prm = {"ipl_from": 2023, "bat": dict(a=0.0, s=1.0, mk=1.0, rw=1.0)}
    parts, den = C.project_parts(P, "bat", 2026, prm, ks)
    i0, i1 = P.players.index("q0"), P.players.index("q1")
    assert parts["dot"][i0] == pytest.approx(100.0 / (1000 + 100))  # 2 x 50 over 1000 balls + k
    assert (
        parts["dot"][i1] < parts["dot"][i0] / 3
    )  # same surplus rate, 20 balls of evidence: pulled to 0
    assert parts["dot"][P.players.index("q2")] == 0.0
    # a bigger k pulls the projection closer to 0; the base part is not shrunk by k
    big = {r: {c: 1e6 for c in v} for r, v in ks.items()}
    assert abs(C.project_parts(P, "bat", 2026, prm, big)[0]["dot"][i0]) < 1e-3
    # controllable value uses a heavier wicket shrink than the plain projection
    p4, _ = C.project_parts(P, "bat", 2026, prm, ks, wk_mult=C.CTRL_WK_MULT)
    assert p4["out"][i0] == parts["out"][i0] == 0.0


def test_saved_params_and_csv_columns():
    p = W.DATA / "components_params.json"
    assert p.exists()
    d = pd.read_csv(W.DATA / "pwar_ipl_2027.csv")
    assert {"pwar", "controllable_war", "controllable_bat", "controllable_bowl"} <= set(d.columns)
    assert (d.controllable_war - (d.controllable_bat + d.controllable_bowl)).abs().max() < 0.0021
    assert d.controllable_war.notna().mean() > 0.95


@requires_real_db
def test_parts_add_up_to_war_input_for_ipl():
    """base + class parts + R equals the runs added that WAR uses, for every IPL player-season (exact by construction), and
    the class shares per league-season sum to about 1."""
    rows, _ = W.season_table("ipl")
    rows = W.centre(rows)
    fr = C.ball_frames("ipl")
    for role in ("bat", "bowl"):
        tab, sig = C.season_components(fr[role], role, rows)
        parts = tab.B + tab.R + sum(tab[f"s_{c}"] for c in C.CLS[role])
        assert (parts - tab.ra).abs().max() < 1e-6
        assert sig > 0
        d = tab[tab.n >= 150]
        assert abs(d.B.sum() / d.n.sum()) < 0.02  # a phase mix is worth about nothing per ball
        # deviations sum to ~0 per league-season (counted classes partition the balls)
        dd = tab.groupby("sy")[[f"D_{c}" for c in C.CLS[role] if c != "ext"]].sum().sum(1)
        assert dd.abs().max() < 5
