"""Writes data.js (window.MOCK) for the static UI mock-up from the real predictor and paper-trading code. Read-only."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from cricket_analytics.ml import paper as pp, predict as P
from cricket_analytics.db import query

OUT = Path(__file__).with_name("data.js")
meta_f = json.loads((P.MODEL_DIR / "production_meta.json").read_text())
V = "MA Chidambaram Stadium, Chepauk"  # exact spelling in the matches table


def state(**k):
    r = P.predict_state("ipl", V, date="2026-05-31", n_sims=1000, **k)
    sims = r.pop("sims")
    h, edges = np.histogram(sims, bins=range(int(sims.min()) // 5 * 5, int(sims.max()) + 6, 5))
    r["hist"] = {"x": edges[:-1].tolist(), "n": h.tolist()}
    r["sim_p_mean"] = float(sims.mean())
    r["sims"] = [int(x) for x in sims]  # full array, for the over/under calculator
    return json.loads(json.dumps(r, default=float))


s1 = state(batting_team="Chennai Super Kings", bowling_team="Sunrisers Hyderabad", innings=1, runs=90, wickets=3, overs=10)
s2 = state(batting_team="Sunrisers Hyderabad", bowling_team="Chennai Super Kings", innings=2, runs=95, wickets=3, overs=10, target=181)

mid = "1535465"  # IPL 2026 final: GT 155 v RCB 161
curve, cm = P.predict_match_curve(mid, n_sims=200)

# paper trading: rerun the replay (no log) so every bet carries its date
rows = pp.load_replay_rows()
rep = pp.replay(rows, log_path=None)
mt = query("select match_id, date, team1, team2 from matches")
mt["match_id"] = mt.match_id.astype(str)
mt = mt.set_index("match_id")
bets = rep["bets"]
ledger = [dict(date=str(b.date.date()), match=f"{mt.loc[b.match,'team1']} v {mt.loc[b.match,'team2']}", checkpoint=b.checkpoint // 6,
               side=b.side, p=b.p_model, price=b.price, ev=b.ev, stake=b.stake, status=b.status, pnl=b.pnl) for b in bets]
# bankroll after each bet
bank, path = pp.START, []
for r in ledger:
    bank += r["pnl"]
    path.append({"date": r["date"], "bankroll": bank})
# make-2 example on the busiest qualifying day (same rule as `paper demo`)
opps = pp.opportunities(rows, "p_ens-G1")
d0 = pd.Series([o.date for o in opps if o.ev >= pp.MIN_EV]).value_counts().idxmax()
day = [o for o in opps if o.date == d0]
placed, why = pp.make_bets(day, 2, pp.Ledger(path=None))
mk = dict(day=str(d0.date()), n_opps=len(day), why=why,
          bets=[dict(match=f"{mt.loc[b.match,'team1']} v {mt.loc[b.match,'team2']}", checkpoint=b.checkpoint // 6, side=b.side, p=b.p_model,
                     price=b.price, ev=b.ev, stake=b.stake) for b in placed])
db_date = query("select max(date) d from matches").d.iloc[0]
MOCK = dict(
    status=dict(db_date=str(db_date)[:10], cutoff=meta_f.get("cutoff"), production=P.PRODUCTION),
    predictor=dict(venue=V, examples={"inn1": s1, "inn2": s2}, curve_meta=cm,
                   curve=json.loads(curve.to_json(orient="records"))),
    paper=dict(start=pp.START, summary=dict(final=rep["final_bankroll"], n_bets=rep["n_bets"], hit=rep["hit_rate"], roi=rep["roi"],
                                           roi_ci=list(rep["roi_ci"]), max_dd=rep["max_drawdown"]),
               path=path, ledger=ledger[-15:], make2=mk))
OUT.write_text("window.MOCK = " + json.dumps(MOCK, default=float) + ";\n", encoding="utf-8")
print("wrote", OUT, OUT.stat().st_size, "bytes")
