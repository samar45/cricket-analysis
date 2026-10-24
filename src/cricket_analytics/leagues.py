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
    # International T20s (all countries — men)
    "t20s":    "https://cricsheet.org/downloads/t20s_csv2.zip",
    # Franchise leagues (verified 200 OK as of 2026-03)
    "ipl":     "https://cricsheet.org/downloads/ipl_csv2.zip",
    "bbl":     "https://cricsheet.org/downloads/bbl_csv2.zip",
    "psl":     "https://cricsheet.org/downloads/psl_csv2.zip",
    "cpl":     "https://cricsheet.org/downloads/cpl_csv2.zip",
    "sa20":    "https://cricsheet.org/downloads/sat_male_csv2.zip",    # SA20 slug = "sat"
    "hundred": "https://cricsheet.org/downloads/hnd_male_csv2.zip",    # Hundred slug = "hnd"
    "blast":   "https://cricsheet.org/downloads/ntb_male_csv2.zip",    # NatWest/Vitality T20 Blast = "ntb"
}

# Value of the legacy matches.format column for each key. Kept identical to the old DB
# (IPL was stored as "T20"). The correct labels are matches.competition + matches.gender.
CRICSHEET_FORMAT_LABELS = {
    "t20s":    "T20",
    "ipl":     "T20",
    "bbl":     "BBL",
    "psl":     "PSL",
    "cpl":     "CPL",
    "sa20":    "SA20",
    "hundred": "Hundred",
    "blast":   "Blast",
}

# Cricsheet key -> matches.competition value (only t20s differs)
COMPETITION_CODES = {k: ("t20i" if k == "t20s" else k) for k in CRICSHEET_URLS}

CRICSHEET_TOURNAMENT_LABELS = {
    "t20s":    "T20I",
    "ipl":     "IPL",
    "bbl":     "Big Bash League",
    "psl":     "Pakistan Super League",
    "cpl":     "Caribbean Premier League",
    "sa20":    "SA20",
    "hundred": "The Hundred",
    "blast":   "Vitality T20 Blast",
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
        sql_filter="({p}competition = 't20i' AND {p}gender = 'male')",
        description="Men's international T20 matches between national teams",
    ),
    Competition(
        label="T20 International (Women)",
        emoji="🌍",
        cricsheet_key="t20s",
        sql_filter="({p}competition = 't20i' AND {p}gender = 'female')",
        description="Women's international T20 matches between national teams",
    ),
    Competition(
        label="IPL",
        emoji="🏏",
        cricsheet_key="ipl",
        sql_filter="({p}competition = 'ipl' AND {p}gender = 'male')",
        description="Indian Premier League",
    ),
    Competition(
        label="BBL",
        emoji="🦘",
        cricsheet_key="bbl",
        sql_filter="({p}competition = 'bbl' AND {p}gender = 'male')",
        description="KFC Big Bash League (Australia)",
    ),
    Competition(
        label="PSL",
        emoji="🟢",
        cricsheet_key="psl",
        sql_filter="({p}competition = 'psl' AND {p}gender = 'male')",
        description="HBL Pakistan Super League",
    ),
    Competition(
        label="CPL",
        emoji="🌴",
        cricsheet_key="cpl",
        sql_filter="({p}competition = 'cpl' AND {p}gender = 'male')",
        description="Republic Bank Caribbean Premier League",
    ),
    Competition(
        label="SA20",
        emoji="🦁",
        cricsheet_key="sa20",
        sql_filter="({p}competition = 'sa20' AND {p}gender = 'male')",
        description="Betway SA20 (South Africa)",
    ),
    Competition(
        label="The Hundred",
        emoji="💯",
        cricsheet_key="hundred",
        sql_filter="({p}competition = 'hundred' AND {p}gender = 'male')",
        description="The Hundred (England & Wales)",
    ),
    Competition(
        label="T20 Blast",
        emoji="💥",
        cricsheet_key="blast",
        sql_filter="({p}competition = 'blast' AND {p}gender = 'male')",
        description="Vitality T20 Blast (England & Wales)",
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
