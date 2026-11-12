# Death execution and dropped catches (2026-11-13)

Data: Cricbuzz commentary joined to Cricsheet, IPL 2017-2026, 156,367 balls with commentary. Runs and wickets always come from Cricsheet. Code: `models/death_execution.py`, `models/drops.py` (tests: `tests/test_death_execution.py`, `tests/test_drops.py`). CSVs in `data/external/commentary/` (`death_execution.csv`, `drops_*.csv`, gitignored).

**Verdict: drop both as predictors. Keep drops as a descriptive fielding-cost number; keep execution only as a descriptive pace-bowler stat.** Neither adds measurable prediction beyond what we already have.

## A. Death execution (overs 16-20)
Execution = yorkers / (yorkers + full tosses) on legal death balls with a length tag. Shrunk toward the league rate (0.481, prior strength k = 48 balls, fitted from the data by method of moments). 898 bowler-seasons. League numbers (3,089 yorkers, 3,330 full tosses): runs per ball 1.28 on yorkers, 2.05 on full tosses, 1.70 on other lengths.

| check (pairs with >= 30 death balls in both seasons) | result | n |
|---|---|---|
| Year-to-year correlation, execution (shrunk) | 0.22 | 211 pairs |
| Same, raw (needs >= 1 yorker/full toss both years) | 0.35 | 184 pairs |
| Year-to-year correlation, death economy (runs/ball) | 0.35 | 211 pairs |
| Predict death economy in t+1 from economy in t only: R² | 0.119 | 211 |
| Add execution in t: R² | 0.124 (gain +0.005) | 211 |
| Coefficient on execution (runs/ball per 1.0 of execution) | +0.67, s.e. 0.62 | 211 |
| Partial correlation, execution_t vs economy_t+1 given economy_t | +0.07 | 211 |

Thresholds 20 and 40 balls give the same story (R² gain +0.002 and +0.005; n = 256, 165). The coefficient has the wrong sign for the idea (higher execution should lower economy) and is within noise anyway. **No gain.** Execution is weakly repeatable (0.2-0.35), less than plain death economy.

Top and bottom 10, IPL 2024-26 pooled, shrunk execution, min 20 tagged death balls (92 bowlers). Econ = runs per over in overs 16-20.
| bowler | death balls | yorkers | full tosses | raw | shrunk | econ |
|---|---|---|---|---|---|---|
| M Jansen | 141 | 19 | 6 | 0.76 | 0.58 | 10.8 |
| MA Starc | 155 | 32 | 16 | 0.67 | 0.57 | 10.1 |
| Avesh Khan | 282 | 63 | 42 | 0.60 | 0.56 | 9.5 |
| Prince Yadav | 131 | 30 | 20 | 0.60 | 0.54 | 10.5 |
| A Kamboj | 130 | 35 | 26 | 0.57 | 0.53 | 10.6 |
| SH Johnson | 50 | 11 | 5 | 0.69 | 0.53 | 9.0 |
| M Pathirana | 209 | 21 | 14 | 0.60 | 0.53 | 9.4 |
| B Kumar | 306 | 54 | 46 | 0.54 | 0.52 | 10.2 |
| SM Curran | 78 | 6 | 2 | 0.75 | 0.52 | 12.7 |
| N Burger | 63 | 6 | 2 | 0.75 | 0.52 | 7.3 |
| ... | | | | | | |
| R Shepherd | 72 | 4 | 11 | 0.27 | 0.43 | 13.6 |
| Rashid Khan | 168 | 0 | 6 | 0.00 | 0.43 | 11.9 |
| YS Chahal | 144 | 0 | 6 | 0.00 | 0.43 | 11.3 |
| MM Sharma | 174 | 10 | 20 | 0.33 | 0.42 | 11.1 |
| LH Ferguson | 84 | 0 | 8 | 0.00 | 0.41 | 11.2 |
| Arshad Khan | 69 | 0 | 8 | 0.00 | 0.41 | 11.0 |
| Kartik Tyagi | 126 | 7 | 18 | 0.28 | 0.41 | 10.6 |
| Yash Dayal | 156 | 14 | 31 | 0.31 | 0.40 | 9.8 |
| HV Patel | 219 | 18 | 40 | 0.31 | 0.39 | 9.3 |
| SN Thakur | 174 | 15 | 43 | 0.26 | 0.36 | 10.3 |

Reading it: the ranking does not line up with results (HV Patel and Yash Dayal are bottom on execution but have good death economy; Jansen and Curran top with poor economy). Spinners (Rashid, Chahal) show up at the bottom only because they rarely bowl yorkers; the score only makes sense for pace bowlers. Small samples (many bowlers have fewer than 30 yorker plus full-toss balls) move the top of the list a lot.

## B. Drops
A drop = Cricbuzz event DROPPED or commentary lapse "drop" (same rule as `commentary_features`). 1,739 drops in 10 seasons. Cost of a drop = runs the reprieved batter scored after that ball in that innings (Cricsheet). Mean 19.6, median 13.0 (n = 1,739). 72% of reprieved batters were out later in the same innings.

By season (all teams): drops 142, 162, 142, 139, 160, 201, 170, 221, 213, 189 for 2017..2026; mean cost 17-20 runs, 24.3 in 2026 (small sample, ~189 drops).

Team fielding cost = sum of the runs after drops, per match (cost / (balls/240)). Whole-history, per match:
| team | drops | cost per match (runs) |
|---|---|---|
| Kolkata Knight Riders | 163 | 43.8 |
| Punjab Kings | 150 | 44.6 |
| Sunrisers Hyderabad | 220 | 48.1 |
| Mumbai Indians | 186 | 50.4 |
| Royal Challengers Bengaluru | 195 | 50.6 |
| Chennai Super Kings | 190 | 53.3 |
| Rajasthan Royals | 174 | 56.9 |
| Delhi Capitals | 226 | 64.4 |
| Gujarat Titans | 112 | 72.6 |
Worst team-season: Gujarat Titans 2025 (27 drops costing 955 runs, 133 per match, avg 35 per drop). Best: KKR 2023 (19 per match). Team-season repeatability (cost per match, t vs t+1): r = 0.18 on 78 pairs; drop counts per ball: r = 0.30 on 78 pairs. So drops are partly a team habit, mostly luck of which batter gets reprieved. Runs-after-drop is dominated by one big innings, so cost is noisy.

Bowler drop luck: 510 bowler-seasons with >= 120 balls had 1,398 drops against 6,048 wickets (drops are about 1.2 per 100 balls). Highest: HV Patel 2022 (9 drops, 321 balls, 19 wk), KK Ahmed 2024 (8 drops, 17 wk), TU Deshpande 2023 (8, 21). Adjusted wickets = wickets + drops (assumes every drop is a lost wicket; the catch is not always takeable, so this is an upper bound).

| does drop-adjusted wickets/ball in t predict raw wickets/ball in t+1? | r | n |
|---|---|---|
| raw wk/ball t -> raw t+1 | 0.160 | 280 pairs (>= 120 balls both years) |
| adjusted wk/ball t -> raw t+1 | 0.155 | 280 |
| difference (adjusted - raw), 5-95% bootstrap | -0.005 (-0.038, +0.030) | 280 |
Thresholds 60 balls (n = 417): -0.006; 200 balls (n = 166): -0.015. Adjusted-to-adjusted correlation (0.21) is higher but not a fair test (drops sit on both sides). **No gain**; the adjusted number is not a better forecast of wickets than raw. Wickets per ball itself repeats weakly (0.13-0.16).

## Caveats
- Length tags exist for about 59-69% of balls and drops depend on the commentator noticing; a drop count is a lower bound and could differ by commentary team.
- A drop's cost counts runs after the ball, so a late drop costs little by design; not compared against what an average batter at that stage would score.
- Pairs overlap (a bowler is in several pairs), so n is not fully independent.
