# Experiment: Hawk-Eye ball tracking (HawkeyeStats) joined to Cricsheet IPL

Date: 2026-10-24. Approved by Samar as a local experiment. Labels: **[M]** measured by this run, **[G]** guess, **[R]** read from the README or GitHub.
**EXPERIMENTAL, UNLICENSED DATA, LOCAL ONLY.** Nothing here may be committed, published or shown to other users.

## 1. Source and legal note
- Repo `github.com/alittlefitness/HawkeyeStats`, branch `main`. **No licence** (GitHub API `license: null`) [M]. README: "a tidy version of the json data available from https://cricketapi-icc.pulselive.com/" [R], i.e. ICC feed data repackaged by a third party. The repo owner cannot grant ICC/Hawk-Eye rights. Risk stays medium-high for anything beyond private analysis [G].
- Rules followed: `data/external/` added to `.gitignore` first (checked with `git check-ignore`); files read with pandas only, scripts run with `python -I`; no commits; no numbers go into the app.
- **Staleness [M]:** the last commit touching the IPL file is **2021-10-17**; the repo's last push was 2022-02-08. The data stops at IPL 2021 and has not been refreshed since.

## 2. Files and sizes
| File | Size (GitHub API) | Downloaded |
|---|---|---|
| mensIPLHawkeyeStats.csv | 19.9 MB (a real CSV, not an LFS pointer) | yes |
| womensIPLHawkeyeStats.csv | 0.29 MB | yes |
| README.md | 1 KB | yes |
| ODI / Test files (men, women) | 55.6 / 68.3 / 1.2 / 0.5 MB | no (not asked) |

Saved in `data/external/hawkeye/` (git-ignored), together with `joined_men.csv.gz` (our joined output, also ignored). Total on disk about 20 MB plus the joined file.

## 3. Profile (men's IPL) [M]
- 149,424 rows, 24 columns, **628 matches** (matchId 2..32242). Innings 1-2 hold 149,295 rows; 129 super-over rows (innings 3-4) were ignored.
- Columns: matchId, delivery (`innings.over.sequence`; over is 1-based; sequence also counts wides and no-balls), ball (legal ball number), batter, batterId, rightHandedBat, nonStriker(+Id), bowler, bowlerId, rightArmedBowl, bowlingStyle (FAST_SEAM, MEDIUM_SEAM, SEAM, LEG_SPIN, OFF_SPIN, ORTHODOX, UNORTHODOX), ballSpeed, dismissalDetails, runs, batterRuns, bowlerRuns, extras (Wd, Lb, Nb, B, NbB, NbLb), pitchX, pitchY, stumpsX, stumpsY, fieldX, fieldY.
- **No date, season or team columns.** Names are full ("Faf du Plessis"), Cricsheet uses initials. The only usable keys are the ICC matchId and the delivery order.
- Null %: pitchX/Y and stumpsX/Y 3.4%, fieldX/Y 2.3%, extras 95.0%, dismissalDetails 95.1%, all other fields 0%.
- `ballSpeed`: -1 is the "missing" marker (5.9% of joined balls). Treated as NaN. Unit m/s per README.
- Glitch values: pitchX up to 242, pitchY from -88 to 898, stumpsY down to -3319. Quantiles used below are robust; buckets put glitches in the end bins. Not cleaned further.
- Women's IPL file: 9 matches, 2,096 rows. **Cannot be joined**: our DB has no women's IPL or Women's T20 Challenge (competitions: ipl = men only, t20i, blast, bbl, cpl, psl, hundred, sa20). Ignored.

## 4. Coordinate system
| Field | What it is | Evidence | Status |
|---|---|---|---|
| ballSpeed | m/s (README). Median fast-seam 38.3 m/s = 138 km/h, spin about 25 m/s = 90 km/h | sanity check 2 | [M] plausible |
| pitchY | metres from the **batter's stumps** to the bounce point (0 = at the stumps, bigger = shorter ball) | 5% / 50% / 95% = 1.5 / 6.3 / 10.8 m; mean 5.5 m in death overs vs 7.1 m in powerplay | [G], well supported |
| pitchX | sideways metres at the bounce point, 0 about the middle line, absolute (not flipped for left-handers) | stumpsX median is RH -0.16 / LH +0.15 (mirrored); pitchX median RH -0.28 / LH +0.02, so pitchX looks shifted by about -0.15 m | [G] |
| stumpsX / stumpsY | sideways position / height of the ball as it reaches the stumps. stumpsY median 0.71 m (= stump height), 5-95% = 0.25-1.32 | | [M] height is clearly metres; only present when the ball reaches the batter |
| fieldX / fieldY | integers 0-96 on both axes, probably a coarse ground grid (wagon wheel) | median (38, 34); 0 shows up when no shot was tracked | [G] not decoded; origin and scale unknown |

Handedness: `rightHandedBat` is in the file. For a right-hander the off side is negative X, for a left-hander positive X [G, from the mirrored stumpsX]. I added +0.15 m to pitchX before mirroring; the offset is a guess.

## 5. Join method and coverage
**Match level** (names differ, no date): for each innings, take the list of total runs per over. Compare the Hawk-Eye fingerprint with every Cricsheet IPL match (both innings must agree exactly). [M] **627 of 628 Hawk-Eye matches (99.8%) map to exactly one Cricsheet match; 0 ambiguous; no Cricsheet match claimed twice.** The one miss is ICC matchId 2439 (124 + 114 deliveries). The only unclaimed Cricsheet match in 2014 is `729309`, probably the same game with a different ball count (guess, not chased).

**Ball level:** inside a matched innings, the n-th Hawk-Eye delivery (ordered by over, sequence) is paired with the n-th Cricsheet delivery. Check: total runs on the ball agree. [M] **148,844 aligned balls, runs agree on 148,842 (100.00%).** A stricter test (bowler surname also agrees) passes 99.02%. The 1% that fail are name spellings (CV Varun vs Varun Chakaravarthy, AN Ahmed vs Abu Nechim, Harmeet Singh vs Harmeet Singh Bansal), plus about 6 balls in one match (Ravi Bishnoi vs Nathan Ellis) that are a real misalignment, negligible.

Coverage = Cricsheet IPL balls (innings 1-2) that have Hawk-Eye data [M]:

| Season | Cricsheet matches | Cricsheet balls | Matches joined | Balls with pitch/speed data | % | Balls with field (wagon) data | % |
|---|---|---|---|---|---|---|---|
| 2007/08 - 2011 | 248 | 58,586 | 0 | 0 | 0 | 0 | 0 |
| 2012 | 74 | 17,767 | 74 | 16,710 | 94.1 | 17,641 | 99.3 |
| 2013 | 76 | 18,152 | 76 | 17,135 | 94.4 | 18,140 | 99.9 |
| 2014 | 60 | 14,288 | 59 | 13,605 | 95.2 | 14,050 | 98.3 |
| 2015 | 59 | 13,641 | 59 | 12,861 | 94.3 | 13,638 | 100.0 |
| 2016 | 60 | 14,096 | 60 | 13,808 | 98.0 | 14,006 | 99.4 |
| 2017 | 59 | 13,849 | 59 | 13,489 | 97.4 | 13,841 | 99.9 |
| 2018 | 60 | 14,286 | 60 | 13,854 | 97.0 | 14,283 | 100.0 |
| 2019 | 60 | 14,293 | 60 | 13,926 | 97.4 | 14,125 | 98.8 |
| 2020/21 | 60 | 14,510 | 60 | 14,301 | 98.6 | 13,456 | 92.7 |
| 2021 | 60 | 14,413 | 60 | 14,218 | 98.6 | 12,386 | 85.9 |
| 2022 - 2026 | 367 | 87,676 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **1,243** | **295,557** | **627** | **143,907 (48.7%)** | | | |

(2007/08-2011 is four seasons summed, 2022-2026 five seasons summed.) **Net: nearly complete for IPL 2012-2021 (94-99% of balls have pitch data), nothing for 2008-2011 and 2022-2026**, i.e. 49% of all IPL balls in our DB. Missing the last five seasons is the big limit.

## 6. Derived buckets and sanity checks
Thresholds (all [G], standard coaching bands; pitchY = metres from the batter's stumps):
- Length: yorker / full toss < 2 m, full 2-6 m, good 6-8 m, short > 8 m.
- Line (off-side distance after the +0.15 m shift and the left/right mirror): leg side (beyond -0.114 m), on stumps (+-0.114 m, half the 22.86 cm stump width), off-stump line 0.11-0.35 m, outside off 0.35-0.9 m, wide of off > 0.9 m.
- Wides excluded.

Overall (139,752 tracked non-wide balls) [M]: full 39.1%, good 28.6%, short 26.1%, yorker/full toss 6.3%. Line: off-stump line 31.3%, on stumps 27.9%, outside off 21.8%, leg side 18.4%, wide 0.8%.

**Sanity 1, length by phase (death overs should be fuller): passes** [M]

| Phase | yorker/FT % | full % | good % | short % | mean pitchY |
|---|---|---|---|---|---|
| Powerplay (ov 1-6) | 2.3 | 27.0 | 35.6 | 35.2 | 7.11 m |
| Middle (7-15) | 3.8 | 48.0 | 28.0 | 20.2 | 6.11 m |
| Death (16-20) | 16.7 | 37.5 | 20.2 | 25.5 | 5.51 m |

Death overs have about 7x the yorkers of the powerplay. The 25% short at the death is probably the bouncer/slower-ball mix (guess).

**Sanity 2, speed by style (spinners should be slower): passes** [M]. Median km/h: fast seam 137.7, medium seam 131.1, "seam" 127.6, off spin 92.2, orthodox 92.8, leg spin 88.4, unorthodox 82.9.

**Sanity 3, outcome by length** [M] (balls faced excluding wides/no-balls; wickets exclude run-outs). Yorker/full toss: strike rate 150.8, 22 balls per wicket. Full: 134.5, 19. Good length: 116.3, 23. Short: 134.2, 22. Good length costs the fewest runs, as expected. Wicket-rate differences were not tested for significance.

## 7. Demo (experimental, unlicensed data, local only)
**V Kohli**, IPL 2012-2021, joined and tracked balls faced: 3,629. The DB has 3,775 legal balls and 117 non-run-out dismissals for the same years, so 96% of balls and 116 of 117 dismissals are covered [M].

| Length | Balls | Runs | Dismissals | Strike rate | Balls per dismissal |
|---|---|---|---|---|---|
| yorker / full toss | 174 | 293 | 6 | 168.4 | 29 |
| full 2-6 m | 1,456 | 2,027 | 44 | 139.2 | 33 |
| good 6-8 m | 1,030 | 1,315 | 34 | 127.7 | 30 |
| short > 8 m | 969 | 1,201 | 32 | 123.9 | 30 |

Small cells (6 dismissals in the first row): do not over-read.

**JJ Bumrah**, 2,398 tracked balls (DB: 2,472 non-wide balls for 2012-2021), median speed 137.8 km/h [M]:

| Length (% of balls) | All | Powerplay | Death | All bowlers, death |
|---|---|---|---|---|
| short > 8 m | 40.2 | 44.7 | 32.5 | 25.5 |
| good 6-8 m | 26.5 | 35.4 | 16.6 | 20.2 |
| full 2-6 m | 18.5 | 13.9 | 24.7 | 37.5 |
| yorker / full toss | 14.7 | 6.0 | 26.2 | 16.7 |

Bumrah's line: outside off 40.7%, off-stump line 25.1%, leg side 19.3%, on stumps 14.4%. It reads as expected: the yorker bowler at the death (26% vs 17% league-wide), back of a length with the new ball.

## 8. Verdict
- **Technically worth it.** The join is clean and cheap: 99.8% of matches match exactly, runs agree on 100% of 148,842 aligned balls, no fuzzy name matching is needed, and all sanity checks pass. The data gives length, line, speed, bowling style, handedness and a wagon-wheel grid.
- **Practically limited.** It ends at IPL 2021, covers only 2012-2021 (49% of our IPL balls), has not been updated since late 2021, and has no licence. Nothing for 2022-2026.
- **Recommendation [G]:** at most an **optional local-only table** for historical analysis, behind a flag and a "personal use only" label. Never in the committed/LFS DB, never in a deployed or shared dashboard. If the dashboard ever goes public, drop it. Treat it as a research tool unless a licensed source appears.
- **What integrating would take:**
  1. S - `ingestion/hawkeye.py`: read the CSV, apply the `join.py` fingerprint logic, write a separate `data/external/hawkeye.duckdb` (new file, never the main DB) with match_id, innings, ball_seq, speed, pitch_x, pitch_y, stumps_x, stumps_y, field_x, field_y.
  2. S - a SQL fragment `deliveries LEFT JOIN hawkeye` plus a `has_tracking` flag, so modules degrade gracefully where it is missing.
  3. M - a "Length and line" module (by phase, bowler, batter) with a visible "2012-2021 only" notice.
  4. M - decode fieldX/Y for a wagon wheel (origin and scale unknown; verify against known shots).
  5. S - settle the open guesses: the 0.15 m pitchX offset, the length thresholds, match 2439.
- **Surprises:** (a) no dates in the file, but the per-over-runs fingerprint makes dates unnecessary; (b) ballSpeed uses -1 for missing; (c) coordinate glitches reach pitchY 898; (d) pitchX is not symmetric between left- and right-handers; (e) the repo is frozen at 2021.

## Reproduce
```
.venv/Scripts/python -I experiments/hawkeye/profile.py data/external/hawkeye/mensIPLHawkeyeStats.csv
.venv/Scripts/python -I experiments/hawkeye/join.py data/external/hawkeye/mensIPLHawkeyeStats.csv data/cricket_analytics.duckdb data/external/hawkeye/joined_men.csv.gz
.venv/Scripts/python -I experiments/hawkeye/derive.py data/external/hawkeye/joined_men.csv.gz
```
