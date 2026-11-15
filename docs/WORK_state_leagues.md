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
