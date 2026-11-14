"""Reference data that is not in Cricsheet: player attributes (generated) and hand-kept overrides. See build_attributes.py."""

from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent
ATTRIBUTES_CSV = REFERENCE_DIR / "player_attributes.csv"
OVERRIDES_CSV = REFERENCE_DIR / "player_overrides.csv"


def team_short(name: str) -> str:
    """Short code for a team: 'Gujarat Titans' -> 'GT'. From team_short.csv; otherwise the first letters of each word
    (one word: its first 3 letters), upper case."""
    import csv

    global _SHORT
    if _SHORT is None:
        with open(REFERENCE_DIR / "team_short.csv", encoding="utf-8", newline="") as f:
            _SHORT = {r["name"]: r["short"] for r in csv.DictReader(f)}
    n = str(name).strip()
    if n in _SHORT:
        return _SHORT[n]
    words = [w for w in n.replace("&", " ").split() if w.lower() not in ("and", "of")]
    return ("".join(w[0] for w in words) if len(words) > 1 else n[:3]).upper()


_SHORT: dict | None = None
