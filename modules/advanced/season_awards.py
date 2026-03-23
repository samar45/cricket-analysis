"""Module A3 — Season Awards & Phase Leaders.

Top 5 per season for:
  - Best death-overs batter / bowler
  - Best powerplay batter / bowler
  - Best middle-overs batter / bowler
  - Best debutants (batter / bowler) in each season
With venue filter support.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class SeasonAwards(BaseModule):
    module_id = "A3"
    module_name = "Season Awards & Phase Leaders"
    category = "advanced"
    supported_filters = frozenset({"format", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        award = (params.extra or {}).get("award", "death_batter")
        if award == "debutant_batter":
            return self._best_debutants(params, "batter")
        elif award == "debutant_bowler":
            return self._best_debutants(params, "bowler")
        else:
            return self._phase_leaders(params, award)

    def _phase_leaders(self, params: ModuleParams, award: str) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")

        # Parse award: {phase}_{role}
        parts = award.split("_")
        phase_name = parts[0]  # death, powerplay, middle
        role = parts[1] if len(parts) > 1 else "batter"

        phase_map = {"death": (15, 19), "powerplay": (0, 5), "middle": (6, 14)}
        overs = phase_map.get(phase_name, (0, 19))

        values.extend([overs[0], overs[1]])

        if role == "batter":
            sql = f"""
            SELECT
                m.season,
                d.batter AS player,
                SUM(d.runs_batter) AS runs,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')) AS balls,
                ROUND(SUM(d.runs_batter) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')), 0), 1) AS strike_rate,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                ROUND((COUNT(*) FILTER (WHERE d.runs_batter = 4)
                     + COUNT(*) FILTER (WHERE d.runs_batter = 6)) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')), 0), 1) AS boundary_pct,
                COUNT(DISTINCT d.match_id) AS matches,
                ROW_NUMBER() OVER (PARTITION BY m.season ORDER BY SUM(d.runs_batter) DESC) AS rank
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
                AND d.over_num BETWEEN ? AND ?
            GROUP BY m.season, d.batter
            HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL OR d.extra_type NOT IN ('wides')) >= 20
            """
        else:
            sql = f"""
            SELECT
                m.season,
                d.bowler AS player,
                COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                    AS wickets,
                SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0)
                    AS runs_conceded,
                COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls,
                ROUND((SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0))
                    * 6.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
                ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                    * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct,
                COUNT(DISTINCT d.match_id) AS matches,
                ROW_NUMBER() OVER (PARTITION BY m.season
                    ORDER BY COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                        AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')) DESC) AS rank
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
                AND d.over_num BETWEEN ? AND ?
            GROUP BY m.season, d.bowler
            HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL) >= 30
            """

        # Wrap to get top 5 per season
        final_sql = f"""
        WITH ranked AS ({sql})
        SELECT * FROM ranked WHERE rank <= 5
        ORDER BY season DESC, rank
        """
        return query(final_sql, values)

    def _best_debutants(self, params: ModuleParams, role: str) -> pd.DataFrame:
        """Find players who debuted in each season and rank by performance."""
        where, values = self._build_where_clauses(params, "m")
        base_where, base_values = self._build_where_clauses(
            ModuleParams(format=params.format), "m"
        )

        all_values = base_values + values

        if role == "batter":
            sql = f"""
            WITH first_season AS (
                SELECT d.batter AS player, MIN(m.season) AS debut_season
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {base_where}
                GROUP BY d.batter
            ),
            debut_stats AS (
                SELECT
                    d.batter AS player,
                    m.season,
                    SUM(d.runs_batter) AS runs,
                    COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')) AS balls,
                    ROUND(SUM(d.runs_batter) * 100.0
                        / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                            OR d.extra_type NOT IN ('wides')), 0), 1) AS strike_rate,
                    COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours,
                    COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                    COUNT(DISTINCT d.match_id) AS matches,
                    MAX(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END) AS was_out_flag
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {where}
                GROUP BY d.batter, m.season
            )
            SELECT
                ds.player,
                ds.season AS debut_season,
                ds.runs,
                ds.balls,
                ds.strike_rate,
                ds.fours,
                ds.sixes,
                ds.matches,
                ROW_NUMBER() OVER (PARTITION BY ds.season ORDER BY ds.runs DESC) AS rank
            FROM debut_stats ds
            JOIN first_season fs ON ds.player = fs.player AND ds.season = fs.debut_season
            WHERE ds.balls >= 15
            """
        else:
            sql = f"""
            WITH first_season AS (
                SELECT d.bowler AS player, MIN(m.season) AS debut_season
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {base_where}
                GROUP BY d.bowler
            ),
            debut_stats AS (
                SELECT
                    d.bowler AS player,
                    m.season,
                    COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL
                        AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field'))
                        AS wickets,
                    SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0)
                        AS runs_conceded,
                    COUNT(*) FILTER (WHERE d.extra_type IS NULL) AS legal_balls,
                    ROUND((SUM(d.runs_total) - COALESCE(SUM(d.runs_extras) FILTER (WHERE d.extra_type IN ('byes','legbyes')), 0))
                        * 6.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
                    COUNT(DISTINCT d.match_id) AS matches,
                    ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 1) AS dot_pct
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                WHERE {where}
                GROUP BY d.bowler, m.season
            )
            SELECT
                ds.player,
                ds.season AS debut_season,
                ds.wickets,
                ds.runs_conceded,
                ds.legal_balls,
                ds.economy,
                ds.dot_pct,
                ds.matches,
                ROW_NUMBER() OVER (PARTITION BY ds.season ORDER BY ds.wickets DESC) AS rank
            FROM debut_stats ds
            JOIN first_season fs ON ds.player = fs.player AND ds.season = fs.debut_season
            WHERE ds.legal_balls >= 24
            """

        final_sql = f"""
        WITH ranked AS ({sql})
        SELECT * FROM ranked WHERE rank <= 5
        ORDER BY debut_season DESC, rank
        """
        return query(final_sql, all_values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None

        award = (params.extra or {}).get("award", "death_batter")

        if "debut_season" in df.columns:
            return self._debutant_plot(df, params, award)
        return self._phase_leader_plot(df, params, award)

    def _phase_leader_plot(self, df, params, award):
        parts = award.split("_")
        phase = parts[0].title()
        role = parts[1] if len(parts) > 1 else "batter"

        # Show latest 4 seasons
        seasons = df["season"].unique()[:4]
        n_seasons = len(seasons)
        if n_seasons == 0:
            return None

        fig = make_subplots(
            rows=1, cols=n_seasons,
            subplot_titles=[str(s) for s in seasons],
        )

        for i, season in enumerate(seasons, 1):
            sdf = df[df["season"] == season].head(5)
            if sdf.empty:
                continue

            if role == "batter":
                fig.add_trace(go.Bar(
                    y=sdf["player"], x=sdf["runs"],
                    orientation="h",
                    marker_color=["#FFD700", "#C0C0C0", "#CD7F32", "#4A90D9", "#4A90D9"][:len(sdf)],
                    text=[f"{r} ({sr})" for r, sr in zip(sdf["runs"], sdf["strike_rate"])],
                    textposition="outside",
                    showlegend=False,
                    hovertemplate="<b>%{y}</b><br>Runs: %{x}<extra></extra>",
                ), row=1, col=i)
            else:
                fig.add_trace(go.Bar(
                    y=sdf["player"], x=sdf["wickets"],
                    orientation="h",
                    marker_color=["#FFD700", "#C0C0C0", "#CD7F32", "#4A90D9", "#4A90D9"][:len(sdf)],
                    text=[f"{w}w ({e})" for w, e in zip(sdf["wickets"], sdf["economy"])],
                    textposition="outside",
                    showlegend=False,
                    hovertemplate="<b>%{y}</b><br>Wickets: %{x}<extra></extra>",
                ), row=1, col=i)

            fig.update_yaxes(autorange="reversed", row=1, col=i)

        role_label = "Batters" if role == "batter" else "Bowlers"
        fig.update_layout(
            title=f"Top 5 {phase} {role_label} by Season",
            height=max(350, 5 * 35),
            margin=dict(r=100),
        )
        return fig

    def _debutant_plot(self, df, params, award):
        role = "batter" if "batter" in award else "bowler"
        seasons = df["debut_season"].unique()[:4]
        n_seasons = len(seasons)
        if n_seasons == 0:
            return None

        fig = make_subplots(
            rows=1, cols=n_seasons,
            subplot_titles=[str(s) for s in seasons],
        )

        for i, season in enumerate(seasons, 1):
            sdf = df[df["debut_season"] == season].head(5)
            if sdf.empty:
                continue

            if role == "batter":
                fig.add_trace(go.Bar(
                    y=sdf["player"], x=sdf["runs"],
                    orientation="h",
                    marker_color=["#FFD700", "#C0C0C0", "#CD7F32", "#4A90D9", "#4A90D9"][:len(sdf)],
                    text=[f"{r} ({m}m)" for r, m in zip(sdf["runs"], sdf["matches"])],
                    textposition="outside",
                    showlegend=False,
                ), row=1, col=i)
            else:
                fig.add_trace(go.Bar(
                    y=sdf["player"], x=sdf["wickets"],
                    orientation="h",
                    marker_color=["#FFD700", "#C0C0C0", "#CD7F32", "#4A90D9", "#4A90D9"][:len(sdf)],
                    text=[f"{w}w ({m}m)" for w, m in zip(sdf["wickets"], sdf["matches"])],
                    textposition="outside",
                    showlegend=False,
                ), row=1, col=i)

            fig.update_yaxes(autorange="reversed", row=1, col=i)

        role_label = "Batters" if role == "batter" else "Bowlers"
        fig.update_layout(
            title=f"Best Debut Season — Top 5 {role_label}",
            height=max(350, 5 * 35),
            margin=dict(r=100),
        )
        return fig
