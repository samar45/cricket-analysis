"""Form: a player's innings (or bowling spells) in date order with rolling averages."""

import pandas as pd

from ..db import query
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters
from ..sql.fragments import BOWLER_WICKET, IS_DOT, LEGAL_BALL, RUNS_CONCEDED
from ..sql.innings import batter_innings


@module(
    id="form",
    title="Player form",
    category="intermediate",
    description="One row per innings (batter) or bowling spell (bowler), oldest first, with rolling averages over "
                "the last `window` rows. Needs a player.",
    params=[
        ParamSpec("player", "player", required=True, help="Exact player name as in the data (use resolve first)"),
        *std("competition", "season", "team", "opposition", "venue"),
        ParamSpec("role", "choice", default="batter", choices=("batter", "bowler"),
                  help="batter: runs and strike rate; bowler: wickets and economy"),
        ParamSpec("window", "int", default=10, help="Rolling window in innings/spells"),
    ],
    caveats=[
        "Rolling values are over the last `window` innings (spells) of that player in the filtered set, not calendar time.",
        "Batter: rolling_runs = mean runs per innings (not a batting average); rolling_sr = total runs * 100 / total balls over the window.",
        "Bowler: rolling_wickets = mean wickets per spell; rolling_economy = total runs conceded * 6 / total legal balls over the window.",
        "A batter dismissed as the non-striker has an innings with 0 balls; one left not out at the non-striker's end without facing has none.",
        "Super-over innings are excluded.",
    ],
)
def form(f: Filters, role: str = "batter", window: int = 10) -> pd.DataFrame:
    window = max(int(window), 1)
    frame = f"ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW"   # window is an int, safe to inline
    if role == "batter":
        inn, params = batter_innings(f, [("m.season", "season"), ("m.venue", "venue")])
        sql = f"""
        WITH inn AS ({inn})
        SELECT ROW_NUMBER() OVER w0 AS innings_no, match_id, date, season, venue, runs, balls, out AS dismissed, fours, sixes,
               ROUND(runs * 100.0 / NULLIF(balls, 0), 1) AS strike_rate,
               ROUND(AVG(runs) OVER w, 1) AS rolling_runs,
               ROUND(SUM(runs) OVER w * 100.0 / NULLIF(SUM(balls) OVER w, 0), 1) AS rolling_sr
        FROM inn WINDOW w0 AS (ORDER BY date, match_id, innings), w AS (ORDER BY date, match_id, innings {frame})
        ORDER BY date, match_id, innings
        """
        return query(sql, params)
    where, params = f.where("bowl")
    sql = f"""
    WITH spell AS (
        SELECT d.match_id, d.innings, m.date, m.season, m.venue,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET}) AS wickets,
               SUM({RUNS_CONCEDED}) AS runs_conceded,
               COUNT(*) FILTER (WHERE {LEGAL_BALL}) AS balls,
               COUNT(*) FILTER (WHERE {IS_DOT}) AS dots
        FROM deliveries d JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
        GROUP BY d.match_id, d.innings, m.date, m.season, m.venue
    )
    SELECT ROW_NUMBER() OVER w0 AS spell_no, match_id, date, season, venue,
           wickets::INTEGER AS wickets, runs_conceded::INTEGER AS runs_conceded, balls::INTEGER AS balls,
           ROUND(runs_conceded * 6.0 / NULLIF(balls, 0), 2) AS economy,
           ROUND(dots * 100.0 / NULLIF(balls, 0), 1) AS dot_pct,
           ROUND(AVG(wickets) OVER w, 2) AS rolling_wickets,
           ROUND(SUM(runs_conceded) OVER w * 6.0 / NULLIF(SUM(balls) OVER w, 0), 2) AS rolling_economy
    FROM spell WINDOW w0 AS (ORDER BY date, match_id, innings), w AS (ORDER BY date, match_id, innings {frame})
    ORDER BY date, match_id, innings
    """
    return query(sql, params)
