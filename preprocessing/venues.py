"""Venue name normalisation — deduplicate and standardise stadium names.

Problems we solve:
  1. Renamed stadiums  (Feroz Shah Kotla → Arun Jaitley Stadium)
  2. Trailing city suffix  (Wankhede Stadium, Mumbai → Wankhede Stadium)
  3. Punctuation typos  (full-stop vs comma in Gahanga stadium)
  4. Abbreviation variants  (PCA Stadium → Punjab Cricket Association IS Bindra Stadium)

Usage:
  from preprocessing.venues import normalise_venue

  clean_name = normalise_venue("Feroz Shah Kotla")   # → "Arun Jaitley Stadium"
"""

import re

# ── Explicit alias map ────────────────────────────────────────────────────────
# Maps any raw Cricsheet venue string → canonical name.
# Add more entries here as new duplicates are discovered.

VENUE_ALIASES: dict[str, str] = {
    # ── India ──────────────────────────────────────────────────────────────
    # Feroz Shah Kotla renamed to Arun Jaitley Stadium in 2019
    "Feroz Shah Kotla":                      "Arun Jaitley Stadium",
    "Feroz Shah Kotla, Delhi":               "Arun Jaitley Stadium",
    "Arun Jaitley Stadium, Delhi":           "Arun Jaitley Stadium",

    # Wankhede
    "Wankhede Stadium, Mumbai":              "Wankhede Stadium",

    # Chepauk
    "MA Chidambaram Stadium, Chepauk, Chennai": "MA Chidambaram Stadium, Chepauk",
    "M.A. Chidambaram Stadium, Chepauk":     "MA Chidambaram Stadium, Chepauk",
    "MA Chidambaram Stadium":                "MA Chidambaram Stadium, Chepauk",

    # Eden Gardens
    "Eden Gardens, Kolkata":                 "Eden Gardens",

    # Chinnaswamy
    "M Chinnaswamy Stadium, Bengaluru":      "M Chinnaswamy Stadium",
    "M. Chinnaswamy Stadium":               "M Chinnaswamy Stadium",

    # Mohali
    "Punjab Cricket Association Stadium, Mohali": "Punjab Cricket Association IS Bindra Stadium, Mohali",
    "PCA Stadium, Mohali":                   "Punjab Cricket Association IS Bindra Stadium, Mohali",
    "Punjab Cricket Association IS Bindra Stadium": "Punjab Cricket Association IS Bindra Stadium, Mohali",

    # Rajiv Gandhi / Uppal
    "Rajiv Gandhi International Stadium":    "Rajiv Gandhi International Stadium, Uppal",
    "Rajiv Gandhi International Stadium, Hyderabad": "Rajiv Gandhi International Stadium, Uppal",

    # Holkar
    "Holkar Cricket Stadium":                "Holkar Cricket Stadium, Indore",
    "Holkar Stadium, Indore":                "Holkar Cricket Stadium, Indore",

    # HPCA Dharamsala
    "Himachal Pradesh Cricket Association Stadium":            "HPCA Stadium, Dharamsala",
    "Himachal Pradesh Cricket Association Stadium, Dharamsala": "HPCA Stadium, Dharamsala",
    "HPCA Stadium":                          "HPCA Stadium, Dharamsala",

    # DY Patil
    "Dr DY Patil Sports Academy":            "Dr. D.Y. Patil Sports Academy, Mumbai",
    "Dr DY Patil Sports Academy, Mumbai":    "Dr. D.Y. Patil Sports Academy, Mumbai",
    "Dr. DY Patil Sports Academy":           "Dr. D.Y. Patil Sports Academy, Mumbai",

    # Narendra Modi / Sardar Patel
    "Sardar Patel Stadium, Motera":          "Narendra Modi Stadium, Ahmedabad",
    "Sardar Patel Stadium":                  "Narendra Modi Stadium, Ahmedabad",

    # Sawai Mansingh
    "Sawai Mansingh Stadium, Jaipur":        "Sawai Mansingh Stadium",

    # Vidarbha
    "Vidarbha Cricket Association Stadium, Jamtha": "VCA Stadium, Nagpur",
    "Vidarbha Cricket Association Stadium":  "VCA Stadium, Nagpur",

    # ── Sri Lanka ───────────────────────────────────────────────────────────
    "R Premadasa Stadium, Colombo":          "R Premadasa Stadium",
    "Sinhalese Sports Club Ground, Colombo": "Sinhalese Sports Club Ground",
    "P Sara Oval, Colombo":                  "P Sara Oval",

    # ── Bangladesh ─────────────────────────────────────────────────────────
    "Shere Bangla National Stadium, Mirpur": "Shere Bangla National Stadium",
    "Sher-e-Bangla National Cricket Stadium, Mirpur": "Shere Bangla National Stadium",
    "Sher-e-Bangla National Cricket Stadium": "Shere Bangla National Stadium",

    # ── West Indies ─────────────────────────────────────────────────────────
    "Warner Park, Basseterre, St Kitts":     "Warner Park, Basseterre",
    "Providence Stadium, Guyana":            "Providence Stadium",
    "Sabina Park, Kingston, Jamaica":        "Sabina Park, Kingston",
    "Queen's Park Oval, Port of Spain, Trinidad": "Queen's Park Oval, Port of Spain",

    # ── Africa ─────────────────────────────────────────────────────────────
    # Punctuation typo: period instead of comma
    "Gahanga International Cricket Stadium. Rwanda": "Gahanga International Cricket Stadium, Rwanda",

    # ── Australia ──────────────────────────────────────────────────────────
    "Western Australia Cricket Association Ground":  "WACA Ground, Perth",
    "Western Australia Cricket Association Ground, Perth": "WACA Ground, Perth",
    "Brisbane Cricket Ground, Woolloongabba":         "Gabba, Brisbane",
    "Brisbane Cricket Ground":                        "Gabba, Brisbane",
    "Melbourne Cricket Ground, Melbourne":            "Melbourne Cricket Ground",
    "Sydney Cricket Ground, Sydney":                  "Sydney Cricket Ground",

    # ── Pakistan ────────────────────────────────────────────────────────────
    "Gaddafi Stadium":                       "Gaddafi Stadium, Lahore",

    # ── UAE ─────────────────────────────────────────────────────────────────
    "Sheikh Zayed Stadium, Abu Dhabi":       "Sheikh Zayed Stadium",
    "Dubai International Cricket Stadium, Dubai": "Dubai International Cricket Stadium",

    # ── West Indies (additional) ─────────────────────────────────────────────
    "Kensington Oval, Bridgetown, Barbados": "Kensington Oval, Bridgetown",
    "Kensington Oval, Barbados":             "Kensington Oval, Bridgetown",

    # ── Australia (additional) ───────────────────────────────────────────────
    "Docklands Stadium, Melbourne":          "Docklands Stadium",

    # ── India (additional) ──────────────────────────────────────────────────
    "Rajiv Gandhi International Stadium, Uppal, Hyderabad": "Rajiv Gandhi International Stadium, Uppal",
    "Sardar Patel (Gujarat) Stadium, Motera": "Narendra Modi Stadium, Ahmedabad",
    "JSCA International Stadium Complex, Ranchi": "JSCA International Stadium Complex",
    "Greenfield International Stadium, Thiruvananthapuram": "Greenfield International Stadium",
    "Shaheed Veer Narayan Singh International Stadium, Raipur": "Shaheed Veer Narayan Singh International Stadium",

    # ── England ──────────────────────────────────────────────────────────────
    "County Ground, New Road, Worcester":    "County Ground, New Road",

    # ── Bangladesh (additional) ─────────────────────────────────────────────
    "Bangabandhu National Stadium, Dhaka":   "Bangabandhu National Stadium",
}

# ── Normalisation function ────────────────────────────────────────────────────

def normalise_venue(raw: str | None) -> str | None:
    """Return the canonical venue name for a raw Cricsheet venue string."""
    if not raw or not raw.strip():
        return raw

    raw = raw.strip()

    # 1. Direct alias lookup (fastest path)
    if raw in VENUE_ALIASES:
        return VENUE_ALIASES[raw]

    # 2. Case-insensitive alias lookup
    raw_lower = raw.lower()
    for alias, canonical in VENUE_ALIASES.items():
        if alias.lower() == raw_lower:
            return canonical

    # 3. Normalise extra whitespace / non-breaking spaces
    clean = re.sub(r"\s+", " ", raw).strip()

    # 4. Return as-is if no match found
    return clean


# ── DB migration ──────────────────────────────────────────────────────────────

def migrate_venues(db_path=None) -> int:
    """Apply all alias mappings to the matches table in-place.

    Returns the number of rows updated.
    """
    from src.cricket_analytics.db import get_connection
    con = get_connection(db_path)

    total_updated = 0
    for raw, canonical in VENUE_ALIASES.items():
        if raw == canonical:
            continue
        # Count rows before update, then update
        before = con.execute(
            "SELECT COUNT(*) FROM matches WHERE venue = ?", [raw]
        ).fetchone()[0]
        if before:
            con.execute("UPDATE matches SET venue = ? WHERE venue = ?", [canonical, raw])
            total_updated += before

    con.close()
    return total_updated


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    n = migrate_venues()
    print(f"Updated {n} venue rows")
