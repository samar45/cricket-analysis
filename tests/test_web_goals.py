"""Goal tests for the FastAPI backend (docs/API_web.md). Frozen: do not edit to make code pass."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cricket_analytics.web.app import app

client = TestClient(app)
WEB = Path(__file__).resolve().parent.parent / "src" / "cricket_analytics" / "web"


@pytest.fixture(scope="module")
def ipl():
    c = client.get("/api/choices", params={"competition": "ipl"}).json()
    return {"competition": "ipl", "venue": c["venues"][0], "batting_team": c["teams"][0], "bowling_team": c["teams"][1]}


def _predict(ipl, **kw):
    r = client.post("/api/predict", json={**ipl, "n_sims": 200, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _check(j):
    s, w = j["score"], j["win"]
    assert s["q10"] <= s["q50"] <= s["q90"]
    assert abs(w["bat"] + w["bowl"] - 1) < 1e-6
    assert isinstance(j["caveats"], list) and j["caveats"]


def test_meta():
    j = client.get("/api/meta").json()
    assert j["data_to"] and j["model"]["score"] and j["model"]["chase"]


def test_health():
    assert client.get("/api/health").status_code == 200


def test_predict_first_innings(ipl):
    _check(_predict(ipl, innings=1, runs=60, wickets=2, overs=7.0))


def test_predict_chase(ipl):
    _check(_predict(ipl, innings=2, runs=70, wickets=3, overs=9.0, target=180))


def test_over_under():
    q = {"q10": 150.0, "q50": 170.0, "q90": 190.0}
    assert abs(client.post("/api/over_under", json={**q, "line": 170.0}).json()["p_over"] - 0.5) < 1e-6
    lo = client.post("/api/over_under", json={**q, "line": 165.0}).json()["p_over"]
    hi = client.post("/api/over_under", json={**q, "line": 180.0}).json()["p_over"]
    assert hi < lo


def test_make_bets():
    j = client.post("/api/paper/make_bets", json={"n": 2}).json()
    assert len(j["placed"]) <= 2
    assert all(b["ev"] >= 0.03 for b in j["placed"])
    assert isinstance(j["explanation"], str) and "paper" in j["note"] and "fake" in j["note"]


def test_bad_request(ipl):
    r = client.post("/api/predict", json={**ipl, "innings": 3, "runs": 10, "wickets": 1, "overs": 2.0})
    assert 400 <= r.status_code < 500 and "error" in r.json()


def test_no_network_or_betting_imports():
    bad = re.compile(r"^\s*(import|from)\s+(requests|betfair|betfairlightweight|aiohttp)\b", re.M)
    files = list(WEB.glob("*.py"))
    assert files
    assert not [f.name for f in files if bad.search(f.read_text(encoding="utf-8"))]
