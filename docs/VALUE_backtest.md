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
1. **Next-season total runs added is hard to forecast by anyone.** All players with IPL data, targets 2024-26 pooled (n 356-427): best
   rho is 0.12 (`ipl3`), then `last_ipl` 0.11, `recent_value` 0.10, `pwar_runs` 0.09, `lw_all` 0.07, `lw_other` 0.04, `pwar` 0.03.
   Our projection (pWAR) is **not better than just using the last 3 IPL seasons**; the 90% ranges of the best ones sit only just above 0.
2. **Bowlers repeat, batters barely do.** Per-ball rate, pooled: bowlers rho 0.13-0.16 (`last_ipl` 0.16, `pwar` 0.14, `ipl3` and `lw_all` 0.13);
   batters about 0 for every predictor (-0.09 to +0.06). Same message as the stability table of VALUE_m2.
3. **Size is wrong even when the order is right.** Mean absolute error for total runs added: 34.2 for "everybody average", 42.6 for `ipl3`,
   47.1 for `last_ipl` (last season's number is too extreme), 33.5 for `pwar_runs` (the only forecast that, barely, beats "average").
4. **The league-weighted overseas score (`lw_other`) never beats the IPL-only baselines.** Overseas buys at the Dec 2025 auction forecasting IPL 2026
   (any player with a ball, n=20): `price` +0.24, `ipl3` +0.29 (only the 13 with IPL history), `pwar` -0.06, `lw_all` -0.14, `lw_other` -0.18
   (the lead's -0.17 / 0.25 / 0.21 are reproduced in size and sign). With 60+ balls (n=12): `price` +0.31, `pwar` -0.32, `lw_other` -0.50.
   **But this is one year with 12-20 players, and every 90% range includes 0.** Pooled 2024-26 overseas buys (n=68): `price` +0.08
   (-0.13 to +0.28), `lw_other` +0.01, `pwar` -0.03. All 153 buys 2024-26: `price` +0.01. Price is a weak hint, our scores are no better.
5. Counting the IPL inside the league-weighted score (`lw_all`) is better than other leagues alone in every pool: other leagues add little to what the IPL says.
6. The sample per year is small (the IPL has 100-140 players with 60+ balls a year); differences of 0.05 in rho are noise. Treat this as
   "no predictor here is good", not as a ranking of predictors.

## 3. Tables
Pooled rho columns show n per year. `-` = not defined.

#### pool = all, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 34.2 |
| last_ipl | +0.15 (113) | +0.14 (121) | +0.03 (122) | +0.11 (356) | +0.02 to +0.19 | 0.13 | 47.1 |
| ipl3 | +0.15 (113) | +0.12 (128) | +0.09 (130) | +0.12 (371) | +0.03 to +0.20 | 0.16 | 42.6 |
| recent_value | +0.14 (113) | +0.10 (128) | +0.08 (130) | +0.10 (371) | +0.01 to +0.19 | 0.15 | - |
| pwar | +0.01 (139) | +0.10 (137) | -0.02 (135) | +0.03 (411) | -0.05 to +0.11 | 0.13 | - |
| pwar_runs | +0.07 (139) | +0.15 (137) | +0.06 (135) | +0.09 (411) | -0.00 to +0.16 | 0.15 | 33.5 |
| lw_other | +0.05 (144) | +0.02 (142) | +0.06 (129) | +0.04 (415) | -0.03 to +0.12 | 0.05 | - |
| lw_all | +0.08 (145) | +0.07 (144) | +0.07 (138) | +0.07 (427) | -0.00 to +0.15 | 0.11 | - |
| price | -0.11 (30) | +0.04 (97) | +0.22 (26) | +0.01 (153) | -0.10 to +0.15 | 0.04 | - |

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
| zero | - | - | - | - | - | - | 0.193 |
| last_ipl | +0.23 (61) | +0.18 (66) | +0.13 (60) | +0.16 (187) | +0.05 to +0.29 | 0.13 | 0.280 |
| ipl3 | +0.23 (61) | +0.08 (72) | +0.14 (67) | +0.13 (200) | +0.01 to +0.24 | 0.12 | 0.257 |
| recent_value | - | - | - | - | - | - | - |
| pwar | +0.13 (76) | +0.19 (76) | +0.12 (70) | +0.14 (222) | +0.03 to +0.25 | 0.16 | - |
| pwar_runs | +0.13 (76) | +0.19 (76) | +0.12 (70) | +0.14 (222) | +0.03 to +0.25 | 0.16 | 0.191 |
| lw_other | +0.07 (79) | +0.10 (81) | +0.09 (64) | +0.10 (224) | -0.02 to +0.21 | 0.08 | - |
| lw_all | +0.09 (79) | +0.15 (81) | +0.15 (70) | +0.13 (230) | +0.03 to +0.25 | 0.14 | - |
| price | - | - | - | - | - | - | - |


#### pool = common, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 30.2 |
| last_ipl | +0.50 (12) | +0.01 (73) | +0.89 (6) | +0.05 (91) | -0.11 to +0.23 | 0.13 | 38.2 |
| ipl3 | +0.50 (12) | +0.02 (73) | +0.94 (6) | +0.08 (91) | -0.08 to +0.27 | 0.15 | 35.4 |
| recent_value | +0.52 (12) | -0.02 (73) | +0.89 (6) | +0.04 (91) | -0.15 to +0.22 | 0.11 | - |
| pwar | -0.03 (12) | +0.03 (73) | -0.54 (6) | -0.00 (91) | -0.16 to +0.19 | 0.14 | - |
| pwar_runs | +0.08 (12) | +0.12 (73) | +0.09 (6) | +0.11 (91) | -0.06 to +0.30 | 0.21 | 29.5 |
| lw_other | +0.18 (12) | +0.07 (73) | -0.66 (6) | +0.04 (91) | -0.12 to +0.22 | 0.06 | - |
| lw_all | +0.05 (12) | +0.08 (73) | +0.09 (6) | +0.06 (91) | -0.11 to +0.25 | 0.09 | - |
| price | -0.18 (12) | -0.03 (73) | +0.32 (6) | -0.07 (91) | -0.24 to +0.11 | -0.00 | - |

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
| zero | - | - | - | - | - | - | 0.198 |
| last_ipl | +0.29 (8) | +0.14 (46) | - | +0.14 (56) | -0.08 to +0.35 | 0.12 | 0.305 |
| ipl3 | +0.29 (8) | +0.19 (46) | - | +0.18 (56) | -0.06 to +0.37 | 0.17 | 0.251 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.12 (8) | +0.30 (46) | - | +0.16 (56) | -0.11 to +0.38 | 0.21 | - |
| pwar_runs | -0.12 (8) | +0.30 (46) | - | +0.16 (56) | -0.11 to +0.38 | 0.21 | 0.195 |
| lw_other | -0.07 (8) | +0.27 (46) | - | +0.14 (56) | -0.09 to +0.37 | 0.16 | - |
| lw_all | +0.00 (8) | +0.33 (46) | - | +0.21 (56) | -0.06 to +0.42 | 0.22 | - |
| price | - | - | - | - | - | - | - |


#### pool = auction, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 30.2 |
| last_ipl | +0.50 (12) | +0.01 (73) | +0.89 (6) | +0.05 (91) | -0.11 to +0.23 | 0.13 | 38.2 |
| ipl3 | +0.50 (12) | -0.04 (80) | +0.53 (12) | +0.02 (104) | -0.16 to +0.19 | 0.07 | 37.7 |
| recent_value | +0.52 (12) | -0.07 (80) | +0.54 (12) | -0.00 (104) | -0.19 to +0.15 | 0.05 | - |
| pwar | +0.03 (26) | +0.00 (87) | -0.41 (16) | -0.07 (129) | -0.22 to +0.09 | 0.05 | - |
| pwar_runs | -0.03 (26) | +0.07 (87) | -0.32 (16) | +0.01 (129) | -0.14 to +0.18 | 0.14 | 29.4 |
| lw_other | +0.09 (30) | -0.00 (93) | -0.29 (18) | -0.01 (141) | -0.15 to +0.12 | -0.01 | - |
| lw_all | +0.04 (30) | -0.00 (93) | -0.08 (18) | -0.02 (141) | -0.14 to +0.12 | 0.01 | - |
| price | -0.11 (30) | +0.04 (97) | +0.22 (26) | +0.01 (153) | -0.10 to +0.15 | 0.04 | - |

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
| zero | - | - | - | - | - | - | 0.198 |
| last_ipl | +0.29 (8) | +0.14 (46) | - | +0.14 (56) | -0.08 to +0.35 | 0.12 | 0.305 |
| ipl3 | +0.29 (8) | +0.06 (52) | -0.14 (7) | +0.03 (67) | -0.17 to +0.24 | 0.05 | 0.290 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.07 (16) | +0.22 (54) | -0.60 (8) | +0.09 (78) | -0.11 to +0.31 | 0.10 | - |
| pwar_runs | -0.07 (16) | +0.22 (54) | -0.60 (8) | +0.09 (78) | -0.11 to +0.31 | 0.10 | 0.199 |
| lw_other | +0.04 (17) | +0.17 (58) | -0.48 (9) | +0.07 (84) | -0.11 to +0.27 | 0.04 | - |
| lw_all | +0.09 (17) | +0.21 (58) | -0.28 (9) | +0.11 (84) | -0.07 to +0.29 | 0.08 | - |
| price | - | - | - | - | - | - | - |


#### pool = auction_os, min balls in target season = 60

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 32.9 |
| last_ipl | +0.90 (5) | +0.08 (28) | +1.00 (4) | +0.21 (37) | -0.12 to +0.49 | 0.33 | 37.9 |
| ipl3 | +0.90 (5) | -0.11 (33) | +0.43 (8) | -0.01 (46) | -0.24 to +0.23 | 0.15 | 41.0 |
| recent_value | +0.90 (5) | -0.06 (33) | +0.45 (8) | +0.04 (46) | -0.20 to +0.30 | 0.20 | - |
| pwar | +0.07 (17) | +0.16 (38) | -0.32 (12) | -0.03 (67) | -0.23 to +0.16 | 0.15 | - |
| pwar_runs | -0.23 (17) | +0.18 (38) | -0.40 (12) | -0.02 (67) | -0.22 to +0.18 | 0.14 | 29.7 |
| lw_other | +0.00 (17) | +0.12 (39) | -0.50 (12) | +0.01 (68) | -0.17 to +0.20 | -0.02 | - |
| lw_all | +0.07 (17) | +0.11 (39) | -0.31 (12) | +0.02 (68) | -0.17 to +0.20 | 0.01 | - |
| price | -0.06 (17) | +0.15 (39) | +0.31 (12) | +0.08 (68) | -0.13 to +0.28 | 0.12 | - |

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
| zero | - | - | - | - | - | - | 0.241 |
| last_ipl | - | +0.22 (19) | - | +0.26 (22) | -0.11 to +0.55 | 0.25 | 0.360 |
| ipl3 | - | +0.23 (23) | -0.10 (5) | +0.12 (30) | -0.21 to +0.40 | 0.18 | 0.334 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.28 (10) | +0.55 (24) | -0.77 (6) | +0.22 (40) | -0.06 to +0.47 | 0.18 | - |
| pwar_runs | -0.28 (10) | +0.55 (24) | -0.77 (6) | +0.22 (40) | -0.06 to +0.47 | 0.18 | 0.221 |
| lw_other | -0.08 (10) | +0.30 (25) | -0.66 (6) | +0.11 (41) | -0.14 to +0.31 | 0.06 | - |
| lw_all | -0.01 (10) | +0.44 (25) | -0.43 (6) | +0.19 (41) | -0.04 to +0.40 | 0.13 | - |
| price | - | - | - | - | - | - | - |


#### pool = auction_os, min balls in target season = 1

**total** (Spearman (n) per target year)

| predictor | 2024 | 2025 | 2026 | pooled | pooled 90% range | Pearson | MAE |
|---|---|---|---|---|---|---|---|
| zero | - | - | - | - | - | - | 28.5 |
| last_ipl | +0.71 (6) | +0.05 (37) | +0.50 (8) | +0.14 (51) | -0.08 to +0.38 | 0.16 | 34.8 |
| ipl3 | +0.71 (6) | -0.11 (43) | +0.29 (13) | -0.04 (62) | -0.24 to +0.18 | 0.10 | 36.2 |
| recent_value | +0.60 (6) | -0.06 (43) | +0.29 (13) | +0.02 (62) | -0.19 to +0.21 | 0.09 | - |
| pwar | +0.09 (21) | +0.12 (52) | -0.06 (20) | -0.03 (93) | -0.20 to +0.17 | 0.17 | - |
| pwar_runs | -0.17 (21) | +0.14 (52) | -0.15 (20) | -0.03 (93) | -0.19 to +0.17 | 0.15 | 25.9 |
| lw_other | -0.04 (21) | +0.12 (54) | -0.18 (20) | +0.02 (95) | -0.14 to +0.19 | -0.00 | - |
| lw_all | -0.01 (21) | +0.11 (54) | -0.14 (20) | +0.02 (95) | -0.14 to +0.18 | 0.03 | - |
| price | +0.07 (21) | +0.05 (54) | +0.24 (20) | +0.11 (95) | -0.05 to +0.25 | 0.13 | - |

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
| zero | - | - | - | - | - | - | 0.382 |
| last_ipl | +0.40 (4) | +0.34 (25) | +0.40 (4) | +0.32 (33) | +0.04 to +0.55 | 0.18 | 0.455 |
| ipl3 | +0.40 (4) | +0.25 (30) | -0.13 (9) | +0.15 (43) | -0.09 to +0.41 | 0.13 | 0.419 |
| recent_value | - | - | - | - | - | - | - |
| pwar | -0.33 (16) | +0.42 (34) | -0.34 (12) | +0.12 (62) | -0.09 to +0.34 | 0.04 | - |
| pwar_runs | -0.33 (16) | +0.42 (34) | -0.34 (12) | +0.12 (62) | -0.09 to +0.34 | 0.04 | 0.329 |
| lw_other | -0.07 (16) | +0.14 (36) | -0.36 (12) | -0.00 (64) | -0.18 to +0.22 | -0.05 | - |
| lw_all | -0.06 (16) | +0.29 (36) | -0.13 (12) | +0.12 (64) | -0.09 to +0.33 | 0.03 | - |
| price | - | - | - | - | - | - | - |


## 4. Phase difficulty and Indian scarcity (M10)
Variants tested with the same backtest (`models/value_variants.py`; nothing existing was changed). Rule set before looking: **keep a variant
(as an optional view, not a default) only if its pooled rho is within 0.02 of the flat one on all three neutral truths.** Improvements would
need a range that excludes zero difference; none has.

### 4a. Phase-weighted Runs Added
Method: a player's powerplay / middle / death runs added are each multiplied by a weight = (wins per run added in that phase) / (wins per run
added in all phases), fitted on IPL seasons up to X only (slope through the origin of centred win-probability-added on runs added, over
player-season-phase cells with 30+ balls; win probability from `models/win_prob.py` via `analysis/wpa.py`). Fitted weights (X = 2025; X = 2023 and 2024 are within 0.03):

| role | powerplay | middle | death |
|---|---|---|---|
| batting | 0.90 | 0.90 | 1.18 |
| bowling | 0.90 | 0.95 | 1.20 |

So a death-over run is worth about 1.2 average runs and the rest about 0.9. Mean absolute win-probability swing per ball (IPL 2023-26, x100):
death 2.17, powerplay 1.49, middle 1.43. **Stability** (correlation of a player's runs added per ball in one season with the next, IPL 2016-26,
players with 40+ batting / 24+ bowling balls in the phase; flat = 120+ / 72+ balls):

| role | powerplay | middle | death | flat (all phases) |
|---|---|---|---|---|
| batting r (n) | -0.01 (239) | 0.06 (416) | **0.22 (151)** | 0.06 (340) |
| bowling r (n) | 0.07 (322) | 0.09 (467) | **0.19 (270)** | 0.13 (416) |

Death-over value repeats better than the rest in this sample, which supports the idea that death skill is real. But as a forecaster of next
season's total it does not help (below): `ipl3_dth` (death only) is at -0.03 and the weighted total (`ipl3_ph`) is level with flat `ipl3`.

### 4b. Indian / overseas replacement
Replacement = next-season runs added per 100 balls of players who were outside their team's top 11 by matches, IPL Impact era, split by nationality
from the auction / contract / retention lists (99% of IPL 2023-26 balls have a known flag; 34.6% are overseas). Fitted on seasons up to 2025:

| role | Indian | overseas | pooled |
|---|---|---|---|
| batting, per 100 balls (balls; players) | -4.46 (4,758; 74) | -0.55 (1,467; 31) | -4.12 |
| bowling, per 100 balls | -6.09 (5,553; 62) | -7.23 (3,624; 32) | -6.54 |

Direction as Samar expects for batting (the Indian bench is weaker than the overseas bench, so an Indian batter is worth more above his
replacement), **but it is not identifiable**: overseas minus Indian replacement, bootstrap over players: batting +2.8 per 100 balls (90% range
-19 to +20), bowling -1.3 (-10 to +8). The variant applies only the Indian / overseas difference (group replacement minus pooled), so the overall
level stays as in war.py.

### 4c. Backtest of the variants
Three truths. Predictors are built from IPL seasons up to X (3-season window, Impact era). Cells: pooled 2024-26 Spearman (90% range), n.
`ipl3` = flat; `ipl3_ph` = phase weighted; `ipl3_grp` = Indian / overseas shift; `ipl3_dth` = death overs only; `ipl3_wpa` = past win probability added; `pwar` = war.py.

**truth = IPL runs added (flat); pool = all** (pooled 2024-26 Spearman, 90% range, n)

| predictor | total | bat | bowl |
|---|---|---|---|
| ipl3 | +0.12 (+0.03 to +0.20) n=371 | +0.09 (-0.02 to +0.21) n=204 | +0.16 (+0.05 to +0.26) n=200 |
| ipl3_ph | +0.11 (+0.02 to +0.20) n=371 | +0.08 (-0.02 to +0.20) n=204 | +0.16 (+0.04 to +0.26) n=200 |
| ipl3_grp | +0.11 (+0.03 to +0.20) n=371 | +0.08 (-0.02 to +0.20) n=204 | +0.15 (+0.04 to +0.26) n=200 |
| ipl3_dth | -0.03 (-0.12 to +0.06) n=371 | +0.00 (-0.11 to +0.12) n=204 | -0.00 (-0.12 to +0.09) n=200 |
| ipl3_wpa | +0.10 (+0.02 to +0.19) n=371 | +0.08 (-0.03 to +0.18) n=204 | +0.09 (-0.02 to +0.21) n=200 |
| pwar | +0.03 (-0.05 to +0.11) n=411 | -0.00 (-0.11 to +0.11) n=226 | +0.11 (+0.00 to +0.21) n=222 |

**truth = IPL runs added (flat); pool = common** (pooled 2024-26 Spearman, 90% range, n)

| predictor | total | bat | bowl |
|---|---|---|---|
| ipl3 | +0.12 (+0.03 to +0.20) n=371 | +0.09 (-0.02 to +0.21) n=204 | +0.16 (+0.05 to +0.26) n=200 |
| ipl3_ph | +0.11 (+0.02 to +0.20) n=371 | +0.08 (-0.02 to +0.20) n=204 | +0.16 (+0.04 to +0.26) n=200 |
| ipl3_grp | +0.11 (+0.03 to +0.20) n=371 | +0.08 (-0.02 to +0.20) n=204 | +0.15 (+0.04 to +0.26) n=200 |
| ipl3_dth | -0.03 (-0.12 to +0.06) n=371 | +0.00 (-0.11 to +0.12) n=204 | -0.00 (-0.12 to +0.09) n=200 |
| ipl3_wpa | +0.10 (+0.02 to +0.19) n=371 | +0.08 (-0.03 to +0.18) n=204 | +0.09 (-0.02 to +0.21) n=200 |
| pwar | +0.08 (-0.01 to +0.16) n=371 | +0.06 (-0.05 to +0.19) n=205 | +0.14 (+0.03 to +0.27) n=202 |

**truth = IPL win probability added (x100); pool = all** (pooled 2024-26 Spearman, 90% range, n)

| predictor | total | bat | bowl |
|---|---|---|---|
| ipl3 | +0.04 (-0.04 to +0.13) n=375 | +0.00 (-0.12 to +0.12) n=206 | +0.09 (-0.02 to +0.21) n=201 |
| ipl3_ph | +0.03 (-0.05 to +0.13) n=375 | -0.01 (-0.13 to +0.11) n=206 | +0.09 (-0.02 to +0.21) n=201 |
| ipl3_grp | +0.04 (-0.04 to +0.13) n=375 | +0.00 (-0.12 to +0.11) n=206 | +0.08 (-0.02 to +0.21) n=201 |
| ipl3_dth | -0.03 (-0.13 to +0.05) n=375 | -0.05 (-0.16 to +0.06) n=206 | +0.03 (-0.09 to +0.14) n=201 |
| ipl3_wpa | +0.08 (-0.01 to +0.18) n=375 | +0.11 (-0.00 to +0.22) n=206 | +0.07 (-0.05 to +0.19) n=201 |
| pwar | +0.10 (+0.00 to +0.18) n=414 | +0.08 (-0.04 to +0.19) n=228 | +0.11 (-0.01 to +0.22) n=222 |

**truth = IPL win probability added (x100); pool = common** (pooled 2024-26 Spearman, 90% range, n)

| predictor | total | bat | bowl |
|---|---|---|---|
| ipl3 | +0.04 (-0.04 to +0.13) n=375 | +0.00 (-0.12 to +0.12) n=206 | +0.09 (-0.02 to +0.21) n=201 |
| ipl3_ph | +0.03 (-0.05 to +0.13) n=375 | -0.01 (-0.13 to +0.11) n=206 | +0.09 (-0.02 to +0.21) n=201 |
| ipl3_grp | +0.04 (-0.04 to +0.13) n=375 | +0.00 (-0.12 to +0.11) n=206 | +0.08 (-0.02 to +0.21) n=201 |
| ipl3_dth | -0.03 (-0.13 to +0.05) n=375 | -0.05 (-0.16 to +0.06) n=206 | +0.03 (-0.09 to +0.14) n=201 |
| ipl3_wpa | +0.08 (-0.01 to +0.18) n=375 | +0.11 (-0.00 to +0.22) n=206 | +0.07 (-0.05 to +0.19) n=201 |
| pwar | +0.14 (+0.06 to +0.23) n=375 | +0.14 (+0.03 to +0.26) n=207 | +0.15 (+0.03 to +0.26) n=203 |

**truth = IPL runs added above the Indian / overseas replacement; pool = all** (pooled 2024-26 Spearman, 90% range, n)

| predictor | total | bat | bowl |
|---|---|---|---|
| ipl3 | +0.11 (+0.01 to +0.19) n=371 | +0.08 (-0.02 to +0.21) n=204 | +0.16 (+0.04 to +0.26) n=200 |
| ipl3_ph | +0.10 (+0.01 to +0.18) n=371 | +0.08 (-0.03 to +0.20) n=204 | +0.15 (+0.04 to +0.26) n=200 |
| ipl3_grp | +0.11 (+0.02 to +0.20) n=371 | +0.09 (-0.01 to +0.21) n=204 | +0.16 (+0.04 to +0.26) n=200 |
| ipl3_dth | -0.03 (-0.12 to +0.05) n=371 | -0.00 (-0.11 to +0.11) n=204 | -0.00 (-0.12 to +0.09) n=200 |
| ipl3_wpa | +0.10 (+0.02 to +0.18) n=371 | +0.08 (-0.02 to +0.19) n=204 | +0.10 (-0.01 to +0.22) n=200 |
| pwar | +0.03 (-0.05 to +0.11) n=411 | -0.00 (-0.12 to +0.10) n=226 | +0.12 (+0.01 to +0.22) n=222 |

**truth = IPL runs added above the Indian / overseas replacement; pool = common** (pooled 2024-26 Spearman, 90% range, n)

| predictor | total | bat | bowl |
|---|---|---|---|
| ipl3 | +0.11 (+0.01 to +0.19) n=371 | +0.08 (-0.02 to +0.21) n=204 | +0.16 (+0.04 to +0.26) n=200 |
| ipl3_ph | +0.10 (+0.01 to +0.18) n=371 | +0.08 (-0.03 to +0.20) n=204 | +0.15 (+0.04 to +0.26) n=200 |
| ipl3_grp | +0.11 (+0.02 to +0.20) n=371 | +0.09 (-0.01 to +0.21) n=204 | +0.16 (+0.04 to +0.26) n=200 |
| ipl3_dth | -0.03 (-0.12 to +0.05) n=371 | -0.00 (-0.11 to +0.11) n=204 | -0.00 (-0.12 to +0.09) n=200 |
| ipl3_wpa | +0.10 (+0.02 to +0.18) n=371 | +0.08 (-0.02 to +0.19) n=204 | +0.10 (-0.01 to +0.22) n=200 |
| pwar | +0.07 (-0.01 to +0.17) n=371 | +0.07 (-0.05 to +0.19) n=205 | +0.15 (+0.03 to +0.27) n=202 |

Reading: every variant is within 0.01-0.03 of flat `ipl3` on every truth (**passes the keep rule**) and none is better beyond noise. Against the
win-probability truth every forecaster is near 0 (best `pwar` 0.10-0.14, `ipl3_wpa` 0.08): next season's win impact is mostly luck.

### 4d. Hardik Pandya and a few others (X = 2025 weights and replacement; WAR over IPL 2023-26)
Hardik by season (`war_flat` = war.py, `war_phase` = phase-weighted runs added instead of flat, `war_group` = Indian replacement shift):

| season | bat_balls | bat_ra | bowl_balls | bowl_ra | war_flat | war_phase | war_group |
|---|---|---|---|---|---|---|---|
| 2023.0 | 253.0 | -3.8 | 144.0 | -50.4 | -0.5 | -0.44 | -0.5 |
| 2024.0 | 151.0 | -44.7 | 216.0 | -82.1 | -1.2 | -1.17 | -1.21 |
| 2025.0 | 137.0 | -26.6 | 204.0 | 33.0 | 0.13 | 0.02 | 0.13 |
| 2026.0 | 149.0 | -24.1 | 136.0 | -27.6 | -0.47 | -0.52 | -0.48 |

Totals 2023-26 for a few all-rounders and finishers:

| player | group | war_flat | war_phase | war_group |
|---|---|---|---|---|
| HH Pandya | indian | -2.04 | -2.11 | -2.06 |
| MP Stoinis | overseas | 0.49 | 0.58 | 0.24 |
| RA Jadeja | indian | 2.13 | 1.97 | 2.11 |
| S Dube | indian | 0.52 | 0.48 | 0.55 |
| SP Narine | overseas | 2.14 | 2.23 | 2.05 |
| VR Iyer | indian | 0.2 | 0.18 | 0.23 |
| Washington Sundar | indian | -1.07 | -1.05 | -1.07 |

**Hardik stays negative: -2.04 flat, -2.11 phase-weighted, -2.06 with the Indian shift.** His batting runs added at the death are negative in
2025 and 2026 (-20.7 and -32.7 runs in 82 and 59 balls), so a 1.2x death weight makes it slightly worse; his bowling is mostly middle overs and
powerplay. The Indian shift is tiny (batting -0.3, bowling +0.5 runs per 100 balls). If the case for him is "an Indian death-overs all-rounder
who frees an overseas slot", that is a roster-slot effect (what the XI looks like with and without him under the 4-overseas cap), not a
replacement-level shift, and is not measured here. Jadeja, Narine, Dube, Iyer move by 0.0-0.2 WAR either way.

### 4e. Decision
- **Phase weighting** (`ipl3_ph`; `value_variants.compare` column `war_phase`): passes the keep rule, shows no gain. Kept as an optional view only.
- **Indian scarcity** (`ipl3_grp`; column `war_group`): passes the keep rule, no gain; the replacement difference is not identifiable (range +-20 per 100 balls). Kept as an optional view only.
- Neither is wired into `runs_added`, `war`, the trade tool or the auction room; defaults are unchanged. `value_variants.compare(players)` shows the three numbers side by side.

## 5. Doubts
- Three target years, 100-140 players each: ranges for pooled rho are about +-0.1. No predictor here is good enough to rank players; bowlers and price are the only hints.
- `sy` cut: leagues that end early in year X+1 (SA20, ILT20, part of BBL) are excluded from a forecast for IPL X+1 even when they finished before it; this costs the league-weighted scores a little information.
- T20I tables include associate teams in the centring (the lead's scratch work used full members only).
- `wpa_table` is IPL only by design. Nationality comes from the auction / contract / retention lists; players missing from them get no shift.
- A bug found and fixed on the way: an early truth table dropped bowlers who never batted; all numbers here are from the fixed version.
