# WORK_smat (worker log)
MILESTONE: Part A done. tests/test_s26_goals.py frozen (2 test-freeze commits); S26_FROM, s26_mask, fresh3_scoring_mask added to ml/evaluate.py; 35 related tests pass.
MILESTONE: Recon. SMAT 2025-26 = two Cricbuzz series: Elite id 10493 (125 matches: 112 group A-E, 12 Super League, 1 Final, 2025-11-26..2025-12-18) and Plate id 10487 (16: 15 group + Final, 2025-11-26..2025-12-06). Total 141 matches, none dated >= 2026-10-15 (the "2026" series 12420/12431 are S26, not touched).
 Scorecard page /live-cricket-scorecard/<id>/x embeds full JSON (batters runs/balls/4s/6s/outDesc, bowlers, extras split, fall of wickets, partnerships, toss, result, venue, POTM). Commentary /api/mcenter/<id>/full-commentary/<inn>: full ball-by-ball only for some matches (final: 126 deliveries incl. extras, runs sum = 262 = scorecard); group games (127830, 127626) only 3-4 over-6/10/15 summary lines. No non-striker per ball.
141 matches listed
MILESTONE: 20/141 matches saved, 57 requests this run
MILESTONE: 40/141 matches saved, 117 requests this run
MILESTONE: 60/141 matches saved, 177 requests this run
MILESTONE: 80/141 matches saved, 237 requests this run
MILESTONE: 100/141 matches saved, 297 requests this run
MILESTONE: 120/141 matches saved, 357 requests this run
MILESTONE: 140/141 matches saved, 417 requests this run
MILESTONE: fetch complete, 141 matches
MILESTONE: Parse done. 141/141 matches scraped and parsed, 0 failed; 20 MB raw in data/external/cricbuzz/smat2025 (gitignored). Parquet: matches 141, innings 282, batting 3103, bowling 1688, deliveries 8657 (36 matches with complete ball-by-ball). 282/282 innings: bat runs + extras = total. Names matched to Cricsheet exactly: batting 1204/3103 rows (243 of 639 players), bowling 693/1688 (156 of 377).
