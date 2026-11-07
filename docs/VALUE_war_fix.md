# Does WAR describe a past IPL season? (war_fix, 2026-11-07)

All numbers **measured by us** (Cricsheet DuckDB, read-only). Until now we only tested whether WAR *predicts* (VALUE_step3, VALUE_backtest). This tests whether it *describes*: for each IPL team-season 2023-26 (40 team-seasons, 10 teams x 4), add up the WAR of every player who played for the team and compare with the wins the team actually got.
Code: `models/war.py` (`season_table(fielding=...)`, `load_params("v2")`), `models/data/war_params_v2.json`, `analysis/war.py` (`version=v1|v2`), `tests/test_war_v2.py`. The default is still **v1**; v2 is opt-in (`cricket run war --version v2`).

## 1. Short answer
- **WAR already describes team seasons well.** Summed over all of a team's players, v1 WAR has r = 0.78 with wins above half (slope 0.99, 95% range 0.78-1.22, so "1 WAR = 1 win" holds) and misses a team's wins by 0.98 on average. The best simple comparison, the team's actual run margin, gets r = 0.80 and a miss of 0.92. A team's wins are 14 coin-flip-ish matches, so this is close to the ceiling.
- **Hardik's -2.04 is not a team-level bug.** A team-level test cannot see who inside a team got the credit, so I also decomposed Hardik by hand (section 4): the number is what his ball-by-ball record says, not an artefact. v1 does overstate how negative it looks, because its replacement level is too high.
- What I found and fixed (in v2, opt-in): run-outs credited nobody on the fielding side; the replacement level was so high that a team of "replacement" players would win 46% of its matches (about 35% is sensible); bowlers carried all the luck of catches.

## 2. Team-season fit (40 team-seasons; y = wins above half; WAR summed over all players of the team)
"Repl. team" = win share of a team whose every player is at WAR 0 (the regression intercept). MAE = mean miss in wins.

| predictor | r | slope (wins per 1 unit) | MAE | repl. team |
|---|---|---|---|---|
| **v1 WAR (before)** | 0.784 | 0.99 (0.78-1.22) | 0.98 | 46% |
| v1, batting part only | 0.63 | 1.22 | 1.20 | - |
| v1, bowling part only | 0.48 | 0.80 | 1.38 | - |
| **v2 WAR (after)**: run-outs, catches, replacement -6 | **0.803** | 0.98 (0.77-1.22) | **0.93** | **36%** |
| v2, fielding part only | 0.52 | 2.49 | 1.32 | - |
| WPA summed over the team (win probability added, in wins) | 0.978 | 1.00 | 0.32 | - |
| actual run margin (per 100 runs) | 0.80 | 0.95 | 0.92 | - |

- WPA is nearly an identity (the win-probability changes of a match add up to its result), so r = 0.98 only shows the win-probability model is consistent. Per part, WPA batting r 0.62 and bowling 0.48 match WAR (0.63 / 0.48).
- By year, v2 / v1: 2023 0.90 / 0.87, 2024 0.75 / 0.75, 2025 0.71 / 0.69, 2026 0.87 / 0.85.
- Joint fit of wins on the three v2 parts: batting 1.15 (+-0.19), bowling 0.70 (+-0.19), fielding 1.40 (+-0.49) wins per WAR. Bowling looks worth a bit less in wins than batting (about 1.5 SE below 1: noise-sized; no change made).
- A mistake I made on the way and corrected: regressing raw wins instead of wins above half made a lower replacement level look much better (r 0.75 to 0.82), only because teams that play more matches (playoffs) have more wins and more balls. The table uses wins above half.

## 3. Audit of each piece (rule stated before the runs)
Rule: keep a change if (a) team r or MAE improves and the slope stays near 1, and (b) year-to-year repeatability of batting and bowling runs added per ball does not fall by more than 0.02 (noise is about +-0.04). Conventions that team data cannot test (catch share, replacement level) are set by a stated criterion and live in v2 only.
Repeatability = correlation of a player's runs added per ball in one IPL season with the next season (batters 150+ balls both years, n = 481; bowlers 100+, n = 601; 2008-2026). "tot" = the same for total WAR (players with 150+ balls).

| change | team r | MAE | repl. team | bat rep. | bowl rep. | tot rep. | verdict |
|---|---|---|---|---|---|---|---|
| v1 as shipped | 0.784 | 0.98 | 46% | 0.131 | 0.145 | 0.184 | baseline |
| run-outs credited to the fielders (full wicket value, split equally) | 0.793 | 0.95 | 46% | 0.131 | 0.148 | 0.176 | **keep** |
| + 10 / 20 / 30 / 50% of catches and stumpings moved from bowler to fielder | 0.793 | 0.95 | 46% | 0.131 | 0.163 / **0.178** / 0.195 / 0.230 | 0.185 / **0.202** / 0.225 / 0.285 | **keep 20%** (convention) |
| replacement -6 per 100 balls, both roles (v1: bat 0, bowl -3.3) | 0.803 | 0.93 | 36% | 0.131 | 0.178 | 0.215 | **keep** |
| replacement -4.5 / -8 | 0.800 / 0.806 | 0.94 / 0.92 | 40% / 32% | same | same | 0.217 / 0.213 | sensitivity |
| centre runs added by phase (powerplay / middle / death) | 0.782 | 0.99 | 46% | 0.122 | 0.138 | 0.181 | **reject** (no fit gain; batting repeatability 2022+ 0.120 to 0.086) |
| runs per win 99.3 | slope 0.99 (0.78-1.22) | | | | | | **unchanged** (slope scales as 1/rpw: 87 would give 1.13, 110 gives 0.89, both inside the range; two independent routes give 99-105) |

Notes on each item:
- **Replacement level.** Team data cannot identify it (every team uses about the same number of balls, so it only moves the intercept), so it is a convention. v1's 0 / -3.3 came from players outside the top 11 in the *next* season, a group biased toward good ones; the same-season measure (-21 / -14) is biased the other way. -6 sits between them and makes a replacement team win 36% (baseball uses about 29%). It lifts everybody by 6 runs per 100 balls, about +0.06 wins per 100 balls: a 450-ball batter gains +0.27 wins.
- **Fielding.** v1 charged a run-out to the batter and credited nobody, so the fielding side's books did not balance. v2 gives the run-out's value to the fielders named (split equally; Cricsheet does not say who threw) and moves 20% of each catch or stumping from the bowler to the fielder. No drop or chance data exists, so 20% is a convention. Warning: bowler repeatability rises with any share (0.30 at 100%) because it removes a noisy piece; that is not evidence the share is right. The reviewed keeper list is not needed: stumpings are marked in the data.
- **Entry situation / phase.** Runs added already compares each ball with the run expectancy for the wickets and balls left. Average runs added per 100 balls by batting position (2023-26, relative to the league mean): positions 1-2 +0.6, 3 +1.1, 4 +0.2, 5 +2.1, 6 +3.7, 7 -4.7, 8+ -9.9. Finishers (5-6) come out slightly positive and the tail negative, as skill would suggest; no finisher penalty. Bowling per 100 balls by phase: powerplay +1.9, middle +0.3, death -1.7 (small; centring it did not help).
- **Not-outs.** A not-out batter pays no wicket cost and gets runs plus the cost of the balls used. Nothing to fix; the team sums include every batter.
- **Impact players and short stints.** WAR is per ball, so a player who bowls 12 balls gets WAR for 12 balls. Short stints add noise to single players but nothing to team sums (every ball is in the 40 team sums). No change.
- **All-rounders (bat / bowl split).** Both parts are measured against the same average player per ball, then added. The joint fit shows no sign of double counting.

## 4. The sanity players, IPL 2023-26 (sum of seasons; WAR)
| player | v1 bat | v1 bowl | v1 total | v2 bat | v2 bowl | v2 field | v2 total |
|---|---|---|---|---|---|---|---|
| HH Pandya | -1.00 | -1.04 | **-2.04** | -0.58 | -1.23 | +0.23 | **-1.58** |
| JJ Bumrah | -0.09 | 3.29 | 3.20 | -0.07 | 3.10 | 0.17 | 3.19 |
| V Kohli | 1.18 | 0.00 | 1.18 | 2.26 | 0.00 | 0.65 | 2.91 |
| SP Narine | -0.62 | 2.76 | 2.14 | -0.34 | 2.61 | 0.42 | 2.69 |
| RA Jadeja | 0.23 | 1.90 | 2.14 | 0.68 | 1.46 | 0.25 | 2.39 |
| H Klaasen | 3.99 | 0.00 | 3.99 | 4.72 | 0.00 | 0.48 | 5.20 |

Why v2 moves them: players with many balls gain from the lower replacement level (Kohli faced about 1,800 balls: +1.1 wins), bowlers give a little to fielders (Jadeja bowl 1.90 to 1.46), and fielders and keepers gain their catches. Kohli's total now passes Jadeja and Narine; the rest keep their order.

**Hardik, checked by hand** (IPL ball-by-ball):

| season | bowling: balls, economy (league), wickets | batting: balls, strike rate (batters in his slot) |
|---|---|---|
| 2023 | 144, 8.92 (8.85), 3 | 253, 137 (about 146) |
| 2024 | 216, 10.75 (9.42), 11 | 151, 143 (about 150) |
| 2025 | 204, 9.53 (9.52), 14 | 137, 164 (about 150-157) |
| 2026 | 136, 11.43 (9.77), 4 | 149, 138 (about 144-152) |

He bowled at or above the league economy in all four seasons (11.4 in 2026) and batted below the strike rate of batters in his slot in three of four seasons. Over about 1,100 balls the total is -226 runs added (-20 per 100 balls), which is -2.3 wins before replacement. The noise on 1,100 balls is about +-0.7 wins, so "below average" is real in this record but the size is not precise; the part of v1 that overstated it was the high replacement level (v2: -1.58). He often bowled with wickets down in the powerplay (0.9 down on average against 0.7 for the league). A ball bowled when the batting side has lost wickets is worth less in the run-expectancy table, so the same economy scores lower. That is the method working as designed, not a bug.

## 5. What changed and what did not
- New: `version=v2` on the `war` module (season view): fielding credit (`field_war` column), replacement -6 / -6 in both eras, fielding shares in `war_params_v2.json`. v1 output is unchanged (existing WAR tests and golden numbers pass).
- **Defaults not changed.** The v2 gain is small (r +0.02, MAE -0.05 wins, bowler repeatability +0.03, replacement team 46% to 36%), and v1 feeds the trade tool, the auction models and pWAR, which would need re-deriving. pWAR (projection) stays v1 and is not refitted for v2.
- Ideas, not done: refit pWAR on v2 (S); v2 in `cricket facts` (S); dropped-catch data from a ball-tracking source (L, none free).
