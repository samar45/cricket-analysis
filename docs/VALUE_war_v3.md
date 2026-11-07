# WAR v3 (2026-11-07): batting + bowling only, match-adjusted

All numbers **measured by us** (Cricsheet DuckDB, read-only). v3 is the default (`version=v3`; v1 and v2 stay selectable). Code: `models/war.py` (`fit_v3`, `match_adjust_rows`, `load_params("v3")`), `models/match_adjust.py`, `models/data/war_params_v3.json`.

## 1. What changed from v2 (Samar's decisions)
1. **No fielding in WAR.** WAR = batting + bowling. The bowler gets the full wicket credit for catches and stumpings again; a run-out credits nobody (as v1). Dropped: `field_war`, pWAR field part (`field` column of `pwar_ipl_2027.csv`), trade `field_value`/`field_war_*`/`field_draws`. The fair-fielding code (`fair_field`, `fit_field_fair`) stays in `models/war.py` and `version=v2` still shows it; the fielding module (`analysis/fielding.py`) has no WAR-style credit yet (not built here).
2. **Match adjustment, w = 0.25.** Each (match, phase, role) gets a condition c = mean runs added per ball of all OTHER players in that match, phase and role. Adjusted runs added = runs added - 0.25 x c x balls, then re-centred per league-season. 25% match conditions, 75% league average (one match can be against a weak or strong side; the average over many balls is safer). The adjustment goes into the scoring part (`sc`), so `bat_scoring`/`bowl_scoring` include it.
3. **Parameters otherwise as v2** (replacement -6, runs per win 99.3 / 91.0): the refit on adjusted runs added moved runs per win to 100.7 (95% range 81.5-126.2, R2 0.613), inside the old range, so not changed.
4. Dependents refitted: pWAR (projection constants refit; grid winners identical to v2), `pwar_ipl_2027.csv` (+ controllable columns), trade values (`trade_match_ra.csv`, built from the adjusted match rows) and beta, auction features/model, backtest tables (now match-adjusted).

## 2. All parameters and coefficients of WAR v3
| item | value | source / size |
|---|---|---|
| Run-expectancy table | `models/data/run_expectancy.csv` (+ `adjust.csv`) | expected runs and wicket cost by over, wickets, innings (balls_per_over per competition); extra tables for SMAT, ILT20, MLC, BPL, LPL |
| Runs added per ball | runs off the bat + value of the state change + innings constant (batting); the mirror image for bowling | v1 definition, no fielding rows |
| Centring | each league-season, batting and bowling separately: average player = 0 per ball | recomputed on the data; re-centred again after the match adjustment |
| Match weight w | **0.25** (c = leave-one-player-out mean of the other players, same match + phase + role) | `models/match_adjust.py`; w grid 0 / .25 / .5 / .75 / 1 in `VALUE_match_adjust.md` |
| Replacement level | **-6.0 runs per 100 balls**, batting (per ball faced) and bowling (per ball bowled) | convention: a replacement-level team wins about 36% (`VALUE_war_fix.md`) |
| Runs per win, IPL 2023+ | **99.30** (v3 refit 100.68; 95% range 81.5-126.2; 40 team-seasons; win-prob cross-check 99.5; run-margin cross-check 104.9) | team runs added vs wins above half |
| Runs per win, IPL 2008-22 | **90.97** (95% range 77.2-107.4; 126 team-seasons) | same |
| Role cut | bowling share of (balls faced + bowled) < 0.2 batter, > 0.8 bowler, else all-rounder | `ROLE_CUT = 0.2` |
| main_war | batters: bat WAR; bowlers: bowl WAR; all-rounders: bat + bowl | |
| pWAR projection | IPL 2023+ evidence (weight 1) + other men's leagues; bat: other leagues a=1.0, strength s=0.5, shrink k=[3000, 6000] balls; bowl: a=1.0, s=1.0, k=[1600, 1600]; 5-season window; expected balls = OLS on last 3 seasons (bat [6.19, 0.65, 0.21], bowl [11.30, 0.59, 0.19]) | refit on adjusted rates, same winners as v2 |

## 3. Team-season fit (IPL 2023-26, 40 team-seasons; WAR summed over a team's players vs wins above half)
| version | r | slope | MAE (wins) | repl. team win share |
|---|---|---|---|---|
| v1 | 0.778 | 1.00 | 0.99 | 50% (no replacement) |
| v2 (fielding, raw) | 0.803 | 0.98 | 0.93 | 36% |
| **v3** | **0.798** | 0.97 | 0.95 | 36% |

Removing fielding and adding the 25% match adjustment costs 0.005 in r (noise-sized); v3 is still above v1. (Measured with the same fit function for all three rows, centred tables, so the v1 row differs by 0.006 from the 0.784 in `VALUE_war_fix.md`.)

## 4. Sanity players, IPL 2023-26 (sum of seasons)
| player | v2 bat | v2 bowl | v2 field | v2 total | v3 bat | v3 bowl | v3 total |
|---|---|---|---|---|---|---|---|
| JJ Bumrah | -0.08 | 3.10 | -0.04 | 2.98 | -0.06 | 3.59 | 3.53 |
| HH Pandya | -0.58 | -1.22 | -0.02 | -1.83 | -0.58 | -0.88 | -1.46 |
| H Klaasen | 4.72 | 0.00 | -0.03 | 4.69 | 4.75 | 0.00 | 4.75 |
| SP Narine | -0.34 | 2.61 | 0.03 | 2.30 | -0.37 | 2.95 | 2.59 |
| V Kohli | 2.27 | 0.00 | 0.08 | 2.35 | 2.28 | 0.00 | 2.28 |

(v2 here = shipped default with fair fielding.) Bumrah and Narine gain 0.35-0.5 because bowlers keep their catches; Hardik is still negative.

## 5. Top 5 by main_war, IPL 2023-26 (all seasons summed, grouped by each season's main_role; `top=5000`)
| rank | batters | bowlers | all-rounders |
|---|---|---|---|
| 1 | H Klaasen 4.75 | B Kumar 3.77 | RA Jadeja 2.79 |
| 2 | B Sai Sudharsan 3.21 | JJ Bumrah 3.59 | SP Narine 1.93 |
| 3 | KL Rahul 2.67 | CV Varun 3.51 | J Overton 1.39 |
| 4 | SA Yadav 2.63 | TA Boult 3.00 | KH Pandya 1.13 |
| 5 | Tilak Varma 2.56 | Mohammed Siraj 2.91 | AD Russell 0.97 |

(Narine's full-career role over 2023-26 is all-rounder with 3.62 main_war; the table groups by each season's role, so seasons where he was mostly a bowler count under bowlers.)

## 6. Old -> new numbers
| item | v2 | v3 |
|---|---|---|
| trade beta (win chance per XII value unit) | 0.054 | 0.085 (10-90%: -0.025 to 0.216; 215 matches) |
| Hardik Pandya for Jaiswal, XII before / after (test golden) | 3.19 / 3.54 | 3.56 / 3.83 |
| `pwar_ipl_2027.csv` columns | cricsheet_name, pwar, bat, bowl, field, ... | field removed; pwar = bat + bowl |
| top pWAR 2027 | (v2 order) | SP Narine 0.644, H Klaasen 0.580, JJ Bumrah 0.508, B Sai Sudharsan 0.493, B Kumar 0.491 |
| V Kohli 2016 bat runs added (war module; runs_added module 153.4) | 162.2 | 127.5 |
| JC Buttler 2022 bat runs added (runs_added module ~157.9 vs war) | 157.9 | 139.3 |
| runs per win (fit) | 99.30 | 100.68 (kept 99.30) |

Backtest (`cricket backtest --pool all --what total`, pooled Spearman with next-season runs added, 2024-26):
| predictor | before (v2, raw tables) | after (v3, adjusted tables) |
|---|---|---|
| pwar | +0.02 (n 411) | +0.01 (411) |
| recent_value | +0.13 (375) | +0.12 (371) |
| ipl3 | +0.12 | +0.12 |
| lw_all | +0.07 | +0.07 |
Differences are within noise (about +-0.05); the truth also changed (match-adjusted), so the rows are not like-for-like. No predictor improves.

## 7. Caveats
- Fielding is not in WAR; the fielding module still lists raw counts only.
- Removing fielding makes the bowler carry the luck of catches again (v2 showed bowler repeatability rises when part of it is moved to fielders).
- w = 0.25 is a judgement call; the repeatability / team-fit curve is in `VALUE_match_adjust.md`.
