# Do commentary features improve the worth score? (2026-11-13)

**Verdict: no. Nothing adopted.** Adding the death-over yorker share (and slower-ball / false-shot shares) to the bowler worth ridge does not beat plain `worth` by more than noise.

## Method (measured by us)
- `worth_plus` = the existing `worth` ridge for bowlers + `cm_death_yorker` (death yorkers / death balls with a known length). `worth_plus3` adds slower-ball share and false-shot share. Batting is identical to `worth`.
- Each feature is shrunk to the pooled rate with its own reliability k (method of moments on bowler totals, clamped 30-3000 balls), computed only from commentary years <= the cut year. Ridge weights are fitted on target seasons 2019..X only (same as `worth`). No later year can leak in (test: `test_bowl_plus_feats_no_future_leak`). Commentary exists for 2017+, so early fits have little of it.
- Code: `models/commentary_features.py` (`bowler_counts`, `bowl_plus_feats`), `models/backtest.py` (`worth_plus`, `worth_plus3`), `models/xii_basis.py` (`extra_bases`), `experiments/worth_plus_backtest.py`.

## Player level, pooled IPL 2024-26 targets (Spearman, 5-95% bootstrap in brackets)
| predictor | total (n) | bowl_rate (n) |
|---|---|---|
| worth | +0.205 [.12,.28] (372) | +0.309 [.21,.40] (201) |
| worth_plus | +0.218 [.13,.30] | +0.301 [.20,.39] |
| worth_plus3 | +0.212 [.13,.30] | +0.277 [.18,.37] |
| worth2 | +0.179 (391) | +0.286 (211) |
| ipl3 | +0.120 (371) | +0.138 (200) |
| recent_value | +0.116 (371) | not defined for rates |

Paired difference vs worth (same players, players resampled 1000x):
| | total | bowl_rate |
|---|---|---|
| worth_plus - worth | +0.013 (-0.044..+0.077) | -0.008 (-0.070..+0.054) |
| worth_plus3 - worth | +0.007 (-0.047..+0.067) | -0.032 (-0.097..+0.035) |

All ranges contain 0. On bowl_rate the point estimate is slightly negative.

## XII level (IPL 2024-26, 30 team-seasons, correlation of the XII's actual WAR with team wins; blend weight fixed at 0.5, not re-picked)
| basis | Spearman | Pearson |
|---|---|---|
| worth | 0.677 | 0.704 |
| worth_plus | 0.687 | 0.699 |
| worth_plus3 | 0.729 | 0.734 |
| worth2 | 0.726 | 0.754 |
| recent | 0.408 | 0.487 |
Differences of 0.01-0.05 on 30 team-seasons are well inside noise (not bootstrapped; n is tiny).

## Caveats
- Missing-not-at-random: contact and delivery mentions ("edge", "slower ball") exist only when the commentator chose to say it, so slower / false-shot shares are biased toward dramatic balls and toward commentators' habits. Length is close to random (59-69% coverage) so death yorker share is the cleanest of the three, and it is also the one that did nothing.
- Only 4-5 prior commentary seasons per bowler, death known-length balls are few per bowler-season (reliability k is large), so these features carry little signal by construction.
- The lead's earlier +0.16 / +0.18 (136 bowler pairs, next-season runs added / WPA) was the in-sample single-feature view; it does not survive as an addition to the worth ridge.
- Spinner "bouncer" parse bug is fixed (see WORK log); death yorker share is unaffected by it.
