"""Module I4 — Player Form Tracker.

Shows a player's rolling performance over their last N innings/matches,
with a rolling 5- and 10-innings average so you can see if they're in form.

Requires a player name (or partial match).
"""

import pandas as pd
import plotly.graph_objects as go

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class FormTracker(BaseModule):
    module_id = "I4"
    module_name = "Player Form Tracker (Rolling Avg)"
    category = "intermediate"
    supported_filters = frozenset({"format", "player", "season"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        if not params.player:
            return pd.DataFrame({"info": ["Please select a player to track form."]})

        where, values = self._build_where_clauses(params, "m")
        values.append(f"%{params.player}%")

        sql = f"""
        WITH innings AS (
            SELECT
                d.batter,
                d.match_id,
                m.date,
                m.format,
                m.season,
                m.venue,
                SUM(d.runs_batter)                                             AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides'))                          AS balls,
                COUNT(*) FILTER (WHERE d.runs_batter = 4)                      AS fours,
                COUNT(*) FILTER (WHERE d.runs_batter = 6)                      AS sixes,
                MAX(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END)       AS was_out
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} AND d.batter ILIKE ?
            GROUP BY d.batter, d.match_id, m.date, m.format, m.season, m.venue
        )
        SELECT
            batter,
            date,
            format,
            season,
            venue,
            runs,
            balls,
            fours,
            sixes,
            was_out,
            ROUND(runs * 100.0 / NULLIF(balls, 0), 1)               AS strike_rate,
            -- Rolling 5-innings average
            ROUND(AVG(runs) OVER (
                PARTITION BY batter ORDER BY date
                ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
            ), 1)                                                    AS rolling_5_avg,
            -- Rolling 10-innings average
            ROUND(AVG(runs) OVER (
                PARTITION BY batter ORDER BY date
                ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
            ), 1)                                                    AS rolling_10_avg
        FROM innings
        ORDER BY date DESC
        LIMIT 50
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty or "date" not in df.columns:
            return None

        df_plot = df.sort_values("date")
        fig = go.Figure()

        # Per-innings bars
        colors = ["#ef5350" if w else "#42a5f5" for w in df_plot["was_out"]]
        fig.add_trace(go.Bar(
            x=df_plot["date"].astype(str), y=df_plot["runs"],
            name="Runs (red=out)",
            marker_color=colors,
        ))

        # Rolling averages
        fig.add_trace(go.Scatter(
            x=df_plot["date"].astype(str), y=df_plot["rolling_5_avg"],
            name="5-innings avg", mode="lines",
            line=dict(color="orange", width=2, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x=df_plot["date"].astype(str), y=df_plot["rolling_10_avg"],
            name="10-innings avg", mode="lines",
            line=dict(color="white", width=2),
        ))

        fig.update_layout(
            title=f"Form Tracker — {params.player or 'Player'}",
            xaxis_title="Date",
            yaxis_title="Runs",
            xaxis_tickangle=-45,
            height=480,
            legend=dict(x=0.01, y=0.99),
        )
        return fig
