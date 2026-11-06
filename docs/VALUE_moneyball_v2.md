# Moneyball v2: stable-skill forecast, availability, buying simulation (2026-11-07)

All numbers **measured by us** (our Cricsheet DuckDB, backtest tool `cricket backtest`, targets IPL 2024/25/26, data before the target only, players with 60+ balls, 90% bootstrap ranges). Code: `models/marcel.py`, `models/availability.py`, `models/strategy.py`; tests `tests/test_marcel.py`. Plan: `docs/RESEARCH_moneyball_v2.md` items b, d, f. rho = rank correlation (1 = perfect order, 0 = none). Treat rho differences under 0.05 as noise (3 target years).

## 1. M11 Marcel-style predictor (item b)
Rule: last 3 seasons weighted 5/4/3; each runs-added part (base, dot, 1-3 runs, four, six, out/wicket, extras, rest) divided by (weighted balls + that part's own stability constant k from `components.k_table`, i.e. the M2 numbers); parts added up to a rate per ball; expected balls = the 5/4/3 mean of his IPL balls (a missed season counts 0). Variants: `marcel` (other men's leagues at weight 0.5, a guess), `marcel_ipl` (IPL only), `marcel_skill` (wicket and rest parts dropped).

Pooled 2024-26, all IPL players, total runs added (bat + bowl):
| predictor | n | rho (range) | MAE runs | bowl rho | bat rho |
|---|---|---|---|---|---|
| ipl3 (old best) | 371 | 0.12 (0.03-0.21) | 42.6 | 0.16 | 0.09 |
| pwar_runs | 411 | 0.09 (-0.00-0.16) | **33.5** | 0.14 | -0.00 |
| marcel | 411 | 0.11 (0.02-0.20) | 35.2 | 0.22 | 0.07 |
| **marcel_ipl** | 388 | **0.15 (0.06-0.23)** | 35.8 | **0.23** | **0.13** |
| marcel_skill | 411 | 0.10 (0.01-0.19) | 35.0 | 0.23 | 0.05 |

Overseas auction buys pooled (n 50-67): marcel_ipl rho 0.09 (-0.16-0.37), marcel 0.07, pwar_runs -0.02, ipl3 -0.01. Bowlers among them: marcel_ipl 0.35 (0.06-0.59), n 32.

Keep rule (rho above ipl3 by more than noise, or MAE below pwar_runs): **not met**. marcel_ipl is +0.03 rho over ipl3 (inside noise) and its MAE is 2.3 runs worse than pwar_runs. It is the best rank order we have; all predictors are weak. Bowlers repeat (0.2); batters barely. The overseas pool is too small to say anything. No default changed; `marcel_ipl` stays an optional predictor.

## 2. M12 Availability (item d)
New truth options in the backtest tool: `--what share` (matches played / the median team's matches in season X+1, capped 1) and `balls` (faced + bowled). Players who never appeared are not in the truth, except sold auction players (counted 0) in the auction pools.

| predictor | all IPL players (n 499) | auction buys (n 204-289) | overseas buys (n 89-120) |
|---|---|---|---|
| share last season | 0.52 (0.47-0.58) | 0.38 | 0.18 (0.02-0.37) |
| share 5/4/3 over 3 seasons | **0.54 (0.48-0.59)** | 0.45 | 0.31 (0.15-0.47) |
| share 3 seasons, shrunk | 0.54 | 0.45 | 0.31 |
| auction price | 0.44 (n 218) | **0.47** (n 289) | **0.42 (0.28-0.55)** |
| marcel value (do good players play more?) | 0.25 | 0.06 | 0.06 |
| balls 5/4/3 (target balls) | **0.58** | 0.50 | 0.37 |
| balls last season | 0.55 | 0.38 | 0.16 |

Reading: who plays is about four times as predictable as how well he plays (rho 0.5 against 0.12). The 3-season share beats last season only slightly. For overseas buys, **price is the best guide to being used** (a franchise plays what it paid for), better than history. Marcel value says almost nothing about who gets picked.

Rate x opportunity for total runs added (pooled): `ropp_last` (marcel_ipl rate x last-season balls) rho 0.16, MAE 36.3; `ropp_share` (rate x balls per match x shrunk predicted share x 14) rho 0.15, MAE 35.1; marcel_ipl alone 0.15 / 35.8. No gain beyond noise; MAE still above pwar_runs 33.5. Opportunity is predictable but the rate it multiplies is the noisy factor.

## 3. M13 Buying-strategy simulation 2023-26 (item f)
Setup (code `strategy.py`): for each auction year, each of the 10 teams gets the budget, squad slots and overseas count of its actual buys. Candidates = the whole auction pool matched to Cricsheet (sold at the actual price, unsold at base price). Only leagues up to the year before the auction are used. Predicted value = marcel_ipl (marcel for players without IPL history), in runs above replacement. Realised value = IPL season Y runs above replacement (runs added minus the era's replacement x balls, the war.py parameters; 0 if he did not play), summed. Teams are simulated independently (two rule teams may pick the same player). Random = same caps, random first-fit, 1000 draws of all 40 team-years. 40 team-years in all; actual spend 1,252 crore.

| buyer | runs above replacement | crore spent | runs per crore | percentile among 1000 random buyers (whole pool) | among random buyers who only see players with a prediction |
|---|---|---|---|---|---|
| actual buys | +299 | 1252 | 0.24 | 60 | 30 |
| rule: highest predicted value first | +100 | 1145 | 0.09 | 49 | 22 |
| rule: best predicted value per crore | -1203 | 766 | -1.57 | 0.1 | 0.0 |
| random (mean, 5-95% range) | | | 0.10 (-0.84 to 1.14) | | 0.54 (-0.37 to 1.45) |

Reading: the model-based buyer does **not** beat random or the real franchises. "Value per crore" is the worst: it picks cheap players whose forecast is high on little evidence, who then do worse (winner's curse: the forecast is most inflated exactly where the ratio is largest). Actual buyers sit near the 60th percentile of random: slightly better than chance, not significantly. With 4 auctions the spread of random results (-0.8 to +1.1 per crore) is wide; nothing here is significant.

Simple rules (runs per crore, versus random draws of the same number of players from the comparable pool):
| rule | n | group | pool average | random mean | percentile |
|---|---|---|---|---|---|
| "proven bowlers cheap": 1000+ bowl balls in 3 seasons, price at or below that year's median sold price | 44 | -1.26 | +0.63 | +0.87 | 35 |
| "no premium for one hot batting season": batter or keeper, price 3 crore+, top-quartile IPL runs added last season | 3 | -1.39 | +0.51 | +0.38 | 28 |

The cheap-bowler rule is worse than the pool average (35th percentile), so the research-doc guess that proven bowlers are underpriced is **not supported** (bowler skill repeats a little, price already knows it). The hot-batter rule has n = 3 (top IPL batters are mostly retained, not auctioned): Pant 2025 (27 cr, -40 runs above replacement) and Fraser-McGurk (9 cr, -80) were bad buys, Rahul (14 cr, +51) a good one. Untestable at this size.

## What to trust
- Trust: availability is predictable (rho about 0.5; price is the best clue for overseas players); bowlers' value repeats a little (rho 0.2); batters' does not.
- Do not trust: any claim that a rule "finds bargains". Three honest tests (model buyer, bowler rule, hot-batter rule) all land inside the spread of random buying.
- Limits: 3 target years, 4 auctions; unmatched auction players (no Cricsheet name; mostly unsold, a few sold uncapped) count 0 for actual buys; no injury data; teams simulated independently, no bidding war; replacement level is fitted, not observed.

## Kept
New optional predictors/options only (`marcel*`, `share_*`, `balls_*`, `ropp_*`, `--what share|balls`, `models/strategy.py`). No module default or CSV changed.
