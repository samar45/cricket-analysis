# Step 4: matchup predictor (`matchup_predict`)

Question answered: batter X against bowler Y (or a bowling type T), in phase P, at match state S: per ball, expected runs, chance of a
wicket, dot %, 4 %, 6 %, plus how many balls stand behind it and a confidence label. Our version of a WagonLens card without the
field map (no line, length or wagon data exists in the source). Code: `models/matchup_model.py`, `analysis/matchup_predict.py`,
`viz/matchup_predict.py`, `viz/video/matchup_predict.py`, fitted weights `models/data/matchup_k.json`, tests `tests/test_matchup_model.py`.
Rebuild: `python -m cricket_analytics.models.matchup_model` (about 3 minutes).

## Short, honest result (measured by us, 33,303 test balls)

The predictor beats the league phase average by 0.0133 nats a ball (0.9 %) and beats both "raw" alternatives clearly. Almost all
of that gain comes from the **match state** and the **batter's own level**. The bowling-type layers add a little. The exact
bowler-v-batter layer adds about 0.00007 nats a ball: out of sample, **head-to-head history is almost noise**. The model is
calibrated for wickets. Wicket risk (the part people care about) is barely predictable beyond the batter and the bowling kind.

## Method

Seven outcomes of a ball the batter faces (wides excluded): dot, 1, 2, 3 (5s folded in), 4, 6, striker out (any way, run outs
included). Everything is a probability over those 7.

1. Start at the league probability of the (era, phase) cell. IPL from 2023 (Impact Player) is its own era, so the baseline uses
   2023+ balls only. Other competitions have one era.
2. Layers, broad to specific. Each looks at a group of balls, compares what happened (O) with what the earlier layers predicted for
   those same balls (E), and multiplies the probabilities by a shrunk ratio `(O + k*pbar) / (E + k*pbar)`: that is k "pseudo-balls"
   that behaved exactly as predicted (a Dirichlet prior), so a group with n balls gets weight about n/(n+k). Then renormalise.
   Order: state (innings 1 / chase, wickets down, required-rate band) -> bowling kind (pace/spin) -> bowling type x batter hand ->
   batter -> bowler -> batter in this phase -> bowler in this phase -> batter v kind -> batter v type -> bowler v batter hand ->
   batter v this exact bowler.
3. Why multiply and renormalise (the odds-ratio / log5 idea): batter and bowler effects add on the log-probability scale, so a
   good batter against a good bowler is not double counted, probabilities stay in 0-1 and sum to 1, and a rare class cannot overflow.
   An additive scheme can go negative or above the league cap; the multiplicative one cannot.
4. Two strengths per layer: `k_run` for the six run classes and `k_w` for the wicket class (wickets are rare, so they need their
   own). Chosen by **walk-forward** validation: for each year t from 2016 to 2024 (2023 skipped, no earlier ball of that era), estimate
   from balls before t, score year t, pick the k pair with the lowest total log loss over a grid. No hand picks.
5. Bowling type, pace/spin and batting hand come ONLY from the reviewed list (`sql/attributes.py`). Unknown stays unknown and that
   layer is skipped (ratio 1). Derived guesses are never used. 22 % of balls have an unknown batter hand and 2 % an unknown bowling
   type in the IPL data.
6. Era handling for the player layers, two options tried (fit through IPL 2024, test on IPL 2025-26):
   (a) isolated: only 2023+ balls, equal weight; (b) decayed: all balls, weight `exp(-lambda * years back)`, times `omega` for a ball
   from the older era, lambda and omega chosen on the walk-forward folds from a grid (lambda 0-0.5, omega 0-1).

### Decision on (a) v (b)

Rule fixed before running: take (b) only if test log loss is lower by at least 0.002 nats, and wicket log loss and run MAE are not worse.

| Option | lambda / omega | Test log loss (7 classes) | Wicket log loss | MAE runs/ball (pairs >= 12 balls) |
|---|---|---|---|---|
| (a) isolated, 2023+ only | 0 / 0 | 1.49962 | 0.19892 | 0.4189 |
| (b) decayed, all seasons | 0.25 / 1.0 | 1.49758 | 0.19879 | 0.4173 |

(b) passes the rule, narrowly: 0.00204 nats better (paired standard error 0.0003 over 33,303 balls, so about 6.8 SE, though balls from the
same player are correlated and the real error is larger). Walk-forward also prefers (b) (loss 168,742 v 168,837). **The default is
(b), but this is a marginal call against the owner's "(a) unless clearly better" rule.** `mode="isolated"` is one switch away.
Practical meaning: omega = 1 says old-era balls are as informative about a player as new ones; the decay of 0.25 a year (an
older season counts about 78 % of the next one) does the work. Players do not change much with the impact-player rule: the era
shows up in the league baseline, not in who the batter is.

## Fitted k (chosen mode: decayed)

| Layer | k_run | k_w | Out-of-sample gain, nats per 1000 balls |
|---|---|---|---|
| state | 400 | 400 | 4.44 |
| kind | 400 | 5 | 2.69 |
| type x hand | 1200 | 3600 | 0.73 |
| batter | 400 | 400 | 5.45 |
| bowler | 1200 | 3600 | 0.64 |
| batter in phase | 1200 | off | 0.38 |
| bowler in phase | 1200 | off | 0.11 |
| batter v kind | 1200 | off | 0.33 |
| batter v type | 1200 | off | 0.05 |
| bowler v batter hand | 3600 | off | 0.01 |
| batter v exact bowler | 1200 | off | 0.015 |

"off" = k of 1,000,000 = the layer does nothing for wickets.

### Are the k = 1,000,000 values a bug? No, a real finding (checked)

The grid maximum means "no data-driven adjustment at all". It shows up only in `k_w`, never in `k_run`. I re-ran the test set with
finite `k_w` for four of these layers (isolated mode, test wicket log loss; off = 0.198922):

| Layer | k_w = 10,800 | 1,200 | 400 | 135 |
|---|---|---|---|---|
| pair | 0.198921 | 0.198915 | 0.198906 | 0.198908 |
| batter v type | 0.198922 | 0.198934 | 0.198996 | 0.199296 |
| bowler | 0.198934 | 0.199043 | 0.199260 | 0.199673 |
| batter in phase | 0.198914 | 0.198882 | 0.198918 | 0.199187 |

Letting these layers move the wicket probability makes the test loss worse (batter v type, bowler) or changes it by under 0.00002
(pair). So a batter's record against a bowling type, and against one bowler, does not predict his dismissal chance beyond his
overall level and the bowling kind. Mechanism (my reading, not tested): dismissals are rare (about 4.5 % of balls), so 100 balls
hold only 4-5 wickets and the sampling noise is as large as any real difference. The runs side (k_run finite) does carry some signal.

## Validation: fit through IPL 2024, test on IPL 2025-26 (33,303 balls; 252,383 train)

Log loss over the 7 classes (lower is better); the 5-class version groups 1-3; wicket = log loss of P(out); Brier for the 5 classes.

| Predictor | 7-class log loss | 5-class log loss | 5-class Brier | Wicket log loss | Wicket Brier |
|---|---|---|---|---|---|
| (a) league phase average (2023+ cells) | 1.5108 | 1.3295 | 0.6814 | 0.1996 | 0.04823 |
| (b) batter raw career rate | 1.5428 | 1.3563 | 0.6939 | 0.2020 | 0.04890 |
| (c) raw head-to-head (else batter raw) | 1.7069 | 1.4894 | 0.7249 | 0.2344 | 0.05392 |
| Model | 1.4976 | 1.3163 | 0.6752 | 0.1988 | 0.04815 |

Raw rates are worse than the league average they ignore: they overfit, which is exactly what the shrinkage fixes.
MAE of expected runs per ball, 668 batter-bowler pairs with at least 12 test balls: league 0.4331, batter raw 0.4509, raw
head-to-head 0.5507, model **0.4173**.
Ball subset where the pair had at least 6 earlier balls (11,096 test balls): model 1.4733 v league 1.4876 v raw head-to-head 1.8135.

Where the gain sits (cumulative log loss as layers are added): league 1.5108, +state 1.5069, +kind 1.5049, +type/hand 1.5044,
+batter 1.4998, +bowler 1.4988, +batter-phase 1.4983, +bowler-phase 1.4981, +batter-kind 1.4977, +batter-type 1.4976, +hand 1.4976, +pair 1.4976.

By head-to-head evidence (7-class log loss, model v league): pair >= 30 prior balls (2,737 test balls) 1.4256 v 1.4469; 12-29
(4,595) 1.4881 v 1.5012; 1-11 (7,760) 1.4746 v 1.4890; none (18,211) 1.5206 v 1.5322. The gain is of similar size everywhere,
which is what you would expect if it comes from the batter's level and not from the pairing.

### Calibration of P(out) (8 equal-count bins, 33,303 test balls)

| Predicted range | Balls | Mean predicted | Actual |
|---|---|---|---|
| 2.1-3.6 % | 4,169 | 3.23 % | 2.90 % |
| 3.6-3.9 % | 4,234 | 3.77 % | 3.61 % |
| 3.9-4.3 % | 4,089 | 4.08 % | 4.43 % |
| 4.3-4.6 % | 4,165 | 4.43 % | 4.25 % |
| 4.6-5.0 % | 4,162 | 4.80 % | 5.53 % |
| 5.0-5.7 % | 4,161 | 5.29 % | 5.58 % |
| 5.7-7.2 % | 4,160 | 6.33 % | 5.53 % |
| 7.2-13.5 % | 4,163 | 8.57 % | 9.03 % |

Each bin is within about 0.7 points and there is no systematic tilt. With about 4,100 balls a bin and a 4-9 % rate, the sampling
error alone is 0.3-0.4 points, so the bumps are mostly noise.

## Confidence label

Judgement thresholds (not fitted): with a named bowler, **strong** = 30 or more balls head-to-head; **medium** = 12-29 head-to-head or
150 or more against his type; else **thin**. With a type or kind only: strong 150+ balls v that type (kind), medium 50-149. No bowler
or type: medium with 300+ career balls, else thin. The validation supports the labels only weakly: model v league gap is similar
at every evidence level (see above), so "strong" means "much data", not "the prediction is much sharper".

## Five worked examples (module card, IPL, `competition=ipl`; raw = plain counts of the most specific group, all phases and states pooled, all seasons)

| Example | Predicted runs/over | Pred. wicket % | League runs/over, wicket % (same phase) | Raw (balls, runs/over, wicket %) | Evidence | Confidence |
|---|---|---|---|---|---|---|
| V Kohli v JJ Bumrah, middle | 7.84 | 3.5 | 8.56, 4.5 | head-to-head: 108, 8.86, 4.6 | 6,926 career, 792 v his type, 108 pair | strong |
| V Kohli v left-arm orthodox | 8.08 | 3.1 | 8.91, 4.8 | v type: 941, 6.94, 1.8 | 941 v type | strong |
| SA Yadav v leg spin, death | 10.04 | 6.9 | 10.14, 7.9 | v type: 570, 8.44, 2.8 | 3,083 career, 570 v type | strong |
| H Klaasen v spin | 9.83 | 4.1 | 9.07, 5.5 | v kind: 531, 10.38, 2.8 | 1,262 career, 531 v kind | strong (after the fix below) |
| Abhishek Sharma v pace, powerplay | 10.58 | 5.0 | 8.98, 4.1 | v kind: 936, 9.74, 5.8 | 1,389 career, 936 v kind | strong (after the fix below) |

How to read them:
- **Kohli v Bumrah:** raw 8.86 runs/over looks better than the prediction 7.84 mainly because the raw number pools powerplay and death
  (higher scoring) while the prediction is for the middle overs. Against the middle-overs league figure (8.56) Kohli is 0.7 runs lower
  against Bumrah, and the wicket chance is 3.5 % v 4.5 % league; the model says Bumrah costs Kohli runs but does not make him
  likelier to get out than the average bowler.
- **Kohli v left-arm orthodox:** raw 6.94 runs/over and 1.8 % wickets across all phases is a very low-scoring, safe record; the model
  moves toward the league (8.08, 3.1 %) because 941 balls with 17 wickets are not enough to trust 1.8 %. Typical batter v this type:
  8.51 runs/over.
- **SA Yadav v leg spin at the death:** the model starts from a 7.9 % league wicket chance and lands at 6.9 %; the raw 2.8 % is all
  phases. His death-overs score is close to league average (10.04 v 10.14) (guess: the batter-in-phase layer holds him near the death average).
- **Klaasen v spin:** predicted 9.83 runs/over against a typical-batter-v-spin value of 8.65 and a league 9.07. The model sits below the raw 10.38 because k_run = 1,200 for the kind layer shrinks even 531 balls. The model also lowers his wicket
  chance to 4.1 % from league 5.5 %, driven by his overall record.
- **Abhishek v pace in the powerplay:** 10.58 runs/over against a league 8.98. Dot % 35.4 and four % 20.5: a boundary-or-nothing
  profile. This is a short IPL career, and the 2023+ era is what his data comes from.

The two "thin" labels the first run produced for Klaasen and Abhishek were a bug in `confidence()` (it read balls against a specific
type, which is 0 when the question names only pace or spin); fixed, the label now uses the balls at the level asked (`ask_balls`).
The table above shows the rating after the fix; the numbers in the cells did not change.

## Which seasons feed each number

- League baseline (phase, state, kind, type x hand): IPL 2023-2026 balls only (the Impact Player era).
- All player layers: every IPL ball 2008-2026, each weighted `exp(-0.25 * years before the newest season)`: 2026 and 2025 count as
  1.0 and 0.78, 2023 as 0.47, 2016 as 0.09. (The production fit uses all data, 2008-2026; the validation fit used data through 2024 only.)
- The raw columns are unweighted counts over all seasons.

## Doubts

- The gain is small (0.9 % in log loss). This is a descriptive tool with honest shrinkage, not a forecasting edge.
- The (a) v (b) decision rests on a 0.002-nat margin; either is defensible.
- Evidence labels are judgement, and the validation does not show the model sharper for "strong" cases.
- The k's were fitted on the IPL only and are reused for other competitions (their own data, untested k).
- The batting-hand layer excludes 22 % of balls (unknown hand); the type layers exclude 2 % (unknown bowling type).
- `phase = all` and `wickets_down / innings = any` are weighted mixes (phases by how the batter faces them; states by the latest-era
  league mix), not a model of "an average over". The chase required-rate band exists only for trusted (non-D/L) chases; others fall in the middle band.
- No line, length, field or batter-position information; an opener's phase effect is not separated from his slot.
- Bumrah, Kohli etc. checked only for sense (probabilities sum to 1, direction), not against an outside source.
