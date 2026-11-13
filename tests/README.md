## Frozen tests
- Frozen tests check a real goal and are written first. They are never edited to make code pass.
- `tests/frozen.lock` holds a sha256 per frozen file; `tests/test_frozen_lock.py` fails if one changes or goes missing.
- If a frozen test is itself wrong: get Samar's OK, edit it, run `python tools/freeze_tests.py <path>`, commit the lock change alone with a `test-freeze:` message.
- `python tools/freeze_tests.py --list` shows entries; `--check` exits non-zero on any mismatch.
