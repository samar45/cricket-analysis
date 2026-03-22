"""Module B2 — Bowling Scorecard & Career Stats.

Wickets, economy rate, bowling average, best bowling figures.
Filterable by: format, season, opposition, phase.
"""

import pandas as pd

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class BowlingStats(BaseModule):
    module_id = "B2"
    module_name = "Bowling Scorecard & Career Stats"
    category = "basic"
    supported_filters = frozenset({"format", "player", "team", "season", "venue", "phase"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player}%")

        # Phase filter
        phase_clause = ""
        if params.phase:
            if params.phase == "powerplay":
                phase_clause = "AND d.over_num BETWEEN 0 AND 5"
            elif params.phase == "middle":
                phase_clause = "AND d.over_num BETWEEN 6 AND 14"
            elif params.phase == "death":
                phase_clause = "AND d.over_num BETWEEN 15 AND 19"

        sql = f"""
        WITH bowling_innings AS (
            SELECT
                d.bowler,
                d.match_id,
                COUNT(DISTINCT d.over_num) AS overs,
                SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes', 'legbyes')), 0) AS runs_conceded,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')) AS wickets,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dot_balls,
                COUNT(*) AS total_balls,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause} {phase_clause}
            GROUP BY d.bowler, d.match_id
        )
        SELECT
            bowler,
            COUNT(*) AS innings,
            SUM(wickets) AS total_wickets,
            SUM(runs_conceded) AS total_runs_conceded,
            ROUND(SUM(runs_conceded) * 1.0 / NULLIF(SUM(wickets), 0), 2) AS bowling_average,
            ROUND(SUM(runs_conceded) * 6.0 / NULLIF(SUM(legal_balls), 0), 2) AS economy,
            ROUND(SUM(legal_balls) * 1.0 / NULLIF(SUM(wickets), 0), 2) AS bowling_strike_rate,
            ROUND(SUM(dot_balls) * 100.0 / NULLIF(SUM(total_balls), 0), 2) AS dot_ball_pct,
            MAX(wickets) AS best_wickets_in_match
        FROM bowling_innings
        GROUP BY bowler
        ORDER BY total_wickets DESC
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        import plotly.express as px
        if df.empty:
            return None
        top = df.head(15)
        fig = px.bar(
            top, x="bowler", y="total_wickets",
            title=f"Top Wicket Takers — {params.format}" + (f" ({params.season})" if params.season else ""),
            labels={"bowler": "Player", "total_wickets": "Wickets"},
            hover_data=["economy", "bowling_average", "innings"],
        )
        fig.update_layout(xaxis_tickangle=-45)
        return fig
