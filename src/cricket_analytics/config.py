"""Centralised configuration loader. All modules read settings from here."""

from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

_config_cache: dict | None = None


def load_config(path: Path | None = None) -> dict:
    """Load and cache the YAML config file."""
    global _config_cache
    if _config_cache is not None and path is None:
        return _config_cache

    config_path = path or _CONFIG_PATH
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    if path is None:
        _config_cache = cfg
    return cfg


def get_path(key: str) -> Path:
    """Return an absolute Path for a config paths entry."""
    cfg = load_config()
    return _PROJECT_ROOT / cfg["paths"][key]


def get_db_path() -> Path:
    """Return the DuckDB database file path."""
    return get_path("database")
