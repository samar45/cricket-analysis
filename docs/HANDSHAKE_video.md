# Handshake: cricket-analysis ⇄ Edit Pipeline (Reels)

How the Reels pipeline (`D:\Claude projects\Edit Pipeline`) gets stats and charts from this app.
Version 2, 2026-10-25. Status marks: ✅ works today · 🔜 planned (Phase 5).

## 1. Rules of the handshake
- **One direction.** Edit Pipeline reads from this app; this app never reads the reels. No shared imports: the two projects have separate venvs, so they talk through **files and the CLI**.
- **No hand-typed numbers.** Every stat in a reel comes from a JSON/PNG this app wrote, and carries its provenance (source, data-through date, DB date, caveats).
- **Read-only.** Nothing the pipeline runs here writes to the database.
- **Data scope.** T20 only (IPL, men's and women's T20I, BBL, PSL, CPL, SA20, The Hundred, Blast), from Cricsheet (ODC-BY, credit "Cricsheet"). No first-class, ODI or Test numbers yet. Super overs excluded unless asked.

## 2. How to call it
Run from any folder with this app's venv:
`"D:\Claude projects\cricket-analysis\.venv\Scripts\cricket.exe" <command>`

| Command | What it gives | Status |
|---|---|---|
| `cricket resolve "<name>"` | Cricsheet name candidates ("rohit sharma" → "RG Sharma"), with matches and last match date. Always resolve first: modules use exact names | ✅ |
| `cricket modules` | The 18 analysis modules and their parameters | ✅ |
| `cricket schema --json` | A JSON Schema per module (parameter names, types, choices) | ✅ |
| `cricket run <module> --player "V Kohli" --competition ipl [--last_n_years 5] [--venue A --venue B] --json --out <file>` | One stats table plus provenance as JSON | ✅ |
| `cricket info` | Matches and latest date per competition | ✅ |
| `cricket facts --player "V Kohli" [--competition ipl] [--last_n_years N] --out reels/<slug>/data/facts.json` | One file with a player's headline facts plus `{token}` strings (see 3b). Exit 1 + closest names if the name is not exact. No `--competition` = all men's T20 (said in `meta.competition_note`) | ✅ |
| `cricket chart <module> [module params] --aspect 9:16\|1:1 [--focus X] --png <file> [--html <file>]` | A reel-ready 1080-wide transparent PNG (and/or standalone HTML). Exit 1 with a message if the result has no rows | ✅ |
| `cricket update [--days 7\|30] [--dry-run] [--no-download] [--replace-changed] [--db PATH]` | Add recently-added Cricsheet matches to the DB (writes the DB: run by hand, not from a reel build) | ✅ wired to `ingest.update.run_update` |

## 3. JSON shape (`--json`)
```json
{
  "meta": {
    "module": "batting", "title": "Batting stats",
    "params": {"player": "V Kohli", "competition": "ipl", "last_n_years": 5},
    "data_through": "2026-05-31", "db_modified": "2026-10-24T18:39:56",
    "row_count": 1, "source": "Cricsheet (ODC-BY)",
    "caveats": ["Super-over innings excluded ...", "..."]
  },
  "data": [{"batter": "V Kohli", "innings": 76, "total_runs": 3053, "average": 48.46, "strike_rate": 146.01, "...": "..."}]
}
```
The pipeline should keep `meta` next to the numbers it uses and print `data_through` in the reel's source line.

## 3b. `facts.json` shape (`cricket facts`)
```json
{
  "meta": {"facts_version": 1, "player": "V Kohli", "role": "batting", "params": {"player": "V Kohli", "competition": "ipl"},
           "generated": "2026-10-25T12:00:00", "data_through": "2026-05-31", "db_modified": "...", "source": "Cricsheet (ODC-BY)",
           "competition_note": null, "caveats": ["..."],
           "calls": [{"module": "batting", "params": {"...": "..."}}], "skipped": [{"section": "x", "reason": "no data"}]},
  "facts": {
    "career": {"source": [{"module": "batting", "params": {}}], "innings": 275, "runs": 9336, "average": 40.42, "strike_rate": 134.8,
               "fifties": 68, "hundreds": 9, "highest": 113, "balls": 6926, "fours": 845, "sixes": 317, "not_outs": 44},
    "best_season": {"source": [], "season": "2016", "runs": 973, "innings": 16, "average": 81.08, "strike_rate": 152.03, "highest": 113},
    "by_phase": {"source": [], "powerplay|middle|death": {"innings": 0, "runs": 0, "balls": 0, "average": 0, "strike_rate": 0, "boundary_pct": 0}},
    "vs_pace_spin": {"source": [], "pace|spin": {"runs": 0, "balls": 0, "strike_rate": 0, "average": 0, "dismissals": 0, "dot_pct": 0, "pct_of_balls": 0}, "unknown_pct": 1.7},
    "home_away": {"source": [], "home|away|neutral": {"matches": 0, "runs": 0, "average": 0, "strike_rate": 0}},
    "chase_vs_set": {"source": [], "setting|chasing": {"innings": 0, "runs": 0, "average": 0, "strike_rate": 0, "big_games": 0, "win_pct": 0}},
    "pressure": {"source": [], "balls": 967, "runs": 1374, "outs": 49, "strike_rate": 142.09, "average": 28.04, "calm_strike_rate": 133.63, "sr_change": 8.46},
    "dismissals": {"source": [], "total": 231, "top_kind": "caught (fielder)", "top_pct": 57.1, "kinds": {"caught_fielder": {"label": "caught (fielder)", "outs": 132, "pct": 57.1}}},
    "profile": {"source": [], "role": "batter", "bat_hand": "right", "bowl_kind": "pace", "bowl_type": "right-arm medium", "usually_bats_at": "usually No.1-2 (52%)"}
  },
  "tokens": {"career.runs": "9,336", "career.average": "40.42", "by_phase.death.strike_rate": "188.4"},
  "tokens_raw": {"career.runs": 9336, "career.average": 40.42, "by_phase.death.strike_rate": 188.38}
}
```
- Only sections with data exist; the ones left out are listed in `meta.skipped`. Every section has `source` = the module calls (`module` + `params`) it came from.
- A bowler (more balls bowled than faced) gets bowling keys instead: `career.wickets`, `bowl_innings`, `economy`, `bowl_average`, `bowl_strike_rate`, `best_figures`, `five_plus`; `by_phase.<phase>.{wickets,economy,dot_pct}`; no `vs_pace_spin` or `dismissals`. A side with 300+ balls (an all-rounder) is in `career` with both key sets.
- Tokens: `tokens` has display strings (`9,336`, `40.42`, `134.8`: whole numbers with commas, 2 decimals, 1 decimal from 100 up), `tokens_raw` the same keys with numbers. Token key = dotted path into `facts` without `source`. Text values (`dismissals.top_kind`, `profile.bat_hand`) are tokens too. A missing key means no data: fail the build, don't guess.
- `profile.*` fields come from the reviewed list; "unknown" values are dropped. `vs_pace_spin.unknown_pct` is the share of balls with no bowling type: check it before quoting a split (IPL ~2%, other competitions much more).

## 4. Charts for video
- `cricket_analytics.viz.video.video_figure(module_id, result, aspect="9:16"|"1:1", focus=None)` returns a Plotly figure: 1080×1920 or 1080×1080, transparent background, the Edit Pipeline scoreboard palette, big numbers, one message per chart, and a source footnote. ✅
- PNG: `cricket chart ...` (CLI, above) or `fig.write_image(path)` in Python (kaleido 1.5 drives the installed Chrome/Edge). ✅ Background is transparent: it looks white in an image viewer; the text is cream/amber for dark reels.
- Dashboard: Explore → any module → **Video** tab → preview, then PNG or HTML download. ✅
- Font: Impact/Arial Narrow today. Switch `FONT` in `viz/video/__init__.py` to Big Shoulders Stencil if it's installed where charts are rendered.

| Module | Video chart | Good reel use |
|---|---|---|
| batting | big-number card; runs-per-season bars (best season highlighted) | career card, "his peak year" |
| bowling | wickets donut (how they fell); economy by phase | "how he gets you out" |
| compare | butterfly bars, "X leads 4 of 5" | player vs player |
| matchup | duel card (balls, runs, outs, SR) | batter vs bowler |
| form | last 15 innings line + average | "in form / out of form" |
| pace_vs_spin | two bars (vs pace / vs spin); per bowling type with `detail` | "his weakness" |
| death_overs | overall vs death bars | finisher / death bowler reels |
| partnerships | top stands bars | famous pairs |
| season_awards | podium | season recap |
| teams / venues | win-loss donut / bat-first vs chase donut | team or ground stories |
| impact / true_performance | leaderboard / raw vs adjusted bars | "underrated" picks |
| player_profile | fact card + "usually bats at No.5–6 (52%)" mixes | player intro |

## 5. Suggested flow inside Edit Pipeline
1. Script names a player → `cricket resolve` → pick the Cricsheet name.
2. `cricket facts --player ... --out reels/<slug>/data/facts.json` for the headline numbers; `cricket run ... --json --out ...` for anything else.
3. `scenes.json` uses tokens like `{career.runs}` (keys of `facts.json` `tokens`) instead of typed numbers; `build.py` fills them from the JSON and fails if a token is missing (Edit Pipeline side, its own session).
4. Charts: export PNGs into `reels/<slug>/assets/` and place them as image layers.
5. The reel's source line prints `meta.source` + `meta.data_through`.

## 6. Known limits (say them in a reel when relevant)
- Only T20. Players famous for Tests or first-class cricket need another source.
- Bowling type and batting hand come from a reviewed list (940 players; IPL 94.9% of balls covered); others show "Unknown".
- No line/length/shot/dropped-catch data (no free legal source). Hawk-Eye trial data is local-only and never goes in a reel.
- Numbers can differ from ESPNcricinfo by a few runs in rare matches (source differences).

## 7. Versioning
- This file is the contract. A breaking change to a command, a JSON key or a module name bumps the version here, with a line below.
- v1 2026-10-24: first version.
- v2 2026-10-25: `cricket facts` and `cricket chart` implemented (sections 2, 3b); `cricket update` added; module count 18. No breaking change to v1 commands.
