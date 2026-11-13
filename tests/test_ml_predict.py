"""Match predictor inference (ml/predict.py). Needs the locally trained models and caches (gitignored): skipped without them."""

import pytest

from cricket_analytics.ml import predict as P
from cricket_analytics.ml.dataset import OUT_DIR

pytestmark = pytest.mark.skipif(
    not (P.V2_DIR / "final_score_q50.txt").exists() or not (OUT_DIR / "states.parquet").exists() or not (OUT_DIR / "balls.parquet").exists(),
    reason="ML models / caches not built",
)
BASE = dict(competition="ipl", venue="Wankhede Stadium", batting_team="Mumbai Indians", bowling_team="Chennai Super Kings", n_sims=300)


def ordered(d):
    return d["q10"] <= d["q50"] <= d["q90"]


def test_first_innings_outputs():
    r = P.predict_state(innings=1, runs=60, wickets=2, overs=5.0, **BASE)
    for part in (r["score"], r["g1"], r["sim"]):
        assert ordered(part)
    assert 100 < r["score"]["q50"] < 300
    assert 0 <= r["win"]["bat"] <= 1 and abs(r["win"]["bat"] + r["win"]["bowl"] - 1) < 1e-9
    assert 0 <= r["g1"]["win_bat"] <= 1 and 0 <= r["sim"]["win_bat"] <= 1
    assert len(r["sims"]) == 300


def test_chase_outputs_and_target_reached():
    r = P.predict_state(innings=2, runs=110, wickets=4, overs=10.0, target=209, **BASE)
    assert ordered(r["score"]) and 0 <= r["win"]["bat"] <= 1
    assert r["target"] == 209 and r["balls_left"] == 60
    done = P.predict_state(innings=2, runs=150, wickets=3, overs=14.0, target=140, **BASE)
    assert done["win"]["bat"] == 1.0
    near = P.predict_state(innings=2, runs=139, wickets=3, overs=15.0, target=145, **BASE)
    assert near["win"]["bat"] > 0.9  # 6 needed off 30 balls, 7 wickets in hand


def test_more_wickets_lower_score():
    lo = P.predict_state(innings=1, runs=90, wickets=6, overs=12.0, **BASE)
    hi = P.predict_state(innings=1, runs=90, wickets=1, overs=12.0, **BASE)
    assert lo["score"]["q50"] <= hi["score"]["q50"]
    assert lo["g1"]["q50"] <= hi["g1"]["q50"] and lo["sim"]["q50"] <= hi["sim"]["q50"]


def test_players_and_inputs():
    r = P.predict_state(innings=1, runs=60, wickets=2, overs=5.3, striker="V Kohli", non_striker="not a player", bowler="JJ Bumrah", **BASE)
    assert r["players_known"] == {"striker": True, "non_striker": False, "bowler": True} and r["balls"] == 33
    assert P.parse_overs(10.3) == 63 and P.parse_overs(20.0) == 120
    for bad in (dict(overs=5.7), dict(overs=21.0), dict(innings=3), dict(innings=2, target=None), dict(wickets=11)):
        with pytest.raises(ValueError):
            P.predict_state(**{**BASE, "innings": 1, "runs": 50, "wickets": 2, "overs": 5.0, **bad})


def test_match_curve_pbks_chase():
    c, meta = P.predict_match_curve(1426280, n_sims=60)
    assert meta["score2"] == 262 and meta["winner"] == "Punjab Kings"
    w = c[c.innings == 2]
    assert w.win_ens.between(0, 1).all() and w.win_ens.iloc[-1] > 0.9 and w.win_ens.iloc[0] < 0.4
    f = c[c.innings == 1]
    assert (f.ens_q10 <= f.ens_q50).all() and (f.ens_q50 <= f.ens_q90).all()
    assert abs(f.ens_q50.iloc[-1] - meta["score1"]) < 25  # last over: the projection is close to the real total


def test_lists():
    assert "ipl" in P.competitions() and "hundred" not in P.competitions()
    assert "Wankhede Stadium" in P.venues("ipl") and "Mumbai Indians" in P.teams("ipl")
    assert "V Kohli" in P.players("ipl", "Royal Challengers Bengaluru", "bat")
