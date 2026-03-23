"""Module A2 — Pace vs Spin Performance.

Classifies bowlers as pace/spin using over-distribution heuristics:
  - Spinners bowl primarily in middle overs (7-15), rarely at death
  - Pacers bowl across all phases, especially PP and death

Then shows how batters/teams perform against each type.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class PaceVsSpin(BaseModule):
    module_id = "A2"
    module_name = "Pace vs Spin Analysis"
    category = "advanced"
    supported_filters = frozenset({"format", "player", "team", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        mode = (params.extra or {}).get("mode", "batter_vs_type")
        if mode == "bowler_classification":
            return self._classify_bowlers(params)
        elif mode == "team_vs_type":
            return self._team_vs_type(params)
        return self._batter_vs_type(params)

    def _classify_bowlers(self, params: ModuleParams) -> pd.DataFrame:
        """Classify bowlers as pace/spin based on when they bowl."""
        where, values = self._build_where_clauses(params, "m")

        sql = f"""
        WITH bowler_overs AS (
            SELECT
                d.bowler,
                COUNT(*) AS total_balls,
                COUNT(*) FILTER (WHERE d.over_num BETWEEN 0 AND 5) AS pp_balls,
                COUNT(*) FILTER (WHERE d.over_num BETWEEN 6 AND 14) AS mid_balls,
                COUNT(*) FILTER (WHERE d.over_num BETWEEN 15 AND 19) AS death_balls,
                COUNT(DISTINCT d.match_id) AS matches
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.bowler
            HAVING COUNT(*) >= 120
        )
        SELECT
            bowler,
            matches,
            total_balls,
            ROUND(pp_balls * 100.0 / total_balls, 1) AS pp_pct,
            ROUND(mid_balls * 100.0 / total_balls, 1) AS mid_pct,
            ROUND(death_balls * 100.0 / total_balls, 1) AS death_pct,
            CASE
                WHEN mid_balls * 1.0 / total_balls > 0.50
                 AND death_balls * 1.0 / total_balls < 0.20
                THEN 'Spin'
                ELSE 'Pace'
            END AS bowler_type
        FROM bowler_overs
        ORDER BY total_balls DESC
        """
        return query(sql, values)

    def _batter_vs_type(self, params: ModuleParams) -> pd.DataFrame:
        """How a batter performs against pace vs spin."""
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND d.batter ILIKE ?"
            values.append(f"%{params.player}%")

        # Values used twice: once for bowler classification, once for main query
        all_values = values + values + (values[:-1] if params.player else values)

        # Classify from same competition/season context
        base_where, base_values = self._build_where_clauses(
            ModuleParams(format=params.format), "m"
        )

        all_values = base_values + values

        sql = f"""
        WITH bowler_type AS (
            SELECT
                d.bowler,
                CASE
                    WHEN COUNT(*) FILTER (WHERE d.over_num BETWEEN 6 AND 14) * 1.0
                         / NULLIF(COUNT(*), 0) > 0.50
                     AND COUNT(*) FILTER (WHERE d.over_num BETWEEN 15 AND 19) * 1.0
                         / NULLIF(COUNT(*), 0) < 0.20
                    THEN 'Spin'
                    ELSE 'Pace'
                END AS bowl_type
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {base_where} AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.bowler
            HAVING COUNT(*) >= 120
        )
        SELECT
            d.batter,
            COALESCE(bt.bowl_type, 'Pace') AS bowler_type,
            COUNT(DISTINCT d.match_id) AS innings,
            SUM(d.runs_batter) AS runs,
            COUNT(*) FILTER (WHERE d.extra_type IS NULL
                OR d.extra_type NOT IN ('wides')) AS balls,
            ROUND(SUM(d.runs_batter) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1) AS strike_rate,
            COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL) AS dots,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct,
            COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
            COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
            ROUND((COUNT(*) FILTER (WHERE d.runs_batter = 4)
                 + COUNT(*) FILTER (WHERE d.runs_batter = 6)) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1) AS boundary_pct,
            COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                AND d.player_out = d.batter
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out')) AS dismissals
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        LEFT JOIN bowler_type bt ON d.bowler = bt.bowler
        WHERE {where} {player_clause}
            AND d.over_num BETWEEN 0 AND 19
        GROUP BY d.batter, COALESCE(bt.bowl_type, 'Pace')
        HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL OR d.extra_type NOT IN ('wides')) >= 20
        ORDER BY runs DESC
        """
        return query(sql, all_values)

    def _team_vs_type(self, params: ModuleParams) -> pd.DataFrame:
        """How teams perform against pace vs spin."""
        where, values = self._build_where_clauses(params, "m")

        base_where, base_values = self._build_where_clauses(
            ModuleParams(format=params.format), "m"
        )
        all_values = base_values + values

        sql = f"""
        WITH bowler_type AS (
            SELECT
                d.bowler,
                CASE
                    WHEN COUNT(*) FILTER (WHERE d.over_num BETWEEN 6 AND 14) * 1.0
                         / NULLIF(COUNT(*), 0) > 0.50
                     AND COUNT(*) FILTER (WHERE d.over_num BETWEEN 15 AND 19) * 1.0
                         / NULLIF(COUNT(*), 0) < 0.20
                    THEN 'Spin'
                    ELSE 'Pace'
                END AS bowl_type
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {base_where} AND d.over_num BETWEEN 0 AND 19
            GROUP BY d.bowler
            HAVING COUNT(*) >= 120
        ),
        batting_team AS (
            SELECT d.match_id, d.innings,
                CASE WHEN d.innings = 1 THEN m.team1 ELSE m.team2 END AS team
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY d.match_id, d.innings, m.team1, m.team2
        )
        SELECT
            bt2.team,
            COALESCE(bt.bowl_type, 'Pace') AS bowler_type,
            SUM(d.runs_batter) AS runs,
            COUNT(*) FILTER (WHERE d.extra_type IS NULL
                OR d.extra_type NOT IN ('wides')) AS balls,
            ROUND(SUM(d.runs_batter) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1) AS strike_rate,
            ROUND((COUNT(*) FILTER (WHERE d.runs_batter = 4)
                 + COUNT(*) FILTER (WHERE d.runs_batter = 6)) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0), 1) AS boundary_pct,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        LEFT JOIN bowler_type bt ON d.bowler = bt.bowler
        JOIN batting_team bt2 ON d.match_id = bt2.match_id AND d.innings = bt2.innings
        WHERE {where} AND d.over_num BETWEEN 0 AND 19
        GROUP BY bt2.team, COALESCE(bt.bowl_type, 'Pace')
        HAVING COUNT(*) >= 60
        ORDER BY strike_rate DESC
        """
        # values used: base_values + values + values
        all_values = base_values + values + values
        return query(sql, all_values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        mode = (params.extra or {}).get("mode", "batter_vs_type")

        if mode == "bowler_classification":
            return self._classification_plot(df, params)
        elif mode == "team_vs_type":
            return self._team_plot(df, params)
        return self._batter_plot(df, params)

    def _batter_plot(self, df, params):
        """Side-by-side: pace SR vs spin SR for each batter."""
        # Pivot: one row per batter, columns for pace/spin
        pivot = df.pivot_table(
            index="batter", columns="bowler_type",
            values=["strike_rate", "boundary_pct", "dot_pct", "runs", "dismissals"],
            aggfunc="first"
        ).reset_index()
        pivot.columns = ["_".join(c).strip("_") for c in pivot.columns]

        # Sort by total runs
        if "runs_Pace" in pivot.columns and "runs_Spin" in pivot.columns:
            pivot["total_runs"] = pivot["runs_Pace"].fillna(0) + pivot["runs_Spin"].fillna(0)
            pivot = pivot.sort_values("total_runs", ascending=False).head(15)
        else:
            pivot = pivot.head(15)

        fig = make_subplots(
            rows=1, cols=2, column_widths=[0.5, 0.5],
            subplot_titles=["Strike Rate: Pace vs Spin", "Boundary %: Pace vs Spin"],
        )

        # Left: SR comparison
        pace_sr = pivot.get("strike_rate_Pace", pd.Series([0]*len(pivot))).fillna(0)
        spin_sr = pivot.get("strike_rate_Spin", pd.Series([0]*len(pivot))).fillna(0)

        fig.add_trace(go.Bar(
            name="vs Pace", y=pivot["batter"], x=pace_sr,
            orientation="h", marker_color="#EF5350",
            text=[f"{v}" for v in pace_sr], textposition="outside",
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            name="vs Spin", y=pivot["batter"], x=spin_sr,
            orientation="h", marker_color="#42A5F5",
            text=[f"{v}" for v in spin_sr], textposition="outside",
        ), row=1, col=1)

        # Right: Boundary %
        pace_bp = pivot.get("boundary_pct_Pace", pd.Series([0]*len(pivot))).fillna(0)
        spin_bp = pivot.get("boundary_pct_Spin", pd.Series([0]*len(pivot))).fillna(0)

        fig.add_trace(go.Bar(
            name="vs Pace", y=pivot["batter"], x=pace_bp,
            orientation="h", marker_color="#EF5350", showlegend=False,
            text=[f"{v}%" for v in pace_bp], textposition="outside",
        ), row=1, col=2)
        fig.add_trace(go.Bar(
            name="vs Spin", y=pivot["batter"], x=spin_bp,
            orientation="h", marker_color="#42A5F5", showlegend=False,
            text=[f"{v}%" for v in spin_bp], textposition="outside",
        ), row=1, col=2)

        title = "Batter Performance: Pace vs Spin"
        if params.player:
            title = f"{params.player} — Pace vs Spin Breakdown"

        fig.update_layout(
            title=title, barmode="group",
            height=max(450, len(pivot) * 35),
            legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"),
        )
        fig.update_yaxes(autorange="reversed", row=1, col=1)
        fig.update_yaxes(autorange="reversed", row=1, col=2)
        fig.update_xaxes(title_text="Strike Rate", row=1, col=1)
        fig.update_xaxes(title_text="Boundary %", row=1, col=2)

        return fig

    def _team_plot(self, df, params):
        """Team performance vs pace/spin."""
        pivot = df.pivot_table(
            index="team", columns="bowler_type",
            values=["strike_rate", "boundary_pct", "dot_pct"],
            aggfunc="first"
        ).reset_index()
        pivot.columns = ["_".join(c).strip("_") for c in pivot.columns]
        pivot = pivot.head(12)

        fig = go.Figure()

        pace_sr = pivot.get("strike_rate_Pace", pd.Series([0]*len(pivot))).fillna(0)
        spin_sr = pivot.get("strike_rate_Spin", pd.Series([0]*len(pivot))).fillna(0)

        fig.add_trace(go.Bar(
            name="vs Pace", y=pivot["team"], x=pace_sr,
            orientation="h", marker_color="#EF5350",
            text=[f"{v}" for v in pace_sr], textposition="outside",
        ))
        fig.add_trace(go.Bar(
            name="vs Spin", y=pivot["team"], x=spin_sr,
            orientation="h", marker_color="#42A5F5",
            text=[f"{v}" for v in spin_sr], textposition="outside",
        ))

        fig.update_layout(
            title="Team Strike Rate: Pace vs Spin",
            barmode="group",
            height=max(400, len(pivot) * 35),
            yaxis=dict(autorange="reversed"),
            legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"),
        )
        return fig

    def _classification_plot(self, df, params):
        """Scatter: pp% vs death% — clusters show pace/spin separation."""
        fig = go.Figure()

        for btype, color, symbol in [("Pace", "#EF5350", "circle"), ("Spin", "#42A5F5", "diamond")]:
            sub = df[df["bowler_type"] == btype]
            if sub.empty:
                continue
            fig.add_trace(go.Scatter(
                x=sub["death_pct"], y=sub["mid_pct"],
                mode="markers+text",
                marker=dict(size=sub["matches"].clip(lower=5) * 0.8, color=color,
                           symbol=symbol, line=dict(width=1, color="#333")),
                text=sub["bowler"].str.split().str[-1],
                textposition="top center", textfont=dict(size=8),
                name=btype,
                hovertemplate="<b>%{text}</b><br>Death%: %{x}<br>Middle%: %{y}<extra></extra>",
            ))

        fig.update_layout(
            title="Bowler Classification: Death Over % vs Middle Over %",
            xaxis_title="Death Over % (higher = pacer)",
            yaxis_title="Middle Over % (higher = spinner)",
            height=500,
        )
        return fig
