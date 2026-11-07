# M14: does auction price depend on demand? (built 2026-11-07, worker)

Code: `models/demand.py` (rebuild: `.venv\Scripts\python -m cricket_analytics.models.demand`, a few seconds, no DB write), `tests/test_demand.py`. Outputs: `models/data/demand_features.csv`, `demand_results.json`. Existing models and defaults are untouched.

## Answer first
**Demand is real in the data, but it did not make the price model better on the final test, so it is NOT adopted.**
- Bidding wars exist: a sold player that many teams could use and afford goes for far more than base price. But the raw link is mostly "stars come early, when every team has money". With controls it shrinks to about +4% per extra interested team.
- Adding demand features to the shipped model (S1) cut the error in 2024 and 2025 (the 2025 mega: 2.08 to 1.82 crore) but **made 2026 worse (1.88 to 1.96-2.07 crore; "price = base" is 1.89)**. Pooled over three years the gain is 0.11-0.15 crore per player, with a 90% range that only just excludes zero and is driven by 2025.
- Sold / unsold: AUC moves up a little (2026: 0.56 to 0.60; 2025: 0.61 to 0.61-0.63; 2024: 0.60 to 0.63-0.66), still weak.
My pre-set rule (adopt only if it beats the shipped model on validation 2025 by 1% AND does not lose on the 2026 test): met the first, failed the second.

## What was built
Each auction is replayed lot by lot (sold players in `lot_no` order). The start state is each team's pre-auction squad (real retention list 2022/25/26; 2023/24 rolled forward, see VALUE_m6). Per team we track purse left (cap minus squad prices), squad places (max 25), overseas places (max 8) and role holes (best-XII quota per role from `scarcity.py`: keeper 1, opener 2, top order 1, middle 2, finisher 1, three pace phases 1 each, spin 2; a player "can fill" a role at weight 0.25 or more). For each lot, using only lots before it:
| feature | meaning |
|---|---|
| n_afford | teams with a free place, an overseas place if needed, and spare purse (purse minus 0.2 cr for each place still needed to reach 18) at least the base price |
| n_need | of those, teams with a hole in one of the player's roles |
| n_hole | teams with such a hole whatever their money |
| lmax_spare, lsecond_spare | spare purse of the richest and second-richest team with need, as log(1 + % of total purse) |
| pos, early | share of the auction elapsed; first 10% of lots |
| no_role | the player fills no data-driven role (unclassified players count as no demand) |
"Small" set = n_need, lmax_spare, pos. "All" = the table. They are added to both parts (price and sold) of the shipped hurdle, same ridge/logistic code, same penalty search. Check: with no extra columns the code gives 2.083 (2025) and 1.883 (2026), identical to VALUE_m4.

## Out of sample (train on earlier years only; MAE in crore on sold players)
| fold | price = base | shipped S1 | S1 + demand small | S1 + demand all |
|---|---|---|---|---|
| 2024 (train 2022-23, 72 sold) | 2.44 | 2.36 | 2.24 | 2.25 |
| 2025 validation (train 2022-24, 182 sold) | 2.54 | 2.08 | 1.85 | **1.82** |
| 2026 test (train 2022-25, 77 sold) | **1.89** | **1.88** | 2.07 | 1.96 |
| Sold AUC 2024 / 2025 / 2026, shipped | | 0.60 / 0.61 / 0.56 | small: 0.63 / 0.63 / 0.59 | all: 0.66 / 0.61 / 0.60 |
Paired gain (shipped error minus demand error, 331 players over the 3 folds, bootstrap over players): small +0.11 cr (90% range +0.02 to +0.21); all +0.15 cr (+0.005 to +0.31). Positive = demand better. The pooled gain is the 2025 mega talking; 2026 alone goes the other way.

## Bidding-war check (615 sold players, price / base price)
| teams with need and money | players | mean price/base | median | sold above base |
|---|---|---|---|---|
| 0 | 418 | 3.5 | 1.0 | 38% |
| 1-2 | 88 | 3.9 | 2.0 | 65% |
| 3-4 | 48 | 5.3 | 3.0 | 71% |
| 5-6 | 38 | 5.9 | 3.6 | 84% |
| 7+ | 23 | 4.9 | 4.1 | 100% |
Median ratio rises steadily with the number of interested teams (Spearman 0.34). But n_need and position are tied (Spearman -0.47): early lots are stars, and every team still has money and holes. Regression of log(price/base) on n_need: with base-price tier and auction-year controls +13% per extra team (90% range +10% to +16%); **adding position, overseas and capped: +4% (+0.7% to +7%)**. So demand is a small real effect on top of "stars go early", not the main driver.

## What to trust
- Trust: the direction (more teams that can afford and need him, higher the premium over base) and the shape of the table. Do not trust the exact size.
- Do not trust the price model with demand features for 2027: it won a mega (2025) and lost the mini (2026), and the 2026 test is the cleaner out-of-sample run.

## Caveats
- **Unsold players have no lot order** in the data (only sold lots have `lot_no`; 2026 unsold have a `set_no`). Their state is taken at their set's median sold lot (2026) or the median lot of sold players with the same base price (2022-25). This is a guess and affects the sold/unsold AUC most.
- Squads for 2023 and 2024 are derived (recall 86%, precision 79% when checked on 2026); purses there are approximate. RTM and mid-auction trades are not modelled. The real bidding limit for a team (its own plan, ceiling) is unobserved; "can afford" is only the purse floor.
- Role holes depend on the data-driven roles; 21-48% of the pool has no role and counts as no demand. Keeper list is incomplete.
- Five auctions, 77-182 sold per test fold: differences of 0.1 crore are inside noise. Features use realised earlier outcomes of the same auction, which would be unknown in advance for 2027 (they need a live replay or simulated order).
- The lot order is the real one; a pre-auction forecast cannot use the "state at the lot" features. Only the room-total version (purses and holes before the auction) is available then.
