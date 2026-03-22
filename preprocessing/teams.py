"""Team name normalisation — deduplicate and standardise franchise names.

Problems we solve:
  1. Renamed teams  (Delhi Daredevils → Delhi Capitals)
  2. Rebranded teams  (Kings XI Punjab → Punjab Kings)
  3. Typo variants  (Rising Pune Supergiant → Rising Pune Supergiants)

Usage:
  from preprocessing.teams import normalise_team

  clean_name = normalise_team("Delhi Daredevils")   # → "Delhi Capitals"
"""

# ── Explicit alias map ────────────────────────────────────────────────────────
# Maps any raw Cricsheet team string → canonical name.
# Add more entries here as new duplicates are discovered.

TEAM_ALIASES: dict[str, str] = {
    # ── IPL renames ──────────────────────────────────────────────────────────
    # Delhi franchise: renamed from Daredevils to Capitals in 2019
    "Delhi Daredevils":                     "Delhi Capitals",

    # Punjab franchise: rebranded from Kings XI Punjab to Punjab Kings in 2021
    "Kings XI Punjab":                      "Punjab Kings",

    # Royal Challengers: city name change Bangalore → Bengaluru in 2024
    "Royal Challengers Bangalore":          "Royal Challengers Bengaluru",

    # Rising Pune: typo variant (missing final 's')
    "Rising Pune Supergiant":               "Rising Pune Supergiants",
}


# ── Normalisation function ────────────────────────────────────────────────────

def normalise_team(raw: str | None) -> str | None:
    """Return the canonical team name for a raw Cricsheet team string."""
    if not raw or not raw.strip():
        return raw

    raw = raw.strip()

    # 1. Direct alias lookup (fastest path)
    if raw in TEAM_ALIASES:
        return TEAM_ALIASES[raw]

    # 2. Case-insensitive alias lookup
    raw_lower = raw.lower()
    for alias, canonical in TEAM_ALIASES.items():
        if alias.lower() == raw_lower:
            return canonical

    # 3. Return as-is if no match found
    return raw


# ── DB migration ──────────────────────────────────────────────────────────────

def migrate_teams(db_path=None) -> int:
    """Apply all alias mappings to the matches table in-place.

    Updates team1, team2, and winner columns.
    Returns the number of rows updated.
    """
    from src.cricket_analytics.db import get_connection
    con = get_connection(db_path)

    total_updated = 0
    for raw, canonical in TEAM_ALIASES.items():
        if raw == canonical:
            continue
        for col in ("team1", "team2", "winner"):
            before = con.execute(
                f"SELECT COUNT(*) FROM matches WHERE {col} = ?", [raw]
            ).fetchone()[0]
            if before:
                con.execute(
                    f"UPDATE matches SET {col} = ? WHERE {col} = ?", [canonical, raw]
                )
                total_updated += before

    con.close()
    return total_updated


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    n = migrate_teams()
    print(f"Updated {n} team rows")
