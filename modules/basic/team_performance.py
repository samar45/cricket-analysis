"""Module B3 — Team Performance Summary.

Win/loss/NR record per team per season per format.
Home vs away split, toss impact analysis, average scores.
"""

import pandas as pd

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class TeamPerformance(BaseModule):
    module_id = "B3"
    module_name = "Team Performance Summary"
    category = "basic"
    supported_filters = frozenset({"format", "team", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        sql = f"""
        WITH team_matches AS (
            SELECT
                team AS team_name,
                m.match_id,
                m.season,
                m.winner,
                m.toss_winner,
                m.toss_decision,
                m.result
            FROM matches m
            CROSS JOIN (
                SELECT m2.match_id, m2.team1 AS team FROM matches m2
                UNION ALL
                SELECT m3.match_id, m3.team2 AS team FROM matches m3
            ) teams
            WHERE m.match_id = teams.match_id AND {where}
        )
        SELECT
            team_name,
            COUNT(*) AS matches_played,
            SUM(CASE WHEN winner = team_name THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN winner IS NOT NULL AND winner != team_name THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN result = 'no result' OR winner IS NULL THEN 1 ELSE 0 END) AS no_results,
            ROUND(SUM(CASE WHEN winner = team_name THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) AS win_pct,
            SUM(CASE WHEN toss_winner = team_name THEN 1 ELSE 0 END) AS toss_wins,
            SUM(CASE WHEN toss_winner = team_name AND winner = team_name THEN 1 ELSE 0 END) AS wins_after_toss_win
        FROM team_matches
        GROUP BY team_name
        ORDER BY win_pct DESC
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        import plotly.express as px
        if df.empty:
            return None
        fig = px.bar(
            df, x="team_name", y=["wins", "losses", "no_results"],
            title=f"Team Performance — {params.format}" + (f" ({params.season})" if params.season else ""),
            labels={"team_name": "Team", "value": "Matches"},
            barmode="stack",
        )
        fig.update_layout(xaxis_tickangle=-45)
        return fig
