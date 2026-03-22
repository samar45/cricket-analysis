"""Module I1 — Phase-by-Phase Analysis.

Breaks innings into Powerplay (0-5), Middle (6-14) and Death (15-19).
Shows run rates, wicket rates, economy, dot-ball % per phase.
Can drill into a team or a player.
"""

import pandas as pd
import plotly.graph_objects as go

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class PhaseAnalysis(BaseModule):
    module_id = "I1"
    module_name = "Phase Breakdown (PP / Middle / Death)"
    category = "intermediate"
    supported_filters = frozenset({"format", "team", "player", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND (d.batter ILIKE ? OR d.bowler ILIKE ?)"
            values.extend([f"%{params.player}%", f"%{params.player}%"])

        team_clause = ""
        if params.team:
            team_clause = "AND (d.batting_team ILIKE ? OR d.bowling_team ILIKE ?)"
            # need batting_team in deliveries — join from matches via innings
            # Use match team1/team2 based on innings number
            team_clause = ""  # handled via matches join

        sql = f"""
        WITH phased AS (
            SELECT
                d.match_id,
                d.innings,
                CASE
                    WHEN d.over_num BETWEEN 0  AND 5  THEN 'Powerplay (0-5)'
                    WHEN d.over_num BETWEEN 6  AND 14 THEN 'Middle (6-14)'
                    WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (15-19)'
                    ELSE 'Other'
                END AS phase,
                CASE
                    WHEN d.over_num BETWEEN 0  AND 5  THEN 1
                    WHEN d.over_num BETWEEN 6  AND 14 THEN 2
                    WHEN d.over_num BETWEEN 15 AND 19 THEN 3
                    ELSE 4
                END AS phase_order,
                d.runs_total,
                d.runs_batter,
                d.extra_type,
                d.wicket_type,
                d.runs_extras
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
        )
        SELECT
            phase,
            phase_order,
            COUNT(DISTINCT match_id || '-' || innings)           AS innings_count,
            SUM(runs_total)                                      AS total_runs,
            COUNT(*) FILTER (WHERE wicket_type IS NOT NULL
                AND wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                                                                 AS wickets,
            COUNT(*) FILTER (WHERE extra_type IS NULL)           AS legal_balls,
            ROUND(SUM(runs_total) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE extra_type IS NULL), 0), 2) AS run_rate,
            ROUND(COUNT(*) FILTER (WHERE wicket_type IS NOT NULL
                AND wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                * 6.0 / NULLIF(COUNT(*) FILTER (WHERE extra_type IS NULL), 0), 2)
                                                                 AS wickets_per_over,
            ROUND(COUNT(*) FILTER (WHERE runs_batter = 0 AND extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*), 0), 2)               AS dot_pct,
            ROUND(AVG(runs_total), 3)                            AS avg_runs_per_ball,
            COUNT(*) FILTER (WHERE runs_batter = 4)              AS fours,
            COUNT(*) FILTER (WHERE runs_batter = 6)              AS sixes
        FROM phased
        WHERE phase != 'Other'
        GROUP BY phase, phase_order
        ORDER BY phase_order
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Run Rate",
            x=df["phase"], y=df["run_rate"],
            marker_color=["#2196F3", "#FF9800", "#F44336"],
            yaxis="y",
        ))
        fig.add_trace(go.Scatter(
            name="Dot Ball %",
            x=df["phase"], y=df["dot_pct"],
            mode="lines+markers",
            marker=dict(size=10, color="white", line=dict(color="gray", width=2)),
            yaxis="y2",
        ))

        title = "Run Rate & Dot Ball % by Phase"
        if params.player:
            title += f" — {params.player}"
        if params.team:
            title += f" — {params.team}"

        fig.update_layout(
            title=title,
            yaxis=dict(title="Run Rate"),
            yaxis2=dict(title="Dot Ball %", overlaying="y", side="right", range=[0, 100]),
            barmode="group",
            height=450,
            legend=dict(x=0.01, y=0.99),
        )
        return fig
