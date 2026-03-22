"""Module I3 — Player Impact Score.

Composite score that blends batting and bowling contributions
into a single "impact" number per player per match, then aggregated.

Impact formula (weighted):
  batting_impact  = runs × (SR / 100) × 0.6
  bowling_impact  = wickets × 20 + (8 - economy) × overs × 0.4   [economy capped]
  overall_impact  = batting_impact + max(bowling_impact, 0)

Great for identifying all-rounders and players who contribute
beyond raw runs / wickets.
"""

import pandas as pd
import plotly.express as px

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

        # Both bat and bowl CTEs use {where} + {player_clause} → duplicate values
        all_values = values + values
        sql = f"""
        WITH bat AS (
            SELECT
                d.batter AS player,
                d.match_id,
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
                d.bowler AS player,
                d.match_id,
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
            ) / NULLIF(COUNT(DISTINCT match_id), 0), 2) AS avg_impact_per_match,
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
        # Fix NaN values that crash Plotly scatter size/color
        for col in ("avg_impact_per_match", "total_impact"):
            if col in top.columns:
                top[col] = pd.to_numeric(top[col], errors="coerce").fillna(0)
        # Need non-zero sizes for scatter — use runs as fallback
        if top["avg_impact_per_match"].sum() == 0:
            top["avg_impact_per_match"] = top["total_runs"].clip(lower=1)
        fig = px.scatter(
            top,
            x="total_runs", y="total_wickets",
            size="avg_impact_per_match",
            color="total_impact",
            hover_name="player",
            color_continuous_scale="Viridis",
            title="Player Impact: Runs vs Wickets (bubble = avg impact/match)",
            labels={
                "total_runs": "Total Runs",
                "total_wickets": "Total Wickets",
                "total_impact": "Total Impact",
            },
        )
        fig.update_layout(height=500)
        return fig
