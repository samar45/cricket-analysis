"""Tests for the module registry and base interface."""

from modules.base import BaseModule, ModuleParams, register_module, get_module, list_modules, _REGISTRY


def test_module_params_defaults():
    p = ModuleParams()
    assert p.format == "T20"
    assert p.player is None
    assert p.output == "dataframe"


def test_register_and_list_modules():
    # Ensure basic modules are imported
    import modules.basic  # noqa: F401

    mods = list_modules()
    ids = [m["id"] for m in mods]
    assert "B1" in ids
    assert "B2" in ids
    assert "B3" in ids


def test_get_module():
    import modules.basic  # noqa: F401

    m = get_module("B1")
    assert m.module_id == "B1"
    assert m.module_name == "Batting Scorecard & Career Stats"


def test_get_module_not_found():
    import pytest
    with pytest.raises(KeyError):
        get_module("Z99")
