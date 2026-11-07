# Plan: Moneyball for the IPL (Samar, 2026-11-06)

Idea: do what Moneyball (Oakland A's), Brentford, Brighton and Bournemouth did — find skills the market under-prices,
especially **uncapped Indian / domestic players** (the cheap "unknown commodity"), and price players by **supply and demand**
(how many teams need a type of player vs how many such players are in the auction pool).
Rule for every step: a model/feature is kept only if it beats simpler baselines **out of sample** (earlier years → later years).
Lead (Opus) has Samar's OK to make decisions and run workers; Samar watches via Remote Control. If tokens run out, resume
from the table below (`docs/JOURNEY.md` §6 points here).

| # | Step | What "done" means | Size | Status |
|---|---|---|---|---|
| M0 | E2E test of the value chain | `docs/E2E_value.md` pass/fail + bug list; bugs fixed | S-M | done (docs/E2E_value.md; F1-F6 fixed (F5 kept as a labelled no-change)) |
| M1 | Auction data 2022-2026 | `reference/ipl_auctions.csv` (+ unsold) + `ipl_retentions.csv`, sourced, checked | M | done (docs/VALUE_auctions.md) |
| M2 | Better player value (research top picks) | stability table per component; component (Marcel-style) projection; "FIP for cricket" (dot/boundary-based, wickets shrunk); keep only what beats current pWAR on next-season holdout | M | done (docs/VALUE_m2.md) |
| M3 | Domestic data (SMAT etc.) | check Cricsheet for Syed Mushtaq Ali Trophy / other domestic T20; ingest into a DB copy; league-translation factor (domestic → IPL), measured on players who played both | M | done (docs/VALUE_m3.md) |
| M4 | Auction price model | hurdle model: P(sold) then price; features base price, capped, overseas, role, recent value, prior price, mega/mini, purse; train 2022-24, validate 2025, test 2026; baselines price=base / last price | M | done (docs/VALUE_m4.md) |
| M5 | Moneyball market check | WAR per crore by player type (uncapped Indian, overseas, role, phase specialist) in the seasons after each auction → which types the market under/over-pays | S-M | done (docs/VALUE_m4.md (7b: vs cheapest alternative)) |
| M6 | Supply and demand | role taxonomy (opener, middle, finisher, PP pace, death pace, middle spin, keeper); team needs after retentions vs auction-pool supply → scarcity index per role; test: did scarcity raise prices in 2022-26? | M | done (docs/VALUE_m6.md) |
| M7 | "Auction room" page | auction pool with predicted price range, value, scarcity, bargain flag; uncapped scouting list | M | done (dashboard/auction_room.py (page 'Auction room')) |
| M8 | Re-run with real 2027 data | after retentions (17 Nov 2026) and auction (16 Dec 2026) | S | waits for dates (17 Nov, 16 Dec 2026) |
| M9 | Backtest | generic "data up to X -> IPL X+1" tool (`cricket backtest`), baselines, pooled tables | M | done (docs/VALUE_backtest.md) |
| M11 | Marcel-style stable skill | 5/4/3 seasons, parts shrunk by own k; `marcel*` predictors | S | done: marcel_ipl rho 0.15 vs ipl3 0.12 (noise), MAE not below pwar_runs; optional only (docs/VALUE_moneyball_v2.md) |
| M12 | Availability | truth `share`/`balls`, share predictors, rate x opportunity | S | done: share rho 0.54 (price 0.42 for overseas buys); rate x opportunity no gain |
| M13 | Buying-strategy simulation 2023-26 | rule buyers vs actual vs 1000 random, simple rules | M | done: model buyer 49th percentile of random, value-per-crore rule 0.1th, actual 60th; no rule beats random |
| M14 | Demand model | lot-by-lot replay of purses, slots, role holes; demand features in the price hurdle | M | done: helps 2024/2025 (2025 MAE 2.08 to 1.82), hurts 2026 test (1.88 to 1.96); not adopted; bidding war +4% per interested team after controls |
| M10 | Phase difficulty + Indian scarcity | fitted phase weights and Indian/overseas replacement, kept only if backtest no worse; Hardik before/after | M | done: both pass keep rule, no gain, optional views only (docs/VALUE_backtest.md section 4) |

Out of scope unless Samar asks: paid data, scraping banned sites, line/length/shot data.
