"""SQL select-lists shared by the Phase 2C modules (compare, true_performance, season_awards, death_overs, pace_vs_spin).

Built only from `fragments`, so a stat is still defined once. Convention as in fragments: `deliveries d`, `matches m`.
"""

from .fragments import BALL_FACED, BOWLER_WICKET, IS_DOT, IS_FOUR, IS_SIX, LEGAL_BALL, RUNS_CONCEDED


def ratio(num: str, den: str, mult: float = 1.0, nd: int = 2) -> str:
    """ROUND(num * mult / den, nd), NULL when den is 0."""
    return f"ROUND(({num}) * {mult} / NULLIF(({den}), 0), {nd})"


def bat_cols(prefix: str = "", when: str = "TRUE") -> str:
    """Aggregates of one batter's balls: {prefix}runs/balls/fours/sixes/dots, counting only rows where `when` holds.

    No dismissals here: a non-striker run out is not on the striker's ball. Use sql.innings.batter_innings for averages.
    """
    n = lambda cond: f"COUNT(*) FILTER (WHERE ({when}) AND {cond})::INTEGER"  # noqa: E731
    return (
        f"COALESCE(SUM(d.runs_batter) FILTER (WHERE {when}), 0)::INTEGER AS {prefix}runs, "
        f"{n(BALL_FACED)} AS {prefix}balls, {n(IS_FOUR)} AS {prefix}fours, {n(IS_SIX)} AS {prefix}sixes, "
        f"{n(IS_DOT)} AS {prefix}dots"
    )


def bowl_cols(prefix: str = "", when: str = "TRUE") -> str:
    """Aggregates of one bowler's balls: {prefix}runs_conceded/legal_balls/faced/wickets/dots/boundaries.

    faced = balls the batters faced (legal + no-balls), the denominator of boundary_pct as in the bowling module."""
    n = lambda cond: f"COUNT(*) FILTER (WHERE ({when}) AND {cond})::INTEGER"  # noqa: E731
    return (
        f"COALESCE(SUM{RUNS_CONCEDED} FILTER (WHERE {when}), 0)::INTEGER AS {prefix}runs_conceded, "
        f"{n(LEGAL_BALL)} AS {prefix}legal_balls, {n(BALL_FACED)} AS {prefix}faced, {n(BOWLER_WICKET)} AS {prefix}wickets, "
        f"{n(IS_DOT)} AS {prefix}dots, {n(f'({IS_FOUR} OR {IS_SIX})')} AS {prefix}boundaries"
    )
