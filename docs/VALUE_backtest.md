# Backtest: does our value forecast next season? (M9, 2026-11-07)

All numbers **measured by us** (Cricsheet DuckDB, read-only). Code: `models/backtest.py`, CLI `cricket backtest`, test `tests/test_backtest.py`.
Rerun: `cricket backtest --pool auction_os --what total` (about 30 s).

## 1. The tool
A **predictor** is one function `fn(T, X, ctx)`: it gets the league-season table cut to seasons ending in year X or earlier (so the
target season is invisible by construction; `sy` = calendar year the season ended, an early-2026 league counts as 2026 and is left out
of an IPL 2026 forecast, a slightly conservative cut) and returns expected IPL runs added per player. **Truth** = the player's IPL
season X+1 runs added (centred so the league-season average player is 0), total (bat + bowl), per role, and per ball. A player
counts in a target year only with 60+ balls in that season (batting or bowling). Auction price is the price paid at the Dec X auction
(`auction_year` X+1), which is before IPL X+1. Adding a predictor = one function with `@predictor(name, scale)`.

Predictors: `zero` (everybody average); `last_ipl` (IPL runs added last season); `ipl3` (mean of the last 3 IPL seasons, Impact era
only); `recent_value` (the trade tool's 4/3/2/1 weighted WAR); `pwar` / `pwar_runs` (war.py projection fitted on earlier seasons, in wins /
in runs); `lw_other` (the lead's overseas score: other leagues only, hand-set league strengths, shrunk to 0, last 3 years);
`lw_all` (the same, IPL counted at weight 1); `price` (auction price in crore, sold players only).
Statistics: Spearman rank correlation (rho) per target year (n in brackets); "pooled" = all three years stacked, with a 90% bootstrap
range (300 draws over players); Pearson r; MAE (mean absolute error in runs) only for predictors on a runs scale. A predictor is only
scored on players it has a number for, so n differs; the `common` pool keeps only players all predictors cover (tiny: it needs IPL
history), `auction` = players bought at that year's auction, `auction_os` = overseas buys only.

## 2. Findings (read first)
1. **Next-season total runs added is hard to forecast by anyone.** All players with IPL data, targets 2024-26 pooled (n 327-378):
   best rho is 0.14 (`ipl3`), `lw_all` 0.11, `pwar` 0.06, `lw_other` 0.05. Only `ipl3`, `last_ipl`, `recent_value`, `lw_all` have a
   range clear of 0, and none is clearly better than another. Our pWAR is **not better than just using the last three IPL seasons**.
2. **Bowlers repeat, batters barely do.** Per-ball rate, pooled: bowlers rho 0.18-0.22 for `last_ipl`, `ipl3`, `pwar`, `lw_all`
   (ranges above 0); batters about 0 for everything (-0.09 to +0.06). This matches the stability table of VALUE_m2.
3. **A zero forecast beats every forecast on MAE.** Mean absolute error of a runs forecast 34.5 (zero) vs 42.7 (`ipl3`) and 47.3
   (`last_ipl`) for total runs added: past seasons are scaled too high; the signal is in the ordering, not the size.
4. **The lead's overseas score (`lw_other`) is the weakest predictor in every pool.** Auction pool, overseas buys, IPL 2026 only
   (n=11 with 60+ balls, or n=17 with any ball): `lw_other` -0.57 / -0.31, `pwar` -0.31 / -0.09, `price` +0.31 / +0.38, own IPL
   history `ipl3` +0.43 / +0.34. The lead's n=20 figures (-0.17, 0.25, 0.21) are reproduced in sign and rough size (a few players differ
   in cut-off rules and league filters). **But the 90% ranges of all of these include 0 and 2026 is one year**: over 2024-26 pooled
   overseas buys (n=63) `price` is +0.13 (-0.04 to +0.33) and every score is +0.01 to +0.02. Price is a weak signal, our scores are none.
5. Adding the IPL itself to the league-weighted score (`lw_all`) fixes most of the damage: other leagues (bowling excepted) add little
   beyond IPL numbers.

## 3. Tables
Pooled rho columns have n in the cell for each year. `-` = not defined (no data or no spread).

#### pool = all, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 34.5 |
| last_ipl | +0.19 (99) | +0.17 (113) | +0.04 (115) | +0.13 (327) | +0.04 to +0.21 | 0.14 | 47.3 |
| ipl3 | +0.19 (99) | +0.16 (119) | +0.08 (123) | +0.14 (341) | +0.06 to +0.24 | 0.17 | 42.7 |
| recent_value | +0.18 (99) | +0.14 (119) | +0.09 (123) | +0.13 (341) | +0.05 to +0.22 | 0.16 | - |
| pwar | +0.02 (120) | +0.16 (126) | -0.01 (127) | +0.06 (373) | -0.02 to +0.16 | 0.14 | - |
| pwar_runs | +0.10 (120) | +0.18 (126) | +0.05 (127) | +0.10 (373) | +0.02 to +0.19 | 0.16 | 33.9 |
| lw_other | +0.11 (122) | +0.03 (121) | +0.02 (115) | +0.05 (358) | -0.05 to +0.14 | 0.06 | - |
| lw_all | +0.15 (125) | +0.12 (129) | +0.06 (124) | +0.11 (378) | +0.03 to +0.20 | 0.14 | - |
| price | -0.09 (26) | +0.06 (84) | +0.18 (24) | +0.01 (134) | -0.13 to +0.16 | 0.06 | - |

**bat_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.183 |
| last_ipl | +0.06 (64) | +0.14 (69) | -0.01 (68) | +0.06 (201) | -0.05 to +0.18 | -0.01 | 0.328 |
| ipl3 | +0.06 (64) | +0.13 (70) | -0.03 (70) | +0.05 (204) | -0.07 to +0.17 | -0.03 | 0.299 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.09 (78) | +0.08 (75) | -0.01 (73) | -0.00 (226) | -0.12 to +0.11 | 0.01 | - |
| pwar_runs | -0.09 (78) | +0.08 (75) | -0.01 (73) | -0.00 (226) | -0.12 to +0.11 | 0.01 | 0.180 |
| lw_other | -0.05 (80) | -0.08 (76) | -0.13 (73) | -0.09 (229) | -0.20 to +0.02 | -0.00 | - |
| lw_all | +0.10 (81) | +0.05 (78) | -0.04 (75) | +0.03 (234) | -0.08 to +0.13 | 0.04 | - |
| price | - | - | - | - | - | - | - |

**bowl_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.195 |
| last_ipl | +0.29 (47) | +0.23 (58) | +0.17 (53) | +0.22 (158) | +0.08 to +0.34 | 0.18 | 0.272 |
| ipl3 | +0.29 (47) | +0.16 (63) | +0.12 (60) | +0.18 (170) | +0.05 to +0.29 | 0.15 | 0.254 |
| recent_value | - | - | - | - | - | - | - |
| pwar | +0.21 (57) | +0.27 (65) | +0.13 (62) | +0.20 (184) | +0.08 to +0.31 | 0.20 | - |
| pwar_runs | +0.21 (57) | +0.27 (65) | +0.13 (62) | +0.20 (184) | +0.08 to +0.31 | 0.20 | 0.193 |
| lw_other | +0.14 (57) | +0.16 (60) | +0.09 (50) | +0.14 (167) | +0.02 to +0.25 | 0.12 | - |
| lw_all | +0.21 (59) | +0.25 (66) | +0.15 (56) | +0.21 (181) | +0.10 to +0.32 | 0.20 | - |
| price | - | - | - | - | - | - | - |


#### pool = common, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 30.7 |
| last_ipl | +0.62 (10) | +0.07 (64) | +0.89 (6) | +0.13 (80) | -0.05 to +0.34 | 0.19 | 37.8 |
| ipl3 | +0.62 (10) | +0.11 (64) | +0.94 (6) | +0.20 (80) | +0.02 to +0.41 | 0.24 | 34.5 |
| recent_value | +0.67 (10) | +0.08 (64) | +0.89 (6) | +0.16 (80) | -0.04 to +0.37 | 0.19 | - |
| pwar | +0.02 (10) | +0.11 (64) | -0.54 (6) | +0.08 (80) | -0.12 to +0.31 | 0.18 | - |
| pwar_runs | +0.10 (10) | +0.15 (64) | +0.09 (6) | +0.15 (80) | -0.04 to +0.38 | 0.23 | 29.7 |
| lw_other | +0.01 (10) | +0.06 (64) | -0.66 (6) | +0.03 (80) | -0.13 to +0.24 | 0.06 | - |
| lw_all | +0.19 (10) | +0.16 (64) | +0.09 (6) | +0.13 (80) | -0.04 to +0.33 | 0.15 | - |
| price | -0.10 (10) | -0.01 (64) | +0.32 (6) | -0.07 (80) | -0.25 to +0.12 | 0.02 | - |

**bat_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.180 |
| last_ipl | +0.00 (4) | +0.24 (34) | +0.80 (4) | +0.22 (42) | -0.02 to +0.47 | 0.20 | 0.369 |
| ipl3 | +0.00 (4) | +0.20 (34) | +1.00 (4) | +0.24 (42) | -0.04 to +0.51 | 0.13 | 0.292 |
| recent_value | - | - | - | - | - | - | - |
| pwar | +0.40 (4) | +0.07 (34) | +0.00 (4) | +0.14 (42) | -0.14 to +0.39 | 0.12 | - |
| pwar_runs | +0.40 (4) | +0.07 (34) | +0.00 (4) | +0.14 (42) | -0.14 to +0.39 | 0.12 | 0.175 |
| lw_other | +0.40 (4) | -0.17 (34) | -0.60 (4) | -0.12 (42) | -0.36 to +0.14 | 0.04 | - |
| lw_all | +0.40 (4) | -0.00 (34) | +0.00 (4) | +0.04 (42) | -0.21 to +0.27 | 0.08 | - |
| price | - | - | - | - | - | - | - |

**bowl_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.200 |
| last_ipl | +0.77 (6) | +0.26 (37) | - | +0.30 (45) | +0.09 to +0.49 | 0.24 | 0.284 |
| ipl3 | +0.77 (6) | +0.39 (37) | - | +0.41 (45) | +0.20 to +0.60 | 0.34 | 0.229 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.26 (6) | +0.44 (37) | - | +0.30 (45) | +0.01 to +0.53 | 0.31 | - |
| pwar_runs | -0.26 (6) | +0.44 (37) | - | +0.30 (45) | +0.01 to +0.53 | 0.31 | 0.193 |
| lw_other | -0.14 (6) | +0.27 (37) | - | +0.13 (45) | -0.13 to +0.37 | 0.16 | - |
| lw_all | -0.03 (6) | +0.49 (37) | - | +0.36 (45) | +0.07 to +0.56 | 0.34 | - |
| price | - | - | - | - | - | - | - |


#### pool = auction, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 30.4 |
| last_ipl | +0.62 (10) | +0.06 (66) | +0.89 (6) | +0.12 (82) | -0.07 to +0.31 | 0.18 | 37.7 |
| ipl3 | +0.62 (10) | +0.01 (72) | +0.53 (12) | +0.09 (94) | -0.10 to +0.26 | 0.13 | 37.2 |
| recent_value | +0.67 (10) | -0.00 (72) | +0.54 (12) | +0.07 (94) | -0.12 to +0.25 | 0.11 | - |
| pwar | +0.12 (22) | +0.09 (78) | -0.43 (15) | +0.01 (115) | -0.17 to +0.16 | 0.11 | - |
| pwar_runs | +0.05 (22) | +0.10 (78) | -0.32 (15) | +0.04 (115) | -0.13 to +0.21 | 0.17 | 29.1 |
| lw_other | +0.09 (26) | +0.03 (79) | -0.37 (16) | +0.00 (121) | -0.14 to +0.14 | -0.00 | - |
| lw_all | +0.12 (26) | +0.07 (81) | -0.14 (16) | +0.03 (123) | -0.10 to +0.16 | 0.05 | - |
| price | -0.09 (26) | +0.06 (84) | +0.18 (24) | +0.01 (134) | -0.13 to +0.16 | 0.06 | - |

**bat_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.180 |
| last_ipl | +0.00 (4) | +0.24 (34) | +0.80 (4) | +0.22 (42) | -0.02 to +0.47 | 0.20 | 0.369 |
| ipl3 | +0.00 (4) | +0.15 (35) | +0.20 (6) | +0.13 (45) | -0.12 to +0.41 | 0.08 | 0.303 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.19 (11) | +0.04 (40) | -0.20 (9) | -0.01 (60) | -0.26 to +0.22 | -0.02 | - |
| pwar_runs | -0.19 (11) | +0.04 (40) | -0.20 (9) | -0.01 (60) | -0.26 to +0.22 | -0.02 | 0.170 |
| lw_other | +0.11 (14) | -0.12 (43) | -0.61 (10) | -0.17 (67) | -0.36 to +0.01 | -0.02 | - |
| lw_all | +0.14 (14) | -0.04 (43) | -0.37 (10) | -0.05 (67) | -0.25 to +0.11 | 0.01 | - |
| price | - | - | - | - | - | - | - |

**bowl_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.203 |
| last_ipl | +0.77 (6) | +0.24 (39) | - | +0.27 (47) | +0.05 to +0.48 | 0.22 | 0.286 |
| ipl3 | +0.77 (6) | +0.18 (44) | -0.14 (7) | +0.15 (57) | -0.06 to +0.36 | 0.14 | 0.280 |
| recent_value | - | - | - | - | - | - | - |
| pwar | +0.16 (12) | +0.35 (45) | -0.71 (7) | +0.17 (64) | -0.06 to +0.38 | 0.15 | - |
| pwar_runs | +0.16 (12) | +0.35 (45) | -0.71 (7) | +0.17 (64) | -0.06 to +0.38 | 0.15 | 0.200 |
| lw_other | +0.12 (13) | +0.24 (44) | -0.68 (7) | +0.08 (64) | -0.12 to +0.28 | 0.05 | - |
| lw_all | +0.20 (13) | +0.36 (46) | -0.50 (7) | +0.20 (66) | -0.01 to +0.38 | 0.15 | - |
| price | - | - | - | - | - | - | - |


#### pool = auction_os, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 33.6 |
| last_ipl | +0.80 (4) | +0.08 (28) | +1.00 (4) | +0.20 (36) | -0.10 to +0.45 | 0.33 | 38.2 |
| ipl3 | +0.80 (4) | -0.11 (33) | +0.43 (8) | -0.01 (45) | -0.26 to +0.24 | 0.15 | 41.3 |
| recent_value | +0.80 (4) | -0.06 (33) | +0.45 (8) | +0.04 (45) | -0.20 to +0.30 | 0.20 | - |
| pwar | +0.20 (14) | +0.16 (38) | -0.31 (11) | +0.01 (63) | -0.21 to +0.22 | 0.17 | - |
| pwar_runs | -0.18 (14) | +0.18 (38) | -0.38 (11) | +0.02 (63) | -0.21 to +0.22 | 0.15 | 30.2 |
| lw_other | +0.08 (14) | +0.15 (38) | -0.57 (11) | +0.01 (63) | -0.18 to +0.21 | -0.03 | - |
| lw_all | +0.13 (14) | +0.13 (38) | -0.35 (11) | +0.02 (63) | -0.16 to +0.22 | 0.01 | - |
| price | +0.11 (14) | +0.19 (38) | +0.31 (11) | +0.13 (63) | -0.04 to +0.33 | 0.14 | - |

**bat_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.183 |
| last_ipl | +0.50 (3) | +0.31 (14) | +1.00 (3) | +0.24 (20) | -0.22 to +0.60 | 0.17 | 0.348 |
| ipl3 | +0.50 (3) | +0.16 (15) | +0.40 (4) | +0.12 (22) | -0.32 to +0.52 | 0.09 | 0.343 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.14 (8) | +0.22 (19) | +0.21 (7) | +0.02 (34) | -0.28 to +0.33 | 0.00 | - |
| pwar_runs | -0.14 (8) | +0.22 (19) | +0.21 (7) | +0.02 (34) | -0.28 to +0.33 | 0.00 | 0.155 |
| lw_other | -0.14 (8) | +0.19 (19) | -0.46 (7) | -0.05 (34) | -0.32 to +0.26 | 0.04 | - |
| lw_all | -0.14 (8) | +0.16 (19) | +0.11 (7) | -0.04 (34) | -0.32 to +0.29 | 0.05 | - |
| price | - | - | - | - | - | - | - |

**bowl_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.250 |
| last_ipl | - | +0.22 (19) | - | +0.25 (21) | -0.08 to +0.53 | 0.26 | 0.355 |
| ipl3 | - | +0.23 (23) | -0.10 (5) | +0.12 (29) | -0.23 to +0.46 | 0.19 | 0.330 |
| recent_value | - | - | - | - | - | - | - |
| pwar | +0.36 (7) | +0.55 (24) | -0.80 (5) | +0.25 (36) | -0.03 to +0.52 | 0.20 | - |
| pwar_runs | +0.36 (7) | +0.55 (24) | -0.80 (5) | +0.25 (36) | -0.03 to +0.52 | 0.20 | 0.229 |
| lw_other | +0.21 (7) | +0.31 (24) | -0.80 (5) | +0.09 (36) | -0.16 to +0.35 | 0.05 | - |
| lw_all | +0.21 (7) | +0.45 (24) | -0.50 (5) | +0.18 (36) | -0.08 to +0.40 | 0.12 | - |
| price | - | - | - | - | - | - | - |


#### pool = auction_os, min balls in target season = 1

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 31.1 |
| last_ipl | +0.80 (4) | -0.03 (33) | +0.57 (7) | +0.08 (44) | -0.20 to +0.36 | 0.14 | 36.5 |
| ipl3 | +0.80 (4) | -0.16 (38) | +0.34 (12) | -0.05 (54) | -0.29 to +0.18 | 0.09 | 38.5 |
| recent_value | +0.80 (4) | -0.11 (38) | +0.36 (12) | -0.01 (54) | -0.26 to +0.26 | 0.07 | - |
| pwar | +0.17 (17) | +0.12 (47) | -0.09 (17) | -0.00 (81) | -0.20 to +0.19 | 0.19 | - |
| pwar_runs | -0.18 (17) | +0.12 (47) | -0.19 (17) | -0.01 (81) | -0.22 to +0.20 | 0.16 | 27.3 |
| lw_other | +0.05 (17) | +0.14 (47) | -0.31 (17) | +0.04 (81) | -0.13 to +0.22 | -0.00 | - |
| lw_all | +0.10 (17) | +0.09 (47) | -0.20 (17) | +0.02 (81) | -0.18 to +0.21 | 0.02 | - |
| price | +0.23 (17) | +0.12 (47) | +0.38 (17) | +0.15 (81) | -0.00 to +0.31 | 0.15 | - |

**bat_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.632 |
| last_ipl | +0.50 (3) | +0.24 (30) | +0.71 (6) | +0.22 (39) | -0.04 to +0.54 | 0.13 | 0.623 |
| ipl3 | +0.50 (3) | +0.21 (35) | +0.66 (11) | +0.26 (49) | +0.04 to +0.48 | 0.11 | 0.616 |
| recent_value | - | - | - | - | - | - | - |
| pwar | +0.35 (17) | +0.32 (47) | +0.48 (17) | +0.35 (81) | +0.18 to +0.50 | 0.29 | - |
| pwar_runs | +0.35 (17) | +0.32 (47) | +0.48 (17) | +0.35 (81) | +0.18 to +0.50 | 0.29 | 0.553 |
| lw_other | +0.39 (17) | +0.27 (47) | +0.10 (17) | +0.25 (81) | +0.07 to +0.42 | 0.25 | - |
| lw_all | +0.41 (17) | +0.26 (47) | +0.19 (17) | +0.26 (81) | +0.08 to +0.43 | 0.26 | - |
| price | - | - | - | - | - | - | - |

**bowl_rate** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 0.361 |
| last_ipl | - | +0.30 (21) | +0.50 (3) | +0.31 (26) | -0.03 to +0.59 | 0.19 | 0.451 |
| ipl3 | - | +0.29 (25) | -0.21 (8) | +0.15 (35) | -0.15 to +0.45 | 0.14 | 0.409 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.03 (12) | +0.49 (29) | -0.43 (9) | +0.17 (50) | -0.09 to +0.39 | 0.04 | - |
| pwar_runs | -0.03 (12) | +0.49 (29) | -0.43 (9) | +0.17 (50) | -0.09 to +0.39 | 0.04 | 0.308 |
| lw_other | -0.03 (12) | +0.21 (29) | -0.53 (9) | +0.00 (50) | -0.23 to +0.20 | -0.06 | - |
| lw_all | -0.04 (12) | +0.32 (29) | -0.30 (9) | +0.09 (50) | -0.14 to +0.27 | -0.01 | - |
| price | - | - | - | - | - | - | - |
