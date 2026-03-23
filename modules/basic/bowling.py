"""Module B2 — Bowling Scorecard & Career Stats.

Wickets, economy rate, bowling average, best bowling figures.
Filterable by: format, season, opposition, phase.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
        phase_clause = self._phase_clause(params, "d")

        player_clause = ""
        if params.player:
            player_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player}%")

        sql = f"""
        WITH bowling_innings AS (
            SELECT
                d.bowler,
                d.match_id,
                COUNT(DISTINCT d.over_num) AS overs,
                SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes', 'legbyes')), 0) AS runs_conceded,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')) AS wickets,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dot_balls,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours_conceded,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes_conceded,
                COUNT(*) AS total_balls,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls,
                SUM(d.runs_extras) FILTER (WHERE d.extra_type = 'wides') AS wides,
                SUM(d.runs_extras) FILTER (WHERE d.extra_type = 'noballs') AS noballs
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
            ROUND((SUM(fours_conceded) + SUM(sixes_conceded)) * 100.0 / NULLIF(SUM(legal_balls), 0), 1) AS boundary_pct,
            SUM(fours_conceded) AS total_fours_conceded,
            SUM(sixes_conceded) AS total_sixes_conceded,
            MAX(wickets) AS best_wickets_in_match,
            COALESCE(SUM(wides), 0) AS total_wides,
            COALESCE(SUM(noballs), 0) AS total_noballs
        FROM bowling_innings
        GROUP BY bowler
        ORDER BY total_wickets DESC
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        top = df.head(15).copy()

        # ── Single player view
        if params.player and len(top) <= 3:
            return self._single_bowler_plot(top, params)

        # ── Multi-bowler: scatter (economy vs SR) + stacked bar (dot% vs boundary%)
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.55, 0.45],
            subplot_titles=[
                "Economy vs Strike Rate (bubble = wickets)",
                "Control Profile — Top 10"
            ],
        )

        # Left: scatter — x=economy, y=bowling SR, size=wickets, color=dot%
        fig.add_trace(go.Scatter(
            x=top["economy"], y=top["bowling_strike_rate"],
            mode="markers+text",
            marker=dict(
                size=top["total_wickets"].clip(lower=3) * 1.2,
                color=top["dot_ball_pct"],
                colorscale="Blues",
                showscale=True,
                colorbar=dict(title="Dot %", x=0.47, len=0.8),
                line=dict(width=1, color="#333"),
            ),
            text=top["bowler"].str.split().str[-1],
            textposition="top center",
            textfont=dict(size=9),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Econ: %{x}<br>SR: %{y}<br>"
                "Wkts: %{marker.size}<extra></extra>"
            ),
            showlegend=False,
        ), row=1, col=1)

        # Add "ideal zone" rectangle (low economy, low SR = top-left)
        fig.add_shape(
            type="rect",
            x0=min(top["economy"]) - 0.5, y0=min(top["bowling_strike_rate"].dropna()) - 2,
            x1=top["economy"].median(), y1=top["bowling_strike_rate"].dropna().median(),
            fillcolor="rgba(76, 175, 80, 0.1)", line=dict(color="rgba(76, 175, 80, 0.3)"),
            row=1, col=1,
        )

        # Right: dual horizontal bar — dot ball % (blue) vs boundary % (red)
        top10 = top.head(10)
        fig.add_trace(go.Bar(
            name="Dot Ball %", y=top10["bowler"], x=top10["dot_ball_pct"],
            orientation="h", marker_color="#42A5F5",
            text=[f"{v}%" for v in top10["dot_ball_pct"]], textposition="outside",
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            name="Boundary %", y=top10["bowler"], x=-top10["boundary_pct"],
            orientation="h", marker_color="#EF5350",
            text=[f"{v}%" for v in top10["boundary_pct"]], textposition="outside",
        ), row=1, col=2)

        title = f"Bowling Stats — {params.format or 'All'}"
        if params.season:
            title += f" ({params.season})"
        if params.phase:
            title += f" | {params.phase.title()}"

        fig.update_layout(
            title=title, barmode="overlay",
            height=550,
            legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        )
        fig.update_xaxes(title_text="Economy Rate", row=1, col=1)
        fig.update_yaxes(title_text="Bowling Strike Rate", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_xaxes(
            title_text="Dot % vs Boundary %", row=1, col=2,
            zeroline=True, zerolinewidth=2, zerolinecolor="#666",
        )

        return fig

    def _single_bowler_plot(self, df, params):
        """Rich breakdown for a single bowler."""
        row = df.iloc[0]
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.45, 0.55],
            specs=[[{"type": "domain"}, {"type": "xy"}]],
            subplot_titles=["Ball Outcomes", "Key Bowling Metrics"],
        )

        # Pie: ball outcomes
        dots = int(row.get("dot_ball_pct", 0) * int(row.get("innings", 0)) * 24 / 100) if row.get("dot_ball_pct") else 0
        fours = int(row.get("total_fours_conceded", 0))
        sixes = int(row.get("total_sixes_conceded", 0))
        wkts = int(row.get("total_wickets", 0))
        other = max(0, int(row.get("innings", 0)) * 24 - dots - fours - sixes - wkts)

        fig.add_trace(go.Pie(
            labels=["Dot Balls", "Fours", "Sixes", "Wickets", "Other"],
            values=[dots, fours, sixes, wkts, other],
            marker_colors=["#90CAF9", "#66BB6A", "#EF5350", "#FF6F00", "#E0E0E0"],
            hole=0.45, textinfo="label+percent",
        ), row=1, col=1)

        # Key metrics bar
        metrics = ["Economy", "Bowling Avg", "Strike Rate", "Dot %", "Boundary %"]
        vals = [float(row.get("economy", 0) or 0), float(row.get("bowling_average", 0) or 0),
                float(row.get("bowling_strike_rate", 0) or 0),
                float(row.get("dot_ball_pct", 0) or 0), float(row.get("boundary_pct", 0) or 0)]
        colors = ["#FF9800", "#4CAF50", "#2196F3", "#42A5F5", "#EF5350"]

        fig.add_trace(go.Bar(
            y=metrics, x=vals, orientation="h",
            marker_color=colors,
            text=[f"{v}" for v in vals], textposition="outside",
            showlegend=False,
        ), row=1, col=2)

        fig.update_layout(
            title=f"{row['bowler']} — {int(row['total_wickets'])} wkts, "
                  f"Econ {row['economy']}, {int(row['innings'])} inn",
            height=400,
        )
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        return fig
