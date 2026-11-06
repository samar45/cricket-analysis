# Franchise leagues added: ILT20, MLC, BPL, LPL (2026-11-07)

Data: Cricsheet (ODC-BY, credit "Cricsheet"). Written by a worker; the lead has not reviewed it yet.

## 1. What was added
Four CSV2 zips downloaded by `cricket ingest --format <key> --db data/cricket_analytics_leagues.duckdb` (all men's).
Code: `competitions.py` keys `ilt20`, `mlc`, `bpl`, `lpl` (zip names `ilt`, `mlc`, `bpl`, `lpl`), `config.yaml` formats list, `SOURCES` in `models/league_translation.py`.
Super Smash (`ssm`) was NOT added: its zip mixes men and women, and it is a provincial league, not a franchise league with IPL players. Add later only if wanted (needs a gender split).

| Key | Label | Matches | Balls | First | Last |
|---|---|---|---|---|---|
| ilt20 | International League T20 | 134 | 31,407 | 2023-01-13 | 2026-01-04 |
| mlc | Major League Cricket | 109 | 25,529 | 2023-07-13 | 2026-07-18 |
| bpl | Bangladesh Premier League | 469 | 111,232 | 2012-02-11 | 2026-01-23 |
| lpl | Lanka Premier League | 143 | 32,917 | 2020-11-26 | 2026-08-08 |

## 2. Checks on the copy (`data/cricket_analytics_leagues.duckdb`, 282 MB, gitignored; live DB untouched)
- Matches: live 11,113 -> copy 11,968 (+855 = 134+109+469+143). Old match_ids missing from the copy: 0.
- Every old competition (ipl 1,243 / 295,732 balls; t20i men 3,627 / 816,237; women 2,183 / 496,500; bbl, psl, cpl, sa20, hundred, blast, smat) has identical match and ball counts to the live DB.
- `cricket health --db <copy>`: ok=True, duplicates 0, orphans 0, all golden checks pass (Kohli 8,661; Buttler 863; Bumrah 5/10; stand 229; IPL 2025 = 74; CSK 142).
- Teams: BPL has 34 team names (franchises rename/relocate often), LPL 19, ILT20 7 (Sharjah Warriorz/Warriors are two spellings), MLC 6.

## 3. Reference files
- `venue_country.csv`: +8 rows (MLC: Morrisville, Pomona, Oakland, Grand Prairie x2 city spellings; BPL: Khulna, 2 Chattogram grounds), all high confidence. ILT20 and LPL venues were already in the file.
- `team_home.csv`: unchanged. New franchises are unlisted, so home_away reads them as neutral everywhere. That is right for ILT20 (all games in UAE, no home ground) and mostly right for BPL/LPL (central venues); MLC franchises have loose home bases but play in hubs. Add rows later if home/away for these leagues matters.
- `tests/test_fe_home_away.py` passes on the copy (7 passed).

## 4. League translation (new rows in `models/data/league_translation.csv`)
Same method as VALUE_m3 (>=200 balls in source and in IPL within +-1 year, IPL-ball weighted, bootstrap over players). Existing 56 rows reproduced identically.
Factor above 1 = the IPL number is higher than the source number.

| Source | n bat / bowl | Bat runs/ball | Bat dismissal rate | Bat boundary% | Bowl runs/ball | Bowl wicket rate | Bowl dot% |
|---|---|---|---|---|---|---|---|
| ILT20 | 9 / 15 | 1.07 (0.98-1.14) | 1.17 (1.04-1.35) | 1.21 (1.06-1.36) | 1.15 (1.10-1.21) | 1.07 (0.92-1.23) | 0.92 (0.85-0.97) |
| MLC | 11 / 14 | 1.03 (0.95-1.11) | 0.94 (0.79-1.13) | 1.06 (0.95-1.18) | 1.14 (1.08-1.21) | 0.89 (0.81-1.03) | 0.83 (0.77-0.90) |
| BPL | 16 / 16 | 1.06 (1.03-1.10) | 0.99 (0.90-1.11) | 1.08 (1.03-1.15) | 1.17 (1.12-1.23) | 0.91 (0.80-1.01) | 0.82 (0.79-0.86) |
| LPL | none | - | - | - | - | - | - |

Reading: ILT20 and MLC bowlers go for ~14-15% more per ball in the IPL; batters keep their runs per ball (ILT20 +7%, MLC +3%, both inside noise).
ILT20 batters get out ~17% more often in the IPL (interval 1.04-1.35). With 9-15 players each these are indicative only. Boundary-% factors are high for bowlers (ILT20 1.31) because IPL grounds are small.
LPL: no player has >=200 balls in LPL and in the IPL within one year, so no factor. Not chased.

## 5. Tests against the copy (`CRICKET_TEST_DB=<copy>`)
Golden, home_away, health, video charts and dashboard files: all pass. One golden test needed a scope change: `test_super_over_ties_store_their_winner` counted 83 instead of 76 super-over ties because the new leagues add 7 (all have a winner). It now excludes ilt20/mlc/bpl/lpl from the 76 and checks they carry winners too (`tests/test_golden.py`). A full-suite run was started but is slow with other workers running; not finished, so the full suite on the copy is untested.
Not done: `ingest/update.py` `_CLUB_EVENTS` has no entries for the new leagues, so `cricket update` will not pick them up (re-download with `cricket ingest --format X --redownload`).
