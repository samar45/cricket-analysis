"""Per-legal-ball state table for T20 prediction (men's + women's, super overs excluded).

A STATE row = the match after k legal balls of an innings (k = 0 .. N). `runs`/`wickets` are totals so far;
`striker`/`non_striker`/`bowler` are those of the NEXT delivery (empty on the last row). The last row of an
innings uses the full innings totals (including extras bowled after the last legal ball).
Written to data/external/ml/ (gitignored). The DB is only read.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ..db import query

OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "external" / "ml"
IMPACT_FROM = 2023  # IPL impact-player era
DLS_METHODS = ("D/L", "VJD", "Awarded", "Lost fewer wickets")

_DELIVERIES = """
WITH d AS (
  SELECT d.match_id, d.innings, d.ball_seq, d.batter, d.non_striker, d.bowler, d.runs_total,
         (d.wides = 0 AND d.noballs = 0)::INT AS legal,
         (d.player_out IS NOT NULL AND coalesce(d.wicket_type, '') NOT IN ('retired hurt', 'retired not out'))::INT AS wk
  FROM deliveries d JOIN matches m USING (match_id)
  WHERE m.gender IN ('male', 'female') AND d.innings <= 2),
c AS (
  SELECT *,
    sum(runs_total) OVER w AS runs, sum(legal) OVER w AS balls, sum(wk) OVER w AS wkts,
    lead(batter) OVER w AS n_striker, lead(non_striker) OVER w AS n_non_striker, lead(bowler) OVER w AS n_bowler,
    sum(runs_total) OVER wall AS tot_runs, sum(wk) OVER wall AS tot_wk, sum(legal) OVER wall AS tot_balls,
    row_number() OVER w AS rn
  FROM d
  WINDOW w AS (PARTITION BY match_id, innings ORDER BY ball_seq ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
         wall AS (PARTITION BY match_id, innings))
SELECT match_id, innings, 0 AS balls_bowled, 0 AS runs, 0 AS wickets,
       batter AS striker, non_striker, bowler, tot_runs, tot_wk, tot_balls
FROM c WHERE rn = 1
UNION ALL
SELECT match_id, innings, balls, CASE WHEN balls = tot_balls THEN tot_runs ELSE runs END,
       CASE WHEN balls = tot_balls THEN tot_wk ELSE wkts END,
       n_striker, n_non_striker, n_bowler, tot_runs, tot_wk, tot_balls
FROM c WHERE legal = 1
"""

_MATCHES = """
SELECT match_id, date, competition, gender, venue, team1, team2, winner, result, outcome_method,
       balls_per_over, year(min(date) OVER (PARTITION BY competition, gender, season)) AS season_year
FROM matches WHERE gender IN ('male', 'female')
"""


def build(write: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (states, innings). `innings` has one row per (match, innings)."""
    st = query(_DELIVERIES)
    m = query(_MATCHES)
    team = query(
        "SELECT match_id, innings, any_value(batting_team) AS batting_team, any_value(bowling_team) AS bowling_team "
        "FROM deliveries WHERE innings <= 2 GROUP BY 1, 2"
    )
    inn = (
        st.groupby(["match_id", "innings"], as_index=False)
        .agg(final_total=("tot_runs", "first"), final_wickets=("tot_wk", "first"), legal_balls=("tot_balls", "first"))
        .merge(team, on=["match_id", "innings"])
        .merge(m, on="match_id")
    )
    first = inn[inn.innings == 1].set_index("match_id").final_total
    inn["first_total"] = inn.match_id.map(first)
    is2 = inn.innings == 2
    inn["target"] = np.where(is2, inn.first_total + 1, np.nan)
    inn["max_balls"] = inn.balls_per_over * 20
    inn["impact_era"] = (inn.competition == "ipl") & (inn.season_year >= IMPACT_FROM)
    # chase result: scoreboard (tie -> NaN); DLS-type matches use the recorded winner; no result -> NaN
    sb = np.where(inn.final_total >= inn.target, 1.0, np.where(inn.final_total == inn.target - 1, np.nan, 0.0))
    byw = np.where(inn.winner.isna(), np.nan, (inn.winner == inn.batting_team).astype(float))
    cw = np.where(inn.outcome_method.isin(DLS_METHODS), byw, sb)
    cw = np.where(inn.result.isin(["no result", "tie"]) | inn.result.isna(), np.nan, cw)
    inn["chase_won"] = np.where(is2, cw, np.nan)
    chased = is2 & (inn.final_total >= inn.target)
    cut_short = (inn.legal_balls < inn.max_balls) & (inn.final_wickets < 10) & ~chased
    inn["reduced"] = (
        inn.outcome_method.isin(DLS_METHODS) | (inn.balls_per_over != 6) | (inn.result == "no result") | cut_short
    )
    inn["reduced"] |= inn.match_id.map(inn.groupby("match_id").reduced.max())  # a reduced match is reduced in both innings
    inn = inn.drop(columns=["team1", "team2"])

    keep = ["match_id", "innings", "date", "season_year", "competition", "gender", "venue", "batting_team",
            "bowling_team", "target", "max_balls", "final_total", "chase_won", "impact_era", "reduced"]
    s = st.drop(columns=["tot_runs", "tot_wk", "tot_balls"]).rename(columns={"wickets": "wickets"}).merge(inn[keep], on=["match_id", "innings"])
    s["balls_left"] = s.max_balls - s.balls_bowled
    s["runs_needed"] = s.target - s.runs
    s["season_year"] = s.season_year.astype(int)
    s["innings"] = s.innings.astype(int)
    s = s.sort_values(["date", "match_id", "innings", "balls_bowled"], kind="stable").reset_index(drop=True)
    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        s.to_parquet(OUT_DIR / "states.parquet", index=False)
        inn.to_parquet(OUT_DIR / "states_innings.parquet", index=False)
    return s, inn


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the files written by build()."""
    return pd.read_parquet(OUT_DIR / "states.parquet"), pd.read_parquet(OUT_DIR / "states_innings.parquet")


if __name__ == "__main__":
    s, inn = build()
    print("states per competition/gender (innings 1+2):")
    print(s.groupby(["gender", "competition"]).agg(states=("runs", "size"), matches=("match_id", "nunique")).to_string())
    print("reduced innings:", int(inn.reduced.sum()), "of", len(inn))
    ipl = inn[(inn.competition == "ipl") & (inn.innings == 1) & ~inn.reduced]
    print(ipl.groupby("season_year").final_total.agg(["count", "mean"]).round(1).T.to_string())
