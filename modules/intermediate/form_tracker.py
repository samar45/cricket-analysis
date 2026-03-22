"""Module I4 — Player Form Tracker.

Shows a player's rolling performance over their last N matches,
with rolling average so you can see if they're in form.
Supports both batting and bowling form tracking.
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
        role = (params.extra or {}).get("role", "batter")
        window = int((params.extra or {}).get("window", 5))
        if role == "bowler":
            return self._bowling_form(params, window)
        return self._batting_form(params, window)

    def _batting_form(self, params: ModuleParams, window: int) -> pd.DataFrame:
        if not params.player:
            return pd.DataFrame({"info": ["Select a player to track batting form."]})

        where, values = self._build_where_clauses(params, "m")
        values.append(f"%{params.player}%")

        sql = f"""
        WITH innings AS (
            SELECT
                d.batter, d.match_id, m.date, m.season, m.venue,
                SUM(d.runs_batter) AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS balls,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                MAX(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END) AS dismissed
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} AND d.batter ILIKE ?
            GROUP BY d.batter, d.match_id, m.date, m.season, m.venue
        )
        SELECT
            date, season, venue, runs, balls, dismissed,
            fours, sixes,
            ROUND(runs * 100.0 / NULLIF(balls, 0), 1) AS strike_rate,
            ROUND(AVG(runs) OVER (ORDER BY date ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW), 1)
                AS rolling_avg,
            ROW_NUMBER() OVER (ORDER BY date) AS match_num
        FROM innings
        ORDER BY date
        """
        return query(sql, values)

    def _bowling_form(self, params: ModuleParams, window: int) -> pd.DataFrame:
        if not params.player:
            return pd.DataFrame({"info": ["Select a player to track bowling form."]})

        where, values = self._build_where_clauses(params, "m")
        values.append(f"%{params.player}%")

        sql = f"""
        WITH spells AS (
            SELECT
                d.bowler, d.match_id, m.date, m.season, m.venue,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                    AS wickets,
                SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                    THEN d.runs_total ELSE 0 END) AS runs_conceded,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls,
                COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} AND d.bowler ILIKE ?
            GROUP BY d.bowler, d.match_id, m.date, m.season, m.venue
        )
        SELECT
            date, season, venue,
            wickets,
            runs_conceded,
            ROUND(legal_balls / 6.0, 1) AS overs,
            ROUND(runs_conceded * 6.0 / NULLIF(legal_balls, 0), 2) AS economy,
            dots,
            ROUND(dots * 100.0 / NULLIF(legal_balls, 0), 1) AS dot_pct,
            ROUND(AVG(wickets) OVER (ORDER BY date ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW), 2)
                AS rolling_wickets,
            ROUND(AVG(runs_conceded * 6.0 / NULLIF(legal_balls, 0))
                OVER (ORDER BY date ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW), 2)
                AS rolling_economy,
            ROW_NUMBER() OVER (ORDER BY date) AS match_num
        FROM spells
        ORDER BY date
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        role = (params.extra or {}).get("role", "batter")
        window = int((params.extra or {}).get("window", 5))

        if df.empty or "date" not in df.columns:
            return None

        df_plot = df.sort_values("date").copy()
        x_axis = df_plot["match_num"] if "match_num" in df_plot.columns else df_plot["date"].astype(str)

        fig = go.Figure()

        if role == "bowler" and "wickets" in df_plot.columns:
            # Bowling form: wickets bars + rolling economy line
            fig.add_trace(go.Bar(
                name="Wickets", x=x_axis, y=df_plot["wickets"],
                marker_color="#2196F3", yaxis="y",
                text=df_plot["wickets"], textposition="outside",
            ))
            if "rolling_economy" in df_plot.columns:
                fig.add_trace(go.Scatter(
                    name=f"{window}-match Avg Economy", x=x_axis,
                    y=df_plot["rolling_economy"],
                    mode="lines+markers", yaxis="y2",
                    line=dict(color="#FF5722", width=2.5),
                    marker=dict(size=6),
                ))
            fig.update_layout(
                title=f"Bowling Form — {params.player or 'Player'}",
                xaxis_title="Match #", yaxis=dict(title="Wickets"),
                yaxis2=dict(title="Economy", overlaying="y", side="right"),
            )
        else:
            # Batting form: runs bars (colored by out/not-out) + rolling avg line
            if "dismissed" in df_plot.columns:
                colors = ["#F44336" if d else "#4CAF50" for d in df_plot["dismissed"]]
            else:
                colors = "#4CAF50"

            fig.add_trace(go.Bar(
                name="Runs", x=x_axis, y=df_plot["runs"],
                marker_color=colors, yaxis="y",
                text=df_plot["runs"], textposition="outside",
            ))
            if "rolling_avg" in df_plot.columns:
                fig.add_trace(go.Scatter(
                    name=f"{window}-match Avg", x=x_axis,
                    y=df_plot["rolling_avg"],
                    mode="lines+markers", yaxis="y",
                    line=dict(color="#FF9800", width=2.5),
                    marker=dict(size=6),
                ))
            fig.update_layout(
                title=f"Batting Form — {params.player or 'Player'}"
                      + (" (green = not out, red = out)" if "dismissed" in df_plot.columns else ""),
                xaxis_title="Match #", yaxis=dict(title="Runs"),
            )

        fig.update_layout(
            height=450,
            legend=dict(x=0.01, y=0.99),
            hovermode="x unified",
        )
        return fig
