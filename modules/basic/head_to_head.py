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

        top = df.head(15).copy()
        top["label"] = top["batter"] + " vs " + top["bowler"]

        # Grouped horizontal bar: Runs (green) + Dismissals (red)
        fig = go.Figure()

        fig.add_trace(go.Bar(
            name="Runs",
            y=top["label"], x=top["runs_scored"],
            orientation="h", marker_color="#4CAF50",
            text=top["runs_scored"], textposition="outside",
        ))

        fig.add_trace(go.Bar(
            name="Dismissals",
            y=top["label"], x=top["dismissals"],
            orientation="h", marker_color="#F44336",
            text=top["dismissals"], textposition="outside",
        ))

        # Add SR as annotation on right
        for i, row in top.iterrows():
            fig.add_annotation(
                x=max(top["runs_scored"]) * 1.15,
                y=row["label"],
                text=f"SR {row['batter_sr']}",
                showarrow=False,
                font=dict(size=11, color="#aaa"),
            )

        title = "Head-to-Head: Runs & Dismissals"
        if params.player and params.player2:
            title = f"{params.player} vs {params.player2}"
        elif params.player:
            title = f"{params.player} vs All Bowlers"

        fig.update_layout(
            title=title,
            barmode="group",
            yaxis=dict(autorange="reversed"),
            xaxis_title="Count",
            height=max(400, len(top) * 35),
            legend=dict(x=0.7, y=0.01),
            margin=dict(r=80),
        )
        return fig
