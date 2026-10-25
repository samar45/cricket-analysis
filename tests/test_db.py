"""Tests for database schema and connection."""


import pytest

from cricket_analytics.db import get_connection, init_schema


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary DuckDB for testing."""
    db_path = tmp_path / "test.duckdb"
    return db_path


def test_init_schema_creates_tables(temp_db):
    init_schema(temp_db)
    con = get_connection(temp_db)
    tables = con.execute("SHOW TABLES").fetchdf()["name"].tolist()
    con.close()

    assert "matches" in tables
    assert "deliveries" in tables
    assert "players" in tables


def test_init_schema_is_idempotent(temp_db):
    init_schema(temp_db)
    init_schema(temp_db)  # Should not raise
    con = get_connection(temp_db)
    tables = con.execute("SHOW TABLES").fetchdf()["name"].tolist()
    con.close()
    assert sorted(tables) == ["deliveries", "matches", "players"]
