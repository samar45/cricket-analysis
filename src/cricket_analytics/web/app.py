"""Thin HTTP layer over the existing predictor / paper-trading code. No model logic lives here.

Run: python -m uvicorn cricket_analytics.web.app:app --port 8600
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import api, competitions
from ..ml import evaluate as ev
from ..ml import paper
from ..ml import predict as P

ROOT = Path(__file__).resolve().parents[3]
DIST = ROOT / "frontend" / "app" / "dist"

# Same cautions the Streamlit "Match predictor" page and docs/ML_PREDICTION.md give.
CAVEATS = [
    "Model chances, not betting advice.",
    "The ball simulator runs high in 2026: IPL 2026 chase calibration is off (chasers won 64%, the model said 57%).",
    "Only the 10-90% score range is checked against real matches (about 80% of totals fall inside it); chances between those points are interpolated.",
    "Not yet tested against bookmaker lines; in the Betfair benchmark the market beat the model.",
    "Known weak spots: the model under-reacts to collapses, over-rates chasers of 220+, and over-predicts Chepauk first innings.",
]

app = FastAPI(title="Cricket Terminal API")


def _j(o):
    """Make numpy / pandas / NaN values JSON safe. Numbers are not rounded."""
    if isinstance(o, dict):
        return {str(k): _j(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray, pd.Series)):
        return [_j(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(o) or math.isinf(o) else float(o)
    if o is pd.NaT:
        return None
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return None if pd.isna(o) else str(pd.Timestamp(o).date())
    return o


@app.exception_handler(RequestValidationError)
async def _bad_body(_: Request, e: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'][1:])}: {err['msg']}" for err in e.errors())
    return JSONResponse({"error": msg}, status_code=422)


@app.exception_handler(ValueError)
async def _bad_value(_: Request, e: ValueError):
    return JSONResponse({"error": str(e)}, status_code=400)


@app.exception_handler(FileNotFoundError)
async def _missing(_: Request, e: FileNotFoundError):
    return JSONResponse({"error": f"not available yet: {e.filename or e}"}, status_code=503)


@lru_cache(1)
def _trained_to() -> str | None:
    try:
        return json.loads((P.MODEL_DIR / "production_meta.json").read_text())["cutoff"]
    except (OSError, KeyError, ValueError):
        return None


@app.get("/api/meta")
def meta():
    info = api.data_info()
    return {"data_to": max(c["latest"] for c in info["competitions"]), "model": P.PRODUCTION, "trained_to": _trained_to(),
            "competitions": [{"key": k, "label": competitions.COMPETITIONS[k].label if k in competitions.COMPETITIONS else k}
                             for k in P.competitions()]}


@app.get("/api/choices")
def choices(competition: str = "ipl"):
    if competition not in P.competitions():
        raise ValueError(f"unknown competition {competition!r}")
    return {"venues": P.venues(competition), "teams": P.teams(competition), "players": api.choices("player", competition)}


class PredictIn(BaseModel):
    competition: str
    venue: str
    batting_team: str
    bowling_team: str
    innings: Literal[1, 2]
    runs: int
    wickets: int
    overs: float
    target: int | None = None
    striker: str | None = None
    non_striker: str | None = None
    bowler: str | None = None
    n_sims: int = 1000


@app.post("/api/predict")
def predict(b: PredictIn):
    if not 100 <= b.n_sims <= 5000:
        raise ValueError("n_sims must be between 100 and 5000")
    r = P.predict_state(**b.model_dump())
    caveats = list(CAVEATS)
    if P.is_in_sample(r["date"], r["competition"]):
        caveats.append(f"The models were trained on matches up to {_trained_to()}; this competition may be in-sample.")
    return _j({**r, "caveats": caveats})


class OverUnderIn(BaseModel):
    q10: float
    q50: float
    q90: float
    line: float
    sims: list[float] | None = None


@app.post("/api/over_under")
def over_under(b: OverUnderIn):
    if not b.q10 < b.q50 < b.q90:
        raise ValueError("need q10 < q50 < q90")
    p = P.p_over(b.q10, b.q50, b.q90, b.line)
    out = {"p_over": p, "p_under": 1 - p}
    if b.sims:
        out["sim_over"] = P.sim_share_over(b.sims, b.line)
    return out


@app.get("/api/matches")
def matches(competition: str = "ipl", season: int | None = None):
    if competition not in P.competitions():
        raise ValueError(f"unknown competition {competition!r}")
    m = P.matches(competition, season)
    m = m[~ev.fresh3_mask(m.assign(gender="male", competition=competition, batting_team=m.team1, bowling_team=m.team2))]  # fresh set #3 lock
    return _j(m[["match_id", "date", "team1", "team2", "winner", "venue"]].to_dict("records"))


@app.get("/api/match_curve/{match_id}")
def match_curve(match_id: str):
    inn = P._inn()
    rows = inn[inn.match_id == str(match_id)]
    if not rows.empty and ev.fresh3_mask(rows).any():
        return JSONResponse({"error": "locked: fresh set #3 matches get no model output"}, status_code=403)
    c, m = P.predict_match_curve(match_id)
    first = c.innings == 1
    pts = pd.DataFrame({
        **{k: c[v].astype(int) for k, v in {"innings": "innings", "ball": "balls", "over": "over", "runs": "runs", "wickets": "wickets"}.items()},
        "p_bat_first_win": (1 - c.win_ens).where(~first),
        "q10": c.ens_q10.where(first, c.sim_q10), "q50": c.ens_q50.where(first, c.sim_q50), "q90": c.ens_q90.where(first, c.sim_q90)})
    return _j({"match": {k: v for k, v in m.items() if k != "in_sample"}, "in_sample": m["in_sample"], "points": pts.to_dict("records")})


class PrematchIn(BaseModel):
    competition: str
    venue: str
    team_a: str
    team_b: str
    date: str | None = None


@app.post("/api/prematch")
def prematch_(b: PrematchIn):
    from ..ml import prematch

    return _j({**prematch.predict(**b.model_dump()), "caveats": CAVEATS[:1] + [
        "Pre-match T20 results are close to a coin flip; expect probabilities within about 0.35 to 0.65."]})


# ---------- paper trading: fake money, no bookmaker or exchange is ever called ----------
@lru_cache(1)
def _rows() -> pd.DataFrame:
    return paper.load_replay_rows()


@lru_cache(1)
def _replay() -> dict:
    return paper.replay(_rows())


def _bet(b: paper.Bet) -> dict:
    return {"date": b.date, "match": b.match, "checkpoint": b.checkpoint, "side": b.side, "p_model": b.p_model, "price": b.price,
            "ev": b.ev, "stake": b.stake, "status": b.status, "pnl": b.pnl}


@app.get("/api/paper/summary")
def paper_summary():
    s = _replay()
    dates = [None] + sorted(_rows().date.unique())
    lo, hi = s["roi_ci"]
    return _j({"start": s["ledger"].start, "final": s["final_bankroll"], "roi": s["roi"], "roi_lo": lo, "roi_hi": hi,
               "hit_rate": s["hit_rate"], "max_drawdown": s["max_drawdown"], "n_bets": s["n_bets"],
               "path": [{"i": i, "date": dates[i] if i < len(dates) else None, "bankroll": v} for i, v in enumerate(s["curve"])],
               "note": paper.BANNER})


@app.get("/api/paper/ledger")
def paper_ledger(limit: int = 50):
    return _j([_bet(b) for b in _replay()["bets"][-max(limit, 0):][::-1]])


class MakeBetsIn(BaseModel):
    n: int
    date: str | None = None


@app.post("/api/paper/make_bets")
def paper_make_bets(b: MakeBetsIn):
    if b.n < 1:
        raise ValueError("n must be at least 1")
    opps = paper.opportunities(_rows(), "p_ens-G1")
    if b.date:
        day = pd.Timestamp(b.date)
    else:
        good = pd.Series([o.date for o in opps if o.ev >= paper.MIN_EV])
        if good.empty:
            return {"placed": [], "explanation": "no opportunity has EV above the threshold", "note": paper.BANNER}
        day = good.value_counts().idxmax()  # busiest day with qualifying opportunities
    placed, why = paper.make_bets([o for o in opps if o.date == day], b.n, paper.Ledger(path=None))
    return _j({"placed": [_bet(x) for x in placed], "explanation": why, "day": day, "note": paper.BANNER})


@app.get("/api/health")
def health():
    runs = sorted((ROOT / "data" / "runs").glob("*.json"), reverse=True)
    last = json.loads(runs[0].read_text(encoding="utf-8")) if runs else None
    return _j({"data": api.data_info(), "last_run": last, "n_runs": len(runs)})


if DIST.is_dir():  # last, so it never shadows /api
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
