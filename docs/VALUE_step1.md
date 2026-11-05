# Value step 1: run expectancy and Runs Added

Built 2026-11-06 from `data/cricket_analytics.duckdb` (read-only). Code: `src/cricket_analytics/models/run_expectancy.py`
(fit + lookup), `analysis/runs_added.py` (module id `runs_added`), charts in `viz/runs_added.py` and `viz/video/runs_added.py`,
tests in `tests/test_runs_added.py`. Rebuild the tables: `.venv\Scripts\python -m cricket_analytics.models.run_expectancy` (about 15 s).
Everything below is **measured by us** unless marked guess.

## 1. How it works (plain words)
- **Run expectancy (RE)** = the average number of runs a side goes on to score, from a given moment, to the end of the
  first innings. A moment = (wickets lost, balls left). Fitted per competition-group (`ipl_male`, `t20i_female`, `hundred_male`...)
  and era, only on trusted first innings (all overs bowled or all out; D/L and awarded matches out; super overs out).
- **Smoothing:** raw cell averages are thin where few innings reach that state. Each wicket row is smoothed along balls left
  (local-linear kernel, so no bias at the innings start), thin cells copy the shape of a neighbouring wicket row, then the table is
  forced monotone (more balls left -> more runs; more wickets lost -> fewer runs) with weighted isotonic regression. The tables
  are 3 CSVs in `models/data/` (`run_expectancy.csv`, `adjust.csv`, `venue_factor.csv`, 400 KB together).
- **Ball value** = runs on the ball + RE(after) - RE(before). It splits into a *ball part* (using up a ball) and a *wicket part*
  (RE(wickets + 1) - RE(wickets), always negative).
- **Batter** gets off-bat runs + ball part + the wicket part when *he* is out. A non-striker run out is charged to the
  dismissed non-striker, not to the striker. Wides give the batter nothing. Extras are not his, so a constant `bat_k` (about +0.075 runs per ball
  = the league's average extras, about 9 runs an innings) is added; it is fitted so the average credit is exactly 0 on the fit sample.
- **Bowler** gets the opposite of (bat runs + wides + no-balls + ball part + wicket part if the wicket is his). Byes/leg-byes and run outs
  are not charged/credited; a constant `bowl_k` (between -0.02 and +0.03 per ball) centres him the same way.
- **Second innings:** same table (it was only fitted on first innings), with RE capped by the runs still needed (`min(RE, target - score)`),
  so a chase that reaches the target stops paying. No attempt to model the chase as a different game: this is a *run-scoring* measure, not
  win probability (the WPA module covers that). Measured: the centred credit in IPL chases is not 0 but +1.1 (batters) / +1.4 (bowlers) runs per innings.
- **Ground factor:** venue's average first-innings total / era average, shrunk toward 1 as (n x ratio + 10) / (n + 10); it multiplies the RE
  change (not the runs). A high-scoring ground makes a dot ball and a wicket cost more. Venues are matched by exact name.

## 2. Eras (choice and evidence)
Average first-innings total per season (trusted innings), IPL:

| 2008 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | **23** | 24 | 25 | 26 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 163 | 150 | 165 | 156 | 158 | 157 | 164 | 169 | 164 | 166 | 172 | 169 | 170 | 159 | 171 | **183** | 190 | 192 | 196 |

Era split chosen: **IPL 2008-2022 (avg 163.4) vs 2023+ (avg 190.1)**: the jump is the impact-player era and has no counterpart earlier.
**Blast: up to 2021 (168.5) vs 2022+ (177.0).** BBL, PSL, CPL, SA20, Hundred, men's T20I and women's T20I: one era each (no clear step;
men's T20I wobbles between 144 and 153 since 2021). Averages used: men's T20I 150.4, women's T20I 119.7, BBL 162.7, PSL 170.3, CPL 159.6,
SA20 166.4, Hundred 147.9 (100 balls).
Caveat: IPL 2026 is already 196 (the 2023+ table is fitted on all of 2023-26, so it understates 2026 scoring a little).

## 3. Run-expectancy excerpts (expected runs still to come)
ipl_male 2023
| wickets lost | balls left | expected runs to go |
|---|---|---|
| 0 | 120 | 190.6 |
| 0 | 60 | 111.5 |
| 1 | 96 | 154.6 |
| 3 | 60 | 97.8 |
| 3 | 30 | 59.7 |
| 6 | 30 | 44.1 |
| 6 | 12 | 20.9 |
| 8 | 12 | 14.2 |
| 9 | 6 | 7.6 |
ipl_male 0
| wickets lost | balls left | expected runs to go |
|---|---|---|
| 0 | 120 | 163.5 |
| 0 | 60 | 98.4 |
| 1 | 96 | 134.7 |
| 3 | 60 | 87.0 |
| 3 | 30 | 52.8 |
| 6 | 30 | 37.0 |
| 6 | 12 | 19.4 |
| 8 | 12 | 11.3 |
| 9 | 6 | 4.8 |
hundred_male 0
| wickets lost | balls left | expected runs to go |
|---|---|---|
| 0 | 100 | 147.7 |
| 0 | 40 | 76.9 |
| 1 | 76 | 113.4 |
| 3 | 60 | 85.6 |
| 3 | 30 | 53.5 |
| 6 | 30 | 45.6 |
| 6 | 12 | 20.0 |
| 8 | 12 | 17.4 |
| 9 | 6 | 3.9 |

Start state check (RE at 0 wickets and a full innings = the era's mean first-innings total): IPL 163.5 vs 163.4 and 190.6 vs 190.1;
all 11 group/era tables are within 3 runs (test `test_start_state_equals_average_first_innings_total`) and all are monotone in both directions.

## 4. IPL leaderboards (`runs_added`, min 100 balls, raw numbers beside)

### 2025 batters (top 15)
| batter | balls | runs | strike_rate | runs_added | runs_added_per_100_balls |
|---|---|---|---|---|---|
| B Sai Sudharsan | 481 | 754 | 156.76 | 123.8 | 25.74 |
| H Klaasen | 282 | 487 | 172.7 | 120.8 | 42.83 |
| SA Yadav | 403 | 682 | 169.23 | 93.2 | 23.12 |
| D Brevis | 125 | 225 | 180.0 | 76.4 | 61.11 |
| SS Iyer | 335 | 597 | 178.21 | 74.8 | 22.33 |
| MR Marsh | 383 | 627 | 163.71 | 74.3 | 19.39 |
| V Kohli | 451 | 656 | 145.45 | 73.2 | 16.22 |
| N Pooran | 267 | 524 | 196.25 | 65.8 | 24.66 |
| R Parag | 236 | 393 | 166.53 | 58.6 | 24.85 |
| KL Rahul | 360 | 539 | 149.72 | 57.5 | 15.96 |
| Naman Dhir | 128 | 245 | 191.41 | 57.5 | 44.95 |
| A Mhatre | 127 | 240 | 188.98 | 56.8 | 44.73 |
| A Badoni | 222 | 329 | 148.2 | 56.6 | 25.48 |
| AM Rahane | 264 | 390 | 147.73 | 50.6 | 19.16 |
| Shashank Singh | 223 | 349 | 156.5 | 49.7 | 22.29 |

### 2025 bowlers (top 15)
| bowler | legal_balls | runs_conceded | economy | wickets | runs_added | runs_added_per_24_balls |
|---|---|---|---|---|---|---|
| Noor Ahmad | 300 | 408 | 8.16 | 24 | 114.1 | 9.13 |
| Kuldeep Yadav | 306 | 361 | 7.08 | 15 | 113.8 | 8.92 |
| JJ Bumrah | 260 | 297 | 6.85 | 16 | 111.9 | 10.33 |
| JR Hazlewood | 246 | 372 | 9.07 | 19 | 97.8 | 9.54 |
| CV Varun | 300 | 383 | 7.66 | 17 | 93.1 | 7.45 |
| TA Boult | 322 | 495 | 9.22 | 20 | 91.7 | 6.84 |
| M Prasidh Krishna | 330 | 451 | 8.2 | 24 | 90.6 | 6.59 |
| R Sai Kishore | 231 | 359 | 9.32 | 17 | 49.7 | 5.17 |
| Mohammed Siraj | 324 | 498 | 9.22 | 15 | 44.4 | 3.29 |
| MJ Santner | 237 | 313 | 7.92 | 10 | 44.0 | 4.46 |
| A Kamboj | 129 | 172 | 8.0 | 8 | 39.8 | 7.41 |
| JD Unadkat | 143 | 175 | 7.34 | 11 | 38.3 | 6.43 |
| KH Pandya | 270 | 369 | 8.2 | 17 | 31.5 | 2.8 |
| HH Pandya | 204 | 324 | 9.53 | 14 | 31.2 | 3.67 |
| JC Archer | 273 | 431 | 9.47 | 11 | 29.2 | 2.57 |

### 2026 batters (top 15)
| batter | balls | runs | strike_rate | runs_added | runs_added_per_100_balls |
|---|---|---|---|---|---|
| V Suryavanshi | 313 | 737 | 235.46 | 196.7 | 62.84 |
| RM Patidar | 229 | 440 | 192.14 | 119.7 | 52.27 |
| Ishan Kishan | 330 | 602 | 182.42 | 113.6 | 34.42 |
| KL Rahul | 340 | 593 | 174.41 | 96.0 | 28.24 |
| JP Inglis | 143 | 266 | 186.01 | 88.0 | 61.55 |
| C Connolly | 301 | 491 | 163.12 | 76.0 | 25.25 |
| Abhishek Sharma | 275 | 563 | 204.73 | 73.6 | 26.75 |
| H Klaasen | 390 | 624 | 160.0 | 71.4 | 18.31 |
| D Ferreira | 177 | 317 | 179.1 | 64.7 | 36.57 |
| V Kohli | 405 | 675 | 166.67 | 61.1 | 15.09 |
| D Padikkal | 250 | 430 | 172.0 | 54.7 | 21.88 |
| MP Stoinis | 120 | 216 | 180.0 | 42.0 | 34.98 |
| Tilak Varma | 236 | 345 | 146.19 | 40.0 | 16.94 |
| B Sai Sudharsan | 457 | 722 | 157.99 | 39.3 | 8.59 |
| VR Iyer | 112 | 209 | 186.61 | 37.3 | 33.33 |

### 2026 bowlers (top 15)
| bowler | legal_balls | runs_conceded | economy | wickets | runs_added | runs_added_per_24_balls |
|---|---|---|---|---|---|---|
| B Kumar | 354 | 467 | 7.92 | 28 | 183.3 | 12.43 |
| K Rabada | 388 | 626 | 9.68 | 29 | 118.5 | 7.33 |
| JO Holder | 230 | 290 | 7.57 | 17 | 102.3 | 10.68 |
| SP Narine | 306 | 339 | 6.65 | 15 | 95.1 | 7.46 |
| L Ngidi | 248 | 340 | 8.23 | 13 | 70.5 | 6.82 |
| E Malinga | 326 | 507 | 9.33 | 20 | 68.4 | 5.04 |
| J Overton | 168 | 249 | 8.89 | 14 | 59.4 | 8.49 |
| Mohsin Khan | 168 | 228 | 8.14 | 11 | 59.4 | 8.48 |
| Rashid Khan | 341 | 516 | 9.08 | 21 | 56.1 | 3.95 |
| JR Hazlewood | 285 | 445 | 9.37 | 14 | 52.2 | 4.4 |
| Rasikh Salam | 233 | 352 | 9.06 | 18 | 51.3 | 5.28 |
| JC Archer | 348 | 542 | 9.34 | 24 | 48.6 | 3.35 |
| RA Jadeja | 198 | 277 | 8.39 | 10 | 46.5 | 5.63 |
| AJ Hosein | 148 | 198 | 8.03 | 8 | 40.8 | 6.62 |
| AS Roy | 163 | 261 | 9.61 | 9 | 27.2 | 4.01 |

### Other checks
IPL 2022 batters (top 8):

| batter | balls | runs | strike_rate | runs_added | runs_added_per_100_balls |
|---|---|---|---|---|---|
| JC Buttler | 579 | 863 | 149.05 | 157.9 | 27.27 |
| DJ Hooda | 330 | 451 | 136.67 | 104.4 | 31.63 |
| KD Karthik | 180 | 330 | 183.33 | 86.9 | 48.26 |
| LS Livingstone | 240 | 437 | 182.08 | 86.1 | 35.88 |
| KL Rahul | 455 | 616 | 135.38 | 82.0 | 18.02 |
| RM Patidar | 218 | 333 | 152.75 | 82.0 | 37.63 |
| AD Russell | 192 | 335 | 174.48 | 80.8 | 42.06 |
| SA Yadav | 208 | 303 | 145.67 | 55.7 | 26.8 |

IPL 2016 batters (top 8; Kohli's 113* in a D/L match is excluded by design, so he shows 860 runs, not 973):

| batter | balls | runs | strike_rate | runs_added | runs_added_per_100_balls |
|---|---|---|---|---|---|
| AB de Villiers | 405 | 687 | 169.63 | 187.6 | 46.31 |
| DA Warner | 556 | 848 | 152.52 | 179.5 | 32.28 |
| V Kohli | 590 | 860 | 145.76 | 117.8 | 19.96 |
| KH Pandya | 124 | 237 | 191.13 | 65.9 | 53.11 |
| Q de Kock | 319 | 443 | 138.87 | 48.3 | 15.14 |
| SPD Smith | 140 | 224 | 160.0 | 40.8 | 29.14 |
| AD Russell | 114 | 188 | 164.91 | 36.7 | 32.16 |
| RG Sharma | 368 | 489 | 132.88 | 35.5 | 9.65 |

IPL 2024 bowlers (top 8; the tables after this one in the raw output are career lists, quoted in section 5):

| bowler | legal_balls | runs_conceded | economy | wickets | runs_added | runs_added_per_24_balls |
|---|---|---|---|---|---|---|
| JJ Bumrah | 287 | 297 | 6.21 | 18 | 170.4 | 14.25 |
| TA Boult | 320 | 443 | 8.31 | 16 | 80.9 | 6.07 |
| Sandeep Sharma | 228 | 311 | 8.18 | 13 | 67.3 | 7.09 |
| M Pathirana | 132 | 169 | 7.68 | 13 | 61.0 | 11.1 |
| SP Narine | 312 | 347 | 6.67 | 16 | 59.7 | 4.59 |
| TU Deshpande | 288 | 424 | 8.83 | 17 | 56.1 | 4.68 |
| CV Varun | 276 | 385 | 8.37 | 19 | 54.4 | 4.73 |
| Harshit Rana | 235 | 349 | 8.91 | 17 | 49.0 | 5.0 |

## 5. Sanity discussion
- **Good:** the well-known big seasons come out on top: Buttler 2022 (863 runs, #1), de Villiers and Warner 2016 (#1, #2), Bumrah 2024 (#1 by a wide
  margin, +170 vs +81 for #2), Sudharsan and Klaasen 2025, Suryavanshi 2026 (SR 235). IPL career lists (min 1,500 balls batting, 1,000 bowling) put de Villiers (+737),
  Warner, Gayle, Rahul at the top of the batters and Narine (+845), Bumrah (+841), Rashid Khan among bowlers. Nothing absurd.
- **Context works as intended:** a steady opener (Hooda 2022: SR 137) can rate above a 183 SR finisher (Karthik) in total because he faced more of the innings;
  per 100 balls the finishers lead (Karthik 48, Russell 42). Brevis (125 balls, +61 per 100) and Mhatre show the small-sample issue: use `min_balls` and read total and rate together.
- **Oddities (not chased):** (1) Sai Sudharsan 2026: SR 158 and 722 runs but only +8.6 per 100: RE says his dismissals and slow balls cost real runs. (2) Kuldeep and Noor
  rank above Prasidh (purple cap, 24 wkts) in 2025: the metric rewards runs saved in the situation, not wicket count. (3) Chahal's career total is low (+233) because his economy (8.0) is poor
  for the era-adjusted baseline although he took 223 wickets. (4) The Hundred row for 9 wickets down rests on 85 balls: the values there are a near-flat guess (3.9 runs). Rare states, but flagged.
- **Not adjusted:** batting order (state handles part of it), opposition quality, pitch within a ground, and the strength of the batter's own side.

## 6. Stability (is it more repeatable than strike rate?)
Method: IPL, each pair of consecutive seasons 2008->2026, players with at least N balls in BOTH seasons; Pearson correlation of the rate in season N with the
same player's rate in N+1, pooled over all pairs. Batting: runs added per 100 balls vs strike rate. Bowling: runs added per 24 balls vs economy.

| role | min balls | pairs | runs_added rate | raw (SR / economy) |
|---|---|---|---|---|
| batting | 100 | 673 | **0.055** | 0.435 |
| batting | 150 | 467 | **0.171** | 0.484 |
| bowling | 100 | 593 | **0.133** | 0.518 |
| bowling | 150 | 428 | **0.154** | 0.541 |

**Result: runs added is much LESS repeatable than plain strike rate / economy in single IPL seasons.** Honest reading:
- Diagnostic (batting, min 100 balls, 673 pairs): next-season correlation SR 0.435; ball-part rate 0.252; wicket-part rate 0.247; total 0.063; outs per 100 balls 0.211.
  Within a season the total correlates +0.62 with SR and -0.43 with dismissal rate. Its SD is 18.8 runs per 100 balls (ball part 16.5, wicket part 13.1).
- The two parts are each partly stable but offset each other (aggressive batters gain on the ball part and lose on the wicket part), and each dismissal is a big lump
  (about -6 runs on average, more early in the innings). A 100-ball sample holds only ~4 dismissals, so dismissal luck alone swings the total by roughly 10-15 runs per 100 balls, comparable to the real spread between batters.
- Raw SR keeps its role (finishers always have a high SR), which makes it repeatable without being a fair comparison. Runs added removes the role effect, and what is left is noisier.
- (guess, untested) Using the batter's shrunk career dismissal rate for the wicket part, or windows of 2-3 seasons, would raise stability. Natural experiment before building WAR on this;
  for now a season of runs added is a descriptive number, not a forecast.

## 7. Other checks
- Sum of centred batting credit over first innings is 0.0 runs per innings (IPL 1,203 innings, men's T20I 3,336, Hundred 190), same for bowling. True by construction (offsets fitted on the same data), but it proves the
  telescoping and the non-striker run-out routing are consistent. In IPL chases it is +1.1 / +1.4 runs per innings (not forced to 0).
- Speed: one IPL season about 0.2 s; a full-IPL ranking about 1 s.
- Tests: `tests/test_runs_added.py`, 19 tests; the table tests need only the shipped CSVs.

## 8. Doubts and not done
1. `pyproject.toml` package-data lists only `reference/*.csv` and `reference/*.json`: add `models/data/*.csv` (and `*.json` for the other worker's file) or a non-editable install will miss the tables. I did not edit pyproject (outside my files).
2. IPL 2026 already scores 196 vs the 190 era average: a third era or a recency weight may be needed.
3. The second-innings treatment (same table, capped by runs needed) is a simple choice and is not validated against win probability.
4. A new competition in the DB needs a refit (`python -m cricket_analytics.models.run_expectancy`) before `runs_added` works for it (it raises a clear error).
5. Women's T20I uses 2009-2026 as one era although scoring rose; check before quoting women's numbers.
