# WORK health (worker B)
MILESTONE: 3 sample run logs in tests/fixtures/runs (pass update, failed update, health)
MILESTONE: dashboard/health.py + nav hook in app.py; verified on :8504 (sample banner, run selector), server stopped
MILESTONE: tests/test_health_page.py 3 passed; docs/RUNBOOK.md written; README linked
MILESTONE: 2026-10-25 workerC tests/conftest.py (requires_real_db, REAL_DB, CRICKET_TEST_NO_DB) + 13 test files use it; NO_DB run: 250 passed, 105 skipped
MILESTONE: 2026-10-25 workerC fixed real leak: facts.build resolved unknown player against live DB, ignoring db_path (now use_db)
MILESTONE: 2026-10-25 workerC ci.yml (lint/test/security, SHA-pinned), dependabot.yml, .pre-commit-config.yaml, docs/CI.md, pinned requirements(-dev).txt, *.duckdb ignored; ruff/pip-audit not installed so untested
MILESTONE: 2026-10-25 [A] runlog.py + update.py rewrite (steps, old_data_unchanged, golden.json, skipped_events, balls sanity, lock check), cricket health / runs, tests/test_health.py (17 tests) done
MILESTONE: 2026-10-25 [A] proof on copy: a) 0 new run 20261025-160814 ok; b) 20 deleted, re-added run 20261025-160825 ok+swapped; c) bad loader run 20261025-160841 old_data_unchanged FAIL, no swap; d) locked copy run 20261025-160846 lock_check FAIL; live health run 20261025-160859 ok (8/8 golden)
