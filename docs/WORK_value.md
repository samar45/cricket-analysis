MILESTONE: C 2026-11-06 ipl_contracts.csv written (278 rows, 10 teams, Wikipedia season pages); checks and gaps in docs/VALUE_contracts.md; 4 teams' retained totals do not reconcile with iplt20.com
MILESTONE: A1 models/run_expectancy.py built; tables fitted (11 group/era, IPL split at 2023, Blast at 2022); start-state RE matches mean first-innings total within 0.5 run.
MILESTONE: A2 analysis/runs_added.py + viz + video + tests/test_runs_added.py (19 tests) done; first-innings centred credit sums to 0.0 runs/innings.
MILESTONE: A3 docs/VALUE_step1.md written. Honest result: IPL season-to-season stability of runs_added per 100 balls is 0.06 (min 100 balls) to 0.17 (min 150), far below strike rate 0.44-0.48; bowling 0.13-0.15 vs economy 0.52-0.54.

MILESTONE: B1 models/win_prob.py written and fitted (chase logistic 38 coefficients + late-cell table, first-innings logistic 22 coefficients), JSON saved in models/data/win_prob.json.
MILESTONE: B2 out-of-sample (fit <=2023, test 2024-26): chase Brier 0.1137 vs 0.1465 (required-rate-only) vs 0.2478 (50/50); first innings 0.2027 vs 0.2483. IPL 2024-26 chase calibration is off (chasers do 10-20 points better than predicted).
MILESTONE: B3 analysis/wpa.py (players + match views), viz/wpa.py, viz/video/wpa.py, tests/test_wpa.py, docs/VALUE_step2.md written.
MILESTONE: F Impact-era test done (docs/VALUE_step2.md): isolated IPL (I) and impact-interaction (H) models do not beat the pooled model out of sample (chase Brier +0.003, real); pooled kept, no code change.
MILESTONE: E2 2026-11-06 matchup predictor finished: models/matchup_model.py refit (k in matchup_k.json, both era options), analysis/matchup_model.py renamed to analysis/matchup_predict.py, tests/test_matchup_model.py (12 tests), docs/VALUE_step4.md. Model beats league average by 0.9% log loss on IPL 2025-26; head-to-head layer adds ~0.00007 nats/ball; wicket layers beyond batter+kind are off (k_w=1e6, genuine). Default era mode = decayed (marginal, 0.002 nats).
MILESTONE: D1 2026-11-06 ra_state widened trust rule (D/L first innings, shortened chases) in run_expectancy; Bumrah 2024 = 311 balls / 20 wkts, Kohli 2016 = 973 runs; test_runs_added still 19 green.
MILESTONE: D2a models/war.py finished: runs per win 99.3 (81-125; cross-checks 104.9 and 99.5 from the WP model), replacement ~ league average (bat 0.0, bowl -3.3 per 100 balls; same-season variant far lower, documented), WAR table.
MILESTONE: D2b pWAR for IPL 2027 written (models/data/pwar_ipl_2027.csv). Red flag checked: heavy shrinkage (k 3000/1600) is what the data supports (talent SD ~6-8 vs noise ~20 runs per 100 balls); top pWAR 0.52.
MILESTONE: D2c out-of-sample 2024-26: bowlers pWAR r 0.32 vs 0.19 last-season WAR; batters r 0.06 (no skill shown, slope -0.08); team XI win share R2 0.3% (n=30) / 1.5% (n=66), nothing predicts it; realised-WAR ceiling R2 0.37-0.41. Older IPL seasons did not help (inside noise) -> weight 0.
MILESTONE: D2d analysis/war.py + viz/war.py + viz/video/war.py + tests/test_war.py (17) + docs/VALUE_step3.md done.

MILESTONE: G1 2026-11-06 models/trade.py: recent value (4/3/2/1 over Impact-era seasons, bootstrap range over own matches), best-XII search with documented rules, trade evaluation; trade_match_ra.csv reproduces season WAR (3e-7). Market 44.7 cr per win (ratio; OLS 6.4, R2 0.08).
MILESTONE: G2 analysis/trade.py (module trade, views trade/squad), viz/trade.py, viz/video/trade.py, tests/test_trade.py (22), registry MULTI_KINDS += player, dashboard/ui.py multiselect for give/get (5 lines).
MILESTONE: G3 docs/VALUE_step5.md: Pant/Kuldeep LSG +0.45 likely better, DC -0.54 likely worse; Natarajan/Ansari DC -0.22 likely worse, SRH too close; MI Hardik for Jaiswal+Punja: no change to either XII.
