# WORK_state_leagues (worker log)
MILESTONE: Recon done 2026-11-15. Cricbuzz has no search page (404); the year archives `/cricket-scorecard-archives/<year>` list every series and were enough. Series ids below come from them (2026 ids match the ones Samar gave: 13073, 12851, 12620).
MILESTONE: 4 sample matches (Shere-e-Punjab 171080 + Final 171243, UP 2025 132379 + Final 132648): full scorecard, full ball-by-ball on both innings, ball runs = scorecard total, batting runs + extras = total. One fixture kept in tests/fixtures/cricbuzz_state.
MILESTONE: Backfill code in `cricket cricbuzz sync --backfill state --seasons 2023-2026` (archive pages -> state series -> scrape -> parquet). Note: Cricbuzz series pages say state "complete" (lower case), the sync matched only "Complete"; fixed (case-insensitive).

| Key | League | Season | Cricbuzz series id | Matches | Dates | Scorecard | Ball-by-ball |
|---|---|---|---|---|---|---|---|
| state_spl | Sher-e-Punjab T20 League | 2026 | 13073 | 27 | 08-30..09-13 | yes (sample 2/2) | full (sample 2/2) |
| state_upt20 | Uttar Pradesh Premier League (UP T20) | 2025 | 10735 | 34 | 2025-08-17..09-06 | yes (2/2) | full (2/2) |
| state_upt20 | UP T20 League | 2026 | not on Cricbuzz | - | - | - | Crex fallback (see below) |
| state_tnpl | Tamil Nadu Premier League | 2023 / 24 / 25 / 26 | 6158 / 7862 / 9866 / 12620 | 32 each | Jun-Jul 23, Jul-Aug 24, Jun-Jul 25, Aug 26 | yes | see parsed table |
| state_dpl | Delhi Premier League | 2025 / 26 | 10581 / 12851 | 44 each | Aug | yes | see parsed table |
| state_maharaja | Maharaja Trophy KSCA T20 | 2023 / 24 / 25 / 26 | 6941 / 8652 / 10515 / 12541 | 33 / 33 / 34 / 34 | Aug 23-25, Jun-Jul 26 | yes | see parsed table |
| state_mumbai | T20 Mumbai League | 2025 / 26 | 9875 / 12299 | 23 each | Jun | yes | see parsed table |
| state_bengal | Bengal Pro T20 | any | not on Cricbuzz (no series in 2023-2026 archives) | - | - | - | Crex fallback |
| state_saurashtra | Saurashtra Premier League | 2023 | 7058 | 11 | Aug 23 | yes | see parsed table |
| state_rpl | Rajasthan Premier League | 2023 | 7088 | 19 | Aug-Sep 23 | yes | see parsed table |
| state_apl | Andhra Premier League | 2025 | 10592 | 25 | Aug 25 | yes | see parsed table |
| state_kcl | Kerala Cricket League | 2025 | 10620 | 33 | Aug-Sep 25 | yes | see parsed table |
| state_mppl | Madhya Pradesh Premier League | 2025 / 26 | 10014 / 12530 | 24 / 48 | Jun | yes | see parsed table |
| state_mpl | Maharashtra Premier League | 2025 | 9944 | 34 | Jun 25 | yes | see parsed table |
| state_cgpl | Chhattisgarh Cricket Premier League | 2025 | 10069 | 18 | Jun 25 | yes | see parsed table |
| state_ppl | Pondicherry Premier League | 2025 | 10350 | 34 | Jul 25 | yes | see parsed table |

Not found on Cricbuzz in 2023-2026: Bengal Pro T20, UP T20 League 2023/24/26, Delhi Premier League 2023/24, T20 Mumbai 2023/24, Saurashtra 2024+, Odisha. (Leagues that did not run in a year are not a gap.)
Layout note: raw files go to `data/external/cricbuzz/<comp>/<series_id>/<match_id>/` (the sync's layout, e.g. `state_tnpl/12620/...`) not `.../state/<key>/...`, so the scheduled sync and verify find them. All 699 listed matches are dated before 2026-10-15.

MILESTONE: Scrape complete 2026-11-15, no block/403/429. 703 matches (4 sample + 699 backfill), 23 series, 14 league keys, ~189 MB raw (data/external/cricbuzz/state_*, gitignored; 9 MB of that is the state_recon series pages). ~2100 requests, 3 s apart, sync lock held (kept fresh) the whole run. No match dated >= 2026-10-15.
MILESTONE: Parsed (parquet per series). 1337 innings: batting runs + extras = total in 1337/1337; wickets > 10 in 0. Ball-by-ball is complete (ball runs = scorecard total in both innings) for 648/703 matches (92%); the other 55 are partial and get no delivery rows. Results: 654 win, 3 tie, 25 abandoned, 19 no result, 2 unknown.

| League | Series (matches / complete ball-by-ball) | Batters | Bowlers (per series) |
|---|---|---|---|
| spl 2026 | 27 / 25 | 106 | 66 |
| upt20 2025 | 34 / 32 | 117 | 68 |
| tnpl 2023, 24, 25, 26 | 32/31, 32/31, 32/31, 32/30 | 140, 130, 129, 129 | 82, 77, 76, 75 |
| dpl 2025, 26 | 44/39, 44/41 | 145, 159 | 86, 90 |
| maharaja 2023, 24, 25, 26 | 33/32, 33/31, 34/33, 34/30 | 111, 108, 107, 110 | 67, 65, 63, 64 |
| mumbai 2025, 26 | 23/22, 23/20 | 131, 126 | 89, 78 |
| saurashtra 2023 | 11/11 | 74 | 46 |
| rpl 2023 | 19/18 | 102 | 61 |
| apl 2025 | 25/23 | 111 | 67 |
| kcl 2025 | 33/31 | 117 | 77 |
| mppl 2025, 26 | 24/19, 48/45 | 94, 160 | 62, 104 |
| mpl (Maharashtra) 2025 | 34/24 | 95 | 56 |
| cgpl 2025 | 18/16 | 98 | 61 |
| ppl 2025 | 34/33 | 107 | 70 |

MILESTONE: Player link (column `cricsheet_name`, `link`='name_only'): derived name ('Ishan Kishan' -> 'I Kishan') or full name must equal exactly one Cricsheet name in the IPL + SMAT player pool; there is no team to match, so every link is name-only (could be a namesake) and nothing is guessed. 329 of 1872 distinct players link (17.6%); per league 11-41 (dpl 41 of 201, upt20 36 of 112, mppl 33 of 171, tnpl 30 of 220).
MILESTONE: verify of all saved matches (read-only DB): state matches 703 -> `no_cricsheet_source`; the 19 waiting / 8 equal / 3 withheld are the older SMAT/T20I rows.
Surprise: Crex (approved fallback) is an Angular app: series page lists UP T20 League 2026 matches (Final lck-vs-mer = 133T), but scoreboard URLs redirect (301) and the data comes from a private JS API. Not built (stop rule). UP T20 League 2026 and Bengal Pro T20 stay missing; a Crex scraper means reverse-engineering that API (M/L).
Surprise 2: only 3 of the 2026 leagues Samar named (spl, dpl, tnpl) plus maharaja, mumbai, mppl 2026 exist on Cricbuzz; UP T20 2026 and Bengal are not there.
