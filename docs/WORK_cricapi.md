# CricAPI (cricketdata.org) pilot, 2026-11-12

Client: `src/cricket_analytics/ingest/cricapi.py` (key from `CRICAPI_KEY` env or gitignored `.env`; cache + call log in gitignored `data/external/cricapi/`).

## Calls used today by this pilot: 8 (limit set 20)
| # | endpoint | purpose | hits charged |
|---|---|---|---|
| 1 | series?search=IPL | find IPL ids | 1 |
| 2 | series_info (IPL 2025) | match list | 1 |
| 3 | match_bbb (CSK v KKR 2025-04-11) | ball-by-ball sample | 1 |
| 4 | match_scorecard (same) | scorecard | **10** |
| 5 | match_info (same) | flags | 1 |
| 6 | series_info (IPL 2023) | coverage | 1 |
| 7 | match_bbb (IPL 2023 match 61) | confirm bbb shape | 1 |
| 8 | series?search=Indian Premier League 2026 | find 2026 | 1 |
Daily counter reported 9/100 before our first call (earlier use by Samar), 25/100 after the last. Total charged by us: 17 hits for 8 calls.

## Findings
1. **Cost**: one HTTP request = 1 hit, except `match_scorecard` = 10 hits (measured: counter 11 -> 21). series_info returns the whole match list in one call (75 matches, no paging). series list pages (25 rows) assumed 1 hit per page (not tested).
2. **Ball-by-ball is NOT real ball-by-ball.** `match_bbb` on the free plan returns only unusual balls: 10 entries for CSK v KKR 2025 (~226 balls), 12 for 2023 match 61. Only wides, no-balls, leg-byes. Fields per entry: n, inning, over, ball, batsman{id,name}, bowler{id,name}, runs, penalty, extras. No wicket, no line/length/speed/shot, no commentary. Whether a paid plan returns full balls is UNVERIFIED (docs page errored; site says paid "Series, Matches, Squads, Ball by Ball"; free page also claims "Ball-by-Ball"). match_scorecard gives per-innings aggregates only.
3. **Coverage**: series found for IPL 2022, 2023, 2024, 2025, 2026 (74 matches listed), plus 2027 empty. IPL 2023: 74/75 matches `bbbEnabled`. Free tier shows no depth limit in listing; we did not probe pre-2022.
4. **Cost for IPL 2023-26 (~290 matches)** at 1 hit per bbb: ~290 + 4 series_info = ~295 hits = 3 days on free (100/day). Scorecards at 10 hits would be ~2,900 hits = 29 days free, ~1.5 days on the 2,000/day... (paid is stated as 2,000 calls, period unverified). But the data returned is sparse, so this is not worth buying.
5. **Versus Cricbuzz commentary pilot**: Cricbuzz text gives per-ball length/line/shot wording, which CricAPI does not give. Cricsheet already gives runs/extras/wickets. CricAPI adds nothing we lack unless a paid plan returns richer bbb (ask CricAPI support / test with 1 paid call before paying).
