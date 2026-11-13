"""Fresh set #3 lock in the web API: locked matches are never listed and never get a model curve. Frozen."""
from fastapi.testclient import TestClient

from cricket_analytics.ml import evaluate as ev
from cricket_analytics.ml import predict as P
from cricket_analytics.web.app import app

client = TestClient(app)


def _locked():
    inn = P._inn()
    return inn[ev.fresh3_mask(inn)]


def test_locked_match_curve_refused():
    locked = _locked()
    if locked.empty:
        return
    r = client.get(f"/api/match_curve/{locked.match_id.iloc[0]}")
    assert r.status_code == 403 and r.json()["error"].startswith("locked: fresh set #3")


def test_locked_matches_not_listed():
    locked = _locked()
    for comp in locked.competition.unique():
        listed = {m["match_id"] for m in client.get("/api/matches", params={"competition": comp}).json()}
        assert not listed & set(locked[locked.competition == comp].match_id.astype(str))
