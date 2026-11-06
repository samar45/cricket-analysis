# M2: component projection, controllable value, stability (2026-11-06/07)

All numbers **measured by us** from our Cricsheet DuckDB (read-only). Code: `models/components.py` (run `python -m cricket_analytics.models.components stability|validate|beta|build`), tests `tests/test_components.py`. Saved: `models/data/stability_ipl2023.csv`, `stability_men_t20.csv`, `components_params.json`, new columns in `pwar_ipl_2027.csv`.

## Decision (read first)
1. **Component projection does NOT beat the current pWAR beyond noise, so pWAR stays the default.** Batters r 0.08 vs 0.06 (difference 95% range -0.16 to +0.18); bowlers r 0.34-0.37 vs 0.32 (best case +0.05, range -0.00 to +0.10). Same 307 player-seasons, 2024-26.
2. **The parts themselves do repeat** (dot, four, six, extras: next-season r 0.3-0.6, beating last season's raw value). What does not repeat is the total, because wickets and "context" (part R) are luck-heavy and large.
3. **Controllable WAR** is added as a second number (`controllable_war`, `_bat`, `_bowl` in `pwar_ipl_2027.csv`). It predicts next-season actual WAR about as well as the components (bowlers r 0.37 vs 0.32, range -0.01 to +0.11), not better beyond noise. Treat it as a "skill-only view", not a more accurate forecast.
4. **Team slope beta:** refitting with shrunk values raises beta (0.094 to 0.317 with pWAR) but only because the values are smaller; per SD of the XI difference it is unchanged (0.13 to 0.11), and leave-one-season-out log-loss stays at coin-flip (0.692). Nothing to change in the trade tool.

## 1. Stability table (split-half reliability, Spearman-Brown)
Method: players with at least n balls; their first n balls (rounded up to whole matches) split into alternate matches; correlation of the two halves' rates across players, stepped up (R = 2r/(1+r)); k fitted in R = n/(n+k). **n50** = balls at which R = 0.5 (= the shrinkage constant k: a player with n balls keeps n/(n+k) of his own rate). **n70** = 7/3 x n50. Range = 90% bootstrap over players. Rates are raw (include role/phase), batters per ball faced, bowlers per delivery (wides and no-balls included). Alternating balls instead of matches gives a smaller n50 (adjacent balls share bowler and match state), so the match split is the conservative one. Limit: IPL 2023+ players top out at about 600 balls, so n70 above that is extrapolated.

### Men's T20 (all leagues + T20I; about 2,400 players with 100+ balls; best measured)
| component | batters n50 (range) | n70 | bowlers n50 (range) | n70 |
|---|---|---|---|---|
| dot % | 76 (70-82) | 178 | 83 (78-88) | 194 |
| 1-3 run % | 88 (82-94) | 205 | 67 (64-72) | 157 |
| four % | 130 (121-139) | 302 | 125 (115-132) | 292 |
| six % | 99 (89-111) | 232 | 409 (368-471) | 955 |
| dismissal / wicket rate | 362 (319-402) | 844 | 1412 (1162-1717) | 3295 |
| wides + no-balls % | - | - | 80 (72-88) | 188 |
| runs per ball | 103 (94-113) | 240 | 147 (134-160) | 342 |
| runs added per ball | 2669 (1941-4228) | 6228 | 876 (774-1045) | 2043 |

### IPL 2023+ only (about 120 players at 100 balls, 40 at 600; narrower talent spread, so larger n50)
| component | batters n50 (range) | n70 | bowlers n50 (range) | n70 |
|---|---|---|---|---|
| dot % | 249 (184-355) | 582 | 142 (103-202) | 330 |
| 1-3 run % | 98 (79-130) | 228 | 53 (43-64) | 123 |
| four % | 213 (163-308) | 496 | 224 (157-325) | 523 |
| six % | 163 (121-237) | 381 | 534 (337-940) | 1245 |
| dismissal / wicket rate | 1102 (659-1687) | 2572 | 1777 (774-3130) | 4146 |
| wides + no-balls % | - | - | 144 (114-202) | 336 |
| runs per ball | 268 (191-425) | 625 | 355 (267-524) | 829 |
| runs added per ball | 1746 (874-3736) | 4074 | 747 (488-1247) | 1743 |

Reading: dots, 1-3 runs, fours, extras settle inside a season (50-250 balls). Sixes take 100 (batting) to 400+ (bowling). Dismissals need 360 (batting) to 1,400+ (bowling) balls, and runs added per ball (what WAR uses) 900 to 2,700+: a 400-ball season is mostly noise. For comparison, baseball: K% 70 batters faced, BABIP about 2,000 balls in play [src: Baseball Prospectus, from the research doc]. No published T20 table was found in the research step.

## 2. Component (Marcel-style) projection
Runs added per player-season is split **exactly** into: base (what his phase / wickets-down mix is worth for an average player, about 0), one part per ball-outcome class (dot, 1-3, four, six, out / wicket, wides+no-balls for bowlers; his deviation from the league rate in that league-season-cell, valued at the league value of that class), and R (rest: value differences inside a class, non-striker run-outs). Cells = 3 phases x 3 wickets-down buckets. Each part is projected as (weighted sum over the last 5 seasons) / (balls + mk x k); other leagues at weight a and strength s, recency weight rw; **k per part by method of moments from earlier seasons only** (all men's leagues). k for 2027 (balls): batters dot 94, 1-3 100, four 239, six 74, out 4,405, R 261; bowlers dot 116, 1-3 146, four 195, six 207, extras 78, R 376, **wicket: no between-bowler variation detected after adjusting for phase and wickets down (k = infinity)**. a, s, mk, rw tuned on earlier seasons as in `war.fit_for` (the tuned grid picked the heaviest shrink, mk 4, at the grid edge: a warning sign); an untuned version (k as estimated, a and s as war.py, no recency weight) is also reported. pWAR = (rate - replacement) x expected balls / runs per win, as in war.py.

## 3. Out-of-sample validation (IPL 2024, 2025, 2026 targets, data before the target only; 160 batter-seasons, 147 bowler-seasons)
| role | method | r | Spearman | MAE (wins) | r minus current pWAR (95% range) | MAE minus pWAR |
|---|---|---|---|---|---|---|
| bat | **current pWAR** | 0.060 | 0.059 | 0.337 | - | - |
| bat | components, tuned | 0.083 | 0.047 | 0.340 | +0.024 (-0.157, +0.178) | +0.002 |
| bat | components, untuned | 0.067 | 0.048 | 0.343 | +0.008 (-0.163, +0.147) | +0.006 |
| bat | controllable, tuned / untuned | 0.059 / 0.052 | 0.040 / 0.045 | 0.343 / 0.348 | -0.000 / -0.007 | +0.005 / +0.011 |
| bat | last-season WAR | 0.092 | 0.063 | 0.474 | +0.033 (-0.123, +0.179) | +0.137 |
| bat | league mean (0) | - | - | 0.344 | - | +0.007 |
| bowl | **current pWAR** | 0.317 | 0.205 | 0.358 | - | - |
| bowl | components, tuned | 0.343 | 0.264 | 0.355 | +0.026 (-0.036, +0.084) | -0.003 |
| bowl | components, untuned | 0.366 | 0.285 | 0.353 | +0.050 (-0.002, +0.103) | -0.006 |
| bowl | controllable, tuned / untuned | 0.363 / 0.366 | 0.286 / 0.303 | 0.354 / 0.354 | +0.046 / +0.050 (-0.013, +0.114) | -0.004 / -0.005 |
| bowl | last-season WAR | 0.193 | 0.128 | 0.483 | -0.124 | +0.124 |
| bowl | league mean (0) | - | - | 0.380 | - | +0.022 |

Rate-level loss (ball-weighted RMSE of runs added per ball, players 60+ balls, as VALUE_step3): batters 0.2074 (pWAR) vs 0.2063 (components); bowlers 0.2179 vs 0.2164. Differences of 0.001 are 0.5% of the loss: noise.

Does each part repeat? Next-season r of the projection of the part vs the realised part (players 100+ balls both years; batters n 135, bowlers 118); last season's raw value of the part in brackets:
| part | batters | bowlers |
|---|---|---|
| dot | 0.43 (0.34) | 0.52 (0.43) |
| 1-3 runs | 0.23 (0.17) | 0.10 (0.09) |
| four | 0.30 (0.15) | 0.59 (0.47) |
| six | 0.48 (0.37) | 0.18 (0.21) |
| out / wicket | 0.30 (0.22) | -0.01 (-0.01) |
| wides+no-balls | - | 0.51 (0.41) |
| R (rest) | 0.21 (0.21) | 0.03 (0.07) |
| base (mix) | 0.13 (0.27) | 0.26 (0.22) |

SD of the realised part per 100 balls: sixes 12 (bat) / 9 (bowl), outs / wickets 12-13, R 10-11, fours 6-7, dots 3.4-3.6. The noisy parts are most of the variance and the repeatable parts are small, which is why the total barely moves.

## 4. Errors-in-variables check of the trade slope (215 IPL 2024-26 matches)
Logistic slope of the match result on the difference of the two XIs' summed value; value of season t from data before t only.
| value used | beta (10-90) | P(beta>0) | SD of XI difference | beta per SD | leave-one-season-out log-loss |
|---|---|---|---|---|---|
| trade tool's recent value (4/3/2/1 of past WAR) | 0.094 (-0.028, 0.237) | 0.85 | 1.41 | 0.133 | 0.6920 |
| current pWAR | 0.317 (-0.223, 0.890) | 0.79 | 0.34 | 0.107 | 0.6922 |
| component pWAR | 0.039 (-0.497, 0.634) | 0.55 | 0.30 | 0.012 | 0.6980 |
| controllable WAR | -0.199 (-0.654, 0.304) | 0.31 | 0.35 | -0.069 | 0.6946 |

(Coin flip = 0.6931.) Beta rises with pWAR only because shrunk values are about 4 times smaller; the effect per SD does not rise and predictive log-loss does not improve. Match outcomes are close to unpredictable from squad value at this sample, so a disattenuated "true" beta is not identifiable here. Keep the trade tool's beta.

## Doubts
- 307 player-seasons over 3 targets; r-difference ranges are +/-0.15 (batters) and +/-0.06 (bowlers). A true bowler gain of 0.03-0.05 is possible but unproven; I tried 5 variants, so the best-looking one (bowl untuned, +0.05) is optimistic.
- The no-wicket-skill result for bowlers rests on a method-of-moments estimate; the raw split-half (includes role/phase) shows some repeatability (n50 1,400-1,800).
- Controllable WAR drops part R and shrinks wickets, moving some batters a lot (Sai Sudharsan pWAR 0.25, controllable -0.12; Abhishek Sharma 0.27 vs 0.55). Validated only as in the table above.
- `war.write_pwar_csv` rewrites the CSV without the controllable columns; rerun `python -m cricket_analytics.models.components build` afterwards. Original CSV columns verified identical to the committed version.
- The live DB was swapped (adds SMAT) after the validation runs; old data identical per the coordinator. `smat` is not in `war.LEAGUES` and was not used.
