"""Module B1 — Batting Scorecard & Career Stats.

Total runs, average, strike rate, 50s, 100s, highest score per player.
Filterable by: format, season, opposition, venue.
"""

import pandas as pd

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class BattingStats(BaseModule):
    module_id = "B1"
    module_name = "Batting Scorecard & Career Stats"
    category = "basic"

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        # Player filter on deliveries
        player_clause = ""
        if params.player:
            player_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        sql = f"""
        WITH batting_innings AS (
            SELECT
                d.batter,
                d.match_id,
                SUM(d.runs_batter) AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL OR d.extra_type NOT IN ('wides')) AS balls_faced,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                MAX(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END) AS was_out
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
            GROUP BY d.batter, d.match_id
        )
        SELECT
            batter,
            COUNT(*) AS innings,
            SUM(runs) AS total_runs,
            MAX(runs) AS highest_score,
            ROUND(SUM(runs) * 1.0 / NULLIF(SUM(was_out), 0), 2) AS average,
            ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls_faced), 0), 2) AS strike_rate,
            SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
            SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(fours) AS total_fours,
            SUM(sixes) AS total_sixes,
            SUM(balls_faced) AS total_balls
        FROM batting_innings
        GROUP BY batter
        ORDER BY total_runs DESC
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        import plotly.express as px
        if df.empty:
            return None
        top = df.head(15)
        fig = px.bar(
            top, x="batter", y="total_runs",
            title=f"Top Run Scorers — {params.format}" + (f" ({params.season})" if params.season else ""),
            labels={"batter": "Player", "total_runs": "Runs"},
            hover_data=["average", "strike_rate", "innings"],
        )
        fig.update_layout(xaxis_tickangle=-45)
        return fig
