# External review: cricket-analysis ML prediction (branch `dev`, HEAD 193e6df)

## Verdict
The basic hygiene is better than most hobby sports-ML work. Features use only earlier matches, and a test checks this. Splits roll forward by season. Locked sets are enforced in code, and failures and slips are written down. The statistics on top of that hygiene are weak, though, and the headline story is overstated:

- **The baseline is a strawman.** The DLS-style resource table is anchored to old scoring levels and never told that scoring has risen. When I scale its remaining runs by the same prior-only level the ML models get (one line, no tuning), it ties the production direct model G1 and beats the S3 LightGBM G0. Most of the "ML beats baseline" gain is level correction, not ML.
- **The test that "failed" v1 cannot be passed at that sample size.** A perfectly calibrated model scored on 70 IPL chases would fail the ECE < 0.08 rule 98% of the time. That rule (ECE, a measure of whether predicted probabilities match observed win rates) is carried forward into fresh set #3.
- **Too many variants on the same data.** Roughly 100 variants have been scored on the same IPL 2022–25 and non-IPL 2024–25 folds. Each is judged with 90% intervals over matches that ignore season-to-season variation.
- **The work has plateaued.** The whole ML effort ran in about 12 hours (commits 01:42–13:59 on 13 Nov). Production (v1, ens-G1) was fixed by 02:52. Every step after that tied or moved by about 0.1–0.3 runs or about 0.01 log loss. Meanwhile a model zoo (XGBoost, CatBoost, GRU…) is running on the same bench again.

The models themselves are reasonable and reasonably calibrated. The evidence that the extra complexity earns its keep is thin.

## Scores out of 10
| Area | Score | Reason |
|---|---|---|
| Validation rigour | 5 | Leakage control and locks are good. But the baseline is a strawman, the pass rules are statistically broken at the n used, the 90% match-level bootstrap ignores season clustering, and about 100 variants share one bench. |
| Honesty of reporting | 7 | Failures, slips and selection caveats are logged unusually well. Some narratives are overstated: the "chase surge is real" claim uses a cherry-picked window, "ML beats baseline" leans on a strawman, and "transfers to other leagues" rests on one test. |
| Real progress | 4 | Real gains came in the first ~3 hours: global pool, level-relative target, simulator, blend. Since then nothing has beaten v1 on any clean test. |
| Use of effort | 3 | The flaw hunt, sim-R, G3, drawing board and now the model zoo all chase a ±0.3-run margin and a collapse bias the project itself says is about half unfixable. Meanwhile the baseline, the test power and the external benchmark were never fixed. |
| Usefulness of current models | 6 | Score ranges have honest coverage (0.76–0.81). Chase probabilities are well calibrated on 312 unseen league chases. In practice the score side is about as good as a level-scaled DLS table. Pre-match is a coin flip (reported as such). |

## Problems found

**HIGH 1: the ECE pass rule cannot be passed at the n used.**
- Where: `ML_PREDICTION.md:483` (IPL 2026 rule), `:526` (the FAIL), `:1080` (the same rule for fresh set #3, which may have fewer than 80 chases). The code is `evaluate.py:114-117`: 10 equal-width bins, no small-sample correction.
- What I did: drew outcomes from ens-G1's own 2026 probabilities, which gives a perfectly calibrated model by construction.
- Result: its mean-of-4 ECE averages **0.107** (95th percentile 0.130) and is above 0.08 in **98%** of draws. ens-G1's actual 0.117 sits inside that null range.
- Effect: the "v1 FAILS on calibration" verdict is mostly a property of the metric at n = 70, not of the model.
- The only real signal is calibration-in-the-large. Mean predicted 0.565 against 0.642 observed is about 1.3 standard errors on 70 matches, so it is weak.
- The fresh non-IPL ECE of 0.046 is also simply at its own null (0.051). It is consistent with good calibration, but "passes 0.08" adds nothing.

**HIGH 2: the baseline is a strawman, so the headline gains are inflated.**
- Where: `ML_PREDICTION.md:179-180, 239`; resource baseline in `baselines.py`.
- The resource table is fit on IPL history and never level-adjusted, which is why it shows a −10 to −15 run bias. The ML models all get a prior-only scoring level.
- What I did: scaled the table's remaining runs by `lvl_ew / mean training first-innings total`. `lvl_ew` is the project's own prior-only level, so this is not leaky.
- Result: innings-weighted MAE goes from 18.12 to **16.40** on the identical 33,873 IPL 2022–25 states. Compare G0 at 16.70 and G1 at 16.30.
- Paired bootstrap over matches:
  - G1 minus the scaled baseline: −0.09 [−0.55, +0.37], a tie.
  - G0 minus the scaled baseline: **+0.29 [+0.04, +0.55]**, so G0 is worse.
- I checked only the median score side, not the chase side.

**HIGH 3: many comparisons on one bench, with a lenient threshold.**
- `data/external/ml/` holds caches for about 100 variants (`g2_*` ≈ 30, `db_*` ≈ 25, `direct_*` 12, `s4b_*`, `flaw_*`, `simfix`, zoo). All are scored on IPL 2022–25 and non-IPL 2024–25.
- The "*" significance flag is a 5–95% interval (`direct.py:303`, `drawing_board.py:127`). That is a 90% interval, so about 1 in 20 null variants shows a one-sided "win" by chance.
- The project acknowledges this in prose (`ML_LEARNINGS.md:58`, `ML_PREDICTION.md:1062`), yet keeps promoting "*" winners: G2, b2, D4f, the monotone chase model.
- The untracked `ml/model_zoo.py` adds about 6 more families plus blends to the same bench. The fresh-set-#3 pre-registration has a hook for its winner (`ML_PREDICTION.md:1075`: "the best model from the model-family benchmark only if it is frozen before this run").

**MEDIUM 4: the bootstrap ignores season-level variation.**
- Where: `direct.py:273-303` (and its copies). It resamples matches pooled over 4 test seasons.
- The dominant error source here is season-level drift: scoring level and chase rate. Season bias swings −3.4 to +1.6 runs (`ML_PREDICTION.md:414`).
- Evidence the intervals are too narrow: the S5 verdict "ens-G1 ≈ sim-B ≈ G1 on win, all intervals contain 0" (`:398`) flipped in 2026, where sim-B beat ens-G1 by 0.029 [+0.010, +0.049] and G1 by 0.074 (`:514-515`).
- With 4 seasons, any claim of "consistently better" needs per-season consistency or a season-block bootstrap.

**MEDIUM 5: the "chasing surge is probably real" claim uses a cherry-picked window.**
- Where: `ML_PREDICTION.md:572` ("64% … against 45–51% in 2022–25 … probably real"), and `ML_LEARNINGS.md:46`.
- My calculation from `states_innings.parquet`: the IPL chase win rate was **0.625 in 2019 and 0.627 in 2021**, then 0.50 / 0.45 / 0.51 / 0.51 for 2022–25, and 0.64 in 2026.
- 64% is within the historical season-to-season swing, which is about what binomial noise gives at n = 70 (SD about 0.06).
- The story "the IPL 2026 failure was specific to that season's surge, the model transfers" (`:707`) is an after-the-fact explanation of a failure that problem 1 shows was mostly metric noise anyway.

**MEDIUM 6: fresh set #3 is underpowered by design.**
- b2 already only ties v1 on the development data: IPL dMAE −0.13 [−0.34, +0.08], dLL −0.006 [−0.013, 0.000] (`ML_PREDICTION.md:1057`).
- The adoption rule needs b2 to beat v1 with the interval excluding 0, plus ECE < 0.08, on a set that "counts" from 80 chases (`:1078-1083`).
- My estimate: power is under 10% for the expected effect. ECE < 0.08 fails about 98% of the time for any model at n ≈ 70–80 per checkpoint.
- Result: the test is close to predetermined to "not adopt", while using up a clean set.
- The pre-registration also still does not say whether ECE means mean-of-4 or pooled. The same ambiguity was noted after the IPL 2026 run (`:88`).

**MEDIUM 7: tempo and process.**
- Both clean test sets were used within about 7 hours of the first feature code: commit `features.py` at 01:42, IPL 2026 opened at 02:55–03:02, non-IPL fresh set at 08:59.
- The IPL 2026 pre-registration (02:53) was committed 2 minutes before the holdout driver.
- The pre-registration is genuine, but development was too short for the dev-fold verdicts to have stabilised. That explains why the holdout then contradicted the S5 ranking.

**LOW 8: evaluation excludes outcome-defined matches.**
- `dataset.py:79-84` defines `reduced` using the match outcome (DLS, no result, cut short) and drops ties. All metrics exclude these matches, but production cannot know a match will be rain-hit.
- The effect is small and optimistic. It should be stated as a scope limit.

**LOW 9: the GRU decision contradicts itself, and one zoo log looks odd.**
- The GRU was skipped "because there is no room left" (`ML_PREDICTION.md:485`), but `model_zoo.py` now runs one (z6).
- `zoo_z6.log`: fold 2024 has **18,485** test score rows against 1,397 / 1,347 for 2022 / 2023. That is a different test set for one fold (probably non-IPL rows included). I did not chase it, but it would make any GRU comparison invalid if it reaches the report.

**LOW 10: leakage tests do not cover the simulator.**
- Prior-only tests exist for `features.py`, resources, prematch and the v2 chase features. There is none for `ball_model.py`, which feeds sim-B, the best chase model.
- I read the code: `prior_sums` and `ew_level` use strictly earlier dates, so I found no leak.
- Fixed constants (`HL_LEVEL`, `K_PLAYER`, `K_BAT_*`, `HL_SLOW/FAST`) have no recorded tuning set. If they were chosen by looking at 2022–25 results, that is mild contamination.

**INFO: disclosed slips that I checked.**
- The January-2026 league rows in the v1 holdout G1 training pool are earlier in time than IPL 2026, so this is not leakage.
- The `tune_k_chase` lock slip is disclosed and plausibly harmless.

## Claims checked
| Claim | What I found |
|---|---|
| IPL 2026: ens-G1 ECE 0.117 → FAIL; log loss 0.344; sim-B ECE 0.081 (`ML_PREDICTION.md:501-526`) | **Reproduced** with `holdout.models()`: mean-of-4 ECE 0.117, pooled 0.091; sim-B 0.081 / 0.055; 70 chases, 274 states. **But** a perfectly calibrated model at this n has ECE about 0.107 (95th percentile 0.130) and fails the 0.08 rule 98% of the time. The FAIL is not evidence of miscalibration. |
| Fresh non-IPL: v1 ECE 0.046, v2 ties v1 on log loss (`:705-706`) | **Reproduced**: v1-ens mean-of-4 0.046, pooled 0.033, 312 matches. v2-ens log loss 0.430 against v1 0.432 (pooled), a tie. Null ECE at this n is 0.051, so this is consistent with good calibration. I confirmed `v2_fresh_*` has **no rows on or after 2026-10-15** (dates 2026-01-01 → 2026-09-20). I did not open `fresh3/`. |
| b2 = mean(G2, GAM): IPL dMAE −0.32*, dLL −0.012* (`:1052`) | **Reproduced** from `db_report_paired.csv`: −0.324 [−0.520, −0.139], dLL −0.0117 [−0.0198, −0.0042]. Non-IPL MAE +0.06 [−0.05, +0.17]. Real but small, it is one of about 100 variants, and against v1 it is a tie. |
| "ML beats the best baseline by about 1.4 runs" (`:239`) | True against the unadjusted table (18.12 → 16.70). **Against a level-scaled table (16.40) G0 is worse and G1 ties.** The gain is mostly the level input, not ML. |
| "Chasers won 64% in 2026 against 45–51% in 2022–25; probably real" (`:572`) | The numbers are right (2022–25: 0.50 / 0.45 / 0.51 / 0.51; 2026: 0.643). **Omitted:** 2019 0.625 and 2021 0.627. This is within normal season swing. |
| Features are prior-only and tested (`features.py` docstring) | **Agree.** The code updates after each day and the test `test_no_leakage_later_matches_do_not_change_earlier_rows` exists. The same holds by reading for `ball_model.py`, which has no test. |
| Pre-match model FAIL reported honestly | **Confirmed** in `prematch_report_fresh.md`: log loss −0.0094 [−0.0244, +0.0047] against a coin flip, 330 matches. |

## Recommendations (ranked)
1. **Rebuild the baselines fairly and restate every headline.**
   - Score side: use the level-scaled resource table (above).
   - Chase side: use a logistic regression on (runs_needed / expected-runs-left, wickets, balls_left, level).
   - Expected value: high, size S. It tells Samar whether the LightGBM/simulator stack is worth its complexity. My check says that on the score side it barely is.
2. **Fix the test statistics before fresh set #3 runs.**
   - Replace ECE < 0.08 with calibration intercept and slope (with intervals), or with ECE compared to its own null from outcomes drawn from the model's probabilities, as I did here.
   - State mean-of-4 versus pooled.
   - Do a power calculation and set the minimum n from it. Expect about 300+ chases for a 0.01 log-loss effect, not 80.
   - Add a season-block bootstrap or per-season sign consistency to development claims.
   - Expected value: high, size S. Otherwise the next clean set is spent on a predetermined "not adopted".
3. **Freeze the development bench and stop variant churn.**
   - Treat the model zoo as exploratory only, and remove the "zoo winner" hook from the fresh-set-#3 pre-registration.
   - Record a running count of variants tried, and use a stricter threshold (95% two-sided, or Holm correction) for "*".
   - Expected value: high in saved effort and in credibility. The last ~10 hours produced no adopted change.
4. **Get a real external benchmark.**
   - In-play win probability should be compared with exchange or bookmaker odds (historical Betfair data, paid), or at least with a published WASP-style model.
   - Expected value: medium-high, size M. It is the only baseline a sceptical sports-analytics reader accepts, and it would show whether the 0.43 log loss on leagues is any good.
5. **Simplify production to match the evidence, then spend effort on information, not model shape.**
   - Use sim-B for chase probability: it won 2026 clearly and tied everywhere else. Use the G1 + sim-B (or scaled-baseline) blend for score.
   - Next gains are more likely from inputs the models lack (confirmed XI is already parsed, toss, day/night/dew, pitch) and from modelling the season-level chase or scoring shift as a Bayesian effect updated within the season, judged per season.
   - Expected value: medium. The collapse-bias hunt is at diminishing returns, and the project's own D2 says about half of it is not in the data.

*Method: read-only. I did a light code read of `dataset.py`, `features.py`, `direct.py`, `evaluate.py`, `ball_model.py` and `holdout.py`, and read `ML_PREDICTION.md` (main sections), `ML_LEARNINGS.md` and `WORK_ml.md`. Checks were 3 cheap Python scripts over cached prediction parquet files, with no refits. Scripts are in the scratchpad (`chk1.py`–`chk3.py`). I did not open `fresh3/` and did not score any row dated 2026-10-15 or later.*
