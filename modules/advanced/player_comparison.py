"""Module A4 — Player vs Player Comparison.

Side-by-side comparison of two batters or two bowlers
with radar charts, stat tables, and phase breakdowns.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class PlayerComparison(BaseModule):
    module_id = "A4"
    module_name = "Player vs Player Comparison"
    category = "advanced"
    supported_filters = frozenset({"format", "player", "player2", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        role = (params.extra or {}).get("role", "batter")
        if role == "bowler":
            return self._bowler_comparison(params)
        return self._batter_comparison(params)

    def _batter_comparison(self, params: ModuleParams) -> pd.DataFrame:
        if not params.player or not params.player2:
            return pd.DataFrame({"info": ["Select two batters to compare."]})

        where, values = self._build_where_clauses(params, "m")

        players = [params.player, params.player2]
        player_clauses = "AND d.batter ILIKE ?"
        all_values = []

        rows = []
        for p in players:
            v = list(values) + [f"%{p}%"]
            sql = f"""
            WITH phase_stats AS (
                SELECT
                    d.batter,
                    CASE
                        WHEN d.over_num BETWEEN 0 AND 5   THEN 'powerplay'
                        WHEN d.over_num BETWEEN 6 AND 14  THEN 'middle'
                        ELSE 'death'
                    END AS phase,
                    SUM(d.runs_batter) AS runs,
                    COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')) AS balls,
                    COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                    COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                    COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots,
                    MAX(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END) AS was_out
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {where} {player_clauses}
                GROUP BY d.batter, phase, d.match_id
            )
            SELECT
                batter,
                COUNT(*) AS innings,
                SUM(runs) AS total_runs,
                MAX(runs) AS highest_score,
                ROUND(SUM(runs) * 1.0 / NULLIF(SUM(was_out), 0), 2) AS average,
                ROUND(SUM(runs) * 100.0 / NULLIF(SUM(balls), 0), 2) AS strike_rate,
                SUM(fours) AS fours,
                SUM(sixes) AS sixes,
                ROUND((SUM(fours) + SUM(sixes)) * 100.0 / NULLIF(SUM(balls), 0), 1) AS boundary_pct,
                ROUND(SUM(dots) * 100.0 / NULLIF(SUM(balls), 0), 1) AS dot_pct,
                -- Phase SR
                ROUND(SUM(runs) FILTER (WHERE phase = 'powerplay') * 100.0
                    / NULLIF(SUM(balls) FILTER (WHERE phase = 'powerplay'), 0), 1) AS sr_powerplay,
                ROUND(SUM(runs) FILTER (WHERE phase = 'middle') * 100.0
                    / NULLIF(SUM(balls) FILTER (WHERE phase = 'middle'), 0), 1) AS sr_middle,
                ROUND(SUM(runs) FILTER (WHERE phase = 'death') * 100.0
                    / NULLIF(SUM(balls) FILTER (WHERE phase = 'death'), 0), 1) AS sr_death,
                SUM(CASE WHEN runs >= 50 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN runs = 0 AND was_out = 1 THEN 1 ELSE 0 END) AS ducks
            FROM phase_stats
            GROUP BY batter
            """
            result = query(sql, v)
            if not result.empty:
                rows.append(result.iloc[0])

        if not rows:
            return pd.DataFrame({"info": ["No data found for selected players."]})
        return pd.DataFrame(rows)

    def _bowler_comparison(self, params: ModuleParams) -> pd.DataFrame:
        if not params.player or not params.player2:
            return pd.DataFrame({"info": ["Select two bowlers to compare."]})

        where, values = self._build_where_clauses(params, "m")
        player_clauses = "AND d.bowler ILIKE ?"

        rows = []
        for p in [params.player, params.player2]:
            v = list(values) + [f"%{p}%"]
            sql = f"""
            WITH phase_stats AS (
                SELECT
                    d.bowler,
                    CASE
                        WHEN d.over_num BETWEEN 0 AND 5   THEN 'powerplay'
                        WHEN d.over_num BETWEEN 6 AND 14  THEN 'middle'
                        ELSE 'death'
                    END AS phase,
                    d.match_id,
                    SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0)
                        AS runs_conceded,
                    COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls,
                    COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                        AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                        AS wickets,
                    COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots,
                    COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours_conceded,
                    COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes_conceded
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {where} {player_clauses}
                GROUP BY d.bowler, phase, d.match_id
            )
            SELECT
                bowler,
                COUNT(DISTINCT match_id) AS innings,
                SUM(wickets) AS total_wickets,
                SUM(runs_conceded) AS total_runs_conceded,
                ROUND(SUM(runs_conceded) * 1.0 / NULLIF(SUM(wickets), 0), 2) AS bowling_average,
                ROUND(SUM(runs_conceded) * 6.0 / NULLIF(SUM(legal_balls), 0), 2) AS economy,
                ROUND(SUM(legal_balls) * 1.0 / NULLIF(SUM(wickets), 0), 2) AS strike_rate,
                ROUND(SUM(dots) * 100.0 / NULLIF(SUM(legal_balls), 0), 1) AS dot_pct,
                ROUND((SUM(fours_conceded) + SUM(sixes_conceded)) * 100.0
                    / NULLIF(SUM(legal_balls), 0), 1) AS boundary_pct,
                -- Phase economy
                ROUND(SUM(runs_conceded) FILTER (WHERE phase = 'powerplay') * 6.0
                    / NULLIF(SUM(legal_balls) FILTER (WHERE phase = 'powerplay'), 0), 2) AS econ_powerplay,
                ROUND(SUM(runs_conceded) FILTER (WHERE phase = 'middle') * 6.0
                    / NULLIF(SUM(legal_balls) FILTER (WHERE phase = 'middle'), 0), 2) AS econ_middle,
                ROUND(SUM(runs_conceded) FILTER (WHERE phase = 'death') * 6.0
                    / NULLIF(SUM(legal_balls) FILTER (WHERE phase = 'death'), 0), 2) AS econ_death,
                MAX(wickets) AS best_wickets
            FROM phase_stats
            GROUP BY bowler
            """
            result = query(sql, v)
            if not result.empty:
                rows.append(result.iloc[0])

        if not rows:
            return pd.DataFrame({"info": ["No data found for selected bowlers."]})
        return pd.DataFrame(rows)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty or "info" in df.columns or len(df) < 2:
            return None

        role = (params.extra or {}).get("role", "batter")
        if role == "bowler":
            return self._bowler_radar(df, params)
        return self._batter_radar(df, params)

    def _batter_radar(self, df, params):
        p1, p2 = df.iloc[0], df.iloc[1]

        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.45, 0.55],
            specs=[[{"type": "polar"}, {"type": "xy"}]],
            subplot_titles=["Performance Radar", "Phase-wise Strike Rate"],
        )

        # Radar chart: normalize stats to 0-100 scale
        categories = ["Average", "Strike Rate", "Boundary %", "100-Dot %", "PP SR", "Death SR"]

        def safe(val, default=0):
            try:
                v = float(val)
                return v if not pd.isna(v) else default
            except (TypeError, ValueError):
                return default

        def normalize(vals, maxvals):
            return [min(v / m * 100, 100) if m > 0 else 0 for v, m in zip(vals, maxvals)]

        p1_raw = [safe(p1.get("average")), safe(p1.get("strike_rate")),
                   safe(p1.get("boundary_pct")), 100 - safe(p1.get("dot_pct")),
                   safe(p1.get("sr_powerplay")), safe(p1.get("sr_death"))]
        p2_raw = [safe(p2.get("average")), safe(p2.get("strike_rate")),
                   safe(p2.get("boundary_pct")), 100 - safe(p2.get("dot_pct")),
                   safe(p2.get("sr_powerplay")), safe(p2.get("sr_death"))]

        maxvals = [max(a, b, 1) for a, b in zip(p1_raw, p2_raw)]
        p1_norm = normalize(p1_raw, maxvals)
        p2_norm = normalize(p2_raw, maxvals)

        fig.add_trace(go.Scatterpolar(
            r=p1_norm + [p1_norm[0]], theta=categories + [categories[0]],
            fill="toself", fillcolor="rgba(66, 165, 245, 0.2)",
            line=dict(color="#42A5F5", width=2),
            name=str(p1.get("batter", params.player)),
        ), row=1, col=1)

        fig.add_trace(go.Scatterpolar(
            r=p2_norm + [p2_norm[0]], theta=categories + [categories[0]],
            fill="toself", fillcolor="rgba(239, 83, 80, 0.2)",
            line=dict(color="#EF5350", width=2),
            name=str(p2.get("batter", params.player2)),
        ), row=1, col=1)

        # Right: Phase-wise SR grouped bar
        phases = ["Powerplay", "Middle", "Death"]
        p1_sr = [safe(p1.get("sr_powerplay")), safe(p1.get("sr_middle")), safe(p1.get("sr_death"))]
        p2_sr = [safe(p2.get("sr_powerplay")), safe(p2.get("sr_middle")), safe(p2.get("sr_death"))]

        fig.add_trace(go.Bar(
            name=str(p1.get("batter", params.player)),
            x=phases, y=p1_sr,
            marker_color="#42A5F5",
            text=[f"{v}" for v in p1_sr], textposition="outside",
            showlegend=False,
        ), row=1, col=2)

        fig.add_trace(go.Bar(
            name=str(p2.get("batter", params.player2)),
            x=phases, y=p2_sr,
            marker_color="#EF5350",
            text=[f"{v}" for v in p2_sr], textposition="outside",
            showlegend=False,
        ), row=1, col=2)

        n1 = str(p1.get("batter", params.player))
        n2 = str(p2.get("batter", params.player2))

        fig.update_layout(
            title=f"{n1} vs {n2} — Batting Comparison",
            barmode="group",
            height=480,
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            legend=dict(orientation="h", y=-0.1, x=0.25, xanchor="center"),
        )
        fig.update_yaxes(title_text="Strike Rate", row=1, col=2)

        return fig

    def _bowler_radar(self, df, params):
        p1, p2 = df.iloc[0], df.iloc[1]

        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.45, 0.55],
            specs=[[{"type": "polar"}, {"type": "xy"}]],
            subplot_titles=["Performance Radar", "Phase-wise Economy"],
        )

        categories = ["Wickets/Inn", "100-Economy*10", "Dot %", "100-Boundary %", "PP Control", "Death Control"]

        def safe(val, default=0):
            try:
                v = float(val)
                return v if not pd.isna(v) else default
            except (TypeError, ValueError):
                return default

        def normalize(vals, maxvals):
            return [min(v / m * 100, 100) if m > 0 else 0 for v, m in zip(vals, maxvals)]

        innings1, innings2 = max(safe(p1.get("innings")), 1), max(safe(p2.get("innings")), 1)
        p1_raw = [
            safe(p1.get("total_wickets")) / innings1,
            max(0, 100 - safe(p1.get("economy")) * 10),
            safe(p1.get("dot_pct")),
            100 - safe(p1.get("boundary_pct")),
            max(0, 100 - safe(p1.get("econ_powerplay", 0)) * 10),
            max(0, 100 - safe(p1.get("econ_death", 0)) * 10),
        ]
        p2_raw = [
            safe(p2.get("total_wickets")) / innings2,
            max(0, 100 - safe(p2.get("economy")) * 10),
            safe(p2.get("dot_pct")),
            100 - safe(p2.get("boundary_pct")),
            max(0, 100 - safe(p2.get("econ_powerplay", 0)) * 10),
            max(0, 100 - safe(p2.get("econ_death", 0)) * 10),
        ]

        maxvals = [max(a, b, 0.1) for a, b in zip(p1_raw, p2_raw)]
        p1_norm = normalize(p1_raw, maxvals)
        p2_norm = normalize(p2_raw, maxvals)

        fig.add_trace(go.Scatterpolar(
            r=p1_norm + [p1_norm[0]], theta=categories + [categories[0]],
            fill="toself", fillcolor="rgba(66, 165, 245, 0.2)",
            line=dict(color="#42A5F5", width=2),
            name=str(p1.get("bowler", params.player)),
        ), row=1, col=1)

        fig.add_trace(go.Scatterpolar(
            r=p2_norm + [p2_norm[0]], theta=categories + [categories[0]],
            fill="toself", fillcolor="rgba(239, 83, 80, 0.2)",
            line=dict(color="#EF5350", width=2),
            name=str(p2.get("bowler", params.player2)),
        ), row=1, col=1)

        # Phase economy comparison
        phases = ["Powerplay", "Middle", "Death"]
        p1_econ = [safe(p1.get("econ_powerplay")), safe(p1.get("econ_middle")), safe(p1.get("econ_death"))]
        p2_econ = [safe(p2.get("econ_powerplay")), safe(p2.get("econ_middle")), safe(p2.get("econ_death"))]

        fig.add_trace(go.Bar(
            name=str(p1.get("bowler", params.player)),
            x=phases, y=p1_econ, marker_color="#42A5F5",
            text=[f"{v}" for v in p1_econ], textposition="outside",
            showlegend=False,
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            name=str(p2.get("bowler", params.player2)),
            x=phases, y=p2_econ, marker_color="#EF5350",
            text=[f"{v}" for v in p2_econ], textposition="outside",
            showlegend=False,
        ), row=1, col=2)

        n1 = str(p1.get("bowler", params.player))
        n2 = str(p2.get("bowler", params.player2))

        fig.update_layout(
            title=f"{n1} vs {n2} — Bowling Comparison",
            barmode="group", height=480,
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            legend=dict(orientation="h", y=-0.1, x=0.25, xanchor="center"),
        )
        fig.update_yaxes(title_text="Economy Rate", row=1, col=2)

        return fig
