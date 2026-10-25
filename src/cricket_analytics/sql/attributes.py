"""Player attributes as a SQL CTE over the two reference CSVs.

FACTS (never change with a filter): role, keeper, bowl_type (and the pace/spin implied by it), bat_hand. Keeper, bowl_type and
bat_hand come ONLY from the hand-kept overrides (player_overrides.csv); everyone else is NULL = unknown. Role is derived from
shares of team balls (broad: batter / bowler / all-rounder) unless an override sets it.
HINTS (columns `hint_*`, from the generated file): career-majority guesses (keeper, pace/spin, batting slot, phase role).
They are for finding gaps in the override list and for a "usually ..." line; never present one as a fact. How a player is
really used (batting position, phase) changes with season / competition / team, so analysis/player_profile.py computes it
at query time from the deliveries and the same Filters.

    from cricket_analytics.sql.attributes import attributes_cte
    sql = f"WITH {attributes_cte()} SELECT d.batter, pa.bat_hand FROM deliveries d JOIN pa ON pa.name = d.batter ..."

`player_attributes.csv` is generated from the data (reference/build_attributes.py). `player_overrides.csv` is kept by
hand. Join on the Cricsheet name (e.g. "JJ Bumrah"). Every fact has a `<attr>_source` (derived / manual-llm / manual /
wikidata) and a `<attr>_confidence` (high / medium / low, NULL when not applicable).
The CSVs are read at query time (read_csv), so editing an override needs no rebuild.
"""

from ..reference import ATTRIBUTES_CSV, OVERRIDES_CSV

# Fixed vocabularies (tests check the CSVs against these).
ROLES = ("batter", "bowler", "all-rounder", "unknown")
KEEPERS = ("yes", "sometimes")
BAT_SLOTS = (
    "opener",
    "top order",
    "middle",
    "finisher",
    "tail",
    "unknown",
)  # values of hint_bat_slot
BOWL_PHASE_ROLES = ("powerplay", "middle", "death", "all-phase")  # values of hint_bowl_phase_role
BOWL_KINDS = ("pace", "spin")
BOWL_TYPES = (
    "right-arm fast",
    "right-arm fast-medium",
    "right-arm medium",
    "left-arm fast",
    "left-arm fast-medium",
    "left-arm medium",
    "right-arm off spin",
    "right-arm leg spin",
    "left-arm orthodox",
    "left-arm wrist spin",
)
BAT_HANDS = ("right", "left")
CONFIDENCES = ("high", "medium", "low")


def bowl_kind_of(bowl_type: str) -> str:
    """'spin' for the spin types, 'pace' for the rest (the same rule is used in SQL below)."""
    return "spin" if any(w in bowl_type for w in ("spin", "orthodox")) else "pace"


def _lit(path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def attributes_cte(name: str = "pa") -> str:
    """`pa AS (...)`: one row per player name, generated columns with overrides applied.

    Columns: name, gender, matches, last_date, role, role_source, role_confidence, keeper, keeper_source, keeper_confidence
    (override only), bowl_type, bowl_type_source, bowl_type_confidence, bowl_kind, bowl_kind_source, bowl_kind_confidence
    (pace/spin implied by the override's bowl_type; NULL without one), bat_hand, bat_hand_source, bat_hand_confidence,
    and the guesses hint_keeper, hint_keeper_confidence, hint_bowl_kind, hint_bowl_kind_confidence, hint_bat_position,
    hint_bat_slot, hint_bat_slot_confidence, hint_bowl_phase_role.
    """
    # all_varchar: blanks are empty strings in both files; NULLIF turns them into NULL
    a = f"read_csv({_lit(ATTRIBUTES_CSV)}, header = true, all_varchar = true)"
    o = f"read_csv({_lit(OVERRIDES_CSV)}, header = true, all_varchar = true)"
    n = lambda c: f"NULLIF({c}, '')"  # noqa: E731
    # the override file may or may not carry a keeper_confidence column (the reviewed list is still being extended)
    with open(OVERRIDES_CSV, encoding="utf-8-sig") as fh:
        keeper_conf = (
            n("o.keeper_confidence")
            if "keeper_confidence" in fh.readline().strip().split(",")
            else "NULL"
        )
    return f"""{name} AS (
    SELECT COALESCE(a.name, o.name) AS name,
           {n("a.gender")} AS gender,
           TRY_CAST({n("a.matches")} AS INTEGER) AS matches,
           TRY_CAST({n("a.last_date")} AS DATE) AS last_date,
           COALESCE({n("o.role")}, {n("a.role")}) AS role,
           CASE WHEN {n("o.role")} IS NOT NULL THEN o.source ELSE {n("a.role_source")} END AS role_source,
           CASE WHEN {n("o.role")} IS NOT NULL THEN NULL ELSE {n("a.role_confidence")} END AS role_confidence,
           {n("o.keeper")} AS keeper,
           CASE WHEN {n("o.keeper")} IS NOT NULL THEN o.source END AS keeper_source,
           CASE WHEN {n("o.keeper")} IS NOT NULL THEN {keeper_conf} END AS keeper_confidence,
           {n("o.bowl_type")} AS bowl_type,
           CASE WHEN {n("o.bowl_type")} IS NOT NULL THEN o.source END AS bowl_type_source,
           CASE WHEN {n("o.bowl_type")} IS NOT NULL THEN {n("o.bowl_type_confidence")} END AS bowl_type_confidence,
           CASE WHEN {n("o.bowl_type")} IS NULL THEN NULL
                WHEN o.bowl_type LIKE '%spin%' OR o.bowl_type LIKE '%orthodox%' THEN 'spin' ELSE 'pace' END AS bowl_kind,
           CASE WHEN {n("o.bowl_type")} IS NOT NULL THEN o.source END AS bowl_kind_source,
           CASE WHEN {n("o.bowl_type")} IS NOT NULL THEN {n("o.bowl_type_confidence")} END AS bowl_kind_confidence,
           {n("o.bat_hand")} AS bat_hand,
           CASE WHEN {n("o.bat_hand")} IS NOT NULL THEN o.source END AS bat_hand_source,
           CASE WHEN {n("o.bat_hand")} IS NOT NULL THEN {n("o.bat_hand_confidence")} END AS bat_hand_confidence,
           {n("a.hint_keeper")} AS hint_keeper,
           {n("a.hint_keeper_confidence")} AS hint_keeper_confidence,
           {n("a.hint_bowl_kind")} AS hint_bowl_kind,
           {n("a.hint_bowl_kind_confidence")} AS hint_bowl_kind_confidence,
           TRY_CAST({n("a.hint_bat_position")} AS DOUBLE) AS hint_bat_position,
           {n("a.hint_bat_slot")} AS hint_bat_slot,
           {n("a.hint_bat_slot_confidence")} AS hint_bat_slot_confidence,
           {n("a.hint_bowl_phase_role")} AS hint_bowl_phase_role
    FROM {a} a FULL OUTER JOIN {o} o ON a.name = o.name
)"""
