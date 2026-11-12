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
- 2026-11-13 (S4b): (1) My first report script had a broken string (a real newline inside a print) from a bad shell-heredoc edit; fixed before any result was produced. (2) S3's iteration counts were tuned on the IPL-all pool, so a fair control "g0r" re-tunes on the global pool; it is 0.1 runs better than G0. Against g0r, E1's MAE gain is -0.25 [-0.64, +0.15], so the MAE part of E1 is not outside noise; the bias part is (+3.3 runs toward zero [+2.9, +3.6]). (3) E4 (win from the score distribution) failed, likely because chase remaining-runs targets are cut off at the target; dropped.

- 2026-11-13 (S5 part 1):
  - The S3 table (innings-weighted over all states) and the S2 table (mean of 4 checkpoints) were not comparable, so G0 and sim-B looked closer than they are; the head-to-head on identical states shows sim-B ahead of G0 by 0.8 runs MAE. Always compare on one row set.
  - First version of my tail check counted one chase several times (one state per checkpoint); the table now states states and matches separately. Surprise counts are clustered: 3 matches gave 7 of sim-B's 10 over-90% misses.
  - match_id is text in `balls.parquet` and the prediction caches but int in some other tables: join with care (a first version of the freak-over check silently matched nothing).
  - Bias flags at 2 s.e. produce about 5% false alarms (1-2 of 33 groups); a single flagged venue is not evidence unless several models agree (Chepauk +10 runs is flagged for all of them).

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

### 2026-11-13: S4b results (fixing the global model's bias and narrow ranges; `ml/s4b.py`, helpers in `ml/direct.py`)
**Setup.** G0 = the S3 global model (`lgbm-global`). Every variant changes one thing, uses G0's config per fold, and re-tunes its iteration counts by early stopping on the inner fold (global pool, seasons < Y-1, validation = IPL Y-1). Because that tuning differs slightly from S3's, a control "g0r" (G0 with only the new tuning) is also shown. Test = IPL 2022-25 rolling, 2026 never opened. n = 284 first innings, 283 chases. Bootstrap = 2000 resamples over matches, mean [5%, 95%] of (variant minus G0). Bias = predicted minus actual median (runs); "bias diff" is signed, so +3.8 means the bias moved 3.8 runs toward zero.

| experiment | MAE | bias | pinball | cov80 | MAE diff vs G0 | bias diff vs G0 | pinball diff vs G0 | verdict |
|---|---|---|---|---|---|---|---|---|
| G0 | 16.70 | -4.43 | 5.311 | 0.759 | - | - | - | reference |
| g0r (control, new tuning) | 16.59 | -3.88 | 5.274 | 0.766 | -0.11 [-0.20, -0.02] | +0.55 [+0.44, +0.66] | -0.036 [-0.056, -0.017] | tuning alone helps a hair |
| E1a level-relative target, lvl_ew | 16.32 | -1.63 | 5.180 | 0.796 | -0.36 [-0.69, -0.02] | +2.78 [+2.46, +3.12] | -0.126 [-0.231, -0.015] | **keep** (bias, clear) |
| E1b same, in-season level (lvl_season) | 16.33 | -0.48 | 5.192 | 0.801 | -0.36 [-0.79, +0.08] | +3.94 [+3.57, +4.31] | -0.114 [-0.241, +0.018] | **keep, chosen for G1** (lowest bias; ties E1a on MAE: +0.005 [-0.26, +0.28]) |
| E2 drop season_year | 16.63 | -4.27 | 5.297 | 0.767 | -0.07 [-0.18, +0.04] | +0.15 [+0.00, +0.30] | -0.014 [-0.041, +0.014] | **keep** (ties on score, simpler, helps the win model, see below) |
| E3 conformal widening (on E1b) | 16.33 | -0.48 | 5.191 | 0.819 | same | same | vs E1b alone: -0.001 | **keep** (coverage 0.80 -> 0.82, no pinball cost) |
| G1 (E1b + E2 + E3) | 16.30 | -0.61 | 5.169 | 0.815 | -0.38 [-0.79, +0.03] | +3.81 [+3.46, +4.15] | -0.137 [-0.262, -0.007] | final |

E3 on the other variants: g0r 0.766 -> 0.811, E1a 0.796 -> 0.815, E2 0.767 -> 0.817 (coverage +0.05 to +0.06, pinball change -0.001 to -0.008, inside noise). How E1 works: the model learns remaining runs divided by (scoring level / 120 x balls left), with that same quantity as the training weight, so the loss is still measured in runs but the prediction scales with the scoring level (the one thing a tree cannot do by itself). How E3 works: the inner-fold model (trained on seasons < Y-1) predicts season Y-1; the 80th percentile of "how far the result fell outside q10-q90" in each of four over buckets (1-6, 7-10, 11-15, 16-20) is added to both sides. Deltas are small, -3 to +3 runs (`models/g1/conformal_delta.json`), because G1 was already close to 0.80.

**E2 on the chase model** (win log loss, G0 0.454): E2 0.444, difference -0.0100 [-0.0174, -0.0025] (outside noise), ECE 0.042 -> 0.033. Dropping the season number helps the win model.

**E4: chase win from the score distribution** (innings-2 remaining-runs quantiles at 9 levels from 5% to 95%; P(win) = P(remaining >= runs needed), CDF interpolated):

| variant | log loss | ECE | log loss diff vs G0 classifier |
|---|---|---|---|
| G0 classifier | 0.454 | 0.042 | - |
| E4 raw quantile model | 0.550 | 0.174 | +0.095 [+0.057, +0.136] |
| E4 level-relative | 0.539 | 0.136 | +0.084 [+0.046, +0.124] |
| average of G0 and E4 raw | 0.474 | 0.102 | +0.019 [+0.001, +0.037] |
| average of G0 and E4 level-relative | 0.469 | 0.083 | +0.015 [-0.002, +0.032] |

**Drop E4.** It is clearly worse than the classifier and averaging does not help. Likely cause (a guess): remaining runs in a chase are cut off at the target, so the upper quantiles are distorted exactly where the answer is read. The classifier stays.

**E5: by test season (G0 / G1 with conformal / baseline), n = 74 / 71 / 70 / 69 first innings.**

| season | MAE G0 | MAE G1 | MAE base | bias G0 | bias G1 | bias base | cov80 G0 | cov80 G1 | chase ll G0 | chase ll G1 | chase ll base |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | 15.94 | 15.62 | 15.69 | -3.5 | -0.7 | -5.1 | 0.775 | 0.807 | 0.458 | 0.446 | 0.427 |
| 2023 | 15.90 | 15.75 | 17.54 | -4.0 | -2.2 | -9.1 | 0.732 | 0.822 | 0.525 | 0.521 | 0.603 |
| 2024 | 18.78 | 17.94 | 20.30 | -7.5 | -0.6 | -13.8 | 0.754 | 0.828 | 0.423 | 0.398 | 0.445 |
| 2025 | 16.21 | 15.93 | 19.11 | -2.8 | +1.2 | -11.6 | 0.775 | 0.804 | 0.407 | 0.409 | 0.480 |

2024 (worst bias, -7.5) is fixed to -0.6, and 2023 improves from -4.0 to -2.2. 2025 flips to slightly over-predicting (+1.2; E1a alone gave +3.3). In 2022 the old resource baseline is still as good as G1 (MAE 15.69 vs 15.62, chase log loss 0.427 vs 0.446): that was before the jump, so the old table fitted it. Per-season n is about 70 matches, so single-season differences are not significant.

**G1 vs G0 vs baseline (2022-25, n = 284 / 283)**

| model | MAE@6 / @10 / @15 | MAE | pinball | cov80 | bias | chase ll | ECE |
|---|---|---|---|---|---|---|---|
| baseline resource-ipl | 23.3 / 18.3 / 11.1 | 18.12 | 5.711 | 0.738 | -9.84 | 0.488 | 0.113 |
| G0 | 20.7 / 16.5 / 10.4 | 16.70 | 5.311 | 0.759 | -4.43 | 0.454 | 0.042 |
| **G1 (with conformal)** | 20.2 / 16.2 / 10.0 | **16.30** | **5.169** | **0.815** | **-0.61** | **0.444** | **0.033** |

G1 minus baseline: MAE -1.80 [-2.61, -0.98], pinball -0.53 [-0.79, -0.29], chase log loss -0.044 [-0.081, -0.008] (all outside noise). G1 minus G0: MAE -0.38 [-0.79, +0.03] (borderline), pinball -0.137 [-0.262, -0.007], bias +3.8 runs toward zero [+3.5, +4.2], coverage +0.056 [+0.041, +0.070], chase log loss -0.010 [-0.017, -0.003].

**Verdict (plain).** The two weaknesses are largely fixed: the first-innings bias drops from -4.4 to -0.6 runs (2024: -7.5 to -0.6) and the 80% range covers 0.815 instead of 0.759. The gain on the median itself is small (0.4 runs, on the edge of noise); the main win is that G1 no longer lags the scoring level. Chase win probability also improved a little (log loss 0.454 to 0.444, ECE 0.033). Remaining soft spots: coverage collapses in the last over (about 0.70 with the widening, 0.53 without; so few runs are left and they are so discrete that a 10-90 range is hard to make exact), and the 2025 sign flip (+1.2) shows the level can overshoot after a jump season. Plots: `docs/img/ml_g1_coverage.png`, `ml_g1_reliability.png`, `ml_g1_bias_by_season.png`. G1 models (per test year: three score quantiles + chase classifier) are in `data/external/ml/models/g1/`, predictions in `data/external/ml/s4b_*.parquet`. Rerun with `python -m cricket_analytics.ml.s4b run`, then `... report` (about 30 min, E4 included). G1 = S5 candidate #1.

### 2026-11-13: S5 part 1 (head-to-head + bias + tails; 2026 holdout NOT opened)
Code: `ml/validate.py` (`python -m cricket_analytics.ml.validate [h2h bias noise tails curves lc] [--extra G1=<prefix>]`; the extra model needs `<prefix>_score.parquet` and `<prefix>_win.parquet` in the direct.py format; it is then included in every table and plot). Tests: `tests/test_ml_validate.py` (3). Full output saved locally in `data/external/ml/s5_part1.md`, audit tables `data/external/ml/s5_audit_*.csv`.

**Setup.** All models are scored on IDENTICAL rows: IPL test 2022-25, checkpoints 0/6/10/15 overs, same (match, innings, balls_bowled) key. That is 1,135 first-innings states (284 innings x 4) for score and 1,111 chase states (283/283/279/266) for win probability; ties and no-results excluded. Models: **resource-ipl** (S1 baseline), **G0** (direct LightGBM, global men's pool, S3), **G1** (improved direct model from S4b: level-relative target, no season feature, conformal-widened q10/q90 from the inner fold; `s4b_g1_*` caches), **sim-B** (ball simulator variant B, 400 paths), **ens** (plain average of G0 and sim-B) and **ens-G1** (average of G1 and sim-B; quantiles averaged then sorted, probabilities averaged). Score is evaluated on the first innings only (the chase gets a win probability, not a score target). "Mean of 4" = average of the four checkpoint metrics, as in the S2 table. No model was refit; G0 and sim-B predictions are the cached rolling-origin ones. Note the S3 table (innings-weighted over all states) and the S2 table (mean of 4) are different measures; this table puts them on one scale.

**1. Head-to-head, same states (mean of 4 checkpoints).**

| model | MAE (runs) | pinball | cov80 | bias | win log loss | Brier | ECE |
|---|---|---|---|---|---|---|---|
| resource-ipl | 20.95 | 6.64 | 0.72 | -12.0 | 0.543 | 0.173 | 0.129 |
| G0 (direct) | 19.26 | 6.12 | 0.75 | -7.1 | 0.494 | 0.161 | 0.058 |
| G1 (direct, improved) | 18.37 | 5.86 | 0.83 | -0.9 | 0.485 | 0.157 | 0.063 |
| sim-B | 18.42 | 5.80 | 0.78 | -1.5 | 0.477 | 0.154 | 0.056 |
| ens (G0 + sim-B) | 18.55 | 5.85 | 0.77 | -4.3 | 0.473 | 0.155 | 0.055 |
| **ens-G1 (G1 + sim-B)** | **18.28** | **5.77** | 0.81 | -1.2 | **0.469** | **0.153** | 0.059 |

By checkpoint, MAE (runs) / chase log loss:

| model | 0 ov | 6 ov | 10 ov | 15 ov |
|---|---|---|---|---|
| resource-ipl | 31.1 / 0.699 | 23.3 / 0.584 | 18.3 / 0.525 | 11.1 / 0.364 |
| G0 | 29.4 / 0.585 | 20.7 / 0.526 | 16.5 / 0.497 | 10.4 / 0.366 |
| G1 | 27.1 / 0.584 | 20.2 / 0.518 | 16.2 / 0.483 | 10.0 / 0.353 |
| sim-B | 26.6 / 0.563 | 20.7 / 0.529 | 16.4 / 0.472 | 9.9 / 0.343 |
| ens | 27.4 / 0.565 | 20.5 / 0.504 | 16.3 / 0.475 | 10.0 / 0.348 |
| ens-G1 | 26.7 / 0.565 | 20.3 / 0.502 | 16.2 / 0.468 | 9.9 / 0.340 |

Bootstrap over matches (2,000 resamples, 5-95%, mean-of-4 difference, negative = first model better):

| comparison | MAE | pinball | win log loss | Brier |
|---|---|---|---|---|
| G0 - sim-B | +0.83 [+0.20, +1.43] | +0.32 [+0.14, +0.50] | +0.017 [-0.009, +0.041] | +0.007 [-0.001, +0.014] |
| G1 - G0 | -0.89 [-1.45, -0.29] | -0.26 [-0.44, -0.08] | -0.009 [-0.017, -0.001] | -0.004 [-0.007, -0.001] |
| G1 - sim-B | -0.05 [-0.45, +0.36] | +0.06 [-0.05, +0.18] | +0.008 [-0.016, +0.031] | +0.003 [-0.005, +0.011] |
| ens - sim-B | +0.13 [-0.20, +0.43] | +0.05 [-0.04, +0.14] | -0.004 [-0.025, +0.012] | 0.000 [-0.004, +0.004] |
| ens-G1 - sim-B | -0.15 [-0.35, +0.06] | -0.03 [-0.09, +0.03] | -0.008 [-0.026, +0.007] | -0.001 [-0.005, +0.003] |
| ens-G1 - resource-ipl | -2.67 [-3.56, -1.71] | -0.87 [-1.15, -0.57] | -0.074 [-0.119, -0.031] | -0.020 [-0.033, -0.007] |

Plain reading: the S4b work paid off. G1 is clearly better than G0 (0.9 runs lower MAE, interval clear of zero; bias -7.1 to -0.9; cov80 0.75 to 0.83) and is now a statistical tie with the simulator on every metric (G1 - sim-B: all intervals contain zero). G1 is a bit behind on pinball (+0.06) and win log loss (+0.008), ahead on MAE (-0.05); it is better at 0 overs than G0 (27.1 vs 29.4) but still behind sim-B there (26.6). The ensemble of the two different model types (ens-G1) is the lowest on all four loss columns, but its gain over sim-B (MAE -0.15, pinball -0.03, log loss -0.008) is inside the noise, so it is the best point estimate, not a proven winner. The old G0 + sim-B average does not help (it is dragged down by G0's bias). Everything beats the baseline by about 2.4 to 2.7 runs and 0.07 log loss, outside noise. Plots: `docs/img/ml_s5_h2h.png`, `docs/img/ml_s5_reliability.png`.

**2. Bias audit** (first-innings score bias = predicted median minus actual; chase calibration = mean predicted minus actual win rate; s.e. by bootstrap over matches; flag = |bias| > 2 s.e., venues need >= 8 test matches and all groups >= 8 matches; at 2 s.e. about 5% of groups are flagged by chance alone, i.e. 1-2 of 33-37). Groups: batting team (10), venue (13), checkpoint, season, toss winner bats first / fields first, and (chases only) target bucket. Plot: `docs/img/ml_s5_bias.png`.

| model | score: flagged groups | win calibration: flagged groups |
|---|---|---|
| resource-ipl | 28 of 33 (everything is 6-23 runs low) | 16 of 37 (too pessimistic for chasers in every phase and season) |
| G0 | 21 of 33 | 2 of 37 |
| ens (G0 + sim-B) | 10 of 33 | 2 of 37 |
| sim-B | 5 of 33 | 0 of 37 |
| G1 | 1 of 33 | 2 of 37 |
| **ens-G1** | **1 of 33** | **1 of 37** |

The best model for the audit and tails is **ens-G1** (lowest pinball and log loss). Its only score flag is MA Chidambaram (Chepauk) +10.6 runs (s.e. 3.9; G1 +9.7, sim-B +11.4: every model over-predicts Chepauk, which is a slow, spinning ground; a venue term would be the fix but gave no accuracy gain), and its only win flag is chases of 220+ (+0.10, s.e. 0.046: over-rates the chaser of a huge target, the same in every model). ens-G1 by season: -1.7 / -3.4 / -1.4 / +1.6 runs (2022-25), by checkpoint -3.3 / -0.4 / -0.1 / -1.1 (0/6/10/15 ov), coverage by checkpoint 0.79 / 0.79 / 0.79 / 0.87 (target 0.80; the lead's worry about G1's late coverage: G1 alone gives 0.84 / 0.81 / 0.79 / 0.88 here, so late ranges are if anything slightly wide, not narrow; the 0.70 seen earlier was the un-widened model). G1's own 2025 bias is +0.1 on these checkpoint states (+1.2 in the innings-weighted S4b table). Details for sim-B: sim-B's flags: Arun Jaitley Stadium -8.5 runs (s.e. 3.8), Eden Gardens -10.2 (4.3), MA Chidambaram (Chepauk) +11.4 (4.0), 15-over checkpoint -1.8 (0.8; coverage 0.84, a little wide), and "toss winner fields first" -3.1 (1.4; the mirror group "bats first" is +3.6, s.e. 2.4, not flagged). Those venue flags are about what 3 of 13 venues would give for a model that ignores venues (sim-B has no venue term; variant C adds one at no accuracy gain). By season sim-B's bias is -2.7 / -4.5 / -2.0 / +3.1 runs (2022 / 23 / 24 / 25, none beyond 2 s.e.), by checkpoint -2.7 / -0.8 / -0.8 / -1.8 at 0 / 6 / 10 / 15 overs. Team biases are all inside 1.4 s.e. for sim-B. G0 is too low everywhere (-15.8 at 0 overs, -11 in 2024) and the ensemble inherits half of that. Win calibration of ens-G1 by target: <160 -0.025, 160-189 -0.023, 190-219 +0.012, 220+ +0.102. For sim-B: <160 -0.008, 160-189 -0.002, 190-219 +0.024, 220+ +0.091 (s.e. 0.047; chasers of 220+ are over-rated by about 9 points, the worst group but 1.9 s.e.; G0 +0.116, s.e. 0.046, is flagged). The only win flag for G0 and ens is Gujarat Titans (-0.14, s.e. 0.066), and the 220+ bucket for G0 and ens.

**3. Noise floor** (how much of the final score is knowable). Share of final-score variance explained, 1 - MSE / Var, test innings (SD of first-innings totals = 34.4 runs). The table below was first computed for sim-B; for the best model ens-G1 the shares are 2.6% / 45.1% / 64.7% / 86.1% (RMSE 34.0 / 25.5 / 20.5 / 12.7), i.e. about the same:

| at | n | best model (sim-B) RMSE | share explained | simulator's own spread (mean SD) | ceiling implied by that spread |
|---|---|---|---|---|---|
| 0 ov | 284 | 33.9 | 3% | 31.1 | 18% |
| 6 ov | 284 | 25.7 | 44% | 23.7 | 53% |
| 10 ov | 284 | 20.7 | 64% | 19.7 | 67% |
| 15 ov | 283 | 12.9 | 86% | 13.4 | 85% |

Plain words: before a ball is bowled the final score is almost all luck from the model's point of view: the best we explain is 3% of the variance (the simulator itself thinks about 18% is learnable, so the early forecast is a little worse than it could be, probably the era drift). By 10 overs two thirds of the variance is explainable, and the model is at that ceiling (RMSE 20.7 vs the simulator's own 19.7 runs). At 15 overs 86% is explained and the rest (SD about 13 runs) is five overs of pure cricket randomness. The simulator spread and the real errors agree within 1-2 runs at every checkpoint: the model knows how uncertain it is. For chases, the average log loss of sim-B (0.563 / 0.529 / 0.472 / 0.343 at 0/6/10/15 overs) is 0.03 / 0.08 / 0.04 / 0.005 above the loss it would score if its own probabilities were exactly right (0.536 / 0.454 / 0.431 / 0.338): at 15 overs there is nothing left to gain; at 6 overs there is the most. A coin flip scores 0.693. Plot: `docs/img/ml_s5_noise.png`.

**4. Upsets and tails** (IPL 2022-25, checkpoint states; "surprise" = chase won from < 10%, or lost from > 90%; expected = sum of the probabilities):

| model | band | states (matches) | surprises | expected |
|---|---|---|---|---|
| ens-G1 | p < 10% | 122 (68) | 3 | 5.6 |
| ens-G1 | p > 90% | 153 (75) | 6 | 6.1 |
| G1 | p < 10% | 126 (69) | 9 | 6.6 |
| G1 | p > 90% | 130 (70) | 7 | 6.1 |
| sim-B | p < 10% | 148 (81) | 6 | 5.3 |
| sim-B | p > 90% | 178 (84) | 10 | 5.1 |
| ens | p < 10% | 114 (64) | 2 | 5.7 |
| ens | p > 90% | 141 (73) | 7 | 6.3 |

The distinct matches behind them (sim-B): won from < 10%: LSG chasing 213 v RCB 2023-04-10 (3.6% at 6 ov), PBKS chasing 262 v KKR 2024-04-26 (6% at ball 0), RR chasing 178 v GT 2023-04-16 (6% at 10 ov), GT chasing 159 v LSG 2022-03-28 (8% at 15 ov), DC chasing 178 v MI 2022-03-27 (8% at 10 ov), PBKS chasing 206 v RCB 2022-03-27 (10% at ball 0). Lost from > 90%: KKR chasing PBKS's 111 on 2025-04-15 (97-100% at 0/6/10 ov; KKR were bowled out for 95), LSG chasing GT's 135 on 2023-04-22 (96-99% at 6/10/15 ov), LSG chasing RCB's 126 on 2023-05-01 (92% at ball 0), DC chasing PBKS on 2023-05-13, GT chasing MI on 2022-05-06 and RR chasing LSG on 2025-04-19 (each 90-93% at one checkpoint). Scanning every ball of G0, 14 of the 283 chases passed under 10% and still won (3 under 5%), and 5 passed over 90% and lost (2 over 95%).
Verdict: the low end is calibrated (6 seen, 5.3 expected). The high end is over-confident for sim-B (10 seen vs 5.1 expected; 3 matches provide 7 of the 10 because the same game counts at several checkpoints), repeating the S2 finding. The ensembles fix it (ens-G1 6 vs 6.1 at the top, 3 vs 5.6 at the bottom, so no excess either side; G1 alone 7 vs 6.1 at the top but 9 vs 6.6 at the bottom, i.e. slightly too pessimistic about big comebacks) by pulling the simulator's 100% down; so for decision use, take the blend (ens-G1) or cap the sim top end (e.g. clip to [0.02, 0.98]). n is small (around 6-10 events): this is suggestive only.
**Last-over defences.** 46 IPL chases (2022-25) entered the 20th over needing 1-10 runs; the defence held in 3 of them (G0 expected 7.5, so the model is too kind to the defence). (n = 46 only; G1 expected 6.9 holds, so both direct models are too kind to the defence while it is the chasers that tend to win these.)
**Freak overs.** Only 10 overs in IPL 2022-25 had >= 5 sixes or >= 30 runs (3 with 5+ sixes), so this check is weak. G0's win probability moved +0.29 on average in a chase across such an over (a typical over moves it 0.05), and in the first innings the median forecast rose 21 runs; the final total stayed inside the 10-90% range G0 gave before the over in only 1 of 4 first-innings cases (n = 4). Nothing can be concluded beyond: such overs are rare and are not predicted, as they should not be.

**5. Famous matches** (win probability after every over, G0 and sim-B; the chasing team's view). G1 is drawn as a third line on each plot (`ml_curve_<id>.png`). Matches chosen by data: the two highest successful chases and the biggest comeback / collapse by G0's ball-level probability. Curves: `docs/img/ml_curve_<match_id>.png`.

| match id | match | what | G0 min / max | sim-B min / max |
|---|---|---|---|---|
| 1426280 | KKR 261, PBKS chased 262, 2024-04-26, chase won | highest successful chase | 0.25 / 0.89 | 0.06 / 1.00 |
| 1473464 | PBKS 245, SRH chased 247, 2025-04-12, chase won | second-highest | 0.17 / 0.99 | 0.14 / 1.00 |
| 1359487 | GT 204, KKR chased 207, 2023-04-09, chase won | biggest comeback | 0.01 / 0.59 | 0.00 / 0.59 |
| 1473468 | PBKS 111, KKR chased and made 95, 2025-04-15, chase lost | biggest collapse | 0.88 / 0.99 | 0.63 / 1.00 |

Both models see the same story. G0 is flatter (it rates a 262 chase at 27% before ball 1, sim-B at 6%; the chase won, which G0 liked better, but one match settles nothing) and sim-B reacts harder to the scoreboard: near the end of the 262 chase it sits at 1.00 while G0 reads 0.89.

**6. Overfitting / learning curve for G0** (test IPL 2025, fixed hyperparameters of that fold, innings-weighted):

| trained on | train rows | test MAE | test pinball | test bias | train MAE (IPL rows) | chase log loss |
|---|---|---|---|---|---|---|
| last 2 seasons | 114k | 16.11 | 5.25 | -1.1 | 14.9 | 0.411 |
| last 4 | 214k | 16.18 | 5.26 | -1.8 | 15.0 | 0.417 |
| last 8 | 333k | 16.28 | 5.24 | -3.0 | 14.8 | 0.411 |
| all | 448k | 16.21 | 5.24 | -2.8 | 14.7 | 0.407 |

The curve is flat: more history does not help or hurt (differences of 0.1 runs are noise, though the bias gets more negative with older data, as expected given the era drift). The train-test gap is about 1.5 runs for this pool (14.7 vs 16.2), small. Extra data is not the bottleneck for G0; level adaptation is. Plot: `docs/img/ml_s5_learning.png`. Single season (2025), one fit per size: indicative only.

**Verdict and what goes to the 2026 holdout.**
- **Take ens-G1 (average of G1 and sim-B) as the primary 2026 candidate, with sim-B and G1 reported alongside as the single-model fallbacks.** ens-G1 has the lowest mean-of-4 MAE (18.28), pinball (5.77), win log loss (0.469) and Brier (0.153); bias -1.2 runs; cov80 0.81; 1 of 33 score-bias flags and 1 of 37 calibration flags (both the same Chepauk and 220+ target effects every model has); no tail excess. Honest strength of evidence: its edge over sim-B is inside the noise (all intervals contain zero), so the ensemble is justified mainly because it is never worse, its calibration is best on the tails, and two model types guard against one failing in 2026. If Samar prefers one model, G1 and sim-B tie.
- Proposed pre-registered rule for 2026 (so we do not pick after peeking): primary = ens-G1; report sim-B, G1, G0 and the baseline on the same states; call a model better only if the paired bootstrap interval over matches excludes zero.
- G0 alone is dominated (21 bias flags, 0.9 runs worse than G1); the G0 + sim-B average is not useful once G1 exists; the baseline is dominated everywhere (12 runs low).
- Known limits to state in any product: the first innings before a ball is bowled is almost unpredictable (about 3% of variance); chasers of 220+ are over-rated by about 10 points; Chepauk first innings are over-predicted by about 10 runs; direct and ensemble models are too kind to a last-over defence; 220+ and freak-over events are rare so n is small.
- Selection caveat: models and the ensemble were compared on the same 2022-25 seasons (G1 was tuned on them through the S4b experiments), so margins are slightly optimistic; the 2026 holdout is the clean check. The 2026 holdout was not opened in this task.

### 2026-11-13 (lead): pre-registration for the IPL 2026 holdout, written BEFORE opening it
- **Frozen models** as of commit 918d89e. Nothing is changed after seeing 2026 results; any later fix is a new version, judged on future data.
- **Candidates:** ens-G1 (primary, the average of G1 and sim-B), with G1, sim-B, G0 and resource-ipl reported on the same states.
- **Training:** each model is refit on all seasons up to 2025 with the same tuning procedure (inner fold = 2025). The 2026 rows are used only for scoring.
- **States:** IPL 2026 at the 0/6/10/15-over checkpoints (same metrics as the S5 head-to-head), plus every over for the curves.
- **Pass rule for ens-G1:**
  - It must beat resource-ipl on first-innings MAE and on chase log loss, with the paired bootstrap interval over matches (5–95%) excluding zero.
  - 80% coverage must fall between 0.72 and 0.88.
  - |bias| must be under 5 runs.
  - ECE must be under 0.08.
- **Reporting:** the results are reported whatever they show.
- **Deep learning (GRU) step skipped:** the learning curve is flat (more history doesn't help), and from 10 overs on the models sit at the simulator's noise ceiling. A sequence model has no room left to gain. It can be revisited if the holdout shows a specific gap.

### 2026-11-13 (lead review of S5 part 1 curves)
- **Flaw found** in the PBKS 262 chase curve (`docs/img/ml_curve_1426280.png`): before a ball was bowled, G0 and G1 gave the chase a 21–27% win chance, while sim-B gave 6%.
  - A 262 target had essentially never been chased before, so the direct classifier is far too kind to huge targets. Tree models flatten out beyond the range they were trained on.
  - This matches the S5 bias flag "220+ targets over-rated by +0.10".
- **Fix for v2** (after the holdout, not before, because the models are frozen): LightGBM monotone constraints on the chase model. Win probability must fall as runs_needed and wickets rise, and rise as balls_left rises. Also add a "required minus expected" feature built from the scoring level.
- The last-over defence finding (direct models too kind to the defending side) is the same problem at the other end. Monotone constraints should help there too.
