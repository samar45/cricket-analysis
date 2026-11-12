# ML score and chase prediction (started 2026-11-13)

Tracking doc for the in-play prediction section. Newest status is at the bottom (§9). A fresh session can resume from this file alone.

## 1. Samar's request, cleaned up
Build models that answer, from any point in a T20 match:
- **First innings:** "After 5 overs, 60/2 at Wankhede: what will they finish on?" The answer is a range, not one number.
- **Chase:** "After 10 overs, 110/4, chasing 209: do they win?" The answer is a win probability, plus the likely final score.
- **Pre-match:** "Team X at venue Y: expected score and win chance."

Requirements:
- Train on several eras: the impact-player era (IPL 2023+), 2020+, 2015+, and a global model (all T20 leagues).
- Tune, cross-check and validate properly: no leakage, no overfitting, and no hidden bias by team, venue or phase.
- Test on real matches from start to finish, including famous comebacks.
- Cricket is random. Measure that randomness instead of pretending it isn't there.

## 2. Corrections to the idea (lead's view)
| Idea | Problem | What we do instead |
|---|---|---|
| A separate model per team or per venue | ~15 matches per team per season, so it would learn noise | **Hierarchical (multilevel) modelling:** one global model, with team and venue effects shrunk toward the average. A venue with 80 matches gets its own effect; one with 5 stays near average. Yes, the name "hierarchical modelling" is right, and it is the correct tool here. |
| Separate 3-year / 2020 / 2015 models | The impact era has only ~220 IPL matches, which is too few on its own | Train **one global model** with era and competition features, then compare it against IPL-only and impact-era-only models, and against recency weighting / fine-tuning. The backtest picks the winner. |
| One number ("they'll make 185") | Hides the uncertainty | Predict a **distribution** (10/50/90% range) and a win probability, both scored for calibration. |
| Random train/test split of balls | Balls from the same match leak into both sides, so the score looks great but is fake | **Split by time and by match:** train on seasons < Y, test on season Y (rolling origin). IPL 2026 stays a **locked final holdout**. |
| "Use the new EDA data" | Commentary failed 3 forecasting tests and exists only for IPL 2017+ | Try it only as one ablation (a with/without comparison); the core uses Cricsheet ball-by-ball data. |

## 3. Approach: three model families, the same test bench
1. **Baselines (must be beaten):** current run rate × 20, a historical lookup table (average final score by over and wickets), and a resource table in the style of DLS / WASP (expected remaining runs per state).
2. **Ball simulator (cricket-native):** a model predicts the outcome of each ball (0/1/2/3/4/6/wicket/extra) from the state, the batter and bowler at the time, venue and era. The rest of the innings is then simulated thousands of times (Monte Carlo). One model gives the final-score range, the win probability and everything in between, and it handles targets naturally.
3. **Direct ML:** LightGBM (gradient-boosted trees). Quantile regression for the final score, and a classifier for the chase win probability, on state features.
4. Optional, only if 2 and 3 plateau: a sequence deep-learning model (GRU). Expect no gain on about 10k matches; it is tested only to be sure.

Hierarchy in all of them: venue, team and player strength enter as **shrunk ratings** (empirical Bayes, fitted on training seasons only).

## 4. Data (Cricsheet, `data/cricket_analytics.duckdb`, read-only)
- Men's T20: IPL plus the major leagues and T20Is, with women's as a separate competition. Super overs excluded.
- Rain-reduced or DLS matches are flagged and excluded from training targets, but kept for a later check.
- One row per legal ball state: match, innings, balls bowled, runs, wickets, target (innings 2), venue, teams, current batters and bowler, competition, season, era flag, final total, chase result.
- Built by `src/cricket_analytics/ml/dataset.py` into `data/external/ml/` (gitignored).

## 5. Validation (the most important part)
- **Splits:** rolling origin by season (test seasons 2022, 2023, 2024, 2025), always trained on earlier seasons only. **IPL 2026 is the locked holdout**, opened once at the end.
- **Score metrics:** MAE of the median, CRPS / pinball loss (how good the whole range is), and 80% interval coverage (should be about 80%).
- **Win metrics:** log loss, Brier score, and reliability (when the model says 30%, do about 30% win?), with ECE (expected calibration error).
- **Bias checks:** calibration and error broken down by team, venue, phase (overs 1–6 / 7–15 / 16–20), innings, competition and era. No group may be systematically off.
- **Overfitting:** the train-vs-test gap, learning curves, and hyperparameters tuned on inner folds only.
- **Real-match tests:** full win-probability curves for a few famous chases and collapses. A tail check: when the model said under 5%, how often did the team actually win, and does that match?
- **Randomness:** how much of the final-score variance is predictable at each over. This is the noise floor; no model can beat it.

## 6. Steps (one worker each, the lead reviews between steps)
| # | Step | Size | Output |
|---|---|---|---|
| S0 | Dataset builder and validation harness (splits, metrics, calibration plots) | M | `ml/dataset.py`, `ml/evaluate.py`, tests |
| S1 | Baselines: run rate, lookup table, resource table | S | baseline scores in §9 |
| S2 | Ball-outcome model and Monte Carlo simulator | L | `ml/ball_model.py`, `ml/simulate.py` |
| S3 | LightGBM direct models (score quantiles, chase win) | M | `ml/direct.py` |
| S4 | Era and hierarchy experiments (global vs IPL vs impact era; shrunk effects vs none vs per-team) | M | experiment table |
| S5 | Full validation, bias, real-match and tail checks; open the 2026 holdout once | M | `docs/img/ml_*.png`, verdict |
| S6 | Dashboard "Match predictor" page and CLI | M | only after S5 passes |

Keep rule for every addition: it must beat the best previous model on the rolling-origin test, not just on training data.

## 7. Decisions log
- 2026-11-13: installed scikit-learn 1.9.1, lightgbm 4.7.0 and scipy 1.18.1 into `.venv` (Samar gave permission to decide on his own). pip downloaded about 60 MB.

## 8. Mistakes and fixes
- 2026-11-13 (S0/S1 data notes, no mistakes):
  - Era drift is the main surprise: IPL first-innings mean was 163 (2008-2022 trained models) vs 183 / 190 / 192 in 2023 / 24 / 25. Every baseline under-predicts the test seasons by 10-15 runs (see §9). Models must carry an era / recency term.
  - Hundred is 100 balls with 5-ball sets, so it is marked `reduced` (balls_per_over = 5) and ignored in training; 5-ball-over matches in other leagues likewise.
  - Matches with D/L, VJD, Awarded, 'Lost fewer wickets', no result, or an innings cut short without being all out/chased are `reduced` in both innings (2,169 of 23,779 innings).
  - `deliveries.ball_seq` orders balls within an innings; legal ball = no wide and no no-ball; wicket = player_out set and not retired hurt / retired not out.
  - Chase result is taken from the scoreboard (tie -> NaN); for D/L matches the recorded winner is used.

- 2026-11-13 (S3/S4): the LightGBM models still under-predict by 4-5 runs in 2022-25 (-7.7 in 2024): trees cannot extrapolate beyond the training range and the EW scoring level lags the 2023-25 jump. Venue/team/player effects gave no gain (raw = shrunk = none). The impact-era pool covers only test 2024-25, so tables compare each pool on the seasons it covers. `season_year` cannot extrapolate for the test year (acts as the latest training year).

- 2026-11-13 (S2 ball model and simulator):
  - **Trees cannot extrapolate the scoring level.** A first LightGBM with the "level" as a tree feature predicted 8.47 runs/over for IPL 2025 (actual 9.18) and 8.12 for 2023 (8.50), because post-2022 levels are above anything in the training years (pooling all men's T20 did not help). Fix: the level enters only through a small linear (multinomial logistic) part by phase, and the trees boost on top of that offset. Ball-level bias in 2025 fell from -0.7 to -0.1 runs/over (variant A, single fold check).
  - A new era cannot be forecast: the IPL 2023 impact-player jump (+12 runs) is only partly caught, because 2023 is the first season with no impact-era data in training (2023 bias -4.5 runs). It is caught better from 2024 on.
  - Wickets that carry runs (run-outs) and wides with extra runs are folded in as small random extras (mean runs on a wicket ball; mean extra beyond 1 on a wide/no-ball), so totals are not biased low.
  - Batter-strength features partly double-count the era: at ball level variant B over-predicted 2025 by 0.34 runs/over (single fold check before the final run); in the final simulated totals the 2025 bias is +3 runs.

## 9. Status (newest at bottom)
- 2026-11-13: plan written; S0 started.

### 2026-11-13: S0 / S1 results
**S0 built** (`ml/dataset.py`, `ml/evaluate.py`, tests `tests/test_ml_dataset.py`, `tests/test_ml_eval.py`; 10 pass).
`python -m cricket_analytics.ml.dataset` writes `data/external/ml/states.parquet` (one row per legal ball, plus a row at 0 balls; players are those of the next delivery) and `states_innings.parquet` (one row per innings). Women's T20I are in the files with `gender='female'`. Super overs are excluded.

| competition | matches | state rows |
|---|---|---|
| T20I (men) | 3,627 | 787,779 |
| T20I (women) | 2,183 | 466,785 |
| Blast | 1,570 | 352,274 |
| IPL | 1,243 | 286,945 |
| SMAT | 695 | 155,720 |
| BBL | 662 | 149,536 |
| BPL | 469 | 108,184 |
| CPL | 445 | 99,708 |
| PSL | 357 | 81,483 |
| Hundred | 201 | 37,681 |
| LPL | 143 | 31,918 |
| ILT20 | 134 | 30,426 |
| SA20 | 130 | 28,183 |
| MLC | 109 | 24,634 |

Sanity, IPL average first-innings total (non-reduced innings):

| year | 2008 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mean | 163 | 149 | 164 | 156 | 158 | 156 | 163 | 168 | 164 | 166 | 172 | 168 | 170 | 159 | 171 | 183 | 190 | 192 | 196 |
| innings | 53 | 52 | 59 | 68 | 73 | 74 | 57 | 53 | 56 | 58 | 57 | 58 | 60 | 60 | 74 | 71 | 70 | 69 | 71 |

**S1 baselines** (`ml/baselines.py`, rerun with `python -m cricket_analytics.ml.baselines`). Test = IPL 2022-2025, rolling (train on earlier seasons only; "all" pools every men's T20 competition; 2026 not touched). Reduced matches and finished states excluded. Numbers are runs (MAE, bias = predicted minus actual, pinball = mean of the 10/50/90% quantile losses, cov80 = share of results inside the 10-90% range, should be 0.80). n = innings (284 first innings in the test seasons).

First-innings final score:

| model | at | n | MAE | pinball | cov80 | bias |
|---|---|---|---|---|---|---|
| run-rate | 6 overs | 284 | 29.1 | 9.12 | 0.74 | -6.2 |
| run-rate | 10 overs | 284 | 21.7 | 6.50 | 0.77 | -12.7 |
| run-rate | 15 overs | 283 | 14.8 | 4.29 | 0.78 | -11.2 |
| run-rate | all, innings-weighted | 284 | 28.2 | 8.44 | 0.76 | -15.0 |
| run-rate+bias shift | 0 overs | 284 | 29.6 | 12.90 | 1.00 | +15.0 |
| run-rate+bias shift | 6 overs | 284 | 28.6 | 9.03 | 0.74 | +5.0 |
| run-rate+bias shift | 10 overs | 284 | 18.9 | 6.02 | 0.77 | 0.0 |
| run-rate+bias shift | 15 overs | 283 | 11.3 | 3.70 | 0.78 | -2.5 |
| run-rate+bias shift | all, innings-weighted | 284 | 24.7 | 7.85 | 0.76 | -0.6 |
| lookup, IPL only | 0 overs | 284 | 32.0 | 10.28 | 0.65 | -21.4 |
| lookup, IPL only | 6 overs | 284 | 24.3 | 7.57 | 0.68 | -15.2 |
| lookup, IPL only | 10 overs | 284 | 19.4 | 6.15 | 0.71 | -12.3 |
| lookup, IPL only | 15 overs | 283 | 12.6 | 4.00 | 0.72 | -9.4 |
| lookup, IPL only | all, innings-weighted | 284 | 18.3 | 5.79 | 0.74 | -9.8 |
| lookup, all comps | 6 / 10 / 15 overs | 284 | 27.2 / 21.4 / 14.2 | 8.53 / 6.72 / 4.41 | 0.67 / 0.70 / 0.70 | -21.0 / -16.7 / -11.8 |
| lookup, all comps | all, innings-weighted | 284 | 20.4 | 6.45 | 0.73 | -14.7 |
| resource, IPL only | 0 overs | 284 | 31.1 | 9.97 | 0.68 | -19.4 |
| resource, IPL only | 6 overs | 284 | 23.3 | 7.29 | 0.70 | -12.8 |
| resource, IPL only | 10 overs | 284 | 18.3 | 5.78 | 0.73 | -9.9 |
| resource, IPL only | 15 overs | 283 | 11.1 | 3.50 | 0.76 | -5.9 |
| resource, IPL only | all, innings-weighted | 284 | 18.1 | 5.71 | 0.74 | -9.8 |
| resource, all comps | 6 / 10 / 15 overs | 284 | 25.9 / 20.6 / 12.5 | 8.11 / 6.54 / 3.96 | 0.68 / 0.71 / 0.75 | -18.8 / -14.5 / -9.5 |
| resource, all comps | all, innings-weighted | 284 | 20.5 | 6.46 | 0.72 | -14.8 |

Chase win probability (second-innings states with the chase still undecided; log loss of a coin flip = 0.693; "const" = always the historical chase win rate):

| model | at | n | log loss | Brier | ECE |
|---|---|---|---|---|---|
| const | all, innings-weighted | 283 | 0.695 | 0.251 | 0.030 |
| lookup, IPL only | 0 / 6 / 10 / 15 overs | 283 / 283 / 279 / 266 | 0.715 / 0.617 / 0.538 / 0.403 | 0.231 / 0.192 / 0.165 / 0.125 | 0.198 / 0.164 / 0.132 / 0.109 |
| lookup, IPL only | all, innings-weighted | 283 | 0.491 | 0.153 | 0.110 |
| lookup, all comps | 0 / 6 / 10 / 15 overs | same | 0.777 / 0.658 / 0.569 / 0.432 | 0.255 / 0.209 / 0.180 / 0.136 | 0.240 / 0.203 / 0.176 / 0.138 |
| lookup, all comps | all, innings-weighted | 283 | 0.525 | 0.168 | 0.151 |
| resource, IPL only | 0 / 6 / 10 / 15 overs | same | 0.699 / 0.584 / 0.525 / 0.364 | 0.226 / 0.185 / 0.163 / 0.115 | 0.184 / 0.143 / 0.112 / 0.077 |
| resource, IPL only | all, innings-weighted | 283 | 0.488 | 0.154 | 0.113 |
| resource, all comps | 0 / 6 / 10 / 15 overs | same | 0.759 / 0.624 / 0.556 / 0.401 | 0.250 / 0.202 / 0.174 / 0.127 | 0.229 / 0.191 / 0.157 / 0.113 |
| resource, all comps | all, innings-weighted | 283 | 0.530 | 0.170 | 0.157 |

Reading it plainly:
- **Best baseline to beat:** the IPL-only resource table (first-innings MAE 18.1 runs overall, 23.3 at 6 overs, 11.1 at 15 overs; win log loss 0.488 overall, 0.364 at 15 overs). The bias-shifted run-rate comes close at 15 overs (MAE 11.3 vs 11.1) but is worse earlier; its bias shift uses train residuals only.
- **Every table-based baseline is too low by 10-15 runs** because IPL scoring jumped in 2023-25 (see §8). Their 80% ranges cover only 68-76%, and the win probabilities are over-pessimistic for chasers (ECE 0.11-0.20), because they look up an older, lower-scoring game. The pooled all-competition versions are worse than IPL-only (different grounds and standards).
- A model with no state (const) has the best calibration but no skill: log loss 0.695. At the start of a chase the table baselines are worse than a coin flip (0.70-0.78) for the same era reason.
- Plots: `docs/img/ml_baseline_resource_ipl_reliability.png`, `docs/img/ml_baseline_lookup_ipl_coverage.png`.

### 2026-11-13: S3 / S4 results (direct LightGBM models; `ml/features.py`, `ml/direct.py`)
**What was built.** 26 frozen features (`features.FEATURES`): state (balls left, wickets, runs, run rate, runs and wickets in the last 30 balls, innings, target / runs needed / required rate, competition, impact-era flag, season), a **scoring level** (exponentially weighted mean first-innings total of the competition over earlier matches, half-life 60 matches, plus the season-to-date mean), shrunk venue and team effects (venue k=100, team k=10, chosen on season 2021 only), and each batter's shrunk career runs-per-ball plus balls faced so far. Every feature uses only matches on earlier dates (tested: deleting later matches does not change a row). Models: 3 quantile boosters (10/50/90% of remaining runs) and 1 classifier (chase won). Config (3 tried) and iterations are tuned on an inner fold (validation = IPL season Y-1, training < Y-1), then refit on all seasons < Y. Test = IPL 2022-25 rolling, 2026 never opened. Same rows and metrics as S1 (n = 284 first innings and 283 chases; MAE in runs; "ll" = chase log loss, innings-weighted; baseline = IPL-only resource table).

**S4 pools (same features, shrunk effects).**

| pool | test seasons | n innings | MAE@6 / @10 / @15 | MAE overall | pinball | cov80 | bias | chase ll | ECE |
|---|---|---|---|---|---|---|---|---|---|
| baseline resource-ipl | 2022-25 | 284 | 23.3 / 18.3 / 11.1 | 18.12 | 5.71 | 0.74 | -9.8 | 0.488 | 0.113 |
| IPL all years (S3) | 2022-25 | 284 | 21.1 / 16.9 / 10.4 | 17.01 | 5.51 | 0.72 | -5.1 | 0.487 | 0.056 |
| IPL 2015+ | 2022-25 | 284 | 20.9 / 16.7 / 10.5 | 16.98 | 5.62 | 0.69 | -4.3 | 0.517 | 0.047 |
| IPL 2020+ | 2022-25 | 284 | 21.6 / 17.2 / 11.0 | 17.59 | 5.96 | 0.63 | -4.8 | 0.533 | 0.057 |
| **global men's T20 (comp feature)** | 2022-25 | 284 | 20.7 / 16.5 / 10.4 | 16.70 | **5.31** | 0.76 | -4.4 | **0.454** | 0.042 |
| global, recency weights (half-life 2 seasons, IPL x3) | 2022-25 | 284 | 20.6 / 16.6 / 10.4 | 16.65 | 5.47 | 0.71 | -3.8 | 0.486 | 0.040 |

Impact-era only (IPL 2023+, so only test 2024-25 exists; all rows below are on those two seasons, n = 139 first innings):

| pool | MAE@6 / @10 / @15 | MAE overall | pinball | cov80 | bias | chase ll | ECE |
|---|---|---|---|---|---|---|---|
| baseline resource-ipl | 26.0 / 19.9 / 11.2 | 19.71 | 6.25 | 0.72 | -12.7 | 0.462 | 0.128 |
| impact-era only | 22.1 / 17.3 / 11.3 | 18.10 | 6.32 | 0.61 | -3.7 | 0.489 | 0.049 |
| IPL all years | 21.9 / 16.8 / 10.5 | 17.51 | 5.73 | 0.72 | -5.1 | 0.443 | 0.079 |
| global | 22.3 / 16.7 / 10.3 | 17.50 | 5.57 | 0.76 | -5.2 | 0.416 | 0.073 |
| global, recency weights | 22.4 / 16.7 / 10.4 | 17.53 | 5.81 | 0.72 | -4.3 | 0.440 | 0.059 |

**S4 hierarchy and ablation (best pool = global, 2022-25, n = 284 / 283).** "none" = no venue / team / player effects (state + scoring level only); "shrunk" = the S3 global model; "raw" = venue / team / player effects with no shrinkage (k = 0); "no level" drops the scoring level; "fast level" uses half-life 20 matches instead of 60.

| variant | MAE@6 / @10 / @15 | MAE overall | pinball | cov80 | bias | chase ll | ECE |
|---|---|---|---|---|---|---|---|
| none (no effects) | 20.8 / 16.1 / 10.7 | 16.58 | 5.27 | 0.77 | -4.5 | 0.459 | 0.050 |
| shrunk (S3 global) | 20.7 / 16.5 / 10.4 | 16.70 | 5.31 | 0.76 | -4.4 | 0.454 | 0.042 |
| raw (unshrunk) | 20.9 / 16.5 / 10.5 | 16.71 | 5.30 | 0.76 | -4.4 | 0.449 | 0.042 |
| shrunk, no scoring level | 21.0 / 16.5 / 10.5 | 16.85 | 5.34 | 0.76 | -5.4 | 0.449 | 0.033 |
| shrunk, fast level (hl 20) | 20.9 / 16.6 / 10.5 | 16.80 | 5.36 | 0.77 | -4.5 | 0.451 | 0.039 |

**Confidence (bootstrap over matches, 2000 resamples, 5-95%; difference vs the IPL-only resource baseline, negative = better; n = 284 matches, impact n = 139).**

| model | MAE difference (runs) | chase log-loss difference |
|---|---|---|
| global | -1.41 [-1.88, -0.93] | -0.033 [-0.072, +0.001] |
| global, no effects | -1.53 [-2.00, -1.06] | -0.029 [-0.064, +0.005] |
| global, raw effects | -1.40 [-1.87, -0.91] | -0.039 [-0.076, -0.003] |
| global, no level | -1.26 [-1.68, -0.84] | -0.039 [-0.077, -0.003] |
| global, recency weights | -1.45 [-2.04, -0.86] | -0.001 [-0.041, +0.037] |
| IPL all years | -1.09 [-1.64, -0.51] | -0.001 [-0.042, +0.037] |
| IPL 2015+ | -1.13 [-1.72, -0.51] | +0.030 [-0.016, +0.072] |
| IPL 2020+ | -0.50 [-1.25, +0.24] | +0.046 [-0.000, +0.090] |
| impact only (2024-25) | -1.62 [-2.85, -0.36] | +0.028 [-0.052, +0.100] |

Pairwise against the previous best (global as the reference): global vs IPL-all MAE -0.32 [-0.62, -0.03], log loss -0.034 [-0.057, -0.014] (global better, small but outside noise). "No effects" vs global: MAE -0.11 [-0.29, +0.06] (tie). Raw vs shrunk: MAE +0.02 [-0.08, +0.11] (tie). No level vs global: MAE +0.15 [+0.04, +0.26] (level helps by a hair). Recency weights vs global: MAE -0.04 [-0.27, +0.20], log loss +0.032 [+0.019, +0.047] (recency weights hurt the win model).

**Overfit gap** (innings-weighted, in-sample rows the model was fit on): IPL-all pool, first-innings MAE 12.0 / 13.3 / 13.6 / 12.0 in-sample vs 17.0 on test; chase log loss 0.17-0.40 in-sample vs 0.49 on test. The gap is about 4 to 5 runs and 0.1-0.3 log loss: real but not extreme for 100-200 trees. Global pool (trains on all leagues, so its train MAE covers all leagues): 14.7-15.7 train vs 16.7 test (IPL only).

**Calibration.** Chase probabilities are well calibrated without help (ECE 0.04, down from the baseline's 0.11; `docs/img/ml_direct_global_reliability.png`). Platt scaling fitted on the inner fold (IPL-all model) moved ECE 0.056 to 0.039 but log loss 0.487 to 0.489 on 2022-25 (no gain), and 0.443 to 0.444 on 2024-25; not adopted. Interval coverage by over: `docs/img/ml_direct_global_coverage.png` (overall 0.76 vs the 0.80 target, so ranges are a bit narrow).

**Verdict (plain).**
- ML beats the best baseline, but modestly: about **1.4 runs** better first-innings MAE overall (16.7 vs 18.1), clear of noise, and about 2.6 runs better at 6 overs. At 15 overs the gain is only about 0.7 runs (10.4 vs 11.1), and chase log loss at 15 overs is a tie with the resource table (0.366 vs 0.364; at 10 overs 0.497 vs 0.525). Overall chase log loss 0.454 vs 0.488 (-0.033; the interval just touches zero, so call it a likely small gain).
- **Winning pool: global men's T20 with a competition feature.** It beats IPL-only on score metrics and chase log loss. IPL-only pools get worse the further back you cut (2020+ is no better than the baseline), impact-era-only is poor (too few matches; coverage 0.61), and recency weights did not help.
- **Hierarchy did not matter.** No effects, shrunk and raw effects are tied within noise. Venue / team / player effects add nothing the trees do not already get from the scoring level and competition feature. Simplest model = "none"; shrunk effects remain available for dashboard text but give no accuracy.
- **Scoring level helps only a hair** (MAE +0.15 without it). Remaining first-innings bias is about -4 to -5 runs (2024 worst at -7.7); a faster level (half-life 20) did not fix it. Main open problem: a level that learns the drift inside the test season (ball simulator, or start-of-season recalibration, are the natural next tries).
- Keep rule: global beats the baseline and the previous best (IPL-all). "No effects" ties with it; S5 candidate #1 = global-none, #2 = global-shrunk.
- Models saved in `data/external/ml/models/` (global and ipl_all, per test year); predictions cached as `data/external/ml/direct_*.parquet`. Rerun with `python -m cricket_analytics.ml.direct`, tables with `... direct report`.

### 2026-11-13: S2 results (ball-outcome model + Monte Carlo simulator)
**What was built.** `ml/ball_model.py` (ball table `data/external/ml/balls.parquet`, causal features, `BallModel`), `ml/simulate.py` (vectorised simulator), `ml/sim_eval.py` (rolling evaluation), `ml/sim_report.py` (tables, bootstrap, plots, sanity). Tests: `tests/test_ml_simulate.py` (7 tests; with the 5 in `test_ml_eval.py` all pass).

**Design (plain words).**
- Every delivery is one of 8 outcomes: 0, 1, 2, 3, 4, 6 runs, wicket, or an extra ball (wide/no-ball: +1 run and the ball is not used up). Byes and leg-byes count as runs; 5 goes to 4, 7 to 6. 2.24M men's T20 deliveries (IPL 296k).
- The model gives the probability of each outcome from the state: over, ball in over, wickets, innings, current and required run rate, target, and a **scoring level** = runs per over this competition scored in the matches strictly before this date (exponentially weighted; half-lives 100 and 25 matches). Variant **A** = state + level. **B** = A + striker (shrunk runs per ball, out rate, experience, balls faced this innings) and bowler (shrunk runs per ball and wicket rate). **C** = B + venue effect (shrunk, earlier matches only). All strengths use only matches on earlier dates.
- Shape: probabilities = softmax(linear part in the level by phase + LightGBM trees on everything else). Training: IPL balls from seasons before the test year; number of trees chosen on the previous season (inner time fold), then refit on all seasons before the test year. 2026 never opened.
- The simulator plays the rest of the innings 400 times per state (any n works; 400 for the backtest to keep it fast). The current batters and the current over's bowler are the real ones; every later batter is the average batter for that wicket number and every later bowler the average bowler for that over (no batting order from the future, so no leak). Innings 1 gives a final-score distribution; innings 2 gives P(win) = share of paths with runs >= target (a tie counts 0.5).
- Cost: about 2-4 minutes per season per variant for 570 states x 400 paths (CPU, 5 threads, with other jobs running).

**Results.** Test = IPL 2022-2025, rolling (train on earlier seasons only). Same states for every model: 4 checkpoints (0 / 6 / 10 / 15 overs); n = 284 first innings per checkpoint (1,135 in all) and 283 / 283 / 279 / 266 chases (1,111 in all; ties and no-results excluded). "Mean of 4" = the average over the four checkpoints (one innings counts at four stages). Score MAE is in runs; pinball = mean of the 10/50/90% quantile losses (lower is better); cov80 should be 0.80; bias = predicted median minus actual.

First-innings final score:

| model | 0 ov MAE | 6 ov MAE | 10 ov MAE | 15 ov MAE | mean-of-4 MAE | pinball | cov80 | bias |
|---|---|---|---|---|---|---|---|---|
| run-rate + bias shift | 29.6 | 28.6 | 18.9 | 11.3 | 22.1 | 7.91 | 0.82 | +4.4 |
| lookup, IPL | 32.0 | 24.3 | 19.4 | 12.6 | 22.1 | 7.00 | 0.69 | -14.6 |
| **resource, IPL (S1 bar)** | 31.1 | 23.3 | 18.3 | 11.1 | 20.9 | 6.64 | 0.72 | -12.0 |
| sim A (state + level) | 26.9 | 20.9 | 16.1 | 9.9 | 18.5 | 5.88 | 0.75 | -3.2 |
| sim B (+ players) | 26.6 | 20.7 | 16.4 | 9.9 | 18.4 | 5.80 | 0.78 | -1.6 |
| sim C (+ venue) | 26.8 | 20.9 | 16.6 | 9.7 | 18.5 | 5.81 | 0.79 | -1.3 |
| sim B, trained on all men's T20 | | | | | 18.5 | 5.83 | 0.79 | -2.0 |

Mean CRPS of the simulated distributions (whole-range score, lower is better): A 13.18, B 13.06, C 13.04 runs. No baseline CRPS (baselines only have 3 quantiles).

Chase win probability (mean of the 4 checkpoints):

| model | log loss | Brier | ECE |
|---|---|---|---|
| lookup, IPL | 0.568 | 0.178 | 0.151 |
| **resource, IPL (S1 bar)** | 0.543 | 0.173 | 0.129 |
| sim A | 0.487 | 0.154 | 0.056 |
| sim B | 0.477 | 0.154 | 0.056 |
| sim C | 0.471 | 0.154 | 0.049 |
| sim B, all men's T20 | 0.477 | 0.156 | 0.054 |

By checkpoint, sim C log loss is 0.569 / 0.504 / 0.468 / 0.342 at 0 / 6 / 10 / 15 overs (resource: 0.699 / 0.584 / 0.525 / 0.364; a coin flip is 0.693).

**Bootstrap over matches** (2,000 resamples, 5-95% interval, difference of the mean-of-4 loss; negative = first model better):

| comparison | MAE | pinball | win log loss | win Brier |
|---|---|---|---|---|
| sim A - resource | -2.49 [-3.26, -1.66] | -0.76 [-1.00, -0.50] | -0.056 [-0.112, +0.005] | -0.018 [-0.034, -0.002] |
| sim B - resource | -2.53 [-3.42, -1.57] | -0.84 [-1.12, -0.54] | -0.066 [-0.116, -0.016] | -0.018 [-0.033, -0.004] |
| sim C - resource | -2.48 [-3.39, -1.50] | -0.83 [-1.12, -0.53] | -0.072 [-0.120, -0.026] | -0.018 [-0.033, -0.004] |
| sim B - sim A | -0.04 [-0.29, +0.23] | -0.08 [-0.16, 0.00] | -0.011 [-0.028, +0.004] | 0.000 [-0.004, +0.004] |
| sim C - sim B | +0.05 [-0.10, +0.20] | +0.01 [-0.03, +0.06] | -0.006 [-0.019, +0.003] | 0.000 [-0.002, +0.002] |
| sim B all-T20 - sim B | +0.12 [-0.04, +0.29] | +0.03 [-0.01, +0.08] | 0.000 [-0.013, +0.011] | +0.002 [-0.002, +0.005] |

**Sanity checks** (variant B, first innings from ball 0, 284 innings x 400 paths):
- Runs per over, simulated vs actual: overs 1-6 8.60 vs 8.88, overs 7-15 8.51 vs 8.49, overs 16-20 10.45 vs 10.84. So the simulator is about 0.3-0.4 runs/over low in the powerplay and the death overs. Mean final total 180.6 vs actual 183.9 (by season 167 / 174 / 188 / 194 vs 171 / 183 / 190 / 192).
- Wickets at the end of an innings: the simulator has slightly too few 8-9 wicket innings (11% + 8% vs actual 14% + 10%) and too many 4-wicket ones (13% vs 10%); all out 8.9% vs 7.4%. Mild.
- Spread: actual totals have SD 34.4 runs; simulated totals pooled over all paths 33.2; inside one innings the simulated SD is 30.9. The z-score of the actual total against the simulated mean and SD has SD 1.08 (1.0 = right), so the ranges are slightly too narrow (cov80 0.75-0.79 at 0-10 overs; at 15 overs coverage is 0.84-0.87, slightly too wide). The PIT histogram has a mild excess at the top (real totals above the 90th percentile more often than 10%).
- Bias by season (variant B, predicted median minus actual): 2022 -2.7, 2023 -4.5, 2024 -2.0, 2025 +3.1 runs; MAE 17.5 / 17.9 / 20.4 / 18.0.
- Win probability by season, log loss: 2022 0.487, 2023 0.550, 2024 0.391, 2025 0.485. Average predicted chase win rate 0.506 vs actual 0.488. **Tails** (variant B, small numbers): of 95 states under 5%, 1 chase won (expected 1.3); of 133 states over 95%, 6 lost (expected 1.7), so the top end is over-confident.
- Plots: `docs/img/ml_sim_reliability_B.png` (and `_0ov`, `_6ov`, `_10ov`, `_15ov`), `docs/img/ml_sim_B_score_checks.png` (PIT, coverage by over, bias by season), `docs/img/ml_sim_B_overs.png` (simulated vs actual cumulative runs).

**Verdict.**
- The ball simulator **beats the best S1 baseline** (IPL resource table): about 2.5 runs lower MAE (20.9 -> 18.4), 0.8 lower pinball, about 0.07 lower chase log loss, and ECE 0.13 -> 0.05. The bootstrap interval excludes zero for MAE, pinball and Brier for all three variants, and for log loss for B and C (A just touches zero). Much of the gain is that the tables lack a drift input and are 12 runs low; the bias-shifted run rate has a similar fix and is closest at 15 overs (11.3 vs 9.9).
- **Players and venue add almost nothing here**: B vs A and C vs B are inside the noise (win log loss -0.011 and -0.006, intervals include zero). A (state + level) is the simple model; B and C are kept as variants. Training on all men's T20 gave no gain and took 8x longer.
- Weak spots: ranges a little narrow early (cov80 0.75-0.79); high-confidence chases (>95%) lost 6 vs 1.7 expected; the first season of a new scoring era (2023) is under-predicted by about 4 runs; powerplay/death scoring is 0.3-0.4 runs/over low.
- Not checked yet (S5): bias breakdown by team / venue, famous chases, comparison with the S3 direct models. The 2026 holdout was not touched.
- Models: `data/external/ml/models/ball_<variant>_<pool>_<year>.pkl` (gitignored). Rerun: `python -m cricket_analytics.ml.ball_model` (build), `python -m cricket_analytics.ml.sim_eval ABC ipl 400`, `python -m cricket_analytics.ml.sim_report ABC`.
