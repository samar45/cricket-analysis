# Web API contract (FastAPI backend <-> React "Cricket Terminal" frontend)

Version 1, 2026-11-14. The backend lives in `src/cricket_analytics/web/` and runs at `uvicorn cricket_analytics.web.app:app --port 8600`. The frontend lives in `frontend/app/` (Vite dev server on 5173, which proxies `/api` to 8600). The production build is served by FastAPI at `/`.

All responses are JSON. Errors are `{"error": "<plain message>"}` with an HTTP 4xx status. The DB is opened read-only. Paper trading only: no endpoint may place a real bet or call any bookmaker or exchange.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/api/meta` | - | `{data_to, model:{score,chase}, trained_to, competitions:[{key,label}]}` |
| GET | `/api/choices?competition=ipl` | - | `{venues:[str], teams:[str], players:[str]}` (recent first) |
| POST | `/api/predict` | `{competition, venue, batting_team, bowling_team, innings:1\|2, runs, wickets, overs, target?, striker?, non_striker?, bowler?, n_sims?=1000}` | `{score:{q10,q50,q90}, win:{bat,bowl}, g1:{q10,q50,q90,win_bat}, sim:{q10,q50,q90,win_bat}, sims:[float], level, caveats:[str]}` |
| POST | `/api/over_under` | `{q10,q50,q90,line, sims?:[float]}` | `{p_over, p_under, sim_over?}` (uses `predict.p_over` / `sim_share_over`) |
| GET | `/api/matches?competition=ipl&season=2026` | - | `[{match_id,date,team1,team2,winner,venue}]` |
| GET | `/api/match_curve/{match_id}` | - | `{match:{...}, in_sample:bool, points:[{innings,ball,over,runs,wickets,p_bat_first_win,q10?,q50?,q90?}]}` |
| POST | `/api/prematch` | `{competition, venue, team_a, team_b, date?}` | output of `prematch.predict` + `caveats` |
| GET | `/api/paper/summary` | - | replay summary: `{start,final,roi,roi_lo,roi_hi,hit_rate,max_drawdown,n_bets,path:[{i,date,bankroll}]}` |
| GET | `/api/paper/ledger?limit=50` | - | `[{date,match,checkpoint,side,p_model,price,ev,stake,status,pnl}]` |
| POST | `/api/paper/make_bets` | `{n, date?}` (opportunities of that replay day, or the busiest day by default) | `{placed:[...], explanation, note:"paper trading, fake money"}` |
| GET | `/api/health` | - | data-health summary (the module behind the Streamlit Data health page) |

Rules:
- Numbers are not rounded on the server.
- Every model response carries the `caveats` that the Streamlit page shows (simulator runs high in 2026, only the 10-90% range is checked, the in-sample flag, the market beat the model).
