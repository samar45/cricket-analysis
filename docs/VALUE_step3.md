# Step 3: WAR (wins above replacement) and projected WAR (pWAR) for IPL 2027

Built 2026-11-06 from our own Cricsheet DuckDB (read-only). Everything is **measured by us** unless marked guess.
Code: `models/war.py` (fit, projection, validation), `analysis/war.py` (module `war`), `viz/war.py`, `viz/video/war.py`, `tests/test_war.py` (17 tests).
Saved numbers: `models/data/war_params.json`, `models/data/pwar_ipl_2027.csv` (step 5 joins it to `reference/ipl_contracts.csv` on `cricsheet_name`; 239 of the 278 contract rows match, the rest have no Cricsheet name or no T20 ball since 2025).
Rebuild: `.venv\Scripts\python -m cricket_analytics.models.war` (about 30 s). Re-run the validation tables below: `... models.war --validate` (about 40 s).

## Headline (read this first)
1. **WAR works as a description.** Summed over a team's most-used XI, realised WAR explains 37% (IPL 2024-26, 30 team-seasons) to 42% (2020-26, 66 team-seasons) of the spread in win share. That is close to the ceiling: win share over 14 matches is itself mostly luck (spread across teams 0.135, pure coin-flip noise would give 0.134).
2. **pWAR is a weak predictor and I will not oversell it.** It beats the simple baselines for **bowlers** (r 0.32 vs 0.19 for last season's WAR and 0.15 for last season's wickets) but **not for batters** (r 0.06; last season's WAR 0.09, runs 0.02, "predict the league average" is as good). At **team level** nothing predicts win share (pWAR R^2 0.3% on 30 team-seasons, 1.5% on 66; last season's win share 1.7% and 0.1%).
3. **The red flag (pWAR collapsing to the average) is real, but it is the data, not an over-shrunk model.** A single season's runs added has a spread of about 20 runs per 100 balls between players (batters and bowlers alike); the part that repeats from one season to the next is about 6 (batters) to 8 (bowlers). So a 200-ball season is about 90% luck. Shrinking hard is the right answer; the test on 2024-26 (below) shows bowling projections are well calibrated (slope 0.93) and batting projections carry no usable signal at all (slope -0.08). Top pWAR is 0.52 (Narine) against realised top seasons of about 2.0.

## 1. Rain-shortened matches in Runs Added
`run_expectancy.ra_state(f)` widens the trust rule for runs added and WAR only (the run-expectancy fit keeps the strict rule). Innings length = balls that side had.
- First innings complete (all overs or all out): full length. First innings stopped early: its length is the balls bowled.
- No D/L label and the chase had the same length: the chase counts with the plain target (first total + 1).
- D/L label: first innings only (the reset target is not stored); the second innings of D/L and awarded matches, no-result matches, and chases longer than the first innings stay out.
IPL gains 37 first innings (+3%) and 12 second innings. Real checks (from the data, Cricsheet):

| check | before | now | real |
|---|---|---|---|
| Bumrah IPL 2024 | 287 balls, 18 wkts, RA +170.4 | **311 balls, 20 wkts**, RA +175.2 | 311 balls in the raw data (ESPN style "about 312"), 20 wkts |
| Kohli IPL 2016 | 590 balls, 860 runs, RA +117.8 | **640 balls, 973 runs**, RA +162.2 | 973 runs (includes the 113* in the D/L match) |

`tests/test_runs_added.py` still passes (19).

## 2. Runs per win (measured)
**Method.** For each IPL team-season: wins above half = (win share - 0.5) x decided matches, regressed through the origin on the **total runs added by everybody on the team** (batting + bowling, all players, centred so the league-average player is 0). Runs per win = 1 / slope. 95% range: bootstrap over team-seasons.
This is the self-consistent choice: the unit WAR uses (runs added) is the unit that is converted to wins. Two independent checks:

| number | runs per win | 95% range | team-seasons | R^2 |
|---|---|---|---|---|
| **IPL 2023-2026 (used)** | **99.3** | 81-125 | 40 | 0.61 |
| cross-check A: mean run margin per match (innings scaled to 120 balls) | 104.9 | 83-137 | 40 | 0.64 |
| cross-check B: step-2 win-probability model, slope of chase win chance per run at a 50% chase | 99.5 | - | - | - |
| IPL 2008-2022 (display of old seasons only) | 91.0 | 77-107 | 126 | 0.51 |
| cross-check A, 2008-22 | 82.7 | 73-96 | 126 | 0.57 |

Plausible: three separate routes land at 99-105 for the Impact Player era. (The old worker's 105 and 84 were check A; I switched to the runs-added version because it is the unit WAR consumes.) Seasons used: 2023, 2024, 2025, 2026.
Sanity scale: 100 runs added = one win = about 7 runs of margin per match. A +100 run season (Kohli 2016, Buttler 2022) = about 1.8 wins; the best season on record is about 2.4 (Russell 2019, B Kumar 2026).

## 3. Replacement level (measured, with a sensitivity check)
**Method.** Replacement = the runs added per ball of players who were *outside their team's top 11* (by matches played, then balls) in the previous season, measured in the next season. (Using the next season keeps the group from being picked by the results being measured.) Bat per ball faced, bowl per ball bowled. Capped at 0: replacement is never better than the average player.

| variant | era | bat, runs per 100 balls (SE) | bowl, runs per 100 balls (SE) | WAR of a regular (400 bat / 288 bowl balls) |
|---|---|---|---|---|
| **next season, outside top 11 (used)** | 2023+ | **+1.0 (5.0), used 0.0** | **-3.3 (3.5)** | +0.04 / -0.10 |
| next season, outside top 11 | pre-2023 | -3.1 (1.8) | -1.0 (1.3) | -0.12 / -0.03 |
| next season, outside top 13 | 2023+ | -3.5 (6.1) | -3.7 (3.7) | -0.14 / -0.11 |
| same season, outside top 11 | 2023+ | -21.4 (4.1) | -14.3 (2.5) | -0.86 / -0.41 |
| same season, outside top 13 | 2023+ | -27.9 (4.4) | -21.4 (2.6) | -1.12 / -0.62 |

Reading: the used definition puts replacement within about 0.1 win of the league average, so **WAR is close to runs added / 99**. The defensible alternative (same season) is far lower and shifts every regular's WAR up by 0.4-1.1 wins. They disagree because the same-season group contains players dropped for playing badly (biased low) while the next-season group contains only players who got another IPL season (biased high). I kept the next-season version (the previous worker's choice, and the one not picked by the outcome) and flag it: **replacement level is the least certain input to WAR.** It shifts all players by a nearly constant amount per ball, so rankings of regulars barely change; comparisons with part-timers do.
Seasons used: players benched in 2023-25, measured 2024-26 (2023+); benched 2008-21, measured 2009-22 (pre).

## 4. WAR per player-season
WAR = (runs added - replacement rate x balls) / runs per win of that IPL era. Batting and bowling added together (fielding not included, no defined fielding credit). Runs added = scoring part (runs and balls used up) + wicket part. Each league-season is centred so the average player is exactly 0 per ball.
Module: `cricket run war --competition ipl --season 2024 [--role batting|bowling] [--components true] [--player X]`; `--view projected` for IPL 2027.
Sample checks (IPL, all roles): 2024 top = Bumrah 1.92, Narine 1.39 (0.61 bat + 0.78 bowl), Pooran 0.93. 2022 batters: Buttler 1.81 first. All-time top seasons: Russell 2019 2.37, B Kumar 2026 2.24, Pant 2018 2.22, de Villiers 2016 2.06, Bumrah 2020 2.06, Rashid 2020 2.03, Suryavanshi 2026 2.03.

## 5. The projection (pWAR, IPL 2027)
**Rule followed (owner's):** IPL evidence = 2023+ only. Older IPL seasons were tested as down-weighted evidence and did **not** help (below), so weight 0.
**Form (Marcel-style, per role and per part).** For a player: projected scoring part per ball = (sum of his scoring runs added over the last 5 seasons) / (balls + k1); same for the wicket part with k2. IPL seasons since 2023 count in full; other leagues' balls (men's BBL, PSL, CPL, SA20, Hundred, Blast, T20I) count at weight a, with their rate multiplied by league-strength factor s. Expected balls = regression on his last three seasons' IPL balls. pWAR = (projected rate - replacement) x expected balls / runs per win. No age data exists in the database, so **no age adjustment**.
**Constants, learned only from past seasons.** k, a and s are noise-to-signal ratios, learned by grid search on every IPL season from 2018 up to the one before the target (for 2027: 2018-2026). For a target season after 2023 the evidence used is IPL 2023+ only; for pseudo-targets up to 2023 all earlier IPL years serve (otherwise there would be too few targets to learn from). The projection of IPL 2027 itself uses IPL 2023-2026 only.

Fitted for 2027:

| | a (other leagues) | s (strength) | k scoring (balls) | k wicket (balls) |
|---|---|---|---|---|
| batters | 1.0 | 0.5 | 3000 | 6000 |
| bowlers | 1.0 | 1.0 | 1600 | 1600 |

k = 3000 balls means a 600-ball batter keeps 17% of his own rate. That sounds extreme but matches the data: talent spread (6 runs per 100 balls) vs noise (20) gives reliability n / (n + k) with k of the order 1500-3000 balls. A first-pass fit on 2024-26 only gave nearly the same k (3000 / 1600).

### Do the extra ingredients help? (loss = ball-weighted RMSE of projected vs realised runs added per ball, IPL 2024-26 targets, players with 60+ balls; lower is better)
| variant | batters | bowlers |
|---|---|---|
| everybody is average | 0.2098 | 0.2242 |
| IPL 2023+ only | 0.2072 | 0.2204 |
| **+ other leagues (used)** | **0.2069** | **0.2179** |
| wicket part also uses older IPL (weight 0.5) | 0.2070 | 0.2161 |
| wicket part also uses older IPL (weight 1.0) | 0.2072 | 0.2162 |
| scoring part only, wicket part dropped | 0.2080 | worse than average |

Older IPL seasons for the whole projection (pre_w), paired bootstrap of the loss difference vs weight 0 (negative = helps): batters +0.0001 to -0.0001 (95% range about -0.002 to +0.002), bowlers -0.0010 / -0.0018 / -0.0023 for weights 0.25 / 0.5 / 1 with ranges that all include 0 (e.g. [-0.0079, +0.0023] at weight 1). **Not adopted: the gain is inside the noise.** Other leagues help bowlers a bit (0.2204 to 0.2179) and batters hardly at all. Shrinking the wicket part toward a longer run helps bowlers by a similar noise-sized amount; I did not adopt it. (Differences of 0.001 are 0.5% of the loss: all of these choices are close to coin-flips; do not read much into which one is picked.)

## 6. Out-of-sample validation (the key part)
For each target season t = 2024, 2025, 2026, the constants are learned from seasons before t, the projection uses data before t only, and it is compared with the realised WAR of the same player in t. Runs per win and replacement level use the all-years values (a scale change only: correlations do not depend on it). Players: at least 100 balls in the role in t and some IPL ball of that role in t-1 (so every baseline is defined). n = 160 batter-seasons, 147 bowler-seasons.

| role | n | r pWAR | r last season WAR | r last season runs / wickets | MAE pWAR (wins) | MAE last WAR | MAE last WAR best-rescaled | MAE "average = 0" |
|---|---|---|---|---|---|---|---|---|
| batting | 160 | 0.06 | 0.09 | 0.02 | 0.337 | 0.474 | 0.340 | 0.344 |
| bowling | 147 | **0.32** | 0.19 | 0.15 | **0.358** | 0.483 | 0.369 | 0.380 |

Spearman: batting 0.06 / 0.06 / 0.02; bowling 0.21 / 0.13 / 0.12.
By year (r pWAR / r last WAR): batting 2024 0.03 / 0.07, 2025 0.33 / 0.26, 2026 -0.10 / -0.03; bowling 2024 0.28 / 0.34, 2025 0.30 / 0.27, 2026 0.36 / 0.03. (About 50 players a year: each r has a range of roughly +/-0.28. Only the bowling-2026 gap and the pooled bowling gap are bigger than that noise, and the pooled one is only just.)
Rate level (projected runs added per 100 balls vs realised, and vs last season's strike rate for batters / economy for bowlers): batters r 0.11, 0.11, -0.08 vs SR 0.04, 0.02, 0.01; bowlers 0.08, 0.21, 0.34 vs economy 0.28, 0.33, 0.07.
Calibration (realised rate regressed on projected rate, ball-weighted, 2024-26): bowlers slope 0.93 (well calibrated; the top fifth of projections, +8.1 per 100 balls, actually delivered +11.9, so top bowlers are, if anything, under-projected); batters slope -0.08 (no signal; the top fifth of batting projections, +7.5, delivered +4.4, while the bottom fifth, -0.1, delivered +9.2).

### Team level: sum of pWAR of each team's most-used XI vs actual win share
| set | n team-seasons | predictor | r | R^2 |
|---|---|---|---|---|
| IPL 2024-26 | 30 | **pWAR (XI)** | 0.06 | 0.003 |
| | | last season's WAR (XI) | -0.01 | 0.000 |
| | | last season's win share | -0.13 | 0.017 |
| | | realised WAR of that XI (ceiling) | 0.61 | 0.368 |
| IPL 2020-26 (2020-23 use all IPL years as evidence) | 66 | **pWAR (XI)** | 0.12 | 0.015 |
| | | last season's WAR (XI) | -0.02 | 0.000 |
| | | last season's win share | -0.02 | 0.001 |
| | | realised WAR of that XI (ceiling) | 0.64 | 0.415 |

Honest R^2: 0.3% (n = 30) and 1.5% (n = 66). pWAR is positive and ahead of the baselines at team level, but it explains almost nothing; an IPL season is 14 coin-flip-ish matches (spread of win share 0.135, pure luck gives 0.134). Rosters change every year and 14 games is too little for any preseason model to separate teams. The XI is the roster that actually played (known only after the season), so even this is the generous version.

## 7. Top 20 pWAR, IPL 2027 (what each rests on)
Evidence: IPL 2023-2026 (full weight; 2022 and earlier ignored) plus men's T20 leagues and T20Is of 2022-2026 at weight 1.0 (bowling) / rate x 0.5 (batting). Expected balls: IPL 2024-26 balls.
| # | player | pWAR | bat | bowl | exp balls bat/bowl | proj. runs added per 100 balls bat/bowl | IPL balls 2023+ |
|---|---|---|---|---|---|---|---|
| 1 | SP Narine | 0.52 | 0.02 | 0.51 | 70 / 248 | +2.2 / +17.0 | 1663 |
| 2 | JJ Bumrah | 0.41 | 0.00 | 0.41 | 12 / 238 | -0.3 / +13.9 | 885 |
| 3 | H Klaasen | 0.38 | 0.38 | 0.00 | 318 / 0 | +12.0 / - | 1205 |
| 4 | B Kumar | 0.37 | 0.00 | 0.37 | 29 / 295 | +0.2 / +9.0 | 1465 |
| 5 | Rashid Khan | 0.36 | 0.01 | 0.35 | 43 / 267 | +2.8 / +9.5 | 1514 |
| 6 | Mohammed Siraj | 0.30 | 0.00 | 0.30 | 18 / 293 | -0.4 / +6.8 | 1368 |
| 7 | Noor Ahmad | 0.30 | 0.00 | 0.30 | 24 / 239 | -1.0 / +9.1 | 1138 |
| 8 | CV Varun | 0.29 | 0.00 | 0.29 | 10 / 213 | -0.9 / +10.2 | 1178 |
| 9 | Abhishek Sharma | 0.27 | 0.28 | 0.00 | 233 / 39 | +11.8 / -4.5 | 1105 |
| 10 | JR Hazlewood | 0.27 | 0.00 | 0.27 | 7 / 217 | -0.2 / +8.9 | 631 |
| 11 | B Sai Sudharsan | 0.25 | 0.25 | 0.00 | 392 / 0 | +6.3 / - | 1567 |
| 12 | Kuldeep Yadav | 0.24 | 0.00 | 0.25 | 26 / 195 | -0.7 / +9.1 | 1206 |
| 13 | SA Yadav | 0.23 | 0.23 | 0.00 | 191 / 0 | +12.2 / +0.1 | 1150 |
| 14 | Tilak Varma | 0.23 | 0.23 | 0.00 | 221 / 12 | +10.1 / +0.9 | 991 |
| 15 | Ishan Kishan | 0.22 | 0.22 | 0.00 | 267 / 11 | +8.1 / -0.1 | 1096 |
| 16 | JC Buttler | 0.22 | 0.22 | 0.00 | 289 / 0 | +7.5 / - | 1185 |
| 17 | KL Rahul | 0.21 | 0.21 | 0.00 | 304 / 0 | +6.9 / - | 1324 |
| 18 | V Kohli | 0.21 | 0.21 | 0.00 | 366 / 0 | +5.7 / +0.1 | 1795 |
| 19 | Shubman Gill | 0.20 | 0.20 | 0.00 | 367 / 0 | +5.5 / - | 1673 |
| 20 | MR Marsh | 0.20 | 0.19 | 0.00 | 274 / 16 | +6.9 / -0.9 | 1032 |
(Players' team in 2027 is not used: pWAR is per player; the league's sum of positive pWAR is 14.0 wins, 28 players above 0.15.)

## 8. Why our scale differs from ipltradevalues (Jaiswal 2.08) - explanation, not forced
Our realised numbers are the same size as theirs for a great season (Bumrah 2024 1.92, Suryavanshi 2026 2.03, Buttler 2022 1.81, whole-season top 2.4). A *projected* 2.08 would need a rate far more extreme than the data supports: with talent spread of 6 to 8 runs per 100 balls, even a +2 SD player projects to about +15 runs per 100 balls = 0.6 wins over 400 balls. So (guess, their method is not available to us) their figure is either a past-season total relabelled as a projection or is less shrunk than this validation allows. Where scales are comparable (a realised season), ours agree.

## 9. Doubts
1. **Batter pWAR has no demonstrated skill**: out-of-sample r 0.06, calibration slope -0.08. Treat the batting part of pWAR as "league average, plus a small tilt". Bowler pWAR is modestly informative (r 0.32, 147 cases, three seasons).
2. **Runs per win** 99 has a wide range (81-125, 40 team-seasons), though three methods agree on 99-105. A 20% error scales every WAR by 20%.
3. **Replacement level** depends on the definition (next-season group: about the league average; same-season group: -0.4 to -1.1 wins). I used the first. A different choice shifts everyone's WAR by a near constant, mostly affecting part-timers.
4. **Hyperparameters were chosen on seasons that include the test seasons for the final 2027 model**, but the validation tables refit them for each target using earlier seasons only. Remaining mild optimism: the grid is large (hundreds of combinations) against differences of 0.5% in loss; the validation's own choices (min 100 balls, "returning" players, the 5-year window, WINDOW and KGRID) were set before looking at results but are still choices.
5. **Only 3 target seasons, about 50 players each.** Per-year r values swing by +/-0.28. Pooled bowler advantage (0.32 vs 0.19) is a real but marginal difference.
6. **Expected balls** are a regression on last three IPL seasons; injuries, auction moves and role changes (impact substitutes) are not modelled. A player with no IPL ball since 2023 has 0 expected balls and pWAR 0 even if his rate looks good (columns `bat_rate` / `bowl_rate` carry the rate; step 5 can use its own playing-time assumption). 39 contract rows have no match in the file (no Cricsheet name or no T20 ball in 2025-26).
7. **Team labels:** WAR is a sum over teams within a season for movers; the team filter shows the player's WAR with that team only.
8. **Wicket part and context:** runs added gives a dismissal a large negative; the "scoring part" is more repeatable than the wicket part (step 1: 0.25 vs 0.25 for batters but they offset). Not re-opened here beyond the tests above.
9. No fielding WAR, no age, no league adjustment beyond the 0.5 batting strength factor; other-league ratings are pooled into one block.
10. `pyproject.toml` `package-data` still does not list `models/data/*.json` / `*.csv` (told not to edit): works in this editable install, a wheel build would miss `war_params.json` and `pwar_ipl_2027.csv`.
