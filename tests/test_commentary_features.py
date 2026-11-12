import numpy as np
import pandas as pd

from cricket_analytics.models import commentary_features as C


def _frame(rows):
    base = dict(match_id="1", innings=1, wides=0, noballs=0, runs_batter=0, speed=np.nan, length=None, line=None, delivery=None,
                contact=None, lapse=None, cb_event="NONE", batter="B", bowler="P", player_out=None, wicket_type=None, year=2024,
                phase="death", bowl_kind="pace", bat_ra=0.0, bat_wpa=0.0, bat_who="B", bowl_ra=0.0, bowl_wpa=0.0)
    d = pd.DataFrame([{**base, **r} for r in rows])
    d["ball_seq"] = range(1, len(d) + 1)
    return d


def test_fill_rules():
    rows = [dict(speed=140.0) for _ in range(12)] + [dict(), dict(speed=943.0), dict(wides=1)]   # pace bowler P: 12 quoted
    rows += [dict(bowler="S", bowl_kind="spin", speed=135.0) for _ in range(12)] + [dict(bowler="S", bowl_kind="spin")]  # spinner median 135: unfit
    rows += [dict(bowler="Q", speed=140.0) for _ in range(5)] + [dict(bowler="Q")]  # < 10 quoted: stays NA
    rows += [dict(bowler="Z", bowl_kind=None, speed=140.0) for _ in range(12)] + [dict(bowler="Z", bowl_kind=None)]  # unknown kind: no fill
    d = C.fill(_frame(rows))
    p = d[d.bowler == "P"]
    assert (p.speed_src.iloc[:12] == "text").all()
    assert (p.speed_src.iloc[12:] == "filled_bowler").all() and (p.speed_f.iloc[12:] == 140.0).all()  # 943 ignored, filled from the median
    assert p.line_src.iloc[14] == "filled_rule" and p.line_f.iloc[14] == "wide"          # wide with no line text
    assert p.line_src.iloc[:14].isna().all() and p.length_src.isna().all()                # nothing else invented
    assert d[d.bowler == "S"].speed_src.iloc[-1] is None or pd.isna(d[d.bowler == "S"].speed_src.iloc[-1])
    assert pd.isna(d[d.bowler == "Q"].speed_f.iloc[-1]) and pd.isna(d[d.bowler == "Z"].speed_f.iloc[-1])


def test_aggregate_tiny():
    rows = [dict(contact="edge", runs_batter=4), dict(contact="miss"), dict(contact="middle", runs_batter=6), dict(runs_batter=4),
            dict(length="yorker"), dict(length="short"), dict(length="full toss", cb_event="DROPPED", runs_batter=1), dict(runs_batter=4), dict(wides=1)]
    d = C.ball_features(C.fill(_frame(rows)))
    bat = C.player_season(d, "bat", min_balls=1).iloc[0]
    assert bat.n == 8                                    # the wide is not faced
    assert np.isclose(bat.false_pct, 2 / 8) and np.isclose(bat.edge_pct, 1 / 8)
    assert np.isclose(bat.edge_bnd_pct, 1 / 8) and np.isclose(bat.clean_bnd_pct, 3 / 8)  # 6 off 'middle', two plain 4s
    assert bat.drop_n == 1 and bat.runs_after_drop == 4  # one 4 after the drop
    bowl = C.player_season(d, "bowl", min_balls=1).iloc[0]
    assert np.isclose(bowl.yorker_pct, 1 / 3) and np.isclose(bowl.short_pct, 1 / 3)  # 3 known lengths among the 8 legal balls


def test_bowl_plus_feats_no_future_leak(monkeypatch):
    from cricket_analytics.models import commentary_features as cf

    rows = {(b, y): dict(death_yorker_n=n, death_yorker_d=40, slower_n=3, slower_d=100, false_n=5, false_d=100)
            for b, ns in {"A": (4, 30, 10), "B": (8, 2, 12), "C": (6, 10, 11)}.items() for y, n in zip((2017, 2018, 2019), ns)}
    c = pd.DataFrame(rows).T
    c.index.names = ["bowler", "year"]
    monkeypatch.setitem(cf._CNT, "c", c)
    early = cf.bowl_plus_feats(2018, ("death_yorker",))
    c2 = c.copy()
    c2.loc[(slice(None), 2019), "death_yorker_n"] = 0  # change the future
    monkeypatch.setitem(cf._CNT, "c", c2)
    assert early.equals(cf.bowl_plus_feats(2018, ("death_yorker",)))
    assert early.cm_death_yorker["A"] > early.cm_death_yorker["B"] and abs(early.cm_death_yorker.mean()) < 0.05
