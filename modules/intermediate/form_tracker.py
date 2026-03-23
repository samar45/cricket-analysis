"""Module I4 — Player Form Tracker.

Shows a player's rolling performance over their last N matches,
with rolling average so you can see if they're in form.
Supports both batting and bowling form tracking.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
            ROUND(AVG(runs * 100.0 / NULLIF(balls, 0)) OVER (ORDER BY date ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW), 1)
                AS rolling_sr,
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

        if role == "bowler" and "wickets" in df_plot.columns:
            return self._bowling_form_plot(df_plot, x_axis, window, params)
        return self._batting_form_plot(df_plot, x_axis, window, params)

    def _batting_form_plot(self, df_plot, x_axis, window, params):
        fig = make_subplots(
            rows=2, cols=1, row_heights=[0.65, 0.35],
            shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=[
                f"Runs per Innings ({window}-match rolling avg)",
                "Strike Rate Trend",
            ],
        )

        # Top: Runs bars + rolling avg line
        if "dismissed" in df_plot.columns:
            colors = ["#EF5350" if d else "#4CAF50" for d in df_plot["dismissed"]]
        else:
            colors = "#4CAF50"

        fig.add_trace(go.Bar(
            name="Runs", x=x_axis, y=df_plot["runs"],
            marker_color=colors,
            hovertemplate="Match #%{x}<br>Runs: %{y}<br>vs %{customdata[0]}<extra></extra>",
            customdata=df_plot[["venue"]].values if "venue" in df_plot.columns else None,
        ), row=1, col=1)

        if "rolling_avg" in df_plot.columns:
            fig.add_trace(go.Scatter(
                name=f"{window}-match Avg",
                x=x_axis, y=df_plot["rolling_avg"],
                mode="lines",
                line=dict(color="#FF9800", width=3),
            ), row=1, col=1)

        # Bottom: Strike Rate area
        if "strike_rate" in df_plot.columns:
            fig.add_trace(go.Scatter(
                name="Strike Rate",
                x=x_axis, y=df_plot["strike_rate"],
                mode="lines",
                fill="tozeroy",
                fillcolor="rgba(33, 150, 243, 0.15)",
                line=dict(color="#2196F3", width=2),
            ), row=2, col=1)

            if "rolling_sr" in df_plot.columns:
                fig.add_trace(go.Scatter(
                    name=f"{window}-match Avg SR",
                    x=x_axis, y=df_plot["rolling_sr"],
                    mode="lines",
                    line=dict(color="#E91E63", width=2, dash="dash"),
                ), row=2, col=1)

        # Add milestone markers (50s and 100s)
        if "runs" in df_plot.columns:
            fifties = df_plot[df_plot["runs"] >= 50]
            hundreds = df_plot[df_plot["runs"] >= 100]
            if not fifties.empty:
                x_50 = fifties["match_num"] if "match_num" in fifties.columns else fifties["date"].astype(str)
                fig.add_trace(go.Scatter(
                    name="50+", x=x_50, y=fifties["runs"],
                    mode="markers",
                    marker=dict(size=12, color="#FF9800", symbol="star", line=dict(width=1, color="#333")),
                    showlegend=True,
                ), row=1, col=1)

        fig.update_layout(
            title=f"Batting Form — {params.player or 'Player'}"
                  + " (green = not out, red = out)",
            height=550,
            legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"),
            hovermode="x unified",
        )
        fig.update_xaxes(title_text="Match #", row=2, col=1)
        fig.update_yaxes(title_text="Runs", row=1, col=1)
        fig.update_yaxes(title_text="Strike Rate", row=2, col=1)

        return fig

    def _bowling_form_plot(self, df_plot, x_axis, window, params):
        fig = make_subplots(
            rows=2, cols=1, row_heights=[0.65, 0.35],
            shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=[
                f"Wickets per Match ({window}-match rolling avg)",
                "Economy Rate Trend",
            ],
        )

        # Top: Wickets bars + rolling avg
        wkt_colors = ["#FF6F00" if w >= 3 else "#42A5F5" for w in df_plot["wickets"]]
        fig.add_trace(go.Bar(
            name="Wickets", x=x_axis, y=df_plot["wickets"],
            marker_color=wkt_colors,
            hovertemplate="Match #%{x}<br>Wickets: %{y}<extra></extra>",
        ), row=1, col=1)

        if "rolling_wickets" in df_plot.columns:
            fig.add_trace(go.Scatter(
                name=f"{window}-match Avg Wkts",
                x=x_axis, y=df_plot["rolling_wickets"],
                mode="lines",
                line=dict(color="#FF9800", width=3),
            ), row=1, col=1)

        # Bottom: Economy area
        if "economy" in df_plot.columns:
            fig.add_trace(go.Scatter(
                name="Economy",
                x=x_axis, y=df_plot["economy"],
                mode="lines",
                fill="tozeroy",
                fillcolor="rgba(239, 83, 80, 0.15)",
                line=dict(color="#EF5350", width=2),
            ), row=2, col=1)

            if "rolling_economy" in df_plot.columns:
                fig.add_trace(go.Scatter(
                    name=f"{window}-match Avg Econ",
                    x=x_axis, y=df_plot["rolling_economy"],
                    mode="lines",
                    line=dict(color="#333", width=2, dash="dash"),
                ), row=2, col=1)

        # 3-wicket haul markers
        hauls = df_plot[df_plot["wickets"] >= 3]
        if not hauls.empty:
            x_h = hauls["match_num"] if "match_num" in hauls.columns else hauls["date"].astype(str)
            fig.add_trace(go.Scatter(
                name="3+ Wickets", x=x_h, y=hauls["wickets"],
                mode="markers",
                marker=dict(size=12, color="#FF6F00", symbol="star", line=dict(width=1, color="#333")),
            ), row=1, col=1)

        fig.update_layout(
            title=f"Bowling Form — {params.player or 'Player'}"
                  + " (orange = 3+ wicket haul)",
            height=550,
            legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"),
            hovermode="x unified",
        )
        fig.update_xaxes(title_text="Match #", row=2, col=1)
        fig.update_yaxes(title_text="Wickets", row=1, col=1)
        fig.update_yaxes(title_text="Economy", row=2, col=1)

        return fig
