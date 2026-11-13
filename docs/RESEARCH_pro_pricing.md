# How professionals price cricket, and can a hobbyist beat a T20 exchange market?

Tags: [read] = I read the page text or abstract page in full via fetch. [snippet] = search-result snippet only. Many PDFs (Norton full text, Swartz, Kaunitz, IRE 2026) failed to fetch (403 or binary), so for those only abstracts and snippets were seen. Research only, not betting advice.

## 5-line executive summary
1. Professional cricket pricing is the same recipe as yours, with more data: a ball-by-ball outcome model (player ratings, venue, phase, wickets and overs left) feeding Monte Carlo simulation or dynamic programming. WASP is the public DP example, Opta/Stats Perform and Smartodds are the commercial simulation examples.
2. The differences are not model class. They are (a) live feeds, (b) the pre-match market as the anchor, (c) human traders plus risk management, (d) speed.
3. The only strong published in-play edge (Norton, Gray, Faff 2015, ODI Betfair, "20% profit" after a wicket) is first-innings overreaction in ODIs. The abstract does not say whether that is after the 5% commission. Nothing peer-reviewed shows it for T20. One unreviewed 2026 IPL preprint claims a wicket-staleness edge [snippet].
4. Your result (market ties at 6 overs, beats you at 10 and 15, blend no better than market, 7-input logistic about as good) is the normal pattern for a liquid, efficient market. It is not evidence you are doing something fundamentally wrong.
5. Verdict: beating a major-league T20 exchange after 5% commission with only public ball-by-ball data and over-snapshot odds is very unlikely. The realistic win is a model that matches the market and finds specific, small, testable pockets (e.g. thin markets, specific states). Closing-line-style calibration versus the market is the right yardstick.

## 1. How professional pricing works

| Method | What is known | Status |
|---|---|---|
| WASP (Brooker and Hogan, Univ. of Canterbury, NZ) | Built from a dynamic programme, not curve fitting. First innings projects a final score, second innings gives chaser win probability, assuming average top-eight teams. Used by Sky NZ since 2012. NV Play has owned it since 2018 and added a pressure concept. Sparse data makes rare states (e.g. 5 down after 10 overs) unreliable. | [snippet] from Wikipedia and NZC pages. Original paper not found. |
| DLS (Duckworth-Lewis-Stern) | A table of resource percentage as a function of overs left and wickets lost. It sets fair targets after interruptions. It is not a win-probability model, but Bailey and Clarke (2006) used the D/L resource table to update a regression forecast of ODI totals during play. | [snippet] |
| Opta / Stats Perform (the Analyst, 2022) | A match simulator replays every remaining ball many times. Per-ball outcome probabilities come from a neural network ("Next Ball Predictor"). Inputs: home team, score, required rate, runs and wickets per ball so far, plus player and venue ratings. Ratings are a hierarchical Bayesian system (batter, bowler and venue runs-per-ball and balls-per-out), adjusted for opponent and situation. Win probability, score prediction and next-ball all come from the same simulations. No published calibration or backtest. Bowler quotas and how the pre-match prior is built are not described. | [read] https://theanalyst.com/eu/2022/05/introducing-cricket-simulation-models/ |
| Academic player-level T20 simulator (Perera, Davis, Swartz) | Ball-by-ball simulation. Multinomial outcome probabilities depend on batter, bowler, overs used and wickets lost, estimated with empirical Bayes (shrinking sparse players toward group means). The target score modifies second-innings probabilities. | [snippet] https://www.sfu.ca/~tswartz/papers/t20sim.pdf (PDF unreadable by fetch) |
| Pricing-team job ads | Smartodds (London) hires a "Cricket Quantitative Analyst" to build pre-match and in-play predictive models and maintain the maths libraries behind clients' pricing tools. Kambi cricket traders price and trade both pre-match and in-play and feed back into models and trading tools. Generic quant ads mention ratings, simulations, in-play models, live liabilities and customer behaviour feeding prices. Roles sit between sportsbook trader, quant researcher and financial-market trader. | [snippet] job-board listings (Kambi, Smartodds, others) |

What is NOT public: bookmaker or syndicate in-play adjustment rules, how the pre-match price is injected as a prior, and any cricket-specific use of fielding, ball-tracking or weather feeds. Sportradar and CricViz internals were not found. Expect them to be similar in structure to the above.

How bookmakers make money (general sports-betting sources, mostly vendor or affiliate pages, so weak) [snippet]: sharp books such as Pinnacle post lines from an internal model and learn from sharp action; soft books copy and add a larger margin (sharp 2-3%, retail 5-7% quoted by one comparison site, unverified). Traders in cricket are mainly managing liability and suspending markets on events (wicket, boundary, review). That is a real-time operations problem as much as a modelling one. I did not find a primary source describing cricket bookmakers explicitly following Betfair, but the general practice is plausible.

On an exchange there is no bookmaker. Prices are set by the crowd, including professional market-making and trading operations, so "the market" at 10 and 15 overs already embeds the best private models plus live information.

## 2. Academic evidence on cricket market efficiency

- **Bailey and Clarke (2006), J. Sports Sci. & Med.**: ODI regression on all 2,200 ODIs before 2005, updated each over via the D/L resource table; the authors say the market is prone to overreact to events, giving brief inefficiencies. Notes over 80% of ODI money is wagered after the match starts. [snippet, abstract confirmed in two result pages] https://pmc.ncbi.nlm.nih.gov/articles/PMC3861745
- **Easton and Uylangco (2007), J. Prediction Markets**: over 8,000 balls of one-day cricket; news is impounded into odds rapidly, odds have some predictive ability for the ball before it is bowled, and there is drift after outcomes become known. [snippet] https://ideas.repec.org/a/buc/jpredm/v1y2007i2p93-109.html
- **Norton, Gray and Faff (2015), J. Banking & Finance 61, S164-S176**: Monte Carlo win-probability model versus Betfair in-play, 1,101 ODIs, ball-by-ball. Strong overreaction in the first innings; betting the batting side after a wicket gave "a significant profit of 20%"; some weaker underreaction in the second innings; model-versus-market discrepancy strategies also profitable. [read abstract] https://research.bond.edu.au/en/publications/yes-one-day-international-cricket-in-play-trading-strategies-can-/ . The abstract does not state commission treatment; a secondary snippet says Betfair keeps 5%. Full text blocked (403). Treat survival after costs as unknown. Caveats I can infer but did not verify: this is ODI, older Betfair data, and markets have since matured.
- **IPL wicket-shock preprint (IRE Journals, 2026, Sharma and Sabharwal)**: 353 IPL matches, 4,300+ wickets; backtest on 52 IPL 2025 markets reports significantly positive expected value; out-of-sample T20 World Cup 2026. Unreviewed, 52-market backtest is small, and fetch failed. Low weight. [snippet]
- **Favourite-longshot bias**: general sports-betting finding; Whelan (CEPR DP17518) explains it via bettor disagreement plus bookmaker risk aversion. I found no cricket-specific or T20-specific test. Angelini, De Angelis and Singleton (Int. J. Forecasting 2022) on Betfair football in-play find mispricing grows after surprise events (e.g. late longshot goal). [snippet]
- **Home or fan bias, IPL fan-money, big versus small leagues, men versus women**: no rigorous study found. Women's-cricket "hidden gem" pages are affiliate marketing with no measurement. Plausible but unmeasured: thinner liquidity and wider spreads in WBBL and women's T20I, which cuts against exploiting any inefficiency. [snippet]
- Overall pattern: older ODI evidence of overreaction, a 2007 rival finding of rapid incorporation, nothing recent and peer-reviewed for T20. Not read: any evidence that edges survived 5% commission.

## 3. Where retail and quant edges realistically come from

- **Speed**: courtsiding is latency arbitrage. Vendor figures: about 1-2 s from venue, 3-6 s TV, 7-15 s streams (Statscore page, vendor, low reliability). Exchanges add an in-play bet delay (Betangel help says up to 12 s, later 1-9 s depending on market/sport, no Betfair primary source found). A model that updates after the ball is public is slower than every professional. [snippet]
- **Team news, toss and pitch**: public information is priced quickly; edge needs being first or interpreting it better (e.g. a mid-order batter out injured changes the ratings feed).
- **Low-liquidity markets**: edges are more plausible where fewer professionals look, but spreads and unmatched volume eat them. I found no matched-volume numbers for BBL or women's cricket. [snippet]
- **Commission**: standard 5% on net winnings for cricket per a comparison blog; Betfair's Premium Charge appears to have been replaced in late 2025 (Racing Post; conflicting affiliate sites). Check Betfair's own page. [snippet]
- **Model plus market ("market as feature")**: Hubacek and Sir (2023, Int. J. Forecasting) explicitly train models decorrelated from the market so they add information beyond the odds. Kaunitz et al. (arXiv 1710.02824) argue profitable play came from using the odds themselves (consensus mispricing between bookmakers), and that bookmakers respond with discriminatory practices (limits) against winners. [read abstracts only]
- **Closing-line value (CLV)**: the practitioner yardstick; consistent CLV indicates edge, ROI alone can be luck. The closing line still carries public biases such as favourite-longshot. [snippet, vendor and blog pages]

## 4. Advanced ideas hobby models often miss: testable here?

Your data: Cricsheet ball-by-ball (full), Betfair BBL odds at first ball and at 4/6/10/15 overs per innings, 303 matches. "Testable" means a paired comparison on those 303 matches (small sample: Brier-score differences of ~0.002 are noise).

| Idea | Why it matters | Testable on our data? |
|---|---|---|
| Pre-match market as prior | Pros do not predict from scratch; the first-ball price already holds team news, toss, pitch, form. Use odds at first ball as a feature and learn only the in-play update. | Yes, directly. Odds at first ball exist for BBL. Cheap, high value. |
| Remaining bowler overs and who is left | Quota: 4 overs per bowler. Whether the best bowler has overs left at the death is a big swing the market sees live. | Yes from Cricsheet (compute overs left per bowler, strongest and weakest remaining). Medium effort. |
| Resource-based state (DLS style) | Smooth resource = f(overs, wickets) summarises state better than raw features; reduces overfit. | Yes, but your logistic and GAM may already capture it. Low effort, low gain. |
| In-season Bayesian team strength | Hierarchical ratings update after each match; BBL has few teams and few games. | Yes, via Elo or hierarchical rating from earlier seasons only (time-ordered). Medium effort. Likely overlapped by the pre-match market. |
| Batter-vs-bowler and new-batter effects | New batters score slower for first balls; matchup by type (pace/spin, handedness) per Opta-style ratings. | Partly: ratings from earlier balls; matchups are sparse in BBL. Medium effort, small gain expected. |
| Player-level simulation with hierarchical shrinkage | Perera/Davis/Swartz-style empirical Bayes per batter and bowler, conditional on overs and wickets. You already built a simulator; check shrinkage and phase terms. | Yes, mostly done. Check calibration by state rather than add complexity. |
| Dew and night-match chase effects | Ball gets wet, spin and slow balls suffer, chasers favoured. I found no rigorous estimate; only blogs. Mostly venue and time features. | Partly: Cricsheet has venue and start time but not dew; use night-game and venue-by-season chase win rate. Low effort. |
| Ground-level scoring adaptation inside the match | Pitch playing slow or fast (market sees powerplay result) shows in early overs and is priced quickly. | Yes: compare first-innings pace at 6 overs versus ground prior. Medium effort. |
| Market-overreaction after wicket or boundary (Norton) | The one published exploitable pattern. | Weakly: your odds are only at 4/6/10/15 overs, so you cannot see price reaction to individual events. You can test: does the market price at 10 overs deviate from the model more after the wickets cluster in overs 7-10? Small sample. |

## Top 8 ideas for this project (ranked)

| # | Idea | Expected value | Effort | Testable on our data |
|---|---|---|---|---|
| 1 | Use first-ball Betfair price as prior and model only the update ("market as feature"), judged against the 6/10/15-over market | Medium: most plausible way to match or slightly beat the market; at least confirms model adds nothing | Low | Yes, direct. |
| 2 | Calibration and sharpness analysis versus de-vigged market by state (overs, wickets, required rate), find where model beats and loses | Medium (diagnostic, tells where any edge lives) | Low | Yes. |
| 3 | Remaining-bowler-overs features (strength of overs left, death specialist available) | Medium at 10 and 15 overs | Medium | Yes (Cricsheet). |
| 4 | Residual test: regress outcome on market logit plus model logit (and extra features); check model coefficient and significance | Medium (the clean "does it add information" test) | Low | Yes, with 303 matches power is limited. |
| 5 | Bayesian in-season team and venue ratings (time-ordered), compared with the pre-match price | Low to medium | Medium | Yes. |
| 6 | Event-conditional mispricing (after wicket clusters or big overs between snapshots), per Norton overreaction | Low to medium; published only for ODI | Medium | Weak; only 4 snapshots per innings. |
| 7 | Night-game, venue, toss, chase-bias features | Low (market already prices it) | Low | Yes. |
| 8 | Out-of-sample on a thinner market (WBBL or other leagues with Betfair odds), where professionals pay less attention | Possibly higher edge but also wider spreads and commission eats it | Medium (needs odds data) | Not on current data. |

## 5. Common amateur mistakes (all from blog and vendor sources unless noted)

- Look-ahead leakage: using closing odds or post-event information; random k-fold on time-ordered data. [snippet]
- Overfitting: tuned 20-factor models underperform simple ones live; free parameters should be far below sample size. [snippet] (Matches your finding that a 7-input logistic equals the complex models.)
- Judging by ROI or accuracy instead of Brier score or log-loss versus the de-vigged market, and CLV. [snippet]
- Ignoring commission, spread, in-play delay and matched-volume limits; paper profits that cannot be executed.
- Selection bias: testing only bets you like, or only seasons where the idea worked; small samples (303 matches means each comparison has wide error bars).
- Not de-vigging: favourite-longshot bias and overround distort implied probabilities (use power or Shin methods). [snippet]
- Treating the market as a competitor to beat rather than as the strongest feature to include.
- Assuming a bookmaker will accept winners: retail books limit winning accounts (Kaunitz abstract). On an exchange this does not apply, but liquidity does.

## Verdict (honest)

- Your pattern (tie at 6 overs, market better later, blend no gain) is what an efficient liquid market looks like: later in the innings the market incorporates more information (live pitch, dew, fielding, injuries, bowler form, captaincy plans) than public ball-by-ball statistics can.
- Fundamentally wrong? No evidence of that. The architecture matches what Opta and academic simulators describe. The gap lies in data (tracking, live feeds, injury and team news) and speed, not model class.
- Chance a hobbyist beats a major-league T20 Betfair market after 5% commission: very low, I would put it at a few percent at best, a guess not a measurement. Published edges are old, ODI, and the abstract does not confirm costs. Edges that exist in thin or women's markets are plausibly eaten by spread and low volume, unmeasured.
- Realistic goal: a calibrated model that approaches the market, plus a diagnosis of where it differs, and (optionally) a thin-market test.

## Surprises / gaps (not chased)
- No primary source on Sportradar, CricViz, Decimal Data internals.
- No peer-reviewed T20 in-play efficiency study found; no cricket favourite-longshot study; no women's-cricket efficiency study.
- Several full-text PDFs could not be fetched (Norton, Swartz, Kaunitz, IRE 2026); claims from them rest on abstracts and snippets.

## Sources
- https://en.wikipedia.org/wiki/WASP_(cricket_calculation_tool)
- https://www.nzc.nz/news-items/archive/whats-wasp-all-about/
- https://theanalyst.com/eu/2022/05/introducing-cricket-simulation-models/
- https://research.bond.edu.au/en/publications/yes-one-day-international-cricket-in-play-trading-strategies-can-/
- https://ideas.repec.org/a/eee/jbfina/v61y2015is2ps164-s176.html
- https://pmc.ncbi.nlm.nih.gov/articles/PMC3861745
- https://ideas.repec.org/a/buc/jpredm/v1y2007i2p93-109.html
- https://www.sfu.ca/~tswartz/papers/t20sim.pdf
- https://www.irejournals.com/formatedpaper/1718842.pdf
- https://arxiv.org/abs/1710.02824
- https://econpapers.repec.org/RePEc:eee:intfor:v:39:y:2023:i:2:p:691-719
- https://econpapers.repec.org/RePEc:eee:intfor:v:38:y:2022:i:1:p:282-299
- https://cepr.org/publications/dp17518
- https://arxiv.org/pdf/2505.01849
- https://betangel.freshdesk.com/support/solutions/articles/80001073155-why-is-there-a-delay-when-placing-bets-
- https://www.gamblingcommission.gov.uk/licensees-and-businesses/guide/in-play-or-in-running-betting
- https://racingpost.com/news/britain/betfair-exchange-to-introduce-new-commission-system-for-2025-as-premium-charge-is-dropped-a7wbg0v4GCAJ
- https://sbcnews.co.uk/uncategorized/2026/05/20/cost-stream-delay-live-betting
- https://developers.statsperform.com/low-latency-sports-data-for-in-play-markets
- https://sportstechjobs.com/cricket-trader-kambi/6882f2faa12bfab030b546ed
- https://www.jobleads.com/gb/job/quantitative-analyst-cricket--city-of-london--eee52e21352c52a6b4a9b481e32bdcb97
- https://sports-models-kb.pages.dev/closing-line-value-clv
- https://sports-models-kb.pages.dev/overfitting-sports-models
