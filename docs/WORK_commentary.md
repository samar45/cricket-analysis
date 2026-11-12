# Commentary pilot

MILESTONE: 2026-11-12 robots.txt checked (2 requests). Pilot stopped before any commentary fetch.
- cricbuzz.com/robots.txt: `User-agent: *` -> `Disallow: /` (only /ads.txt allowed). Googlebot-only rules otherwise. Any path we would use (/api/, /match/, *.json) is disallowed for generic agents.
- espncricinfo.com/robots.txt: HTTP 403 "Access Denied" (Akamai bot block) on the very first request. Stopped per conduct rule.
- No match data fetched, no parser written. Needs Samar's decision (see report).

MILESTONE: 2026-11-12 Samar approved Cricbuzz despite robots.txt. Pilot match 149684 (CSK v PBKS, Cricsheet 1527680) done, 5 requests total, no block.
- Served by: JSON `https://www.cricbuzz.com/api/mcenter/{matchId}/full-commentary/{inningsId}` (the same call the full-commentary page makes in the browser). One call returns the whole innings (no paging). Items: commText, ballNbr, overNumber (19.6 = 6th ball of 20th over, Cricsheet over_num 19), event (FOUR/WICKET/DROPPED/UDRS...), totalRuns, legalRuns. "B0$" placeholders in commText are filled from commentaryFormats.
- Requests used: live-cricket-scores page, full-commentary page, one JS chunk (to learn the route), 2 JSON calls. Next matches need 2 each.
- Parsed 251 balls (131 + 120). Join to Cricsheet by innings + delivery order: 251/251 paired, over, total runs, bowler and batter surnames agree on all 251. Cricsheet ball_num counts wides, Cricbuzz does not, so match on order, not ball_num.
- Field coverage (all balls): speed 13%, length 66%, line 61%, delivery type 15%, contact 25%, shot 65%, drop/misfield 6%. Regex guesses, not verified beyond the 6 test lines; speed only appears when the commentator quotes it.
- Code: src/cricket_analytics/ingest/commentary.py (CLI: `python -m cricket_analytics.ingest.commentary --match 149684 --cricsheet 1527680`), tests/test_commentary.py. Raw JSON cached in data/external/commentary/cricbuzz/ (gitignored).

MILESTONE: 2026-11-12 step 2 done (Samar overrode robots.txt). 21 requests (1 series page + 20 innings JSON for 10 matches), no block, no 403/429.
- Ids: the series page `/cricket-series/9241/indian-premier-league-2026/matches` embeds JSON for all 74 matches (matchId, startDate, teams). Mapped to Cricsheet by IST date + team pair: 74/74 unique. Saved to `src/cricket_analytics/reference/cricbuzz_ids.csv` (ids, dates, teams only). Series id 9241 came from a link in an already cached page.
- Sample (10 matches, 2,402 balls, spread over 10 venues, saved without raw text in gitignored `data/external/commentary/parsed_ipl2026_sample.csv`): 149618 149629 149640 149662 149673 149699 149710 151902 152097 152108.
- Join (by innings + delivery order): 2,402/2,402 balls paired, over and total runs agree on all. Batter/bowler surnames agree ~92%/~95%; the rest are spelling differences (Sooryavanshi/Suryavanshi, "CV Varun"/Chakaravarthy), not misalignment.
- Surprise: Cricbuzz sometimes serves a truncated text fragment for a real delivery (match 151902 ball 11.3: no "bowler to batter," prefix). It used to be dropped and shifted the join by one ball (runs matched only 199/245). Now kept as a ball with all parsed fields empty -> 246/246.
- Parser fixes: "wide long-on" no longer counts as a wide line; "wide of off" = outside off; "down leg"/"leg-lined" = leg; "straight" alone removed (matched "drive straight"); "at the stumps" = middle; "length and", "shortish", "fraction shorter"; "inside-edging/top-edging" etc.
- Coverage after fixes (2,402 balls): speed 13.6%, length 64.6%, line 53.1%, delivery type 13.3%, contact 20.7%, shot 61.8%, drop/misfield 2.0%. Line fell from 58.7% because false positives were removed. Missing = the commentator did not say it, not a parser bug.
- Hand check (30 random balls, seed 7, before fixes): length 0 wrong of 20 assigned (2 text cut off, unjudged); contact 7/7 right, 1 missed (inside-edging); line 15/20 = 75% (5 wrong: wide-fielder x2, wide-of-off, "drive straight", wide vs down-leg). All 5 plus 3 misses fixed and covered by tests; accuracy after fixes is only re-checked on those same lines (biased), so treat as ~90% at best, untested on a fresh sample.
- CLI: `python -m cricket_analytics.ingest.commentary --series ipl --season 2026 --limit N [--ids a,b] [--out csv]`. Cache-aware: cached matches cost 0 requests, so reruns resume. Full 2023-26 pull NOT run; 2023-25 ids still need their 3 series pages.
- Estimate for 2023-26: ~296 matches x 2 requests x ~5 s (3 s wait + latency; measured ~12 s/match... 20 requests took ~100 s) = about 50 min plus 3 id-page requests.
MILESTONE: 2026-11-12 full pull started in background (python -m cricket_analytics.ingest.commentary --all); log data/external/commentary/pull.log. Resumable: rerun skips cached. Ids for 2023-25 mapped (series 5945/7607/9237, 3 requests).

MILESTONE: 2026-11-12 steps 1-5 done. Full IPL 2023-26 pull finished, no 403/429/captcha. 565 requests total (3 series pages + 562 innings/series calls, incl. earlier cached ones counted once), no block.
- Fresh accuracy check (seed 90210, 30 balls from the 10 cached matches, hand-judged, before fixes): length 17/19 assigned right (89%; "short of a good length" mapped to short x2), line 13/13 (100%), contact 5/5 (100%), shot 19/21 (90%; "punches the air" and fielder "cut it off" wrongly read as shots). Misses (not wrong, just unlabelled): fullish/pitched up, "on leg", "connected", pats/prods/chopped/left alone/digs it out. All fixed with tests; re-check on that same sample is biased.
- Ids: IPL 2023/24/25 series pages are 5945 / 7607 / 9237 (`/cricket-series/<id>/indian-premier-league-<year>/matches`). reference/cricbuzz_ids.csv now 292 rows (74+71+73+74). Unmatched Cricbuzz: 2023-05-28 final (washed out, played 29th, which is mapped), 2024 x3 (13/16/19 May washouts, Cricsheet has none), 2025-05-17 RCB v KKR (washed out, no Cricsheet match). Unmatched Cricsheet: 2025 match 1473495 (PBKS v DC no result, 8 May; not under that date/pair in Cricbuzz) - skipped. 2026 match 1527691 had 1 ball unjoined.
- Output: data/external/commentary/parsed_ipl_2023_2026.csv (gitignored, 69,700 rows, no raw text). Load with `cricket_analytics.ingest.commentary.load_parsed()`; join on (match_id, innings, ball_seq) to deliveries. Rebuild with `--all` (cache makes it 0 requests).
- Bug found by the pull: some Cricbuzz items lack legalRuns/totalRuns (match 151891, over-break items); now default 0.
- Mismatches (over or total runs): isolated single balls in 7 matches, plus match 1527691 innings 2 from ball ~50 (56 balls shifted). Cricsheet super-over innings (3+) are not fetched.

MILESTONE: 2026-11-12 IPL 2020-22 ids mapped (series 3130/3472/4061 via /cricket-scorecard-archives/<year>, 3+1 requests): 60/60, 60/60, 74/74 to Cricsheet; 2021 unmatched Cricbuzz = 2 postponed matches (35718, 35723). Fields inventory in docs/CRICBUZZ_fields.md (0 requests). Background pull started (GAP 4 s, 60 s pause per 100 requests): python -m cricket_analytics.ingest.commentary --old; log data/external/commentary/pull_old.log

MILESTONE: 2026-11-12 pace changed per Samar: GAP 2 s, 30 s pause per 100 requests (restarted after 44 matches / 88 requests, no block). Added extras(): parsed_*_matches/_overs/_impact/_players CSVs and bat_id/bowl_id/bat_mins/bat_dots/team_score columns. Impact subs are free text only (regex name extraction gave garbage), so only mention rows kept.

MILESTONE: 2026-11-12 IPL 2020-22 pull done: 194 matches, 46,835 balls, parsed_ipl_2020_2022*.csv; no block. IPL 2015-19 ids mapped (series 2330/2430/2568/2676/2810): 59/60/59/60/60. One-match probe (10 requests): 2015 and 2016 return an empty commentary list (skipped); 2017-19 have full commentary. Pulling 2017-19 (--seasons 2017-2019), 2 s gap.

MILESTONE: 2026-11-12 IPL 2017-2026 commentary done (2015 and 2016: Cricbuzz returns an empty commentary list, probed 1 match each; skipped). Requests this run: 4 (2020-22 archive pages incl. 1 earlier) + 5 archive pages (2015-19) + 10 probe + 352 (2017-19) + ~340 (2020-22) ~ 710, plus 3 series ids, no 403/429/captcha/slow-down. Pace 4 s (first 88 requests of 2020-22) then 2 s.
| season | matches | balls | Cricsheet balls (inn 1-2) | innings with ball count AND runs equal | length/line/shot/contact/speed % |
|---|---|---|---|---|---|
| 2017 | 59/59 | 13,811 | 13,849 | 115/118 | 44/41/60/18/3 |
| 2018 | 60/60 | 14,285 | 14,286 | 117/120 | 51/48/60/18/4 |
| 2019 | 60/60 | 14,292 | 14,293 | 117/120 | 49/47/60/17/8 |
| 2020 | 60/60 | 14,510 | 14,510 | 119/120 | 53/46/62/17/11 |
| 2021 | 60/60 | 14,413 | 14,413 | 118/120 | 55/50/64/19/12 |
| 2022 | 74/74 | 17,912 | 17,912 | 147/148 | 59/55/67/20/10 |
| 2023 | 74/74 | 17,863 | 17,863 | 146/147 | 64/59/67/20/10 |
| 2024 | 71/71 | 17,103 | 17,103 | 142/142 | 69/66/67/20/11 |
| 2025 | 73/74 | 17,212 | 17,275 | 142/146 | 72/68/66/20/6 |
| 2026 | 74/74 | 17,522 | 17,523 | 143/147 | 68/63/66/21/13 |
- Problems: 2017 match 1082647 innings 2 has only 89 of 127 balls (truncated, joined order breaks after); most other "not ok" innings have the right ball count and runs off by 1-6 (extras/penalty runs or one mis-ordered ball); 2025 match 1473495 has no commentary (no-result match, unmapped).
- Older seasons have less detail (length/line 44-51% in 2017-19 vs 65-70% in 2024-25).
- Outputs (gitignored): parsed_ipl_2017_2019.csv, parsed_ipl_2020_2022.csv, parsed_ipl_2023_2026.csv, each with _matches/_overs/_impact/_players CSVs. load_parsed() reads all three ball files.
