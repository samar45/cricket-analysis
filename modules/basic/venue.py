"""Module B6 — Venue Analysis.

Full venue breakdown:
  - Match stats: avg 1st/2nd innings scores, batting-first win %, toss impact
  - Team records at venue
  - Best batters at venue (runs, SR, avg)
  - Best bowlers at venue (wickets, economy)
  - Best death overs (16-20) bowlers at venue
  - Best powerplay bowlers at venue

Select a venue to drill into it; leave blank for all-venue summary.
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from modules.base import BaseModule, ModuleParams, register_module
from src.cricket_analytics.db import query


@register_module
class VenueAnalysis(BaseModule):
    module_id = "B6"
    module_name = "Venue Analysis"
    category = "basic"
    supported_filters = frozenset({"format", "venue", "season", "team"})

    # ── Main run() → overview or venue-level match stats ─────────────────────

    def run(self, params: ModuleParams) -> pd.DataFrame:
        """
        No venue selected → sorted list of venues with avg scores & win rates.
        Venue selected    → match-level stats for that venue.
        """
        if params.venue:
            return self._venue_match_stats(params)
        return self._all_venues_summary(params)

    # ── run_tabs() → additional tabbed views when venue is set ───────────────

    def run_tabs(self, params: ModuleParams) -> dict[str, pd.DataFrame] | None:
        if not params.venue:
            return None
        return {
            "🏏 Top Batters":         self._best_batters(params),
            "🎳 Top Bowlers":          self._best_bowlers(params),
            "💀 Death Overs (16–20)":  self._death_bowlers(params),
            "⚡ Powerplay Bowlers":    self._powerplay_bowlers(params),
            "🏆 Team Records":         self._team_records(params),
        }

    # ── Internal queries ──────────────────────────────────────────────────────

    def _all_venues_summary(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        # {where} is used in two CTEs → duplicate bind values
        sql = f"""
        WITH inn_scores AS (
            SELECT
                m.venue,
                d.match_id,
                d.innings,
                SUM(d.runs_total) AS score
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY m.venue, d.match_id, d.innings
        ),
        venue_agg AS (
            SELECT
                venue,
                COUNT(DISTINCT match_id)                    AS matches,
                ROUND(AVG(score) FILTER (WHERE innings = 1), 1) AS avg_1st_innings,
                ROUND(AVG(score) FILTER (WHERE innings = 2), 1) AS avg_2nd_innings
            FROM inn_scores
            GROUP BY venue
        ),
        venue_wins AS (
            SELECT
                m.venue,
                COUNT(*) FILTER (WHERE m.toss_decision = 'bat' AND m.winner = m.team1
                    OR m.toss_decision = 'field' AND m.winner = m.team2) AS bat_first_wins,
                COUNT(*) FILTER (WHERE m.winner IS NOT NULL)             AS decisive_matches
            FROM matches m
            WHERE {where}
            GROUP BY m.venue
        )
        SELECT
            va.venue,
            va.matches,
            va.avg_1st_innings,
            va.avg_2nd_innings,
            ROUND(vw.bat_first_wins * 100.0 / NULLIF(vw.decisive_matches, 0), 1)
                AS bat_first_win_pct
        FROM venue_agg va
        LEFT JOIN venue_wins vw ON va.venue = vw.venue
        WHERE va.matches >= 3
        ORDER BY va.matches DESC
        """
        return query(sql, values + values)  # values used in 2 CTEs

    def _venue_match_stats(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        sql = f"""
        WITH inn AS (
            SELECT d.match_id, d.innings, SUM(d.runs_total) AS score,
                   COUNT(*) FILTER (WHERE d.wicket_type IS NOT NULL) AS wickets
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            WHERE {where}
            GROUP BY d.match_id, d.innings
        )
        SELECT
            m.venue,
            m.season,
            COUNT(DISTINCT m.match_id)                                    AS matches,
            ROUND(AVG(inn.score) FILTER (WHERE inn.innings = 1), 1)       AS avg_1st_innings,
            ROUND(AVG(inn.score) FILTER (WHERE inn.innings = 2), 1)       AS avg_2nd_innings,
            MAX(inn.score) FILTER (WHERE inn.innings = 1)                 AS highest_1st_innings,
            MAX(inn.score) FILTER (WHERE inn.innings = 2)                 AS highest_2nd_innings,
            ROUND(
                COUNT(DISTINCT m.match_id) FILTER (
                    WHERE (m.toss_decision = 'bat' AND m.winner = m.team1)
                    OR (m.toss_decision = 'field' AND m.winner = m.team2)
                ) * 100.0 / NULLIF(COUNT(DISTINCT m.match_id) FILTER (WHERE m.winner IS NOT NULL), 0),
                1
            )                                                             AS bat_first_win_pct,
            ROUND(
                COUNT(DISTINCT m.match_id) FILTER (WHERE m.toss_winner = m.winner)
                * 100.0 / NULLIF(COUNT(DISTINCT m.match_id) FILTER (WHERE m.winner IS NOT NULL), 0),
                1
            )                                                             AS toss_winner_wins_pct
        FROM matches m
        JOIN inn ON m.match_id = inn.match_id
        WHERE {where}
        GROUP BY m.venue, m.season
        ORDER BY m.season DESC
        """
        return query(sql, values)

    def _best_batters(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        sql = f"""
        SELECT
            d.batter,
            COUNT(DISTINCT d.match_id)  AS matches,
            SUM(d.runs_batter)          AS runs,
            MAX(
                (SELECT SUM(d2.runs_batter)
                 FROM deliveries d2
                 WHERE d2.match_id = d.match_id AND d2.batter = d.batter)
            )                           AS highest_score,
            ROUND(SUM(d.runs_batter) * 1.0
                / NULLIF(SUM(CASE WHEN d.player_out = d.batter THEN 1 ELSE 0 END), 0),
                2)                      AS average,
            ROUND(SUM(d.runs_batter) * 100.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL
                    OR d.extra_type NOT IN ('wides')), 0),
                2)                      AS strike_rate,
            COUNT(*) FILTER (WHERE d.runs_batter = 6) AS sixes,
            COUNT(*) FILTER (WHERE d.runs_batter = 4) AS fours
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
        GROUP BY d.batter
        HAVING SUM(d.runs_batter) >= 50
        ORDER BY runs DESC
        LIMIT 20
        """
        return query(sql, values)

    def _best_bowlers(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        sql = f"""
        SELECT
            d.bowler,
            COUNT(DISTINCT d.match_id)  AS matches,
            SUM(CASE WHEN d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
                THEN 1 ELSE 0 END)       AS wickets,
            ROUND(COUNT(*) FILTER (WHERE d.extra_type IS NULL) / 6.0, 1) AS overs,
            ROUND(SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                THEN d.runs_total ELSE 0 END) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*), 0), 2)  AS dot_pct
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where}
        GROUP BY d.bowler
        HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL) >= 30
        ORDER BY wickets DESC
        LIMIT 20
        """
        return query(sql, values)

    def _death_bowlers(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        sql = f"""
        SELECT
            d.bowler,
            COUNT(DISTINCT d.match_id)  AS matches,
            ROUND(COUNT(*) FILTER (WHERE d.extra_type IS NULL) / 6.0, 1) AS death_overs,
            SUM(CASE WHEN d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
                THEN 1 ELSE 0 END)       AS wickets,
            ROUND(SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                THEN d.runs_total ELSE 0 END) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*), 0), 2)  AS dot_pct,
            SUM(d.runs_total)           AS runs_conceded
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} AND d.over_num BETWEEN 15 AND 19
        GROUP BY d.bowler
        HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL) >= 18
        ORDER BY economy ASC
        LIMIT 20
        """
        return query(sql, values)

    def _powerplay_bowlers(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        sql = f"""
        SELECT
            d.bowler,
            COUNT(DISTINCT d.match_id)  AS matches,
            ROUND(COUNT(*) FILTER (WHERE d.extra_type IS NULL) / 6.0, 1) AS pp_overs,
            SUM(CASE WHEN d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
                THEN 1 ELSE 0 END)       AS wickets,
            ROUND(SUM(CASE WHEN d.extra_type NOT IN ('byes','legbyes') OR d.extra_type IS NULL
                THEN d.runs_total ELSE 0 END) * 6.0
                / NULLIF(COUNT(*) FILTER (WHERE d.extra_type IS NULL), 0), 2) AS economy,
            ROUND(COUNT(*) FILTER (WHERE d.runs_batter = 0 AND d.extra_type IS NULL)
                * 100.0 / NULLIF(COUNT(*), 0), 2)  AS dot_pct
        FROM deliveries d
        JOIN matches m ON d.match_id = m.match_id
        WHERE {where} AND d.over_num BETWEEN 0 AND 5
        GROUP BY d.bowler
        HAVING COUNT(*) FILTER (WHERE d.extra_type IS NULL) >= 18
        ORDER BY economy ASC
        LIMIT 20
        """
        return query(sql, values)

    def _team_records(self, params: ModuleParams) -> pd.DataFrame:
        where, values = self._build_where_clauses(params, "m")
        sql = f"""
        SELECT
            team,
            COUNT(*)                                                        AS matches,
            SUM(CASE WHEN winner = team THEN 1 ELSE 0 END)                 AS wins,
            SUM(CASE WHEN winner IS NOT NULL AND winner != team THEN 1 ELSE 0 END) AS losses,
            ROUND(SUM(CASE WHEN winner = team THEN 1 ELSE 0 END)
                * 100.0 / NULLIF(COUNT(*) FILTER (WHERE winner IS NOT NULL), 0), 1) AS win_pct
        FROM (
            SELECT m.team1 AS team, m.winner, m.match_id
            FROM matches m WHERE {where}
            UNION ALL
            SELECT m.team2 AS team, m.winner, m.match_id
            FROM matches m WHERE {where}
        ) t
        GROUP BY team
        HAVING COUNT(*) >= 2
        ORDER BY win_pct DESC
        """
        # values used twice (for union)
        return query(sql, values + values)

    # ── Plot (overview / venue drill-down) ────────────────────────────────────

    def plot(self, df: pd.DataFrame, params: ModuleParams):
        if df.empty:
            return None
        if params.venue:
            # Bar chart: avg 1st vs 2nd innings by season
            fig = go.Figure()
            if "avg_1st_innings" in df.columns:
                fig.add_bar(x=df["season"].astype(str), y=df["avg_1st_innings"],
                            name="Avg 1st Innings", marker_color="#1f77b4")
                fig.add_bar(x=df["season"].astype(str), y=df["avg_2nd_innings"],
                            name="Avg 2nd Innings", marker_color="#ff7f0e")
            fig.update_layout(
                title=f"Average Innings Scores at {params.venue}",
                xaxis_title="Season", yaxis_title="Runs",
                barmode="group", height=400,
            )
            return fig
        else:
            # Top venues by matches played
            top = df.head(20)
            fig = px.scatter(
                top, x="avg_1st_innings", y="bat_first_win_pct",
                size="matches", hover_name="venue",
                color="avg_1st_innings", color_continuous_scale="RdYlGn",
                title="Venues: Avg 1st Innings Score vs Batting-First Win %",
                labels={"avg_1st_innings": "Avg 1st Innings",
                        "bat_first_win_pct": "Bat First Win %"},
            )
            return fig
