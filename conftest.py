"""Add project root to sys.path so all packages resolve correctly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
