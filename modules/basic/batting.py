"""Module B1 — Batting Scorecard & Career Stats.

Total runs, average, strike rate, 50s, 100s, highest score per player.
Filterable by: format, season, opposition, venue, phase.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class BattingStats(BaseModule):
    module_id = "B1"
    module_name = "Batting Scorecard & Career Stats"
    category = "basic"
    supported_filters = frozenset({"format", "player", "team", "season", "venue", "phase"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        phase_clause = self._phase_clause(params, "d")

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
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots,
                MAX(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END) AS was_out
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause} {phase_clause}
            GROUP BY d.batter, d.match_id
        )
        SELECT
            batter,
            COUNT(*) AS innings,
            SUM(CASE WHEN was_out = 0 THEN 1 ELSE 0 END) AS not_outs,
            SUM(runs) AS total_runs,
            MAX(runs) AS highest_score,
            ROUND(SUM(runs) * 1.0 / NULLIF(SUM(was_out), 0), 2) AS average,
            ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls_faced), 0), 2) AS strike_rate,
            SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
            SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN runs = 0 AND was_out = 1 THEN 1 ELSE 0 END) AS ducks,
            SUM(fours) AS total_fours,
            SUM(sixes) AS total_sixes,
            SUM(balls_faced) AS total_balls,
            ROUND(SUM(dots) * 100.0 / NULLIF(SUM(balls_faced), 0), 1) AS dot_pct,
            ROUND((SUM(fours) + SUM(sixes)) * 100.0 / NULLIF(SUM(balls_faced), 0), 1) AS boundary_pct
        FROM batting_innings
        GROUP BY batter
        ORDER BY total_runs DESC
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        top = df.head(15).copy()

        # ── Single player: detailed breakdown radar + scatter
        if params.player and len(top) <= 3:
            return self._single_player_plot(top, params)

        # ── Multi-player: bubble chart — x=SR, y=Avg, size=Runs, color=boundary%
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.55, 0.45],
            subplot_titles=[
                "Runs vs Strike Rate (bubble = innings)",
                "Scoring Profile — Top 10"
            ],
        )

        # Left panel: scatter plot
        fig.add_trace(go.Scatter(
            x=top["strike_rate"], y=top["average"],
            mode="markers+text",
            marker=dict(
                size=top["innings"].clip(lower=3) * 2,
                color=top["boundary_pct"],
                colorscale="YlOrRd",
                showscale=True,
                colorbar=dict(title="Boundary %", x=0.47, len=0.8),
                line=dict(width=1, color="#333"),
            ),
            text=top["batter"].str.split().str[-1],  # last name only
            textposition="top center",
            textfont=dict(size=9),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "SR: %{x}<br>Avg: %{y}<br>"
                "Innings: %{marker.size}<extra></extra>"
            ),
            showlegend=False,
        ), row=1, col=1)

        # Right panel: stacked horizontal bar — 4s vs 6s contribution
        top10 = top.head(10)
        runs_from_4s = top10["total_fours"] * 4
        runs_from_6s = top10["total_sixes"] * 6
        other_runs = top10["total_runs"] - runs_from_4s - runs_from_6s

        fig.add_trace(go.Bar(
            name="Other Runs", y=top10["batter"], x=other_runs,
            orientation="h", marker_color="#90CAF9",
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            name="Fours", y=top10["batter"], x=runs_from_4s,
            orientation="h", marker_color="#66BB6A",
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            name="Sixes", y=top10["batter"], x=runs_from_6s,
            orientation="h", marker_color="#EF5350",
        ), row=1, col=2)

        title = f"Batting Stats — {params.format or 'All'}"
        if params.season:
            title += f" ({params.season})"
        if params.phase:
            title += f" | {params.phase.title()}"

        fig.update_layout(
            title=title,
            barmode="stack",
            height=550,
            legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        )
        fig.update_xaxes(title_text="Strike Rate", row=1, col=1)
        fig.update_yaxes(title_text="Average", row=1, col=1)
        fig.update_xaxes(title_text="Runs", row=1, col=2)
        fig.update_yaxes(autorange="reversed", row=1, col=2)

        return fig

    def _single_player_plot(self, df, params):
        """Detailed view when a single player is selected."""
        row = df.iloc[0]
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.45, 0.55],
            specs=[[{"type": "domain"}, {"type": "xy"}]],
            subplot_titles=["Run Sources", "Key Stats"],
        )

        # Pie: where runs come from
        runs_4s = int(row["total_fours"]) * 4
        runs_6s = int(row["total_sixes"]) * 6
        other = int(row["total_runs"]) - runs_4s - runs_6s
        fig.add_trace(go.Pie(
            labels=["From 4s", "From 6s", "Running"],
            values=[runs_4s, runs_6s, other],
            marker_colors=["#66BB6A", "#EF5350", "#42A5F5"],
            hole=0.45, textinfo="label+percent",
        ), row=1, col=1)

        # Horizontal bar: key metrics
        metrics = ["Average", "Strike Rate", "Boundary %", "Dot %"]
        vals = [float(row["average"] or 0), float(row["strike_rate"] or 0),
                float(row["boundary_pct"] or 0), float(row["dot_pct"] or 0)]
        colors = ["#4CAF50", "#FF9800", "#E91E63", "#9E9E9E"]

        fig.add_trace(go.Bar(
            y=metrics, x=vals, orientation="h",
            marker_color=colors,
            text=[f"{v}" for v in vals], textposition="outside",
            showlegend=False,
        ), row=1, col=2)

        fig.update_layout(
            title=f"{row['batter']} — {int(row['total_runs'])} runs, {int(row['innings'])} inn, "
                  f"{int(row.get('not_outs', 0))} NO, HS: {int(row['highest_score'])}",
            height=400,
        )
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        return fig
