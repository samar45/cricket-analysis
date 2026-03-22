"""Module B5 — Season Leaderboards (Orange/Purple Cap).

Top run-scorers and wicket-takers per format and season.
Orange Cap = most runs; Purple Cap = most wickets.
Also includes strike-rate and economy leaderboards.
"""

import pandas as pd
import plotly.express as px

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class Leaderboards(BaseModule):
    module_id = "B5"
    module_name = "Season Leaderboards (Orange / Purple Cap)"
    category = "basic"
    supported_filters = frozenset({"format", "season"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        """Returns Orange Cap (run leaders) by default.
        Set params.extra['cap'] = 'purple' for wicket leaders.
        Set params.extra['cap'] = 'sr' for strike-rate leaders.
        Set params.extra['cap'] = 'economy' for economy leaders.
        """
        cap = params.extra.get("cap", "orange")
        where, values = self._build_where_clauses(params, "m")

        if cap == "purple":
            sql = f"""
            SELECT
                d.bowler                               AS player,
                m.season,
                m.format,
                COUNT(DISTINCT d.match_id)             AS matches,
                SUM(CASE WHEN d.wicket_type IS NOT NULL
                    AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
                    THEN 1 ELSE 0 END)                 AS wickets,
                ROUND(SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                    THEN d.runs_total ELSE 0 END) * 6.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
                ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                    * 100.0 / NULLIF(COUNT(*), 0), 2) AS dot_pct
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY d.bowler, m.season, m.format
            HAVING SUM(CASE WHEN d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
                THEN 1 ELSE 0 END) > 0
            ORDER BY wickets DESC
            LIMIT 25
            """
        elif cap == "economy":
            sql = f"""
            SELECT
                d.bowler                               AS player,
                m.season,
                m.format,
                COUNT(DISTINCT d.match_id)             AS matches,
                ROUND(COUNT(*) FILTER (WHERE d.extra_type IS NULL) / 6.0, 1) AS overs,
                ROUND(SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                    THEN d.runs_total ELSE 0 END) * 6.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY d.bowler, m.season, m.format
            HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL) >= 60
            ORDER BY economy ASC
            LIMIT 25
            """
        elif cap == "sr":
            sql = f"""
            SELECT
                d.batter                               AS player,
                m.season,
                m.format,
                COUNT(DISTINCT d.match_id)             AS matches,
                SUM(d.runs_batter)                     AS runs,
                ROUND(SUM(d.runs_batter) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')), 0), 2) AS strike_rate
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY d.batter, m.season, m.format
            HAVING SUM(d.runs_batter) >= 200
            ORDER BY strike_rate DESC
            LIMIT 25
            """
        else:  # orange cap (runs)
            sql = f"""
            SELECT
                d.batter                               AS player,
                m.season,
                m.format,
                COUNT(DISTINCT d.match_id)             AS matches,
                SUM(d.runs_batter)                     AS runs,
                ROUND(SUM(d.runs_batter) * 1.0
                    / NULLIF(SUM(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END), 0),
                    2)                                 AS average,
                ROUND(SUM(d.runs_batter) * 100.0
                    / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                        OR d.extra_type NOT IN ('wides')), 0), 2) AS strike_rate,
                COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
                COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY d.batter, m.season, m.format
            ORDER BY runs DESC
            LIMIT 25
            """

        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None
        cap = params.extra.get("cap", "orange")

        if cap == "purple":
            fig = px.bar(df, x="player", y="wickets",
                         color="economy", color_continuous_scale="Blues_r",
                         title="Purple Cap — Top Wicket Takers",
                         labels={"player": "Bowler", "wickets": "Wickets"})
        elif cap == "economy":
            fig = px.bar(df, x="player", y="economy",
                         title="Best Economy Rates (min 10 overs)",
                         labels={"player": "Bowler", "economy": "Economy"})
        elif cap == "sr":
            fig = px.bar(df, x="player", y="strike_rate",
                         color="runs", color_continuous_scale="Oranges",
                         title="Strike Rate Leaders (min 200 runs)",
                         labels={"player": "Batter", "strike_rate": "Strike Rate"})
        else:
            fig = px.bar(df, x="player", y="runs",
                         color="strike_rate", color_continuous_scale="Oranges",
                         title="Orange Cap — Top Run Scorers",
                         labels={"player": "Batter", "runs": "Runs"})

        fig.update_layout(xaxis_tickangle=-45)
        return fig
