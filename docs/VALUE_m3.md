# M3: domestic T20 data and league translation (2026-11-06)

Data: Cricsheet (ODC-BY, credit "Cricsheet"). Written by a worker; the lead has not reviewed it yet.

## 1. What Cricsheet has (checked on its downloads page and by HEAD requests)
Syed Mushtaq Ali Trophy (SMAT) exists: 695 men's matches, CSV2 zip `sma_csv2.zip` (3.6 MB; downloaded, 1,391 files).
Other T20 sets with CSV2 that we do NOT have (sizes in MB): Bangladesh Premier League `bpl` 2.6 (469 matches), Lanka
Premier League `lpl` 0.8 (143), Major League Cricket `mlc` 0.6 (109), International League T20 `ilt` 0.75 (134),
CSA T20 Challenge `ctc` 1.7 (314), Super Smash `ssm` 2.5 (467, both genders), Major Clubs T20 `mct` 0.6 (121),
Nepal Premier League `npl` 0.4 (76), Ireland Inter-Provincial `ipt` 0.6 (111), European T20 Premier League `etpl` 0.2 (31),
non-official T20Is `it20s` 1.1 (320). Women's: WBBL 527, WPL 88, women's Blast 112, etc. All are small. Nothing was added
except SMAT. Ours before: ipl, t20i (men + women), bbl, psl, cpl, sa20, hundred, blast.

## 2. SMAT coverage is patchy (important)
| Calendar year | Matches |
|---|---|
| 2016 | 83 |
| 2018 | 79 |
| 2019 | 261 (2018/19 + 2019/20) |
| 2021 | 181 (2020/21 + 2021/22) |
| 2022 | 44 |
| 2023 | 39 |
| 2024 | 8 |

No 2017 and no 2025 season, and the last match is 2024-12-15. Recent seasons are mostly the televised matches only, so
"recent SMAT" means roughly 2019-2021 for most players. Total 158,839 deliveries.

## 3. New DB and checks
Live DB untouched. Copy: `data/cricket_analytics_m3.duckdb` (252 MB, gitignored). Loaded with
`cricket ingest --format smat --db data/cricket_analytics_m3.duckdb`. Code changes: `competitions.py` (key `smat`,
competition value `smat`, men, club), `config.yaml` formats list.
- Old match_ids: 10,418 in old DB, 0 missing in the copy; copy has 11,113 (+695 = SMAT only).
- Per-competition match and ball counts for old competitions identical (e.g. ipl 1,243 / 295,732; t20i men 3,627 / 816,237).
- `cricket health --db` on the copy: ok=True; duplicates 0, orphans 0, all golden checks pass (Kohli 8,661; Buttler 863; Bumrah 5/10; stand 229; IPL 2025 = 74; CSK 142).
- Swapping needs the lead's go: the live DB must stay closed, and the dashboard's competition lists may need `smat` added (not checked).
- Note: `cricket update` only picks events it can classify; SMAT is not in its event map, so SMAT will not auto-update (Cricsheet SMAT zip must be re-downloaded by `cricket ingest --format smat --redownload`).

## 4. League translation (`src/cricket_analytics/models/data/league_translation.csv`)
Method: players with >=200 balls in the source and >=200 in the IPL, within +-1 calendar year. Factor = actual IPL events / what the
player's source rate predicts for the same IPL balls (IPL-ball weighted). 95% interval: bootstrap over players, 2000 draws.
Factor above 1 means the IPL number is higher than the source number. Super overs excluded, men only.
Rates are per legal ball (batters: balls faced, no wides).

| Source | n bat / bowl | Bat runs/ball | Bat dismissal rate | Bat boundary% | Bowl runs/ball (econ) | Bowl wicket rate | Bowl dot% |
|---|---|---|---|---|---|---|---|
| SMAT | 57 / 59 | 0.98 (0.96-1.00) | 1.20 (1.14-1.27) | 0.96 (0.93-1.00) | 1.21 (1.17-1.24) | 0.87 (0.78-0.96) | 0.86 (0.83-0.88) |
| SA20 | 14 / 14 | 1.05 (1.02-1.08) | 0.96 (0.88-1.08) | 1.08 (1.02-1.15) | 1.17 (1.11-1.24) | 1.01 (0.88-1.16) | 0.88 (0.83-0.94) |
| T20I men | 108 / 128 | 1.01 (0.99-1.03) | 0.91 (0.88-0.95) | 1.03 (1.01-1.06) | 1.05 (1.03-1.06) | 0.90 (0.86-0.94) | 0.95 (0.93-0.97) |
| BBL | 37 / 48 | 1.02 (0.99-1.04) | 1.07 (0.99-1.16) | 1.12 (1.08-1.17) | 1.06 (1.03-1.09) | 0.95 (0.89-1.02) | 1.01 |
| PSL | 13 / 11 | 1.01 (0.96-1.08) | 1.08 (0.94-1.24) | 1.03 | 1.07 (1.01-1.12) | 0.92 (0.82-1.10) | 0.95 |
| CPL | 28 / 29 | 1.03 (0.99-1.07) | 1.03 (0.98-1.09) | 1.08 | 1.11 (1.06-1.17) | 0.98 (0.90-1.05) | 0.82 |
| Blast | 27 / 36 | 0.96 (0.91-1.01) | 1.09 (1.03-1.20) | 1.00 | 1.05 (1.02-1.10) | 0.88 (0.79-0.96) | 1.01 |

Full table (all 4 metrics, all sources, intervals, ball counts) is in the CSV. Plain reading for SMAT: a batter keeps his
runs per ball but gets out ~20% more often in the IPL; a bowler goes for ~20% more runs per ball and takes ~13% fewer wickets.
Wicket rates are the noisiest; SA20 and PSL rest on 11-14 players, so treat them as indicative only.

## 5. Uncapped scouting preview (SMAT 2020 onwards, under 100 IPL balls) - TRANSLATED ESTIMATE
Value = translated runs above the IPL average per 100 balls (rate shrunk toward the SMAT mean with 150 balls of prior; each
wicket assumed worth 20 runs, which is an assumption). Only 150-500 SMAT balls per player, so this is a noisy shortlist, not a ranking.
Source file: `src/cricket_analytics/models/data/scouting_preview_smat.csv`.

| # | Player | Role | SMAT balls | Value per 100 | IPL balls | IPL 2027 squad |
|---|---|---|---|---|---|---|
| 1 | Ashutosh Aman | bowl | 264 | +44.8 | 0 | no |
| 2 | Shivank Vashisth | bowl | 174 | +43.9 | 0 | no |
| 3 | Cheepurapalli Stephen | bowl | 244 | +36.3 | 0 | no |
| 4 | AA Barot | bat | 153 | +33.2 | 0 | no |
| 5 | Ravi Teja | bowl | 311 | +32.9 | 0 | no |
| 6 | Rahul Singh | bat | 251 | +32.8 | 0 | no |
| 7 | Vishnu Vinod | bat | 182 | +30.6 | 65 | PBKS |
| 8 | SP Jackson | bat | 493 | +28.1 | 57 | no |
| 9 | Khrievitso Kense | bowl | 185 | +26.6 | 0 | no |
| 10 | Chetan Bist | bat | 284 | +26.2 | 0 | no |
| 11 | Chirag Khurana | bat | 175 | +26.2 | 0 | no |
| 12 | Kishan Lyngdoh | bat | 173 | +25.5 | 0 | no |
| 13 | NA Rathva | bowl | 324 | +24.2 | 0 | no |
| 14 | Amit Yadav | bowl | 168 | +21.5 | 0 | no |
| 15 | RK Bhui | bat | 299 | +20.8 | 26 | no |
| 16 | Milind Kumar | bat | 155 | +20.2 | 0 | no (plays for USA; 578 T20I balls) |
| 17 | AV Wankhade | bat | 278 | +19.0 | 0 | no |
| 18 | Pankaj Jaswal | bowl | 245 | +17.4 | 0 | no |
| 19 | Shivam Chauhan | bat | 274 | +15.6 | 0 | no |
| 20 | Tanush Kotian | bowl | 289 | +15.3 | 31 | no |

## 6. Doubts
- Thin data: SMAT has no 2025 and few 2022-24 matches, so many scouted players are judged on one 2019-21 season. Anyone whose form moved since then is invisible.
- "Uncapped Indian" is not verified: the list uses "few IPL balls" and flags T20I balls only. Capped / overseas status needs the contracts CSV or ESPNcricinfo. Milind Kumar is a USA player.
- Selection bias: translation factors come from players who reached the IPL (survivors), so they likely understate how hard the IPL is for an average domestic player. Treat translated values as optimistic.
- Name matching is by Cricsheet name string (initials differences could split or merge players). Squad flag matched to `cricsheet_name` in `ipl_contracts.csv` only.
- Wicket cost of 20 runs and the 150-ball prior are my choices, not tuned.
- Domestic pitch/ball conditions and opposition quality differ by zone; no adjustment was made.
- Ranking mixes batters and bowlers on one scale; per-role comparisons are safer.
