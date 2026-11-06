# Research: value, projection and auction methods worth adding (2026-11-06)

Labels: **[src]** = measured/stated in the cited source; **[claimed]** = source asserts it, I did not see the evidence; **[guess]** = my judgement; **[ours]** = measured in our VALUE_step docs.
Limits: web search returned abstracts and snippets only. I could not read full texts of the IPL-price papers (R-squared values were NOT found; I do not quote any). Nothing was fetched from ESPNcricinfo/Cricbuzz.

## 0. What our problems really are (diagnosis, [guess])
1. Season-to-season r of 0.06-0.17 is mostly **small sample + noisy outcome (wickets)**, not "no skill". Baseball reaches usable projections by (a) measuring reliability per component, (b) shrinking each component by its own amount, (c) rebuilding the total. We shrink one lumped number.
2. Team win share being luck and beta 0.09 is partly **errors-in-variables**: squad value is noisy, so the slope is attenuated. Fixing player-value noise (shrinkage) raises beta without any new data.
3. Missing context (order, phase, pace/spin, hand) is a **contextual-expectation** problem, solvable with a log-linear/empirical-Bayes expected-runs model (cricket literature has exactly this, see 1.9).

## 1. Methods

### 1.1 Marcel / ZiPS / Steamer / PECOTA principles (baseball)
- What: weighted multi-year average (5/4/3 weights), regress toward the league mean in proportion to sample size, adjust for age. ZiPS/Steamer add per-component regression and comps; PECOTA adds comparable-player (nearest neighbour) forecasts. [claimed, general knowledge; Marcel is the "minimum-effort baseline everything must beat"]
- Data needed: multi-season ball-by-ball; we have it. Age missing (see 1.4).
- Supported: yes. Benefit: problems 1, 4. Effort S.
- Validation: leave-one-season-out forecast of next-season runs/ball and WAR; compare against "last season" and "league mean". Only keep it if it beats both (our current r 0.13 for WAR is the bar).
- Notes: we already use 4/3/2/1 recency weights on WAR but with no shrinkage by balls faced. That is the gap.

### 1.2 Stabilisation points and regression to the mean
- What: reliability (split-half / KR-21 / Cronbach alpha, Spearman-Brown extended) per stat; the "stabilisation point" is the sample where reliability = 0.70 (or 0.5). Shrinkage weight = n / (n + n_half) where n_half is the sample at reliability 0.5. [src] Baseball Prospectus: K% 70 BF, BB% 170 BF, single rate 670, AVG 630, BABIP ~2,000 BIP (reliability 0.70, KR-21/alpha, 2003-12). https://www.baseballprospectus.com/news/article/20516/baseball-therapy-should-i-worry-about-my-favorite-pitcher/ . Also [src] a warning that estimates vary a lot by method.
- Cricket: I found **no published T20 stabilisation table** [src: search]. Only an ESPNcricinfo piece saying a new batter settles after ~10 balls (warm-up effect, not reliability). So we compute our own. [guess] boundary%, dot%, wicket% will stabilise at very different sizes (boundary/dot in a few hundred balls, dismissal rate in thousands).
- Data: ours. Effort S. Benefit: problems 1, 4 (tells us which parts of RA are signal).
- Validation: odd/even-ball (or odd/even-match) split-half correlation per component, Spearman-Brown stepped up, by role and phase; report n_half.

### 1.3 Component-based projection (project skills, rebuild total)
- What: project separately dot%, 1-3 run rate, boundary%, dismissal rate (batter); dot%, boundary conceded, wicket rate (bowler), each shrunk by its own stabilisation, then recompute runs-added from the components via our run-expectancy table. This is the ZiPS/Steamer/Marcel-by-component idea. [claimed]
- Supported: yes (ball outcomes). Benefit: problems 1, 4 strongly. Effort M.
- Validation: next-season component r vs the lumped RA r (0.06-0.17); rebuilt-total r; calibration (decile of projected vs actual).

### 1.4 Aging curves
- What: delta-method curves (year-over-year change among players who play both years) to adjust projections. [claimed]
- Data: **DOB is not in Cricsheet.** Cricsheet people.csv has identifier, name, unique_name and site keys (key_cricinfo, key_cricbuzz, key_cricketarchive, key_bcci, key_opta ...), no DOB, no Wikidata id [src: https://cricsheet.org/register]. Register licence: Open Data Commons Attribution [src]. Legal route: Wikidata (property P2697 = ESPNcricinfo player ID, https://www.wikidata.org/wiki/Property:P2697 [src]) joined on key_cricinfo, then take date of birth (P569). Wikidata is CC0 [claimed from memory, confirm on wikidata.org/wiki/Wikidata:Licensing before use]. Coverage of lesser players unknown [guess]; use SPARQL dump, not scraping cricinfo.
- Supported: partly. Benefit: small for T20 within a 3-4 year window; matters for auction (age feature) [guess]. Effort M (join + coverage check). Validation: coverage % of IPL 2023-26 players; delta-method curve smoothness; does adding age improve holdout error of 1.1/1.3 at all.

### 1.5 DIPS / FIP analogue (separate controllable from luck)
- What: baseball's FIP replaces a pitcher's allowed hits/runs with K, BB, HR (the parts he controls) and ignores balls in play. [claimed, general knowledge]
- Cricket analogue [guess]: bowler skill = dot%, boundary% conceded, wide/no-ball rate; wicket-taking is partly luck (edges, catches, fielding). A "fielding-independent" bowler value = value of dots and boundaries, with wickets shrunk hard toward the expected wicket rate for that dot/boundary profile. Batter: boundary% and dot% are controllable; dismissal rate regressed hard.
- Supported: yes (no fielding data needed, since it excludes outcomes). Benefit: problem 1 (the dismissal-luck swamping) directly. Effort S-M, and the cleanest single fix. Validation: does "dot/boundary-only RA" repeat better than full RA (target >0.3 for bowlers, >0.2 batters [guess]); does adding shrunk wickets back help predict next-season WAR.

### 1.6 WAR frameworks (fWAR vs bWAR, replacement level)
- What: fWAR uses fielding-independent inputs; bWAR uses actual runs allowed. Replacement level around 0.294 win% (about 48 W/162 for a team) [claimed]. Our WAR already has a replacement level fixed by params.
- Lesson: offering **two WARs** (actual vs controllable) is the baseball way of admitting luck; matches 1.5. Effort S once 1.5 exists. Validation: which WAR predicts next-season team wins/runs better (baseball finds the fielding-independent one for pitchers [claimed]).

### 1.7 RE24 / WPA / leverage index
- What: RE24 (we have: run expectancy). WPA = change in win probability; leverage = how much a play swings win prob. [claimed]
- Data: ours (we have a WPA module per CLAUDE.md). Benefit: problem 3 (leverage context): report "context-neutral" (RA) and "clutch-adjusted" (WPA/leverage) and treat the difference as noise unless it repeats. Baseball evidence that clutch does not repeat is well known [claimed]. Effort S (reuse). Validation: year-to-year r of (WPA - RA); expect ~0 -> drop clutch from projections.

### 1.8 RAPM / regularised plus-minus (basketball, hockey)
- What: ridge regression on a design matrix of who was on court/ice; coefficient = player effect after controlling for teammates and opponents; lambda by cross-validation. Lasso is an alternative that zeroes average players. [src] https://squared2020.com/2017/09/18/deep-dive-on-regularized-adjusted-plus-minus-ii-basic-application-to-2017-nba-data-with-r/ , https://arxiv.org/html/2406.09895v2 (lasso vs ridge note).
- Cricket fit: every ball has exactly one batter, one bowler (plus non-striker). Regress ball value (runs + RE change) on batter dummies + bowler dummies + venue + phase, ridge. This is a **crossed random-effects model**; ridge = empirical-Bayes shrinkage, so it fixes opposition/bowler-quality adjustment AND small samples at once. Also supports partnerships (striker x non-striker). Equivalent to the Davis-Perera-Swartz / arXiv log-linear idea (1.9).
- Data: ours, ~0.5M IPL balls, a sparse matrix; fits in seconds with sklearn Ridge or glmnet-like. Benefit: problems 1, 3, 4. Effort M. Validation: next-season hold-out log-loss/RMSE on ball value; r of player coefficients across seasons (split by odd/even seasons); compare to plain RA. Choose lambda by grouped (by-match) CV, not random-ball CV.
- Risk [guess]: bowler effects are weakly identified in 14 games; pool across leagues with league as a covariate.

### 1.9 Cricket context-adjusted expected-runs models (published)
- [src] Davis, Perera, Swartz, "Player Evaluation in Twenty20 Cricket", Journal of Sports Analytics 2015: ball-by-ball simulator-based batting/bowling metrics; they report the metrics correlate weakly with conventional average/strike rate/economy, and apply them to overpaid/underpaid IPL players (abstract-level, full text not read). https://www.sfu.ca/~tswartz/papers/moneyball.pdf (hosted copy; cited in https://journals.sagepub.com/doi/reader/10.3233/JSA-220640 as the source).
- [src] Perera, Swartz, Davis "Advanced Metrics in Twenty20 Cricket" (BAYSM 2014): empirical Bayes for batting/bowling characteristics given game situation. https://baysm2014.wu.ac.at/download.php?id=56 . Thomson, Perera, Swartz, "Contextual batting and bowling in limited overs cricket", S. Afr. Stat. J. 2021 [claimed from snippet].
- [src, abstract only] Bandyopadhyay, "Context-adjusted Player Evaluation for Twenty20 Cricket", arXiv 2608.18020 (CC BY 4.0): Runs Above Expected from a multiplicative log-linear Poisson model with empirical-Bayes shrinkage, plus Dismissal Adjusted Runs priced from a dynamic-programming value function and a league-wide hazard (martingale residual). 2.7M men's T20 balls. Validation stated only as "recovers known structure" and "face-valid" leaderboards, **no out-of-sample test** in the abstract. https://arxiv.org/abs/2608.18020 . Closest published match to our RA; its "only charge wickets above/below a league hazard" is a version of 1.5.
- Effort M for a log-linear context model (batting position, phase, pace/spin, hand, venue as multiplicative factors). Validation: per 1.8.
- I did not find CricViz/Impact Index method documentation in a fetchable open source; skip (do not claim) [guess].

### 1.10 Bayesian hierarchical models
- What: player skill ~ role/league group mean + player deviation; partial pooling gives the shrinkage amounts automatically and gives credible intervals (we currently bootstrap). Equivalent in spirit to 1.3/1.8 but handles unequal sample size and multi-league pooling (IPL, SA20, BBL, T20I) naturally. [claimed]
- Effort M-L (PyMC/Stan install needed; ask first). Cheaper: empirical-Bayes beta-binomial/Poisson shrinkage per component, effort S, 90% of the benefit [guess]. Benefit: problems 1, 4; also gives honest ranges for the trade tool.
- Validation: posterior-interval coverage on held-out season (do 80% intervals contain 80%?), plus the r test.

### 1.11 Elo / Glicko / TrueSkill ratings
- What: online ratings updated per match; Glicko adds uncertainty. Works for team strength; for players in a team sport TrueSkill-type models give each player a rating from team outcomes. [claimed]
- Cricket fit: team Elo with a squad-value input could address problem 2; player-from-team-result rating is far noisier than ball-based RA [guess]. Benefit: low-moderate; Effort M. Validation: Brier/log-loss of match win prob vs a season-prior baseline, time-split. Rank below 1.8 for players; useful as the team-strength baseline in the season simulator.

### 1.12 xG / xT / VAEP (football on-ball value)
- What: VAEP values any action by the change in P(score in next ~10 actions) minus P(concede), classifiers on the last 3 game states (CatBoost in the paper). xT is a grid-based Markov version. [src] Decroos et al., KDD 2019, https://arxiv.org/pdf/1802.07127 ; KU Leuven note that VAEP and xT rankings differ with design choices (https://dtai.cs.kuleuven.be/sports/vaep).
- Cricket fit: our run expectancy + win-prob change IS the one-state analogue (state = wickets, balls, score, innings). VAEP adds richer state (batter set, who is bowling, phase, last-3-balls). A gradient-boosted ball-outcome model (P(wicket), E[runs] given state + batter + bowler IDs as features) is the practical version.
- Data gap: no shot/line/length, so state richness limited to score, wickets, balls, striker/bowler identity, bowler type, recent balls. Benefit: problem 3 moderate; Effort L. Not first.

### 1.13 Football/market valuation (Transfermarkt-style, hedonic pricing)
- What: price = f(age, position, performance, contract length, league) on log scale; hedonic regression. Transfermarkt values are crowd-sourced, tied to age-curves and performance [claimed]. IPL has the same structure with fixed purses.
- See auction section below for IPL-specific evidence.

## 2. Ranked shortlist (top 8) and order

| # | Method | Fixes | Effort | Why this rank |
|---|---|---|---|---|
| 1 | Reliability / stabilisation table per ball-outcome component (1.2) | 1, 4 | S | Tells us what is signal. Prerequisite for everything else. |
| 2 | Component projection with per-component shrinkage + Marcel baseline (1.1 + 1.3) | 1, 4 | M | Direct baseball recipe for our exact failure (0.06-0.17). Must beat "last season" and "league mean". |
| 3 | FIP-style controllable value: dot%/boundary% heavy, wickets shrunk hard; dual WAR (1.5, 1.6) | 1 | S-M | Attacks dismissal luck head-on; no extra data. |
| 4 | Ridge crossed-effects model / RAPM on batter+bowler+venue+phase+order (1.8, 1.9) | 1, 3, 4 | M | Gives order/phase/opposition/hand adjustment and shrinkage in one fit; closest to published cricket methods. |
| 5 | Errors-in-variables fix for team slope: refit squad-value -> win slope using shrunk values and ridge slope, report disattenuated beta (new, from 1.2) | 2 | S | Our beta 0.09 is likely attenuated [guess]; cheap to test by simulation. |
| 6 | Auction model (section 3), time-split | auction | M | Separate deliverable; value feeds it as a feature. |
| 7 | Empirical-Bayes intervals / Bayesian hierarchical, multi-league pooling (1.10) | 4 | S-M (EB) / L (full) | Honest ranges; borrows strength from other T20 leagues. |
| 8 | Wikidata DOB join + age curves (1.4) | 1, auction | M | Age helps auction and mild projection; coverage uncertain. |
Not recommended now: VAEP-style boosted model (L, no shot data), Elo/TrueSkill for players (noisy), clutch/WPA adjustments (do not repeat [claimed]).

Order: 1 -> 2 -> 3 -> 5 -> 4 -> 6 -> 7 -> 8. Gate: each step is kept only if its next-season hold-out correlation beats the previous one on the same 2025 and 2026 targets (218 player-seasons).

## 3. Auction price model

**What published work says (abstract-level; no R-squared obtained):**
- Karnik 2013, "Pricing of Cricketers: The Experience of Two IPL Auctions", Int. J. Sport Finance 8(1): runs in shorter formats, Test wickets, age and nationality are significant; Heckman selection used to handle unsold players. [src abstract] https://ideas.repec.org/a/jsf/intjsf/v8y2013i1p3-20.html
- Lenten et al. 2012 and Bhattacharya & Bhattacharya 2012: hedonic/regression, price on performance covariates; criticised for ignoring the auction process. 2011 hedonic study: Indian players, "X-factor" and prior T20 experience attract higher values. [src via snippet] https://journals.sagepub.com/doi/abs/10.3233/JSA-200580 (JSA 2020 predicts price from performance variables by role)
- Chowdhury & Bansal 2026, Sport Business and Management: 2,547 player-seasons 2015-2024, fixed effects, hedonic, performance index, propensity-score matching; foreign players carry a premium the stats do not support. [src abstract] https://www.citedrive.com/en/discovery/return-on-investment-and-player-valuation-effectiveness-in-the-indian-premier-league-a-comprehensive-analysis-of-foreign-versus-domestic-player-economics/
- Modified hedonic model beat XGBoost in one ICCCNT 2021 paper [claimed from snippet; small samples]. Base-price setting from performance: JSA 2022 https://journals.sagepub.com/doi/10.3233/JSA-220633 .
- Reported coefficient sizes/R-squared: **not found**. [guess] hedonic R-squared in the literature is moderate (0.4-0.7 on log price); do not rely on it.

**Features to build (all except the last three from our data/contracts):**
base price slab (strongly censors: many sell at base) | capped/uncapped (India) | nationality (overseas) | role (bat/bowl/WK/AR) | batting position and phase usage | age (via 1.4) | recent value: shrunk component WAR (not raw RA) over last 1-3 seasons, T20 across leagues | career balls (experience) | prior IPL price (strongest single feature in industry practice [guess]) | retained/RTM flag | team purse remaining and slots open (market-level, per auction) | auction type (mega vs mini) as a fixed effect. Position-scarcity at the auction (how many comparable players in the pool) [guess].

**Recipe:**
1. Two-part model (hurdle): (a) P(sold) logistic; (b) log(price / base price) or log price given sold, ridge or gradient boosting (LightGBM small, depth 3). Optionally Heckman correction as in Karnik for the selection into "sold".
2. Handle the structure: price clusters at base-price slabs; predict log price, report quantile intervals (quantile regression 10/50/90), not just a point.
3. Inflation: price in "share of purse" (price / total purse) so 2022-2026 are comparable. [guess: purse changed 90 -> 95 -> 100 -> 120 cr.] Check before use.
4. Time split: train 2022 mega + 2023/2024 minis; validate 2025 mega; final test 2026 mini (do not tune on it). Note mega vs mini differ greatly; include auction type, and also report a mega-only check.
5. Metrics: MAE in rupees crore (sold players only) and MAE as % of purse; R-squared on log price; Spearman rank correlation (most important for trade/shortlist use); AUC and Brier for sold-vs-unsold; calibration of P10-P90 interval (coverage). Baselines to beat: "price = base price", "price = last year's price" (retained/re-auctioned only), and a base-price + capped + overseas + role OLS.
6. Report sample size honestly: roughly 150-250 sold players per mega and 70-100 per mini [guess], so expect wide intervals; no deep models.
7. Ablation: does adding our shrunk value improve over the non-performance baseline? If not, say so; published work suggests nationality and reputation may dominate.

## 4. Five key sources
1. Baseball Prospectus stabilisation points: https://www.baseballprospectus.com/news/article/20516/baseball-therapy-should-i-worry-about-my-favorite-pitcher/
2. Bandyopadhyay, Context-adjusted Player Evaluation for T20 (arXiv 2608.18020): https://arxiv.org/abs/2608.18020
3. Davis, Perera, Swartz, Player Evaluation in Twenty20 Cricket (JSA 2015): https://www.sfu.ca/~tswartz/papers/moneyball.pdf
4. Karnik 2013, Pricing of Cricketers (IJSF): https://ideas.repec.org/a/jsf/intjsf/v8y2013i1p3-20.html ; and Chowdhury & Bansal 2026 (link in section 3)
5. Decroos et al., VAEP (KDD 2019): https://arxiv.org/pdf/1802.07127 ; RAPM primer: https://squared2020.com/2017/09/18/deep-dive-on-regularized-adjusted-plus-minus-ii-basic-application-to-2017-nba-data-with-r/
