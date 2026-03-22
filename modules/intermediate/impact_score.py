"""Module I3 — Player Impact Score.

Composite score that blends batting and bowling contributions
into a single "impact" number per player per match, then aggregated.

Impact formula (weighted):
  batting_impact  = runs * (SR / 100) * 0.6
  bowling_impact  = wickets * 20 + max(8 - economy, 0) * overs * 0.4
  overall_impact  = batting_impact + max(bowling_impact, 0)
"""

import pandas as pd
import plotly.graph_objects as go

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class ImpactScore(BaseModule):
    module_id = "I3"
    module_name = "Player Impact Score"
    category = "intermediate"
    supported_filters = frozenset({"format", "player", "team", "season"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND (d.batter ILIKE ? OR d.bowler ILIKE ?)"
            values.extend([f"%{params.player}%", f"%{params.player}%"])

        all_values = values + values
        sql = f"""
        WITH bat AS (
            SELECT
                d.batter AS player, d.match_id,
                SUM(d.runs_batter) AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS balls
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
            GROUP BY d.batter, d.match_id
        ),
        bowl AS (
            SELECT
                d.bowler AS player, d.match_id,
                SUM(CASE WHEN d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
                    THEN 1 ELSE 0 END) AS wickets,
                SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                    THEN d.runs_total ELSE 0 END) AS runs_conceded,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
            GROUP BY d.bowler, d.match_id
        ),
        combined AS (
            SELECT
                COALESCE(bat.player, bowl.player) AS player,
                COALESCE(bat.match_id, bowl.match_id) AS match_id,
                COALESCE(bat.runs, 0) AS runs,
                COALESCE(bat.balls, 0) AS balls,
                COALESCE(bowl.wickets, 0) AS wickets,
                COALESCE(bowl.runs_conceded, 0) AS runs_conceded,
                COALESCE(bowl.legal_balls, 0) AS legal_balls
            FROM bat
            FULL OUTER JOIN bowl ON bat.player = bowl.player AND bat.match_id = bowl.match_id
        )
        SELECT
            player,
            COUNT(DISTINCT match_id) AS matches,
            SUM(runs) AS total_runs,
            SUM(wickets) AS total_wickets,
            ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 1) AS batting_sr,
            ROUND(SUM(runs_conceded) * 6.0 / NULLIF(SUM(legal_balls), 0), 2) AS economy,
            ROUND(SUM(
                runs * (runs * 1.0 / NULLIF(balls, 0)) * 0.6
                + GREATEST(wickets * 20.0
                    + GREATEST(8 - (runs_conceded * 6.0 / NULLIF(legal_balls, 1)), 0)
                    * (legal_balls / 6.0) * 0.4, 0)
            ) / NULLIF(COUNT(DISTINCT match_id), 0), 2) AS avg_impact,
            ROUND(SUM(
                runs * (runs * 1.0 / NULLIF(balls, 0)) * 0.6
                + GREATEST(wickets * 20.0
                    + GREATEST(8 - (runs_conceded * 6.0 / NULLIF(legal_balls, 1)), 0)
                    * (legal_balls / 6.0) * 0.4, 0)
            ), 1) AS total_impact
        FROM combined
        GROUP BY player
        HAVING COUNT(DISTINCT match_id) >= 3
        ORDER BY total_impact DESC
        LIMIT 30
        """
        return query(sql, all_values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        top = df.head(20).copy()
        for col in ("avg_impact", "total_impact"):
            if col in top.columns:
                top[col] = pd.to_numeric(top[col], errors="coerce").fillna(0)

        # Horizontal bar: total impact, colored by batting/bowling split
        fig = go.Figure()

        # Batting contribution bar
        bat_impact = (top["total_runs"] * top["batting_sr"].fillna(0) / 100 * 0.6).round(1)
        bowl_impact = (top["total_impact"] - bat_impact).clip(lower=0).round(1)

        fig.add_trace(go.Bar(
            name="Batting Impact",
            y=top["player"], x=bat_impact,
            orientation="h", marker_color="#4CAF50",
        ))
        fig.add_trace(go.Bar(
            name="Bowling Impact",
            y=top["player"], x=bowl_impact,
            orientation="h", marker_color="#2196F3",
        ))

        # Annotate avg impact on right
        for _, row in top.iterrows():
            fig.add_annotation(
                x=float(row["total_impact"]) + max(top["total_impact"]) * 0.03,
                y=row["player"],
                text=f"avg {row['avg_impact']}",
                showarrow=False,
                font=dict(size=10, color="#aaa"),
            )

        fig.update_layout(
            title="Player Impact Score — Batting vs Bowling Contribution",
            barmode="stack",
            yaxis=dict(autorange="reversed"),
            xaxis_title="Total Impact Score",
            height=max(400, len(top) * 30),
            legend=dict(x=0.7, y=0.01),
        )
        return fig
