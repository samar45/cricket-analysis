"""Shared test setup. CI has no real DB: set CRICKET_TEST_NO_DB=1 locally to run the suite the same way."""

import os
from pathlib import Path

import pytest

_DEFAULT = Path(__file__).parent.parent / "data" / "cricket_analytics.duckdb"
if os.environ.get("CRICKET_TEST_NO_DB"):
    REAL_DB = _DEFAULT.parent / "__hidden_for_ci__.duckdb"  # never exists
else:
    REAL_DB = Path(os.environ.get("CRICKET_TEST_DB") or _DEFAULT)

requires_real_db = pytest.mark.skipif(not REAL_DB.exists(), reason="real DB not built")

if os.environ.get("CRICKET_TEST_NO_DB"):  # also make the app's own default DB path point nowhere
    from cricket_analytics import config

    config.load_config()
    config._config_cache["paths"]["database"] = str(REAL_DB)
