# Length-based batter-vs-bowler matchup: backtest (2026-11-13)

**Verdict: DROP as a predictor.** The length model does not beat the pace/spin split (c) on runs error, and it is even worse than using the batter's overall strike rate alone (b). The gap is statistically clear (95% interval excludes zero). Do not register a dashboard module for it.

## What was built
`src/cricket_analytics/models/length_matchup.py`. Five length buckets (yorker/full toss, full, good + back of a length, short + short of length, bouncer). Batter rate per bucket (runs/ball, wicket/ball) and bowler length mix, both shrunk toward the league with (sum + k x prior) / (n + k), using only balls whose length is known in commentary (about 57% of faced balls). Prediction = sum over buckets of bowler mix x batter rate, rescaled so the average matches the all-balls level (known-length balls skew towards big hits). Runs and wickets come from Cricsheet, never the commentary text.

## Backtest
Fit on IPL 2017-2024. Test: every batter-bowler pair in 2025-26 with 6 or more balls faced (2,207 pairs, 22,735 balls, wides excluded). Shrinkage strength k was chosen per method on 2017-22 to 2023-24 (never on the test years). Ball-weighted. Lower MSE and log-loss are better; higher Spearman is better.

| Method | Runs/ball MSE | Spearman (pair runs/ball) | Wicket log-loss |
|---|---|---|---|
| (a) league average | 0.4706 | n/a | 0.15087 |
| (b) batter overall (shrunk) | 0.4551 | 0.045 | 0.15001 |
| (c) batter vs pace/spin (shrunk to league kind rate) | **0.4511** | **0.120** | 0.15012 |
| (c2) pace/spin, prior = batter overall x league kind pattern | 0.4502 | 0.113 | 0.15002 |
| (d) length model (league prior, as specified) | 0.4618 | 0.018 | 0.15018 |
| (d2) length, prior = batter overall x league bucket pattern | 0.4591 | 0.025 | **0.14999** |
| (d3) d2 x bowler's own concession per bucket | 0.4592 | 0.078 | 0.15026 |

Runs-MSE difference, length minus pace/spin (positive = length worse), 95% interval from resampling pairs 2,000 times:
- (d) - (c): +0.0107 [+0.0046, +0.0173]
- (d2) - (c2): +0.0088 [+0.0030, +0.0150]
- (d3) - (c2): +0.0090 [+0.0022, +0.0160]
- (d) - (b): +0.0067 [+0.0035, +0.0098]

Keep rule (length must beat (c) on runs MSE): **failed**, in every variant.

Wickets: all methods sit within 0.001 of each other; wicket log-loss differences are tiny and not meaningful (wickets are about 1 in 20 balls and pairs have few balls). (d2) is nominally best, by 0.0001.

## Why it probably fails (guesses, not tested)
- Buckets differ less than you would hope. League runs/ball: yorker/full toss 1.59, full 1.63, good length 1.20, short 1.63, bouncer 0.93 (bouncer is only 1.5% of balls). Three of five buckets are about the same.
- A bowler's length mix is mostly a pace/spin and phase signal (spinners: 38% full, 5% yorker; pace: 14% yorker), which (c) already uses directly with 100% coverage, while length is missing on 43% of balls.
- Batter-by-bucket rates are noisy: a batter has about 20-60 known balls per bucket even after 8 seasons.
- Level shift: 2025-26 pair runs/ball average 1.60 against 1.36-1.41 predicted by every method (scoring rose, and 6+ ball pairs favour top batters). This hurts all methods equally and does not change the comparison.

## Examples (train years only; shrunk rates, k=40 balls)
| Batter | Case | Batter runs/ball (league) | Wkt/ball (league) | Bowlers who bowl that length most (share of their known-length balls; league 30% short, 26% full, 30% good, 12% yorker/FT) |
|---|---|---|---|---|
| AD Russell | weak vs short (n=199) | 1.56 (1.60) | 0.071 (0.054) | S Gopal 62%, RD Chahar 46%, M Markande 43% |
| SO Hetmyer | weak vs full (n=127) | 1.43 (1.57) | 0.045 (0.049) | Noor Ahmad 50%, Imran Tahir 48%, Ravi Bishnoi 47% |
| N Rana | weak vs good length (n=293) | 0.96 (1.16) | 0.033 (0.043) | JR Hazlewood 43%, JD Unadkat 41%, I Sharma 40% |
| SP Narine | weak vs yorker/full toss (n=79) | 1.48 (1.58) | 0.063 (0.051) | T Natarajan 33%, DJ Bravo 33%, SL Malinga 27% |
| RD Gaikwad | strong vs short (n=304) | 1.78 (1.60) | 0.040 (0.054) | S Gopal 62%, RD Chahar 46%, M Markande 43% |

Reading: these are plausible stories (Russell's extra wickets against short-heavy leg spin; Narine against yorker bowlers), but "weak" here is a small gap on 80-300 balls. The backtest says such gaps do not carry over to unseen pairs better than a pace/spin split does. Treat them as descriptions, not predictions.

## Caveats
- Bowlers without an entry in player_overrides.csv have no pace/spin kind; (c) falls back to (b) for them.
- Length is under the commentary's reporting rules (bouncer only when the text says bouncer/bumper; "short of length" counted as short).
- One test (IPL 2025-26, one split). Not repeated with other splits.

Files (gitignored): `data/external/commentary/length_matchup_summary.csv`, `_backtest_pairs.csv`, `_examples.csv`. Run: `.venv\Scripts\python -m cricket_analytics.models.length_matchup`. Test: `tests/test_length_matchup.py`.
