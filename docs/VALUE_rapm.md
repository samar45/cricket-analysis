# Opponent-adjusted player value (RAPM) and WAR v4 (2026-11-08)

All numbers **measured by us** (Cricsheet DuckDB, read-only). Code: `models/rapm.py`, tests `tests/test_rapm.py`, eval script `experiments/rapm_eval.py`.

## Verdict
- **Opponent quality barely matters in the IPL.** Over a season a batter faces a similar mix of bowlers as everyone else, so the correction averages out: for IPL 2023-26 players with 300+ balls it moves a player's total by about 4 runs (0.04 WAR, standard deviation), at most 15 runs (0.15 WAR, Noor Ahmad). v3 and v4 correlate 0.999.
- **WAR v4 = v3 + opponent adjustment** is added as `version=v4` on the war module (default stays v3). It passes the team-fit test and is a hair better on repeatability, but the gains are inside the noise. Next-season prediction is no better than the current per-ball predictors (section 4). Treat v4 as a fairness correction, not a better skill measure.
- The "pure" ridge value (effect x balls, shrunk toward average, one fit per season) **fails the team test** (r 0.69 vs 0.80): shrinkage compresses everything and the slope is 2.7, not 1. Not used as WAR.
- The wicket-by-batter-quality idea (section 5) is **rejected**.

## 1. Method in plain words
Every usable ball (no super overs) is one row. Target y = the batter-side runs added WAR already uses (runs on the ball + change in run expectancy; wicket part only when the bowler is credited; centred per league-season). Model: `y = batter effect - bowler effect + noise`, where a positive effect = good (batter adds runs, bowler removes them). Balls nobody faced (wides) have no batter term, y = minus the bowler's credit. This is a *ridge regression*: every player's effect is pulled toward 0 (= league average) by a penalty, so a player with few balls stays near average. The penalty lambda is in "balls of average evidence": a player with n balls keeps about n / (n + lambda) of his raw rate. It is chosen by 5-fold cross-validation where whole **matches** are held out (all balls of a match are in the same fold), with separate lambdas for batting and bowling. Solved by conjugate gradients on the normal equations in numpy (no scipy). One IPL fit (69,123 balls, 2023-26) takes under a second.

Fixed terms (phase, innings, venue) are not added: the run-expectancy surface and venue factor already inside y handle them (as in WAR).

**Lambda** (held-out-match mean squared error, IPL 2023-26; lower is better; the whole table varies by only 0.003 of 7.22, because ball-level noise is huge):

| lambda bat \ bowl | 250 | 500 | 1000 | 2000 | 4000 |
|---|---|---|---|---|---|
| 500 | 7.2187 | 7.2176 | 7.2179 | 7.2190 | 7.2202 |
| **1000** | 7.2181 | **7.2170** | 7.2172 | 7.2181 | 7.2192 |
| 2000 | 7.2185 | 7.2173 | 7.2174 | 7.2182 | 7.2193 |
| 4000 | 7.2191 | 7.2180 | 7.2180 | 7.2187 | 7.2197 |

Chosen: **batting 1000, bowling 500** (flat optimum; smaller than the usual n50 stability constants of 2669 / 876 balls because the opposition is now part of the model).

**WAR v4** (`rapm.v4_rows`): take v3's player-season rows (centred, 25% match adjustment) and add, per ball, the opposition's effect: a batter's ball gets + the bowler's effect, a bowler's ball gets + the batter's effect (wides: none); re-centre per league-season. Effects are fitted per era (before 2023, 2023 on) on all that era's IPL balls. Runs per win (99.3) and replacement (-6 per 100 balls) are v3's, unchanged. The pWAR projection (`view=projected`) is still the v3 file.

## 2. Test (a): team-season fit (40 IPL team-seasons 2023-26, WAR summed over a team's players vs wins above half; same function for all rows)
| version | r | slope | MAE (wins) |
|---|---|---|---|
| v3 | 0.798 | 0.97 | 0.95 |
| **v4 (v3 + opponent)** | **0.804** | 0.98 | 0.92 |
| v4 without the 25% match adjustment | 0.801 | 1.00 | 0.94 |
| v4 with wicket-quality variant | 0.798 | 0.96 | 0.94 |
| pure ridge (effect x balls, per season) | 0.693 | 2.68 | 1.08 |

Keep rule: r must not fall by more than 0.03 (noise at n = 40 is about 0.07). I wrote the rule down after seeing the pure-ridge row and before building the v4 comparison; v4 passes, pure ridge fails.

## 3. Test (b): season-to-season repeatability of per-ball value (Pearson r, consecutive seasons; bat 150+ balls, bowl 100+ both years)
| version | bat 2008-26 (n 481) | bowl 2008-26 (n 601) | bat 2023-26 | bowl 2023-26 |
|---|---|---|---|---|
| v3 | 0.145 | 0.148 | 0.144 | 0.170 |
| **v4** | **0.151** | **0.151** | **0.159** | **0.179** |
| v4 without match adjustment | 0.137 | 0.147 | 0.138 | 0.186 |
| v4 + wicket-quality (h = 24) | 0.151 | 0.144 | 0.159 | 0.163 |
| pure ridge per season | 0.146 | 0.173 | 0.166 | 0.210 |

All four v4 numbers are equal or higher than v3, but each rise (0.003-0.015) is far inside the noise (about +-0.04). The pure ridge's bowler gain partly comes from shrinkage by ball count.

## 4. Test (c): next-season backtest (data before the target only; IPL 2024-26 pooled Spearman; n about 200 per column, +-0.07 noise)
| predictor | total | bat_rate | bowl_rate |
|---|---|---|---|
| pwar (v3) | 0.009 | -0.005 | 0.138 |
| recent_value | 0.116 | - | - |
| worth | 0.205 | 0.103 | 0.309 |
| ipl3 (last 3 seasons, v3 per ball) | 0.120 | 0.067 | 0.138 |
| `rapm` (ridge effects, IPL 2023+ up to X) | 0.094 | 0.105 | 0.104 |
| `rapm_pool` (+ 7 other leagues at weight 0.5, a guess) | 0.079 | 0.077 | 0.161 |
| `rapm_adj` (ipl3 with opponent adjustment) | 0.119 | 0.071 | 0.134 |

Reading: `rapm_adj` equals `ipl3` (the opponent adjustment changes nothing measurable). The ridge predictor is better than pwar on batting rate, worse on bowling rate, and no predictor here beats `worth` (which uses far more information). Lambda for each backtest fit is chosen by 3-fold CV inside the training seasons (2023 data: 500 / 4000; 2024-25: 1000 / 1000; pooled: 500 / 500). The rank for "total" uses rate x expected balls.

## 5. Wicket value by batter quality
Checked: the run-expectancy wicket cost is the league average for any batter, so Kohli's and a number 10's wickets cost the same. The ball-level opponent term adds the dismissed batter's per-ball effect for that one ball only. Variant tested: count it for his expected remaining balls, min(balls left, 24) (24 is a guess). Result: team fit unchanged (0.798), bowler repeatability falls (0.151 -> 0.144 all years, 0.179 -> 0.163 since 2023). **Rejected**; `wicket_h` stays 0 (code option `opp_delta(..., wicket_h=24)`).

## 6. IPL 2023-26, top 10 (300+ balls, seasons summed)
v3 and v4 WAR (same order except bowler ranks 4-5):

| rank | batter | v3 | v4 | bowler | v3 | v4 |
|---|---|---|---|---|---|---|
| 1 | H Klaasen | 4.75 | 4.81 | B Kumar | 3.77 | 3.74 |
| 2 | B Sai Sudharsan | 3.21 | 3.18 | JJ Bumrah | 3.58 | 3.57 |
| 3 | KL Rahul | 2.67 | 2.71 | CV Varun | 3.51 | 3.52 |
| 4 | SA Yadav | 2.63 | 2.62 | SP Narine | 2.95 | 3.06 |
| 5 | Tilak Varma | 2.54 | 2.53 | TA Boult | 3.00 | 3.02 |
| 6 | Shubman Gill | 2.46 | 2.45 | Mohammed Siraj | 2.91 | 2.82 |
| 7 | V Kohli | 2.29 | 2.27 | Noor Ahmad | 2.25 | 2.40 |
| 8 | N Pooran | 2.16 | 2.24 | RA Jadeja | 2.12 | 2.20 |
| 9 | V Suryavanshi | 2.05 | 2.10 | Rashid Khan | 2.09 | 2.12 |
| 10 | RM Patidar | 1.88 | 1.87 | KH Pandya | 1.97 | 1.99 |

Pure ridge talent estimate (one fit over 2023-26, effect x balls, with +6/100 replacement, / 99.3; shrunk toward average, so smaller):

| rank | batter | per 100 | WAR | bowler | per 100 | WAR |
|---|---|---|---|---|---|---|
| 1 | H Klaasen | 19.3 | 3.07 | B Kumar | 15.4 | 2.89 |
| 2 | B Sai Sudharsan | 10.5 | 2.60 | CV Varun | 16.9 | 2.68 |
| 3 | Shubman Gill | 6.8 | 2.15 | Mohammed Siraj | 13.8 | 2.67 |
| 4 | KL Rahul | 9.1 | 2.02 | JJ Bumrah | 22.8 | 2.50 |
| 5 | V Kohli | 4.9 | 1.97 | SP Narine | 13.8 | 2.37 |

## 7. Sanity players, IPL 2023-26 (WAR, v3 -> v4)
| player | bat | bowl | total |
|---|---|---|---|
| JJ Bumrah | -0.06 -> -0.07 | 3.58 -> 3.57 | 3.52 -> 3.51 |
| V Kohli | 2.29 -> 2.27 | - | 2.29 -> 2.27 |
| H Klaasen | 4.75 -> 4.81 | - | 4.75 -> 4.81 |
| HH Pandya | -0.58 -> -0.62 | -0.89 -> -0.89 | -1.47 -> -1.51 |
| SP Narine | -0.37 -> -0.41 | 2.95 -> 3.06 | 2.58 -> 2.65 |
| Rashid Khan | 0.76 -> 0.74 | 2.09 -> 2.12 | 2.85 -> 2.85 |

Biggest single moves (runs, 4 seasons): bowlers Noor Ahmad +14.8, Narine +10.9, Siraj -9.2; batters Axar +8.7, Pooran +7.9, Gaikwad -8.9.

## 8. Limits
- Ball-level noise is enormous (a wicket swings y by 30+ runs); skill explains about 0.1% of the variance, so all effects are heavily shrunk and four IPL seasons cannot separate players finely.
- Run-outs of the striker are not charged to the bowler in the regression (v3 still charges the batter in WAR). Wides cost the bowler only.
- Pooled-league weight (0.5) and wicket height (24) are guesses. Players with few IPL balls borrow strength from other leagues only in `rapm_pool` (not in v4).
- Not wired: pWAR projection for v4, the trade / auction tools (they stay on v3).
