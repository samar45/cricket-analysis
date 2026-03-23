"""Module I1 — Phase-by-Phase Analysis.

Breaks innings into Powerplay (0-5), Middle (6-14) and Death (15-19).
Separate views for batting and bowling with role-appropriate stats:
  Batting: runs, balls, strike rate, dismissals, boundary %, dot %, innings, not outs
  Bowling: overs, runs conceded, wickets, economy, dot ball %, boundary %
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class PhaseAnalysis(BaseModule):
    module_id = "I1"
    module_name = "Phase Breakdown (PP / Middle / Death)"
    category = "intermediate"
    supported_filters = frozenset({"format", "team", "player", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        role = (params.extra or {}).get("role", "batting")
        if role == "bowling":
            return self._bowling_phase(params)
        return self._batting_phase(params)

    def _batting_phase(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        player_clause = ""
        if params.player:
            player_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        sql = f"""
        WITH phase_innings AS (
            SELECT
                CASE
                    WHEN d.over_num BETWEEN 0 AND 5   THEN 'Powerplay (1-6)'
                    WHEN d.over_num BETWEEN 6 AND 14  THEN 'Middle (7-15)'
                    WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (16-20)'
                END AS phase,
                CASE WHEN d.over_num <= 5 THEN 1 WHEN d.over_num <= 14 THEN 2 ELSE 3 END AS phase_order,
                d.match_id,
                d.batter,
                d.innings
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
        )
        SELECT
            pi_agg.phase,
            pi_agg.phase_order,
            pi_agg.innings,
            pi_agg.not_outs,
            d_agg.runs,
            d_agg.balls,
            d_agg.strike_rate,
            d_agg.dismissals,
            d_agg.fours,
            d_agg.sixes,
            d_agg.boundary_pct,
            d_agg.dots,
            d_agg.dot_pct
        FROM (
            SELECT
                CASE
                    WHEN d.over_num BETWEEN 0 AND 5   THEN 'Powerplay (1-6)'
                    WHEN d.over_num BETWEEN 6 AND 14  THEN 'Middle (7-15)'
                    WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (16-20)'
                END AS phase,
                CASE WHEN d.over_num <= 5 THEN 1 WHEN d.over_num <= 14 THEN 2 ELSE 3 END AS phase_order,
                SUM(d.runs_batter) AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS balls,
                ROUND(SUM(d.runs_batter) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')), 0), 1) AS strike_rate,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.player_out = d.batter) AS dismissals,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                ROUND((COUNT(*) FILTER (WHERE d.runs_batter = 4)
                     + COUNT(*) FILTER (WHERE d.runs_batter = 6)) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')), 0), 1) AS boundary_pct,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots,
                ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY phase, phase_order
        ) d_agg
        JOIN (
            SELECT
                phase, phase_order,
                COUNT(DISTINCT match_id || '-' || innings) AS innings,
                COUNT(DISTINCT match_id || '-' || innings) -
                    COUNT(DISTINCT CASE WHEN has_dismissal = 1 THEN match_id || '-' || innings END) AS not_outs
            FROM (
                SELECT
                    CASE
                        WHEN d.over_num BETWEEN 0 AND 5   THEN 'Powerplay (1-6)'
                        WHEN d.over_num BETWEEN 6 AND 14  THEN 'Middle (7-15)'
                        WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (16-20)'
                    END AS phase,
                    CASE WHEN d.over_num <= 5 THEN 1 WHEN d.over_num <= 14 THEN 2 ELSE 3 END AS phase_order,
                    d.match_id, d.innings,
                    MAX(CASE WHEN d.wicket_type IS NOT NULL AND d.player_out = d.batter THEN 1 ELSE 0 END) AS has_dismissal
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {where} {player_clause}
                    AND d.over_num BETWEEN 0 AND 19
                GROUP BY phase, phase_order, d.match_id, d.innings, d.batter
            ) sub
            GROUP BY phase, phase_order
        ) pi_agg ON d_agg.phase = pi_agg.phase
        ORDER BY d_agg.phase_order
        """
        # Values are used 3 times in the query
        all_values = values + values + values
        return query(sql, all_values)

    def _bowling_phase(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        player_clause = ""
        if params.player:
            player_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player}%")

        sql = f"""
        SELECT
            CASE
                WHEN d.over_num BETWEEN 0 AND 5   THEN 'Powerplay (1-6)'
                WHEN d.over_num BETWEEN 6 AND 14  THEN 'Middle (7-15)'
                WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (16-20)'
            END AS phase,
            CASE WHEN d.over_num <= 5 THEN 1 WHEN d.over_num <= 14 THEN 2 ELSE 3 END AS phase_order,
            ROUND(COUNT(*) FILTER (WHERE d.extra_type IS NULL) / 6.0, 1) AS overs,
            SUM(d.runs_total) AS runs_conceded,
            COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                AS wickets,
            ROUND(SUM(d.runs_total) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
            ROUND(
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) * 1.0
                / NULLIF(COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')), 0),
                1) AS bowling_sr,
            COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours_conceded,
            COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes_conceded,
            ROUND((COUNT(*) FILTER (WHERE d.runs_batter = 4) + COUNT(*) FILTER (WHERE d.runs_batter = 6))
                * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1) AS boundary_pct,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct,
            SUM(d.runs_extras) FILTER (WHERE d.extra_type = 'wides') AS wides,
            SUM(d.runs_extras) FILTER (WHERE d.extra_type = 'noballs') AS noballs
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} {player_clause}
            AND d.over_num BETWEEN 0 AND 19
        GROUP BY phase, phase_order
        ORDER BY phase_order
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty or "phase" not in df.columns:
            return None

        role = (params.extra or {}).get("role", "batting")
        phases = df["phase"].tolist()
        phase_colors = ["#2196F3", "#FF9800", "#F44336"]

        if role == "bowling":
            return self._bowling_plot(df, phases, phase_colors, params)
        return self._batting_plot(df, phases, phase_colors, params)

    def _batting_plot(self, df, phases, phase_colors, params):
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.55, 0.45],
            subplot_titles=["Strike Rate by Phase", "Boundary % vs Dot Ball %"],
        )

        # Left: SR bar chart with color-coded phases
        fig.add_trace(go.Bar(
            name="Strike Rate", x=phases, y=df["strike_rate"],
            marker_color=phase_colors,
            text=[f"{v}" for v in df["strike_rate"]], textposition="outside",
            showlegend=False,
        ), row=1, col=1)

        # Right: grouped bar — boundary % vs dot %
        fig.add_trace(go.Bar(
            name="Boundary %", x=phases, y=df["boundary_pct"],
            marker_color="#E91E63",
            text=[f"{v}%" for v in df["boundary_pct"]], textposition="outside",
        ), row=1, col=2)

        fig.add_trace(go.Bar(
            name="Dot Ball %", x=phases, y=df["dot_pct"],
            marker_color="#9E9E9E",
            text=[f"{v}%" for v in df["dot_pct"]], textposition="outside",
        ), row=1, col=2)

        title = "Batting Phase Breakdown"
        if params.player:
            title += f" — {params.player}"
        if params.team:
            title += f" — {params.team}"

        fig.update_layout(
            title=title, barmode="group",
            height=450,
            legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        )
        fig.update_yaxes(title_text="Strike Rate", row=1, col=1)
        fig.update_yaxes(title_text="Percentage", row=1, col=2)
        return fig

    def _bowling_plot(self, df, phases, phase_colors, params):
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.55, 0.45],
            subplot_titles=["Economy by Phase", "Dot % vs Boundary %"],
        )

        # Left: economy bars
        fig.add_trace(go.Bar(
            name="Economy", x=phases, y=df["economy"],
            marker_color=phase_colors,
            text=[f"{v}" for v in df["economy"]], textposition="outside",
            showlegend=False,
        ), row=1, col=1)

        # Right: dot % vs boundary %
        fig.add_trace(go.Bar(
            name="Dot Ball %", x=phases, y=df["dot_pct"],
            marker_color="#42A5F5",
            text=[f"{v}%" for v in df["dot_pct"]], textposition="outside",
        ), row=1, col=2)

        boundary_pct = df["boundary_pct"] if "boundary_pct" in df.columns else [0] * len(phases)
        fig.add_trace(go.Bar(
            name="Boundary %", x=phases, y=boundary_pct,
            marker_color="#EF5350",
            text=[f"{v}%" for v in boundary_pct], textposition="outside",
        ), row=1, col=2)

        title = "Bowling Phase Breakdown"
        if params.player:
            title += f" — {params.player}"
        if params.team:
            title += f" — {params.team}"

        fig.update_layout(
            title=title, barmode="group",
            height=450,
            legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        )
        fig.update_yaxes(title_text="Economy", row=1, col=1)
        fig.update_yaxes(title_text="Percentage", row=1, col=2)
        return fig
