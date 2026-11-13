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

- 2026-11-13 (S5 part 2, holdout): No bug hit; the holdout was run once (fit, then report). Two things to remember: (1) the pre-registration said "ECE" without saying pooled or mean-of-4; I used the head-to-head form (mean of the 4 checkpoints) as the literal reading and also printed the pooled one; both fail the 0.08 limit, so the choice did not matter. (2) The "season" bias group is constant (all 2026) and was dropped from the audit.

- 2026-11-13 (v2 development):
  - **Lock slip, disclosed.** Before the lock code existed I ran `tune_k_chase(inn, 2026)` on the unfiltered table once. Its "season < 2026" filter let in Jan-2026 matches of BBL 2025/26 and SA20 2025/26 (season_year 2025). I saw only the chosen k (100) and one aggregate log loss (0.694) over tens of thousands of matches, plus per-league match counts and latest dates of the locked set (no per-match results). Nothing from it was used: k was re-tuned on lock-filtered data. The fresh test is not materially compromised, but the lead should know.
  - The lock is wider than the test set: all men's non-IPL matches >= 2026-01-01 (also T20I and Hundred) are dropped from development; the fresh test set is the 9 franchise leagues.
  - The tuned chase-season weight k hit the top of its grid (first 100, then 1000) in every fold. I widened the grid once, on pre-2026 data. Result: the season-so-far rate has no pooled predictive value.
  - My first stacking pooled in logit space; on leave-one-fold-out it was worse than a plain average (over-confident). I then added a linear pool. This choice was made after looking at a table that also contains the seen 2026 fold, so v2's margins are slightly optimistic.
  - The chosen chase variant (w1m) was picked after seeing all dev folds including the seen IPL 2026 (reason: consistent small gain, simplest).
  - Non-IPL sim-B: no cache existed; the sim worker's men's-pool sim-B parquet was not ready when I finished (its script failed on an undefined name), so the non-IPL check covers the direct models only. The report picks the parquet up automatically when it exists.
- 2026-11-13 (sim-B overshoot investigation): (1) My first hypothesis (level input too high / half-life too reactive) was wrong: the level input at the start of 2026 (9.29 slow, 9.84 fast) was at or below the real 2026 scoring (9.82), and half-life or log-level changes did nothing. (2) The first "era-relative" player fix (subtract the all-men's-T20 average strength) did not help because that average does not follow the IPL's own rise; the working version rescales each ball's runs by 8 / the competition level of that match. (3) A bug found before any result: `simfix` first referenced columns (`g_rpb`) that I had already removed from the ball table; the run crashed at once, no numbers were produced. (4) `season_year` is the year a season STARTS, so BBL 2025/26 has January-2026 matches with season_year 2025: the training filter uses the match date (< 2026-01-01), not the season year.
- 2026-11-13 (flaw hunt): (1) My first feature table dropped every row dated 2026-01-01 or later, which would have removed IPL 2026; caught before any run was used, fixed by using the fresh-lock mask (men's non-IPL only). (2) I assumed the event biases were a missing-feature problem; six feature sets and one capacity test showed they are not. The bias survived, and the one training change that helped (G2, early stopping on all competitions) was found afterwards, so its margins are optimistic (chosen after seeing test results; the fresh set is untouched). (3) The v1 IPL 2026 holdout G1 had January-2026 league rows in its training pool (season_year 2025 includes them); my control re-run removes them, so it differs from the saved holdout predictions by 2.0 runs on average. (4) A blanket `taskkill` of python was refused by the harness (it could have killed other workers); I stopped only my own process by its command line. (5) Events are defined from the same ball states the model sees, and a median guess can differ from the mean for skewed outcomes; checked with the below-median share, which agrees.
- 2026-11-13 (drawing board): (1) My first empirical-lookup test used cells that were too thin for the chase (almost every state fell back to the coarse cell), so the fine and coarse chase rows were identical; I widened the cells (all balls of one over share a key) and re-ran. (2) The first D2 mixed a median prediction with a mean outcome; I added a mean variant and a stationary floor (random-match CV) before reading anything into it. (3) The first MLP script passed the hidden layers positionally and crashed (sklearn 1.9 makes it keyword-only); no result was affected. (4) LightGBM with 16 threads was about 5x slower than with 4 while other jobs ran on the machine; I fixed 4 threads. (5) IPL 2026 was not run for M1-M4 / D3-D4, to save time.
- 2026-11-13 (resources-left features, G3): (1) Three LightGBM jobs started at once (each using all 16 threads, next to another worker's heavy job) made one fold take 20+ minutes instead of 1; I killed them and re-ran with OMP_NUM_THREADS=5 each (about 40 min lost, no numbers affected; reproducibility checked: the re-run G3 equals the earlier r3 to 0.0). (2) My first unit-test expectation was wrong (best batter left at ball 0 is C, not K); fixed the test, not the code. (3) The first resources table lacked the strength of batters already out (`bat_out_str`, needed for the W3 test); added and rebuilt before any model used it. (4) The XI is rebuilt from deliveries, so a player who neither batted, bowled nor took a catch/run-out is missing (see coverage); I pad with tail-order values and did not fix this. (5) The lead's hypothesis (collapses = weaker batters left) was not supported; the model does use the new columns (best_bat_left 5.5% of score gain) but the bias stays. (6) A shell heredoc inserted a real newline into one print in flaw_plot.py; caught by the syntax error and fixed before use.
- 2026-11-13 (sim-R): (1) My own hypothesis (generic batter hides the weak real tail) was wrong; I only found that the real batter queue adds about 5 runs after running both halves separately, which I did as a diagnostic after the full run, not before. (2) The first non-IPL run was started in the background and logs were lost (shared temp folder cleaned), so I could not see its progress and lost an hour of waiting; it was stopped unfinished, so non-IPL sim-R is untested. (3) A script bug (the CLI block sat above the new functions) cost one failed launch, caught by the first run.

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

### 2026-11-13 (S5 part 2): IPL 2026 holdout results
The holdout was opened once, exactly as pre-registered. Models were frozen (commit 918d89e) and refit on seasons up to 2025 with the same procedure (inner fold 2025; the tuning chose config 2 for score and config 0 for win; sim-B 56 boosting rounds); the simulator used **1000 paths** per state. Code: `src/cricket_analytics/ml/holdout.py` (`fit`, `report`); caches `data/external/ml/holdout_*.parquet`; plots `docs/img/ml_holdout_*.png`. IPL 2026 has 74 matches; 3 are reduced (rain) and excluded as in all earlier work, leaving **71 first innings and 70 chases** at the 0/6/10/15-over checkpoints: 284 first-innings states and 274 chase states (65-70 per checkpoint; fewer late because some chases are already decided). This is small: about 70 matches, so intervals are wide.

**1. Head-to-head, same states, mean of the 4 checkpoints** (MAE in runs; bias = predicted median minus actual; cov80 = share of totals inside the 10-90% range, target 0.80; ECE = calibration error of the chase probability):

| model | MAE | pinball | cov80 | bias | win log loss | Brier | ECE |
|---|---|---|---|---|---|---|---|
| resource-ipl | 23.83 | 7.56 | 0.673 | -15.6 | 0.593 | 0.191 | 0.257 |
| G0 | 20.84 | 6.49 | 0.750 | -6.5 | 0.428 | 0.138 | 0.183 |
| G1 | 20.94 | 6.47 | 0.718 | -2.9 | 0.389 | 0.125 | 0.166 |
| sim-B | 20.14 | 6.37 | 0.757 | +6.5 | 0.315 | 0.098 | 0.081 |
| **ens-G1** | 20.23 | **6.27** | 0.764 | +1.8 | 0.344 | 0.107 | 0.117 |

MAE by checkpoint (0/6/10/15 ov): ens-G1 30.7 / 20.7 / 17.7 / 11.9; sim-B 29.7 / 21.0 / 17.6 / 12.4; G1 33.0 / 21.1 / 18.1 / 11.6; G0 34.3 / 20.5 / 17.4 / 11.2; baseline 38.0 / 26.0 / 19.2 / 12.2. Chase log loss by checkpoint: ens-G1 0.533 / 0.324 / 0.303 / 0.216; sim-B 0.506 / 0.282 / 0.274 / 0.198; G1 0.591 / 0.381 / 0.342 / 0.243; baseline 1.043 / 0.576 / 0.468 / 0.287. Plot: `docs/img/ml_holdout_h2h.png`.

Paired bootstrap over matches (5-95%, negative = first model better):

| comparison | MAE | pinball | win log loss | Brier |
|---|---|---|---|---|
| ens-G1 - resource-ipl | -3.60 [-6.15, -0.97] | -1.30 [-2.09, -0.51] | -0.249 [-0.355, -0.151] | -0.084 [-0.116, -0.054] |
| ens-G1 - sim-B | +0.09 [-0.77, +0.97] | -0.11 [-0.33, +0.13] | **+0.029 [+0.010, +0.049]** | +0.009 [+0.002, +0.017] |
| G1 - sim-B | +0.80 [-0.94, +2.53] | +0.10 [-0.36, +0.58] | **+0.074 [+0.035, +0.115]** | +0.027 [+0.011, +0.044] |
| ens-G1 - G1 | -0.71 [-1.59, +0.17] | -0.21 [-0.45, +0.04] | -0.045 [-0.066, -0.025] | -0.018 [-0.027, -0.009] |

**2. Pass rule, applied literally to ens-G1:**

| criterion | value | result |
|---|---|---|
| beats resource-ipl on first-innings MAE, interval excludes 0 | -3.60 [-6.15, -0.97] | PASS |
| beats resource-ipl on chase log loss, interval excludes 0 | -0.249 [-0.355, -0.151] | PASS |
| 80% coverage between 0.72 and 0.88 | 0.764 | PASS |
| bias under 5 runs | +1.79 | PASS |
| ECE under 0.08 | 0.117 (pooled over checkpoints 0.091) | **FAIL** |

**Overall: FAIL** (4 of 5 pass). The chase win probability of ens-G1 is not calibrated well enough on 2026 by the pre-registered ECE limit.

Plain reading. Every model is clearly better than the old baseline, and the score forecast is good: the ensemble is about 3.6 runs better than the baseline with a small bias. The failure is calibration of the chase win probability. In 2026 chasers won 64% of the time (at all four checkpoints) and every model gives them too little: ens-G1 is 8-10 points too pessimistic about the chasing team at 0 and 6 overs and 6-7 points at 10 and 15 overs. The direct model (G1) is worse (bias -0.09 to -0.18, 11 of 21 groups flagged) than the simulator (3 flagged). The simulator alone passes ECE on the pooled measure (0.055) and just misses on the mean-of-4 form (0.081 vs limit 0.08). **On the win side this contradicts the S5 part 1 ranking:** sim-B is clearly better than both G1 and ens-G1 on win log loss (intervals exclude zero), whereas in 2022-25 all three tied. On first-innings score the three are still tied (all intervals contain zero); ens-G1 is lowest on pinball (6.27) but not by a provable margin. So the ensemble's "never worse" claim does not hold for win probability in 2026: averaging a good simulator with a worse direct model dilutes it. Reported as it came; nothing is changed after the fact (rule: no peeking and re-picking). Which model to use is Samar's decision, to be made as a new pre-registered version judged on future data (2027).

**3. Bias audit** (2026; flag = |bias| > 2 s.e.; about 5% of groups are flagged by chance: about 1 of 17 score groups, 1 of 21 win groups; venues need 8+ matches, so only Narendra Modi Stadium qualifies; teams have only 5-10 matches each, so team results are noisy). Plot: `docs/img/ml_holdout_bias.png`.

| model | score groups flagged (of 17) | win groups flagged (of 21) |
|---|---|---|
| resource-ipl | 9 (all too low, -4 to -28) | 14 |
| G1 | 3 (SRH -14, 0 ov -9.4, 15 ov +3.2) | 11 |
| sim-B | 6 (all too high: +5 to +8.5 at every checkpoint, CSK +8.3, toss winner fields first +6.5) | 3 |
| **ens-G1** | **1** (15 ov +4.4, s.e. 1.5) | **7** |

Score, ens-G1: bias by checkpoint -0.5 / +1.3 / +1.9 / +4.4 runs at 0/6/10/15 overs; the single flag is the 15-over checkpoint. The blend works partly by cancellation: sim-B is 8.5 runs too high at 0 overs and G1 is 9.4 too low, so the average is near zero (-0.5); that is opposite errors cancelling, not two accurate models. Team biases are large in size but not flagged (LSG +14.9, RCB -12.9, PBKS -11.0, DC +10.1, s.e. 4-15; 5-9 matches each). Narendra Modi Stadium +3.5 (s.e. 5.1), not flagged; Chepauk, flagged in 2022-25, did not have the 8 matches needed. Coverage of the 80% range by checkpoint, ens-G1: 0.72 / 0.77 / 0.79 / 0.77 (a little narrow but in the allowed band); G1 alone 0.69 / 0.73 / 0.69 / 0.76 (guess: its conformal widening was fitted on 2025 only and 2026 is more spread out).
Win, ens-G1: flagged are the 0, 6 and 15-over checkpoints (bias -0.10, -0.08, -0.07), "toss winner bats first" (-0.20, 12 matches), Punjab Kings chasing (-0.22, 8 matches), RCB chasing (-0.14, 8 matches) and chases of a target under 160 (-0.11; all 12 of these chases were won, so any probability below 1 is "too low", a mild flag). By target: 160-189 -0.12, 190-219 -0.02, 220+ -0.09 (the 2022-25 problem of over-rating the chaser of 220+ did not recur; the sign is opposite). All flags point the same way: chasers underrated.

**4. Tails and upsets** (checkpoint states; surprise = chase won from < 10% or lost from > 90%; expected = sum of probabilities):

| model | p < 10%: states (matches), chase won, expected | p > 90%: states (matches), chase lost, expected |
|---|---|---|
| ens-G1 | 25 (16), 0, 0.9 | 58 (30), 0, 2.6 |
| G1 | 33 (18), 0, 1.6 | 44 (27), 0, 2.2 |
| sim-B | 24 (15), 0, 0.6 | 83 (35), 1, 3.0 |
| G0 | 19 (13), 0, 1.1 | 26 (18), 0, 1.7 |

No chase was won from below 10% at a checkpoint, and only sim-B had one lost from above 90% (1 seen vs 3.0 expected). On the tails the models are, if anything, slightly under-confident at the top (0 seen vs 2.6 expected for ens-G1). The 2022-25 sim-B over-confidence at the top (10 vs 5.1) did not repeat. Counts are tiny; weak evidence either way.
**Last-over defence:** 11 chases entered the 20th over needing 1-10 runs; the defence held in 0 (G0 expected 1.4, G1 0.7). Small n; chasers again did better than the models thought.

**5. Win-probability curves** (chasing team's view; G0, G1, sim-B every over):
- 1529278, 2026-04-25, Delhi Capitals 264 v Punjab Kings 265, chase won: the biggest successful chase of 2026. G1 range 0.13 to 0.96, sim-B 0.19 to 0.98. sim-B was far more optimistic early (0.84 after 6 overs vs G1 0.48); all three agree from over 16. Plot `docs/img/ml_holdout_curve_1529278.png`.
- 1529284, 2026-04-29, Mumbai Indians 243 v Sunrisers Hyderabad 249, chase won: the biggest swing (largest G1 max minus min among the other matches; chosen by rule). G1 0.21 to 0.97, sim-B 0.31 to 0.99. Plot `docs/img/ml_holdout_curve_1529284.png`.
Both chasers won, consistent with the models underrating chasers.

**6. Sanity check: scoring level.** The 2026 first-innings average is 195.8 (71 non-reduced innings; 193.0 including the 3 reduced ones). Mean forecast at 0 overs for the same 71 states: resource-ipl 167.9, G0 177.3, G1 186.3, **ens-G1 195.3**, sim-B 204.3 (mean of paths 203.9). So the ensemble matches the 2026 level (-0.5 runs); the baseline is 28 low, G0 18 low, G1 9 low (the level-relative target helps but still lags a record-high season) and sim-B is 8.5 high (a model characteristic; cause not investigated).

**Verdict (2026 evidence only, about 70 matches).**
- ens-G1 **fails the pre-registered rule on one of five criteria (ECE 0.117 vs the 0.08 limit)**; it passes the other four, including a clear win over the baseline on MAE and log loss. Reported as FAIL.
- First innings: ens-G1, sim-B and G1 are statistically tied; the ensemble's low bias comes from opposite errors cancelling.
- Chase win probability: sim-B is best and beats both G1 and ens-G1 with intervals clear of zero; every model underrates chasers in 2026 (64% won), the direct models most.
- Limits: 71 matches; teams and venues have 5-10 matches each; one season's chasing share may be a quirk, not a trend. The holdout was evaluated once; nothing was tuned on 2026.
- Not done, per the pre-registration: nothing was changed after seeing 2026; the GRU step stays skipped. Possible next version (to be judged on future data): use sim-B for win probability, or recalibrate the direct model's win output on the latest season.

### 2026-11-13 (lead): verdict on the IPL 2026 holdout, and the v2 plan
- **Verdict:** v1 (ens-G1) **fails** the pre-registered rule, on calibration only (ECE 0.117 against the 0.08 limit). It passes the other four criteria: it beats the baseline on score by 3.6 runs and on chase log loss by 0.25, coverage is 0.76, and bias is +1.8.
- **Cause (measured by us):** chasers won **64%** of IPL 2026 matches, against 45–51% in 2022–25. That is about 2.3 standard errors from 50% on 70 chases, so it is probably real (perhaps the conditions or the 2025+ second-ball rule), but it could also be luck. All models assumed the old base rate.
- **Also measured:** among non-IPL leagues in 2025–26, chasers won 64–67% of the time in the BBL, BPL, CPL and PSL, while the Blast, SA20 and T20I sat at 46–52%. A chasing advantage that differs by league and by season looks real.
- **sim-B was the best chase model in 2026** (log loss 0.315, ECE 0.081). The direct model (G1) was the worst of the ML models.

#### Pre-registration for v2 (written before any v2 work)
- **Fresh holdout:** **men's non-IPL franchise leagues, matches dated 2026-01-01 or later** (BBL 25/26 from January, BPL, PSL, SA20, ILT20, CPL 2026, MLC 2026, LPL 2026, Blast 2026). No model has been evaluated on these yet. It also tests whether the model is generic beyond the IPL.
- **Locked:** no v2 development may look at those matches. Training and tuning for this test use data dated before 2026-01-01, and IPL 2026 may be used as an already-seen fold.
- **Comparison:** v1 (ens-G1, G1, sim-B frozen at 918d89e) against v2, on the same states (checkpoints 0/6/10/15), with paired bootstrap over matches.
- **v2 is adopted only if** it beats v1 ens-G1 on chase log loss with the interval excluding zero, is no worse on score MAE (interval includes or is below zero), and has ECE under 0.08.
- **Planned v2 changes:**
  1. Monotone constraints on the chase model.
  2. A prior-only "chase-win rate so far" level for each competition and season, plus a long-run level.
  3. Ensemble weights fitted on rolling folds instead of a flat 50/50.
  4. The sim-B 0-over overshoot (+8.5 in 2026) investigated and fixed if it's a bug.

### 2026-11-13: sim-B overshoot investigation (why +8.5 runs on IPL 2026 at 0 overs; `ml/simfix.py`, `ml/ball_model.py`)
Data used: IPL 2008-2025 (rolling 2022-25 = the fair test) plus IPL 2026 as an already-seen fold. Men's non-IPL matches dated 2026-01-01 or later were not read (the training filter asserts it). 400 paths per state (2026 sim-B: the original 1000-path run; 71 first innings / 70 chases). Plot: `docs/img/ml_simfix_bias.png`.

**1. Where the bias is** (sim-B 2026 model, innings 1 from ball 0, 1000 paths): simulated vs actual runs per over, actual in brackets: overs 1-6 10.15 (9.84), overs 7-15 9.52 (9.31), overs 16-20 11.38 (10.58). So +0.3, +0.2 and +0.8 runs/over, the death overs being the biggest part. Wickets are fine (6.34 per innings vs 6.21 actual), so it is not a wicket problem. Total 203.5 vs 195.8. Through the season: the bias is present in all four blocks of 18 matches (+0.4 to +1.0 runs/over at ball level), so it is not just an early-season level lag.

**2. The scoring level is not the cause.** The level input at the first 2026 match was 9.29 (slow) / 9.84 (fast); the 2026 average was 9.82 runs/over. Using only the linear level part (no trees) the model gives 9.89 / 9.29 / 11.45 for powerplay / middle / death against actual 9.84 / 9.35 / 11.09: nearly right. The trees then ADD +0.46 / +0.66 / +1.05 runs/over. The ball-level bias of the whole model grows year by year (runs/over, predicted minus actual, PP / middle / death): 2022 -0.31 / -0.09 / -0.12; 2023 -0.57 / -0.10 / +0.16; 2024 -0.04 / +0.17 / +0.46; 2025 -0.10 / +0.36 / +0.63; 2026 +0.51 / +0.61 / +1.41. In 2026 actual death scoring (11.09) fell from 2025 (11.78) while the level kept rising; a model tied to the level cannot know that.
- What drives the trees: the batter-strength feature `bat_rpb` (career runs per ball, shrunk) is itself era-dependent: IPL average 1.35 in 2019-23, then 1.38 / 1.41 / 1.44 in 2024 / 25 / 26 (batters' records come from the high-scoring years). Replacing it with its training mean lowers the 2026 forecast by 0.57 runs/over. So the same era signal enters twice: through the level and through the players (guess for the mechanism: the trees also learned a "lag bonus" in 2023-25, when the level trailed real scoring).

**3. Fix candidates** (ball-level screen on real states, first innings; sum over an innings of predicted minus actual runs, 2022 / 23 / 24 / 25 / 26):

| candidate (one change each) | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| sim-B (baseline) | -3.2 | -3.8 | +3.3 | +5.4 | +14.7 |
| level as log-ratio | -3.3 | -4.0 | +2.7 | +5.4 | +14.2 |
| slow half-life 100 -> 50 | -3.0 | -4.2 | +2.8 | +6.6 | +16.4 |
| fast half-life 25 -> 12 | -1.8 | -3.5 | +1.5 | +4.5 | +14.8 |
| slow half-life 100 -> 400 | -4.1 | -2.7 | +6.4 | +6.6 | +15.0 |
| level slopes shrunk x0.5 (damped level) | -3.2 | -7.3 | -5.4 | -2.2 | +5.4 |
| player strengths from era-rescaled runs ("adj") | -3.5 | -4.1 | +1.8 | +2.9 | +11.5 |
| adj + level slopes x0.7 | -3.5 | -6.3 | -3.4 | -1.9 | +4.6 |
| season-neutral trees + adj ("Bsn_adj") | -4.3 | -6.5 | -0.2 | +0.5 | +8.9 |

Half-lives and the log level do nothing; damping the level just shifts every year down (2023 becomes -7). Only the player-era fixes act on the cause. (Ball level exaggerates the simulated bias by about 1.7x; the real check is section 4.) A blend toward a long-run level was not tried separately: the linear part already receives a slow and a fast level and can weight them freely, so a blend adds nothing.
- "adj": batter and bowler career strength is built from runs rescaled to a reference era (x 8 / the competition level of that match), so strength no longer carries the era.
- "season-neutral trees": while the trees are fitted, a per-season, per-phase shift is added to the linear part so that the trees cannot learn the season-level scoring; the shift is not used at prediction time.

**4. Full simulated evaluation** (400 paths; checkpoints 0/6/10/15; 2022-25: 1,135 first-innings and 1,111 chase states; 2026: 284 / 274). Bias at 0 overs = mean forecast minus actual; MAE and chase = mean of the 4 checkpoints:

| | 2022 | 2023 | 2024 | 2025 | 2026 (seen) |
|---|---|---|---|---|---|
| sim-B bias at 0 ov | -3.7 | -8.9 | -2.2 | +1.9 | +8.1 |
| Badj | -5.1 | -8.9 | -3.0 | +1.9 | +9.5 |
| Bsn_adj | -5.3 | -10.4 | -3.7 | +0.7 | +5.4 |
| sim-B MAE | 17.5 | 17.9 | 20.4 | 18.0 | 20.1 |
| Bsn_adj MAE | 17.7 | 17.9 | 20.1 | 18.2 | 19.9 |
| sim-B chase log loss / ECE | 0.485 / 0.104 | 0.548 / 0.121 | 0.389 / 0.092 | 0.483 / 0.124 | 0.315 / 0.081 |
| Bsn_adj chase log loss / ECE | 0.486 / 0.091 | 0.558 / 0.130 | 0.389 / 0.092 | 0.509 / 0.108 | 0.324 / 0.090 |

Paired bootstrap over matches, candidate minus sim-B (5-95%, negative = candidate better):

| candidate | fold | MAE | pinball | chase log loss | Brier |
|---|---|---|---|---|---|
| Badj | 2022-25 | -0.02 [-0.13, +0.10] | -0.01 [-0.04, +0.02] | -0.005 [-0.019, +0.005] | 0.000 [-0.001, +0.002] |
| Badj | 2026 | +0.06 [-0.19, +0.31] | +0.02 [-0.05, +0.09] | +0.005 [-0.001, +0.010] | +0.002 [0.000, +0.004] |
| Bsn_adj | 2022-25 | +0.03 [-0.10, +0.16] | +0.01 [-0.03, +0.05] | +0.009 [-0.003, +0.025] | 0.000 [-0.002, +0.002] |
| Bsn_adj | 2026 | -0.25 [-0.67, +0.19] | -0.09 [-0.21, +0.04] | +0.009 [-0.001, +0.021] | +0.004 [0.000, +0.009] |

**5. Last-over realism** (chases that reached the 20th over needing 1-10 runs, IPL 2022-2026, 60 chases, 1000 paths): sim-B predicts the chasing team wins 87.7% of them, actually 93.2% (56 of 60; the defence held 4 times, sim-B expected 7.4). Bsn_adj: 87.2%. By year (predicted / actual, %): 2022 91 / 92, 2023 85 / 93, 2024 88 / 100, 2025 86 / 89, 2026 88 / 92 (n = 10-14 each). A mild under-rating of chasers at the death, in line with the 2026 finding; 60 chases is too few to call it a fault.

**Verdict.** No fix passes the rule "better on the rolling 2022-25 test, not only on 2026". On 2022-25 every candidate ties sim-B within noise (all intervals contain zero), and the one that cuts the 2026 overshoot most (Bsn_adj: +8.1 to +5.4 at 0 overs) makes the 2023 bias a little worse (-8.9 to -10.4) and the 2025 chase log loss worse (0.483 to 0.509). So **sim-B2 is not adopted; sim-B stays as it was** and its caches are unchanged. What the investigation shows: (a) the 2026 overshoot is not a bug; (b) it is a double count of the era through batter and bowler strengths on top of an almost correct level (trees add +0.5 to +1.0 runs/over), plus a real 2026 drop in death-over scoring that no level-based model could foresee; (c) about 40% of the 2026 simulated bias (8.1 to 5.4) can be removed by era-neutral player strengths and season-neutral trees, with no gain on average accuracy and no provable harm, so for v2 it is a candidate to re-test on new data, not a change to adopt now.
- Not done: no non-IPL cache for the v2 stacking (no candidate won, and sim-B has only ever been fitted for IPL test years; the old `s2_preds_B_men.parquet` holds IPL test states only). Extra files for the record: `data/external/ml/s2_preds_Badj_ipl.parquet`, `s2_preds_Bsn_adj_ipl.parquet` (IPL 2022-26, columns as `s2_preds_B_ipl.parquet` plus `competition`), `simfix_screen.csv`, `simfix_lastover.csv`; models `data/external/ml/models/ball_{Badj,Bsn_adj}_ipl_{2022..2026}.pkl`.
- Code: `ml/ball_model.py` (ball table gains `bat_rpa` / `bow_rpa` and level columns `lvl_h50` / `lvl_h12` / `lvl_h400`; `BallModel` options `lvl_cols`, `lvl_log`, `lvl_shrink`, `season_neutral`; default behaviour unchanged, old pickles still load), `ml/simulate.py` (extra level columns), `ml/simfix.py` (candidates, screen, full, compare, lastover), `tests/test_ml_simfix.py`. Rerun: `python -m cricket_analytics.ml.simfix screen B,Badj,Bsn_adj` / `full Bsn_adj 400` / `compare B,Badj,Bsn_adj` / `lastover B,Bsn_adj`.


### 2026-11-13 (v2 development results; fresh holdout NOT opened)
Code: `ml/v2.py` (`run`, `report`, `final`, `fresh`), new features in `ml/features.py` (frozen list untouched), lock in `ml/evaluate.py` (`fresh_holdout_mask`, `assert_no_fresh`), tests `tests/test_ml_v2.py` (5). Full report `data/external/ml/v2_report.md`. Plots `docs/img/ml_v2_reliability.png`, `ml_v2_drift.png`, `ml_v2_lg_reliability.png`, `ml_v2_curve_1426280.png`. Final dev-trained models (all data < 2026-01-01 + IPL 2026) in `data/external/ml/models/v2/final_*`.

**Lock.** Men's non-IPL matches dated >= 2026-01-01 are dropped from every table before features are built; `split()` raises if one reaches train, validation or test (training raises even with `allow_fresh=True`). Only `fresh` may open the test rows.

**Folds.** IPL 2022, 23, 24, 25 (rolling), IPL 2026 (seen, trained on <= 2025), and non-IPL franchise leagues 2024 and 2025 (rolling, dated < 2026-01-01). Checkpoints 0/6/10/15, "mean of 4", paired bootstrap over matches (2000 resamples, 5-95%; ECE 500). n chase states: 289/281/273/268 (IPL 22-25, 1,111), 274 (2026), 1,569 + 1,317 (leagues). v1 = cached G1 / sim-B / 50-50 ens-G1; on the leagues v1 = the same G1 recipe refit (w0), which reproduces v1 G1 on IPL 2022-25 to 3 decimals.

**Per-change verdicts.**

| change | evidence (chase log loss, difference vs control w0; negative = better) | verdict |
|---|---|---|
| C1a monotone constraints only (w1m) | IPL 2022-25 -0.002 [-0.009, +0.006]; IPL 2026 -0.030 [-0.047, -0.013]; leagues -0.004 [-0.007, -0.001]; ECE 0.063 -> 0.057, 2026 0.155 -> 0.139 | **keep** (never worse, clear gain in two sets; small) |
| C1b + `req_vs_exp` / `req_ratio` (w1) | 2022-25 -0.001 ns; 2026 -0.008 ns but +0.022 [+0.008, +0.036] worse than w1m; leagues -0.002 ns | **drop** (adds nothing over monotone alone) |
| C2 chase-rate features + C1 (w2) | 2022-25 -0.011 [-0.022, +0.001]; 2026 +0.002 ns; leagues -0.002 ns | **drop** (does not hold in 2026 or leagues) |
| C2 alone (w2c) | 2022-25 +0.003 ns; 2026 +0.023 [+0.010, +0.037] (worse) | **drop** |
| C2 with fixed fast season weight k=10 (w2s) | 2022-25 0.000; 2026 -0.005 ns | **drop** |
| C3 chase ensemble, logit-space weights | vs v1-ens 2022-25 +0.010 [0.000, +0.024] (worse); 2026 -0.017 [-0.026, -0.007] | drop (over-confident) |
| C3 chase ensemble, **linear pool** (weight on direct 0.32 fitted on 2022-25, 0.20 on 2022-26) | vs v1-ens 2022-25 +0.003 [-0.003, +0.010] (tie); 2026 -0.019 [-0.030, -0.007] (weights from 2022-25 only); ECE 2026 -0.028 [-0.036, -0.005] | **keep** |
| C3 score weights (fitted per quantile) | MAE +0.02 [-0.02, +0.05], coverage 0.81 -> 0.79 | **drop**: score stays a plain 50/50 average |
| C4 score side (G1 recipe, level-relative target, conformal) | refit on dev data = v1 numbers on IPL 2022-25; leagues: MAE 18.7, bias -1.5, cov80 0.816 | fine, unchanged |

Why C2 failed: the tuned season weight k hit the top of its grid (1000) in all 7 folds, so "season so far" carried no information beyond the long-run rate. The 2026 chase surge (64%) was not predicted by any prior-only rate. All chase variants still under-rate chasers in 2026 (mean predicted - actual: w0 -0.12, w1m -0.09, v1 ens -0.08, v2 ens -0.05, sim-B -0.03; `ml_v2_drift.png`).

**v2 = G1 score model (unchanged) + monotone chase classifier (w1m); chase probability = linear pool 0.20 x v2 direct + 0.80 x sim-B (weights fitted on IPL 2022-26; 0.32 / 0.68 if fitted on 2022-25); score = 50/50 average of G1 and sim-B quantiles.** Chase log loss / ECE (mean of 4, the pre-registered form):

| model | IPL 2022-25 ll | 2022 | 2023 | 2024 | 2025 | IPL 2026 (seen) ll | ECE 22-25 | ECE 2026 |
|---|---|---|---|---|---|---|---|---|
| v1 G1 | 0.485 | 0.481 | 0.566 | 0.439 | 0.451 | 0.389 | 0.063 | 0.166 |
| v1 sim-B | 0.477 | 0.485 | 0.548 | 0.389 | 0.483 | 0.315 | 0.056 | 0.081 |
| v1 ens-G1 | 0.469 | 0.478 | 0.543 | 0.408 | 0.443 | 0.344 | 0.059 | 0.117 |
| v2 direct (w1m) | 0.483 | 0.477 | 0.581 | 0.432 | 0.439 | 0.359 | 0.057 | 0.139 |
| **v2 ens (linear pool)** | 0.472 | 0.480 | 0.551 | 0.403 | 0.452 | 0.325 | 0.045 | 0.100 |

(The 2026 v2-ens row uses weights from IPL 2022-25 only, so the weights are out of sample, but the 2026 fold is seen.) Pooled ECE for IPL 2026: v1 ens 0.091, v2 ens 0.062, sim-B 0.055. Plot `ml_v2_reliability.png`.

Score, mean of 4 (v2 ens equals v1 ens by construction, except G1's small 2026 difference from dev-data features): 2022-25 MAE v1 G1 18.37, sim-B 18.42, v1 ens 18.28, v2 ens 18.28; pinball 5.86 / 5.80 / 5.77 / 5.77; cov80 0.83 / 0.78 / 0.81 / 0.81; bias -0.9 / -1.5 / -1.2 / -1.2. IPL 2026: MAE 20.94 / 20.14 / 20.23 / 20.07; cov80 0.72 / 0.76 / 0.76 / 0.76; bias -2.9 / +6.5 / +1.8 / +2.9. Differences v2 ens vs v1 ens on score are inside noise (2026 MAE -0.16 [-0.41, +0.09]).

**Bootstrap, v2 ens minus v1 ens-G1** (negative = v2 better): IPL 2022-25 log loss +0.003 [-0.003, +0.010], Brier +0.001 [-0.001, +0.003], ECE -0.010 [-0.019, +0.009]; IPL 2026 log loss -0.019 [-0.030, -0.007], Brier -0.006 [-0.011, -0.001], ECE -0.028 [-0.036, -0.005]. v2 ens minus sim-B alone: 2022-25 -0.005 [-0.019, +0.006]; 2026 +0.010 [+0.001, +0.019] (sim-B alone still wins 2026).

**Non-IPL leagues 2024 + 2025 (rolling; direct models only so far; 1,569 + 1,317 chase states).** Log loss w0 0.427, w1m 0.423, w1 0.425, w2 0.425 (ECE 0.048 / 0.046 / 0.044 / 0.043); chasers under-rated by 3-5 points in both years (actual chase rate 0.54 / 0.53). Only the monotone model separates from noise (-0.004 [-0.007, -0.001]). Score (G1 recipe) is fine outside the IPL: MAE 18.7, pinball 5.94, cov80 0.82, bias -1.5. Plot `ml_v2_lg_reliability.png`.

**Huge targets.** Chase calibration for targets of 220+ (235 checkpoint states, IPL 2022-26; mean predicted - actual): w0 +0.019, w1m +0.003, sim-B +0.038, v1 ens +0.029, v2 ens +0.030 (small n). **PBKS chase of 262** (match 1426280, before ball 1): v1 G1 21.3%, v2 monotone 16.0% (with req_vs_exp 15.4%), v1 sim-B 6.2%, v2 ens about 8.2%. Monotone constraints only partly fix it (21% to 16%); the ensemble gets the rest from sim-B. Curve: `ml_v2_curve_1426280.png`.

**Honest read.** v2 is a modest, cheap improvement, not a breakthrough: the monotone chase model is a small consistent gain; chase-rate drift features did not work; the re-weighted ensemble ties v1 on 2022-25 and wins on the seen 2026 fold mainly by leaning on sim-B (0.8). Selection caveat: the chase variant and pooling type were picked after seeing the 2026 fold. The fresh holdout is the clean test.

**Not done.** sim-B on the non-IPL dev folds: waiting on the sim worker's `s2_preds_B_men_nonipl.parquet` (its script failed on an undefined `CHECK`); rerun `python -m cricket_analytics.ml.v2 report` once it exists and the leagues tables gain v1-ens / v2-ens rows. `fresh` calls the sim worker's `simfix.predict_checkpoints(..., "ball_B_men_fresh")`, so `simfix.fit_fresh()` must be run first. `fresh` was rehearsed on dev data (non-IPL leagues 2025 as pretend holdout, 13 matches, 100 paths with my own sim-B training path, since the simfix model did not exist yet): it runs end to end, numbers meaningless. The simfix branch of `fresh` is untested. The real fresh run was NOT executed.

**Command for the lead (opens the locked data once):**
`.venv\Scripts\python -m cricket_analytics.ml.v2 fresh` (optional `--sims 600`). It trains v1 and v2 on data < 2026-01-01 + IPL 2026, scores the 9 franchise leagues, prints the pre-registered adoption rule, and writes `data/external/ml/v2_fresh_report.md` and `docs/img/ml_v2_fresh_reliability.png`.

### 2026-11-13: sim-B for non-IPL leagues (for the v2 fresh holdout; `ml/simfix.py`)
**What was made.** (1) `data/external/ml/models/ball_B_men_fresh.pkl`: sim-B (defaults, variant B) fitted on the men's pool (all men's T20 except the Hundred), training only matches dated before 2026-01-01 plus IPL 2026 (allowed). Early stopping on IPL 2026, 204 boosting rounds. No non-IPL row dated 2026-01-01 or later was read (the training filter asserts it). (2) Sanity cache `data/external/ml/s2_preds_B_men_nonipl.parquet`: rolling (train before the test year, men's pool) non-IPL checkpoints 0/6/10/15 for 2024 and 2025, 300 paths; columns as `s2_preds_B_ipl.parquet` plus `competition`. Test matches dated 2026 (BBL 2025/26 January games) are excluded; the latest match in the file is 2025-12-31. Models `ball_B_men_{2024,2025}_nonipl.pkl`. (3) `simfix.predict_checkpoints(keys, model="ball_B_men_fresh", n=1000)` takes a DataFrame with `match_id, innings, balls_bowled` and returns `target, q10, q50, q90, mean, sd, win, wk_mean`; CLI `python -m cricket_analytics.ml.simfix fresh_fit` refits the model, `... nonipl` rebuilds the cache. The function does not check the lock; the caller decides which matches to ask for.

**Sanity check** (13,050 states: 7,109 T20I, 1,846 Blast, 764 ILT20, 749 BPL, 512 SA20, 501 PSL, 496 CPL, 440 BBL, 391 MLC, 178 LPL, 64 SMAT; chase states 3,382 in 2024 and 2,922 in 2025). First innings, mean forecast minus actual (bias) / MAE / 80% coverage by checkpoint:

| year | 0 ov | 6 ov | 10 ov | 15 ov |
|---|---|---|---|---|
| 2024 (n 918 / 918 / 915 / 898) | +2.5 / 30.5 / 0.73 | +1.1 / 21.8 / 0.71 | +0.1 / 17.2 / 0.73 | -1.1 / 10.7 / 0.76 |
| 2025 (n 777 / 777 / 777 / 766) | +3.5 / 30.7 / 0.70 | +1.6 / 21.8 / 0.73 | +1.4 / 16.3 / 0.77 | +0.3 / 10.9 / 0.77 |

Chase win probability (mean of 4 checkpoints): 2024 log loss 0.394, Brier 0.130, ECE 0.039 (mean p 0.481 vs actual 0.502); 2025 log loss 0.376, Brier 0.121, ECE 0.038 (0.508 vs 0.506). By competition in 2025, bias at all checkpoints: T20I +5.1 (n 1,741), Blast -4.5 (492), ILT20 -3.5, MLC -5.6, SA20 -1.8, CPL +1.5, BBL +1.3, PSL -1.5, BPL +14.7 (only 24 states). Plain reading: on non-IPL leagues the men's-pool sim-B is well calibrated for chases (ECE under 0.04, better than its IPL ECE) and has a small score bias (+0.3 to +3.5 runs); ranges are a little narrow at 0-10 overs (coverage 0.70-0.77, the same weakness as in the IPL). T20I runs about 5 runs high and the Blast about 4 low, so league-level effects exist (small samples for BPL, BBL). Not compared with the old baselines or G1 here.

### 2026-11-13 08:58 (lead): fresh holdout result (men's non-IPL franchise leagues, ≥ 2026-01-01; run once)
- **Sample:** 316 first innings (1,262 states) and 312 chases (1,206 states). sim-B used 600 paths. The full output is in `data/external/ml/v2_fresh_report.md`.
- **v2 ADOPTED: NO.** Chase log loss is v2 0.426 against v1 0.428, a difference of −0.002 [−0.007, +0.003], a tie. The score side is identical, because the score part of v2 is the same as v1.
- **The bigger finding: both v1 and v2 pass calibration on unseen leagues.** ECE is 0.046 / 0.051 (mean of 4 checkpoints) and 0.033 / 0.030 pooled, against the 0.08 limit. Score MAE is 19.2, 80% coverage 0.77, and bias about +2 runs.
  - So the IPL 2026 failure was specific to that season's chasing surge, not a general flaw. The model transfers to other leagues.
- **Ensemble vs sim-B alone:** the ensemble is better on score (MAE −0.26 [−0.41, −0.09]) and ties on chase prediction.
- **League gaps (predicted minus actual chase win rate):** CPL −0.07 and PSL −0.07 under-rate chasers, again the high-chase leagues. ILT20 has n=3, too few to read.
- **Missing:** the run did not include the resource baseline, so "beats the baseline" is not tested on this set. It was tested on IPL 2022–25 and 2026.
- **Decision:** keep **v1 ens-G1** as the production model, because v2 is not proven better. The monotone constraint is still worth carrying into v1's chase model for sanity with huge targets (262 chase: 21% → 16%), but only as a logged, non-accuracy change.

### 2026-11-13 (pre-match worker): pre-registration for the pre-match model fresh run, written BEFORE running it
Model: `ml/prematch.py` (see the "Pre-match model" entry below once the run is done). This is a new model, so the locked set (men's non-IPL franchise leagues, dated 2026-01-01 or later) is clean for it. Development used only matches before 2026-01-01 plus the already-seen IPL 2026.
- **Primary model:** `logit` = antisymmetric logistic on Elo difference, run-margin strength difference and home advantage; toss is NOT used (the point is a forecast before the toss). `elo` and `logit+toss` are reported as secondary.
- **Pass rule (all must hold):** (1) log loss beats the 50% coin-flip baseline, with the paired bootstrap over matches (5%-95%) of (model minus baseline) entirely below 0; (2) ECE < 0.08 (10 bins, pooled). Score forecasts are reported but not part of the rule.
- **Procedure:** parameters fixed from pre-2022 tuning (`models/prematch/params.json`); coefficients fitted on every match not in the locked set; test features come from the full history (earlier 2026 matches are known, prior-only). Run once with `python -m cricket_analytics.ml.prematch fresh` (a flag file refuses a second run).
- **Expectation, stated in advance:** about 300 matches, so the bootstrap interval is about plus or minus 0.01 log loss wide; on the 2024-25 development leagues the primary model was -0.010 [-0.021, +0.001]. A FAIL on rule (1) is a likely outcome and will be reported as FAIL.

### 2026-11-13 (pre-match worker): Pre-match model (`ml/prematch.py`) - result: small gain on leagues, none in the IPL, fresh run FAIL
**What it is.** `cricket_analytics.ml.prematch.predict(competition, venue, team_a, team_b, date=None, toss_winner=None, toss_decision=None, xi_a=None, xi_b=None)` returns `score_a_q10/q50/q90`, `score_b_q10/q50/q90` (each side's first-innings score if it bats first), `p_a_win` and a `parts` dict (level, venue effect, Elo, attack/defence, home, which win model). Everything uses only matches dated before `date` (same-day matches do not see each other); names are matched loosely ("Wankhede Stadium" works). Rolling backtest and fresh run: `python -m cricket_analytics.ml.prematch backtest | report | fresh | fit`. Model file `data/external/ml/models/prematch/model.json` (+ `params.json`).
- **Score:** level (decayed competition mean) + venue effect + batting-team attack + bowling-team defence (all shrunk, from first innings only), weighted OLS; the 10/50/90 range is the recent residual quantiles of the competition. Separate coefficients for national teams, franchise leagues, and any competition with 250+ earlier matches (IPL, Blast, ...).
- **Win:** logistic with no intercept on three differences (Elo, run-margin strength, home advantage); trained on swapped copies, so swapping the teams gives exactly 1 - p when the toss is unknown. `logit+toss` adds the toss winner and decision. Elo: K and the between-season pull-back tuned on pre-2022 data only. Home comes from `reference/team_home.csv` + `venue_country.csv`.
- **Not used:** XI strength (`xi_a`, `xi_b` are accepted and ignored). Player values are not cheaply prior-only; not tested.
- **Tests:** `tests/test_ml_prematch.py` (prior-only: deleting later matches changes nothing; 0 <= p <= 1; swap gives 1 - p; toss; name matching). All 44 `tests/test_ml_*.py` pass.

**Win probability, log loss (coin flip = 0.6931; lower is better; diff = model minus coin flip, paired bootstrap 5-95% over matches).**

| set | n matches | model | log loss | Brier | accuracy | ECE | diff [5%, 95%] |
|---|---|---|---|---|---|---|---|
| IPL 2022-25 | 289 | coin flip | 0.6931 | 0.2500 | 0.50 | 0.002 | - |
| | | Elo | 0.7001 | 0.2534 | 0.46 | 0.060 | +0.0069 [+0.0021, +0.0119] |
| | | logit | 0.7103 | 0.2586 | 0.41 | 0.127 | +0.0172 [+0.0075, +0.0270] |
| | | logit+toss | 0.7189 | 0.2626 | 0.47 | 0.086 | +0.0257 [+0.0116, +0.0406] |
| IPL 2026 (seen) | 73 | Elo | 0.6911 | 0.2490 | 0.52 | 0.072 | -0.0021 [-0.0087, +0.0048] |
| | | logit | 0.6925 | 0.2497 | 0.51 | 0.075 | -0.0007 [-0.0146, +0.0137] |
| | | logit+toss | 0.6771 | 0.2420 | 0.59 | 0.086 | -0.0160 [-0.0385, +0.0067] |
| Leagues 2024-25 (dev) | 806 | Elo | 0.6841 | 0.2455 | 0.56 | 0.036 | -0.0091 [-0.0180, +0.0002] |
| | | logit | 0.6829 | 0.2449 | 0.56 | 0.027 | -0.0103 [-0.0211, +0.0008] |
| | | logit+toss | 0.6823 | 0.2446 | 0.57 | 0.027 | -0.0108 [-0.0223, +0.0012] |
| **Leagues 2026 (FRESH, run once)** | 330 | Elo | 0.6864 | 0.2465 | 0.61 | 0.105 | -0.0068 [-0.0202, +0.0059] |
| | | **logit (primary)** | 0.6837 | 0.2451 | 0.59 | 0.069 | -0.0094 [-0.0244, +0.0047] |
| | | logit+toss | 0.6800 | 0.2433 | 0.56 | 0.040 | -0.0131 [-0.0309, +0.0044] |

(The coin flip's accuracy is 0.50 by chance because it always picks team B. Rolling folds: each season is fitted on earlier seasons only. Leagues = BBL, Blast, BPL, CPL, ILT20, LPL, MLC, PSL, SA20.)

**First-innings score (runs; same matches for every row; cov80 = share inside the 10-90% range, should be 0.80).**

| set | model | MAE | pinball | cov80 | bias |
|---|---|---|---|---|---|
| IPL 2022-25 (284) | (a) competition level | 26.85 | 8.50 | 0.75 | -7.1 |
| | level + venue | 26.55 | 8.40 | 0.76 | -4.5 |
| | level + venue + teams | 26.64 | 8.45 | 0.76 | -6.2 |
| | in-play G1 at ball 0 | 27.07 | 8.49 | 0.84 | -3.9 |
| | in-play sim-B at ball 0 | 26.62 | 8.40 | 0.77 | -2.7 |
| IPL 2026 (71, seen) | level / +venue / +teams | 30.05 / 29.52 / 30.06 | 9.05 / 8.98 / 9.16 | 0.75 / 0.75 / 0.73 | -1.2 / +2.6 / -2.3 |
| | in-play G1 / sim-B at ball 0 | 33.04 / 29.66 | 9.85 / 9.21 | 0.69 / 0.69 | -9.4 / +8.5 |
| Leagues 2024-25 (749) | level / +venue / +teams | 26.24 / 26.21 / 26.51 | 8.41 / 8.42 / 8.49 | 0.78 / 0.78 / 0.78 | -1.6 / -1.4 / +1.5 |
| | in-play G1 / sim-B at ball 0 | 26.51 / 26.87 | 8.48 / 8.61 | 0.82 / 0.75 | -2.5 / -2.0 |
| Leagues 2026 FRESH (316) | level / +venue / +teams | 28.04 / 27.71 / 27.24 | 8.71 / 8.62 / 8.55 | 0.75 / 0.75 / 0.76 | +4.3 / +5.1 / +6.2 |

Paired MAE difference vs the competition level, 5-95%: venue -0.31 [-0.74, +0.14] (IPL 22-25), -0.03 [-0.26, +0.22] (leagues dev); venue + teams -0.22 [-0.65, +0.22] and +0.27 [-0.17, +0.71]. All intervals contain 0. In-play models at ball 0 know the opening pair, so they are a reference, not a fair pre-match contest. In-play win at ball 0 of the chase already knows the target, so it is not comparable and not shown.

**Pre-registered fresh run: FAIL.** Rule (1), log loss below the coin flip with the interval entirely below 0: primary model -0.0094 [-0.0244, +0.0047], the interval contains 0, so FAIL. Rule (2), ECE < 0.08: 0.069, PASS. Overall FAIL (n = 330 matches). Files: `data/external/ml/prematch_report_fresh.md`; plots `docs/img/ml_prematch_reliability_{dev,fresh}.png`, `ml_prematch_logloss_{dev,fresh}.png`.

**Plain reading.**
- Pre-match T20 is close to a coin flip, as the literature says. In leagues the rating models are about 0.01 log loss better than 50% in dev (806 matches) and fresh (330), the same direction both times, but not provable at this sample size (the interval touches or crosses 0). Accuracy is 56-59%.
- **In the IPL the rating models are worse than a coin flip in 2022-25** (the whole interval is above 0, accuracy 41-47%) and about equal in 2026. A guess, not tested: the 2022 mega-auction and impact-player years reshuffled squads, so last year's rating says little, while the fit learned from earlier years that ratings persist. On the pre-2022 IPL folds (2017-21) Elo was 0.690 against 0.693, also near a coin flip. For the IPL the honest pre-match answer is about 50%, shifted slightly by toss and home.
- Toss helps a little in leagues and 2026 (logit+toss is best everywhere except the 2022-25 IPL), but the effect is small.
- Score: the competition level does almost all the work (MAE 26-28 runs, which is just the spread of T20 totals). Venue and team effects move the median by a few runs but do not provably help. The 10-90% range is slightly too narrow (cov80 0.75-0.78). On the fresh leagues the level is 4-6 runs low (2026 scoring rose and the level lags a rising season, the same issue as in-play).
- The pre-match score range is as good as the in-play models at ball 0 (IPL MAE 26.6 for level + venue, same as sim-B, 27.1 for G1), so the in-play models add nothing before ball 1, as expected.
- Recommendation for the dashboard: show the score range and the win % with a clear "close to a coin flip" caption; use the IPL win % only together with the toss, and never present it as a confident call.

**Mistakes and notes (pre-match worker).**
- My first version fitted one set of coefficients on all men's matches; the IPL came out worse than a coin flip. I changed to per-group / per-large-competition coefficients (the IPL still loses, so that was not the main cause). That change was made after seeing the dev folds (IPL 2022-25 included), so dev margins are slightly optimistic; the fresh set was not seen.
- Tuning grids (pre-2022 data only): Elo K 10-30 and between-season pull-back 0.4-1.0 per group; venue shrinkage k 30-1000 and team k 2-15. The chosen venue k is 1000 (top of the grid, i.e. almost no venue effect beyond the regression coefficient) and the franchise pull-back is 1.0 (top of its range); I did not widen them. Logistic regularisation made no difference on pre-2022 IPL / BBL / Blast folds, so C = 1.
- Women's matches are in the rolling state (own key) and a women's model is fitted, but it is not backtested.

### 2026-11-13 (luck worker): Luck tracker (`ml/luck.py`, dashboard tab "Luck & surprises")

**What it is.** Per decided IPL chase, from the win-probability curve of the chasing team after each over (G1 direct model, cached **out-of-sample** per-ball predictions: rolling folds IPL 2022-25 and the 2026 holdout; 353 matches, ties/no-results skipped). Not the full blend per over: sim-B per-over probabilities are not cached (replaying via `predict_match_curve` costs about 10 s/match and is in-sample for the IPL). The start-of-chase probability is the blend (G1 + sim-B) / 2 from the caches. The first innings has no win curve (G1 win is chase-only), so first-innings swings are not tracked.
- **Surprise** = 1 - P(winner) at the start of the chase. **Comeback** = winner's lowest probability during the chase. **Swing** = sum of |change| per over (the final move to the real result is included). **Lead changes** = crossings of 50%. **Decisive over** = biggest single move, with runs/wickets from the deliveries.
- **Luck** per team-season = wins - expected wins, with expected = sum of pre-chase probabilities (1 - p for the side batting first). Also z = luck / sqrt(sum p(1-p)), and a chase-adjusted version where the season's pre-chase logits are shifted by one constant so the mean equals the real chase win rate.

**Validation.** Luck sums to 0 across teams by construction (each match gives +x to one side, -x to the other), so that is not a test. Real checks: the model's mean chase probability vs the real chase rate per season, and the spread of z (about 1 if probabilities are honest).

| season | matches | real chase win rate | model mean | bias | sd of team z (raw / adjusted) |
|---|---|---|---|---|---|
| 2022 | 74 | 50.0% | 51.5% | -0.015 | 1.16 / 1.15 |
| 2023 | 71 | 45.1% | 44.8% | +0.003 | 0.92 / 0.92 |
| 2024 | 70 | 51.4% | 51.5% | -0.001 | 0.62 / 0.62 |
| 2025 | 68 | 51.5% | 52.8% | -0.014 | 0.92 / 0.92 |
| 2026 | 70 | 64.3% | 54.1% | +0.102 | 1.03 / 1.06 |

Only 2026 has a real chase bias (+10 points). It moves individual teams by up to 0.5 wins (LSG +0.25, DC -0.66 vs raw), and the team ranking barely changes (correlation 0.97).
Caveat (measured, not fixed): the G1 curve is noisy in the first overs (it can move 10-20 points in one ball), which inflates the swing numbers (mean swing about 1.0-1.3). Rank matches by swing, do not read the absolute value. The decisive over can be over 1 because of this noise. The curve at over 0 is G1 alone while surprise uses the blend, so the first step is not exactly the blend.

**IPL 2026 team luck** (wins in decided matches only, so totals differ a little from the table):

| team | matches | wins | expected | luck | luck chase-adj. | z |
|---|---|---|---|---|---|---|
| Royal Challengers Bengaluru | 15 | 11 | 9.3 | +1.7 | +1.7 | +1.1 |
| Gujarat Titans | 17 | 10 | 8.9 | +1.1 | +0.9 | +0.6 |
| Sunrisers Hyderabad | 15 | 9 | 8.0 | +1.0 | +1.6 | +0.6 |
| Punjab Kings | 13 | 7 | 6.1 | +0.9 | +0.5 | +0.5 |
| Delhi Capitals | 14 | 7 | 6.2 | +0.8 | +0.1 | +0.5 |
| Rajasthan Royals | 15 | 8 | 7.3 | +0.7 | +1.1 | +0.4 |
| Chennai Super Kings | 14 | 6 | 6.3 | -0.3 | -0.1 | -0.2 |
| Mumbai Indians | 13 | 4 | 4.6 | -0.6 | -0.7 | -0.4 |
| Kolkata Knight Riders | 12 | 5 | 7.4 | -2.4 | -2.5 | -1.6 |
| Lucknow Super Giants | 12 | 3 | 6.0 | -3.0 | -2.7 | -2.1 |

LSG are the only team beyond |z| 2 (one team out of ten, as expected by chance). **Top 5 surprises, IPL 2026** (winner's chance at the start of the chase): 1529278 Punjab Kings chased down Delhi Capitals (15%); 1529275 Rajasthan Royals beat LSG, who were chasing (15%); 1529299 Gujarat Titans beat SRH (22%); 1529284 SRH over Mumbai Indians (24%); 1529290 Mumbai Indians over LSG (26%). (Most swingy: 1529301 MI v PBKS, 1529269 DC v RCB, 1529297 RCB v MI.)

**Top team-season luck 2022-25** (biggest +/-): 2022 Gujarat Titans +4.0 (12 wins vs 8.0 expected), CSK -2.9, MI -3.1; 2023 MI +2.8, SRH -2.8; 2024 RR +1.3, PBKS -1.4; 2025 RCB +3.1, CSK -2.5. Top surprise each season: 2022 LSG over CSK (82%), 2023 RCB over LSG (89%), 2024 Punjab Kings' 262 chase v KKR (86%, matches the famous result, a sanity check), 2025 Punjab Kings over KKR defending 111 (97%). Full tables: `luck.team_luck("ipl", season)`.
Interpretation: this is "luck relative to this model's pre-chase view" - a strong team beating a weak one is not luck, a weak-looking team winning is. It does not know about toss, injuries or the middle of the match.
**Scope.** IPL 2022-26 only (the only competition with cached out-of-sample curves). Tests: `tests/test_ml_luck.py` (3, synthetic curve and calibrated luck), `tests/test_dashboard_predictor.py` (+1, tab loads and runs).

### 2026-11-13 (error-analysis worker): where v1 ens-G1 is good or bad
Out-of-sample error report by team, venue, season, match type and biggest misses (IPL 2022-26 plus the non-IPL 2026 fresh set): see [ML_ERRORS.md](ML_ERRORS.md). Code: `ml/error_report.py`. Short version: no team is flagged; Chepauk is the one flagged IPL venue (guesses about 9 runs high, and the baseline beats the model there); very low (<160) and very high (220+) totals are pulled toward the middle; chase calibration is fine 2022-25 and off in IPL 2026 (chasers won 64%, model 57%).

### 2026-11-13 (lead): event tests (G1 out-of-sample, IPL 2022–26, at over ends 3–17)
- **Collapse** (3+ wickets in 12 balls), 35 matches:
  - First-innings prediction is too high by **+10.8 runs** [4.2, 17.2], against −0.6 normally. The model **under-reacts to collapses**.
  - Chase: predicted 22% against 16% actual, gap interval [−0.01, +0.12]. The same direction, but not proven.
- **Big over** (20+ runs), 119 matches:
  - First-innings bias is −3.4 [−6.8, +0.3].
  - Chase: predicted 56% against 61% actual, gap interval [−0.10, +0.01].
  - Mild under-reaction, borderline.
- **Powerplay:**
  - The pre-match prediction explains about 0% of final-score variance (−3%), and its correlation with powerplay runs is 0.08.
  - Powerplay runs (mean 54.5, SD 14.6) correlate 0.64 with the final total, and 0.28 with the runs scored in the remaining 14 overs.
  - So the early error is mostly irreducible luck. Once the powerplay is known, the model explains 46%.
- **Fix idea (not done):** stronger short-window momentum features for G1 (last 12 balls, wickets in the last 12), or a bigger simulator weight after shock events. The simulator reacts harder, so this needs checking on the blend.

### 2026-11-13 (flaw-hunt worker): flaw hunt + feature fixes (`ml/flaw_tests.py`, `ml/flaw_fit.py`, `ml/flaw_plot.py`, new builders at the end of `ml/features.py`)
**Plain summary.** The lead's finding is real and general: G1 reacts too little to sudden events. After a collapse it guesses too high, after a burst it guesses too low, and in extreme states (many or few wickets left late) it is pulled toward the middle. This holds in the IPL and in other leagues and in every season. **No new feature fixed it** (recent-balls windows, partnership/"set batter out" features, recent venue form: all tested). What did help a little is a change in how G1 is trained: stopping the training by looking at all competitions of the previous season, not only the ~70 IPL matches. That cuts the event biases by about a quarter and improves the chase probabilities everywhere, but it does not remove them. I call that version **G2** (same columns as G1). It was chosen after I had seen the test results, so it is a candidate, not a proven fix (see caveats).

**Method (part A).** States = ends of overs 3-17 (balls 18-102). For each event the bias (innings 1: median guess minus the real final total, in runs; chase: mean win probability minus real win, in probability points "pp") is compared with non-event states of the same over (weighted by the event's own over mix), so the phase does not confuse it. Intervals = 5-95% bootstrap over matches (2000 resamples for the G1 / sim-B tables, 1000 for the variant comparisons). Out-of-sample only: IPL 2022-25 rolling + IPL 2026 holdout caches (pooled as "IPL", 71-74 matches per season) and non-IPL men's 2024-25 (1695 matches, produced with the same G1 recipe, rolling by season; I checked that the IPL 2022-25 predictions of this re-run are identical to the saved `s4b_g1` cache: max difference 0.0). Locked fresh data (men's non-IPL from 2026-01-01) is removed from the feature table and was never used. sim-B and ens-G1 only at its checkpoints (6/10/15 overs). Extra check for innings 1 because a median guess can differ from the mean when the outcome is skewed: "below-median share" = share of actual totals under the median guess minus 50%; it agrees with the run bias (collapse 2 wickets in 12 balls: +10 pp in the IPL, +6 pp elsewhere), so it is not a skew artefact. 80 event rows per model; saved in `data/external/ml/flaw_battery.csv`, plot `docs/img/ml_flaw_events_g1.png`.

**Ranked flaw table, G1 (`*` = 5-95% interval excludes 0; excess over matched non-event states; runs for innings 1, pp for chase; n = matches).** Ranked by size and consistency; "-" = fewer than 8 matches.

| rank | event | IPL innings 1 | other leagues innings 1 | IPL chase | other leagues chase | reading |
|---|---|---|---|---|---|---|
| 1 | collapse, 3 wkts in 6/12/18 balls | +11.5* (12b, n=35) / +8.8* (18b) | +12.9* / +9.4* / +7.1* | +8.6* / +9.0* | +14.0* (6b) / +6.6* / +5.4* | strongest: guesses far too high |
| 2 | chase needing 13+ an over | - | - | +8.5* (n=167) | +6.6* (n=653) | win chance too high |
| 3 | death start (over 16) with 6+ wkts in hand | -3.8* | -3.7* | -6.8* | -6.1* | too pessimistic (extreme state pulled to the middle) |
| 4 | late, 7+ wkts in hand / late, 4 or fewer in hand | -2.7* / +3.0* | -2.8* / +3.3* | -6.0* / +5.6* | -4.7* / +6.1* | same pull to the middle |
| 5 | collapse, 2 wkts in 12/18/24 balls | +4.9* / +4.7* / +4.4* | +4.5* / +3.8* / +3.5* | +6.9* / +6.3* / +5.5* | +4.5* / +4.2* / +3.8* | milder, very consistent |
| 6 | new pair (both batters faced < 6) | +4.1* | +3.9* | +3.4 | +3.6* | too high |
| 7 | burst (top 10%: 16+ in 6, 28+ in 12, 39+ in 18 balls) | -2.0* (6b) / -1.3 / -1.4 | -3.6* / -4.8* / -4.9* | -2.1 / -2.4 / -1.7 | -3.8* / -3.6* / -3.8* | too low; weaker in the IPL |
| 8 | slow middle (overs 7-12 under 7 an over) | +0.6 | +2.8* | +1.6 | +2.5* | small, other leagues only |
| 9 | venue cooler lately (recent mean 10+ runs under its long run) | - | -6.7* (n=37) | - | -2.3 | guesses too LOW (n small; sim-B agrees: -6.5) |
| 9 | venue hotter lately (10+ runs over) | -4.0* (n=71) | -0.6 | +2.4 | -4.6 | guesses too low in the IPL (borderline) |
| 10 | set batter (30+ balls) just out | -0.6 | +0.0 | +2.3 | -0.8 | **no bias** |
| 10 | set pair (both 20+ balls) | -0.7 | -1.5* | +0.2 | -4.0* | small |
Significant rows of all 18-22 per group: IPL innings 1 11/18, IPL chase 11/20, other leagues 18/20 and 18/22. Same direction in IPL and other leagues for every row of ranks 1-8: generality is clear. By season the collapse bias (2 wkts in 12 balls) is positive in all 7 season groups (IPL 2022 +8.3, 2023 only +0.3, 2024 +6.5, 2025 +6.3, 2026 +4.5; other leagues 2024 +5.5, 2025 +2.8), so it is not one odd year. The old resource-table baseline was not tested here.
**Other models.** sim-B (checkpoints only) has the same direction and about half the size on collapses (other leagues 3 wkts in 12 balls: +6.1 runs vs G1 +9.4) but it is also biased and, in the IPL, a set batter out gives -12 pp on the chase (n=47, not seen for G1). The 50/50 blend ens-G1 has almost no significant innings-1 event biases in the IPL (2 of 18) but this is at 3 over ends only (n small) and the blend still shows the same biases on other leagues (16/19) and on the chase (7/20 IPL, 11/22 other leagues). So the blend helps a bit but is not a fix. Full tables: `data/external/ml/flaw_report_g1.txt`.
**Two quick diagnoses.** (1) In-sample check (fold 2025 model on its own training seasons 2023-24): the collapse bias is about half as large in other leagues (+2.3 runs after 2 wkts in 12 balls, vs +4.5 out-of-sample) and not clear in the IPL (n small), so part is under-fitting and part is out-of-sample. (2) More tree capacity (63 leaves, min 50 rows, light regularisation) made the event biases slightly worse, not better, and worsened overall metrics (other leagues pinball +0.049 [+0.033, +0.068]); so it is not simply "the trees are too small".

**Part B: feature experiments (one change each; rolling IPL 2022-25 n = 284 innings 1 / 283 chases; seen fold IPL 2026 n = 71; other leagues men's 2024-25 n = 1695; differences vs the control = paired bootstrap over matches; control `g1r` = G1 re-run on the same code).** Columns: dMAE / dpinball (runs) and dLL (chase log loss); negative = better; `*` = interval excludes 0. "Event" = does it remove a significant event bias? (headline events: collapses, bursts, death start, late wickets, rrr 13+, new pair.)

| id | change | IPL 22-25 dMAE / dpin / dLL | IPL 2026 dMAE / dLL | other leagues dMAE / dpin / dLL | events | verdict |
|---|---|---|---|---|---|---|
| F1a | add runs/wkts in last 6, 12, 18 balls (keep l30) | +0.04 / +0.026 / +0.001 | -0.12 / -0.004 | +0.03 / +0.003 / +0.004* | no change (collapse 3wk/12b IPL 11.5 -> 12.1) | **drop** |
| F1b | replace l30 by l18 (best single window for first-innings loss on the inner folds) | +0.00 / +0.010 / +0.010* | +0.16 / +0.010* | -0.07* / -0.023* / +0.004* | no change | **drop** (chase worse) |
| F1c | replace l30 by l12 (best single window for chase loss on the inner folds) | +0.11 / +0.027 / +0.007 | +0.18 / -0.018* | -0.01 / -0.003 / +0.002* | no change | **drop** |
| F2 | wickets-in-hand x balls-left, partnership balls + runs, balls since a set batter fell | -0.01 / +0.007 / +0.002 | -0.09 / -0.002 | -0.05* / -0.018* / +0.003* | no change | **drop** (gain only in other leagues, 0.3%) |
| F3 | recent-venue effect (last 730 days, shrunk k=30 chosen on season 2021 only) next to the long-run one | +0.15 / +0.019 / -0.010* | +0.44 / -0.014* | +0.08* / +0.013 / -0.005* | chase biases -0.5 to -1.5 pp; innings 1 slightly worse | **drop** as a score feature; helps the chase classifier vs g1r but see below |
| F4 | only "balls since last wicket" (pair_balls) | -0.03 / +0.002 / +0.003 | +0.16 / -0.000 | +0.00 / -0.005 / +0.008* | no change | **drop** |
| F5 | sim-B momentum input | not done (a ball-model retrain plus 4 folds of 1000-path simulations is not quick) | | | | skipped |
Window screen (inner folds only, no test rows touched; lower = better; score = sum of three quantile losses, win = chase log loss, mean of 4 folds): l30 (current) 0.1716 / 0.4422; only l6 0.1715 / 0.4444; only l12 0.1717 / 0.4376; only l18 0.1713 / 0.4439; only l24 0.1714 / 0.4422; only l36 0.1716 / 0.4382; l6+l12+l18+l30 0.1716 / 0.4436; **no window at all 0.1713 / 0.4445**. Differences are 0.0005 or less, inside the noise of the ~70-match inner folds: **the momentum window is worth nothing measurable either way.**
F4 check: the existing set-ness columns (balls the striker / non-striker already faced) rank 18th and 19th of 25 for the score model (gain 1.8% and 1.5%) and 22nd / 23rd of 25 for the chase classifier (0.16%). The "new pair" bias is real (+4 runs) but the extra "balls since last wicket" feature did not move it.

**What did work: the early-stopping set (G2).** G1 picks its number of trees by early stopping on IPL season Y-1 only (about 70 matches). G2 stops on all competitions of season Y-1 (all men's matches, rows dated before 2026-01-01); the conformal widening deltas also come from that set. Same columns, same everything else. (diagnostic variant "gval"; the saved model set "g2" reproduces it exactly.)

| scope | model | MAE | pinball | cov80 | chase LL | ECE | G2 minus G1: dMAE / dpin / dcov / dLL |
|---|---|---|---|---|---|---|---|
| IPL 2022-25 (n 284/283) | G1 | 16.30 | 5.169 | 0.815 | 0.444 | 0.033 | |
| | G2 | 16.32 | 5.167 | 0.827 | 0.433 | 0.029 | +0.03 [-0.11, +0.16] / -0.002 [-0.047, +0.041] / +0.011* / -0.011* [-0.019, -0.003] |
| IPL 2026, seen fold (n 71) | G1 | 17.95 | 5.587 | 0.700 | 0.346 | 0.119 | |
| | G2 | 17.70 | 5.447 | 0.788 | 0.314 | 0.088 | -0.25 [-0.65, +0.15] / -0.142 [-0.290, 0.000] / +0.089* / -0.032* [-0.049, -0.015] |
| other leagues 2024-25 (n 1695) | G1 | 17.40 | 5.550 | 0.757 | 0.343 | 0.035 | |
| | G2 | 17.23 | 5.476 | 0.807 | 0.335 | 0.027 | **-0.16* [-0.22, -0.11] / -0.074* [-0.097, -0.052] / +0.050* / -0.008* [-0.009, -0.005]** |
Event biases G1 -> G2 (excess; `*` still significant), a few rows of `docs/img/ml_flaw_g1_vs_g2.png`: collapse 3 wkts/12 balls: IPL innings 1 +11.5* -> +11.5*, other leagues +9.4* -> +7.3*, IPL chase +8.6* -> +6.0 (n.s.), other leagues chase +6.6* -> +4.8*; chase rrr 13+: IPL +8.5* -> +6.3*, other +6.6* -> +4.8*; late 7+ wkts in hand chase: IPL -6.0* -> -4.8 (n.s.), other -4.7* -> -2.5 (n.s.); burst 28+/12 balls innings 1 other leagues -4.8* -> -4.0*. Significant rows: IPL chase 11/20 -> 6/20, IPL innings 1 11/18 -> 11/18, other leagues chase 18/22 -> 17/22, innings 1 18/20 -> 17/20. In the 50/50 blend with sim-B (checkpoints): other leagues MAE -0.10 [-0.13, -0.07], pinball -0.040 [-0.051, -0.030], chase LL -0.003 [-0.005, -0.002]; IPL 2022-25 flat (MAE +0.05 [-0.02, +0.12], LL -0.004 [-0.008, -0.000]); IPL 2026 LL -0.014 [-0.022, -0.006]; blend event excess (chase, other leagues) 3.5 -> 2.9 mean absolute.
**Features on top of G2** (control = G2; 7 variants): windows (6/12/18) dMAE IPL -0.01 [-0.12, +0.11], other -0.00; wickets x balls + pair (F2) IPL dMAE -0.09 [-0.22, +0.04], dpin -0.027 [-0.055, +0.001], other flat; F1 + F2 together IPL +0.01, other -0.00 (event mean |excess| other leagues 3.6 -> 3.2 runs); venue-recent (F3) IPL dpin -0.026 [-0.053, +0.001] but IPL 2026 dLL +0.019*, other dpin +0.012*; l12 instead of l30 no gain, IPL 2026 dLL +0.020*. None reaches the keep rule (nothing outside noise in the good direction in more than one scope, and no significant event bias removed).

**Keep / drop verdict.** Features F1-F4: **all dropped** (keep rule not met; most differences inside noise; some worsen chase calibration in some scope). Training change "early stopping on all competitions" (G2): **keep as a candidate**: it improves overall metrics outside noise (other leagues MAE, pinball, coverage; chase log loss in all three scopes), does not worsen IPL 2022-25 MAE or pinball (intervals contain 0), and shrinks the event biases by about a quarter, but it does not remove them. **Generality:** the improvement is strongest on other leagues (n = 1695 matches, 9 competitions) and on IPL 2026; in IPL 2022-25 the first-innings median is unchanged and only the chase probability and range coverage move. IPL range coverage goes to 0.827 (target 0.80), slightly wide. The event biases are the same in IPL and other leagues, so a fix would not have to be IPL-specific.
**Feature importance (gain share, mean of the 4 rolling folds).** G1 score q50: runs 12.7%, lvl_season 12.2%, bat_team_eff 9.5%, bowl_team_eff 6.9%, runs_l30 6.9%, wickets 6.2%, venue_eff 5.6%, lvl_ew 5.5%, wk_l30 5.3%, ns_balls_prior 4.2%, venue_n 4.0%, striker_balls_prior 3.9%, comp_code 3.8%, crr 3.5%, striker_rpb 2.5%. G1 chase: rrr 53.3%, rr_diff 17.0%, runs_needed 4.7%, target 3.5%, wickets 2.9%, bat_team_eff 2.6%, bowl_team_eff 2.0%, venue_eff 1.9%, comp_code 1.7%, wk_l30 1.5%, lvl_season 1.4%, venue_n 1.4%, lvl_ew 1.4%, runs 1.2%, striker_balls_prior 0.6%. G2 is the same to within 0.3 points (score q50: runs 12.5, lvl_season 12.2, bat_team_eff 9.3, ...; chase: rrr 53.0, rr_diff 17.1, ...). Note that the team-form columns are the 3rd and 4th most important for the score even though S3 found them useless as a block; the momentum window (runs_l30 / wk_l30) is 5th and 9th, so the model does use recent balls, just not in a way that fixes shocks.
**Recommended final column list (G2):** `balls_left, wickets, runs, crr, runs_l30, wk_l30, innings, target, runs_needed, rrr, rr_diff, comp_code, impact_era, lvl_ew, lvl_season, venue_eff, venue_n, bat_team_eff, bowl_team_eff, striker_rpb, ns_rpb, striker_balls_prior, ns_balls_prior, striker_faced, ns_faced` (= G1: the 26 FEATURES minus `season_year` = 25 columns; nothing added). Target stays level-relative (`lvl_season`). What changes is only the early-stopping set and the conformal deltas (both now from all competitions of season Y-1).
**Where things are.** Models: `data/external/ml/models/g2/g2_<year>_{score_q10,score_q50,score_q90,win}.txt` + `g2_<year>_conformal.json` (rounds, deltas, columns), years 2022-26. Out-of-sample caches (S = first-innings quantiles with conformal widening in q10/q90, W = chase p, V = inner-fold validation rows): `data/external/ml/g2_<name>_{S,W,V}.parquet`; `g2_g2_*` are the G2 ones, `g2_g1r_*` the G1 control, the others one per experiment (`f1a f1b f1c f2 f3 f4`, diagnostics `cap1 cap1f gval gvalf gval3 gvalf3 gval1218 gval2 gvalw`). Feature table `flaw_feat.parquet`, event table `flaw_events.parquet`, battery `flaw_battery*.csv`, comparisons `flaw_compare*.txt`. Re-run: `python -m cricket_analytics.ml.flaw_fit build | run g2 | compare ...`, `python -m cricket_analytics.ml.flaw_tests events | report`, `python -m cricket_analytics.ml.flaw_plot`. Tests: `tests/test_ml_flaw.py` (3: windows prior-only, pair / set-out detection, event masks + matched-baseline test); all 54 `tests/test_ml_*.py` pass. Production `predict.py`, dashboard, luck.py, error_report.py untouched; v1 still reproduces (features.py / direct.py / s4b.py only got additions; direct.py and s4b.py not edited).
**Caveats.** (1) G2 was chosen after the feature tests failed and after I had seen the IPL 2022-26 and other-league results, so its margins are somewhat optimistic; the only data that never entered any decision is the locked fresh set (men's non-IPL from 2026-01-01), which I did not touch. A fresh run for G2 needs a new pre-registration. (2) Events overlap (one match can be a collapse at several over ends) so the intervals are bootstrapped over matches but the many events are not independent tests; a few of the 80 rows per model will be flagged by chance (about 5% at the 90% interval). (3) Venue-recency events have only 37-123 matches. (4) The IPL 2026 G1 control here (`g1r`, trained without January-2026 league rows) differs from the saved holdout G1 by 2.0 runs on average per state (bias +1.3), which is a sense of the model-to-model noise. (5) F5 (sim-B momentum) not done.
**Suggestion for the lead (not done).** The shock bias survives every feature and more capacity, so the likely fixes are not features: (a) a small second-stage correction fitted on nested out-of-fold errors of the training seasons (residual vs wk_l12 / runs_l12 / wickets-in-hand), (b) a bigger sim-B weight after shock events (the blend already removes most IPL innings-1 event biases at the checkpoints), or (c) accepting it and widening the range after a shock. Each needs its own pre-registered test.


### 2026-11-13 (sim-R worker): sim-R "real batters and bowlers left" (`ml/simulate.py` plan option, `ml/simfix.py` PlanCtx / build_plan / simr)
**Question (lead's hypothesis).** Sim-B brings in an average batter by wicket number and an average bowler by over, so after a collapse it does not know the real, weaker lower order, nor who still has overs. Does simulating with the team's actual remaining XI and the bowlers' remaining overs shrink the under-reaction to collapses / steep chases / "many wickets in hand late"?

**Design (plain words).** Same saved sim-B ball models (so only the simulator differs; paired comparison). `simulate(..., plan=...)` is off by default (sim-B reproduces exactly; test `test_plan_none_is_the_old_simulator`).
- *Playing XI:* reconstructed from the deliveries (`resources.xi_from_deliveries`; no XI table). Known before the match, so legitimate.
- *Next batter:* XI members who are not yet at the crease and have not batted, ordered by their **prior typical batting position** (`resources.Strengths`, earlier matches only), each with his own prior strength in the ball model's own units (`bat_rpb`, `bat_out`, `bat_exp`; for a player who never faced a ball in this match, his latest strictly earlier match). The n-th wicket brings in the n-th name in the queue. The actual order of the match is never read (test `test_build_plan_reads_only_the_state_so_far`); the queue runs out into the generic by-wicket batter.
- *Future overs:* bowlers = XI members who bowled in this innings so far or bowl in at least 25% of their prior matches. Each has 4 minus overs already bowled. The over now starting keeps the state's bowler. The death overs (index 16-19) go first, to the cheapest eligible bowlers; the other overs are filled one by one by whoever has most overs left (cheapest first); nobody bowls twice in a row; nobody can exceed 4 overs (test `test_bowler_schedule_respects_four_overs_and_no_back_to_back`). An empty slot falls back to the generic bowler. The level term and everything else is unchanged.
- Checkpoints 0/6/10/15 overs, IPL 2022-25 rolling (400 paths) and IPL 2026 (seen fold, 1000 paths); caches `s2_preds_R_ipl.parquet` (and `s2_preds_R_bat_ipl` / `s2_preds_R_bowl_ipl`, 2024-25 only, diagnostic: only one half of sim-R). Non-IPL: not evaluated: the run (men's non-IPL 2024-25, roughly 5x the IPL states) had not finished after 60 min on a shared machine and was stopped, since the IPL result already fails the keep rule. `simfix.simr('nonipl')` is ready if anyone wants it. Runtime: about 11 min for the IPL run (plus 25 s to build the XI context), the machine was shared with other jobs.

**Overall, sim-R vs sim-B (IPL, same states and models).**
| fold | model | n (inn1 + chase) | MAE | bias at 0 overs | pinball | cov80 | chase log loss | ECE |
|---|---|---|---|---|---|---|---|---|
| 2022-25 rolling | sim-B | 1135 + 1111 | 18.43 | -3.3 | 5.80 | 0.777 | 0.477 | 0.056 |
| 2022-25 rolling | **sim-R** | same | 18.63 | -0.5 | 5.89 | 0.778 | **0.500** | 0.074 |
| 2026 (seen) | sim-B | 284 + 274 | 20.14 | +8.1 | 6.37 | 0.757 | 0.315 | 0.081 |
| 2026 (seen) | **sim-R** | same | 21.35 | **+15.8** | 6.80 | 0.746 | 0.323 | 0.083 |

Paired bootstrap, R minus B (5-95%): 2022-25 MAE +0.20 [-0.08, +0.53] (noise), pinball +0.088 [+0.007, +0.175] (worse), chase log loss +0.024 [+0.011, +0.036] (worse), Brier +0.009 [+0.004, +0.014] (worse); 2026 MAE +1.21 [+0.45, +1.93] (worse), pinball +0.43 [+0.21, +0.62] (worse), log loss +0.008 [-0.009, +0.027] (noise). The pooled 2022-25 "bias" looks better only because B was too low in 2022-23 and R pushes everything up; by year R's bias is 2024 +2.6 (B -2.2), 2025 +6.5 (B +1.9), 2026 +15.8 (B +8.1).

**Event biases (IPL 2022-26, over-end states at the checkpoints 6/10/15, excess over the matched non-event states, runs or win-probability points; 5-95% over matches in brackets for B).** First innings: median prediction minus actual. Chase: mean win probability minus actual win.
| event | n matches | sim-B excess | sim-R excess |
|---|---|---|---|
| inn1 collapse 2 wk / 12 balls | 83 | +2.4 [-1.2, +6.3] | +2.6 |
| inn1 collapse 3 wk / 12 balls | 13 | +0.7 | +0.1 |
| inn1 collapse 2 wk / 18 balls | 155 | +0.9 | +1.1 |
| inn1 collapse 3 wk / 18 balls | 39 | +3.2 [-2.5, +8.6] | +3.4 |
| inn1 collapse 2 wk / 24 balls | 228 | +1.4 | +1.8 |
| inn1 collapse 3 wk / 24 balls | 77 | +3.0 [-1.1, +7.1] | +3.9 |
| inn1 late, >=7 wkts in hand | 158 | -1.3 | -1.9 |
| inn1 death start, >=6 wkts in hand | 246 | -0.9 | -1.2 |
| chase rrr >= 13 | 122 | +4.4 pp | +4.4 pp |
| chase collapse 2 wk / 12 balls | 83 | +7.7 pp | +7.6 pp |
| chase collapse 3 wk / 24 balls | 88 | +6.4 pp | +5.5 pp |
| chase late, >=7 wkts in hand | 133 | -4.2 pp | -3.9 pp |
The excess biases do not shrink (first innings collapse excess is a little larger; chase unchanged within 1 pp). Plot: `docs/img/ml_simr_events.png`; full battery `data/external/ml/simr_battery.csv`.

**Where the extra runs come from (diagnostic, IPL 2024-25 only, n = 555 + 541 states).** Batters only: MAE 19.70, bias at 0 +4.6, chase log loss 0.454. Bowlers only: MAE 19.30, bias at 0 -0.8, log loss 0.439. sim-B: 19.20, -0.2, 0.436. Both: 19.55, +4.6, 0.470. So the real bowler plan is neutral and the real batter queue pushes totals up by about 5 runs. The queue strengths are higher than the generic batter's: the next batters average rpb 1.39 to 1.43 for the first five names (generic by wicket 1.31 to 1.34); the real batting order is looser than the prior typical position (finishers, impact subs, a different order on the day), and the best remaining batters are put in first. Wickets are unchanged (mean 6.47 vs 6.44 for B vs actual 6.42, first innings, IPL 2025 from ball 0), so a "weaker real tail" does not create more collapses. Sanity, IPL 2025 first innings from ball 0, runs per over: powerplay B 9.55 / R 9.67 / actual 9.75; middle B 9.12 / R 9.43 / actual 8.77; death B 10.99 / R 11.17 / actual 11.52; total B 194.2 / R 198.7 / actual 192.3.

**Verdict: DROP (not kept as the default).** Keep rule was "overall not worse and event biases shrink, or overall better outside noise". Overall it is worse (pinball, chase log loss, 2026 MAE significant) and the event biases do not shrink. The hypothesis, that the generic batter hides the real lower order, is not supported: the shock bias is not a matter of who bats next. Code stays (additive, default off).
**Not tried (would be the next step if someone wants to chase it, lead's call).** Centre the queue strengths on the generic by-wicket batter and keep only the relative differences; model the batting order as probabilities instead of a fixed order. Neither addresses the shock bias that the event tests show, so I did not chase them.

### 2026-11-13 (resources-left worker): resources-left features (G3) (`ml/resources.py`, `ml/flaw_fit.py` variants r1-r3 / w1-w3 / `_s2` `_s3` `_s1r`, `ml/flaw_plot.py g3`)
**Plain summary.** The idea was: after a collapse the model does not know the best batters are gone, so it is too hopeful. I gave it "who is still to bat" (from the playing XI, strengths from earlier matches only, batting order never used) and "what bowling is left". **It did not remove the collapse bias**: IPL first-innings guess after 3 wickets in 12 balls is still about +13 runs too high (G2 +11.5; G3 +12.9, inside noise), other leagues +6.7 (G2 +7.3). It gives a small gain on other leagues (MAE -0.13 runs, 0.8%, outside noise) and on the IPL chase log loss, but the IPL 2026 chase log loss is worse (+0.018). Momentum windows on top of it add nothing clear. Using prior-season WAR or recency-weighted rates as the strength source did not beat the plain shrunk rates. My verdict: **G3 = r3 is a weak, marginal candidate; do not adopt it on this evidence alone**; the collapse bias needs a different fix (see the earlier suggestions: second-stage correction, blend weights, wider range after shocks).

**Playing XI (no XI table exists in the DB).** Rebuilt as every player who appears for the side in either innings (batted, non-striker, bowled, or named as a fielder). 23,936 (match, side) pairs. Size: 11 for 69.9%, below 11 for 22.6% (10: 14.3%, 9: 5.1%, 8 or fewer 3.2%; mean 10.68), above 11 for 7.5%. By group: IPL men 61% = 11, 16% < 11, 23% > 11; other men 74% / 20% / 7%; women 61% / 37% / 2% (women's sides miss more players; women are in the table but the model test is men's). IPL impact era (2023+): 78% of sides have 12 or more (the impact sub and the player he replaced both appear), 13.5% exactly 11, 8.5% fewer. All who appear are counted. Missing players are those who neither batted, bowled nor fielded a catch or run-out (usually unused lower-order batters); missing slots are padded with a tail batter (exp 0.5, ratio 0.8, position 9), i.e. `bat_left_n` = 11 - batters used when the XI is incomplete, and no padding above 11. Small leak risk: the missing members depend on who batted, so a side that batted deep looks more complete; effect assumed small, not measured. A real pre-match XI would remove this and is what a live version would use.

**Features (all in `ml/resources.py`, pure functions the simulator can import; unit tests `tests/test_ml_resources.py`, 4 pass).** Strength of a player = from matches strictly before the match date, shrunk toward average: batting ratio = runs / runs an average team batter would score off the same balls (era-neutral; pseudo-obs 80 runs), balls per innings (prior 9, k=4), typical position (prior 7, k=3), `exp` = ratio x balls per innings; bowling economy ratio (k=150 runs), wicket ratio (k=3), death-over ratio (k=80), chance of bowling at all (prior 0.35, k=3). At each ball, batters left = XI minus everyone who has batted or is at the crease (so no later order). Columns: `bat_left_n`, `bat_left_str` (sum of exp of those left), `best_bat_left` (max exp), `bat_left_top` (how many have typical position <= 7), `bat_out_str` (summed exp of batters already out), `bowl_left_econ` / `bowl_left_wk` (the cheapest bowlers fill the overs left, each capped at 4 minus overs he bowled; a bowler who has not bowled yet has cap 4 x his chance of bowling; unfilled overs get a part-timer value), `death_top_left` (overs left of the 3 best death bowlers). Bowling features update only at over ends, batting ones only when a new batter walks in. Tests: features change only on a new batter / over boundary, identical when later deliveries are deleted, bowler overs never negative, same-day records never seen, recency weights. Output `data/external/ml/resources*.parquet` (2.64M state rows, about 1.5 min to build).

**Results, G3 (r3) vs G2 (rolling IPL 2022-25 n 284/283, IPL 2026 seen fold n 71/71, other leagues men's 2024-25 n 1695; paired bootstrap over matches 5-95%; `*` = interval excludes 0; negative = better).** Locked fresh data (men's non-IPL from 2026-01-01) was never touched.

| scope | variant | MAE | pinball | cov80 | chase LL | ECE | vs G2: dMAE / dpin / dLL |
|---|---|---|---|---|---|---|---|
| IPL 22-25 | G2 | 16.32 | 5.167 | 0.827 | 0.433 | 0.029 | |
| | R1 batting only | 16.24 | 5.150 | 0.819 | 0.420 | 0.031 | -0.09 [-0.27, +0.10] / -0.018 / **-0.014*** |
| | R2 bowling only | 16.36 | 5.166 | 0.831 | 0.435 | 0.026 | +0.04 / -0.001 / +0.001 |
| | **R3 both (G3)** | 16.25 | 5.147 | 0.821 | 0.422 | 0.028 | -0.07 [-0.27, +0.13] / -0.019 [-0.060, +0.022] / **-0.011* [-0.018, -0.005]** |
| IPL 2026 | G2 | 17.70 | 5.447 | 0.788 | 0.314 | 0.088 | |
| | R1 / R2 / R3 | 17.73 / 17.77 / 17.49 | 5.449 / 5.444 / 5.377 | 0.795 / 0.795 / 0.795 | 0.336 / 0.330 / 0.332 | 0.116 / 0.107 / 0.111 | R3: -0.20 [-0.68, +0.28] / -0.069 [-0.160, +0.027] / **+0.018* [0.000, +0.036]** (R1 +0.022*, R2 +0.017*) |
| other 24-25 | G2 | 17.23 | 5.476 | 0.807 | 0.335 | 0.027 | |
| | R1 / R2 | 17.17 / 17.21 | 5.449 / 5.458 | 0.804 / 0.807 | 0.326 / 0.336 | 0.023 / 0.026 | R1 -0.06 / **-0.026*** / **-0.009***; R2 -0.03 / **-0.017*** / 0.000 |
| | **R3 (G3)** | 17.10 | 5.430 | 0.805 | 0.328 | 0.025 | **-0.13* [-0.20, -0.06] / -0.046* [-0.063, -0.029] / -0.007* [-0.010, -0.005]** |
Batting-left carries nearly all of it; bowling-left alone does nothing. The gain is about 0.8% of MAE outside the IPL, and the IPL 2026 chase gets worse (a seen fold, n = 71 matches, so noisy, but all three variants agree).

**Event battery before / after (excess bias, runs for innings 1, pp for chase; full battery in `data/external/ml/flaw_battery_g1_g2_g3.csv`, plot `docs/img/ml_g3_events.png`).**

| event | IPL inn 1 G2 -> G3 | other inn 1 G2 -> G3 | IPL chase G2 -> G3 | other chase G2 -> G3 |
|---|---|---|---|---|
| collapse 3 wkts / 12 balls | +11.5 -> +12.9 | +7.3 -> +6.7 | +6.0 -> +6.7 | +4.8 -> +4.8 |
| collapse 2 wkts / 12 balls | +4.8 -> +5.2 | +3.4 -> +3.1 | +5.5 -> +5.9 | +3.1 -> +3.1 |
| chase rrr >= 13 | | | +6.3 -> +6.2 | +4.8 -> +4.5 |
| death start, 6+ wkts in hand | -3.7 -> -4.3 | -2.7 -> -2.2 | -5.4 -> -5.5 | -3.8 -> -3.3 |
| late, 7+ wkts in hand | -2.6 -> -2.8 | -2.1 -> -1.7 | -4.8 -> -5.1 | -2.5 -> -2.0 |
| burst 28+ runs / 12 balls | -0.9 -> -1.5 | -4.0 -> -3.8 | -1.8 -> -2.4 | -2.6 -> -2.4 |
| significant events | 11/18 -> 12/18 | 17/20 -> 17/20 | 6/20 -> 7/20 | 17/22 -> 17/22 |
| mean abs excess | 3.6 -> 4.2 | 3.6 -> 3.3 | 3.8 -> 4.1 | 3.3 -> 3.2 |
**Reading: no event bias shrinks outside noise; in the IPL they get slightly worse (not significantly), in other leagues about 5-10% smaller.** So "the model does not know who is left" is not what drives the shock bias (guess: after a collapse the remaining batters' differences are small next to the extra risk of further wickets, which the trees under-weight at these few events; not tested).

**Strength source (on top of R3; control = R3; paired over matches).** S1 = shrunk own prior rates (default). S2 = prior-season WAR runs added (`models/war.py` v3, 8 men's leagues pooled; a season-year record counts only for matches in a LATER calendar year, so even the early part of BBL 2025/26 cannot see 2025/26; slightly conservative; players without WAR use S1 values). S3 = same rates with recency weights (half-life 548 days). s1r = S1 turned into 1-100 ratings (percentile within competition and season-year, batting on the ratio, bowling on 1/economy) and the features rebuilt from the ratings.

| source | IPL 22-25 dMAE / dpin / dLL | IPL 2026 dMAE / dpin / dLL | other dMAE / dpin / dLL | events (sig / mean abs excess: IPL inn1; other chase) |
|---|---|---|---|---|
| S2 WAR | +0.08 [-0.06, +0.21] / +0.009 / +0.002 | +0.17 / +0.049 / -0.005 | +0.05 [0.00, +0.11] / +0.012 / -0.001 | 11/18 4.4; 16/22 3.0 |
| S3 recency | -0.03 [-0.14, +0.08] / -0.009 / +0.001 | +0.23 / +0.051* / +0.003 | -0.02 / -0.003 / -0.004* | 11/18 4.3; 15/22 3.0 |
| s1r ratings 1-100 | +0.12 [-0.01, +0.25] / +0.034* / -0.001 | +0.29* / +0.042 / -0.005 | +0.04 / +0.013 / +0.003* | 12/18 4.3; 15/22 3.1 |
**No source beats the plain shrunk rates (S1)**: WAR is slightly worse, recency is a wash (tiny chase gain on other leagues, worse on IPL 2026). The 1-100 rating keeps most of the information (rank correlation with the raw aggregates 0.92 for `bat_left_str`, 0.79 `best_bat_left`, 0.88 `bowl_left_econ`) but costs a little (IPL pinball +0.034*): fine for the dashboard, use raw values in the model. Ratings table (all XI players, per match, prior-only): `data/external/ml/player_ratings_s1.parquet` (`bat_rating`, `bowl_rating`, 1-100, 50 = typical).

**Momentum windows on top of R3 (lead's extra test; control R3).** W1 = + runs / wkts last 12 balls; W2 = + last 6 and last 12; W3 = + `lost_l12` (summed strength of the batters dismissed in the last 12 balls, exact, prior-only).

| variant | IPL 22-25 dMAE / dpin / dLL | IPL 2026 dMAE / dLL | other dMAE / dpin / dLL | events |
|---|---|---|---|---|
| W1 | +0.01 [-0.09, +0.10] / 0.000 / +0.002 | +0.09 / **-0.017*** | **-0.046* [-0.083, -0.006]** / -0.004 / -0.001 | IPL chase abs excess 4.1 -> 3.7; sig 12 -> 11 (IPL inn 1), 7 -> 6 (IPL chase), 17 -> 16 (other chase) |
| W2 | +0.01 / +0.001 / +0.001 | +0.01 / **-0.014*** | +0.02 / +0.007 / -0.001 | no change |
| W3 | -0.00 / -0.006 / +0.002 | +0.06 / +0.006 | +0.00 / +0.002 / **-0.003*** | IPL chase 7 -> 6 sig; others flat |
**Momentum is not larger once resources are known**: nothing outside noise except tiny pieces (W1 other-league MAE -0.05 = 0.3%, similar to its size on top of G2 earlier, and chase loss in IPL 2026). Agrees with the lead's own linear check (6/12/18/30 windows within 0.006 R2). The exact "strength of batters lost in the last 12 balls" (`lost_l12`) adds nothing.

**Feature importance (G3, gain share, mean of 4 folds).** Score q50: runs 11.0%, lvl_season 10.8%, bat_team_eff 8.2%, bowl_team_eff 6.2%, runs_l30 5.6%, **best_bat_left 5.5%**, venue_eff 5.3%, lvl_ew 5.3%, venue_n 3.9%, comp_code 3.9%, **bat_left_n 3.6%**, wk_l30 3.5%, ... **bat_left_str 2.7%**, **bat_out_str 1.7%**, **bowl_left_econ 1.7%**, death_top_left 1.2%, bowl_left_wk 1.0%, bat_left_top 0.6%. Chase: rrr 56.2%, rr_diff 12.6%, runs_needed 3.3%, ..., **bat_left_str 1.7%**, best_bat_left 1.4%, bat_out_str 1.1%, bat_left_n 0.8%, bowl_left_econ 0.2%. The model uses the batting columns (partly as a wickets/position proxy: `best_bat_left` and `bat_left_n` fall with every wicket) but they do not turn into better extremes.

**Keep / drop.** Keep rule: overall not worse AND significant event biases shrink, or overall improves outside noise; must hold outside the IPL. R3 (G3): other leagues improve outside noise (MAE, pinball, chase LL) and IPL 22-25 chase LL improves; IPL 22-25 MAE / pinball are inside noise (not worse); event biases do not shrink; IPL 2026 chase log loss is worse (+0.018). **Verdict: passes the letter of the rule only through the other-league gain of 0.8% MAE; I recommend DROP as a fix and keep G2 as the working candidate** (G3 models are saved so the lead can decide). W1-W3, S2, S3, ratings: **drop**. R2 alone: drop. Generality: the (small) gain holds on other leagues and the IPL chase; the failure to fix events is the same in both groups.

**Where things are.** Code: `ml/resources.py` (committed first for the simulator), `ml/flaw_fit.py` (variant names r1 r2 r3, w1_r3 w2_r3 w3_r3, r3_s2 r3_s3 r3_s1r, g3=r3; defaults unchanged, so v1 / G1 / G2 still reproduce; direct.py / s4b.py not edited), `ml/flaw_plot.py g3` (plot + importance). Models: `data/external/ml/models/g3/g3_<year>_{score_q10,score_q50,score_q90,win}.txt` + `_conformal.json`, years 2022-26; caches `data/external/ml/g3_{S,W,V}.parquet` (= `g2_g3_*`, identical to `g2_r3_*`), every variant `g2_<name>_{S,W,V}.parquet`; compare outputs `g3_compare1-4.txt`. Rebuild strengths: `python -m cricket_analytics.ml.resources build [s1|s2|s3|s1r]` (needs `.venv`, read-only DB). **Caveats.** (1) Resources are chosen on the same IPL 2022-26 / other-leagues 2024-25 data I evaluate on (G2 already was), and about 10 variants were tried, so any single "significant" gain is optimistic. (2) XI is inferred from the match itself (see above). (3) Events overlap; about 5% of rows flag by chance. (4) Women's strengths exist but were not tested.

### 2026-11-13: drawing board: shrinkage diagnosis + other model families (`ml/drawing_board.py`, `drawing_board_fit.py`, `drawing_board_report.py`)
**Plain summary.** The lead's idea was that G1/G2 react too little to shocks because of generic "shrinkage to the mean" (too much regularisation, early stopping on a small season, the level-relative target). The data say: **only a little of it is that, and not in the way guessed.** (1) A straight-line check of actual vs predicted shows the models are compressed by only 6-8% (first-innings slope 1.06; chase calibration slope 1.0-1.1), which explains perhaps 1-3 runs of an 8-12 run collapse miss. (2) More capacity, a lower learning rate, no regularisation, a raw (not level-relative) target: **none of them fixes the shock biases**, so it is not under-fitting or the early-stopping set. (3) A pure empirical table that looks up the exact collapse situation keeps about half of the collapse bias on the 2024-25 test seasons, so about half is **not available to any model** here (era drift or hidden pitch information; a stationary check says the test itself adds only about 1 run). (4) The other half is partly **the tree model's shape**: smooth models (spline GAM, small neural net) have almost no event bias, and a 50/50 average of G2 with the GAM is **better than G2 in the IPL and level elsewhere, with the event biases cut by 25-45%**. Best candidate: **b2 = average of G2 and the spline GAM (M2)**; chase probabilities are best from the 3-way average (G2 + GAM + MLP). Collapse bias is reduced, not removed (non-IPL 3 wkts in 12 balls: +7.3 -> +5.8 runs for b2, +4.0 for the 4-way mix b23f).

**Setup.** Scopes (men's only, out-of-sample, over-end states, identical states for every model): `ipl` = IPL 2022-25 (284 first innings, 283 chases), `non` = non-IPL men's 2024-25 (1695 matches). IPL 2026 (seen fold) is in D1 only. The locked fresh set (non-IPL >= 2026-01-01) was not touched. Differences = paired bootstrap over matches (1000 resamples, 5-95%), `*` = interval excludes 0. `g2oe` = the G2 recipe re-run through the new runner on over-end states; it reproduces the saved G2 predictions exactly (identical metrics), so it is the control. Training pool: all competitions of seasons < Y; early stopping / tuning on all competitions of season Y-1; never the test season.

**D1: regression-slope / calibration-slope test** (pooled 6/10/15-over checkpoints; 5-95% over matches; slope > 1 = predictions too close to the mean). Plots `docs/img/ml_db_calibration_slope.png`, `docs/img/ml_db_deciles.png`; tables `db_d1_slopes*.csv`, `db_d1_deciles*.csv`.

| model | 1st-inn slope IPL / IPL 2026 / non-IPL | chase calibration slope IPL / IPL 2026 / non-IPL |
|---|---|---|
| G1 | 1.07 / 0.92 / 1.08 | 1.03 / 1.88 / 1.22 |
| G2 | 1.06 / 0.93 / 1.06 | 1.02 / 1.82 / 1.10 |
| sim-B (checkpoints) | 1.03 / 0.97 / 1.05 | 0.85 / 1.75 / 0.91 |
| lookup table (baseline) | 1.12 / 0.98 / 1.21 | 0.73 / 1.35 / 0.84 |
| resource table (baseline) | 1.10 / 0.96 / 1.21 | 0.74 / 1.37 / 0.83 |

G2 first innings by checkpoint (IPL / non-IPL): 6 overs 1.08 / 1.11, 10 overs 1.10 / 1.07, 15 overs 1.03 / 1.02. Reading: the trees are mildly compressed (a 6% slope on a 25-run spread is 1-2 runs at a typical state), the old tables more (0.2, mostly the era jump), the chase models are roughly calibrated (non-IPL 1.10 = a bit timid; IPL 2026 1.8 rests on 71 matches, interval 1.4-3.1). By decile, **the lowest predicted totals are guessed about 6 runs too high in non-IPL (G2 +5.8, GAM +7.7, b2 +8.5)**, so "totals under 160 are over-predicted" is not fixed by anything here; the top decile is about right for G2 (-0.5). The slope test says "mild shrinkage", not "the" cause.

**D2: empirical-truth check** (men's matches, tables fit on seasons < Y only, over ends 3-17, excess bias of event vs matched non-event states; runs for innings 1, pp for chase; `*` significant). `emp-fine` = lookup by (balls, wickets, wickets in last 12 balls, last-12 pace band) with back-off (98% of states served by the full cell); `emp-coarse` = (balls, wickets) only; stationary floor = the fine lookup with random-match 5-fold CV over 2018-25 (no time shift).

| event | G1 | G2 | emp-coarse | emp-fine | stationary floor |
|---|---|---|---|---|---|
| collapse 3 wkts/12b, non-IPL innings 1 (n=300) | +9.4* | +7.3* | +5.5* | +4.8* | +1.1 (n.s.) |
| same, IPL innings 1 (n=35) | +11.5* | +11.5* | +9.5* | +11.0* | +4.5 (n.s.) |
| same, non-IPL chase (pp) | +6.6* | +4.8* | +2.9* | +2.7* | +2.0* |
| collapse 2 wkts/12b, non-IPL innings 1 | +4.5* | +3.4* | +2.8* | +1.9* | +0.7* |
| chase needing 13+/over, non-IPL (pp) | +6.6* | +4.8* | +2.5* | +3.0* | +0.1 |
| burst 28+ in 12 balls, non-IPL innings 1 | -4.8* | -4.0* | -10.8* | -7.9* | - |
| death start, 6+ wkts in hand, non-IPL innings 1 | -3.7* | -2.7* | -1.8* | -1.8* | -1.3* |

**Verdict D2.** The finer table is closer to the truth than G1/G2 on collapses but **not zero** on the 2024-25 seasons. For the non-IPL collapse: out of G1's +9.4, about 1 is test artefact, about 4 is shared with the table (era drift or hidden information), about 4.5 is G1-specific; for G2: 1 / 4 / 2.5. The table over-reacts to bursts (-8 vs G2 -4), and a table is a poor model (non-stationary cell means), so this check bounds the problem rather than solving it. The stationary rows show the event test itself is close to unbiased (<= +1.1 runs non-IPL); the IPL rows are 35 matches and noisy.

**D3 / D4: LightGBM recipe variants** (control `g2oe`; paired differences vs control; "events" = mean absolute excess over all ~20 events, non-IPL innings 1 / non-IPL chase, control 3.61 / 3.30; collapse = 3 wkts/12b non-IPL innings 1, control +7.3).

| id | change | IPL dMAE | non-IPL dMAE / dpin / dLL | events | collapse | verdict |
|---|---|---|---|---|---|---|
| D3 | only 14 state columns (no venue/team/player/era/striker columns) | +0.03 | +0.48* / +0.159* / +0.003 | 2.88 / 2.75 | +5.9 | **drop** (clearly worse overall; the extra columns carry signal, so "too many columns" is not the cause) |
| D4a | learning rate 0.02, up to 3000 rounds, patience 100, stop on all competitions of Y-1 | -0.07 | -0.04* / -0.017* / -0.000 | 3.36 / 3.14 | +6.6 | tiny gain, **no event fix** |
| D4b | min_data_in_leaf 20, lambda 0, 31 leaves | -0.01 | -0.02 / +0.001 / -0.001 | 3.69 / 3.41 | +7.4 | no change |
| D4c | target = raw remaining runs, level only as a feature | +0.19 | -0.02 / +0.004 / 0 | 3.31 / 3.30 | +7.2 | no change (IPL bias -4.6: trees cannot extrapolate the level) |
| D4d | L2 mean model, raw remaining runs; quantiles from residuals by bucket | +0.04 | -0.03 / +0.088* / 0 | 3.22 / 3.30 | +6.7 | no better |
| D4e | Poisson mean model, raw runs | -0.02 | -0.04 / +0.095* / 0 | **2.47** / 3.30 | **+4.8** | events better, pinball worse (residual-quantile ranges are looser) |
| D4f | L2 mean model, level-relative target | -0.12 | **-0.08\*** / +0.013 / 0 | **2.41** / 3.30 | **+5.1** | **keep as score option**: MAE better outside noise on non-IPL, pinball inside noise, innings-1 event bias down by about a third |

Chase probabilities for D4d-f are the control's (they change only the first-innings score). **Verdict D3/D4: the shrinkage-by-regularisation / early-stopping / level-target hypothesis is not supported** (D4a-c move events by less than 1 run). What helps a little is modelling the **mean** (D4e/D4f) instead of the median with quantile loss, with quantiles from residuals (guess: the median-regression trees are the weakest link).

**M1-M4: other model families** (identical states; keep rule = overall not worse and events shrink, and it must hold on non-IPL). Columns: IPL dMAE / dpinball / dLL; non-IPL dMAE / dpinball / dLL; collapse (3 wkts/12b, non-IPL innings 1 / chase); event mean |excess| (IPL inn1, non inn1, IPL chase, non chase).

| model | IPL | non-IPL | collapse non-IPL | events | verdict |
|---|---|---|---|---|---|
| g2oe (control; MAE 16.29 / 17.15, pinball 5.15 / 5.45, LL 0.431 / 0.331) | | | +7.3* / +4.8* | 4.14 / 3.61 / 3.63 / 3.30 | reference |
| M1 k-NN (k 50-400 by inner fold; 7 relative state features) | -0.08 / -0.036 / -0.011 | +1.11* / +0.380* / +0.013* | +8.3* / +0.6 | 2.18 / 3.89 / 2.04 / 1.69 | **drop** (innings 1 clearly worse non-IPL; chase LL worse) |
| M2 spline GAM (ridge on spline terms incl. balls-left x wickets tensor and momentum; logistic for the chase) | -0.27 / -0.062 / -0.013 | +0.69* / +0.248* / +0.002 | +4.3* / +0.8 | 1.97 / 1.87 / 1.88 / 1.05 | **chase: keep** (LL tie, ECE 0.013 vs 0.026, events cut about 70%); innings 1: IPL better, non-IPL worse alone, **keep in a blend** |
| M3 MLP (64-32, early stopping, L2 1e-3) | +0.01 / +0.006 / -0.013 | +0.84* / +0.288* / +0.004 | +2.4* / -0.4 | 1.77 / 1.16 / 1.66 / 1.06 | like M2; smallest event biases, worst non-IPL innings-1 MAE |
| M4 stretch of G2 (OLS on level-relative out-of-fold predictions of seasons Y-4..Y-1, slope b about 1.10; chase logistic slope 1.11-1.20) | -0.12 / +0.029 / +0.002 | +0.06 / +0.030* / -0.002* | +4.5* / +3.9* | 2.24 / 1.95 / 2.90 / 2.68 | **partial**: events -30%, overall tie, but ranges widen (cov80 0.85-0.88) and pinball is slightly worse |
| M4b = M4 + ridge on the out-of-fold residual (wickets, balls left, wk_l12, runs_l12) | +0.21 / +0.140* / +0.002 | +0.42* / +0.135* / -0.002* | -1.0 / +3.9* | 3.02 / 3.57 / 2.90 / 2.68 | **drop** (over-corrects: bursts and late states get +5 bias) |
| **b2** = mean of G2 and M2 | **-0.32\*** / **-0.097\*** / **-0.012\*** | +0.06 / +0.029 / **-0.003\*** | +5.8* / +2.8* | 2.35 / 2.70 / 2.36 / 2.00 | **keep: best candidate** (IPL better outside noise, non-IPL a tie, events -25 to -45%) |
| b3 = mean of G2 and M3 | -0.29* / -0.091* / -0.012* | +0.09 / +0.038* / -0.003 | +4.9* / +2.2* | 1.97 / 2.29 / 2.18 / 1.85 | similar to b2 |
| b23 = mean of G2, M2, M3 | -0.34* / -0.101* / -0.014* | +0.21* / +0.081* / -0.002 | +4.7* / +1.7 | 1.83 / 2.15 / 1.98 / 1.47 | best chase events; non-IPL innings 1 slightly worse |
| b23f = score from D4f + M2 + M3, chase from G2 + M2 + M3 | -0.31 / -0.087* / -0.014* | +0.20* / +0.075* / -0.002 | +4.0* / +1.7 | 1.60 / 1.78 / 1.98 / 1.47 | lowest innings-1 event bias; non-IPL pinball a hair worse |

Versus the **v1 blend** (G1 + sim-B at the 3 checkpoints): b2 IPL dMAE -0.13 [-0.34, +0.08], dpinball -0.049 [-0.106, +0.012], dLL -0.006 [-0.013, +0.000]; non-IPL dMAE -0.02 [-0.10, +0.06], dpinball -0.010 [-0.033, +0.014], dLL -0.002 [-0.005, +0.001]. So b2 matches the v1 blend overall without the simulator, works at every ball, and has smaller event biases (G2 alone vs the blend: pinball +0.054* in the IPL).

**Headline event excess (g2oe | M2 | M3 | b2 | b23).** Collapse 3 wkts/12b, non-IPL innings 1: +7.3* | +4.3* | +2.4* | +5.8* | +4.7*; same, non-IPL chase: +4.8* | +0.8 | -0.4 | +2.8* | +1.7. Chase needing 13+/over, non-IPL: +4.8* | +3.0* | +3.0* | +3.9* | +3.6*. Death start with 6+ wkts in hand, non-IPL chase: -3.8* | +0.3 | -0.3 | -1.7 | -1.3. Late with 7+ wkts in hand, non-IPL innings 1: -2.1* | -0.5 | -0.3 | -1.3* | -1.0*. Significant events (of about 20), g2oe -> M2 -> M3: IPL chase 7 -> 1 -> 1; non-IPL chase 16 -> 2 -> 2; IPL innings 1 11 -> 2 -> 3; non-IPL innings 1 17 -> 11 -> 5. Steep chases (13+/over) stay too hopeful for every model (+3 to +5 pp).

**Which hypothesis does the data support?** Neither pure one. (a) Generic shrinkage from regularisation, capacity, the early-stopping set or the level-relative target: **no** (D3, D4a-c). (b) The trees are **structurally** too stiff in how wickets, balls left and recent momentum interact (and the median objective adds to it): **yes**, smooth models are nearly unbiased after shocks even though they are worse in the average state, and averaging fixes part of the shock bias for free. (c) The information is partly hidden: **yes**, the model-free table keeps about +5 runs after a collapse in 2024-25, and the lowest decile of predicted totals is over-predicted by about 6 runs in every model including the GAM; neither is fixable from the ball state.
**Keep / drop.** KEEP as candidates: b2 (G2 + GAM average) for score and chase; b23 for chase probabilities; D4f as an optional score model. DROP: M1, M4b, D3, D4a-c (no event gain). M4 optional only. **All these choices were made after looking at the 2022-25 / 2024-25 test results (about 10 variants and 4 blends), so margins are optimistic; a fresh run needs a new pre-registration** (the locked set was not touched). IPL 2026 was not run for M1-M4 / D3-D4.
**Caveats.** (1) Over-end states only (6..114 for metrics, 18..102 for events); production models see every ball. (2) GAM / MLP / k-NN train on over-end rows only; the trees on every 4th ball. (3) Event tests overlap; about 5% of rows flag by chance. (4) M2-M3 quantiles use residuals by bucket from season Y-1 (not conformal widening); coverage is 0.80-0.82 on average but not guaranteed by state. (5) Intervals are over matches pooled over 4 seasons.
**Where things are.** Code: `ml/drawing_board.py` (D1 slopes, D2 lookups, paired tables; `python -m cricket_analytics.ml.drawing_board d1|d2`), `ml/drawing_board_fit.py` (all fits and blends: `python -m cricket_analytics.ml.drawing_board_fit g2oe d3 d4a ... m1 m2 m3 m4 b2 b23 b23f`, `... report m2 b2 ...`), `ml/drawing_board_report.py` (`python -m cricket_analytics.ml.drawing_board_report plots`). Caches `data/external/ml/db_<name>_{S,W}.parquet`; logs `db_d2.log`, `db_report1-3.log`. Tests `tests/test_ml_drawing_board.py` (4).

### 2026-11-13 (lead): PRE-REGISTRATION of fresh set #3, written before any new data is downloaded
- **Set:** all men's T20 matches dated **2026-10-15 or later** that arrive with the next `cricket update`. That covers franchise leagues, domestic T20 (e.g. SMAT), and T20Is where **both** teams are among the 12 full members (Afghanistan, Australia, Bangladesh, England, India, Ireland, New Zealand, Pakistan, South Africa, Sri Lanka, West Indies, Zimbabwe). Associate T20Is are excluded; reduced or no-result matches are excluded as before.
- **Locked:** no model development, tuning or inspection may use these matches. Workers may only build data for them.
- **Models**, all trained on matches dated before 2026-10-15 with their frozen recipes:
  - v1 ens-G1 (production)
  - G2
  - b2 = mean(G2, spline GAM)
  - b23 = mean(G2, GAM, MLP)
  - resource baseline
  - the best model from the model-family benchmark only if it is frozen before this run
- **Checkpoints:** 0/6/10/15 overs, both innings. Paired bootstrap over matches, 5–95%.
- **b2 replaces v1** only if all four hold:
  1. MAE or chase log loss beats v1 with the interval excluding 0.
  2. The other metric is not worse (interval includes or is below 0).
  3. ECE is under 0.08.
  4. cov80 is between 0.72 and 0.88.
- **Also reported:** the collapse event bias (3 wickets in 12 balls), and T20I (full members) vs leagues separately.
- **Small sample:** about 1 month of matches. If fewer than 80 decided chases, the result counts as **indicative only** and is confirmed on live BBL data.

#### Amendment 1 (before opening), 2026-11-13: test statistics fixed after the external review
Written while fresh set #3 holds 6 matches and has not been opened or scored (`data/external/ml/fresh3/` untouched; no row dated 2026-10-15 or later has been evaluated). It replaces the items named below; everything else above stays as registered. Reason: `docs/REVIEW_external_2026-11-13.md` HIGH 1, HIGH 3, MEDIUM 4, MEDIUM 6. Functions: `ml/evaluate.py` (`calibration_test`, `season_block_bootstrap`, `match_bootstrap`, `power_n`, `holm`).
- **Calibration rule replaced.** "ECE under 0.08" is dropped (a perfectly calibrated model fails it about 98% of the time at n = 70; on IPL 2026 the null mean was 0.107). New rule = `calibration_test(chase_won, p, groups=match_id)` on all four checkpoints (0/6/10/15 overs) pooled, with match-clustered standard errors. **Primary:** the 95% interval of the calibration intercept contains 0 and the 95% interval of the slope contains 1. **Secondary (reported, not gating):** ECE against its own null (outcomes drawn from the model's probabilities, 2000 draws, one shared draw per match), mean-of-4 form with `by=balls_bowled`, plus the pooled form; pass = ECE at or below the null 95th percentile. Both forms are always printed, so the old mean-of-4 vs pooled ambiguity is closed.
- **Minimum sample, from a power calculation** (80% power, two-sided 5%; per-match paired SDs from the cached dev folds, checkpoints 6/36/60/90 balls, mean over checkpoints): chase log-loss difference 0.01 needs about 550 (G1 vs G2, SD 0.084) to 780 (b2 vs G2 in the IPL, SD 0.100) decided chases; a 0.3-run MAE difference needs about 190 (G1 vs G2) to 650 (b2 vs G2, all leagues, SD 2.7) first innings. **The set is run only once it holds at least 800 decided chases (men's, non-reduced, `chase_won` known) and 650 first innings in scope (about 800 matches).** Below that, **no model scores may be computed on it, not even an "indicative" read**. Recommendation: skip the indicative read entirely. Under 800 matches the power is below about 50% for the effect we expect (b2 vs v1 was a tie on dev data), a look cannot change a decision, and it only spends the set. Allowed before the run: counting matches and data-quality checks that do not use model outputs. The old "80 decided chases counts as indicative" clause is void. It also replaces "confirmed on live BBL data" with: wait until the size is reached, then run once.
- **What counts as "better":** a log-loss or MAE gain counts only if **both** (a) the paired match bootstrap, now a **two-sided 95%** interval (2.5%-97.5%), excludes 0, **and** (b) the season-block bootstrap (blocks = competition x calendar month) excludes 0 or, when there are fewer than 6 blocks, the sign of the difference is the same in at least 75% of blocks that have 30 or more decided chases. The adoption conditions 1-4 above stay, with the 5-95% interval read as this 95% interval, and condition 3 read as the new calibration rule (primary).
- **"Zoo winner" removed.** The line "the best model from the model-family benchmark only if it is frozen before this run" no longer applies: the model zoo (`ml/model_zoo.py`) is exploratory only and nothing from it enters this run.
- **Production model: `<production model as of the run date, to be filled in by the lead before the run>`.** Production may change before the run (for example sim-B for the chase and a fair-table blend for the score). The run compares the candidates against whatever is production at that date, and the choice is written here, with its commit hash, before any data is opened. It is not named in this amendment.
- **Multiplicity:** about 110 variant families have been scored on the development bench (cache-file count in `data/external/ml/`, rough). Candidates in this run are the few registered above, so no extra correction is needed inside it; for development claims, report the count of variants tried and use Holm (`evaluate.holm`) or the stricter 95% interval, not "*" on a 5-95% interval.

### 2026-11-13: model zoo benchmark (`ml/model_zoo.py`, `ml/model_zoo_report.py`; exploratory only, nothing frozen)
**Plain summary.** Every model family on the same bench as the drawing board (identical over-end states: IPL 2022-25 = 284 first innings / 283 chases, non-IPL men's 2024-25 = 1695 matches; trained on earlier seasons, tuned on an inner fold = the last training season, never the test season; same G2 columns and level-relative target). **No new family beats G2 by a margin that matters, and none beats b2 / b23.** XGBoost, HistGradientBoosting and ExtraTrees tie G2 on average; RandomForest is worse; CatBoost is slightly better on non-IPL score (MAE -0.10*, pinball -0.043*) but not in the IPL. All tree families keep the shock bias (collapse +4.8 to +8.2 runs vs G2 +7.3). The GRU, like the GAM and MLP, has a small shock bias but is clearly worse on the non-IPL average. Per the lead, this is a family comparison only: **no winner is frozen for fresh set #3**.

**What was scored.** 6 new models (Z1-Z6) and 3 blends = 9 new rows; 11 inner-fold tuning arms in total (2 configs each for XGB / Cat / RF / ET / HGB, 1 GRU recipe; early stopping on season Y-1). Reference rows (G2, G1, M1-M3, b2, b23, resource) come from the drawing-board caches on the same states; sim-B and the v1 blend exist only at 6/10/15 overs, so they are in a separate checkpoint table. Picking CatBoost as the blend partner was done after seeing results, so blend margins are optimistic. Folds 2024-25 have far more test rows than 2022-23 (18,485 and 15,933 vs 1,397 and 1,347 first-innings rows) because they include every non-IPL competition by design; checked: identical row counts for g2oe, Z1 and Z6, so this is not a GRU bug.

**Recipes.** Z1 XGBoost 3.4.1 hist, `reg:quantileerror` alpha 0.1/0.5/0.9 in one model, eta 0.05, lambda 10, depth 4 or 6, early stopping 40; chase `binary:logistic`. Z2 CatBoost 1.2.10 `MultiQuantile:alpha=0.1,0.5,0.9`, depth 4 or 6, lr 0.08, l2 10, early stopping 50; chase Logloss. Z3/Z4 sklearn RandomForest / ExtraTrees, 120 trees, max_features 0.5, min_samples_leaf 100/400 (RF) or 50/200 (ET), RF row subsample 0.5; mean (L2) model of remaining/level with weights s^2, quantiles = residual quantiles by state bucket (8 buckets) on the inner validation; chase = classifier probability. Z5 HistGradientBoosting quantile loss per quantile (15 or 31 leaves), iterations picked by staged predictions on the inner validation (sklearn's internal early-stopping split is random and leaks across balls of a match); chase classifier. Quantile-objective models (Z1, Z2, Z5, Z6) get the same conformal widening as G2. Z6 GRU: 1 layer, 48 hidden, per-delivery inputs (runs, wicket, extra, legal, balls/120, wickets/10, runs/level) + static (level, target/level, competition one-hot), separate nets for first-innings quantiles (ordered outputs, pinball loss) and the chase (BCE), Adam 3e-3, batch 128 innings, patience 4 on the inner fold (stopped at 5-9 epochs), CPU 4 threads, trained on every even-ball state of seasons < Y; 11 minutes for all 4 folds.

**Main table** (identical over-end states; IPL columns = IPL 2022-25; acc = share of chases where p > 0.5 matches the result; collapse = 3 wkts in 12 balls, non-IPL first-innings excess bias in runs; events = mean |excess| over about 20 events, innings 1 in runs / chase in pp, average of IPL and non-IPL; train = seconds per fold including tuning and both models; pred = microseconds per state; the G2 time is one LightGBM fold re-timed; `-` = not logged).

| model | MAE@6 | @10 | @15 | pinball | cov80 | acc@10 | acc@15 | chase LL | ECE | non-IPL MAE | non-IPL LL | collapse | events inn1 / chase | train s | pred us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Resource table | 23.18 | 18.04 | 11.26 | 5.703 | 0.717 | 0.778 | 0.838 | 0.482 | 0.111 | 19.41 | 0.372 | +8.0 | 4.67 / 5.34 | - | - |
| G1 LightGBM | 20.20 | 16.16 | 10.04 | 5.157 | 0.819 | 0.796 | 0.861 | 0.442 | 0.028 | 17.31 | 0.339 | +9.4 | 4.48 / 4.62 | - | - |
| **G2 LightGBM (control)** | 20.47 | 16.14 | 10.04 | 5.151 | 0.833 | 0.799 | 0.853 | 0.431 | 0.031 | 17.15 | 0.331 | +7.3 | 3.88 / 3.47 | 16 | - |
| k-NN (M1) | 20.92 | 16.15 | 10.03 | 5.114 | 0.837 | 0.796 | 0.831 | 0.420 | 0.027 | 18.26 | 0.344 | +8.3 | 3.04 / 1.86 | - | - |
| Spline GAM (M2) | 20.80 | 15.66 | 9.92 | 5.088 | 0.825 | 0.792 | 0.831 | 0.418 | 0.017 | 17.83 | 0.333 | +4.3 | 1.92 / 1.47 | - | - |
| MLP (M3) | 20.97 | 15.85 | 9.87 | 5.156 | 0.819 | 0.799 | 0.827 | 0.418 | 0.012 | 17.98 | 0.335 | +2.4 | 1.47 / 1.36 | - | - |
| b2 = G2 + GAM | 20.41 | 15.75 | 9.84 | 5.053 | 0.839 | 0.796 | 0.846 | 0.419 | 0.018 | 17.20 | 0.328 | +5.8 | 2.52 / 2.18 | - | - |
| b23 = G2 + GAM + MLP | 20.46 | 15.71 | 9.74 | 5.049 | 0.835 | 0.796 | 0.835 | 0.417 | 0.017 | 17.35 | 0.329 | +4.7 | 1.99 / 1.72 | - | - |
| Z1 XGBoost | 21.17 | 16.50 | 10.17 | 5.163 | 0.845 | 0.781 | 0.853 | 0.422 | 0.030 | 17.11 | 0.327 | +6.6 | 3.84 / 3.40 | 43 | 3.3 |
| Z2 CatBoost | 20.87 | 16.45 | 10.08 | 5.156 | 0.816 | 0.774 | 0.853 | 0.432 | 0.033 | 17.05 | 0.335 | +4.8 | 2.84 / 3.84 | 87 | 0.8 |
| Z3 RandomForest | 20.49 | 16.36 | 10.66 | 5.232 | 0.867 | 0.789 | 0.857 | 0.438 | 0.028 | 17.25 | 0.332 | +8.2 | 3.44 / 4.83 | 61 | 4.2 |
| Z4 ExtraTrees | 20.50 | 16.27 | 10.25 | 5.165 | 0.870 | 0.785 | 0.861 | 0.430 | 0.040 | 17.12 | 0.332 | +5.5 | 2.52 / 3.59 | 48 | 5.5 |
| Z5 HistGradientBoosting | 20.51 | 16.32 | 10.05 | 5.168 | 0.829 | 0.789 | 0.850 | 0.433 | 0.026 | 17.12 | 0.331 | +6.7 | 3.65 / 3.52 | 126 | 2.4 |
| Z6 GRU | 21.12 | 16.18 | 10.03 | 5.100 | 0.809 | 0.781 | 0.850 | 0.430 | 0.034 | 17.86 | 0.367 | +3.8 | 2.04 / 2.41 | 162 | 9.1 |
| Z7a CatBoost + G2 | 20.63 | 16.30 | 10.02 | 5.135 | 0.825 | 0.778 | 0.853 | 0.428 | 0.028 | 17.05 | 0.331 | +6.0 | 3.34 / 3.65 | - | - |
| Z7b CatBoost + b2 | 20.62 | 16.08 | 9.93 | 5.087 | 0.833 | 0.785 | 0.850 | 0.422 | 0.022 | 17.03 | 0.329 | +5.3 | 2.65 / 2.97 | - | - |
| Z7c CatBoost + G2 + GAM | 20.54 | 15.97 | 9.89 | 5.072 | 0.835 | 0.789 | 0.850 | 0.420 | 0.023 | 17.06 | 0.329 | +5.5 | 2.59 / 2.69 | - | - |

Checkpoint-only (6/10/15 overs, adds the models that exist only there): G2 pinball 4.965 / chase LL 0.434 / ECE 0.048; b2 4.862 / 0.423 / 0.027; sim-B 4.947 / 0.440 / 0.031 (cov80 0.779); v1 ens-G1 4.913 / 0.429 / 0.023. Paired vs G2 at checkpoints: v1 blend IPL pinball -0.054*, non-IPL tie; sim-B IPL tie, non-IPL pinball +0.070*.

**Paired difference vs G2** (model minus G2, bootstrap over matches, 1000 resamples). Each cell: difference, 5-95% interval, and the two-sided 95% interval (2.5-97.5%); `*` = excludes 0 in that interval; n.s. = neither interval excludes 0 (see `zoo_paired2.csv` for all numbers).

| model | IPL dMAE | IPL dpinball | IPL dLL | non-IPL dMAE | non-IPL dpinball | non-IPL dLL |
|---|---|---|---|---|---|---|
| Z1 XGBoost | +0.16 n.s. | +0.011 n.s. | -0.009 [-0.014, -0.003]* / [-0.016, -0.002]* | -0.03 n.s. | -0.010 n.s. | -0.004 [-0.006, -0.002]* / [-0.006, -0.002]* |
| Z2 CatBoost | +0.07 n.s. | +0.005 n.s. | +0.002 n.s. | -0.10 [-0.17, -0.03]* / [-0.19, -0.02]* | -0.043 [-0.065, -0.022]* / [-0.069, -0.017]* | +0.004 [0.000, +0.007]* / [-0.000, +0.007] |
| Z3 RandomForest | +0.02 n.s. | +0.081 [+0.006, +0.151]* / [-0.013, +0.163] | +0.007 n.s. | +0.11 [+0.03, +0.19]* / [+0.01, +0.21]* | +0.076 [+0.051, +0.101]* / [+0.046, +0.105]* | +0.001 n.s. |
| Z4 ExtraTrees | -0.20 [-0.46, +0.07] / [-0.53, +0.13] n.s. | +0.014 n.s. | -0.001 n.s. | -0.02 n.s. | +0.034 [+0.006, +0.060]* / [+0.001, +0.067]* | +0.001 n.s. |
| Z5 HGB | +0.06 n.s. | +0.018 n.s. | +0.002 n.s. | -0.02 n.s. | -0.008 n.s. | 0.000 n.s. |
| Z6 GRU | -0.14 n.s. | -0.051 [-0.141, +0.036] / [-0.160, +0.055] n.s. | -0.002 n.s. | +0.71 [+0.50, +0.93]* / [+0.47, +0.97]* | +0.212 [+0.149, +0.274]* / [+0.139, +0.285]* | +0.036 [+0.027, +0.046]* / [+0.025, +0.047]* |
| b2 (drawing board, 5-95% only) | -0.32 [-0.52, -0.14]* | -0.097 [-0.149, -0.048]* | -0.012 [-0.020, -0.004]* | +0.06 n.s. | +0.029 n.s. | -0.003 [-0.006, -0.000]* |
| Z7b CatBoost + b2 | -0.16 [-0.34, +0.01] / [-0.38, +0.04] n.s. | -0.064 [-0.110, -0.021]* / [-0.118, -0.012]* | -0.009 [-0.016, -0.002]* / [-0.017, -0.001]* | -0.12 [-0.19, -0.05]* / [-0.20, -0.04]* | -0.042 [-0.057, -0.025]* / [-0.060, -0.021]* | -0.002 n.s. |
| Z7c CatBoost + G2 + GAM | -0.22 [-0.40, -0.05]* / [-0.44, -0.02]* | -0.078 [-0.125, -0.034]* / [-0.133, -0.027]* | -0.011 [-0.018, -0.004]* / [-0.019, -0.003]* | -0.08 [-0.16, -0.00]* / [-0.17, +0.02] | -0.025 [-0.045, -0.005]* / [-0.048, -0.002]* | -0.003 [-0.005, -0.000]* / [-0.006, +0.000] |

With 9 new rows x 6 comparisons (54 intervals) about 3 would exclude 0 by chance at 95%, so single starred cells are weak evidence.

**Verdict (plain language).**
1. **Best family.** On average-state accuracy the gradient-boosted trees (LightGBM, XGBoost, CatBoost, HistGradientBoosting) are indistinguishable; ExtraTrees is close; RandomForest is worse. XGBoost's chase log loss is a little better than G2 (-0.009 IPL, -0.004 non-IPL, both excluding 0 at 95%); CatBoost's non-IPL score is a little better. Changing tree library is worth about as much as these small gaps.
2. **Trees vs smooth models on shocks.** Every tree model keeps the collapse bias (+4.8 to +8.2 runs after 3 wickets in 12 balls). The smooth models (GAM +4.3, MLP +2.4, GRU +3.8) have much smaller event biases (innings-1 events 1.5-2.0 runs vs trees 2.5-3.9) but are worse on ordinary states, most visibly non-IPL (MAE +0.7 to +1.1). Reading, not proven: a tree answers with the average of a bucket of past states, so a rare combination (many wickets, few balls left, slow last 12 balls) is blurred into its neighbours; a smooth model bends continuously with wickets and balls left, so shocks move the forecast, but it cannot capture the sharp competition-specific differences that matter on average. Averaging the two (b2, b23) keeps most of both.
3. **GRU.** Reading the ball order did not help beyond the state features: it behaves like the MLP (about 17,700 innings of training data; stopped after 5-9 epochs).
4. **Nothing beats G2/b2 for free.** b2 / b23 keep the best IPL numbers and low event biases; CatBoost-based blends match them on non-IPL but not on shocks. **b2 (G2 + GAM) stays the best candidate**; extra families add at most about 0.05 pinball. Not frozen and not added to the fresh-set #3 list.
5. **Cost** per fold (score + chase, tuning included): XGBoost 43 s, ExtraTrees 48 s, RF 61 s, CatBoost 87 s, HGB 126 s, GRU 162 s, LightGBM about 16 s (4 threads). Prediction 1-9 microseconds per state for all.

**Caveats.** Over-end states only; the GRU trains on every even ball, trees on every 4th ball, GAM/MLP/k-NN on over ends; RF/ET use one-hot competition, HGB a numeric code, RF row subsample 0.5; RF/ET ranges are looser (cov80 0.87). The test seasons were seen in earlier experiments; the tuning grids used inner folds only, but the choice of CatBoost as the blend partner did not.
**Packages installed into `.venv`.** xgboost 3.4.1 (about 57 MB on disk), catboost 1.2.10 (about 330 MB on disk; pulls graphviz 0.21), torch 2.15.0+cpu (wheel 126.6 MB; pulls networkx 3.7, fsspec 2026.9.0). scikit-learn 1.9.1 and lightgbm 4.7.0 as before.
**Where things are.** Code `ml/model_zoo.py` (`python -m cricket_analytics.ml.model_zoo z1 z2 z3 z4 z5 z6 | blend z2 | report`), `ml/model_zoo_report.py`; caches `db_z*_{S,W}.parquet`, `zoo_table.csv`, `zoo_table_ckpt.csv`, `zoo_paired*.csv`, `zoo_battery.csv`, `zoo_times.json` in `data/external/ml/`; plot `docs/img/ml_zoo.png`; tests `tests/test_ml_zoo.py` (6).

### 2026-11-13 (fair-baseline worker): PRE-REGISTERED decision rule for simplifying production, written BEFORE any comparison was computed
Reason: `docs/REVIEW_external_2026-11-13.md` HIGH 2 and recommendations 1 and 5. Nothing below has been computed yet: no F-score or F-chase prediction exists, and the cached predictions of G1 / G2 / sim-B / v1 / b2 have not been re-tabulated for this purpose. `data/external/ml/fresh3/` is not opened, and no row dated 2026-10-15 or later is read.

**Fair baselines (definitions fixed here, in `ml/baselines.py`).**
- **F-score** = the existing `Resource` table (DLS-form expected remaining runs by balls left and wickets), fitted per fold on men's training seasons only, with its remaining runs (mean + the training residual quantiles by over) multiplied by `k = lvl_ew / mean(first-innings totals of the training innings in the pool)`. `lvl_ew` is the project's prior-only scoring level of the match, so no test-fold information is used. q10 and q90 are widened per over bucket by the split-conformal delta that G1 uses (`direct.conformal_delta`), fitted on the inner fold (season Y-1, table fitted on seasons < Y-1). Pool: IPL history for IPL tests, all men's history for non-IPL tests (same convention as `resource-ipl` / `resource-all`).
- **F-chase** = logistic regression (scikit-learn, L2 C=1, standardised inputs) on: log(runs needed / level-scaled expected runs left), that ratio, wickets in hand, balls left / 120, lvl_ew / 150, and two interactions (log ratio x balls left, log ratio x wickets in hand). Fitted per fold on the training second-innings states of the same pool.
- Neither uses a test-fold row; both are scored on exactly the rows of the other models.

**Bench and metric (fixed).** Dev folds = IPL 2022-25 (rolling) + men's non-IPL 2024-25 (rolling), pooled. States = the checkpoints 0 / 6 / 10 / 15 overs (balls 0 / 36 / 60 / 90), non-reduced, undecided, the same rows for every model compared (rows present in all candidate caches). Every figure below = the mean over the 4 checkpoints of that checkpoint's pooled value. Point estimates decide; intervals are reported (match bootstrap two-sided 95%, and a season-block bootstrap with blocks = competition x season, or per-block signs) but do not enter the rule. IPL 2026 and non-IPL 2026-01-01..2026-10-14 are reported only and play no part in the decision.

**Rule 1, chase production.** Candidates: v1 ens-G1 (current production) and sim-B. **Chase production = sim-B if sim-B's chase log loss on the dev folds is at most v1 ens-G1's + 0.005 (equal or better also qualifies). Otherwise v1 ens-G1 stays.**

**Rule 2, score production.** Candidates, in order of simplicity: (1) F-score, (2) mean(F-score, G1) (mean of quantiles, then sorted), (3) G1, (4) v1 ens-G1. "Best" = the candidate with the lowest dev MAE. **Score production = the simplest candidate whose dev MAE is within 0.2 runs of the best AND whose dev cov80 (share of finals inside q10-q90) is between 0.75 and 0.85.** If a simpler candidate fails the coverage condition, the next-simplest that meets both conditions is chosen. If none qualifies, v1 ens-G1 stays. G2, b2, the zoo models and sim-B are reported but are not candidates (they were chosen with these folds in view).

**What changes if the rule fires.** `ml/predict.py`: `predict_state` and `predict_match_curve` get a `model` argument, default the rule's outcome, `model="v1"` keeps the old path; same signatures and output keys otherwise. The dashboard model notes are updated to match.

### 2026-11-13 (fair-baseline worker): results of the fair-baseline comparison and the pre-registered production rule (`ml/baselines.py` F-score / F-chase, `ml/fair_report.py`)
**Plain summary.** A DLS-style table that is told the current scoring level (F-score) is a much harder baseline than the old one. On the IPL it **ties G1 and the blend on the first-innings score** (G1 minus F-score: -0.40 runs [-0.97, +0.22]; G1 is ahead in all 4 seasons, but not outside noise). On non-IPL leagues the ML is clearly better (-1.65 runs [-2.01, -1.31]; season-block interval [-2.40, -0.05]). For the chase, a 7-input logistic regression (F-chase) **ties or beats every ML model on the IPL** and loses to them by 0.02-0.03 log loss on non-IPL leagues. Applying the rule fixed in the entry above (commit `a2c05be`, written before anything was computed): **score = G1 alone, chase stays v1 ens-G1** (sim-B missed the +0.005 limit by 0.00004). The review's check was reproduced first: on the 33,873 IPL 2022-25 states, old table MAE 18.12, level-scaled F-score **16.40**, G1 16.30, G1 minus F-score -0.09 [-0.55, +0.37].

**Set-up (as registered).** Folds as before (IPL 2022-25; men's non-IPL 2024-25, trained on earlier seasons). Rows = checkpoints 0/6/10/15 overs, identical for the models compared; "mean 4" = mean of the 4 checkpoint values, pooled over both scopes ("dev" = 1,979 first innings / 1,964 decided chases at 0 overs). b2 only exists at 6/10/15 overs, so it is shown on "mean 3". F-score: `k = lvl_ew / mean training first-innings total` (IPL table for IPL, all-men's for non-IPL), conformal widening fitted on the inner fold. F-chase: logistic on log(needed / level-scaled expected left), that ratio, wickets in hand, balls left, level and two interactions, per fold. Intervals: match bootstrap two-sided 95%; "block" = season-block bootstrap over competition x season (24 blocks on dev; 4 for the IPL alone, where per-season signs are given instead). Caches `data/external/ml/fair_*.parquet`, `fair_tables.csv`, `fair_paired.csv`.

**Old baseline restated (IPL 2022-25, checkpoints):** resource table MAE 20.95, bias -11.99, cov80 0.716 -> F-score 18.77 (bias -5.09, cov80 0.832): the level correction is worth **2.18 runs [1.45, 2.85]**; G1 18.37, ens-G1 18.28, G2 18.43, sim-B 18.42, mean(F,G1) 18.33. Of the old "G1 beats the baseline by 2.6 runs", 2.2 was the level.

**First-innings score, mean of 4 checkpoints (MAE / pinball / cov80 / bias):**
| model | dev pooled | IPL 22-25 | non-IPL 24-25 | IPL 2026 (spent) | non-IPL 2026 (spent) |
|---|---|---|---|---|---|
| F-score | 20.88 / 6.66 / 0.820 / -1.3 | 18.77 / 5.92 / 0.832 / -5.1 | 21.23 / 6.79 / 0.818 / -0.7 | 20.15 / 6.28 / 0.757 / -2.2 | 19.46 / 6.11 / 0.871 / +1.6 |
| mean(F,G1) | 19.74 / 6.28 / 0.816 / -0.4 | 18.33 / 5.81 / 0.837 / -3.0 | 19.97 / 6.36 / 0.813 / +0.1 | 20.46 / 6.32 / 0.750 / -2.6 | 19.16 / 5.96 / 0.835 / +1.9 |
| G1 | 19.41 / 6.18 / 0.787 / +0.6 | 18.37 / 5.86 / 0.829 / -0.9 | 19.58 / 6.24 / 0.780 / +0.9 | 20.94 / 6.47 / 0.718 / -2.9 | 19.19 / 5.99 / 0.781 / +2.3 |
| G2 | 19.30 / 6.13 / 0.816 / +0.4 | 18.43 / 5.85 / 0.833 / -1.8 | 19.44 / 6.18 / 0.813 / +0.8 | 20.36 / 6.27 / 0.806 / +0.8 | - |
| sim-B | 19.76 / 6.30 / 0.743 / +0.8 | 18.42 / 5.80 / 0.777 / -1.5 | 19.98 / 6.39 / 0.737 / +1.2 | 20.14 / 6.37 / 0.757 / +6.5 | 19.49 / 6.06 / 0.754 / +1.9 |
| v1 ens-G1 | 19.36 / 6.16 / 0.767 / +0.7 | 18.28 / 5.77 / 0.810 / -1.2 | 19.54 / 6.22 / 0.760 / +1.0 | 20.23 / 6.27 / 0.764 / +1.8 | 19.23 / 5.98 / 0.771 / +2.1 |
| b2 (MAE, mean 3: 6/10/15 ov) | 16.10 (F 17.64, G1 16.28, ens 16.14) | 15.33 (F 15.98, G1 15.47) | 16.23 (F 17.92, G1 16.42) | - | - |

MAE by checkpoint 0 / 6 / 10 / 15 overs, dev pooled: F-score 30.6 / 22.9 / 18.2 / 11.9; G1 28.8 / 21.2 / 16.7 / 11.0; ens-G1 29.0 / 21.1 / 16.6 / 10.7; mean(F,G1) 29.2 / 21.5 / 17.0 / 11.2.

**Paired differences, score MAE (model minus F-score; negative = better than the fair baseline), 95%:**
| set | G1 | v1 ens-G1 | b2 (6/10/15) | G2 |
|---|---|---|---|---|
| dev pooled, match | -1.47 [-1.81, -1.14]* | -1.52 [-1.79, -1.25]* | -1.54 [-1.80, -1.28]* | -1.58 [-1.94, -1.24]* |
| dev pooled, season-block | -1.47 [-2.20, -0.13]* | -1.52 [-2.24, -0.27]* | -1.54 [-2.17, -0.46]* | -1.58 [-2.37, -0.17]* |
| IPL 22-25, match | -0.40 [-0.97, +0.22] (4/4 seasons better) | -0.49 [-0.97, +0.03] (4/4) | -0.65 [-1.18, -0.06]* (4/4) | -0.34 [-0.86, +0.21] (3/4) |
| non-IPL 24-25, match | -1.65 [-2.01, -1.31]* | -1.69 [-1.98, -1.41]* | -1.69 [-1.98, -1.42]* | -1.79 [-2.18, -1.43]* |
| IPL 2026 (spent) | +0.80 [-0.24, +1.78] | +0.08 [-0.89, +1.00] | - | +0.21 [-0.74, +1.15] |
| non-IPL 2026 (spent) | -0.27 [-0.73, +0.20] | -0.23 [-0.61, +0.15] | - | - |

Dev pooled: G1 minus ens-G1 MAE +0.05 [-0.07, +0.16] (tie; block [-0.14, +0.23]); mean(F,G1) minus ens-G1 +0.38 [+0.25, +0.50]*. On pinball (range quality) the ML models are ahead of F-score by 0.48-0.53 on dev (*, also by blocks) and tie it on the IPL alone (G1 -0.07 n.s., ens-G1 -0.16*).

**Chase win probability, mean of 4 checkpoints (log loss / Brier / accuracy):**
| model | dev pooled | IPL 22-25 | non-IPL 24-25 | IPL 2026 (spent) | non-IPL 2026 (spent) |
|---|---|---|---|---|---|
| F-chase | 0.416 / 0.136 / 0.804 | 0.462 / 0.150 / 0.779 | 0.408 / 0.134 / 0.808 | 0.365 / 0.115 / 0.848 | 0.436 / 0.144 / 0.776 |
| G1 | 0.404 / 0.130 / 0.815 | 0.485 / 0.157 / 0.787 | 0.390 / 0.126 / 0.820 | 0.389 / 0.125 / 0.812 | 0.440 / 0.146 / 0.780 |
| G2 | 0.398 / 0.130 / 0.814 | 0.477 / 0.156 / 0.783 | 0.384 / 0.125 / 0.819 | 0.357 / 0.114 / 0.837 | - |
| sim-B | 0.399 / 0.130 / 0.810 | 0.477 / 0.154 / 0.764 | 0.385 / 0.126 / 0.818 | 0.315 / 0.098 / 0.870 | 0.432 / 0.140 / 0.779 |
| v1 ens-G1 | 0.394 / 0.128 / 0.814 | 0.469 / 0.153 / 0.781 | 0.381 / 0.124 / 0.820 | 0.344 / 0.107 / 0.851 | 0.428 / 0.141 / 0.784 |
| b2 (log loss, mean 3) | 0.349 (F 0.373, ens 0.352) | 0.430 (F 0.427) | 0.335 (F 0.364) | - | - |

Log loss by checkpoint 0 / 6 / 10 / 15 overs, dev pooled: F-chase 0.545 / 0.445 / 0.384 / 0.291; G1 0.526 / 0.424 / 0.375 / 0.290; ens-G1 0.521 / 0.414 / 0.364 / 0.278; sim-B 0.534 / 0.425 / 0.364 / 0.273.

**Paired differences, chase log loss (model minus F-chase; negative = better than the fair baseline), 95%:**
| set | G1 | v1 ens-G1 | sim-B | b2 (6/10/15) |
|---|---|---|---|---|
| dev pooled, match | -0.012 [-0.021, -0.004]* | -0.022 [-0.029, -0.015]* | -0.017 [-0.025, -0.008]* | -0.024 [-0.031, -0.017]* |
| dev pooled, season-block | -0.012 [-0.024, +0.003] | -0.022 [-0.032, -0.006]* | -0.017 [-0.028, +0.003] | -0.024 [-0.031, -0.013]* |
| IPL 22-25, match | +0.023 [+0.001, +0.046]* (F-chase better) | +0.007 [-0.008, +0.022] | +0.015 [-0.009, +0.045] | +0.003 [-0.012, +0.018] |
| non-IPL 24-25, match | -0.019 [-0.028, -0.010]* | -0.027 [-0.035, -0.020]* | -0.023 [-0.031, -0.014]* | -0.029 [-0.037, -0.021]* |
| IPL 2026 (spent) | +0.024 [+0.003, +0.046]* | -0.021 [-0.044, +0.003] | -0.050 [-0.091, -0.008]* | - |
| non-IPL 2026 (spent) | +0.003 [-0.015, +0.022] | -0.008 [-0.023, +0.006] | -0.005 [-0.023, +0.017] | - |

**Rule 1 (chase).** v1 ens-G1 dev log loss **0.39416**, sim-B **0.39920**, difference **+0.00504 [-0.000, +0.010]** (block [-0.002, +0.013]) against the limit +0.005. **Not within the limit, by 0.00004: chase production stays v1 ens-G1.** This is a knife-edge, not a finding: the difference is zero within noise. For information only (spent sets play no part): sim-B minus ens-G1 is -0.029 [-0.052, -0.006]* on IPL 2026 and +0.004 [-0.010, +0.025] on non-IPL 2026; IPL 2022-25 +0.008 [-0.009, +0.030].

**Rule 2 (score).** Dev MAE: F-score 20.877, mean(F,G1) 19.736, G1 19.406, ens-G1 19.358 (best). Within 0.2 of the best: G1 (+0.048) and ens-G1 only. cov80: F-score 0.820, mean(F,G1) 0.816, **G1 0.787**, ens-G1 0.767 (both in 0.75-0.85). **Score production = G1 (simplest qualifying candidate).** F-score is rejected on accuracy (+1.5 runs), mean(F,G1) on accuracy (+0.38 against the best).

**What changed.** `ml/predict.py`: `PRODUCTION = {"score": "G1", "chase": "ens-G1"}`; `predict_state(..., model="auto")` and `predict_match_curve(..., model="auto")`: the first-innings score range (and `ens_q10/q50/q90` in the curve) is G1 alone; the win probability and everything else are unchanged; `model="v1"` restores the old blend for the score. The dashboard notes are updated. At 5 overs, 60/2 (IPL, Wankhede, MI v CSK) the median total moves from 203.6 to 198.2 and the range from 168.9-239.2 to 161.8-238.3. The simulator still runs (the chase probability needs it), so nothing gets faster.

**Reading.**
1. The "ML beats the baseline" story is real only outside the IPL (non-IPL score -1.7 runs, chase -0.02 to -0.03 log loss, both with the season-block interval excluding 0) and on score pinball (better ranges). In the IPL, with the level given to the baseline, the score is a tie and the chase is a tie (F-chase is nominally better than G1, G2 and sim-B on 2022-25 and ties the blend).
2. Why the IPL chase is hard to beat: 70 chases per season give a very noisy target and F-chase has only 7 coefficients. Reading, not tested.
3. On the spent IPL 2026 set sim-B stands out (log loss 0.315 vs F-chase 0.365, -0.050 [-0.091, -0.008]*), but it is a single season and was seen; the dev folds do not reproduce it (+0.015 vs F-chase). No decision rests on it.
4. Caveats. F-score / F-chase pools follow the old `resource-ipl` / `resource-all` convention (IPL table for IPL; all men's for non-IPL), men's only; a global-pool F-chase for the IPL was not tried (no tuning of the baseline). "Mean 4" weights each checkpoint equally, so ball 0 (MAE about 29) dominates MAE. About 110 variants have been scored on these folds; the two F-* baselines were pre-registered, but differences inside the ML family are still tie-sized.

### 2026-11-13 (lead): PRE-REGISTRATION of the model-vs-market benchmark (Betfair BBL in-play odds), written before any join or score
- **Data.** Betfair Australia data-science CSVs `BBL10..BBL15_Match_Odds.csv` (betfair-datascientists.github.io, free, no login, "use at your own risk"), 303 BBL matches, 2020-12-10 to 2026-01-25, kept local in gitignored `data/external/odds/betfair_ds/`. No row on or after 2026-10-15 is used.
- **Market probability.** For each runner and snapshot: mid = average of 1/best_back and 1/best_lay (1/best_back if lay is missing); then normalise the two runners to sum to 1 (removes the overround). Matches with a missing snapshot are dropped for that checkpoint only; counts reported.
- **Checkpoints (primary).** Chase at 6, 10 and 15 overs: Betfair `SECOND_INN_SIX/TEN/FIFTEEN_OV` against our states at 36 / 60 / 90 legal balls of innings 2. **Secondary (reported):** first ball vs the pre-match model; first innings 6/10/15 vs our first-innings win probability. Caveat to report: Betfair's snapshot moment may not be exactly the over-end ball.
- **Our model.** Out-of-sample only: for each BBL season, the model is fit on matches before that season's first match (rolling by season). Primary = production chase model (v1 ens-G1: G1 + sim-B average). Also reported: G1, sim-B, F-chase (fair logistic). Super-over and reduced (rain-shortened) matches are excluded by the usual rule; counts reported.
- **Metrics.** Log loss (primary), Brier, accuracy, `calibration_test` (intercept/slope, ECE vs null) for model and market. Paired difference model minus market per match, with **both** the match bootstrap (two-sided 95%) and the season-block bootstrap (6 seasons; if too few blocks, per-season sign).
- **Two pre-stated questions, nothing else counts as a finding.**
  1. Gap: how much worse (or better) is our model than the market, in log loss, per checkpoint? Expected: the market is better (it sees team news, pitch, dew).
  2. Complementarity: does a 50/50 average of the logits of model and market beat the market alone? "Yes" only if both bootstraps exclude 0. If yes, our model holds information the market misses.
- **No decision follows** (nothing is adopted); this is a yardstick. **No betting use.**
- **Goal tests, written and frozen before the code** (worker commits them alone, as `test-freeze:`): normalised market probabilities lie in (0,1) and sum to 1; every odds event maps to at most one Cricsheet match, with the same two teams, and at least 95% of events join (or the misses are listed); the Betfair winner agrees with the Cricsheet winner in at least 98% of joined decided matches; model predictions for a season use only matches dated before that season starts; no row dated 2026-10-15 or later.

### 2026-11-13 (worker): RESULT of the model-vs-market benchmark (Betfair BBL in-play odds), run exactly as pre-registered above
Code `ml/market.py`, goal tests `tests/test_market_goals.py` (frozen in commits 93d563b + 63183ab, before the code in 743856f). Run: `python -m cricket_analytics.ml.market preds | report`. Per-row table: `data/external/ml/market_rows.parquet` (gitignored). Yardstick only: nothing adopted, no betting use.

**Data checks (measured).** 303 odds events, 303 joined to a men's BBL Cricsheet match (100%; rule: same two teams, Cricsheet date within +-1 day of the Betfair UTC date; 301 same-day, 2 one day off; no unjoined events, no Cricsheet match used twice). Betfair winner = Cricsheet winner in 303/303 matches (100%). Chase states: 283 / 282 / 260 matches have an eligible model state at 6 / 10 / 15 overs (the other events: 19 reduced matches and 1 chase that ended before 36 balls); market snapshot missing for 0 / 2 / 6 of those, leaving n = 283 / 280 / 254.

**Out-of-sample protocol.** No cached prediction was reused: the old caches train on season_year < Y, differ in recipe, and drop BBL 2025/26 matches dated from 2026-01-01. Every model was refitted per BBL season (BBL10..BBL15 = season_year 2020..2025) on rows dated strictly before the season's first match (recorded per row as `train_cutoff`, always the day before; test `test_predictions_use_only_matches_before_season_start`). All four models exist for all six seasons, 3,300 model rows. G1 = s4b chase classifier (no season feature, global pool, config picked on the IPL of the same calendar year, early stopping on that IPL, final fit on all rows dated before the season start); sim-B = ball simulator, men's pool, early stop on that IPL, refit on all balls dated before the season start, 1000 paths; ens-G1 = mean of the two; F-chase = fair logistic with the all-men's resource table fitted on men's states dated before the season start. Deviations to note: (a) shrinkage strengths KV=100, KT=10 (the production constants, originally chosen on IPL 2022 data) are used for every season; (b) sim-B win probabilities of exactly 0 or 1 (63 rows, every one correct) are clipped to [0.0005, 0.9995] (half a path); ens-G1 uses the clipped value; (c) the Betfair snapshot moment may not be exactly the over-end ball (not checkable).

**Primary: chase, model minus market in log loss (positive = model worse). Intervals: match bootstrap | season-block bootstrap (6 blocks), two-sided 95%.**
| Over | n | ens-G1 LL | market LL | ens-G1 minus market | match boot | season-block | blend minus market | match boot | season-block |
|---|---|---|---|---|---|---|---|---|---|
| 6 | 283 | 0.4632 | 0.4581 | +0.0051 | [-0.021, +0.031] | [-0.012, +0.020] | -0.0038 | [-0.017, +0.009] | [-0.013, +0.004] |
| 10 | 280 | 0.4228 | 0.3959 | +0.0268 | [+0.005, +0.050] | [+0.010, +0.040] | +0.0071 | [-0.003, +0.018] | [+0.001, +0.013] |
| 15 | 254 | 0.3264 | 0.2905 | +0.0360 | [+0.008, +0.066] | [+0.013, +0.051] | +0.0087 | [-0.005, +0.024] | [-0.005, +0.018] |

Other models, same layout (diff, match boot | season-block), at 6 / 10 / 15 overs: G1 +0.015 [-0.012, +0.043] | [-0.005, +0.038]; +0.035 [+0.011, +0.060] | [+0.016, +0.051]; +0.046 [+0.015, +0.079] | [+0.028, +0.061]. sim-B +0.002 [-0.025, +0.028] | [-0.015, +0.020]; +0.024 [+0.000, +0.048] | [+0.006, +0.045]; +0.031 [+0.002, +0.061] | [+0.001, +0.051]. F-chase +0.009 [-0.017, +0.036] | [-0.012, +0.026]; +0.022 [-0.006, +0.050] | [-0.005, +0.047]; +0.034 [+0.003, +0.069] | [+0.019, +0.049].

| Over | Brier model / market | Accuracy model / market | Calibration, model (intercept, slope, ECE vs null p95) | Calibration, market |
|---|---|---|---|---|
| 6 | 0.1530 / 0.1499 | 76.7% / 78.1% | +0.24, 1.15, 0.054 (0.085) pass | +0.13, 1.09, 0.036 (0.082) pass |
| 10 | 0.1384 / 0.1300 | 80.4% / 82.1% | +0.22, 1.10, 0.038 (0.081) pass | +0.05, 1.14, 0.061 (0.078) pass |
| 15 | 0.1020 / 0.0917 | 86.2% / 87.4% | +0.19, 1.01, 0.044 (0.071) pass | +0.16, 1.02, 0.057 (0.068) pass |
("pass" = the intercept interval contains 0 and the slope interval contains 1, the `calibration_test` primary rule.)

**Question 1 (gap).** The market is better at every checkpoint, as expected. Our production chase model (ens-G1) is +0.005 log loss worse at 6 overs (not distinguishable from 0 on either interval), +0.027 at 10 overs and +0.036 at 15 overs (both intervals exclude 0). The gap widens as the match goes on. Per season, ens-G1 beat the market in 2 of 6 seasons at 6 overs and in 1 of 6 at 10 and 15 overs. Reading, not tested: the market sees team news, pitch and dew, and the model does not.
**Question 2 (complementarity).** "Yes" only if both bootstraps exclude 0 with the blend better. No checkpoint meets it: at 6 overs the blend is nominally better (-0.004) but both intervals include 0; at 10 and 15 overs it is nominally worse than the market alone (+0.007, +0.009; at 10 overs the season-block interval is [+0.001, +0.013] and the match interval includes 0). So we cannot say our model holds information the market misses. The numbers rest on 254-283 chases from one league over six seasons.

**Secondary (reported, not part of the two questions).** First ball vs the pre-match model (fitted per season on matches before its start; n = 303): market log loss 0.664; model without toss 0.678 (diff +0.0135 [-0.003, +0.030] | [-0.002, +0.030]), with toss known 0.683 (+0.0187 [+0.002, +0.036] | [+0.003, +0.032]). Both models are near a coin flip (0.693) and the market is a little better. First innings at 6 / 10 / 15 overs vs our first-innings win probability: **not done.** `predict.py` builds it from live production models plus a bespoke chase grid per state, there is no out-of-sample version, and building one was beyond the 20 minute limit.

**Caveats.** n of 254-283 chases gives intervals of about +-0.03 log loss. The Betfair back/lay pair is sometimes crossed in the files; the mid uses their mean either way. Missing 15-over snapshots (6) are mostly decided chases (reading, not checked). The tuned pre-match parameters were chosen on pre-2022 data, so BBL10-BBL11 are not strictly blind for that one secondary model. No decision follows.

### 2026-11-13 (lead): PRE-REGISTRATION of market-anchored model (test 1) and state-wise diagnosis (test 2), before any computation
Data and rows: exactly the benchmark rows in `data/external/ml/market_rows.parquet` (BBL10-15, chase at 6/10/15 overs, out-of-sample model columns). Betfair first-ball and snapshot probabilities de-vigged as in the benchmark pre-registration. No row on or after 2026-10-15.

**Test 1: market as the prior.**
- **A (primary, no fitting):** logit p_A = logit(market first-ball p for the chaser) + [logit(ens-G1 p now) - logit(pre-match model p for the chaser)]. The pre-match model is the same out-of-sample `prematch` prediction (toss unknown) used in the benchmark's secondary comparison. Meaning: start from the market's pre-match view (team news, pitch) and add only our model's in-play change.
- **B (secondary):** logistic regression of the chase result on [logit market first-ball p, logit ens-G1 p, logit prematch p], one fit per checkpoint, **expanding window by season** (trained on earlier BBL seasons only, so BBL10 has no B prediction; BBL11-15 are scored).
- **Compared with:** the live market at the same checkpoint (primary), and ens-G1 alone. Log loss primary, plus Brier, accuracy and `calibration_test`. Both bootstraps (match, two-sided 95%; season-block).
- **Finding rules:** "A beats ens-G1" or "A ties or beats the market" count only if both intervals agree. Same for B on the BBL11-15 rows.
- Expectation written beforehand: A closes part of the gap to the market but does not beat it.

**Test 2: where we lose to the market (descriptive).**
- Per checkpoint, rows are split by wickets down (0-1, 2-3, 4+) and by required rate at the checkpoint (< 8, 8-10, > 10 runs per over); 9 cells per checkpoint, 27 in all.
- Per cell: n, log loss of ens-G1 and of the market, the difference with a match-bootstrap 95% interval, and the Holm-adjusted p-value over the 27 cells.
- Only cells with Holm p < 0.05 are called a finding. The rest are reported as indicative. Cells with fewer than 20 matches are shown but not tested.
- **No decision follows from test 2.** It points at what information we lack.

**Goal tests, frozen before code (`test-freeze:`):**
- A and B probabilities lie strictly in (0,1).
- Every B prediction for season S was fit only on seasons before S.
- Test 2 cells partition the rows: counts sum to the checkpoint n, with no row in two cells.
- The row set equals the benchmark rows.
- No row dated 2026-10-15 or later.

### 2026-11-13 (worker): RESULT of test 1 (market-anchored model) and test 2 (state-wise diagnosis), run exactly as pre-registered above
Code `ml/market_anchor.py`, goal tests `tests/test_market_anchor_goals.py` (frozen in 8ac9d39 + f006b9b, before the code). Run: `python -m cricket_analytics.ml.market_anchor`. Per-row table `data/external/ml/market_anchor_rows.parquet` (gitignored). No new model fits except B; ens-G1, market and pre-match columns are the benchmark's (`market_rows.parquet`, `market_rows_firstball.parquet`, `market.py` unchanged). Implementation notes: the pre-match p (toss unknown) and the market first-ball p are taken from `market_rows_firstball.parquet` (team_a = alphabetically first team) and flipped to the chaser; checked that the pre-match y agrees with the chase result on every row. B = sklearn logistic regression, C = 1e6 (effectively unpenalised), one fit per checkpoint and season on earlier seasons only (BBL11 trains on about 50 rows per checkpoint). Required rate = runs_needed / overs left at the checkpoint. 817 rows = 283 / 280 / 254; B rows 228 / 226 / 203 (BBL11-15). Yardstick only, no betting use.

**Test 1. Model minus reference in log loss (positive = model worse); intervals = match bootstrap | season-block bootstrap (6 blocks; 5 for B), two-sided 95%.**
| Over | n | LL A | LL ens-G1 | LL market | A minus market | A minus ens-G1 |
|---|---|---|---|---|---|---|
| 6 | 283 | 0.4642 | 0.4632 | 0.4581 | +0.0061 [-0.021, +0.035] / [-0.014, +0.029] | +0.0010 [-0.012, +0.015] / [-0.009, +0.014] |
| 10 | 280 | 0.4264 | 0.4228 | 0.3959 | +0.0305 [+0.007, +0.054] / [+0.012, +0.055] | +0.0036 [-0.009, +0.016] / [-0.007, +0.018] |
| 15 | 254 | 0.3278 | 0.3264 | 0.2905 | +0.0373 [+0.006, +0.070] / [+0.011, +0.062] | +0.0014 [-0.011, +0.014] / [-0.010, +0.018] |

B on BBL11-15 only (n = 228 / 226 / 203):
| Over | LL B | LL ens-G1 | LL market | B minus market | B minus ens-G1 |
|---|---|---|---|---|---|
| 6 | 0.4806 | 0.4531 | 0.4459 | +0.0347 [-0.010, +0.082] / [-0.023, +0.086] | +0.0276 [+0.001, +0.059] / [-0.007, +0.067] |
| 10 | 0.4544 | 0.4088 | 0.3735 | +0.0809 [+0.038, +0.128] / [+0.020, +0.168] | +0.0456 [+0.009, +0.086] / [-0.013, +0.136] |
| 15 | 0.3823 | 0.3253 | 0.2942 | +0.0881 [+0.037, +0.139] / [+0.050, +0.129] | +0.0570 [+0.020, +0.097] / [+0.005, +0.120] |
(A on the same BBL11-15 rows, minus market: +0.007 / +0.039 / +0.034; ens-G1 minus market there: +0.007 / +0.035 / +0.031.)

| Over | Brier A / B / market | Accuracy A / B / market | Calibration A (intercept, slope, ECE vs null p95) | Calibration B |
|---|---|---|---|---|
| 6 | 0.1536 / 0.1583 / 0.1499 | 77.4% / 75.4% / 78.1% | +0.18, 1.08, 0.057 (0.083) pass | +0.25, 0.84, 0.076 (0.087) pass |
| 10 | 0.1403 / 0.1470 / 0.1300 | 80.4% / 79.2% / 82.1% | +0.15, 1.04, 0.034 (0.081) pass | +0.16, 0.82, 0.071 (0.083) pass |
| 15 | 0.1018 / 0.1171 / 0.0917 | 85.4% / 84.7% / 87.4% | +0.12, 0.99, 0.042 (0.072) pass | -0.01, 0.73, 0.058 (0.073) fail |
(Brier and accuracy for B are on its BBL11-15 rows, so not like for like with A on all six seasons; market Brier on those rows is 0.1446 / 0.1206 / 0.0928 and accuracy 78.5% / 85.0% / 87.2%.)

**Verdicts by the registered rules.**
- **A beats ens-G1:** no at any checkpoint (both intervals include 0 each time; differences +0.001 / +0.004 / +0.001, essentially identical to ens-G1).
- **A ties or beats the market:** at 6 overs both intervals include 0, so "tie" is allowed (nominally +0.006 worse, as is ens-G1 itself at +0.005, so this is no evidence of A closing anything). At 10 and 15 overs A is **worse than the market** on both intervals.
- **B beats ens-G1 / ties or beats the market (BBL11-15):** no. B is never better than ens-G1 and is worse than the market at 10 and 15 overs on both intervals; at 6 overs the market-gap intervals include 0 but B is nominally the worst of all. B vs ens-G1 is worse on both intervals at 15 overs and on the match interval only at 6 and 10 (the season-block interval includes 0).
- **Pre-written expectation** ("A closes part of the gap to the market but does not beat it"): the second half held; the first half did **not**. A is within 0.004 of ens-G1 everywhere, so the gap to the market is unchanged (+0.006 / +0.031 / +0.037 vs +0.005 / +0.027 / +0.036 for ens-G1). Reading, not tested: our pre-match p is near a coin flip, so subtracting its logit barely changes anything, and the in-play term dominates; B's three free weights fit on about 50-180 rows overfit (B calibration slope 0.73-0.84).

**Test 2. ens-G1 minus market log loss by cell (positive = model worse); match bootstrap 95% (4000 resamples), two-sided bootstrap p, Holm over all 27 cells (cells with n < 20 are shown, not tested, and count as p = 1).** Wickets down at the checkpoint x required rate (runs per over).
| Over | Wickets | RRR | n | LL model | LL market | Diff | 95% interval | Holm p | Finding |
|---|---|---|---|---|---|---|---|---|---|
| 6 | 0-1 | <8 | 57 | 0.2309 | 0.2265 | +0.0044 | [-0.066, +0.060] | 1.000 | no |
| 6 | 0-1 | 8-10 | 59 | 0.6670 | 0.6410 | +0.0259 | [-0.039, +0.096] | 1.000 | no |
| 6 | 0-1 | >10 | 18 | 0.5226 | 0.5233 | -0.0007 | not tested | | |
| 6 | 2-3 | <8 | 38 | 0.4691 | 0.4988 | -0.0297 | [-0.097, +0.028] | 1.000 | no |
| 6 | 2-3 | 8-10 | 58 | 0.6209 | 0.6218 | -0.0009 | [-0.062, +0.057] | 1.000 | no |
| 6 | 2-3 | >10 | 36 | 0.2491 | 0.2321 | +0.0170 | [-0.010, +0.048] | 1.000 | no |
| 6 | 4+ | <8 | 5 | 0.4283 | 0.4536 | -0.0253 | not tested | | |
| 6 | 4+ | 8-10 | 5 | 0.7606 | 0.7331 | +0.0275 | not tested | | |
| 6 | 4+ | >10 | 7 | 0.0608 | 0.0269 | +0.0339 | not tested | | |
| 10 | 0-1 | <8 | 29 | 0.1715 | 0.1193 | +0.0523 | [+0.010, +0.122] | 0.0067 | **yes** |
| 10 | 0-1 | 8-10 | 18 | 0.5512 | 0.4805 | +0.0707 | not tested | | |
| 10 | 0-1 | >10 | 9 | 0.7190 | 0.7518 | -0.0328 | not tested | | |
| 10 | 2-3 | <8 | 52 | 0.2467 | 0.2489 | -0.0022 | [-0.037, +0.031] | 1.000 | no |
| 10 | 2-3 | 8-10 | 60 | 0.6791 | 0.6062 | +0.0729 | [+0.020, +0.127] | 0.163 | no (indicative) |
| 10 | 2-3 | >10 | 48 | 0.4058 | 0.3917 | +0.0141 | [-0.048, +0.091] | 1.000 | no |
| 10 | 4+ | <8 | 12 | 0.7205 | 0.7974 | -0.0768 | not tested | | |
| 10 | 4+ | 8-10 | 18 | 0.4882 | 0.4471 | +0.0411 | not tested | | |
| 10 | 4+ | >10 | 34 | 0.1919 | 0.1841 | +0.0078 | [-0.016, +0.025] | 1.000 | no |
| 15 | 0-1 | <8 | 9 | 0.0383 | 0.0093 | +0.0290 | not tested | | |
| 15 | 0-1 | 8-10 | 2 | 0.2361 | 0.1218 | +0.1144 | not tested | | |
| 15 | 0-1 | >10 | 1 | 0.3370 | 0.2055 | +0.1315 | not tested | | |
| 15 | 2-3 | <8 | 40 | 0.1785 | 0.2171 | -0.0386 | [-0.117, +0.018] | 1.000 | no |
| 15 | 2-3 | 8-10 | 18 | 0.5444 | 0.5719 | -0.0275 | not tested | | |
| 15 | 2-3 | >10 | 18 | 0.5198 | 0.5239 | -0.0042 | not tested | | |
| 15 | 4+ | <8 | 41 | 0.3515 | 0.2571 | +0.0944 | [+0.003, +0.205] | 0.996 | no (indicative) |
| 15 | 4+ | 8-10 | 24 | 0.6168 | 0.5562 | +0.0606 | [-0.037, +0.149] | 1.000 | no |
| 15 | 4+ | >10 | 101 | 0.2599 | 0.2074 | +0.0525 | [+0.017, +0.092] | 0.039 | **yes** |

Cell counts sum to 283 / 280 / 254 (checked in the code). **Findings (Holm p < 0.05): two.** (1) 10 overs, 0-1 wickets down, required rate < 8 (n = 29): model worse by +0.052. (2) 15 overs, 4+ wickets down, required rate > 10 (n = 101): model worse by +0.053. Cell (2) is the one big cell and its Holm p (0.039) is close to the line; cell (1) rests on 29 matches. The cells where the model looks better than the market (negative diffs) are small and none is significant. These are descriptive; no decision follows and nothing is adopted. Reading, not tested: both are lopsided states (far ahead of the rate, or far behind it) where the market may price information we lack (team news, pitch, dew).

### 2026-11-13 (lead): PRE-REGISTRATION of test 3 (wicket overreaction) and test 4 (does player information explain the market gap?), before any computation
Data: Betfair BBL10-15 CSVs (snapshots at first ball and 4/6/10/15 overs of each innings), joined to Cricsheet as in `market.py`. Market p de-vigged as before. No row on or after 2026-10-15.

**Test 3: does the market overreact to wickets?** (Norton, Gray & Faff 2015 found this for ODI first innings.)
- Rows: for each innings and each consecutive snapshot pair (4->6, 6->10, 10->15 overs), the market probability for the **batting team** at the later snapshot, and W = wickets that fell between the two snapshots (from Cricsheet).
- Model: logistic regression of "batting team won" on logit(market p) as an offset, plus beta x W, with match-clustered errors and a match bootstrap.
- beta > 0 means that after wickets the market is too pessimistic about the batting team (overreaction). beta < 0 means underreaction.
- **Primary:** first innings, pooled over the 3 pairs. **Secondary:** second innings pooled, and each pair alone.
- A finding needs the 95% interval to exclude 0 on both the match bootstrap and the season-block bootstrap.
- Paper P&L, reported **only if the primary is a finding**: back the batting team at the later snapshot when W >= 2. Flat 100 stake, 5% commission on winnings, the lower of the two listed prices, with a bootstrap range. Research only, no betting use.

**Test 4: does the market use player information that our model misses?**
- Rows: the chase at 6/10/15 overs (benchmark rows).
- Residual r = logit(market p) - logit(ens-G1 p).
- Regress r on 4 player features, all prior-only shrunk career rates (as in `resources.py`) using the real XI from `xi.parquet`:
  1. strength of the two batters at the crease;
  2. strength of the chasing team's batters not yet in;
  3. bowling strength of the fielding team's remaining overs;
  4. a keeper/finisher flag is NOT used (no reliable source).
- Each feature is standardised. The four slopes are judged with the match bootstrap plus the season-block bootstrap, Holm over the 4.
- A slope that survives means the market prices player information our model under-uses. That is the new reason needed to retry player features (see `ML_LEARNINGS.md` §5). If none survive, the gap is not player information we can measure from free data.
- **No decision follows directly.** A follow-up would be pre-registered separately.

**Goal tests, frozen before code:**
- Market p for the batting team is in (0,1) and the two teams' values sum to 1.
- W equals the Cricsheet wickets between the two snapshot balls, and is 0 to 10.
- Player features use only matches dated before the match.
- The test 4 rows equal the benchmark rows.
- No row dated 2026-10-15 or later.
