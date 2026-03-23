"""Module A1 — True Strike Rate & True Economy.

Adjusts batting SR and bowling economy for match context:
  - Phase (powerplay / middle / death)
  - Wickets fallen (pressure)
  - Venue scoring difficulty

True SR  = (Actual Runs / Expected Runs) * League Avg SR
True Econ = (Actual Conceded / Expected Conceded) * League Avg Economy

Players who perform in tough situations (death overs, high-pressure wickets down)
get boosted; those padding stats in easy situations get adjusted down.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class TruePerformance(BaseModule):
    module_id = "A1"
    module_name = "True Strike Rate & True Economy"
    category = "advanced"
    supported_filters = frozenset({"format", "player", "team", "season"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        role = (params.extra or {}).get("role", "batting")
        if role == "bowling":
            return self._true_economy(params)
        return self._true_sr(params)

    def _true_sr(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        # Baseline = league average (same format/season, but no player/team filter)
        base_params = ModuleParams(format=params.format, season=params.season)
        base_where2, base_values2 = self._build_where_clauses(base_params, "m")

        # SQL has 2 parameterized sections: phase_baseline (base_where2) + player_phase (where)
        all_values = base_values2 + values

        sql = f"""
        WITH phase_baseline AS (
            SELECT
                CASE
                    WHEN d.over_num BETWEEN 0 AND 5   THEN 'powerplay'
                    WHEN d.over_num BETWEEN 6 AND 14  THEN 'middle'
                    ELSE 'death'
                END AS phase,
                AVG(d.runs_batter) AS expected_runs_per_ball,
                AVG(d.runs_batter) * 100.0 AS expected_sr
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {base_where2}
                AND (d.extra_type IS NULL OR d.extra_type NOT IN ('wides'))
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY phase
        ),
        player_phase AS (
            SELECT
                d.batter,
                CASE
                    WHEN d.over_num BETWEEN 0 AND 5   THEN 'powerplay'
                    WHEN d.over_num BETWEEN 6 AND 14  THEN 'middle'
                    ELSE 'death'
                END AS phase,
                SUM(d.runs_batter) AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS balls,
                COUNT(DISTINCT d.match_id) AS matches,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.batter, phase
        ),
        league_avg AS (
            SELECT ROUND(AVG(expected_sr), 1) AS avg_sr
            FROM phase_baseline
        )
        SELECT
            pp.batter,
            SUM(pp.matches) AS matches,
            SUM(pp.runs) AS total_runs,
            SUM(pp.balls) AS total_balls,
            ROUND(SUM(pp.runs) * 100.0 / NULLIF(SUM(pp.balls), 0), 1) AS raw_sr,
            ROUND(
                SUM(pp.runs)
                / NULLIF(SUM(pp.balls * pb.expected_runs_per_ball), 0)
                * (SELECT avg_sr FROM league_avg),
                1
            ) AS true_sr,
            ROUND(
                SUM(pp.runs) * 100.0 / NULLIF(SUM(pp.balls), 0)
                - SUM(pp.runs)
                  / NULLIF(SUM(pp.balls * pb.expected_runs_per_ball), 0)
                  * (SELECT avg_sr FROM league_avg),
                1
            ) AS sr_adjustment,
            SUM(pp.fours) AS fours,
            SUM(pp.sixes) AS sixes,
            -- Phase-wise raw SR
            MAX(CASE WHEN pp.phase = 'powerplay' THEN ROUND(pp.runs * 100.0 / NULLIF(pp.balls, 0), 1) END) AS sr_powerplay,
            MAX(CASE WHEN pp.phase = 'middle' THEN ROUND(pp.runs * 100.0 / NULLIF(pp.balls, 0), 1) END) AS sr_middle,
            MAX(CASE WHEN pp.phase = 'death' THEN ROUND(pp.runs * 100.0 / NULLIF(pp.balls, 0), 1) END) AS sr_death
        FROM player_phase pp
        JOIN phase_baseline pb ON pp.phase = pb.phase
        GROUP BY pp.batter
        HAVING SUM(pp.balls) >= 30
        ORDER BY true_sr DESC
        LIMIT 40
        """
        return query(sql, all_values)

    def _true_economy(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player}%")

        base_params = ModuleParams(format=params.format, season=params.season)
        base_where, base_values = self._build_where_clauses(base_params, "m")

        # SQL has 2 parameterized sections: phase_baseline (base_where) + bowler_phase (where)
        all_values = base_values + values

        sql = f"""
        WITH phase_baseline AS (
            SELECT
                CASE
                    WHEN d.over_num BETWEEN 0 AND 5   THEN 'powerplay'
                    WHEN d.over_num BETWEEN 6 AND 14  THEN 'middle'
                    ELSE 'death'
                END AS phase,
                AVG(d.runs_total) AS expected_runs_per_ball
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {base_where}
                AND d.extra_type IS NULL
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY phase
        ),
        bowler_phase AS (
            SELECT
                d.bowler,
                CASE
                    WHEN d.over_num BETWEEN 0 AND 5   THEN 'powerplay'
                    WHEN d.over_num BETWEEN 6 AND 14  THEN 'middle'
                    ELSE 'death'
                END AS phase,
                SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0) AS runs_conceded,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls,
                COUNT(DISTINCT d.match_id) AS matches,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')) AS wickets,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
                AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.bowler, phase
        ),
        league_avg AS (
            SELECT ROUND(AVG(expected_runs_per_ball) * 6, 2) AS avg_economy
            FROM phase_baseline
        )
        SELECT
            bp.bowler,
            SUM(bp.matches) AS matches,
            SUM(bp.runs_conceded) AS runs_conceded,
            SUM(bp.legal_balls) AS legal_balls,
            ROUND(SUM(bp.legal_balls) / 6.0, 1) AS overs,
            SUM(bp.wickets) AS wickets,
            ROUND(SUM(bp.runs_conceded) * 6.0 / NULLIF(SUM(bp.legal_balls), 0), 2) AS raw_economy,
            ROUND(
                SUM(bp.runs_conceded)
                / NULLIF(SUM(bp.legal_balls * pb.expected_runs_per_ball), 0)
                * (SELECT avg_economy FROM league_avg),
                2
            ) AS true_economy,
            ROUND(
                SUM(bp.runs_conceded) * 6.0 / NULLIF(SUM(bp.legal_balls), 0)
                - SUM(bp.runs_conceded)
                  / NULLIF(SUM(bp.legal_balls * pb.expected_runs_per_ball), 0)
                  * (SELECT avg_economy FROM league_avg),
                2
            ) AS econ_adjustment,
            ROUND(SUM(bp.dots) * 100.0 / NULLIF(SUM(bp.legal_balls), 0), 1) AS dot_pct,
            -- Phase-wise raw economy
            MAX(CASE WHEN bp.phase = 'powerplay' THEN ROUND(bp.runs_conceded * 6.0 / NULLIF(bp.legal_balls, 0), 2) END) AS econ_powerplay,
            MAX(CASE WHEN bp.phase = 'middle' THEN ROUND(bp.runs_conceded * 6.0 / NULLIF(bp.legal_balls, 0), 2) END) AS econ_middle,
            MAX(CASE WHEN bp.phase = 'death' THEN ROUND(bp.runs_conceded * 6.0 / NULLIF(bp.legal_balls, 0), 2) END) AS econ_death
        FROM bowler_phase bp
        JOIN phase_baseline pb ON bp.phase = pb.phase
        GROUP BY bp.bowler
        HAVING SUM(bp.legal_balls) >= 60
        ORDER BY true_economy ASC
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
            rows=2, cols=2,
            row_heights=[0.55, 0.45],
            column_widths=[0.55, 0.45],
            subplot_titles=[
                "Raw SR vs True SR",
                "SR Adjustment (+ = tougher situations)",
                "Phase-wise Strike Rate — Top 10",
                "True SR vs Balls Faced (bubble = runs)"
            ],
            vertical_spacing=0.12, horizontal_spacing=0.1,
        )

        top15 = top.head(15).sort_values("true_sr", ascending=True)

        # Top-Left: dumbbell chart — raw SR vs true SR
        for _, row in top15.iterrows():
            color = "#4CAF50" if row["true_sr"] > row["raw_sr"] else "#EF5350"
            fig.add_trace(go.Scatter(
                x=[row["raw_sr"], row["true_sr"]],
                y=[row["batter"], row["batter"]],
                mode="lines+markers",
                line=dict(color=color, width=3),
                marker=dict(size=[6, 11], color=[color, color],
                           symbol=["circle", "diamond"]),
                showlegend=False,
                hovertemplate=f"<b>{row['batter']}</b><br>Raw: {row['raw_sr']}<br>True: {row['true_sr']}<extra></extra>",
            ), row=1, col=1)

        # Top-Right: SR adjustment bar (waterfall-style)
        top15_adj = top15.sort_values("sr_adjustment", ascending=True)
        adj_colors = ["#4CAF50" if a > 0 else "#EF5350" for a in top15_adj["sr_adjustment"]]
        fig.add_trace(go.Bar(
            y=top15_adj["batter"], x=top15_adj["sr_adjustment"],
            orientation="h", marker_color=adj_colors,
            text=[f"{a:+.1f}" for a in top15_adj["sr_adjustment"]],
            textposition="outside",
            showlegend=False,
            hovertemplate="<b>%{y}</b><br>Adjustment: %{x:+.1f}<extra></extra>",
        ), row=1, col=2)

        # Add zero line
        fig.add_vline(x=0, line_dash="dash", line_color="#666", row=1, col=2)

        # Bottom-Left: grouped bar — phase SR for top 10
        top10 = top.head(10)
        phases = ["sr_powerplay", "sr_middle", "sr_death"]
        phase_labels = ["PP", "Middle", "Death"]
        phase_colors = ["#2196F3", "#FF9800", "#F44336"]

        for phase_col, label, color in zip(phases, phase_labels, phase_colors):
            if phase_col in top10.columns:
                fig.add_trace(go.Bar(
                    name=label, y=top10["batter"],
                    x=top10[phase_col].fillna(0),
                    orientation="h", marker_color=color,
                ), row=2, col=1)

        # Bottom-Right: scatter — true SR vs balls, sized by runs
        fig.add_trace(go.Scatter(
            x=top["total_balls"], y=top["true_sr"],
            mode="markers+text",
            marker=dict(
                size=top["total_runs"].clip(lower=50) / 15,
                color=top["sr_adjustment"].fillna(0),
                colorscale="RdYlGn", cmid=0,
                showscale=True,
                colorbar=dict(title="Adj", x=1.0, len=0.4, y=0.2),
                line=dict(width=1, color="#333"),
            ),
            text=top["batter"].str.split().str[-1],
            textposition="top center", textfont=dict(size=8),
            showlegend=False,
            hovertemplate="<b>%{text}</b><br>True SR: %{y}<br>Balls: %{x}<extra></extra>",
        ), row=2, col=2)

        title = "True Strike Rate — Context-Adjusted Batting"
        if params.player:
            title += f" — {params.player}"
        if params.season:
            title += f" ({params.season})"

        fig.update_layout(
            title=title,
            barmode="group", height=700,
            legend=dict(orientation="h", y=-0.05, x=0.25, xanchor="center"),
        )
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_yaxes(autorange="reversed", row=2, col=1)
        fig.update_xaxes(title_text="Strike Rate", row=1, col=1)
        fig.update_xaxes(title_text="Adjustment", row=1, col=2)
        fig.update_xaxes(title_text="Phase SR", row=2, col=1)
        fig.update_xaxes(title_text="Balls Faced", row=2, col=2)
        fig.update_yaxes(title_text="True SR", row=2, col=2)

        return fig

    def _bowling_plot(self, df, params):
        top = df.head(20).copy()

        fig = make_subplots(
            rows=2, cols=2,
            row_heights=[0.55, 0.45],
            column_widths=[0.55, 0.45],
            subplot_titles=[
                "Raw Economy vs True Economy",
                "Economy Adjustment (- = tougher situations)",
                "Phase-wise Economy — Top 10",
                "True Economy vs Wickets (bubble = overs)"
            ],
            vertical_spacing=0.12, horizontal_spacing=0.1,
        )

        top15 = top.head(15).sort_values("true_economy", ascending=False)

        # Top-Left: dumbbell chart
        for _, row in top15.iterrows():
            color = "#4CAF50" if row["true_economy"] < row["raw_economy"] else "#EF5350"
            fig.add_trace(go.Scatter(
                x=[row["raw_economy"], row["true_economy"]],
                y=[row["bowler"], row["bowler"]],
                mode="lines+markers",
                line=dict(color=color, width=3),
                marker=dict(size=[6, 11], color=[color, color],
                           symbol=["circle", "diamond"]),
                showlegend=False,
                hovertemplate=f"<b>{row['bowler']}</b><br>Raw: {row['raw_economy']}<br>True: {row['true_economy']}<extra></extra>",
            ), row=1, col=1)

        # Top-Right: adjustment bar
        top15_adj = top15.sort_values("econ_adjustment", ascending=False)
        adj_colors = ["#4CAF50" if a < 0 else "#EF5350" for a in top15_adj["econ_adjustment"]]
        fig.add_trace(go.Bar(
            y=top15_adj["bowler"], x=top15_adj["econ_adjustment"],
            orientation="h", marker_color=adj_colors,
            text=[f"{a:+.2f}" for a in top15_adj["econ_adjustment"]],
            textposition="outside",
            showlegend=False,
            hovertemplate="<b>%{y}</b><br>Adjustment: %{x:+.2f}<extra></extra>",
        ), row=1, col=2)

        fig.add_vline(x=0, line_dash="dash", line_color="#666", row=1, col=2)

        # Bottom-Left: phase economy for top 10
        top10 = top.head(10)
        phases = ["econ_powerplay", "econ_middle", "econ_death"]
        phase_labels = ["PP", "Middle", "Death"]
        phase_colors = ["#2196F3", "#FF9800", "#F44336"]

        for phase_col, label, color in zip(phases, phase_labels, phase_colors):
            if phase_col in top10.columns:
                fig.add_trace(go.Bar(
                    name=label, y=top10["bowler"],
                    x=top10[phase_col].fillna(0),
                    orientation="h", marker_color=color,
                ), row=2, col=1)

        # Bottom-Right: scatter — true economy vs wickets, sized by overs
        fig.add_trace(go.Scatter(
            x=top["wickets"], y=top["true_economy"],
            mode="markers+text",
            marker=dict(
                size=top["overs"].clip(lower=5) / 3,
                color=top["econ_adjustment"].fillna(0),
                colorscale="RdYlGn_r", cmid=0,
                showscale=True,
                colorbar=dict(title="Adj", x=1.0, len=0.4, y=0.2),
                line=dict(width=1, color="#333"),
            ),
            text=top["bowler"].str.split().str[-1],
            textposition="top center", textfont=dict(size=8),
            showlegend=False,
            hovertemplate="<b>%{text}</b><br>True Econ: %{y}<br>Wkts: %{x}<extra></extra>",
        ), row=2, col=2)

        title = "True Economy — Context-Adjusted Bowling"
        if params.player:
            title += f" — {params.player}"
        if params.season:
            title += f" ({params.season})"

        fig.update_layout(
            title=title,
            barmode="group", height=700,
            legend=dict(orientation="h", y=-0.05, x=0.25, xanchor="center"),
        )
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_yaxes(autorange="reversed", row=2, col=1)
        fig.update_xaxes(title_text="Economy Rate", row=1, col=1)
        fig.update_xaxes(title_text="Adjustment", row=1, col=2)
        fig.update_xaxes(title_text="Phase Economy", row=2, col=1)
        fig.update_xaxes(title_text="Wickets", row=2, col=2)
        fig.update_yaxes(title_text="True Economy", row=2, col=2)

        return fig
