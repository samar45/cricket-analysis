"""Module B4 — Head-to-Head Matchup Analysis.

Batter vs bowler: runs, balls, dismissals, SR, dot ball %, economy.
Use player= for the batter, player2= for the bowler (both optional — set
one to get their full record vs all opponents, or both for a specific duel).
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class HeadToHead(BaseModule):
    module_id = "B4"
    module_name = "Head-to-Head Matchup"
    category = "basic"
    supported_filters = frozenset({"format", "player", "player2", "season", "venue", "phase"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        phase_clause = self._phase_clause(params, "d")

        batter_clause = ""
        if params.player:
            batter_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        bowler_clause = ""
        if params.player2:
            bowler_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player2}%")

        sql = f"""
        SELECT
            d.batter,
            d.bowler,
            COUNT(*) FILTER (WHERE d.extra_type IS NULL OR d.extra_type NOT IN ('wides'))
                AS balls_faced,
            SUM(d.runs_batter) AS runs_scored,
            COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out')
                AND d.player_out = d.batter)
                AS dismissals,
            COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                AS dot_balls,
            COUNT(*) FILTER (WHERE d.runs_batter = 1) AS singles,
            COUNT(*) FILTER (WHERE d.runs_batter = 2) AS doubles,
            COUNT(*) FILTER (WHERE d.runs_batter = 3) AS triples,
            COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
            COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
            ROUND(
                SUM(d.runs_batter) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0),
                2
            ) AS batter_sr,
            ROUND(
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0),
                2
            ) AS dot_pct,
            ROUND(
                (COUNT(*) FILTER (WHERE d.runs_batter = 4) + COUNT(*) FILTER (WHERE d.runs_batter = 6))
                * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0),
                2
            ) AS boundary_pct,
            ROUND(
                SUM(d.runs_batter) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0),
                2
            ) AS bowler_economy
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} {batter_clause} {bowler_clause} {phase_clause}
        GROUP BY d.batter, d.bowler
        HAVING COUNT(*) >= 6
        ORDER BY runs_scored DESC
        LIMIT 50
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        top = df.head(12).copy()
        top["label"] = top["batter"] + " vs " + top["bowler"]

        # ── Specific matchup: radar-style breakdown
        if params.player and params.player2 and len(top) == 1:
            return self._single_matchup_plot(top.iloc[0], params)

        # ── Multi-matchup: stacked bar showing runs composition + line for SR
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Stacked bar: dots, singles, doubles/triples, fours, sixes
        fig.add_trace(go.Bar(
            name="Dots", y=top["label"], x=top["dot_balls"],
            orientation="h", marker_color="#E0E0E0",
            hovertemplate="%{y}<br>Dots: %{x}<extra></extra>",
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            name="Singles", y=top["label"], x=top["singles"],
            orientation="h", marker_color="#90CAF9",
            hovertemplate="%{y}<br>Singles: %{x}<extra></extra>",
        ), secondary_y=False)

        twos_threes = top["doubles"] + top["triples"]
        fig.add_trace(go.Bar(
            name="2s & 3s", y=top["label"], x=twos_threes,
            orientation="h", marker_color="#FFB74D",
            hovertemplate="%{y}<br>2s & 3s: %{x}<extra></extra>",
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            name="Fours", y=top["label"], x=top["fours"],
            orientation="h", marker_color="#66BB6A",
            hovertemplate="%{y}<br>Fours: %{x}<extra></extra>",
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            name="Sixes", y=top["label"], x=top["sixes"],
            orientation="h", marker_color="#EF5350",
            hovertemplate="%{y}<br>Sixes: %{x}<extra></extra>",
        ), secondary_y=False)

        # Line: Strike Rate on secondary axis
        fig.add_trace(go.Scatter(
            name="Strike Rate",
            y=top["label"], x=top["batter_sr"],
            mode="markers+text",
            marker=dict(size=10, color="#FF6F00", symbol="diamond"),
            text=[f"{sr}" for sr in top["batter_sr"]],
            textposition="middle right",
            textfont=dict(size=10, color="#FF6F00"),
            hovertemplate="%{y}<br>SR: %{x}<extra></extra>",
        ), secondary_y=True)

        title = "Head-to-Head: Ball-by-Ball Breakdown"
        if params.player:
            title = f"{params.player} — Scoring Breakdown vs Bowlers"
        elif params.player2:
            title = f"Batters vs {params.player2} — Scoring Breakdown"

        fig.update_layout(
            title=title,
            barmode="stack",
            yaxis=dict(autorange="reversed"),
            xaxis_title="Balls",
            height=max(450, len(top) * 42),
            legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
            margin=dict(r=100),
            hovermode="y unified",
        )
        fig.update_yaxes(title_text="Strike Rate", secondary_y=True)

        return fig

    def _single_matchup_plot(self, row, params):
        """Rich visual for a specific batter vs bowler matchup."""
        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.55, 0.45],
            specs=[[{"type": "domain"}, {"type": "xy"}]],
            subplot_titles=["Scoring Wheel", "Key Numbers"],
        )

        # Donut chart: run distribution
        labels = ["Dots", "Singles", "Doubles", "Triples", "Fours", "Sixes"]
        vals = [int(row["dot_balls"]), int(row["singles"]), int(row["doubles"]),
                int(row["triples"]), int(row["fours"]), int(row["sixes"])]
        colors = ["#E0E0E0", "#90CAF9", "#FFB74D", "#CE93D8", "#66BB6A", "#EF5350"]

        fig.add_trace(go.Pie(
            labels=labels, values=vals,
            marker_colors=colors, hole=0.5,
            textinfo="label+value",
            hovertemplate="%{label}: %{value} balls (%{percent})<extra></extra>",
        ), row=1, col=1)

        # Key stats as indicator-style bars
        metrics = ["Runs", "Balls", "SR", "Boundary %", "Dot %"]
        metric_vals = [
            float(row["runs_scored"]), float(row["balls_faced"]),
            float(row["batter_sr"]), float(row["boundary_pct"]), float(row["dot_pct"])
        ]
        bar_colors = ["#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9E9E9E"]

        fig.add_trace(go.Bar(
            y=metrics, x=metric_vals, orientation="h",
            marker_color=bar_colors,
            text=[f"{v}" for v in metric_vals],
            textposition="outside",
            showlegend=False,
        ), row=1, col=2)

        fig.update_layout(
            title=f"{params.player} vs {params.player2}  |  {int(row['runs_scored'])} runs off {int(row['balls_faced'])} balls  |  {int(row['dismissals'])} dismissals",
            height=420,
            showlegend=True,
            legend=dict(orientation="h", y=-0.1, x=0.25, xanchor="center"),
        )
        fig.update_xaxes(showgrid=False, row=1, col=2)
        fig.update_yaxes(autorange="reversed", row=1, col=2)

        return fig
