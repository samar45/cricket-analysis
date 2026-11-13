"""Goal tests for the model-vs-market benchmark (pre-registered in docs/ML_PREDICTION.md section 9).
Written and frozen BEFORE src/cricket_analytics/ml/market.py exists. Do not edit to make code pass.

Names the code must provide (ml/market.py):
  market_probs(df)            raw Betfair rows (one row per runner per event) -> long frame EVENT_ID, RUNNER_NAME, snapshot, p
  load_odds()                 all BBL10..BBL15 CSVs, concatenated (raw columns + SEASON)
  join_events(odds, db=None)  one row per event: EVENT_ID, SEASON, EVENT_DATE, team_a, team_b, bf_winner, match_id, cs_team1, cs_team2,
                              cs_date, cs_winner (match_id is NaN when unjoined). db = DataFrame of men's BBL matches (match_id, date,
                              team1, team2, winner) or None for the project database.
  cricsheet_bbl()             that DataFrame from the project database
  load_predictions()          out-of-sample model predictions: match_id, date, season, season_start, train_cutoff, model, balls_bowled, p
"""

import pandas as pd
import pytest

from cricket_analytics.ml import market as M

LOCK_DATE = pd.Timestamp("2026-10-15")
needs_odds = pytest.mark.skipif(not list(M.ODDS_DIR.glob("BBL1*_Match_Odds.csv")), reason="odds files not present")


def _runner(eid, name, back, lay):
    return {"EVENT_ID": eid, "RUNNER_NAME": name, "BEST_BACK_FIRST_BALL": back, "BEST_LAY_FIRST_BALL": lay}


def test_market_probs_synthetic_sum_to_one():
    df = pd.DataFrame([_runner(1, "A", 2.0, 2.02), _runner(1, "B", 1.9, 1.92), _runner(2, "A", 1.5, None), _runner(2, "B", 3.0, 3.1)])
    p = M.market_probs(df)
    assert set(p.snapshot) == {"FIRST_BALL"}
    assert ((p.p > 0) & (p.p < 1)).all()
    assert (p.groupby(["EVENT_ID", "snapshot"]).p.sum().sub(1).abs() < 1e-9).all()
    # missing lay: falls back to 1/back (event 2, runner A = 1/1.5 before normalising)
    a = 1 / 1.5
    b = (1 / 3.0 + 1 / 3.1) / 2
    got = p[(p.EVENT_ID == 2) & (p.RUNNER_NAME == "A")].p.iloc[0]
    assert abs(got - a / (a + b)) < 1e-9


def test_market_probs_drops_event_with_missing_runner_snapshot():
    df = pd.DataFrame([_runner(1, "A", 2.0, 2.0), _runner(1, "B", None, None)])
    assert M.market_probs(df).empty


@needs_odds
def test_market_probs_real_in_unit_interval_and_sum_to_one():
    p = M.market_probs(M.load_odds())
    assert len(p) > 0
    assert ((p.p > 0) & (p.p < 1)).all()
    g = p.groupby(["EVENT_ID", "snapshot"]).p
    assert (g.size() == 2).all()
    assert (g.sum().sub(1).abs() < 1e-9).all()


def _db():
    return pd.DataFrame({
        "match_id": [10, 11, 12],
        "date": pd.to_datetime(["2021-01-05", "2021-01-06", "2021-01-20"]),
        "team1": ["Perth Scorchers", "Perth Scorchers", "Sydney Sixers"],
        "team2": ["Sydney Sixers", "Sydney Sixers", "Brisbane Heat"],
        "winner": ["Sydney Sixers", None, "Brisbane Heat"],
    })


def _odds(eid, date, a, b, winner):
    return pd.DataFrame({"EVENT_ID": [eid, eid], "SEASON": ["BBL10"] * 2, "EVENT_DATE": [pd.Timestamp(date)] * 2, "RUNNER_NAME": [a, b],
                         "IS_WINNER": [int(a == winner), int(b == winner)], "HOME_TEAM": [a] * 2, "AWAY_TEAM": [b] * 2})


def test_join_synthetic_date_window_and_team_pair():
    o = pd.concat([_odds(1, "2021-01-05", "Sydney Sixers", "Perth Scorchers", "Sydney Sixers"),   # exact date, runner order swapped
                   _odds(2, "2021-01-19", "Brisbane Heat", "Sydney Sixers", "Brisbane Heat"),    # one day off
                   _odds(3, "2021-03-01", "Brisbane Heat", "Sydney Sixers", "Brisbane Heat")])   # no such match
    j = M.join_events(o, _db()).set_index("EVENT_ID")
    assert j.loc[1, "match_id"] == 10 and j.loc[2, "match_id"] == 12 and pd.isna(j.loc[3, "match_id"])
    assert j.index.is_unique


@needs_odds
def test_join_real_unique_same_teams_and_rate():
    o = M.load_odds()
    j = M.join_events(o, M.cricsheet_bbl())
    assert j.EVENT_ID.is_unique and j.EVENT_ID.nunique() == o.EVENT_ID.nunique()
    got = j[j.match_id.notna()]
    assert got.match_id.is_unique, "two odds events mapped to one Cricsheet match"
    same = got.apply(lambda r: {r.team_a, r.team_b} == {r.cs_team1, r.cs_team2}, axis=1)
    assert same.all(), got[~same][["EVENT_ID", "team_a", "team_b", "cs_team1", "cs_team2"]].to_string()
    miss = j[j.match_id.isna()]
    rate = len(got) / len(j)
    assert rate >= 0.95, f"join rate {rate:.3f}; unjoined events:\n{miss[['EVENT_ID', 'SEASON', 'EVENT_DATE', 'team_a', 'team_b']].to_string()}"


@needs_odds
def test_betfair_winner_agrees_with_cricsheet():
    j = M.join_events(M.load_odds(), M.cricsheet_bbl())
    d = j[j.match_id.notna() & j.cs_winner.notna()]
    assert len(d) > 100
    agree = (d.bf_winner == d.cs_winner).mean()
    assert agree >= 0.98, f"agreement {agree:.3f}; disagreements:\n{d[d.bf_winner != d.cs_winner][['EVENT_ID', 'EVENT_DATE', 'bf_winner', 'cs_winner']].to_string()}"


def _preds():
    try:
        return M.load_predictions()
    except FileNotFoundError:
        pytest.skip("predictions not built yet")


def test_predictions_use_only_matches_before_season_start():
    p = _preds()
    assert len(p) > 0
    assert (p.train_cutoff < p.season_start).all(), p[p.train_cutoff >= p.season_start].groupby(["season", "model"]).size()
    assert (p.date >= p.season_start).all()
    assert ((p.p > 0) & (p.p < 1)).all()


@needs_odds
def test_no_rows_on_or_after_lock_date():
    o = M.load_odds()
    assert (pd.to_datetime(o.EVENT_DATE, utc=True).dt.tz_localize(None) < LOCK_DATE).all()
    p = _preds()
    assert (pd.to_datetime(p.date) < LOCK_DATE).all()
    assert (pd.to_datetime(p.train_cutoff) < LOCK_DATE).all()
