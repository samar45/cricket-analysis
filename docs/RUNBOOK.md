# Runbook: run the cricket app by hand (no Claude needed)

For a fresh Windows 11 laptop. Mac/Linux differences are in the last section. Commands are typed in PowerShell,
from inside the project folder. Anything marked **(untested)** was not run on a fresh machine; the rest exists in
`cricket --help` or was run on the dev laptop.

## 1. What you need first

| Thing | Why | Check |
|---|---|---|
| Python 3.12 | The code needs it. Anaconda's Python 3.9 is too old. | `py -3.12 --version` |
| Git | To download the project | `git --version` |
| Microsoft Edge (comes with Windows) | Only for saving chart PNGs | nothing to do |
| Ollama (optional) | Only for the "Ask" page. Runs a small AI model on your PC. | `ollama --version` |

## 2. Get the project and install it (once)

```
git clone https://github.com/samar45/cricket-analysis.git
cd cricket-analysis
git checkout overhaul
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pip install -e .
```

(The `.venv` folder is a private copy of Python for this project, so nothing else on the laptop is touched.
The `git checkout overhaul` line is needed until the overhaul branch is merged into main.)

## 3. First full build of the database (once, ~10 minutes)

```
.venv\Scripts\cricket ingest --db data\cricket_analytics.duckdb
```

Downloads about 42 MB of Cricsheet zips into `data\raw\`, then builds `data\cricket_analytics.duckdb` (about 250 MB).
Check it worked:

```
.venv\Scripts\cricket info
```

You should see about 10,400 matches and a latest date within the last few weeks.

## 4. Start the dashboard

```
.venv\Scripts\streamlit run dashboard/app.py
```

Open the address it prints (usually http://localhost:8501). Stop it with Ctrl+C in that window.
Pages: Overview, Explore, Ask, Data health.

## 5. Daily (or weekly) update

The update downloads only recently added matches (last 30 days), checks them, and swaps the new database in.
The old one is kept as a backup. **The dashboard must be stopped first**, because Windows will not let the database
file be replaced while the dashboard has it open.

1. Stop the dashboard (Ctrl+C in its window).
2. Optional preview, changes nothing: `.venv\Scripts\cricket update --dry-run`
3. Real update: `.venv\Scripts\cricket update`
4. Read the summary it prints. You want `ok=True swapped=True`.
5. Start the dashboard again and open **Data health**.

Other options: `--days 7` (smaller window), `--replace-changed` (also reload old matches whose numbers Cricsheet
corrected; only use after reading the "changed" list in the summary), `--no-download` (reuse today's files).

## 6. Reading the Data health page

- **Top cards**: result of the last run (green tick = fine, amber warning = fine but look, red cross = failed),
  when the database file was last changed, and how many runs are recorded.
- **Runs table**: newest first. Columns show new matches added, how many checks passed / failed / warned,
  total seconds, and whether the new database was swapped in.
- **Open a run** to see: steps with timings; the checks (red = failed, amber = warning) with expected versus
  actual; freshness (matches and latest date per competition, before and after); fingerprint (matches, balls, runs,
  wickets before and after, changed numbers highlighted); golden numbers (famous stats that must never change);
  new matches; skipped events; the backup file name. "Download run JSON" saves the whole record.
- **Buttons**: "Run health check" (read-only checks) and "Dry-run update" (preview). The real update is hidden
  behind a tick box on purpose; use the terminal route in section 5 instead.
- Runs are stored as `data\runs\<run_id>.json`. Until the first real run, the page shows clearly labelled SAMPLE runs.

## 7. What each check means, and what to do when it fails

| Check | Means | If it fails |
|---|---|---|
| `all_loaded` | Every new match found was actually loaded | Re-run `cricket update`. If it repeats, send the run JSON to whoever maintains the code. |
| `no_duplicate_keys` | No match or ball appears twice | Do not use the new DB. Nothing was swapped; re-run. |
| `every_match_has_deliveries` | Every new match has ball-by-ball rows | Usually a bad download. Re-run (it re-downloads). |
| `innings_runs_match_files` | Innings totals equal the downloaded files' totals, and are between 0 and 400 | Do not use. Re-run; if repeated, report. |
| `old_data_unchanged` | Matches already in the DB still have the same numbers | Something rewrote history. Nothing is swapped. Look at "Matches whose numbers changed"; if Cricsheet really corrected them, re-run with `--replace-changed`. |
| Golden numbers | Famous stats (for example Kohli's IPL runs to 2025 = 8,661) | A mismatch means the data is wrong or a filter changed. Restore the backup (section 8) and report. |
| Freshness warning | Latest match is older than expected | Probably just no matches recently. Check the skipped events list: a league may have been renamed. |

A failed update never replaces your database: the swap step shows "skip". A warning is not a failure.
Only the checks that exist in your version appear; the Data health page shows the real list.

## 8. Restore a backup

Each real update leaves `data\cricket_analytics_prev_<date>.duckdb` (its name is in the run's "Backup" line and in the
update summary). To go back (dashboard stopped):

```
Move-Item data\cricket_analytics.duckdb data\cricket_analytics_bad.duckdb
Copy-Item data\cricket_analytics_prev_2026-10-24.duckdb data\cricket_analytics.duckdb
.venv\Scripts\cricket info
```

Replace the date with your backup's. `Copy-Item` keeps the backup safe. Delete `_bad` and old `_prev_` files when
you are happy (they are about 250 MB each). Last resort: run section 3 again.

## 9. Health check on demand

```
.venv\Scripts\cricket health
.venv\Scripts\cricket runs
```

`health` runs the integrity and golden-number checks on the current database without changing anything and records
a run. `runs` lists recorded runs. **(untested at time of writing: these two commands are added in parallel with this
runbook; run `cricket --help` to confirm they exist.)**

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| Syntax errors on `X \| None`, or `python --version` says 3.9 | Anaconda's Python was used. Always call `.venv\Scripts\python`, `.venv\Scripts\cricket`, `.venv\Scripts\streamlit`, or run `.venv\Scripts\Activate.ps1` first. |
| "database is locked" or the swap fails | The dashboard (or another window) has the DB open. Stop it, then run the update. Nothing was changed. |
| `cricket` not found | Use the full `.venv\Scripts\cricket`, or re-run `.venv\Scripts\pip install -e .` |
| Chart PNG fails (`cricket chart ...`) | It needs `kaleido` (installed with requirements) and Microsoft Edge or Chrome installed. |
| Ask page: "Ollama is not running" | Start it with `ollama serve` in another window, then reload. First question is slow while the model loads. The model is `nemotron-3.5-bolt:e4b-q4_K_M`; if missing, `ollama pull nemotron-3.5-bolt:e4b-q4_K_M` **(untested; ~2.5 GB, a big download)**. |
| Port already in use | `.venv\Scripts\streamlit run dashboard/app.py --server.port 8510` |
| Download errors | Check internet, re-run. Cricsheet is free but occasionally slow. |

## 11. Where things live

| What | Where |
|---|---|
| Database | `data\cricket_analytics.duckdb` |
| Backups | `data\cricket_analytics_prev_<date>.duckdb` |
| Downloaded Cricsheet files | `data\raw\` |
| Run logs (shown on Data health) | `data\runs\*.json` |
| Sample logs used when there are none | `tests\fixtures\runs\` |
| Project history and decisions | `docs\JOURNEY.md`, `docs\STATUS.md` |

## 12. Mac / Linux differences

- Python: `python3.12 -m venv .venv`
- Use `/` and `bin`: `.venv/bin/pip`, `.venv/bin/cricket`, `.venv/bin/streamlit run dashboard/app.py`.
- Restore: `mv` and `cp` instead of `Move-Item` and `Copy-Item`.
- The swap works even with the dashboard open on Mac/Linux, but still stop it (the dashboard would keep showing the old file until restarted).
- PNG charts use Chrome or Chromium instead of Edge. All of this is **untested** on Mac/Linux.

## 13. Tests (optional)

```
.venv\Scripts\python -m pytest -q
```
