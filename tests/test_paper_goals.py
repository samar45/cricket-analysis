"""Goal tests for the paper-trading engine (fake money). Frozen before the code was written."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cricket_analytics.ml import paper
from cricket_analytics.ml.paper import Ledger, Opportunity, ev, make_bets, replay, settle, stake_for


def opp(match="m1", cp=36, side="A", p=0.6, price=2.0, date="2024-01-01"):
    return Opportunity(match, cp, side, p, price, ev(p, price), pd.Timestamp(date))


def test_ev_hand_computed():
    # p=0.6, price 2.0: 0.6*1*0.95 - 0.4 = 0.17
    assert ev(0.6, 2.0) == pytest.approx(0.17)
    # p=0.5, price 3.0: 0.5*2*0.95 - 0.5 = 0.45
    assert ev(0.5, 3.0) == pytest.approx(0.45)
    # p=0.4, price 2.0: 0.4*0.95 - 0.6 = -0.22
    assert ev(0.4, 2.0) == pytest.approx(-0.22)


def test_no_bet_below_threshold(tmp_path):
    led = Ledger(path=tmp_path / "l.jsonl")
    # p=0.52, price 2.0: EV = 0.52*0.95 - 0.48 = 0.014 < 0.03
    placed, why = make_bets([opp(p=0.52)], 2, led)
    assert placed == [] and led.bankroll == 5000 and why


def test_stake_cap_and_nonnegative():
    assert stake_for(0.99, 10.0, 5000) == pytest.approx(250.0)  # capped at 5%
    assert stake_for(0.4, 2.0, 5000) == 0.0  # negative edge never negative stake
    rng = np.random.default_rng(0)
    for _ in range(200):
        p, pr, b = rng.uniform(0, 1), rng.uniform(1.01, 20), rng.uniform(10, 9000)
        s = stake_for(p, pr, b)
        assert 0 <= s <= 0.05 * b + 1e-9


def test_stake_is_quarter_kelly_below_cap():
    # p=0.55, price 2.0: b=0.95, EV=0.55*0.95-0.45=0.0725, kelly=EV/b, quarter, of 5000
    assert stake_for(0.55, 2.0, 5000) == pytest.approx(0.0725 / 0.95 / 4 * 5000)


def test_bankroll_win_and_loss(tmp_path):
    led = Ledger(path=tmp_path / "l.jsonl")
    placed, _ = make_bets([opp(p=0.6, price=2.0)], 1, led)
    b = placed[0]
    s = b.stake
    assert s > 0 and led.bankroll == pytest.approx(5000 - s)
    settle(b, True, led)  # win: stake back + 0.95 * stake * (2-1)
    assert led.bankroll == pytest.approx(5000 + 0.95 * s)
    led2 = Ledger(path=tmp_path / "l2.jsonl")
    b2 = make_bets([opp(p=0.6, price=2.0)], 1, led2)[0][0]
    settle(b2, False, led2)
    assert led2.bankroll == pytest.approx(5000 - b2.stake)


def test_make_bets_top_n_and_one_per_match(tmp_path):
    led = Ledger(path=tmp_path / "l.jsonl")
    opps = [opp("m1", p=0.6), opp("m2", p=0.7), opp("m3", p=0.65), opp("m2", cp=60, p=0.9)]
    placed, why = make_bets(opps, 2, led)
    assert len(placed) == 2
    assert {b.match for b in placed} == {"m2", "m3"}  # highest EV per match, top 2
    assert placed[0].ev >= placed[1].ev
    assert len({b.match for b in placed}) == len(placed)
    assert "2" in why


def test_fewer_than_n_explains(tmp_path):
    led = Ledger(path=tmp_path / "l.jsonl")
    placed, why = make_bets([opp("m1", p=0.7), opp("m2", p=0.4)], 2, led)
    assert len(placed) == 1 and "1 of 2" in why and "EV" in why
    placed, why = make_bets([opp("m9", p=0.3)], 2, Ledger(path=tmp_path / "l3.jsonl"))
    assert placed == [] and "0 of 2" in why


def test_no_second_bet_on_same_match_across_calls(tmp_path):
    led = Ledger(path=tmp_path / "l.jsonl")
    make_bets([opp("m1", p=0.7)], 1, led)
    placed, _ = make_bets([opp("m1", cp=60, p=0.8)], 1, led)
    assert placed == []


def test_decisions_are_logged(tmp_path):
    f = tmp_path / "l.jsonl"
    make_bets([opp("m1", p=0.7), opp("m2", p=0.4)], 2, Ledger(path=f))
    text = f.read_text().splitlines()
    assert len(text) >= 2 and all('"ev"' in t and "reason" in t for t in text)


def _rows(n_days=6, flip_from=None):
    out = []
    for d in range(n_days):
        for k in range(2):
            for cp in (36, 60, 90):
                out.append(dict(match_id=f"{d}-{k}", date=pd.Timestamp("2024-01-01") + pd.Timedelta(days=d), balls_bowled=cp,
                                chaser="A", opponent="B", p_model=0.62 if cp == 60 else 0.5, price_chaser=2.0, price_opp=2.0,
                                y=float((d + k) % 2 == 0)))
    df = pd.DataFrame(out)
    if flip_from is not None:
        m = df.date >= pd.Timestamp("2024-01-01") + pd.Timedelta(days=flip_from)
        df.loc[m, "y"] = 1 - df.loc[m, "y"]
    return df


def test_replay_date_order_and_first_qualifying_checkpoint():
    df = _rows()
    a = replay(df.sample(frac=1, random_state=1), p_col="p_model")
    b = replay(df, p_col="p_model")
    assert [x.match for x in a["bets"]] == [x.match for x in b["bets"]]
    dates = [x.date for x in b["bets"]]
    assert dates == sorted(dates)
    assert all(x.checkpoint == 60 for x in b["bets"])  # first qualifying checkpoint
    assert len({x.match for x in b["bets"]}) == len(b["bets"]) == 12


def test_replay_no_lookahead():
    base = replay(_rows(), p_col="p_model")["bets"]
    for D in (2, 4):
        alt = replay(_rows(flip_from=D), p_col="p_model")["bets"]
        cut = pd.Timestamp("2024-01-01") + pd.Timedelta(days=D)
        same = lambda bets: [(x.match, x.checkpoint, x.side, round(x.stake, 9)) for x in bets if x.date <= cut]
        assert same(base) == same(alt)  # results from day D onward cannot change bets up to day D


def test_replay_summary_keys():
    s = replay(_rows(), p_col="p_model")
    for k in ("final_bankroll", "n_bets", "hit_rate", "roi", "max_drawdown", "roi_ci"):
        assert k in s


def test_no_network_or_betting_imports():
    src = Path(paper.__file__).read_text(encoding="utf-8")
    bad = r"^\s*(import|from)\s+(requests|urllib|http|socket|httpx|aiohttp|betfairlightweight|betfair|smtplib|websocket|ftplib)\b"
    assert not re.search(bad, src, re.M)
    assert not re.search(r"https?://|api[_-]?key|place_orders", src, re.I)
