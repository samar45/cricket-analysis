# Cleanup audit (read-only), 2026-11-14

Scope: `src/cricket_analytics/` (not `web/`), `dashboard/`, `tools/`, `experiments/`, `tests/`, repo root, `docs/`. No code was changed. Method: an import scan of every `ml/` and `models/` module (src, dashboard, tests, tools, experiments), vulture 60%+ with a hand-check of each function hit, and a grep of ML_LEARNINGS section 3/5 and ML_PREDICTION. Line numbers are as of commit `99cd220`.

## Size now (Python lines, excluding web/ and frontend/)

| Folder | Lines |
|---|---|
| src/cricket_analytics/ml | 10,644 |
| src/cricket_analytics/models | 9,830 |
| src/cricket_analytics/viz | 5,318 |
| src/cricket_analytics/analysis | 4,600 |
| src/cricket_analytics/ingest | 1,887 |
| src/cricket_analytics other (api, cli, ask, facts, sql, ...) | ~3,900 |
| dashboard | 1,745 |
| tests | 9,499 |
| experiments / scripts / evals / tools | 769 / 56 / 176 / 53 |
| docs (md) | 16,249 |

Total active Python is about 48,500 lines. The list below removes roughly **3,000 lines (about 6%)** from the active tree (archived, not deleted, where results must stay reproducible).

## Ranked table

| # | what | where | evidence | action | lines saved | risk | frozen-test? |
|---|---|---|---|---|---|---|---|
| 1 | Drawing board + model zoo chain (5 modules) and their tests | `ml/drawing_board.py` 465, `drawing_board_fit.py` 489, `drawing_board_report.py` 147, `model_zoo.py` 537, `model_zoo_report.py` 164; `tests/test_ml_drawing_board.py` 40, `tests/test_ml_zoo.py` 45 | Only importers are each other (closed chain: no src, dashboard, cli or other test uses it). ML_LEARNINGS section 5: "shrinkage ruled out", zoo rows Z1-Z7 tie or worse, "drop". They import `flaw_fit`/`flaw_tests`, so those stay | archive to `experiments/archive/ml_zoo/` (tests go with it) | 1,887 | low | no |
| 2 | `ml/error_report.py` + its test | `ml/error_report.py` 319, `tests/test_ml_error_report.py` 31 | 0 importers in src/dashboard/cli; one finished report (docs/ML_ERRORS.md: no team flagged, only Chepauk) | archive | 350 | low | no |
| 3 | `ml/flaw_plot.py` | 71 lines | 0 importers, 0 tests; one-off plotting script from the flaw hunt | archive | 71 | low | no |
| 4 | Failed commentary-input models | `models/length_matchup.py` 180, `death_execution.py` 93, `drops.py` 72; tests 28+24+24 | ML_LEARNINGS section 5: commentary-derived inputs (length matchup, death execution, drop luck) failed. Only their own tests import them; `worth.py` lists `length_matchup` as an importer-side reference, so check before moving | archive after checking `worth.py` | ~420 | med | no |
| 5 | Dead functions (0 references anywhere, hand-checked) | `ml/sim_report.py:141 plots_and_breakdowns` (52), `ingest/commentary.py:233 series_ids` (22), `models/worth.py:280 ridge_check` (15), `models/rapm.py:148 seasonal` (13), `ml/luck.py:92 match_luck` (10), `ml/s4b.py:100 _cache` (7), `ml/evaluate.py:125 at_checkpoints` (6), `ml/drawing_board.py:164 _keep_s` (2), `models/backtest.py:57 _wide` (2) | grep -w across src, dashboard, tests, tools, experiments, docs finds only the `def` | delete | ~130 | low | `evaluate.py` is imported by frozen tests: run them after |
| 6 | Same helper written many times | `_logit`: `evaluate.py:229`, `luck.py:20`, `market.py:221`, `react.py:39`, `drawing_board.py:85`, plus `_sig` in `market_anchor.py:23`. Log loss: `evaluate.log_loss`, `model_zoo.ll`, `market_anchor._ll`, `react._ll`, inner `ll` in `direct.py`. Bootstrap by match: `evaluate.match_bootstrap`, `market_t34._boot`, `validate._boot_se`, `v2.py:358`, `paper.py:173`, `market_anchor.test2`, `sim_report.bootstrap`, `error_report`, `fair_report.py:276`, `flaw_tests.py:177`, `drawing_board.py:109` (the multinomial-weights trick appears 5 times) | grep for def and `default_rng` | merge into `evaluate` (already the stats home per ML_LEARNINGS section 2) | ~120 | med: a merge must give identical numbers, run the goal tests after each | **yes** (react, market*, paper) |
| 7 | Junk in repo root | `catboost_info/` (32 KB, untracked, no line for it in .gitignore) | `git status` shows it untracked | add `catboost_info/` to .gitignore, delete folder | 0 | low | no |
| 8 | Four old DB backups | `data/cricket_analytics_prev_2026-10-24`, `-11-07`, `-11-07b`, `-11-13` `.duckdb`, about 1.0 GB total | already gitignored; only the newest is needed for the old-match_id check | delete the 3 oldest after Samar OK (disk, not lines) | 0 | low | no |
| 9 | Stale WORK_*.md | `docs/WORK_*.md`, 34 files, 804 lines; 18 are 1-6 line stubs (`WORK_phase4/5/6/7`, `WORK_match_adjust`, `WORK_war_fix`, ...) dated 2026-10-25 to 11-13 | `git log` dates | move to `docs/archive/` (keep: milestone logs) | 0 (tidy) | low | no |
| 10 | Unreferenced reference CSVs | `models/data/stability_ipl2023.csv`, `stability_men_t20.csv` (2 KB each) | no filename match in any .py | delete, or note the producer | 0 | low | no |
| 11 | Unused / unsatisfiable code (vulture 100%) | `ml/sim_report.py:120` and `ml/validate.py:189` (ternary cannot differ: `... if ov else 0) if ov else 0`); unused vars `analysis/war.py:18 db_mtime`, `api.py:250 mtime`, `ask.py:219 db_key`, `ask_rules.py:128 has_true`, `prematch.py:410 xi_a/xi_b`, `backtest.py:61 scale_rate`, `matchup_model.py:656 mtime` | vulture, each checked by eye | simplify | ~15 | low | no |
| 12 | `experiments/` scripts tied to failed ideas | `worth_plus_backtest.py`, `eda_commentary.py`, `feature_repeatability.py`, `rapm_eval.py` (769 lines in the folder) | worth_plus is in ML_LEARNINGS section 5 "failed" | move to `experiments/archive/` | 0 (tidy) | low | no |

Rows 1-6 and 11 total about **3,000 lines**. `print(` in `ml/` (134) is mostly CLI report output of `python -m` runs, so not counted.

## Do not touch (and why)

- **Frozen-test modules**: `ml/market.py`, `market_anchor.py`, `market_t34.py`, `paper.py`, `react.py`, `production_refit.py`, `predict.py`, `features.py` (pinned by test_market*_goals, test_paper_goals, test_react_goals, test_production_refit_goals, test_over_under_goals, test_in_sample_goal, test_ml_features in `tests/frozen.lock`), plus `ingest/update.py` and the golden numbers. react (F1/F2) and the market tests look like finished experiments, but only Samar can release them.
- **`ml/holdout.py`, `simfix.py`, `sim_eval.py`, `sim_report.py`, `s4b.py`, `v2.py`, `validate.py`, `direct.py`, `prematch.py`, `ball_model.py`, `baselines.py`, `fair_report.py`, `flaw_fit.py`, `flaw_tests.py`, `resources.py`**: rejected experiments (simfix, v2, holdout) but still on the import path of `production_refit`, `predict`, `market` and `react`. They look dead from ML_LEARNINGS, but are not. Archiving needs the dependency chain untangled: high risk.
- **`models/backtest.py` and `value_variants.py` predictors** (about 20 functions vulture flags): used through the `@predictor` decorator, not dead.
- **`analysis/*` (death_overs, pace_vs_spin, season_awards, true_performance, underrated), `cli.py` commands, `models/availability` share_* functions**: registry or CLI decorator use, vulture false positives.
- **`models/league_translation.py`** (no importers, no tests): auction and scarcity reference the name, probably its CSV. Unsure, so high risk; left alone.
- **`logs/`** (740 KB) is gitignored; **`evals/results`** (14 JSON) are documented eval records: keep.
- Archived code must stay runnable by `python -m`: move it with its imports, or tag the commit first. Never plain-delete (ML_LEARNINGS reproducibility).

## Surprises (not chased)

- `.gitignore` is modified in the working tree (not by this audit; another worker).
- Row 6: the bootstrap weights trick is pasted 5 times, the biggest source of subtle drift if a seed or CI definition changes.
- Row 4: confirm `worth.py` does not need `length_matchup` before moving it.
