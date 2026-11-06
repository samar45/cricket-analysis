# Research: Moneyball v2 (2026-11-07)

Scope: why our value forecast fails and what to try next. Web claims are labelled **source** (abstract/summary only; full texts were paywalled, I did not read them), numbers about our data are **measured by us** (from `docs/VALUE_backtest.md`, not re-run here), everything else is **guess**.

## 1. What the outside world says

| Topic | Finding | Source |
|---|---|---|
| IPL price determinants | Karnik 2010 (2008 auction, 75 players): price follows runs/wickets, young players get a premium, Indian and Australian players get a premium. Karnik 2013 (2011 auction, Heckman selection correction): short-format runs, Test wickets, age, nationality matter; IPL track record changes valuations. | [Karnik 2010](https://ro.uow.edu.au/dubaipapers/250), [Karnik 2013](https://ideas.repec.org/a/jsf/intjsf/v8y2013i1p3-20.html) |
| Overbidding | Lenten, Geerling, Konya 2010: separate ability from personal traits; some evidence of overbidding, correlated with players who later turned out better (i.e. not clean "overpay = bad"). | [La Trobe WP 2010.04](https://econpapers.repec.org/RePEc:trb:wpaper:2010.04) |
| Price vs realised performance | J. Sports Analytics 8(3), 2020: hedonic price model by role, compare price with realised performance, value under a budget cap. | [JSA 2020](https://content.iospress.com/articles/journal-of-sports-analytics/jsa200580) |
| Baseball projections | Marcel: last 3 seasons weighted 5/4/3, add ~2 seasons' worth of league-average (regression to mean), small age adjustment around 29. Tango calls it the minimum bar any forecaster must beat; fancier systems only beat it modestly. | [Baseball-Reference](https://www.baseball-reference.com/about/marcels.shtml), [MLB glossary](https://www.mlb.com/glossary/projection-systems/marcel-the-monkey-forecasting-system) |
| Football league strength | Opta Power Rankings: Elo-style team ratings (results, xG when available) on a global 0-100 scale; league strength = aggregate of its teams; Opta suggests using it as an exchange rate when a player moves leagues. | [Opta Analyst](https://theanalyst.com/articles/strongest-football-leagues-in-the-world-opta-power-rankings) |
| Fitting translation from movers | Analytics FC dropped league-level exchange rates for club-level strength (ClubStrength+). An R-bloggers piece fits a model of performance change after transfer by (from-league, to-league). Twenty First Group: I found no public method. | [ClubStrength+](https://analyticsfc.co.uk/blog/2024/01/22/introducing-clubstrength-adjusting-performance-by-opponent-strength/), [R-bloggers](https://www.r-bloggers.com/2021/06/quantifying-relative-soccer-league-strength/) |
| Birth dates | Wikidata property P2697 = ESPNcricinfo player ID, P569 = date of birth. A query joining both should work; **I did not run it**. | [Wikipedia Cricinfo template](https://www.wikipedia.com/wiki/Template:Cricinfo) |

Takeaways: (1) the honest benchmark is a Marcel-style rule, and we found our fancy model is not better than "mean of last 3 IPL seasons" (rho 0.12 vs 0.09) - same lesson as baseball. (2) Aging and nationality are the standard price drivers in the IPL papers, and we have neither age nor a clean price model. (3) League factors in football are fitted from movers (or from team ratings), not hand-set.
Not found: CricViz/Cricmetric public methods for league equivalency or injury proxies (their models are proprietary); I did not find a legal free injury dataset.

## 2. Why our system fails (introspection)

| # | Reason | Evidence / confidence |
|---|---|---|
| 1 | **Target is too noisy.** One IPL season = ~100-300 balls for most batters; runs added per season is mostly luck. Batters repeat at rho ~0, bowlers 0.13-0.16 per ball. | measured |
| 2 | **Wrong target class.** We predict runs added (total), which mixes skill, role, batting position, opportunity (balls faced) and luck. Opportunity (selected? bats at 3 or 8?) is probably more predictable than skill. | guess, testable (task d) |
| 3 | **League weights hand-set** (lw_other ~0 or negative). Never validated; with hand weights the sign could even be wrong per league. | measured (score) + guess (cause) |
| 4 | **Small n on the one pair we care about** (overseas buys, n=68, price rho +0.08). Fitting on IPL-only movers wastes most mover data. | measured |
| 5 | **No age.** The IPL price papers find age matters; aging curves are the standard fix for projections. | source + guess |
| 6 | **Availability ignored.** Injuries, national duty, late arrivals decide whether a buy produces anything. No injury list. | guess |
| 7 | **Price model has no demand side.** Price ~ second-highest willingness to pay; that depends on which teams have purse, slots, role holes. Our price model = base-price baseline, role scarcity didn't help. | measured (baseline) + guess (cause) |
| 8 | **Test period is tiny:** 3 target years, 90% bootstrap ranges overlap for the top predictors. We cannot tell 0.12 from 0.05. | measured |
| 9 | **Impact-era split** (IPL 2023+ separate) shrinks the IPL sample further. | design choice, memory note |
| 10 | **SMAT 2024-25 missing** blocks the recent-form test. | measured |

## 3. Proposals

Common test harness: `cricket backtest` with one new `@predictor` per idea, same truth (IPL X+1), targets 2024-26 plus, for league-translation, any-league targets 2019-26. Always compare to `ipl3` (rho 0.12) and the Marcel-like rule below. Report rho with bootstrap range AND MAE.

### a. Fit league translation factors from movers (all leagues)
- **Build:** for every player with 60+ balls in league A in season s and 60+ balls in league B in season s+1 (or same calendar year), regress per-ball runs-added (batting rate, bowling rate separately, shrunk) in B on that in A with a league-pair or league-of-origin intercept/slope: `y_B = alpha_B + beta_{A->B} * y_A`. Use a mixed model or ridge with partial pooling so thin pairs shrink to a global beta. Output: a table of fitted league multipliers (like Opta's exchange rate) plus an uncertainty. Replace the hand weights in `lw_*`.
- **Data:** what we have (Cricsheet, 13+ leagues, players matched by Cricsheet id). Size: guess several thousand mover pairs in total (IPL-only is ~70-100/yr). Check actual count first (S step).
- **Test:** (i) fit on seasons <= X, score on movers X+1 in any league (large n, per-ball rate); (ii) then plug fitted factors into `lw_other` and rerun the IPL-only backtest. Also compare vs "no league adjustment" and vs Marcel regression.
- **Expected gain:** guess: clear gain for mover prediction in-sample-style tests (n large enough to detect), small gain on IPL overseas buys (rho 0.0 -> 0.1 at best). Confidence in a *measurable* result: high; in an *IPL payoff*: low-medium.
- **Size:** M. Catch: selection bias (players who move are the ones who did well or got picked); football literature has the same issue; mitigation = include player random effect, report as "descriptive exchange rates".

### b. Stable skill metrics, shrunk
- **Build:** batters: boundary%, dot%, balls per boundary, strike rate by phase (not runs); bowlers: dot%, boundary conceded %, wicket rate, economy; each shrunk (empirical Bayes: `(n*x + k*mu)/(n+k)`, k fitted from split-half reliability). Compose a Marcel-like score: 5/4/3 weights over three seasons in all leagues, mapped by (a).
- **Data:** ball-by-ball already in DuckDB. Zero new data.
- **Test:** first the *reliability* (split-half and season-to-season rho) of each metric -- cheap, tells which metrics are worth anything. Then predictor vs next-season IPL runs added per ball and vs rate metrics themselves (predicting boundary% is easier than predicting runs). Compare to `ipl3`.
- **Expected gain:** guess: boundary%/dot% beat raw runs in repeatability (that is the usual finding in baseball for K%/BB% over BA, so I label this analogy not measurement). Rho vs runs added maybe 0.15-0.2 for bowlers, still ~0.1 for batters.
- **Size:** S. Best cost/benefit.

### c. Team demand model for auction price
- **Build:** for each auction year and player: teams with purse >= base, open slots, open overseas slots, role hole (e.g. no death bowler, no keeper) after retentions; compute expected number of interested bidders and a "max willingness" proxy (e.g. purse left / slots left). Model price (hurdle: sold? then log price/purse share) with these plus performance and nationality, age if (e) lands.
- **Data:** we have auctions 2022-26, retentions, base price, team. Purse-left after retentions: derive from contracts (check whether ours is complete; otherwise public rules fix purse = 90 / 100 / 120 crore by year, **verify**).
- **Test:** leave-one-auction-out price MAE (5 folds: 2022-26) vs base-price baseline, plus rank correlation of residuals. Beating baseline by 10%+ MAE would be a win.
- **Expected gain:** guess: modest (5-15% MAE), because price is dominated by a few bidding wars between 2-3 rich teams, which is a sample of ~20 players per year. Confidence low-medium; n is about 5 x 25 expensive players.
- **Size:** L (feature building from partial contract data, many ways to leak, e.g. "purse left" must be pre-bid purse, not post).

### d. Availability and selection as target and feature
- **Build:** target = share of team matches played in IPL X+1 (and balls bowled/faced per match played). Features: last-season share, leagues played, age, role, overseas flag, price (higher price -> more selection). This is partly knowable from Cricsheet (a match with the player in the XI).
- **Data:** Cricsheet match XIs. No injury list; treat "missed" as unknown reason (injury, form, rotation).
- **Test:** same backtest design, truth = games-played share for players on the squad; compare `last-season share` vs fitted model; then check if adding it to a value rule (value = rate * expected balls) improves rho for total runs added vs rate-only.
- **Expected gain:** guess: opportunity is the larger component of runs-added variance; selection share rho possibly 0.3-0.5 (likely much higher than skill). That alone would lift total-runs-added forecasts. Confidence medium-high.
- **Size:** S-M. Limit: cannot separate injury from benching; squad membership (who was on the team roster) needs the auction/contract table, which we have.

### e. Age curves via Wikidata
- **Build:** pull DOB for every player with `key_cricinfo` in Cricsheet `people.csv`, via Wikidata (P2697 -> P569). Fit simple aging curve on per-ball rates (delta method, as in baseball: compare same players year over year, pooled by age) and add an age term to Marcel/hedonic price.
- **Feasibility:** one SPARQL query returning all items with P2697 and P569 should be small (guess: 5-15k rows; **not run**), free and legal. Coverage risk: Wikidata mostly has DOB for internationals and well-known IPL players; many domestic/associate players will be missing (guess 60-80% coverage of IPL/T20I players, lower for SMAT). Fallback for missing: Cricsheet doesn't carry DOB; do not scrape ESPNcricinfo/Cricbuzz. Wikipedia infobox via Wikidata is the only legal source I'd use.
- **Test:** coverage first (S). Then age term in `pwar` and in the price model; backtest rho and MAE with/without age on players with DOB only.
- **Expected gain:** guess: small for performance (age curves in T20 are flat 25-33, drop after ~35; edge is for extreme ages), moderate for price (Karnik: young premium). Confidence medium that it helps price, low for performance.
- **Size:** M.

### f. Reframe: value per crore with uncertainty, strategy simulation
- **Build:** drop "predict stars". Define realised value per crore of a buy = runs added (bat + bowl, own-season IPL, from a fixed truth definition) per crore paid, over seasons 2023-26. Score candidates with posterior mean AND interval from shrinkage (b); rule examples:
  1. buy proven bowlers (3 seasons, 1000+ balls, rate shrunk) priced below median;
  2. never pay a premium for one hot batting season (batter price > X crore and 1-season history -> skip);
  3. prefer Indian-capped fill-ins when price gap > threshold.
- **Test (simulation):** for each auction year Y (2023-26): from the list of players actually sold, apply the rule using data available before the auction, buy under a purse (e.g. the same total spent, or per-team average) in rank order, compute realised value per crore in IPL Y (+ optionally Y+1) versus (i) actual buys, (ii) random buys with the same price distribution (1000 draws), (iii) cheapest-N buys. Metric: value per crore, with bootstrap over players; need the rule to beat random AND actual with a CI that excludes zero. With ~4 years the CI will be wide; report it honestly.
- **Data:** all in hand.
- **Expected gain:** guess: bowler rule likely beats actual (bowlers are the only repeatable skill we found); "avoid hot batter" is mostly an avoided loss, may show as lower variance not higher mean. Confidence medium, because it needs only a coarse ranking, not an accurate point forecast.
- **Size:** M. Gotchas: survivorship (only sold players), counting only balls actually played (injured buy = zero value, include it), team context ignored.

## 4. Ranking (expected gain x confidence / cost; all numbers are my guesses)

| Rank | Idea | Gain | Confidence | Cost | Score note |
|---|---|---|---|---|---|
| 1 | **b** shrunk stable skill metrics (Marcel-style baseline) | medium | medium-high | S | Cheapest; also gives the honest benchmark and the uncertainty needed for f |
| 2 | **d** availability / selection | medium-high | medium-high | S-M | Probably the most predictable piece of "runs added" |
| 3 | **f** value-per-crore strategy simulation | medium | medium | M | Matches the real goal; needs b |
| 4 | **a** fitted league translation | medium (mostly measurement) | medium | M | Bigger n, replaces guessed weights; IPL payoff doubtful |
| 5 | **e** age via Wikidata | small-medium | medium (price), low (performance) | M | Do a coverage check (S) before committing |
| 6 | **c** team demand price model | small-medium | low | L | Highest realism, smallest n; defer |

## 5. Recommendation
Implement first, in this order: **b -> d -> f** (b gives metrics and shrinkage, d gives the opportunity forecast, f combines them into the Moneyball test that matters). Run the cheap sub-steps first as kill switches: split-half reliability for b, mover-pair count for a, Wikidata coverage for e. Pick a next only if the reliability table shows league effects are large; c last. Because the test window is 3 target years, treat any rho difference under ~0.05 as noise.

Not claimed: no experiment here was run; all expected gains are guesses. No code or data was changed.
