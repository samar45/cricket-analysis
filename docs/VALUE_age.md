# Player birth dates and a first age curve (2026-11-07)

## Source
- Cricsheet `people.csv` (1.2 MB, https://cricsheet.org/register/people.csv) links each Cricsheet player to a Cricinfo ID.
- Wikidata SPARQL (one query, 31,070 items with ESPNcricinfo ID P2697 + date of birth P569, 2.1 MB; raw CSV + query in `data/external/wikidata/sparql_2026-11-07/`). Wikidata is CC0.
- Joined by Cricinfo ID -> `src/cricket_analytics/reference/player_dob.csv` (built by `scripts/build_player_dob.py`). Cricinfo IDs with conflicting DOBs are dropped. Caveat: Wikidata DOBs with low precision (year only) show as Jan 1; not filtered.

## Coverage (share of players with a DOB)
| Group | Players | With DOB |
|---|---|---|
| IPL 2023-26 (batted or bowled) | 356 | 91% |
| 2026 auction pool, players matched to a Cricsheet name | 108 of 156 | 89% (96 of 108) |
| 2026 auction pool, all 156 | 156 | 62% (48 have no Cricsheet name yet, i.e. never played in the data) |
| All players in DB | 11,504 | 50% (the long tail of minor internationals) |

Spot-checks: Kohli 1988-11-05, Bumrah 1993-12-06, Hardik Pandya 1993-10-11 all correct (also Dhoni 1981-07-07).

## Age curve (first look)
Method: players pooled over IPL, BBL, PSL, CPL, SA20, Hundred, Blast per calendar year (2014-2026); at least 100 balls in both seasons; change in runs added per 100 balls from season X to X+1, by age in season X (year minus birth year). Script: `scripts/age_curve.py`.

| Age in X | Batting n | Batting mean change | Bowling n | Bowling mean change |
|---|---|---|---|---|
| <=22 | 167 | -1.4 | 194 | -4.3 |
| 23-24 | 208 | +0.3 | 229 | -4.8 |
| 25-26 | 261 | -2.0 | 263 | -1.8 |
| 27-28 | 291 | -0.7 | 304 | -2.5 |
| 29-30 | 306 | -2.2 | 279 | -2.7 |
| 31-32 | 296 | -0.3 | 256 | -1.7 |
| 33-34 | 232 | -2.6 | 189 | -2.8 |
| 35+ | 293 | -1.2 | 247 | -3.2 |

(Standard error is 1.3 to 2.0 per row. Bowling "runs added" is signed so that higher is better, same as the module; all means are negative.)

## What it says, plainly
- Almost every group drops a little year on year. That is mostly "regression to the mean": players who did well get picked again, so the next year is on average slightly worse. It is not ageing.
- No clear age trend in either table: differences between buckets are within noise (about 2 points). Only the youngest bowlers (<=24, about -4.5) look worse, and that is also within roughly 2 standard errors of the rest.
- So with this simple method, the data does not show a decline by age 35. A real curve needs a fix for selection (who gets re-picked) and more seasons per player (e.g. fit each player's level, then age as an effect). Not done; no model integration yet.
