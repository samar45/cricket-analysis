import pandas as pd

from cricket_analytics.models import components as C
from cricket_analytics.models.marcel import marcel_frame


def _tab():
    cols = ["comp", "sy", "player", "n", "B", "R"] + [f"s_{c}" for c in C.CLS["bat"]]
    row = lambda comp, sy, n, s: dict(comp=comp, sy=sy, player="A", n=n, B=0.0, R=0.0, **{f"s_{c}": s for c in C.CLS["bat"]})  # noqa: E731
    bat = pd.DataFrame([row("ipl", 2024, 100, 1.0), row("bbl", 2023, 100, 1.0)], columns=cols)
    bowl = pd.DataFrame(columns=["comp", "sy", "player", "n", "B", "R"] + [f"s_{c}" for c in C.CLS["bowl"]])
    return {"bat": bat, "bowl": bowl}


def test_marcel_shrinks_and_weights_balls():
    ks = {r: {**{c: 100.0 for c in C.CLS[r]}, "R": 100.0} for r in C.CLS}
    f = marcel_frame(_tab(), ks, 2024, other_w=0.0)
    # IPL 2024 only (weight 5 of 12): rate = 5 parts x (5*1)/(5*100+100) ; balls = 5*100/12
    assert abs(f.bat_rate["A"] - 5 * 5 / 600) < 1e-9
    assert abs(f.bat["A"] - f.bat_rate["A"] * 500 / 12) < 1e-9
    # an old season outside the 3-year window is ignored
    assert marcel_frame(_tab(), ks, 2027, other_w=0.0).bat_rate.isna().all()


def test_weighted_share_regresses_to_mean():
    from cricket_analytics.models.availability import weighted_share

    sh = pd.DataFrame({2024: [1.0, 0.0], 2023: [1.0, 0.0], 2022: [1.0, 0.0]}, index=["a", "b"])
    assert list(weighted_share(sh)) == [1.0, 0.0]
    s = weighted_share(sh, k=12.0, mean=0.5)  # k = one full set of weights of mean
    assert abs(s["a"] - 0.75) < 1e-9 and abs(s["b"] - 0.25) < 1e-9


def test_strategy_pick_respects_budget_slots_and_overseas_cap():
    from cricket_analytics.models.strategy import percentile, pick

    df = pd.DataFrame({"cost": [5.0, 4.0, 3.0, 1.0], "overseas": [True, True, False, False]})
    assert pick(df, [0, 1, 2, 3], budget=9.0, n_max=3, os_max=1) == [0, 2, 3]  # 4.0 skipped: overseas cap
    assert pick(df, [0, 1, 2, 3], budget=100.0, n_max=2, os_max=2) == [0, 1]
    assert abs(percentile(2.0, [1, 2, 3]) - 100 / 3) < 1e-9
