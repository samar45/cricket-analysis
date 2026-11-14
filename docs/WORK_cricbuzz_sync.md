# WORK_cricbuzz_sync (worker log)

## What it is
`cricket cricbuzz sync [--dry-run] [--no-verify] [--max-matches N]` (code: `src/cricket_analytics/ingest/cricbuzz_sync.py`, tests: `tests/test_cricbuzz_sync_goals.py`, frozen).
Discover (Cricbuzz `/cricket-schedule/series/all`) -> scrape finished men's T20 matches not yet saved -> verify against Cricsheet (DB read-only).
- Series kept: name table `PATTERNS` (ipl, bbl, psl, cpl, sa20, blast, hundred, ilt20, mlc, bpl, lpl, smat) plus INTERNATIONAL series whose match list holds men's "T20I" matches (key `t20i`). Women's section, women/U19/U23 names, Tests/ODIs/first-class are dropped. T20-looking series not in the table are logged ("unmapped T20-looking series") and skipped.
- Raw: `data/external/cricbuzz/<comp>/<series_id>/<match_id>/` (scorecard.html.gz, comm1/2.json, meta.json); parquet per series next to it. All gitignored.
- Data only: matches dated 2026-10-15 or later are saved, nothing here scores a model. Does not touch `data/external/live/`.
- Lock: `data/external/cricbuzz/.sync.lock` (stale after 3 h). Politeness: one request at a time, >= 3 s apart, stop at the first block (exit 2, partial work kept).
- Output: `docs/VERIFY_cricbuzz_cricsheet.md` (overwritten), `data/external/cricbuzz/verify.parquet`, `data/external/cricbuzz/sync.log`.
- Team names: `src/cricket_analytics/reference/cricbuzz_team_map.csv` (competition, cricbuzz_name, cricsheet_name); a name not in it must equal a Cricsheet name exactly, else the match is `unmapped_team` and listed in the doc.

## Scheduled task
Registered 2026-11-15: `CricketCricbuzzSync`, every 3 days at 21:00 local, runs `tools/cricbuzz_sync.ps1` (which runs `.venv\Scripts\cricket.exe cricbuzz sync` in the repo and appends output to `data/external/cricbuzz/sync_run.log`). StartWhenAvailable, runs only when SAMAR is logged on (no stored password), stops after 2 hours.
- Show: `Get-ScheduledTask CricketCricbuzzSync | Get-ScheduledTaskInfo`
- Remove: `Unregister-ScheduledTask -TaskName CricketCricbuzzSync -Confirm:$false`
