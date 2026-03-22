"""League/competition definitions for Cricket Analytics Platform.

Maps user-facing competition names to:
  - Cricsheet download key (for ingestion)
  - SQL WHERE condition (for filtering)
  - Display metadata

Only T20 formats are supported (no ODI/Test).
"""

from dataclasses import dataclass

# ── Cricsheet download keys ────────────────────────────────────────────────────
# Each maps to a Cricsheet CSV2 zip URL.
# Key is also used as the sub-folder under data/raw/cricsheet/

CRICSHEET_URLS = {
    # International T20s (all countries)
    "t20s":    "https://cricsheet.org/downloads/t20s_csv2.zip",
    # Franchise leagues
    "ipl":     "https://cricsheet.org/downloads/ipl_csv2.zip",
    "bbl":     "https://cricsheet.org/downloads/bbl_csv2.zip",
    "psl":     "https://cricsheet.org/downloads/psl_csv2.zip",
    "cpl":     "https://cricsheet.org/downloads/cpl_csv2.zip",
    "sa20":    "https://cricsheet.org/downloads/sa20_csv2.zip",
    "hundred": "https://cricsheet.org/downloads/the_hundred_csv2.zip",
    "blast":   "https://cricsheet.org/downloads/t20_blast_csv2.zip",
    "wpl":     "https://cricsheet.org/downloads/wpl_csv2.zip",
    "super_smash": "https://cricsheet.org/downloads/super_smash_csv2.zip",
}

# What format label to store in the matches table for each key
CRICSHEET_FORMAT_LABELS = {
    "t20s":        "T20",
    "ipl":         "IPL",
    "bbl":         "BBL",
    "psl":         "PSL",
    "cpl":         "CPL",
    "sa20":        "SA20",
    "hundred":     "Hundred",
    "blast":       "Blast",
    "wpl":         "WPL",
    "super_smash": "Super Smash",
}

CRICSHEET_TOURNAMENT_LABELS = {
    "t20s":        "T20I",
    "ipl":         "IPL",
    "bbl":         "Big Bash League",
    "psl":         "Pakistan Super League",
    "cpl":         "Caribbean Premier League",
    "sa20":        "SA20",
    "hundred":     "The Hundred",
    "blast":       "T20 Blast",
    "wpl":         "Women's Premier League",
    "super_smash": "Super Smash",
}


# ── Dashboard competition definitions ─────────────────────────────────────────

@dataclass(frozen=True)
class Competition:
    label: str              # shown in UI
    emoji: str
    cricsheet_key: str      # key into CRICSHEET_URLS (for download)
    # SQL filter applied to matches table (use {p} as the table prefix placeholder)
    sql_filter: str
    # Bind values for sql_filter (no placeholders needed if using literals/ILIKE)
    sql_values: tuple = ()
    description: str = ""


# Order matters — shown in this order in the UI
COMPETITIONS: list[Competition] = [
    Competition(
        label="T20 International",
        emoji="🌍",
        cricsheet_key="t20s",
        sql_filter="{p}format = 'T20'",
        description="All international T20 matches between national teams",
    ),
    Competition(
        label="IPL",
        emoji="🏏",
        cricsheet_key="ipl",
        sql_filter="({p}format = 'IPL' OR {p}tournament ILIKE '%Indian Premier%')",
        description="Indian Premier League",
    ),
    Competition(
        label="BBL",
        emoji="🦘",
        cricsheet_key="bbl",
        sql_filter="({p}format = 'BBL' OR {p}tournament ILIKE '%Big Bash%')",
        description="KFC Big Bash League (Australia)",
    ),
    Competition(
        label="PSL",
        emoji="🟢",
        cricsheet_key="psl",
        sql_filter="({p}format = 'PSL' OR {p}tournament ILIKE '%Pakistan Super%')",
        description="HBL Pakistan Super League",
    ),
    Competition(
        label="CPL",
        emoji="🌴",
        cricsheet_key="cpl",
        sql_filter="({p}format = 'CPL' OR {p}tournament ILIKE '%Caribbean Premier%')",
        description="Republic Bank Caribbean Premier League",
    ),
    Competition(
        label="SA20",
        emoji="🦁",
        cricsheet_key="sa20",
        sql_filter="({p}format = 'SA20' OR {p}tournament ILIKE '%SA20%')",
        description="Betway SA20 (South Africa)",
    ),
    Competition(
        label="The Hundred",
        emoji="💯",
        cricsheet_key="hundred",
        sql_filter="({p}format = 'Hundred' OR {p}tournament ILIKE '%Hundred%')",
        description="The Hundred (England & Wales)",
    ),
    Competition(
        label="T20 Blast",
        emoji="💥",
        cricsheet_key="blast",
        sql_filter="({p}format = 'Blast' OR {p}tournament ILIKE '%T20 Blast%' OR {p}tournament ILIKE '%Vitality Blast%')",
        description="Vitality T20 Blast (England & Wales)",
    ),
    Competition(
        label="WPL",
        emoji="👸",
        cricsheet_key="wpl",
        sql_filter="({p}format = 'WPL' OR {p}tournament ILIKE '%Women%Premier%')",
        description="Women's Premier League (India)",
    ),
]

# Fast lookup by label
COMPETITION_MAP: dict[str, Competition] = {c.label: c for c in COMPETITIONS}

ALL_LABELS = [c.label for c in COMPETITIONS]


def get_sql_filter(label: str, table_alias: str = "m") -> tuple[str, list]:
    """Return (sql_fragment, bind_values) for a competition label.

    Returns ("1=1", []) for unknown/None labels (no filter applied).
    """
    comp = COMPETITION_MAP.get(label)
    if not comp:
        return "1=1", []
    p = f"{table_alias}." if table_alias else ""
    sql = comp.sql_filter.replace("{p}", p)
    return sql, list(comp.sql_values)
