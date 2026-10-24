"""One definition per cricket stat, as SQL snippets. Every analysis module builds from these.

Convention: `deliveries` is aliased `d`, `matches` is aliased `m` (snippets hard-code `d.`).
Economy everywhere = runs conceded * 6 / legal balls. Strike rate = batter runs * 100 / BALL_FACED.
"""

# A ball the batter faced: everything except a wide. (A no-ball IS faced.)
BALL_FACED = "(d.wides = 0)"

# A ball that counts towards the over: not a wide, not a no-ball.
LEGAL_BALL = "(d.wides = 0 AND d.noballs = 0)"

# Runs charged to the bowler: bat runs + wides + no-balls. Byes, leg-byes and penalty runs are not his.
RUNS_CONCEDED = "(d.runs_batter + d.wides + d.noballs)"

# Dismissals credited to the bowler: everything except run outs, retirements, obstructing the field and
# hitting the ball twice (1 row). ('retired not out' is not a dismissal at all.)
_NOT_BOWLER = ("'run out', 'retired hurt', 'retired out', 'retired not out', "
               "'obstructing the field', 'hit the ball twice'")
BOWLER_WICKET = f"(d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ({_NOT_BOWLER}))"

# `player_out` left the crease dismissed on this ball (any way except retired hurt / retired not out).
# It may be the STRIKER or the NON-STRIKER (non-striker run outs are 5,345 balls in the data), so count
# an innings' dismissal by grouping on d.player_out, never on d.batter:
#   SELECT d.player_out AS batter, match_id, innings FROM deliveries d WHERE DISMISSAL
DISMISSAL = "(d.player_out IS NOT NULL AND d.wicket_type NOT IN ('retired hurt', 'retired not out'))"

# The striker (d.batter) was the one dismissed on this ball. Use it only for ball-level questions such as
# "batter X dismissed by bowler Y"; for innings/average counts use DISMISSAL grouped by player_out.
BATTER_OUT = f"({DISMISSAL[1:-1]} AND d.player_out = d.batter)"

# Dot ball: a delivery with no runs of any kind (no bat runs, extras, wides or no-balls).
IS_DOT = "(d.runs_total = 0 AND d.wides = 0 AND d.noballs = 0)"

# Boundaries as the batter hit them (runs_batter 4 or 6; an all-run 4 is indistinguishable in Cricsheet).
IS_FOUR = "(d.runs_batter = 4)"
IS_SIX = "(d.runs_batter = 6)"


def phase_sql(d: str = "d", m: str = "m") -> str:
    """CASE expression giving 'powerplay' / 'middle' / 'death' for a delivery.

    6-ball overs (T20): overs 0-5 / 6-14 / 15-19 (first 6 overs, last 5 overs).
    The Hundred (balls_per_over = 5, Cricsheet groups it in 20 sets of 5): sets 0-4 / 5-14 / 15-19,
    i.e. the first 25 balls are powerplay and the last 25 are death.
    """
    pp = f"CASE WHEN {m}.balls_per_over = 5 THEN 5 ELSE 6 END"
    return (f"(CASE WHEN {d}.over_num < {pp} THEN 'powerplay' "
            f"WHEN {d}.over_num < 15 THEN 'middle' ELSE 'death' END)")


PHASES = ("powerplay", "middle", "death")


# One row per match with the winner and who batted first. Use as `WITH mo AS ({MATCH_OUTCOME})`.
#  - winner: matches.winner. Ingest stores the tie-break winner (super over / bowl-out) there, with result = 'tie'
#    and outcome_method = 'super over' / 'bowl out'. NULL only for no-results and ties with no tie-break.
#  - bat_first: batting_team of innings 1 (NOT team1 and NOT derived from the toss).
MATCH_OUTCOME = """
    SELECT m.match_id, m.winner, i1.bat_first
    FROM matches m
    LEFT JOIN (SELECT match_id, any_value(batting_team) AS bat_first
               FROM deliveries WHERE innings = 1 GROUP BY match_id) i1 ON i1.match_id = m.match_id
"""
