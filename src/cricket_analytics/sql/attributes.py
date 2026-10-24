"""Player attributes (role, keeper, batting slot, bowling type, batting hand) as a SQL CTE over the two reference CSVs.

    from cricket_analytics.sql.attributes import attributes_cte
    sql = f"WITH {attributes_cte()} SELECT d.batter, pa.bat_hand FROM deliveries d JOIN pa ON pa.name = d.batter ..."

`player_attributes.csv` is generated from the data (reference/build_attributes.py). `player_overrides.csv` is kept by
hand and wins column by column. Join on the Cricsheet name (e.g. "JJ Bumrah"). Every attribute has a `<attr>_source`
(derived / manual-llm / manual / wikidata) and a `<attr>_confidence` (high / medium / low, '' when not applicable).
The CSVs are read at query time (read_csv), so editing an override needs no rebuild.
"""

from ..reference import ATTRIBUTES_CSV, OVERRIDES_CSV

# Fixed vocabularies (tests check the CSVs against these).
ROLES = ("batter", "bowler", "all-rounder", "unknown")
KEEPERS = ("yes", "sometimes")
BAT_SLOTS = ("opener", "top order", "middle", "finisher", "tail", "unknown")
BOWL_PHASE_ROLES = ("powerplay", "middle", "death", "all-phase")
BOWL_KINDS = ("pace", "spin")
BOWL_TYPES = ("right-arm fast", "right-arm fast-medium", "right-arm medium", "left-arm fast", "left-arm fast-medium",
              "left-arm medium", "right-arm off spin", "right-arm leg spin", "left-arm orthodox", "left-arm wrist spin")
BAT_HANDS = ("right", "left")
CONFIDENCES = ("high", "medium", "low")


def bowl_kind_of(bowl_type: str) -> str:
    """'spin' for the spin types, 'pace' for the rest (the same rule is used in SQL below)."""
    return "spin" if any(w in bowl_type for w in ("spin", "orthodox")) else "pace"


def _lit(path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def attributes_cte(name: str = "pa") -> str:
    """`pa AS (...)`: one row per player name, generated attributes with overrides applied.

    Columns: name, gender, matches, last_date, role, role_source, role_confidence, keeper, keeper_source,
    keeper_confidence, bat_position, bat_slot, bat_slot_source, bat_slot_confidence, bowl_phase_role, bowl_type,
    bowl_type_source, bowl_type_confidence, bowl_kind, bowl_kind_source, bowl_kind_confidence, bat_hand,
    bat_hand_source, bat_hand_confidence.
    """
    # all_varchar: blanks are empty strings in both files; NULLIF turns them into NULL
    a = f"read_csv({_lit(ATTRIBUTES_CSV)}, header = true, all_varchar = true)"
    o = f"read_csv({_lit(OVERRIDES_CSV)}, header = true, all_varchar = true)"
    n = lambda c: f"NULLIF({c}, '')"  # noqa: E731
    return f"""{name} AS (
    SELECT COALESCE(a.name, o.name) AS name,
           {n('a.gender')} AS gender,
           TRY_CAST({n('a.matches')} AS INTEGER) AS matches,
           TRY_CAST({n('a.last_date')} AS DATE) AS last_date,
           COALESCE({n('o.role')}, {n('a.role')}) AS role,
           CASE WHEN {n('o.role')} IS NOT NULL THEN o.source ELSE {n('a.role_source')} END AS role_source,
           CASE WHEN {n('o.role')} IS NOT NULL THEN NULL ELSE {n('a.role_confidence')} END AS role_confidence,
           COALESCE({n('o.keeper')}, {n('a.keeper')}) AS keeper,
           CASE WHEN {n('o.keeper')} IS NOT NULL THEN o.source ELSE {n('a.keeper_source')} END AS keeper_source,
           CASE WHEN {n('o.keeper')} IS NOT NULL THEN NULL ELSE {n('a.keeper_confidence')} END AS keeper_confidence,
           TRY_CAST({n('a.bat_position')} AS DOUBLE) AS bat_position,
           {n('a.bat_slot')} AS bat_slot,
           {n('a.bat_slot_source')} AS bat_slot_source,
           {n('a.bat_slot_confidence')} AS bat_slot_confidence,
           {n('a.bowl_phase_role')} AS bowl_phase_role,
           {n('o.bowl_type')} AS bowl_type,
           CASE WHEN {n('o.bowl_type')} IS NOT NULL THEN o.source END AS bowl_type_source,
           CASE WHEN {n('o.bowl_type')} IS NOT NULL THEN {n('o.bowl_type_confidence')} END AS bowl_type_confidence,
           -- pace/spin: from the hand-kept bowling type when there is one, else the derived guess
           CASE WHEN {n('o.bowl_type')} IS NOT NULL
                THEN (CASE WHEN o.bowl_type LIKE '%spin%' OR o.bowl_type LIKE '%orthodox%' THEN 'spin' ELSE 'pace' END)
                ELSE {n('a.bowl_kind')} END AS bowl_kind,
           CASE WHEN {n('o.bowl_type')} IS NOT NULL THEN o.source ELSE {n('a.bowl_kind_source')} END AS bowl_kind_source,
           CASE WHEN {n('o.bowl_type')} IS NOT NULL THEN {n('o.bowl_type_confidence')} ELSE {n('a.bowl_kind_confidence')} END AS bowl_kind_confidence,
           {n('o.bat_hand')} AS bat_hand,
           CASE WHEN {n('o.bat_hand')} IS NOT NULL THEN o.source END AS bat_hand_source,
           CASE WHEN {n('o.bat_hand')} IS NOT NULL THEN {n('o.bat_hand_confidence')} END AS bat_hand_confidence
    FROM {a} a FULL OUTER JOIN {o} o ON a.name = o.name
)"""
