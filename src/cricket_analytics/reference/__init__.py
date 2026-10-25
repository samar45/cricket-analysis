"""Reference data that is not in Cricsheet: player attributes (generated) and hand-kept overrides. See build_attributes.py."""

from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent
ATTRIBUTES_CSV = REFERENCE_DIR / "player_attributes.csv"
OVERRIDES_CSV = REFERENCE_DIR / "player_overrides.csv"
