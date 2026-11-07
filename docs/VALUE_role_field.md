# WAR: main role and fair fielding

All numbers measured by us (Cricsheet DuckDB, read-only), IPL. Code: `models/war.py` (`main_role`, `fair_field`, `fit_field_fair`), `analysis/war.py`. Params: `field_fair` in `models/data/war_params_v2.json`.

## 1. Main role (so a pure bowler is not judged by his batting)
- Rule: bowling share = bowl balls / (balls faced + balls bowled), per player-season. Under 20% = **batter**, over 80% = **bowler**, in between = **all-rounder**.
- Where 20% comes from: of 2,038 player-seasons with 100+ balls, 659 have a share under 2% and 436 over 95%; the middle (shares 5%-40%) is flat at about 25-40 per 5%-bin and only fills in beyond 40%. 20/80 cuts the two big clusters off from that flat middle, symmetric for both sides.
- `main_war` = bat WAR (batter), bowl WAR (bowler), bat + bowl (all-rounder). Fielding is not in it. `war` (total = bat + bowl + field) is still there and keeps its meaning. The war view sorts by `main_war`; the chart and the video use it. Keeper status is not a role here (keepers are batters), it only decides the fielding group.
- Bumrah, IPL 2023-26: batting -0.08 wins, bowling +3.10. main_war = 3.10 (bowler), total 2.98.

## 2. Fair fielding
Before: every catch gave the fielder 20% of the wicket value, so keepers and slip fielders got more simply by position. Now (default; `fair_fielding=false` gives the old raw credit):
- Catches + stumpings per match are compared with the average of the player's **group**, per season: keepers (yes / sometimes in `player_overrides.csv`) with keepers, everyone else with everyone else. Run-outs are compared with the league average per match. "Matches" = matches he batted or bowled in (substitute-only fielders get no credit).
- Each part is shrunk toward 0 by its season-to-season reliability, measured on IPL players with 6+ matches in both of two consecutive seasons:

| part | consecutive-season correlation | pairs | weight used |
|---|---|---|---|
| catches/stumpings, non-keepers | 0.41 | 1,131 | m / (m + 16.1), m = matches (13 matches: 0.45) |
| catches/stumpings, keepers | 0.28 | 161 | m / (m + 22.3) (13 matches: 0.37) |
| run-outs (credit per match) | about 0.07 | all | 0.07 flat |

- k = matches at which noise equals signal (catch counts are Poisson, so noise per match = their mean; signal = covariance between seasons). Catches are partly repeatable (position, role), run-outs are almost pure luck, hence nearly zero weight. The 20% catch share is unchanged: the data cannot test it.
- Result: the spread of team-level fielding sums falls from 0.40 to 0.10 wins. Fielding WAR is now within about +-0.15 per season for everyone (Kohli 2023-26: 0.65 raw, 0.08 fair).
- Side effect: average fielding credit is now 0, so total WAR of nearly everybody falls slightly (Kohli 2.91 -> 2.35). Differences between players, not the level, are the point.

## 3. Does it still describe team seasons? (IPL 2023-26, 40 team-seasons, wins above half vs summed WAR, method of VALUE_war_fix.md)

| fielding in total WAR | r | slope | mean miss (wins) | replacement team |
|---|---|---|---|---|
| raw v2 (before) | 0.803 | 0.98 | 0.93 | 36% |
| centred only, no shrink | 0.796 | 1.00 | 0.95 | - |
| **fair, shrunk (now)** | **0.774** | 1.04 | **1.02** | 43% |

- Slightly **worse** (r -0.03, miss +0.09 wins), within noise for 40 team-seasons (r has a standard error of about 0.07), but the direction is consistent: raw fielding carries real team information that a per-player shrink removes (good bowling teams get more catches, which is partly luck of the bowler but also what wins matches). Team sums describe teams; the shrink is for judging players. I kept the shrink because the task asks for it and the player-level reliability is what matters for rating one player; `fair_fielding=false` restores the raw version.
- Not refitted: pWAR (uses raw fielding), trade and auction models (call `war_table` without appearances, so they still use the raw v2 total). Replacement level stays -6.

## 4. Top 10 by main_war, IPL 2023-26 summed (every season counted, role from pooled balls, 300+ balls)
Batters (main_war = bat WAR): Klaasen 4.72, Sai Sudharsan 3.14, KL Rahul 2.66, SA Yadav 2.53, Shubman Gill 2.44, Tilak Varma 2.36, Kohli 2.27, Pooran 2.23, V Suryavanshi 2.10, Patidar 1.89.

Bowlers (main_war = bowl WAR): Bumrah 3.10, Varun Chakravarthy 2.69, B Kumar 2.41, Boult 2.20, Siraj 1.98, Rashid Khan 1.81, Noor Ahmad 1.66, Kuldeep 1.34, Hazlewood 1.22, Malinga 1.01.

## 5. Before / after (IPL 2023-26 summed; before = raw v2 total, after = main_war and fair total)

| player | role (pooled) | bat | bowl | field raw -> fair | total before -> after | main_war |
|---|---|---|---|---|---|---|
| Bumrah | bowler | -0.08 | 3.10 | 0.16 -> -0.04 | 3.19 -> 2.98 | **3.10** |
| Hardik Pandya | all-rounder | -0.58 | -1.22 | 0.23 -> -0.02 | -1.59 -> -1.83 | -1.81 |
| Klaasen | batter | 4.72 | 0 | 0.48 -> -0.03 | 5.21 -> 4.69 | 4.72 |
| Narine | all-rounder | -0.34 | 2.61 | 0.42 -> 0.03 | 2.69 -> 2.30 | 3.30 (sum of per-season roles) |
| Kohli | batter | 2.27 | 0 | 0.65 -> 0.08 | 2.91 -> 2.35 | 2.27 |
| MS Dhoni (keeper) | batter | 0.82 | 0 | 0.32 -> 0.01 | 1.15 -> 0.83 | 0.82 |
| Sanju Samson (keeper) | batter | 1.38 | 0 | 0.52 -> -0.01 | 1.91 -> 1.37 | 1.38 |

Keepers lose the most raw fielding credit (Dhoni 0.32, Samson 0.52 -> about 0), which was the position effect. Narine's main_war is higher than bat + bowl because in seasons where he bowled much more than he batted he is a "bowler" and his batting is left out.

## Limits
- No fielding position and no drop data exist, so deep fielders' saves stay invisible and field_war is a rough guide, not a skill rating.
- Matches = matches batted or bowled; a keeper who neither bats nor bowls is under-counted (rare).
- "Sometimes" keepers (6 players) count as keepers all seasons.
