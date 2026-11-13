# ML prediction: learnings and decision log

**Purpose:** to stop us going in circles. Read this **before** starting any new ML idea.
- Each entry says what we tried, the measured result, the decision and why, and whether to try it again.
- Detailed numbers live in `docs/ML_PREDICTION.md` §9 (dated entries), `docs/ML_ERRORS.md` and `docs/WORK_ml.md`.
- **Rule:** append a line here whenever an experiment finishes, including failed ones.

---

## 1. Goal
Predict a T20 match from any point in it:
- first-innings final score as a range (10/50/90%)
- chase win probability
- a pre-match view

Judge it on real, unseen matches. Cricket is random, so the job is to be **calibrated** (honest percentages) rather than "always right".

## 2. Rules of the game (why we test the way we do)
| Rule | Why |
|---|---|
| Train on earlier seasons, test on a later one (rolling over 2022, 23, 24, 25) | We want to forecast unseen seasons. A random split leaks the future: the model would already have seen a team's form change that season. |
| Whole matches stay on one side of the split | Balls from one match on both sides make the model look far better than it is. |
| Every input uses only matches **before** the match date | No peeking. A test enforces this. |
| Pass rules are **written down before** opening a locked test set, and each set is run once | Stops us tuning to the answer. |
| Bootstrap over matches, **two-sided 95%** (was 5–95%, which is only a 90% interval), **and** a season-block bootstrap (or per-season sign consistency) for every comparison (`evaluate.match_bootstrap`, `season_block_bootstrap`) | Small gains are usually noise, and the main error is season-level drift that a match bootstrap cannot see. "Better" only counts if both intervals exclude 0. |
| Calibration is judged by `evaluate.calibration_test`: intercept and slope with 95% intervals (primary), ECE against its own null (secondary). **No fixed ECE limit.** | A perfectly calibrated model fails "ECE < 0.08" about 98% of the time at n ≈ 70. "70%" must still mean about 70%, but we test it with the right yardstick. |
| Set the sample size from a power calculation before a locked set is run (`evaluate.power_n`): about 550-780 decided chases for a 0.01 log-loss gain, 190-650 first innings for 0.3 runs | A set that is too small is spent on a predetermined "no difference". Below the size, do not score it, not even an "indicative" read. |
| Count every variant tried on a bench and use Holm (`evaluate.holm`) or the 95% interval; about 110 families so far | About 1 in 20 null variants shows a "*" win on a 5–95% interval. |
| The model zoo and other exploratory runs never feed a locked set | No "winner" hooks. |
| A change is kept only if it is not worse overall **and** fixes something real, or is better overall outside noise. It must also hold on non-IPL leagues. | Stops overfitting to the IPL. |

Locked test sets so far:
- **IPL 2026**: used 13 Nov 2026, for v1.
- **Non-IPL men's leagues from 2026-01-01**: used 13 Nov 2026, for v1 vs v2.
- **The pre-match model** used the non-IPL set once as its own first test.
- **Both sets are now spent.**
- **Fresh set #3** (men's from 2026-10-15; T20Is only between the 12 full members): locked and pre-registered in `ML_PREDICTION.md` §9. On 13 Nov it held only 6 matches, so it is saved, not run. It grows as new data is pulled (BBL from mid-December 2026).

## 3. Timeline and decisions
| Date | Step | Result (measured) | Decision and why |
|---|---|---|---|
| 13 Nov | S0 dataset | 2.64M ball states across 14 competitions; IPL first-innings average 171 → 196 (2022–26) | Scoring drift is the main issue, so every model needs a "current scoring level" input |
| 13 Nov | S1 baselines | Best was the DLS-style resource table: MAE 18.1, chase log loss 0.488, 10–15 runs too low | This is the bar to beat |
| 13 Nov | S3/S4 LightGBM, era pools | All men's leagues beats IPL-only (MAE 16.7), and beats the impact-era-only and 2020+ pools | **Use the global pool.** More data beats era purity; the era goes in as an input. |
| 13 Nov | S4 hierarchy (team/venue effects) | None, shrunk and raw effects all tie | Team/venue effects add nothing measurable. Kept, but not a lever. **Don't retry** without a new reason. |
| 13 Nov | S2 ball simulator | MAE 18.4 vs 20.9 baseline; well calibrated | Keep. A linear scoring-level term fixes the drift that trees can't extrapolate. |
| 13 Nov | S4b, G1 | Level-relative target, no season_year, conformal ranges: bias −4.4 → −0.6, coverage 0.82 | Keep as G1 |
| 13 Nov | S5 head-to-head | G1 ties the simulator; their average (ens-G1) is best. Noise floor: 3% explainable at ball 0, 45% after 6 overs, 86% after 15 | Production = ens-G1. **Deep learning (GRU) skipped**: at or near the noise ceiling, and the learning curve is flat. |
| 13 Nov | IPL 2026 holdout | 4 of 5 pass rules met; failed on ECE 0.117 (limit 0.08) | Cause: chasers won 64% vs about 50% before. A real season shift, not a bug. |
| 13 Nov | v2 (monotone chase model, chase-rate drift, stacking) | A "chase rate so far" input carried no signal. Monotone constraints are a small, safe gain. | v2 built |
| 13 Nov | Simulator overshoot | +8 runs in 2026: player strength rose with the era, so the era was counted twice. 8 fixes tried, none better on 2022–25. | Simulator unchanged. Don't tune on a seen season. |
| 13 Nov | Fresh non-IPL 2026 test | v1 passes (ECE 0.046); v2 only ties (log loss 0.426 vs 0.428) | **v1 stays in production.** The model generalises beyond the IPL. |
| 13 Nov | Pre-match model | About a coin flip (59% correct, log loss 0.684 vs 0.693); IPL team ratings failed from 2022 on | The pre-match tab is a rough guide only. Before the toss, T20 is near 50/50. |
| 13 Nov | Error report | No team flagged. Only Chepauk flagged (+9 runs). Extremes shrink toward the middle. | Chepauk: its scoring has changed (155 → 188), so a venue effect that leans on recent seasons is worth trying |
| 13 Nov | Event tests | After a collapse, +10.8 runs too high. Powerplay is about 0% predictable pre-match. | Early-innings error is luck. The collapse problem is a real flaw. |
| 13 Nov | Flaw hunt, 9 situations | Under-reaction is generic (IPL and 9 other leagues): collapse, rrr ≥ 13, wickets in hand late, new pair | Flaws confirmed |
| 13 Nov | Momentum windows (6/12/18/30 balls) | All about the same, and "no window" as good. Lead's check: momentum adds about 1 point of R² for the next 12 balls; a recent wicket costs about 1 extra run | Momentum is real but tiny. **Not the fix.** Don't retry windows on their own. |
| 13 Nov | Partnership, wickets × balls, balls since wicket, recent venue | No event bias removed | Dropped |
| 13 Nov | G2 (early stopping on all competitions of season Y-1) | Chase log loss −0.011, coverage better, collapse bias about a quarter smaller | Candidate. **Clue:** fitting harder helps, so the model may be shrunk. |
| 13 Nov | "Who is left" (XI resources) in LightGBM, R1–R3 | Collapse bias **not** fixed; batting + bowling slightly better on non-IPL (MAE −0.13) | Information about who is left isn't the main cause, or our estimate of it is too rough |
| 13 Nov | G3 final (who-is-left + windows + strength sources) | R3 vs G2: IPL MAE −0.07 (noise), non-IPL −0.13* (0.8%); IPL 2026 chase log loss worse (+0.018*). Collapse bias unchanged (IPL +11.5 → +12.9). Last-12-ball window tiny (0.3%). WAR as strength slightly worse; 1–100 ratings lose a little information (keep for display). | **G3 dropped, G2 stays the candidate.** About 10 variants tried on the same data, so any single small "win" is optimistic. XI is rebuilt from deliveries (no XI table: 70% of sides have exactly 11). |
| 13 Nov | Simulator with real remaining XI (sim-R) | IPL: worse (MAE +0.2, log loss +0.024; 2026 MAE +1.2); no event bias shrank. Bowlers-only is neutral. Batters-only adds about +5 runs: the queued real batters average 1.39–1.43 runs/ball vs 1.31–1.34 generic. Wickets are unchanged (6.47 vs 6.42 actual). | **Dropped.** The real lower order is not weaker than the generic one, so "average batter hides a weak tail" is false. Small-sample career rates for lower-order hitters also look too high. Non-IPL not run (it already failed the keep rule). |
| 13 Nov | Drawing board D1/D2 | Calibration slope only 1.06 (mild shrink). A model-free fine historical lookup keeps about half the collapse bias (+4.8 vs G2 +7.3 vs G1 +9.4, non-IPL). | **Mixed:** about 30–50% is model caution (fixable), and the rest is in the data too (hidden conditions or era drift). The collapse flaw can be about halved, not removed. |
| 13 Nov | Drawing board, final | Shrinkage ruled out as the main cause (slope 1.06; capacity/regularisation/early stopping move collapse bias <1 run; a minimal column set is worse, so "too many columns" is not it). **Tree shape matters:** the spline GAM and MLP have almost no shock bias but are worse on average. Mean (L2) target cuts innings-1 event bias by about 1/3. k-NN worse. | **Best candidate b2 = average of G2 and the spline GAM:** IPL MAE −0.32*, chase log loss −0.012*, collapse bias +7.3 → +5.8 (non-IPL). It ties the v1 blend and needs no simulator. Needs a new locked test (seasons were seen while choosing). |
| 13 Nov | Playing XI source | Cricsheet `_info.csv` already lists `info,player,<team>,<name>` for every player (incl. impact subs) | Use it instead of rebuilding the XI from deliveries. No scraping needed. |
| 13 Nov | XI source built (`ingest/xi.py` -> `xi.parquet`) | 11,937 matches parsed; sides listed with 11 players: 99%+ in most leagues; 12 = IPL impact era (551 of 2,486 IPL sides) and ILT20 (199 of 268), SMAT 134, BBL 47, LPL 49; 'other' (13 etc.): 12 sides. 31 DB matches have no info file (fallback to deliveries). `resources.xi_from_info` added, default still from deliveries | Real XI is available for the next fresh-set run; not yet tested for model gain |
| 13 Nov | Data update (`cricket update`, 30 days) | Real run ok: +39 matches (22 men's T20I to 2026-11-01, 17 women's T20I to 2026-10-25), 11,968 old matches unchanged, backup `_prev_2026-11-13`. Kohli IPL 9,336 (golden, unchanged). XI file rebuilt. | Done |
| 13 Nov | Fresh set #3 built (`data/external/ml/fresh3/`) | Only **6 matches** qualify (all men's T20I: India v West Indies 1, India v New Zealand 5), 5 chases. No league data since 15 Oct. Counts only, no results opened. | **Saved, not run** (Samar). Far below the 80-chase bar. Keep the lock and let the set grow (BBL from mid-Dec, more T20Is); run once when it is big enough. |
| 13 Nov | WAR or 1–100 ratings as player strength | No better than simple shrunk career rates | Use simple rates for the model; 1–100 is for display only |

| 13 Nov | Model zoo Z1 XGBoost (depth 4/6 grid, quantile objective, conformal) | IPL MAE@6/10/15 21.17/16.50/10.17, pinball 5.163, chase LL 0.422; non-IPL MAE 17.11, LL 0.327; collapse +6.6. Vs G2: IPL tie, non-IPL tie, chase LL better (IPL -0.009*, non -0.004*) | Ties G2 on score; shock bias not fixed. Trees of any brand behave the same. |
| 13 Nov | Z2 CatBoost (MultiQuantile, depth 4/6) | IPL pinball 5.156, chase LL 0.432; non-IPL MAE 17.05 (vs G2 -0.10*), pinball -0.043*; collapse +4.8; chase events worse (3.84 pp vs 3.47) | Best single new model on non-IPL score; no IPL gain; shock bias partly lower. |
| 13 Nov | Z3 RandomForest (mean + residual quantiles) | IPL pinball 5.232 (+0.081*), cov80 0.867, chase LL 0.438; non-IPL MAE +0.11*; collapse +8.2 | Worse than G2. Drop. |
| 13 Nov | Z4 ExtraTrees (mean + residual quantiles) | IPL pinball 5.165, chase LL 0.430; non-IPL MAE 17.12 (tie), pinball +0.034*; collapse +5.5, events inn1 2.52 | Tie overall, smoother (events better than G2) but ranges looser. Optional blend member only. |
| 13 Nov | Z5 HistGradientBoosting (sklearn, 15/31 leaves) | Matches LightGBM within noise on every column (IPL pinball 5.168, non-IPL MAE 17.12, LL 0.331; collapse +6.7) | Confirms the LightGBM G2 result is not a library artefact. No reason to switch. |
| 13 Nov | Z6 GRU on the ball-by-ball sequence (1 layer, 48 hidden, early stopped at 5-9 epochs) | IPL pinball 5.100 (-0.051, n.s.), cov80 0.809, chase LL 0.430; **non-IPL clearly worse** (MAE +0.71*, LL +0.036*); collapse +3.8, events 2.04 | Like the MLP/GAM: small shock bias, worse average. Ball order adds nothing over the over-end state features. Drop. |
| 13 Nov | Zoo blends Z7a/b/c (CatBoost + G2; CatBoost + b2; CatBoost + G2 + GAM) | Z7b IPL pinball -0.064*, non-IPL MAE -0.12*, pinball -0.042*; Z7c IPL pinball -0.078*; but IPL MAE and collapse bias (5.3-5.5) no better than b2 / b23 (5.8 / 4.7) | **Nothing beats b2/b23 clearly.** CatBoost in the mix helps non-IPL slightly; choosing CatBoost was done after seeing results. Exploratory only, not frozen. |
| 13 Nov | Test statistics fixed (`evaluate.calibration_test`, `season_block_bootstrap`, `match_bootstrap`, `power_n`, `holm`; `tests/test_ml_eval_stats.py`). Spent sets re-scored, reporting only: IPL 2026 chases (70): ens-G1 intercept +0.72 [+0.03, +1.41], slope 1.61 [1.11, 2.11]; sim-B +0.18 [-0.47, +0.84], 1.45 [1.01, 1.88]. ECE vs its null (mean-of-4, p95): ens-G1 0.117 vs 0.134, sim-B 0.081 vs 0.127, both pass. Non-IPL 2026 (312): v1 / v2 pass both tests (slope 0.90 / 0.89). Power: 0.01 log loss needs 550-780 decided chases, 0.3 runs needs 190-650 first innings. About 110 variant families tried. | "v1 FAILS ECE on IPL 2026" does **not** stand: ECE 0.117 is inside the null (p = 0.25). A smaller real signal remains: under-confident (slope > 1; intercept CI just excludes 0 for ens-G1; sim-B slope CI [1.01, 1.88] just excludes 1), so even the primary test fails on IPL 2026, narrowly, for every model. Not a clean pass or fail. Fresh set #3 pre-registration amended (Amendment 1): minimum 800 decided chases, no indicative read, both bootstraps, no zoo hook. |
| 13 Nov | Outside review (Opus, no context; `docs/REVIEW_external_2026-11-13.md`) | Scores: rigour 5, honesty 7, progress 4, effort 3, usefulness 6. Lead re-ran 2 checks: (a) **a level-scaled DLS table gets MAE 16.40, so G1 ties it (−0.09 [−0.55, +0.37]) and G0 is worse**; (b) IPL chase rate was 0.61 in 2019 and 0.63 in 2021, so 2026's 0.63 is not unusual. Also: ECE < 0.08 fails for a perfectly calibrated model about 98% of the time at n ≈ 70; about 100 variants on one bench; the bootstrap ignores season clustering. | **Accepted.** The old baseline was a strawman, and the "chase surge" story is withdrawn. Fix the test statistics (power, calibration test, season-block bootstrap) before fresh set #3 runs. The zoo is exploratory only, with no winner hook. |

## 4. What works (keep)
- Global training pool with a competition input
- Prior-only scoring level, used as a level-relative target or as a linear term in the simulator
- Averaging LightGBM with the simulator
- Conformal widening of the 10–90% range
- Rolling-season validation with locked, pre-registered tests
- Averaging a tree model with a smooth model (GAM / MLP): b2 / b23 are still the best candidates after the model zoo

## 5. What failed (don't retry without a NEW reason)
- Commentary-derived inputs for value/forecasting: length matchup, death execution, drop luck, worth_plus
- Separate per-team or per-venue models, and team/venue effects as an accuracy lever
- Impact-era-only or 2020+ training pools; recency weighting
- Chase win probability derived from the predicted score range (worse than the direct classifier)
- A "chase rate so far" drift input
- Short momentum windows on their own
- Partnership / balls-since-wicket inputs
- Bigger tree capacity on its own
- Real-XI simulator (pending final confirmation)
- Pre-match team ratings for IPL 2022+
- Switching tree library or tree family (XGBoost, CatBoost, HistGradientBoosting, ExtraTrees all tie G2; RandomForest worse): the stiffness is the tree shape, not the package
- GRU / sequence model on the ball-by-ball data (non-IPL worse, IPL tie)

## 6. Lessons
1. **More data beats purity.** All leagues beat IPL-only, even for IPL forecasts.
2. **Trees can't extrapolate past their training range** (scoring jumps, 262 targets). Use level-relative targets, linear terms or monotone constraints.
3. **A seen season is not a test.** Choosing a fix because it looks good on 2026 is fitting to the answer.
4. **"Theoretically right" isn't enough.** Who-is-left and momentum both sounded right and measured nothing. Always measure.
5. **Every flaw points the same way:** extremes pulled toward the middle. Diagnose that before adding more inputs.
6. **Pre-match T20 is close to a coin flip.** Real skill appears from about 6 overs in.
7. **Under 10 matches is an anecdote.** Judge on hundreds of matches, with intervals.
8. **Machine limits:** 3 LightGBM processes at once need thread limits (`OMP_NUM_THREADS=5`), or they slow each other down.

## 7. Open questions
- Shrinkage or hidden information? (The drawing board answers this.)
- Does any non-tree model (k-NN, spline, MLP) react better to shocks?
- A live BBL test from mid-December.
- A betting-odds comparison (deferred; needs historical odds, which aren't freely available).
