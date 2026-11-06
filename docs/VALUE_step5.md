# Step 5: IPL trade tool (option A: recent value, honest ranges, no playoff or title odds)

Built 2026-11-06. Everything is **measured by us** (Cricsheet ball-by-ball to 2026-05-31, contracts from `reference/ipl_contracts.csv`) unless marked guess.
Code: `models/trade.py`, `analysis/trade.py` (module `trade`), `viz/trade.py`, `viz/video/trade.py`, `tests/test_trade.py` (22 tests, 2 need the real DB).
Saved data: `models/data/trade_match_ra.csv` (7,932 rows: runs added, balls and batting position per player per match, IPL 2023-26; rebuild `python -m cricket_analytics.models.trade`, about 3 s). With that file the tool needs no database.
Use: `cricket run trade --team "Mumbai Indians" --team2 "Rajasthan Royals" --give "Hardik Pandya" --get "Yashasvi Jaiswal, Yash Raj Punja"`; `--view squad` lists one squad; `--baseline before_trades` undoes the announced trades of the named players first. The dashboard (Explore, experimental) drives it: team and team2 are fixed lists of the ten teams, give and get are multiselects filled from the chosen team's contract players.

## Headline
1. The tool shows **recent value** (what a player delivered in the Impact Player era), not a forecast. Our own tests (VALUE_step3) say batters' projections have no out-of-sample skill and team win share is mostly luck, so there are **no playoff or title odds**. A check of the recent value itself: it predicts next season's WAR with r 0.13 and slope 0.17 (218 player-seasons, targets 2025 and 2026). About a sixth of a season's value repeats. A verdict therefore describes the past evidence, not the future.
2. Every number carries a range (10th to 90th percentile of 400 bootstrap draws over the player's own matches). A swap whose range straddles 0 is "too close to call".
3. **Market price: 44.7 crore per win** (what the ten squads paid on average per win above replacement). Salary is only loosely tied to recent value (R^2 0.08), so this is a price paid, not what a win is worth.
4. Of the three requested cases, only Pant for Kuldeep gives a verdict that excludes "too close to call" on both sides; the Hardik trade changes nothing in either best XII (Jaiswal's recent value is negative).

## 1. Player value (what is counted)
- Source: WAR (`models/war.py`) rebuilt per match. `trade_match_ra.csv` reproduces season WAR exactly (max difference 3e-7 for 819 player-seasons; test on Bumrah 2024). Runs per win 99.3, replacement level from the WAR params (batting 0.0, bowling -3.3 runs per 100 balls).
- **Recent value** (wins above replacement per season) = sum over seasons of weight x season WAR / sum of weights, weights 2026:4, 2025:3, 2024:2, 2023:1, over the seasons **from the player's first Impact-era IPL season to 2026**. A season a veteran missed counts as 0 (replacement); seasons before debut are not counted, so a 2026 debutant is not shrunk (Suryavanshi 1.07 = his 2026 WAR). Batting and bowling parts are kept separate (`bat_value`, `bowl_value`); the total is their sum.
- **Why 4/3/2/1 (judgement, simple)**: a backtest (predict 2025 and 2026 total WAR from earlier Impact-era seasons, 218 player-seasons with 100+ balls in the target): last season only r 0.076; equal weights 0.128; 4/3/2/1-style linear 0.128; steep 8/4/2/1 0.121. Using several seasons beats using the last one; the exact weights make no measurable difference, so I kept a simple decay. Fitting weights would be fitting noise.
- **Bowlers' pWAR** (the validated projection, r 0.32 for bowlers) is shown beside the recent value (`bowl_pwar`) but **not** added into the XII value: pWAR is shrunk (top 0.5 wins) and recent value is not, so mixing them would need a scale judgement I cannot validate. Use the column to see whether a bowler's recent value is far above what a projection supports.
- **Range**: bootstrap. For each player and season his matches are resampled with replacement (the same resample feeds batting and bowling), WAR is recomputed, the recency weights applied; 400 draws. The median player's range is 0.26 wins wide (355 players). It captures luck in the matches he played; it does **not** capture role changes, injuries, age (no age data), or fielding (not in WAR).
- **No IPL evidence since 2023** (new signings, uncapped; 34 of 247 squad rows): value 0 (replacement), flagged "no IPL evidence" in `role`/`notes`; nothing invented from other leagues. Their range is the spread of past debutants' first-season WAR (147 players, SD 0.31) centred on 0.
- Draws are fixed per player (same player = same draws in every squad), so shared players cancel out of a before/after difference.
- Selection optimism: the XII is chosen on point values and then scored on draws, so ranges of an XII are slightly optimistic (not corrected).

## 2. Market: rupees per win
Salary (2026 price, crore) against recent value, players with IPL evidence and 5+ matches since 2023 (n = 179):

| method | result |
|---|---|
| OLS: (salary - 0.30 base) on value | 6.4 crore per win, intercept 5.4, r 0.28, **R^2 0.08** |
| **Ratio (used)**: total (salary - 0.30) of all 247 squad players / total positive recent value | 1,065 cr / 23.9 wins = **44.7 crore per win** |

The two disagree by a factor of 7 because salary hardly follows value (a flat 5 crore for any regular plus huge fees for stars). I use the ratio (what the market actually paid per win, bench included) and say so. 0.30 crore = base price of an uncapped player = cost of a replacement.
- **Surplus** (crore) = recent value x 44.7 - (salary - 0.30). **Value per crore** = recent value / salary. A team's value per crore = best-XII value / salary of those 12.
- **Net value of a swap** (crore) = surplus of the incoming players minus surplus of the outgoing, at the new salaries.

## 3. Best XII (judgement calls, all in `pick_xii`)
- XII = XI + impact player. Search: swap hill-climb from the top-valued 11 plus 30 random starts (no ILP library), penalising rule breaks. Not guaranteed optimal; a test checks that losing a player never raises the XII value on three squads.
- Rules for the **XI**: at most 4 overseas; a keeper from the **reviewed list only** (a "yes", else a "sometimes"; if the squad has none, the rule is skipped and a note says so; derived guesses never count); at least 5 bowling options with at least 20 overs of capacity; at least 6 usual top-seven batters (average position 7.0 or better, 5+ batting matches).
- Bowling option = bowled in 30%+ of his matches and averages 1+ over when he does; capacity = his usual spell rounded up (3.2 average means he can bowl 4), at most 4.
- **Impact player** = best remaining player with value above 0; an Indian if the XI already has 4 overseas (judgement from the "4 overseas on the field" rule; an overseas impact player replacing an overseas player would also be legal, so this is slightly strict); counted at **half weight** (guess: he plays about half a match).
- Slot weighting: **not added**. WAR already scales with a player's balls faced and bowled in his usual position; weighting slots again would count usage twice. Slots (keeper, opener 1-2, middle 1-3, finisher, pace 1-3, spin 1-2) are used only for holes.
- **Hole** = a slot where the team's best available player is below the **league median** for that slot (median over the ten squads; the mean would flag most teams because values are skewed), or nobody qualifies. Membership uses usual batting position (opener <= 2.5, middle 2.5-6.5, finisher above 6.5, 5+ matches) and the reviewed bowling type (pace/spin). A player may fill several slots. Holes are listed before/after; created/filled shown. About half of all slots are "holes" by construction, so read a created/filled hole, not the count.
- Known weakness: the XII ignores reputation. A star with poor recent form (Rohit Sharma -0.51, Hardik -0.44, Jaiswal -0.25) can sit outside the best XII, and a trade involving him then reads as "no change" for the XII (money still moves; see net value).

## 4. Trade evaluation
For team A (gives X, gets Y) and B: XII value before and after with range, change with range and the share of draws in which the change is positive (`p_better`), salary of the squad before/after (purse freed = old minus new), value per crore, holes. Verdict from `p_better`: 80%+ "likely better", 20%- "likely worse", between "leans better/worse", and **"too close to call" when the 10-90 range of the change contains 0 and p_better is 30-70%**; "no change to the best XII" when neither XII changes. A moved player takes the price on his `traded_in` contract row if the file has one (a real announced trade), else keeps his salary. Squad size outside 18-25 is flagged.

### Case (a): Pant LSG to DC (27 to 15 cr), Kuldeep DC to LSG (baseline: announced trades undone)
| | XII before | XII after | change (10-90) | p better | purse | net value | verdict |
|---|---|---|---|---|---|---|---|
| LSG | 1.04 | 1.49 | **+0.45** (+0.03 to +0.85) | 0.92 | +13.75 cr freed | +35.7 cr | likely better |
| DC | 1.93 | 1.40 | **-0.54** (-1.03 to +0.03) | 0.11 | -1.75 cr | -23.7 cr | likely worse |
Pant's recent value is -0.07 (2024 +0.62, 2025 -0.40, 2026 -0.17) for 27 cr; Kuldeep's +0.41 (2025 +1.26, the rest about 0). Both are driven by one good season of Kuldeep. LSG's lone extra benefit is a spin slot filled; DC opens a spin 1 hole. The real trade cut Pant's price to 15 cr, which the tool uses. Reading: on recent value the swap favoured LSG; the DC side's range only just includes 0. Pant's keeping value is not in the model (no fielding or keeping credit).

### Case (b): Natarajan DC to SRH (10.75 to 5 cr), Zeeshan Ansari SRH to DC (0.40 cr) (Pant/Kuldeep trade kept in place)
| | XII before | XII after | change | p better | purse | net value | verdict |
|---|---|---|---|---|---|---|---|
| DC | 1.62 | 1.40 | -0.22 (-0.45 to +0.01) | 0.11 | +10.35 cr freed | +0.5 cr | likely worse |
| SRH | 2.95 | 2.97 | +0.02 (-0.08 to +0.11) | 0.62 | -4.60 cr | +5.3 cr | too close to call |
Natarajan's recent value is +0.05 (one good 2024), Ansari's -0.17 (2025 only). DC's XII drops because the bowling-options rule forces a bowler into the XI and Ansari is the weaker one; DC frees 10.35 cr, which the XII value ignores. SRH changes nothing measurable (Natarajan becomes the impact player).

### Case (c): the screenshot hypothetical, MI gives Hardik Pandya, gets Yashasvi Jaiswal (18 cr) + Yash Raj Punja (0.90 cr in our file; the screenshot's 0.30 is probably a different price) from RR (current squads)
| | XII before | XII after | change | purse | net value | verdict |
|---|---|---|---|---|---|---|
| MI | 2.69 | 2.69 | 0.00 | -2.55 cr (pays more) | +5.4 cr | no change to the best XII |
| RR | 2.32 | 2.32 | 0.00 | +2.55 cr | -5.4 cr | no change to the best XII |
None of Hardik, Jaiswal or Punja is in either best XII (recent values -0.44, -0.25, -0.02), so on recent value nothing changes; what moves is money (MI 122.7 to 125.25 cr, squad 26 players = over the limit of 25, flagged). In the earlier test version Hardik was forced into the XI by the bowling rule and the swap looked +0.35 for MI; the final rule (capacity rounded up) lets MI field a legal XI without him. **This case shows the main limit**: the website ranks Jaiswal at 2.08 projected WAR, we rank him -0.25 recent value (2023 +0.92, 2026 -0.76); our scale and theirs differ (VALUE_step3 section 8), and a one-season dip dominates a 4/3/2/1 average.

## 5. Caveats and doubts
1. **Contracts**: retained totals of CSK, DC, KKR and RR do not reconcile with iplt20.com (2.0 to 6.0 cr), so those salaries are less certain; there are no retention or release lists. **Re-run after the 17 Nov 2026 retention deadline** (and after the mini-auction). 34 squad rows have no IPL evidence (new or uncapped players, or no Cricsheet name).
2. **Batter values are recent form, not skill** (r 0.06 projected; recent value r 0.13 over 218 player-seasons). Do not read a 0.3 difference as ability.
3. **No fielding, no keeping value, no age, no overseas-availability or injury model.**
4. **Reviewed list gaps**: no keeper is listed for KKR or PBKS (rule skipped; they would be Seifert/Allen, Prabhsimran/Inglis types), RR has only a "sometimes". Adding keepers to `player_overrides.csv` fixes this. Bowling-type slots only count reviewed bowl types.
5. Market price (44.7 cr per win) rests on one season of salaries and a squad total (about 24 positive wins); OLS gives 6.4 cr per win with R^2 0.08. Surplus and "net value" in crore depend entirely on which you pick.
6. The impact-player weight (0.5), the 20-over and 5-bowler rule, the 6-batter rule and the hole definitions are my judgement; changing them moves XII values by a few tenths of a win.
7. Search is a heuristic, ranges are slightly optimistic (selection on point values), and 400 draws give percentiles good to about 0.02.
8. Ideas (not built): put a "must play" toggle for named stars; a keeper column in the reviewed list; an auction-budget view for the 16 Dec mini-auction.
