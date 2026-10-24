# cricket-analysis - worker scores

Score out of 10: correct 4, complete 2, honest 2, constraints 1, efficient 1. Scored by the lead after checking the work.

| Date | Worker (Sonnet 5.5) | Task | Score | Notes |
|---|---|---|---|---|
| 2026-10-24 | auditor | Code audit → `docs/AUDIT.md` | 9 | 3 claims spot-checked, all true. Found the batting-team bug. -1: missed that CSV2 has fielder columns |
| 2026-10-24 | video-link | Edit Pipeline audit → `docs/AUDIT_video.md` | 9 | Spot-check true (hand-typed 11,167). Clear interface proposal |
| 2026-10-24 | researcher | Data + NLQ → `docs/RESEARCH_data_nlq.md` | 10 | Found the fielder_1 columns (lead verified), corrected our CLAUDE.md, labelled every claim |
| 2026-10-24 | builder | Phase 1 loader + DB + verification | 10 | Lead re-ran key checks, all true. Found 2 extra old bugs (ball 4.10, outcome). Respected the one-DB-writer and no-tests rules |
| 2026-10-24 | test-writer | `tests/test_ingest.py` + fixture | 9 | 10 tests, self-checking fixture numbers. Correctly flagged the stale test_db.py instead of editing it |
| 2026-10-24 | researcher-2 | Ball-tracking sources → `docs/RESEARCH_ball_tracking.md` | 9 | Lead verified the HawkeyeStats repo. Corrected its own earlier unverified claim. -1: wagon/field-data wording slightly overstated |
| 2026-10-24 | core-builder (2A) | Package, fragments, filters, registry, api, CLI | 9 | Lead re-ran tests and CLI; Buttler 2022 correct. Flagged super overs and non-striker run outs instead of guessing. -1: setuptools gap found late |
| 2026-10-24 | porter (2B) | 6 modules + 2 core fixes | 9 | Golden numbers match known records. Found missing super-over winners. -1: overwrote 2C's log lines once (owned up) |
| 2026-10-24 | porter (2C) | 6 advanced modules | 10 | Every old-vs-new difference explained; found 3 old bugs beyond the audit; stayed in its files |
