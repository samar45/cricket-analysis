"""Matchup predictor (models/matchup_model.py + the `matchup_predict` module). Most tests build a tiny synthetic ball set
and need no database; the last ones use the real DB (skipped in CI)."""

import numpy as np
import pytest

from cricket_analytics import api
from cricket_analytics.models import matchup_model as M
from cricket_analytics.sql.attributes import BOWL_TYPES
from cricket_analytics.viz import matchup_predict as mviz
from cricket_analytics.viz import video
from tests.conftest import requires_real_db

real = requires_real_db
OFF = {n: [1e6, 1e6] for n, _ in M.LAYERS}


def synth(n_pair=0, pair_out=0.0, n_type=2000, seed=0):
    """Batter 0 faces bowler 1 (type 0, pace) `n_pair` times with wicket rate pair_out, and bowler 2 (type 6, spin) `n_type` times."""
    rng = np.random.default_rng(seed)
    rows = []
    for bowler, ty, kind, n, pw in ((1, 0, 0, n_pair, pair_out), (2, 6, 1, n_type, 0.05)):
        cls = np.where(rng.random(n) < pw, 6, rng.choice([0, 1, 4, 5], n, p=[0.4, 0.4, 0.15, 0.05]))
        rows.append((np.full(n, bowler), np.full(n, ty), np.full(n, kind), cls))
    # a pool of other batters / bowlers so the league layers exist
    m = 3000
    rows.append(
        (
            np.full(m, 3),
            np.full(m, 0),
            np.full(m, 0),
            rng.choice([0, 1, 4, 5, 6], m, p=[0.4, 0.4, 0.1, 0.05, 0.05]),
        )
    )
    bowler, ty, kind, cls = (np.concatenate(x) for x in zip(*rows))
    n = len(cls)
    batter = np.where(bowler == 3, 4, 0)
    codes = dict(
        yr=np.full(n, 2024),
        era=np.ones(n, np.int64),
        phase=np.ones(n, np.int64),
        state=np.zeros(n, np.int64),
        kind=kind.astype(np.int64),
        type=ty.astype(np.int64),
        hand=np.zeros(n, np.int64),
        batter=batter.astype(np.int64),
        bowler=bowler.astype(np.int64),
        cls=cls.astype(np.int64),
        runs=np.array([0, 1, 2, 3, 4, 6, 0.0])[cls],
    )
    vocab = M.Vocab(
        ["b0", "p1", "s2", "o3", "b4"],
        np.zeros(5, np.int64),
        np.array([-1, 0, 6, 0, -1]),
        np.array([-1, 0, 1, 0, -1]),
    )
    return codes, vocab


def test_probabilities_sum_to_one_and_positive():
    codes, vocab = synth(40, 0.1)
    fit = M.fit_chain(codes, {n: [15, 15] for n, _ in M.LAYERS})
    P = fit.apply(codes)
    assert np.allclose(P.sum(axis=1), 1) and (P[:, [0, 1, 4, 5, 6]] > 0).all()
    r = M.predict(fit, vocab, "b0", "p1", phase="middle")
    assert r["P"].sum() == pytest.approx(1) and (r["P"][[0, 1, 4, 5, 6]] > 0).all()


def test_zero_head_to_head_equals_type_layers():
    """A bowler with no balls against this batter: the pair layer changes nothing."""
    codes, vocab = synth(n_pair=0)
    ks = {n: [15, 15] for n, _ in M.LAYERS}
    fit = M.fit_chain(codes, ks)
    r = M.predict(fit, vocab, "b0", "p1", phase="middle")
    r2 = M.predict(fit, vocab, "b0", None, bowl_type=BOWL_TYPES[0], phase="middle")
    assert r["evidence"]["pair"] == 0
    assert np.allclose(r["P"], r2["P"])  # same batter, same type, no pair evidence


def test_huge_sample_goes_to_raw_and_k_shrinks():
    codes, _ = synth(n_pair=30000, pair_out=0.2)
    ks = {n: [1e6, 1e6] for n, _ in M.LAYERS} | {"pair": [5, 5]}
    fit = M.fit_chain(codes, ks)
    L = fit.layer("pair")
    g = np.flatnonzero((L.keys // M.RAD) == 0)  # batter 0 rows
    # pair (b0, p1): last in key order for batter 0 with bowler 1
    key = 0 * M.RAD + 1
    row = L.R[np.searchsorted(L.keys, key)]
    assert L.n[np.searchsorted(L.keys, key)] == 30000
    # after the layer the wicket rate for that pair is close to the raw 0.2
    c = dict(codes)
    P = fit.apply({k: v[codes["bowler"] == 1][:1] for k, v in c.items()})
    assert P[0, 6] == pytest.approx(0.2, abs=0.02)
    assert row[6] > 1 and len(g) >= 1
    # and with k = 1e6 the layer does nothing
    off = M.fit_chain(codes, OFF)
    assert np.allclose(off.layer("pair").R, 1, atol=1e-2)


def test_ratio_shrinkage_monotone_in_k():
    obs = np.array([[10.0, 10, 0, 0, 0, 0, 10]])
    E = np.array([[16.0, 10, 1, 1, 1, 1, 1]])
    r_small = M.ratios(obs, E, 1, 1)[0, 6]
    r_big = M.ratios(obs, E, 1000, 1000)[0, 6]
    assert r_small > r_big > 1 > 0 and M.ratios(np.zeros((1, 7)), np.zeros((1, 7)), 5, 5).min() >= 0


def test_unknown_bowler_type_skips_type_layers():
    codes, vocab = synth()
    fit = M.fit_chain(codes, {n: [15, 15] for n, _ in M.LAYERS})
    r = M.predict(fit, vocab, "b4", "o3", phase="middle")  # b4 has no hand, o3 listed pace
    r_unknown = M.predict(fit, vocab, "b0", None, phase="middle")  # no bowler, no type
    assert r_unknown["type"] == -1 and r_unknown["kind"] == -1
    assert r["P"].sum() == pytest.approx(1)


def test_confidence_labels():
    assert M.confidence({"pair": 40}, "x", True) == "strong"
    assert M.confidence({"pair": 5, "bat_type": 200}, "x", True) == "medium"
    assert M.confidence({"pair": 5, "bat_type": 20}, "x", True) == "thin"
    assert M.confidence({"bat_type": 20}, None, True) == "thin"
    assert M.confidence({"bat": 900}, None, False) == "medium"


def test_kind_question_uses_kind_balls():
    codes, vocab = synth()
    fit = M.fit_chain(codes, {n: [15, 15] for n, _ in M.LAYERS})
    r = M.predict(fit, vocab, "b0", None, bowl_type="spin", phase="middle")
    assert r["evidence"]["ask_balls"] == r["evidence"]["bat_kind"] > 0
    assert M.confidence(r["evidence"], None, True) == "strong"


def test_state_cells_cover_all_when_open():
    assert sorted(M.state_cells(None, None, None)) == list(range(M.N_STATES))
    assert M.state_cells("0-2", "first", None) == [0]
    assert M.state_cells("6+", "chase", "high") == [3 + 2 * 3 + 2]


def test_viz_module_ids_match_registry():
    from cricket_analytics import registry

    assert registry.get("matchup_predict").id == "matchup_predict"
    assert "matchup_predict" in video.module_ids() and hasattr(mviz, "figure")


# ── real DB ──────────────────────────────────────────────────────────────────────────────────────────────────


@real
def test_card_real():
    r = api.run(
        "matchup_predict", player="V Kohli", player2="JJ Bumrah", phase="middle", competition="ipl"
    )
    d = r.data.iloc[0]
    assert d.bowl_type_source == "reviewed list"
    probs = d[["p_dot", "p_1", "p_2", "p_3", "p_4", "p_6", "p_out"]].astype(float)
    assert probs.sum() == pytest.approx(1, abs=2e-3)
    assert 0 < d.p_out < 0.3 and 0 < d.exp_runs_per_6 < 15
    assert d.pair_balls > 0 and d.confidence in ("strong", "medium", "thin")
    assert mviz.figure(r).data and video.video_figure("matchup_predict", r).layout.annotations


@real
def test_grid_real():
    r = api.run("matchup_predict", player="V Kohli", view="grid", competition="ipl")
    assert len(r.data) == len(BOWL_TYPES) * 4
    assert r.data.exp_runs_per_6.between(0, 15).all()
    assert mviz.figure(r).data and video.video_figure("matchup_predict", r).layout.annotations


@real
def test_bad_input_real():
    with pytest.raises(Exception):
        api.run(
            "matchup_predict",
            player="V Kohli",
            player2="JJ Bumrah",
            bowl_type="spin",
            competition="ipl",
        )
