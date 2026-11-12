import pandas as pd

from cricket_analytics.models import length_matchup as L


def test_shrink():
    assert L.shrink(0, 0, 1.5, 40) == 1.5          # no data -> prior
    assert abs(L.shrink(600, 100, 1.0, 100) - 3.5) < 1e-9  # (600+100)/(200)
    assert abs(L.shrink(6000, 1000, 1.0, 1) - 6.0) < 0.01  # lots of data -> raw rate


def _train():
    rows = []
    for _ in range(200):
        rows += [dict(batter="A", bowler="X", runs=0.0, w=0.0, b="short"), dict(batter="A", bowler="Y", runs=6.0, w=0.0, b="full"),
                 dict(batter="C", bowler="X", runs=2.0, w=0.0, b="short"), dict(batter="C", bowler="Y", runs=2.0, w=0.0, b="full")]
    rows += [dict(batter=b, bowler=w, runs=0.0, w=1.0, b=k) for b in "AC" for w, k in (("X", "short"), ("Y", "full"))] * 5
    d = pd.DataFrame(rows).assign(match_id="1", year=2020, bowl_kind="pace")
    return d


def test_predict_uses_bowler_mix_and_shrinks():
    pairs = pd.DataFrame(dict(batter=["A", "A", "ZZ"], bowler=["X", "Y", "X"], bowl_kind="pace"))
    p = L.predict(_train(), pairs, kr=1, kw=1, km=1, kc=1)
    assert p.pr_len[1] > p.pr_len[0] + 2          # A hits the full-bowler hard, not the short-bowler
    assert p.pr_len[2] > p.pr_len[0]              # unseen batter -> league-like, above A vs the short-bowler
    assert p.pr_league[0] == _train().runs.mean()
    assert p.pw_len.between(0.001, 0.5).all()
