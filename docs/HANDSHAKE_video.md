# Handshake: cricket-analysis ⇄ Edit Pipeline (Reels)

How the Reels pipeline (`D:\Claude projects\Edit Pipeline`) gets stats and charts from this app.
Version 1, 2026-10-24. Status marks: ✅ works today · 🔜 planned (Phase 5).

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
| `cricket modules` | The 14 analysis modules and their parameters | ✅ |
| `cricket schema --json` | A JSON Schema per module (parameter names, types, choices) | ✅ |
| `cricket run <module> --player "V Kohli" --competition ipl [--last_n_years 5] [--venue A --venue B] --json --out <file>` | One stats table plus provenance as JSON | ✅ |
| `cricket info` | Matches and latest date per competition | ✅ |
| `cricket facts --player X --out reels/<slug>/data/facts.json` | One file with a player's headline facts for a reel (career card, best season, phase splits, vs pace/spin) | 🔜 |
| `cricket chart <module> ... --aspect 9:16 --png <file>` | A reel-ready PNG from the command line | 🔜 (works today from Python and from the dashboard's Video tab) |

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

## 4. Charts for video
- `cricket_analytics.viz.video.video_figure(module_id, result, aspect="9:16"|"1:1", focus=None)` returns a Plotly figure: 1080×1920 or 1080×1080, transparent background, the Edit Pipeline scoreboard palette, big numbers, one message per chart, and a source footnote. ✅
- PNG: `fig.write_image(path)` (kaleido 1.5 uses the installed Edge). ✅ Checked on Kohli's IPL card.
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

## 5. Suggested flow inside Edit Pipeline 🔜
1. Script names a player → `cricket resolve` → pick the Cricsheet name.
2. `cricket run ... --json --out reels/<slug>/data/<module>.json` for each stat the script needs (later: one `cricket facts` call).
3. `scenes.json` uses tokens like `{batting.total_runs}` instead of typed numbers; `build.py` fills them from the JSON and fails if a token is missing (Edit Pipeline side, its own session).
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
