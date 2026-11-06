# M4 auction price model and M5 moneyball market check (built 2026-11-07, worker)

Code: `models/auction.py` (features, numpy ridge and logistic, evaluation, market table), `analysis/auction.py` (module `auction`, views `predict` / `market` / `player`), `viz/auction.py`, `viz/video/auction.py`, `tests/test_auction.py` (9 tests).
Saved: `models/data/auction_model.json` (all tables below plus final coefficients), `auction_features.csv`, `auction_predictions.csv` (one out-of-sample prediction per player on the block), `auction_market_players.csv` (M5, one row per buy).
Rebuild (about 20 s, reads the live DB read-only, writes only those files): `.venv\Scripts\python -m cricket_analytics.models.auction`. Nothing is committed.

## Headline (read this first)
1. **The model is a weak predictor and I will not oversell it.** On the 2026 test (fit on 2022-25, run once) its median price has a mean error of 1.88 crore; "price = base price" has 1.89 crore. It does beat a plain regression on base + caps + nationality + role (2.18 crore) and it gives honest ranges (80% range holds 84% of the 2026 prices; 90% on 2025). The sold / unsold part has **almost no skill** (2026 AUC 0.55, 2025 AUC 0.61; 0.5 = coin flip).
2. **Reputation beats performance.** Adding our WAR value, experience, or SMAT domestic value to base price + nationality + last price did not help consistently. Validation 2025: 2.08 crore (last price only) vs 2.16 (+WAR) vs 2.12 (+SMAT). Test 2026: 1.88 vs 1.84 vs 1.82. Differences of 0.05 crore on 77 players are noise. Rule used (decided before the test): a bigger feature set must beat the smaller one by 1% on validation; none did, so **S1 (base, nationality, caps, role, last price, mega flag) is the shipped model.**
3. **Moneyball check: no evidence that uncapped Indians are better value.** Their WAR per 10 crore is *below* the others (-0.15 vs +0.11 capped Indian and +0.05 overseas, 2022-25 buys). Difference uncapped minus rest: -0.23 WAR per 10 crore (95% range -0.46 to -0.004; 2.3% of resamples above 0). They are cheap, but they mostly do not play (61% got IPL balls) and those who play are slightly below average. The finding we hoped for is not in the data; see the doubts.

## 1. Data used and how it was prepared
- `reference/ipl_auctions.csv` rows with `sold` or `presented_on_block = true`: 2022 300, 2023 151, 2024 134, 2025 283 (182 sold + 101 on-block unsold; the 293 blank-status rows are left out), 2026 156 = 1,024 rows, 615 sold. `ipl_retentions.csv` feeds prior price (cycle 2022, 2025, 2026).
- **Name fixes.** 9 names the mapping missed were added (e.g. B Sai Sudharsan, Rasikh Salam). The automatic initials mapping also **joined different people**. 2026-11-07 review of all 721 `initials`-type rows (`match_basis` containing "initials"): every row was checked for surname and initials, then for plausibility against the Cricsheet record (matches, first and last year, teams, share of T20I matches, role). **60 rows (43 players) were blanked in `ipl_auctions.csv` itself** (`match_basis = none`, a note says which name was dropped); the code list `BAD_MAP` was removed. Examples: Sonu / Sanjay / Siddharth Yadav (all joined to Suryakumar), Mangesh Yadav (to Mayank Yadav), Upendra Yadav (to Umesh), Gaurav Gambhir (to Gautam), Mohammed Kaif (to the 2008-12 Mohammad Kaif), Agni Chopra (to Aakash Chopra), Vishnu Solanki and James Anderson (to England T20I players), Rajan / Ramesh / Ravi Kumar (to Vinay Kumar), and players whose "Cricsheet match" has only T20I games although the auction player is an Indian domestic (Aradhya Shukla, Smaran Ravichandran, Naman Tiwari...). Two rows the old list blanked wrongly are now kept: Prabhsimran Singh and Mayank Yadav (2022). Effect of the cleanup: test-2026 MAE unchanged (1.88 cr), sold AUC 0.547 to 0.557, validation MAE 2.124 to 2.129, uncapped-minus-rest -0.231 to -0.232 per 10 cr: **no conclusion changed**. Still unverified: spelling variants of one person (Steve / Steven Smith, Ben / Benny Howell) are kept as the same person, and N Smith (CPL 2021) was left although unconfirmed.
- **Total purse** = 10 x purse per team (90, 95, 100, 120, 125 crore). The leftover purse of a mini auction is not known, so "purse left in the room" is not a feature.
- Players of unknown nationality (52 unsold rows) count as Indian. No age feature exists.

## 2. Features (all dated before the auction)
| Feature | Source and cut-off |
|---|---|
| log base price, overseas, capped (source flag; data proxy for the sold part), Indian uncapped, role, mega auction flag | auction file; role for unsold rows comes from our data (bat vs bowl balls before the auction) because the source has none |
| last price, was it a retention, has a last price | latest deal in auctions (earlier years) or retentions (that cycle or earlier). 2022 has none (no pre-2022 prices) |
| experience: log IPL balls, log all-T20 balls, has any data | Cricsheet, seasons with sy < auction year |
| our value: shrunk batting and bowling runs added (a standard 300 / 288-ball season in wins), WAR of the last two IPL seasons | `war.fit_for(P, Y)` refits the shrinkage constants on seasons < Y; evidence rule of the project (IPL 2023+ only for 2024+, other leagues at the fitted weight). Replacement level and runs-per-win come from the saved file, which uses data to 2026 (small leak of a constant, flagged) |
| SMAT value (S4 only) | shrunk runs per ball above the SMAT mean (batting), below (bowling), log SMAT balls, matches before the auction date. The league-translation factor is a constant scale; a standardised ridge ignores constants, so it is not applied separately |
Feature sets: S0 base, nationality, caps, role, mega; S1 + last price; S2 + experience; S3 + our WAR value; S4 + SMAT.

## 3. Model
Hurdle: (a) ridge logistic P(sold | on the block), (b) ridge on log price for sold players. Penalty chosen by leave-one-auction-out CV on the training years. P10 / P50 / P90 = prediction plus the 10 / 50 / 90th percentile of the cross-validated residuals, never below the base price. Everything in numpy (sklearn is not installed).
**Two price targets** (decided on 2025 validation, not on the test):
| target | validation 2025 MAE (crore) | R2 log price | 80% range coverage |
|---|---|---|---|
| A: log rupees (log purse as a feature) | 10.4 | -0.77 | 15% |
| **B: log share of total purse (used)** | **2.12** | **0.50** | **90%** |
A fails because it trains on purses of 90-100 and must extrapolate to 120-125 for the 2025 mega. Share of purse is the right scale. (Note: on the 2026 test A would have scored slightly better, 1.84 vs 1.88 crore; that is noise on 77 players and was not used.)

## 4. Validation, 2025 mega auction (train 2022-24; 182 sold players, 258 on the block)
Price metrics are for sold players (crore); sold metrics are for all on-block rows.
| model | MAE cr | median abs % err | R2 log | Spearman | 80% cover | sold AUC | Brier |
|---|---|---|---|---|---|---|---|
| baseline: price = base | 2.54 | 41 | 0.22 | 0.78 | - | - | - |
| baseline: price = last price (131 rows) | 2.95 | 55 | 0.29 | 0.64 | - | - | - |
| baseline: OLS base + caps + nationality + role | 2.12 | 78 | 0.61 | 0.74 | - | - | - |
| baseline: share sold (70.5%) | - | - | - | - | - | 0.50 | 0.217 |
| S0 | 2.25 | 48 | 0.54 | 0.74 | 0.90 | 0.62 | 0.204 |
| **S1 (shipped)** | **2.08** | 50 | 0.56 | 0.73 | 0.79 | 0.61 | 0.220 |
| S2 + experience | 2.15 | 42 | 0.53 | 0.75 | 0.84 | 0.61 | 0.219 |
| S3 + our WAR value | 2.16 | 36 | 0.50 | 0.75 | 0.91 | 0.62 | 0.220 |
| S4 + SMAT | 2.12 | 39 | 0.50 | 0.75 | 0.90 | 0.63 | 0.223 |
On the 131 rows with a last price the S1 model has MAE 2.63 against 2.95 for "last price" and 3.18 for "base" on the same rows. Reading: the model beats the baselines on MAE; it does **not** beat "price = base" on rank (Spearman 0.73 vs 0.78) or median percentage error.

## 5. Final test, 2026 mini auction (train 2022-25, run once; 77 sold, 154 on the block)
| model | MAE cr | median abs % err | R2 log | Spearman | 80% cover | sold AUC | Brier |
|---|---|---|---|---|---|---|---|
| price = base | 1.89 | 0 | 0.14 | 0.64 | - | - | - |
| price = last price (35 rows) | 2.79 | 38 | 0.39 | 0.69 | - | - | - |
| OLS base + caps + nationality + role | 2.18 | 94 | 0.36 | 0.57 | - | - | - |
| share sold (50%) | - | - | - | - | - | 0.50 | 0.264 |
| S0 | 1.96 | 42 | 0.31 | 0.57 | 0.77 | 0.51 | 0.265 |
| **S1 (shipped)** | **1.88** | 46 | 0.35 | 0.62 | 0.84 | 0.55 | 0.258 |
| S2 + experience | 1.88 | 51 | 0.33 | 0.60 | 0.79 | 0.51 | 0.262 |
| S3 + our WAR value | 1.84 | 50 | 0.36 | 0.58 | 0.84 | 0.52 | 0.260 |
| S4 + SMAT | 1.82 | 42 | 0.33 | 0.65 | 0.88 | 0.50 | 0.261 |
S1 on the 35 rows with a last price: MAE 2.30 vs 2.79 for "last price" and 2.43 for "base". "Median abs % error" of 0 for the base baseline is real: more than half of the 2026 buys went at exactly base price (which is why it is hard to beat). Intervals: 84% of the sold prices fall in P10-P90 (target 80%).
Mega-only check: 2025 (above) is the only mega in validation; the 2022 mega is in training.

## 6. 2026 test: biggest misses (model median vs paid; reasons are what the model leans on)
**Market paid far more than the model** (paid / model median): Prashant Veer 14.2 vs 0.39 cr (36x), Kartik Sharma 14.2 vs 0.40 (35x), Auqib Nabi 8.4 vs 0.39 (21x), Mangesh Yadav 5.2 vs 0.39 (13x), Tejasvi Singh 3.0 vs 0.40 (7x), Cameron Green 25.2 vs 3.74 (6.7x), Mukul Choudhary 2.6 vs 0.40, Akshat Raghuwanshi 2.2 vs 0.38, Pathum Nissanka 4.0 vs 0.78, Jack Edwards 3.0 vs 0.60, Ben Dwarshuis 4.4 vs 1.16, Salil Arora 1.5 vs 0.40, Liam Livingstone 13.0 vs 3.54, Matheesha Pathirana 18.0 vs 5.39, Rahul Chahar 5.2 vs 1.80.
Reason visible in the features: the first nine are **uncapped Indians or low-base overseas players with a 0.3-0.75 cr base**, no last price. The model has only "base price" to go on and base price is the strongest feature (coefficient +1.13 on standardised log base). Nothing in our features (no data, SMAT included) marks them out; this is a bidding war on youth or a franchise need that our inputs cannot see. Green, Livingstone and Pathirana are real stars on a 2 cr base and the model's P90 (26, 25, 37 cr) does cover them.
**Market paid far less than the model**: Prithvi Shaw 0.75 vs 1.81 (0.41), Akash Deep 1.0 vs 1.97, Shivam Mavi 0.75 vs 1.36, Anrich Nortje 2.0 vs 3.59, David Miller 2.0 vs 3.37, Hasaranga 2.0 vs 3.37, Rachin Ravindra 2.0 vs 3.28, Rahul Tripathi 0.75 vs 1.16, Jamieson 2.0 vs 3.07, Hosein 2.0 vs 3.07, Finn Allen 2.0 vs 3.00, Ngidi 2.0 vs 3.00, Matt Henry, Jacob Duffy, Tom Banton (2.0 vs 2.9). Reason: they **all sold at base price**; the model lifts them because of a high last price (Shaw 7.5, Akash Deep 8.0, Miller 7.5 cr) or a 2 cr base. The model does not know that the market had a short supply of bids in 2026 (only 77 sold).
Lesson: the model's median is a typical price; individual bidding outcomes are well outside it. Use the range.

## 7. Moneyball market check (M5)
For each buy in the 2022-25 auctions (538 players) plus the 2022 and 2025 retentions (73; the six 2022 new-team draft picks are excluded), WAR in the IPL season of that auction (a bench player counts 0). "WAR per 10 crore" = total WAR / total crore x 10 (ratio of sums), 95% bootstrap over players (4,000 draws). "Surplus" = WAR minus price / 234 (crore per win actually paid across all 2022-25 buys, so the pooled mean surplus is zero by construction; note this is more than twice the roughly 100 crore a win costs in the 2025 trade-market fit, because many buys never play). 2026 buys are available with `include_2026`.

By type (2022-25, auctions plus retentions):
| type | players | crore | WAR | WAR / 10 cr | 95% range | played IPL | mean surplus |
|---|---|---|---|---|---|---|---|
| capped Indian | 135 | 1,015 | +10.8 | +0.107 | 0.016 to 0.204 | 90% | +0.048 |
| overseas | 206 | 995 | +5.1 | +0.051 | -0.054 to 0.156 | 81% | +0.004 |
| uncapped Indian | 270 | 378 | -5.7 | -0.152 | -0.367 to 0.056 | 61% | -0.027 |
Uncapped minus all others: **-0.23** WAR per 10 cr (range -0.46 to -0.004). Counting only players who played (165 uncapped): -0.26 (-0.53 to -0.003). By price band, the uncapped-minus-rest gap is negative in every band (to 0.5 cr: -1.9, range -4.1 to +0.04; 0.5-2 cr: -0.23, -0.82 to +0.33; 2-8 cr: -0.11, -0.36 to +0.16), so the result is not just "cheap players play less".
By price band: **over 8 cr +0.115** (0.041 to 0.196; 106 players, 99% played), 2-8 cr +0.019 (-0.10 to 0.14), **0.5-2 cr -0.369** (-0.65 to -0.09; 146 players), to 0.5 cr -0.07 (-1.0 to 0.9, 209 players). The expensive stars pay off; the middle band (0.5-2 cr) loses wins per crore, for uncapped Indians (-0.54) and overseas players (-0.42) alike.
By kind: retained +0.124 (0.011 to 0.239, 73 players), mega auction -0.007, mini auction +0.028 (both ranges contain 0). By role the only separated group is all-rounders (-0.113, -0.25 to +0.03; weakly negative); batters -0.01, bowlers +0.074, keepers +0.089 (all ranges contain 0). Retained players have no role listed, so they sit in the "unknown" row (+0.127).
Per year the uncapped Indian result is not stable: 2022 -0.31 per 10 cr (99 players), 2023 -0.54 (41), 2024 +0.02 (34), 2025 +0.01 (96). Best uncapped buys: Sai Sudharsan 2025 (retained, 8.5 cr, WAR +1.2; he counts as uncapped only through the proxy), Mohsin Khan 2022 (0.2 cr, +1.1), Avesh Khan 2022 (10 cr, +0.8), Shashank Singh 2024 (0.2 cr, +0.7), Swapnil Singh 2024.
### 7b. Fairer replacement: against the cheapest alternative (added 2026-11-07)
WAR is measured against the league average, so a below-average cheap player shows negative value. A realistic alternative is "fill that roster slot with a base-price buy": per cycle, the mean WAR of buys with base <= 0.3 cr sold at base (2022: 54 players, mean -0.019 WAR; 2023: 28, -0.019; 2024: 24, +0.033; 2025: 46, -0.025; only 35-58% of them got any IPL balls). Each buy's WAR above cheapest = WAR minus that cycle mean; per 10 cr = sum / total crore x 10, 95% bootstrap over players (the cycle mean is taken as known). Retained players are their own group here (in 7 above they sit inside the types).
| group | players | crore | WAR / 10 cr vs average | 95% range | WAR / 10 cr vs cheapest | 95% range | played IPL |
|---|---|---|---|---|---|---|---|
| capped Indian (auctions) | 99 | 552 | +0.098 | -0.03 to 0.24 | +0.129 | 0.003 to 0.269 | 88% |
| overseas (auctions) | 188 | 769 | +0.005 | -0.12 to 0.12 | +0.036 | -0.08 to 0.15 | 79% |
| retained | 73 | 799 | +0.124 | 0.01 to 0.24 | +0.145 | 0.03 to 0.26 | 99% |
| uncapped Indian (auctions) | 251 | 267 | -0.209 | -0.47 to 0.06 | -0.078 | -0.34 to 0.19 | 59% |
Share who got any IPL balls, by price band (players in brackets): uncapped Indian to 0.5 cr 49% (172), 0.5-2 cr 74% (42), 2-8 cr 84% (32); overseas 62% (21), 71% (79), 86% (59), over 8 cr 100% (29); capped Indian 62% (16), 84% (25), 97% (31), 96% (27); retained 96% (28) and 100% (45) at 2-8 and over 8 cr.
**Plain conclusion.** The cheapest-alternative view helps uncapped Indians (-0.21 becomes -0.08, and the range now includes 0), because buying a cheap player who rarely plays is not a loss against the next cheap player who also rarely plays. It does not turn them into a bargain: the estimate is still below capped Indians (+0.13) and retained players (+0.145), and no range for uncapped Indians is clearly above 0. So the first reading stands ("no evidence that the market under-prices uncapped Indians as a type") but is softer: "no worse than the cheapest alternative, not better". The cheap-alternative WAR is almost 0 in every cycle (-0.03 to +0.03), so the choice of replacement only moves results by about 0.1 per 10 cr; the range for each group is wider than that.

**Reading for the Brentford idea:** the market did not under-price uncapped Indians in 2022-25 on average; a handful of cheap hits (Mohsin Khan, Shashank Singh) are offset by many who never play. A better search would target *which* uncapped players, not the type. Samples: every group above has 100+ players except the flagged ones (capped Indian to 0.5 cr 16, uncapped Indian over 8 cr 9: `small_sample`).

## 8. Decisions
1. Share-of-purse target (B) over log rupees (A) - A extrapolates badly (MAE 10 cr).
2. Feature set by a 1% validation rule: S1 shipped. S3 (our WAR) and S4 (SMAT, as requested by the lead) are reported in the ablation but not used.
3. Out-of-sample predictions saved for every row: 2022-24 leave-one-auction-out, 2025 from the 2022-24 fit, 2026 from the 2022-25 fit (`prediction` column). Pool predictions for a future auction need a feature row built from the same code; not wired (M7).
4. Prior price uses the latest deal before the auction; "released by that team" is not separate (everyone in the pool with a last price was released or not retained).
5. Role: for the sold model only data-derived roles and a data proxy for caps are used, so sold and unsold rows are described identically.

## 9. Doubts and gaps
- 77 sold in the test: differences of 0.05 crore between feature sets are noise. The test is one mini auction.
- The unsold lists contain only players who went under the hammer, and only those. Sold-vs-unsold is therefore a narrow question, which likely explains the AUC near 0.5; it is not evidence that nothing predicts who is picked.
- WAR for batters has no out-of-sample skill (docs/VALUE_step3.md), so a null effect of "our value" on price is partly just a noisy input.
- Name mapping: 43 wrong initials matches were found and blanked (see section 1); a wrong match with a unique name and a plausible record would still pass. 52 uncapped "unmapped" buys count as 0 WAR (none of the unmapped sold players showed up as unmatched IPL players of that season in my check, so this is probably right).
- Capped flag for retained players is a data proxy (any T20I before the season); it misses ODI/Test-only players (for example Sai Sudharsan 2025 counts as uncapped).
- Single-season WAR is mostly luck; 2022-era WAR uses the older runs-per-win (91) and replacement.
- Not done: Heckman correction, age, pool Spearman across sold and unsold, a 2027 pool.
