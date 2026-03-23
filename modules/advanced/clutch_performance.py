"""Module A5 — Clutch Performance & Pressure Index.

Measures player performance under high-pressure situations:
  - Death overs in close chases (2nd innings, RR > 9, last 5 overs)
  - Batting with 5+ wickets down
  - Bowling at the death with game on the line

Clutch Index = (Actual performance in pressure / Expected performance) * 100
  > 100 = performs better under pressure
  < 100 = chokes under pressure
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class ClutchPerformance(BaseModule):
    module_id = "A5"
    module_name = "Clutch & Pressure Index"
    category = "advanced"
    supported_filters = frozenset({"format", "player", "team", "season"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        role = (params.extra or {}).get("role", "batting")
        if role == "bowling":
            return self._bowling_clutch(params)
        return self._batting_clutch(params)

    def _batting_clutch(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        all_values = values + values

        sql = f"""
        WITH normal_stats AS (
            SELECT
                d.batter,
                SUM(d.runs_batter) AS normal_runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS normal_balls,
                COUNT(*) FILTER (WHERE d.runs_batter = 4 OR d.runs_batter = 6) AS normal_boundaries,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL AND d.player_out = d.batter
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out')) AS normal_dismissals,
                COUNT(DISTINCT d.match_id) AS total_matches
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.batter
        ),
        pressure_stats AS (
            SELECT
                d.batter,
                SUM(d.runs_batter) AS pressure_runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS pressure_balls,
                COUNT(*) FILTER (WHERE d.runs_batter = 4 OR d.runs_batter = 6) AS pressure_boundaries,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL AND d.player_out = d.batter
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out')) AS pressure_dismissals,
                COUNT(DISTINCT d.match_id) AS pressure_matches
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
                AND (
                    -- Death overs in 2nd innings (chasing)
                    (d.innings = 2 AND d.over_num >= 15)
                    -- OR batting with 4+ wickets down (reconstructed from ball data)
                    OR d.over_num >= 15
                )
            GROUP BY d.batter
        )
        SELECT
            n.batter,
            n.total_matches AS matches,
            n.normal_runs AS total_runs,
            n.normal_balls AS total_balls,
            ROUND(n.normal_runs * 100.0 / NULLIF(n.normal_balls, 0), 1) AS overall_sr,

            p.pressure_matches AS pressure_innings,
            p.pressure_runs,
            p.pressure_balls,
            ROUND(p.pressure_runs * 100.0 / NULLIF(p.pressure_balls, 0), 1) AS pressure_sr,

            -- Clutch Index: pressure SR / overall SR * 100
            ROUND(
                (p.pressure_runs * 100.0 / NULLIF(p.pressure_balls, 0))
                / NULLIF(n.normal_runs * 100.0 / NULLIF(n.normal_balls, 0), 0) * 100,
                1
            ) AS clutch_index,

            ROUND(p.pressure_boundaries * 100.0 / NULLIF(p.pressure_balls, 0), 1) AS pressure_boundary_pct,
            ROUND(n.normal_boundaries * 100.0 / NULLIF(n.normal_balls, 0), 1) AS overall_boundary_pct,
            p.pressure_dismissals,
            ROUND(p.pressure_runs * 1.0 / NULLIF(p.pressure_dismissals, 0), 1) AS pressure_avg
        FROM normal_stats n
        JOIN pressure_stats p ON n.batter = p.batter
        WHERE n.normal_balls >= 50 AND p.pressure_balls >= 15
        ORDER BY clutch_index DESC
        LIMIT 40
        """
        return query(sql, all_values)

    def _bowling_clutch(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player}%")

        all_values = values + values

        sql = f"""
        WITH normal_stats AS (
            SELECT
                d.bowler,
                SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0)
                    AS normal_runs_conceded,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS normal_legal_balls,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                    AS normal_wickets,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS normal_dots,
                COUNT(DISTINCT d.match_id) AS total_matches
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.bowler
        ),
        pressure_stats AS (
            SELECT
                d.bowler,
                SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0)
                    AS pressure_runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS pressure_legal_balls,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                    AS pressure_wickets,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS pressure_dots,
                COUNT(DISTINCT d.match_id) AS pressure_matches
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num >= 15
            GROUP BY d.bowler
        )
        SELECT
            n.bowler,
            n.total_matches AS matches,
            ROUND(n.normal_runs_conceded * 6.0 / NULLIF(n.normal_legal_balls, 0), 2) AS overall_economy,
            n.normal_wickets AS total_wickets,

            p.pressure_matches AS death_innings,
            p.pressure_runs AS death_runs,
            p.pressure_legal_balls AS death_balls,
            ROUND(p.pressure_runs * 6.0 / NULLIF(p.pressure_legal_balls, 0), 2) AS death_economy,
            p.pressure_wickets AS death_wickets,

            -- Clutch: lower death economy relative to overall = clutch bowler
            -- Index > 100 means bowler is BETTER at death than overall
            ROUND(
                NULLIF(n.normal_runs_conceded * 6.0 / NULLIF(n.normal_legal_balls, 0), 0)
                / NULLIF(p.pressure_runs * 6.0 / NULLIF(p.pressure_legal_balls, 0), 0) * 100,
                1
            ) AS clutch_index,

            ROUND(p.pressure_dots * 100.0 / NULLIF(p.pressure_legal_balls, 0), 1) AS death_dot_pct,
            ROUND(n.normal_dots * 100.0 / NULLIF(n.normal_legal_balls, 0), 1) AS overall_dot_pct,
            ROUND(p.pressure_wickets * 6.0 / NULLIF(p.pressure_legal_balls, 0), 2) AS death_wicket_rate
        FROM normal_stats n
        JOIN pressure_stats p ON n.bowler = p.bowler
        WHERE n.normal_legal_balls >= 120 AND p.pressure_legal_balls >= 30
        ORDER BY clutch_index DESC
        LIMIT 40
        """
        return query(sql, all_values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        role = (params.extra or {}).get("role", "batting")
        if role == "bowling":
            return self._bowling_plot(df, params)
        return self._batting_plot(df, params)

    def _batting_plot(self, df, params):
        top = df.head(20).copy()

        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.5, 0.5],
            subplot_titles=[
                "Clutch Index (>100 = thrives under pressure)",
                "Overall SR vs Pressure SR"
            ],
        )

        # Left: Clutch Index horizontal bar with color gradient
        colors = ["#4CAF50" if ci >= 100 else "#EF5350" for ci in top["clutch_index"]]
        top_sorted = top.sort_values("clutch_index", ascending=True).head(15)
        bar_colors = ["#4CAF50" if ci >= 100 else "#EF5350" for ci in top_sorted["clutch_index"]]

        fig.add_trace(go.Bar(
            y=top_sorted["batter"], x=top_sorted["clutch_index"],
            orientation="h", marker_color=bar_colors,
            text=[f"{v}" for v in top_sorted["clutch_index"]],
            textposition="outside",
            showlegend=False,
            hovertemplate="<b>%{y}</b><br>Clutch: %{x}<extra></extra>",
        ), row=1, col=1)

        # Add vertical line at 100 (baseline)
        fig.add_vline(x=100, line_dash="dash", line_color="#666", row=1, col=1)

        # Right: Dumbbell — overall SR vs pressure SR
        top15 = top.head(15).sort_values("pressure_sr", ascending=True)
        for _, row in top15.iterrows():
            color = "#4CAF50" if row["pressure_sr"] >= row["overall_sr"] else "#EF5350"
            fig.add_trace(go.Scatter(
                x=[row["overall_sr"], row["pressure_sr"]],
                y=[row["batter"], row["batter"]],
                mode="lines+markers",
                line=dict(color=color, width=2.5),
                marker=dict(size=[7, 11], color=[color, color],
                           symbol=["circle", "diamond"]),
                showlegend=False,
                hovertemplate=f"<b>{row['batter']}</b><br>Overall: {row['overall_sr']}<br>Pressure: {row['pressure_sr']}<extra></extra>",
            ), row=1, col=2)

        fig.add_annotation(text="● Overall SR  ◆ Pressure SR", x=0.75, y=-0.12,
                          xref="paper", yref="paper", showarrow=False, font=dict(size=10))

        fig.update_layout(
            title="Batting Clutch Performance — Death Overs Under Pressure",
            height=max(500, 15 * 32),
            legend=dict(orientation="h", y=-0.12, x=0.25, xanchor="center"),
        )
        fig.update_xaxes(title_text="Clutch Index", row=1, col=1)
        fig.update_xaxes(title_text="Strike Rate", row=1, col=2)

        return fig

    def _bowling_plot(self, df, params):
        top = df.head(20).copy()

        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.5, 0.5],
            subplot_titles=[
                "Clutch Index (>100 = death specialist)",
                "Overall Economy vs Death Economy"
            ],
        )

        # Left: Clutch Index bar
        top_sorted = top.sort_values("clutch_index", ascending=True).head(15)
        bar_colors = ["#4CAF50" if ci >= 100 else "#EF5350" for ci in top_sorted["clutch_index"]]

        fig.add_trace(go.Bar(
            y=top_sorted["bowler"], x=top_sorted["clutch_index"],
            orientation="h", marker_color=bar_colors,
            text=[f"{v}" for v in top_sorted["clutch_index"]],
            textposition="outside",
            showlegend=False,
        ), row=1, col=1)

        fig.add_vline(x=100, line_dash="dash", line_color="#666", row=1, col=1)

        # Right: Dumbbell — overall economy vs death economy
        top15 = top.head(15).sort_values("death_economy", ascending=False)
        for _, row in top15.iterrows():
            # Lower death economy than overall = better at death (green)
            color = "#4CAF50" if row["death_economy"] <= row["overall_economy"] else "#EF5350"
            fig.add_trace(go.Scatter(
                x=[row["overall_economy"], row["death_economy"]],
                y=[row["bowler"], row["bowler"]],
                mode="lines+markers",
                line=dict(color=color, width=2.5),
                marker=dict(size=[7, 11], color=[color, color],
                           symbol=["circle", "diamond"]),
                showlegend=False,
                hovertemplate=f"<b>{row['bowler']}</b><br>Overall: {row['overall_economy']}<br>Death: {row['death_economy']}<extra></extra>",
            ), row=1, col=2)

        fig.add_annotation(text="● Overall Econ  ◆ Death Econ", x=0.75, y=-0.12,
                          xref="paper", yref="paper", showarrow=False, font=dict(size=10))

        fig.update_layout(
            title="Bowling Clutch Performance — Death Over Specialists",
            height=max(500, 15 * 32),
        )
        fig.update_xaxes(title_text="Clutch Index", row=1, col=1)
        fig.update_xaxes(title_text="Economy Rate", row=1, col=2)

        return fig
