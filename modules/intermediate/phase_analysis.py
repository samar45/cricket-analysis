"""Module I1 — Phase-by-Phase Analysis.

Breaks innings into Powerplay (0-5), Middle (6-14) and Death (15-19).
Separate views for batting and bowling with role-appropriate stats:
  Batting: runs, balls, strike rate, dismissals, boundary %
  Bowling: overs, runs conceded, wickets, economy, dot ball %
"""

import pandas as pd
import plotly.graph_objects as go

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class PhaseAnalysis(BaseModule):
    module_id = "I1"
    module_name = "Phase Breakdown (PP / Middle / Death)"
    category = "intermediate"
    supported_filters = frozenset({"format", "team", "player", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        role = (params.extra or {}).get("role", "batting")
        if role == "bowling":
            return self._bowling_phase(params)
        return self._batting_phase(params)

    def _batting_phase(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        player_clause = ""
        if params.player:
            player_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        sql = f"""
        SELECT
            CASE
                WHEN d.over_num BETWEEN 0 AND 5   THEN 'Powerplay (1-6)'
                WHEN d.over_num BETWEEN 6 AND 14  THEN 'Middle (7-15)'
                WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (16-20)'
            END AS phase,
            CASE WHEN d.over_num <= 5 THEN 1 WHEN d.over_num <= 14 THEN 2 ELSE 3 END AS phase_order,
            SUM(d.runs_batter)                                            AS runs,
            COUNT(*) FILTER (WHERE d.extra_type IS NULL
                OR d.extra_type NOT IN ('wides'))                         AS balls,
            ROUND(SUM(d.runs_batter) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1)            AS strike_rate,
            COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                AND d.player_out = d.batter)                              AS dismissals,
            COUNT(*) FILTER (WHERE d.runs_batter = 4)                     AS fours,
            COUNT(*) FILTER (WHERE d.runs_batter = 6)                     AS sixes,
            ROUND((COUNT(*) FILTER (WHERE d.runs_batter = 4)
                 + COUNT(*) FILTER (WHERE d.runs_batter = 6)) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1)            AS boundary_pct,
            COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} {player_clause}
            AND d.over_num BETWEEN 0 AND 19
        GROUP BY phase, phase_order
        ORDER BY phase_order
        """
        return query(sql, values)

    def _bowling_phase(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        player_clause = ""
        if params.player:
            player_clause = "AND d.bowler ILIKE ?"
            values.append(f"%{params.player}%")

        sql = f"""
        SELECT
            CASE
                WHEN d.over_num BETWEEN 0 AND 5   THEN 'Powerplay (1-6)'
                WHEN d.over_num BETWEEN 6 AND 14  THEN 'Middle (7-15)'
                WHEN d.over_num BETWEEN 15 AND 19 THEN 'Death (16-20)'
            END AS phase,
            CASE WHEN d.over_num <= 5 THEN 1 WHEN d.over_num <= 14 THEN 2 ELSE 3 END AS phase_order,
            ROUND(COUNT(*) FILTER (WHERE d.extra_type IS NULL) / 6.0, 1) AS overs,
            SUM(d.runs_total)                                             AS runs_conceded,
            COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                                                                          AS wickets,
            ROUND(SUM(d.runs_total) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
            ROUND(
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) * 1.0
                / NULLIF(COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')), 0),
                1)                                                        AS bowling_sr,
            COUNT(*) FILTER (WHERE d.runs_batter = 4)                     AS fours_conceded,
            COUNT(*) FILTER (WHERE d.runs_batter = 6)                     AS sixes_conceded,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct,
            SUM(d.runs_extras) FILTER (WHERE d.extra_type = 'wides')           AS wides,
            SUM(d.runs_extras) FILTER (WHERE d.extra_type = 'noballs')         AS noballs
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} {player_clause}
            AND d.over_num BETWEEN 0 AND 19
        GROUP BY phase, phase_order
        ORDER BY phase_order
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty or "phase" not in df.columns:
            return None

        role = (params.extra or {}).get("role", "batting")
        phases = df["phase"].tolist()
        colors = ["#2196F3", "#FF9800", "#F44336"]

        if role == "bowling":
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Economy", x=phases, y=df["economy"],
                marker_color=colors, yaxis="y",
                text=df["economy"], textposition="outside",
            ))
            fig.add_trace(go.Scatter(
                name="Dot Ball %", x=phases, y=df["dot_pct"],
                mode="lines+markers+text",
                marker=dict(size=12, color="white", line=dict(color="#333", width=2)),
                text=[f"{v}%" for v in df["dot_pct"]],
                textposition="top center", yaxis="y2",
            ))
            title = "Bowling: Economy & Dot % by Phase"
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Strike Rate", x=phases, y=df["strike_rate"],
                marker_color=colors, yaxis="y",
                text=df["strike_rate"], textposition="outside",
            ))
            fig.add_trace(go.Scatter(
                name="Boundary %", x=phases, y=df["boundary_pct"],
                mode="lines+markers+text",
                marker=dict(size=12, color="white", line=dict(color="#333", width=2)),
                text=[f"{v}%" for v in df["boundary_pct"]],
                textposition="top center", yaxis="y2",
            ))
            title = "Batting: Strike Rate & Boundary % by Phase"

        if params.player:
            title += f" — {params.player}"
        if params.team:
            title += f" — {params.team}"

        fig.update_layout(
            title=title,
            yaxis=dict(title="Strike Rate" if role != "bowling" else "Economy"),
            yaxis2=dict(title="Boundary %" if role != "bowling" else "Dot Ball %",
                        overlaying="y", side="right", range=[0, 100]),
            height=450, legend=dict(x=0.01, y=0.99),
        )
        return fig
