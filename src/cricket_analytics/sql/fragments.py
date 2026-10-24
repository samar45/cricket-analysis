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

# Dismissals credited to the bowler: everything except run outs, retirements and obstructing the field.
# ('retired not out' is not a dismissal at all.)
_NOT_BOWLER = "'run out', 'retired hurt', 'retired out', 'retired not out', 'obstructing the field'"
BOWLER_WICKET = f"(d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ({_NOT_BOWLER}))"

# The striker was dismissed on this ball, any way except retired hurt / retired not out.
# Known gap: a non-striker run out has player_out != batter, so it is not counted for either man.
BATTER_OUT = "(d.player_out = d.batter AND d.wicket_type NOT IN ('retired hurt', 'retired not out'))"

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
