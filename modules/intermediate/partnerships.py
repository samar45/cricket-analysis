"""Module I2 — Partnership Analysis.

Best batting partnerships overall, or filtered by format / team / venue / season.
Also shows top partnership pairs and their combined record.
"""

import pandas as pd
import plotly.express as px

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class PartnershipAnalysis(BaseModule):
    module_id = "I2"
    module_name = "Partnership Analysis"
    category = "intermediate"
    supported_filters = frozenset({"format", "player", "team", "season", "venue"})

    def run(self, params: ModuleParams) -> pd.DataFrame:
        """Top partnerships.

        Player filter: only partnerships where that batter was involved.
        """
        where, values = self._build_where_clauses(params, "m")

        player_clause = ""
        if params.player:
            player_clause = "AND (d.batter ILIKE ? OR d.non_striker ILIKE ?)"
            values.extend([f"%{params.player}%", f"%{params.player}%"])

        # Build partnership key: always sort alphabetically so (A,B) = (B,A)
        sql = f"""
        WITH ball_level AS (
            SELECT
                d.match_id,
                d.innings,
                CASE WHEN d.batter <= d.non_striker
                    THEN d.batter || ' & ' || d.non_striker
                    ELSE d.non_striker || ' & ' || d.batter
                END AS pair,
                d.runs_batter,
                d.runs_total,
                d.extra_type,
                d.wicket_type
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where} {player_clause}
              AND d.non_striker IS NOT NULL
        )
        SELECT
            pair,
            COUNT(DISTINCT match_id || '-' || innings)           AS innings_together,
            SUM(runs_batter)                                     AS runs,
            COUNT(*) FILTER (WHERE extra_type IS NULL
                OR extra_type NOT IN ('wides'))                  AS balls,
            ROUND(SUM(runs_batter) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE extra_type IS NULL
                    OR extra_type NOT IN ('wides')), 0), 2)      AS partnership_sr,
            COUNT(*) FILTER (WHERE runs_batter = 6)              AS sixes,
            COUNT(*) FILTER (WHERE runs_batter = 4)              AS fours,
            ROUND(COUNT(*) FILTER (WHERE runs_batter = 0 AND extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*), 0), 2)               AS dot_pct
        FROM ball_level
        GROUP BY pair
        HAVING SUM(runs_batter) >= 30
        ORDER BY runs DESC
        LIMIT 30
        """
        return query(sql, values)

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None
        top = df.head(15)
        fig = px.bar(
            top, x="pair", y="runs",
            color="partnership_sr",
            color_continuous_scale="Greens",
            title="Top Batting Partnerships" + (f" involving {params.player}" if params.player else ""),
            labels={"pair": "Partnership", "runs": "Runs", "partnership_sr": "SR"},
            hover_data=["innings_together", "balls", "sixes", "fours"],
        )
        fig.update_layout(xaxis_tickangle=-45, height=480)
        return fig
