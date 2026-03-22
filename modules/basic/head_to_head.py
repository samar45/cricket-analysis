"""Module B4 — Head-to-Head Matchup Analysis.

Batter vs bowler: runs, balls, dismissals, SR, dot ball %, economy.
Use player= for the batter, player2= for the bowler (both optional — set
one to get their full record vs all opponents, or both for a specific duel).
"""

import pandas as pd
import plotly.graph_objects as go

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class HeadToHead(BaseModule):
    module_id = "B4"
    module_name = "Head-to-Head Matchup"
    category = "basic"
    supported_filters = frozenset({"format", "player", "player2", "season"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

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
                * 100.0 / NULLIF(COUNT(*), 0),
                2
            ) AS dot_pct,
            ROUND(
                SUM(d.runs_batter) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0),
                2
            ) AS bowler_economy
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} {batter_clause} {bowler_clause}
        GROUP BY d.batter, d.bowler
        HAVING COUNT(*) >= 6
        ORDER BY runs_scored DESC
        LIMIT 50
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None
        top = df.head(20)

        # Bubble chart: x=balls, y=runs, size=dismissals, colour=SR
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=top["balls_faced"],
            y=top["runs_scored"],
            mode="markers+text",
            marker=dict(
                size=top["dismissals"].clip(lower=1) * 8,
                color=top["batter_sr"],
                colorscale="RdYlGn",
                showscale=True,
                colorbar=dict(title="Batter SR"),
            ),
            text=top["batter"] + " vs " + top["bowler"],
            textposition="top center",
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Balls: %{x}<br>Runs: %{y}<br>"
                "Dismissals: %{marker.size}<br>"
                "<extra></extra>"
            ),
        ))
        title = "Head-to-Head Matchups"
        if params.player:
            title = f"{params.player} vs " + (params.player2 or "All Bowlers")
        fig.update_layout(
            title=title,
            xaxis_title="Balls Faced",
            yaxis_title="Runs Scored",
            height=500,
        )
        return fig
