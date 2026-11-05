MILESTONE: C 2026-11-06 ipl_contracts.csv written (278 rows, 10 teams, Wikipedia season pages); checks and gaps in docs/VALUE_contracts.md; 4 teams' retained totals do not reconcile with iplt20.com
MILESTONE: A1 models/run_expectancy.py built; tables fitted (11 group/era, IPL split at 2023, Blast at 2022); start-state RE matches mean first-innings total within 0.5 run.
MILESTONE: A2 analysis/runs_added.py + viz + video + tests/test_runs_added.py (19 tests) done; first-innings centred credit sums to 0.0 runs/innings.
MILESTONE: A3 docs/VALUE_step1.md written. Honest result: IPL season-to-season stability of runs_added per 100 balls is 0.06 (min 100 balls) to 0.17 (min 150), far below strike rate 0.44-0.48; bowling 0.13-0.15 vs economy 0.52-0.54.

MILESTONE: B1 models/win_prob.py written and fitted (chase logistic 38 coefficients + late-cell table, first-innings logistic 22 coefficients), JSON saved in models/data/win_prob.json.
MILESTONE: B2 out-of-sample (fit <=2023, test 2024-26): chase Brier 0.1137 vs 0.1465 (required-rate-only) vs 0.2478 (50/50); first innings 0.2027 vs 0.2483. IPL 2024-26 chase calibration is off (chasers do 10-20 points better than predicted).
MILESTONE: B3 analysis/wpa.py (players + match views), viz/wpa.py, viz/video/wpa.py, tests/test_wpa.py, docs/VALUE_step2.md written.
