# Player worth: which few metrics describe a player (2026-11-07)

All numbers **measured by us** from our Cricsheet DuckDB (read-only). Code: `models/worth.py` (rerun the selection: `python -m cricket_analytics.models.worth select`), module `player_worth` (`analysis/player_worth.py`, chart `viz/player_worth.py`), tests `tests/test_worth.py`. Saved: `models/data/worth_selected.csv` (every candidate with its numbers, `kept` marks the panel).

## Decision (read first)
1. **Batting panel (8): strike rate in the middle overs, balls per boundary, balls per six, dot-ball %, strike rate vs spin, strike rate vs pace, balls per dismissal in the middle overs, rotation % in the middle overs. Bowling panel (5): balls per boundary conceded, dot-ball %, middle-over economy, dot-ball % and balls per boundary conceded against left-handers.** The data supports only about three independent bowling signals; the two left-hander items are a split of the same two skills, not new ones.
2. **Repeatability is modest everywhere.** Season-to-season r is 0.2-0.6 for the best candidates (median over all candidates 0.21-0.25), so every number is shrunk toward the league mean and shown with its balls.
3. **Not kept as season-level skill: wickets and runs added per ball.** Bowler wicket rate: season-to-season r 0.02 (k about 1,200 balls); runs added per ball: 0.06 (batters) and 0.19 (bowlers). They matter for winning (r with win probability added 0.5-0.7) but barely repeat, so they are outcomes, not skills. Wickets and runs added stay in the existing modules and in the highlights.
4. **Match-relative versions (minus everyone else in the same match, or minus teammates) did not repeat better** (median season-to-season r 0.18-0.20 vs 0.21-0.25 for the plain version). Subtracting the match removes some of the persistent part along with the noise. So they are used for what they are good at, single-match highlights ("4-0-35-2 in a 260 game", "50 off 25 when the rest scored at 7"), not for the season profile.
5. **Fine bowling types (right-arm fast-medium, left-arm orthodox...) are too thin** to be a metric: 28-80 season pairs and 40-60 balls per player-season. Only pace / spin (batters) and left / right hand (bowlers) are in the panel.

## Method
**Candidates (182 = 112 batting + 70 bowling).** Per player-season, per metric x phase x variant.
- Batting metrics: strike rate, boundary %, six %, dot %, rotation % (1s and 2s as a share of non-boundary balls), dismissal rate, runs added per ball. Bowling: economy, dot %, boundary % conceded, wicket rate, runs added per ball. "Balls per boundary / six / dismissal / wicket" are 1 / the rate, so they share their rate's numbers.
- Phases: all, powerplay (overs 1-6), middle (7-15), death (16-20).
- Variants: plain; minus everyone else in the same match and phase (both sides); minus same-innings teammates; batters vs pace / vs spin and vs each of the 10 reviewed bowling types; bowlers vs left- / right-handers. Types and hands come only from `player_overrides.csv`.
- Data: ball-by-ball for 6-ball T20 matches with a trusted target and a result (the `wpa` data): IPL 2023-26 is 281 matches, 67,880 balls. Checked on BBL and PSL (last 4 seasons each).

**Reliability.** Every metric is a mean of one per-ball value, so one definition fits all: **k** = balls at which reliability is 0.5, by method of moments (within-player variance / between-player variance, from player-seasons with 100+ balls for a whole-season metric, 30+ for a slice). Shrunk value = (balls x his rate + k x league rate) / (balls + k). Also the plain **season-to-season r** of the raw rates for the same player in consecutive seasons (IPL 155 pairs for a middle-overs metric; BBL and PSL checks). k measures noise inside a season; season-to-season r also sees changes between seasons, so it is the lower and honest number. The score uses the season-to-season r, pooled over IPL, BBL, PSL weighted by pairs.

**Relevance.** Correlation of the shrunk metric with the player-season's win probability added per ball (`wpa`, same phase, same balls), pooled over the three leagues. Out-of-sample check: the same metric in season t against win probability added per ball in t+1 (`r_next_wpa`; IPL).

**Score and selection.** score = pooled reliability (floored at 0) x pooled relevance. Walk down the ranking, keep a candidate unless |r| >= 0.8 with an already kept one across player-seasons (same cluster), skip a second view of a metric that only differs by "all phases" vs one phase, and require pooled reliability >= 0.15, relevance >= 0.25, 100+ player-seasons and 80+ season pairs. Only plain and pace/spin/hand variants are paneled. The thresholds are my choice (a guess, not fitted); with 0.65 instead of 0.8 the panel shrank to about half (measured in a trial run with slightly stricter floors), so the panel is "the independent signals plus the nearest useful splits".

## Ranking (top, pooled over IPL 2023-26, BBL, PSL)
| candidate | k (balls) | season-to-season r IPL / BBL / PSL | r with WPA | r with next-season WPA | score |
|---|---|---|---|---|---|
| bat sr middle | 81 | 0.46 / 0.38 / 0.13 | 0.60 | 0.07 | 0.22 |
| bat boundary % middle (clone of sr, dropped) | 93 | 0.53 / 0.37 / 0.16 | 0.54 | 0.06 | 0.21 |
| bat boundary % all | 98 | 0.49 / 0.44 / 0.02 | 0.45 | 0.05 | 0.17 |
| bat six % all | 87 | 0.38 / 0.41 / 0.18 | 0.43 | 0.05 | 0.15 |
| bat dot % all | 130 | 0.48 / 0.40 / 0.03 | -0.36 | -0.10 | 0.15 |
| bat dismissal rate middle | 568 | 0.25 / 0.07 / 0.22 | -0.57 | -0.12 | 0.11 |
| bat rotation % middle | 68 | 0.51 / 0.21 / 0.10 | 0.22 | 0.13 | 0.09 |
| bat runs added per ball (dropped) | 959 | 0.06 / 0.27 / -0.17 | 0.60 | -0.01 | 0.04 |
| bowl boundary % all | 134 | 0.60 / 0.35 / 0.45 | -0.50 | -0.25 | 0.23 |
| bowl dot % all | 103 | 0.52 / 0.50 / 0.27 | 0.45 | 0.29 | 0.21 |
| bowl economy all (clone of boundary %, dropped) | 216 | 0.44 / 0.12 / 0.30 | -0.63 | -0.35 | 0.19 |
| bowl economy middle | 160 | 0.27 / 0.14 / 0.10 | -0.68 | -0.25 | 0.13 |
| bowl wicket rate (dropped) | 1,217 | 0.02 / 0.14 / 0.00 | 0.51 | -0.02 | 0.02 |
| bowl runs added per ball (dropped) | 795 | 0.19 / -0.03 / 0.16 | 0.71 | 0.18 | 0.08 |

Full table: `worth_selected.csv` (all 182 rows; columns `r_s2s`, `r_s2s_bbl`, `r_s2s_psl`, `rel_pool`, `relevance_pool`, `score`, `kept`, `max_r_kept`).

**Incremental check (ridge, lambda 10, standardised, shrunk kept metrics on player-season WPA per ball, IPL, 224 batter-seasons / 184 bowler-seasons):** batting R2 0.43; largest betas boundary % +0.27, dismissal rate -0.24, six % +0.21, dot % -0.19, sr vs pace +0.10; strike rate in the middle overs only +0.05 once boundary % is in (it is the same information). Bowling R2 0.50: dot % +0.45, boundary % -0.34, middle economy -0.11. R2 here is in-sample for the same season.

## The kept metrics, one paragraph each
**Batting**
- **Strike rate, middle overs (7-15).** Runs per 100 balls where most balls are faced; the strongest single link to win probability (r 0.60), k 81 balls. Phase chosen over the all-phase version (0.15 vs 0.22 score) because the middle overs are where batters differ most and the all-phase number mixes a finisher's death overs with an opener's powerplay. Boundary % in the same overs is a clone (|r| above 0.8).
- **Balls per boundary (all phases).** Boundary % of balls faced, k 98. The best repeating scoring-power measure (season-to-season 0.49 IPL, 0.44 BBL); the ridge gives it the largest weight after the others are in.
- **Balls per six.** k 87. Adds the big-hitting part not already in boundary % (it passed the 0.8 cluster test and has its own weight in the ridge, +0.21).
- **Dot-ball %.** Share of balls faced with no run, k 130. Lower is better (r with WPA -0.36). Repeats about as well as boundary % in IPL and BBL.
- **Strike rate vs spin / vs pace.** k 70 / 109, season-to-season 0.36 and 0.22 (IPL; spin 0.51 BBL). Keeps the type split Samar cares about; the bowler's type is only from the reviewed list, bowlers without a label are left out of the split.
- **Balls per dismissal, middle overs.** Dismissal rate, k 568, so it needs about 570 balls to be half skill; the weakest repeater of the kept ones (0.25 IPL), kept because it is the only "safety" signal and carries a large share of win relevance (r -0.57) and a big ridge weight (-0.24). Read it with its own_share (often 0.4-0.6).
- **Rotation %, middle overs.** 1s and 2s as a share of non-boundary balls, k 68; repeats well (0.51 IPL) but explains less of winning (r 0.22). Kept as the style marker (anchor vs hitter), not as a value measure.

**Bowling**
- **Balls per boundary conceded.** Boundary % of deliveries, k 134, season-to-season 0.60 (IPL), 0.35 BBL, 0.45 PSL: the most repeatable bowling skill in the data, and next season's WPA correlates -0.25 with it.
- **Dot-ball %.** k 103, season-to-season 0.52 / 0.50 / 0.27; best predictor of next-season WPA (0.29).
- **Economy, middle overs.** k 160; the strongest link to winning (r -0.68) but repeats less (0.27), so it is kept only for the middle overs where economy is a pure control measure; the all-phase economy is a clone of boundary %.
- **Dot-ball % and boundary % against left-handers.** Splits, k 68 and 130; kept as "does he have a hand-specific problem" markers, not independent skills (they sit in the panel because their correlation with the all-batter versions is below 0.8, which with a median of 57 balls per player-season is partly noise). Right-hander versions did not qualify.

## Dropped, and why
- **Runs added per ball (bat and bowl).** Reliable only after 800-1,000 balls (k 959 / 795); season-to-season 0.06 / 0.19. It is the right summary of what happened (r with WPA 0.6-0.7), the wrong summary of what will happen. Existing `runs_added` module keeps it.
- **Wicket rate (bowling).** k 1,200+ and season-to-season 0.02; most of it is luck once phase and wickets-down are accounted for (as VALUE_m2 found).
- **Death-over and powerplay variants** of every rate: 30-60 balls per player-season, so they repeat poorly (season-to-season r: death-over economy 0.04, dismissal rate 0.08, strike rate 0.16). They are still computed on request (`phase` filter) and appear in the table.
- **Match-relative and teammate-relative variants**: see decision 4. Example: bowler dot % relative to the match 0.36 vs 0.52 plain.
- **Fine bowling types** (decision 5).

## Sanity check: 5 players, IPL 2023-26 (value, percentile among peers with 100+ balls, own_share = balls / (balls + k))
| player | metric | value | pctile | |
|---|---|---|---|---|
| V Kohli (bat) | dot-ball % | 27.0 | 97 | few dots, anchor |
| | SR middle / vs spin / vs pace | 137 / 128 / 166 | 38 / 16 / 80 | weak vs spin, quick vs pace |
| | balls per boundary / per six | 4.9 / 17.9 | 44 / 17 | not a big hitter |
| | balls per dismissal (middle) | 29.4 | 98 | rarely out (own share 0.58) |
| H Klaasen (bat) | SR middle / vs spin | 158 / 172 | 90 / 92 | |
| | dot-ball % | 24.2 | 100 | |
| | balls per dismissal (middle) | 32.6 | 99 | |
| HH Pandya (bat) | balls per boundary / six | 5.3 / 14.8 | 24 / 33 | |
| | SR vs spin / vs pace | 149 / 144 | 71 / 21 | |
| SP Narine (bat) | SR middle / balls per six | 170 / 8.8 | 96 / 93 | |
| | dot-ball %, balls per dismissal | 39.2, 18.5 | 2, 2 | all-out hitter (own share 0.18) |
| JJ Bumrah (bowl) | balls per boundary / dot % | 6.9 / 39.0 | 98 / 97 | |
| | middle economy | 7.19 | 100 | |
| | vs left-handers dot % / boundary | 40.7 / 7.5 | 99 / 100 | |
| SP Narine (bowl) | balls per boundary / middle economy | 7.8 / 7.50 | 100 / 99 | 1,143 balls, own share 0.9 |
| HH Pandya (bowl) | balls per boundary / dot % / middle economy | 4.5 / 30.5 / 8.7 | 29 / 45 / 65 | average to below, worst vs left-handers (5th) |

Does it match cricket sense? Yes on the large calls: Bumrah and Narine as elite bowlers, Klaasen as the cleanest middle-overs hitter (best dot-ball % and a high strike rate vs spin), Kohli as a low-risk anchor weaker vs spin than vs pace, Narine the batter as all-or-nothing, Hardik as a modest bowler. Two things to read carefully: (1) Kohli's 98th percentile for balls per dismissal is partly because the number is pulled hard toward the mean (own share 0.58); (2) a 1,100-ball bowler like Narine is solid, but Bumrah's middle-over economy rests on only 243 balls (own share 0.60), because he bowls mostly in the powerplay and death. Hardik's left-hander split (5th percentile, 160 balls) is a small sample, so treat it as a flag, not a verdict.

## Limits
- Season-to-season r has about +/-0.09 uncertainty at 150 pairs (guess from the usual 1/sqrt(n) rule); gaps of 0.05 between candidates are within noise, so the order inside the panel is not meaningful, only panel vs not-panel.
- Reliability is "at typical balls" (the median qualified player-season), so a phase metric looks worse than the same skill over a whole season.
- Win probability added uses our win-probability model, so relevance inherits its errors; both batters and bowlers are credited the same balls from opposite sides.
- Non-striker run outs are not in a batter's dismissal rate; the bowling economy is per delivery (wides included) and converted to per legal ball for display.
- Percentiles are against all batters / bowlers in scope with enough balls, not split by batting slot or bowler type (the roles in the data are guesses, and Samar's rule keeps guesses internal).

## worth v2 (2026-11-09): phase-aware, wickets back

Problem: the trade tool's old default basis "worth" rated Arshdeep Singh -0.07 WAR (recent +0.28) and Hardik Pandya +0.13 (recent -0.31). The kept bowling metrics had no wicket-taking and used middle-over economy for every bowler. The default is back to `recent`; `worth` and `worth2` stay selectable.

Method (`backtest.worth2_pred`, basis name `worth2`): from the league-season-phase table (IPL rows, 2016 to the cut year), per player and phase: runs per ball (SR / economy), wicket rate, runs added per ball. Each is shrunk toward the league rate IN THAT PHASE (runs k = 150 balls, set not fitted; wicket k fitted per phase by method of moments with binomial variance, clamped 400-3000; runs-added k = the backtest's K_SHRINK / 3). Then a mean over phases weighted by the player's OWN share of balls in the phase (expected usage), so a powerplay + death bowler is judged against powerplay and death norms. Same for batters. Three features per role go to the same ridge (lambda 10), refitted on target years 2019..X only, with the same expected-balls rule as `worth`. First attempt (raw phase rates, not minus the phase rate) was wrong: it still penalised death bowlers; fixed before the numbers below.

Limits: no dot% / boundary% (the phase table has only runs, wickets, runs added), so v2 has fewer features than v1. The ridge gives the wicket rate almost no weight: wicket rate does not predict next-season runs added per ball in this sample (r -0.05 on 517 bowler-seasons). Economy relative to phase carries the signal (r -0.24).

Results (IPL 2024-26 targets, pooled):

| Test | recent | worth | worth2 |
|---|---|---|---|
| backtest Spearman, total (n 355 common) | 0.135 (ipl3) | 0.202 | 0.170 |
| bat_rate | 0.116 (ipl3) | 0.100 | 0.107 |
| bowl_rate | 0.164 (ipl3) | 0.305 | 0.285 |
| XII test, r(XII value, wins), 30 team-seasons | -0.114 | 0.236 | 0.224 |
| XII test, r(XII actual WAR, wins) | 0.487 | 0.704 | 0.754 |

(`recent_value` is only scored on total: 0.135 on the common pool, 0.116 on all.) Rule set before the run: worth2 becomes the default only if it beats recent on the XII test AND is not worse than worth on the backtest AND the sanity table has no glaring failures. It beats recent on the XII test and is better than worth on XII actual WAR, but is worse than worth on the backtest (total, bowl_rate), so the default stays `recent`.

Sanity (WAR, next season value; recent / worth / worth2): Arshdeep Singh 0.28 / -0.07 / 0.04, Bumrah 0.97 / 0.37 / 0.70, Hardik Pandya -0.31 / 0.13 / 0.07, Deepak Chahar 0.01 / 0.06 / 0.08, Varun Chakravarthy 0.61 / 0.21 / 0.25, Rashid Khan 0.49 / 0.39 / 0.52, Klaasen 1.07 / 0.59 / 0.38. Arshdeep is no longer below replacement but is still far under recent: his 2026 economy was poor in all three phases, and wickets carry no weight.

Trade MI gives Hardik for PBKS Arshdeep (delta WAR, 10-90 range): recent MI +0.21 (-0.25 to 0.63), PBKS -0.37 (-0.76 to 0.09); worth MI -0.16 (-0.79 to 0.32), PBKS +0.13 (-0.17 to 0.49); worth2 MI -0.03 (-0.63 to 0.45), PBKS +0.03 (-0.45 to 0.63). Every range spans zero.
