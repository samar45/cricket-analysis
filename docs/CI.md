# CI and checks

The DuckDB file (253 MB) is gitignored and never in CI. CI runs only the fixture-based tests; the ~105 real-DB tests (golden numbers, dashboard, facts on real data) skip there. Run them locally.

## What runs where

| Where | What |
|---|---|
| GitHub Actions `.github/workflows/ci.yml` (push + PR to `main`, `overhaul`) | `lint` (ruff check; ruff format is advisory), `test` (pytest with `CRICKET_TEST_NO_DB=1`), `security` (pip-audit on `requirements.txt`, gitleaks secrets scan over full history) |
| Your machine | the full suite with the real DB, golden numbers, dashboard, `cricket update` |
| Dependabot (`.github/dependabot.yml`) | weekly PRs for pip pins and action SHAs |
| pre-commit (optional) | ruff, whitespace, private keys, blocks `*.duckdb` and files > 5 MB |

Actions are pinned by full commit SHA (comment = version). Dependabot keeps them current.

## Same checks by hand (Windows, from the project root)

```
.venv\Scripts\python -m pip install -r requirements-dev.txt     # once
.venv\Scripts\python -m pytest -q                                # full suite, real DB
set CRICKET_TEST_NO_DB=1 && .venv\Scripts\python -m pytest -q -rs   # exactly what CI runs (cmd; PowerShell: $env:CRICKET_TEST_NO_DB=1)
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .                    # advisory in CI
.venv\Scripts\python -m pip_audit -r requirements.txt
```

`CRICKET_TEST_NO_DB=1` hides the real DB from the tests and from the app's default path, so a test that secretly depended on it fails. Without it the whole suite uses the real DB when present. `CRICKET_TEST_DB=<path>` points the tests at another DB file.

Optional pre-commit: `pip install pre-commit` then `pre-commit install`.

## GitHub settings to click (Settings > Branches > Add rule for `main`)

- Require a pull request before merging; require status checks `lint`, `test`, `security` to pass (they appear after the first CI run).
- Require branches to be up to date; block force pushes; block deletions.
- Settings > Actions > General: workflow permissions = read only; Settings > Code security: enable Dependabot alerts and secret scanning (free on public repos).
- Git LFS: CI checks out without LFS on purpose (saves quota).

## Releases (later, only if wanted)

Tag `vX.Y.Z` on `main` (`git tag v0.2.0 && git push --tags`) and create a GitHub Release from the tag. A tag-triggered workflow could build a wheel (`python -m build`), but nothing needs that yet.

## Secrets

None are used. Test-only env vars: `CRICKET_TEST_NO_DB`, `CRICKET_TEST_DB`; runtime: `CRICKET_RUNS_DIR` (run-log folder, default `data/runs`). So no `.env.example`.
