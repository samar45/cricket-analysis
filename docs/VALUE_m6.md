# M6: supply and demand in IPL auctions 2022-2026 (built 2026-11-07, worker; not committed)

Code: `models/scarcity.py` (rebuild `python -m cricket_analytics.models.scarcity`, reads the live DB read-only, which now includes SMAT), module `scarcity` (views `auction`, `team_needs`, `2027`), `viz/scarcity.py`, `tests/test_scarcity.py` (10). Outputs in `models/data/`: `scarcity_usage.csv` (input counts), `_players`, `_demand`, `_index`, `_teams`, `_tests`, `_squad_check`, `_2027`, `_2027_teams`. For the auction-price model: `scarcity_for(player_roles, auction_year, kind="relative")` (1.0 = the auction's average role; `"log"` and `"raw"` also; year 2027 = provisional).

## Answer first
**Scarcity did not raise prices detectably.** Price of sold players (n = 615, auction fixed effects, 1,000 bootstrap draws): +1 SD of role scarcity changes log price by -0.04 (about -4%; 90% interval -10% to +2%). Without fixed effects: -0.045 (-10% to +2%). P(sold): -0.4 points (-2.5 to +1.7; 1,024 players on the block). Out of sample (train on earlier auctions only, no fixed effects): adding scarcity changes the log-price error (RMSE) by 0.002 (2024), 0.000 (2025), 0.003 (2026); only 2024's interval excludes 0, and by 0.002, which is nothing. The null is not proof of no effect: the index rests on 5 auctions, 9 roles, and only 52-79% of the pool gets a role. What does explain price: base price (elasticity 1.33), capped (lower than an uncapped player of the same base and role, -0.44), overseas (lower, -0.31). Recent value (our simple rate) has no detectable effect once base price is in.

## Role taxonomy (from usage, not labels)
Window: the 3 calendar years before the auction (year weights 3/2/1 for value). Source: IPL if the player has >= 5 IPL matches in the window, else other men's T20 (T20I, BBL, PSL, CPL, SA20, Blast, SMAT) if >= 5 matches there, else no role. A player can fill several roles; "can fill" = weight >= 0.25.
- Batting: factor f = min(1, balls faced per match / 10), needs >= 5 innings. Weight = f x share of his innings entered at position 1-2 (opener), 3-4 (top_order), 5-6 (middle), 7-8 (finisher). Position 9+ is tail = no role.
- Bowling: factor f = min(1, overs per match / 2), needs >= 60 balls. Pace (reviewed list only): pp_pace / mid_pace / death_pace = f x share of his balls in overs 1-6 / 7-15 / 16-20. Spin: weight f in all phases (spin is mostly middle overs, phase not split); `w_spin_finger` (off, orthodox) and `w_spin_wrist` (leg, left-arm wrist) are sub-labels, scarcity is for `spin` as a whole. Bowlers with no bowling type on the reviewed list get `w_bowl_untyped` (2-6% of the pool) and no role (owner's rule).
- Keeper: reviewed list only, yes = 1, sometimes = 0.5.
- Overseas vs Indian: from the auction file (blank -> from country, else Indian). Capped: from the auction file (blank = not capped, with a dummy in the regression). Supply and index are also given split by origin (`index_overseas`, `index_indian`); capped vs uncapped is a regression control, not a separate supply.
- Recent value: runs above the league-competition-year average per 100 balls (a wicket = 20 runs), shrunk toward 0 by adding 300 balls. A simple proxy, NOT pWAR, so that it exists for every year and league; it is not translated across leagues (the SMAT translation table was not applied).

## Demand (per team, before each auction)
- Squads: 2022, 2025, 2026 = real retention lists. 2023 and 2024 have none: squad = previous roster (retained + bought) minus everybody put up again. Check on 2026 (roll-forward vs the real list): 148 of 173 real names found (recall 86%), 148 of 188 derived names correct (precision 79%). Gaps: trades, retirements, mid-season replacements, released players who were not put up. Prices carry over, so purse left = cap (90/95/100/120/125 cr; 2027 assumed 125) minus squad prices.
- Need = best-XII slots (keeper 1, opener 2, top order 1, middle 2, finisher 1, pp pace 1, mid pace 1, death pace 1, spin 2; like `trade.SLOTS` but by data role) that are empty or below the league median slot value (median over the ten teams, empty = 0, same rule as `trade.league_slot_means`; trade.py itself is untouched). Scaled down if need exceeds open squad places (25 minus squad). Weighted by purse (purse left / median purse left, clipped 0.1-3). The 8-overseas cap splits demand between the overseas and Indian pool.

## Supply and index
Supply = players with `presented_on_block = true` who can fill the role; quality supply = those with recent value >= the league median for the role (IPL-sourced players who can fill it in that window). Index = demand / (quality supply + 1); relative index = index / geometric mean over the 9 roles (log version centred on 0). Players with no usable usage (mostly unknown uncapped players) count in no supply: 79 / 68 / 71 / 66 / 52% of the pool were classified in 2022-2026. SMAT was available as a source for uncapped players; it helped little (2026: 35 of 156 got a role from non-IPL data, 75 still none).

## Per auction: three scarcest and three most plentiful roles (index; average price of sold players whose main role it is; n sold)
| Year | Scarcest | Most plentiful |
|---|---|---|
| 2022 mega | keeper 1.17 (5.7 cr, 9); finisher 0.64 (3.5, 5); spin 0.64 (2.9, 29) | pp_pace 0.15 (3.0, 37); death_pace 0.14 (4.7, 9); top_order 0.12 (2.9, 23) |
| 2023 mini | keeper 1.83 (10.6, 2); middle 0.82 (3.0, 5); spin 0.78 (0.9, 11) | death_pace 0.35 (0.3, 1); pp_pace 0.27 (3.0, 14); top_order 0.20 (1.3, 9) |
| 2024 mini | spin 0.84 (1.3, 4); keeper 0.63 (none sold); opener 0.42 (5.4, 2) | mid_pace 0.15 (7.3, 4); pp_pace 0.15 (4.3, 18); top_order 0.09 (3.7, 9) |
| 2025 mega | keeper 1.35 (11.6, 6); spin 0.92 (3.8, 20); middle 0.74 (2.4, 14) | death_pace 0.33 (6.5, 6); top_order 0.22 (5.4, 21); pp_pace 0.21 (5.2, 33) |
| 2026 mini | middle 1.82 (2.5, 2); finisher 1.72 (2.4, 2); spin 1.66 (5.9, 5) | top_order 0.98 (4.2, 5); pp_pace 0.58 (1.6, 8); mid_pace 0.33 (7.9, 4) |

Keepers look scarcest in four of five auctions and fetched the highest average prices (5.7 to 11.6 cr) in 2022, 2023 and 2025, but only 2-9 keepers sold per auction and the reviewed keeper list is incomplete (supply understated), so this is the one place pattern and index agree and also the least trustworthy. Elsewhere there is no consistent link (2024's plentiful mid_pace sold at 7.3 cr, n = 4; 2026's scarce middle/finisher at 2.4-2.5 cr, n = 2 each). Cells hold 1-37 players.

## 2027 forward view (PROVISIONAL until retentions, 17 Nov 2026)
Today's squads are full (23-25 each), so the open-places cap would zero everyone's need; the forward view counts weak or empty best-XII slots (what a team would fix by releasing someone), purse-weighted, against an assumed quality supply (median of the 2023, 2024, 2026 mini auctions). Provisional relative index: keeper 2.4, spin 1.4, middle 1.3, opener 1.0, pp/mid/death pace 0.8-0.9, finisher 0.8, top_order 0.5. Teams with the most weak slots: DC 10, MI 9, KKR 8, PBKS 8 (`scarcity_2027_teams.csv`); KKR has the most purse left (36.6 cr), MI the least (2.3). Squads include only the announced trades. Re-run after the retention list and again once the pool is announced (supply known, assumption dropped).

## Gaps and cautions
- Squads before 2023 and 2024 are derived (above). The 2025 unsold list has 293 unconfirmed rows that are NOT in the pool.
- Keeper list incomplete; keeper scarcity overstated.
- Exposure weights a player's roles (>= 0.25) by their usage weights; a main-role-only version was not run.
- The index counts the player himself in supply (a small mechanical overlap); 5 auctions only; no multiple-testing correction.
