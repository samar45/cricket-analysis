"""Hard lock: frozen goal tests must not change unless Samar OKs it and the lock is refreshed."""

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "tests" / "frozen.lock"


def _entries():
    return [ln.split("  ", 1)[::-1] for ln in LOCK.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_lock_file_exists_and_is_not_empty():
    assert LOCK.exists() and _entries(), "tests/frozen.lock is missing or empty"


@pytest.mark.parametrize("path,expected", _entries() if LOCK.exists() else [])
def test_frozen_file_unchanged(path, expected):
    f = ROOT / path
    assert f.exists(), f"Frozen test missing: {path}. It was deleted or renamed; see tests/README.md."
    got = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert got == expected, (
        f"Frozen test changed: {path}. Frozen tests must not be edited to make code pass. "
        f"If the test itself is wrong, get Samar's OK, then run `python tools/freeze_tests.py {path}` "
        "and commit the lock change alone with a 'test-freeze:' message."
    )
