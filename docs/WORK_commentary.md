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
