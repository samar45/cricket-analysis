# Audit: how the analytics app can serve the reels pipeline (2026-10-24)

Read-only research. Project A = `D:\Claude projects\Edit Pipeline` (video). Project B = this repo (analytics). Nothing was run, rendered or queried; every claim below is from reading files. Guesses are marked "(guess)".

## 1. The video pipeline (15 lines)

1. Opus (lead) picks a player, reads Wikipedia/ESPNcricinfo by hand, writes `reels/<slug>/script.md` or `PLAN.md` (fact sheet with sources) and `vo-tts.txt` (one line per scene).
2. Voice: TTS (Kokoro `hm_omega`) or the user's phone recording -> `tools/vo.sh` (cleanup, -14 LUFS).
3. `tools/captions.py` (faster-whisper, CUDA) -> `words.json` / `captions.json` (word timings mapped onto the script text).
4. Sonnet workers fetch CC photos from Wikimedia Commons + cut-outs (`hyperframes remove-background`), `assets/CREDITS.md`.
5. A worker writes `reels/<slug>/scenes.json` (one scene per script line; blocks timed with `"@line:word"` tokens).
6. `python tools/build.py reels/<slug> [theme]` inlines `templates/engine.js` + a theme CSS into `index.html` (a Hyperframes HTML/GSAP composition), assigns motions/transitions/SFX, adds music and captions. Edit `scenes.json`, never `index.html`.
7. `npm run check`, `sh tools/peek.sh` (snapshot sheet), then `npx hyperframes render` -> `tools/finish.sh` (music fade, loudness) -> `renders/<slug>-<theme>.mp4`.
8. **Where data enters:** only step 1, typed by hand. Numbers go into `scenes.json` blocks as display strings (`"big": "11,167", "count": 11167`). There is no data file, no fetch, no stats tool. `PLAN.md` for the Tambe and Marsh reels records no sources.
9. Stat blocks the engine already has: `big` (+`count` odometer), `card`/`sub`, `row` of cards, `bars` (name/value pairs, e.g. Goel 637 vs 530), `grid` (list of names), `stamp`, `tag`, `label`, `quote`, `pcard`. Scene-level `palette` (bg, ink, a1, a2) re-colours any theme.
10. Six themes (scoreboard is the user's favourite and default), 1080x1920, 30 fps, safe zone: nothing key in the top 250 px or bottom 420 px.
11. Hard rules that limit data graphics: one big number per beat (two side by side read as "288"), images on screen over 50% of the time, a new visual every 2-3 s, no match footage. A full-screen chart is a poor fit; a stat belongs in a card, plate or bar inside a photo scene.
12. Roles: Opus plans and reviews; Sonnet 5.5 workers do all hands-on work. Pro plan, so cost matters.
13. The user has asked since 2026-10-11 for this app to become "the strongest differentiator" (PLAN.md, "Ideas from the user"). Status there: "Waiting".

Real example scene (`reels/albie-morkel/scenes.json`, line 2, compacted; the `"@2:206-0.2"` token means "0.2 s before the word 206 is spoken"):

```json
{ "line": 2, "photo": "chepauk.jpg", "mask": "panel",
  "credit": "Photo: BCCI/Sportzpics, CC BY-SA 3.0, Wikimedia Commons",
  "blocks": [
    { "tag": "12 April 2012", "at": "@2:12" },
    { "title": "Chepauk, Chennai", "size": "small", "at": "@2:Chepauk" },
    { "label": "Chennai Super Kings", "at": "@2:Chennai" },
    { "big": "206", "count": 206, "size": "big", "at": "@2:206-0.2" },
    { "label": "to chase vs RCB", "at": "@2:against" } ] }
```

Top level of the file: `{ "theme", "palette", "marquee", "music", "total", "scenes": [...] }`.

## 2. Every stat or graphic in the 10 finished reels, and where it came from

All 10 reels use the same few graphics: a counted big number, a pair of stat cards, one bar pair (Goel), a name grid, a stamp. There are no charts, scoreboards from real matches, season tables, timelines or head-to-heads with data. About 60 numeric blocks in total (rough count of big/card/bars blocks).

**Source for all of them: Wikipedia, typed by hand.** No block cites Cricsheet or any file. Where a fact sheet exists it names a Wikipedia page (Amol also Scroll.in/Wisden, Goel CricketArchive via Wikipedia).

| Reel (theme) | Data-driven items on screen | Source recorded in repo | Flags |
|---|---|---|---|
| amol-muzumdar (worldcup) | 11,167 FC runs; 30 centuries; 664 stand; 260 on debut; 171 matches, avg 48.13; "IND beat SA by 52 runs" | `script.md` fact table (Wikipedia, Wisden, Scroll) | OK. First-class numbers, not in a T20 DB |
| albie-morkel (poster) | 28 off one over; 206 chase; 2008/2013; 105 m; FC avg 44.26, 203 wkts; 1 Test | `PLAN.md` (Wikipedia, one page) | 28-off-Kohli over and the 206 chase are IPL: checkable in this app. The card says "batting avg" but the figure is first-class (script says so) |
| hashim-amla (scoreboard) | 311; No. 1; 27 ODI hundreds, avg 49.46; 8,000 runs in 176 inn; 55 hundreds | `PLAN.md` (Wikipedia) | "2nd fastest (in 2019)" is time-stamped by hand, will go stale. 311 is hedged "at the time" (record broken in 2025) |
| fawad-alam (scoreboard) | 168 on debut; missed 88 Tests; FC 14,788 runs, avg 55.38; "10y 258d"; 4,218 days; 5 hundreds in 22 inn | `PLAN.md` (Wikipedia) | OK. "10y 258d" typed as a string, separate from any date maths |
| tilak-varma (scoreboard) | 170, 140, 10 balls, "avg 45" | `PLAN.md`: T20I avg about 45, SR about 146.6, 107\* and 120\* (Nov 2024), 69 in Asia Cup final | **170 / 140 / 10 are the user's spoken claims, not stats.** The user's "SR 160" was caught and dropped by Opus by hand. T20I avg/SR/hundreds are exactly what this app can compute |
| rajinder-goel (test) | 750 wkts; bars 637 vs 530; avg 18.58; 59 five-fors; age 42; 39 wkts final season | `script.md` fact table (Wikipedia) | 637 is CricketArchive; Indian sources say 640 (noted in the sheet). Bars hold only 2 values, hand-typed |
| pat-cummins (collage) | 18 (debut age); 1,946 days; 4 (home summers missed); WTC 2023 | `PLAN.md`: one line "Source for every fact: Wikipedia" | 1,946 appears 3 times by hand. Not shown how it was derived |
| pravin-tambe (collage) | 41 (debut age); 12 wkts in 5 matches; hat-trick victims; 2000-02 | `PLAN.md` has **no source line** | **Unsourced in the repo.** Hat-trick (IPL 2014 v KKR) is checkable here; the Champions League numbers likely are not (guess: CLT20 is not one of the 8 configured competitions) |
| shaun-marsh (ipl) | 616 runs (2008 Orange Cap); 141 on Test debut; 6 Test and 7 ODI hundreds | **No PLAN.md, no script.md** in the folder, only `vo-tts.txt` | **Unsourced in the repo.** 616 and the Orange Cap are checkable in this app (IPL 2008) |
| yuvraj-singh (collage) | 362 runs, 15 wkts (2011 WC); 3 chemo cycles; "2007 six sixes" | `script.md` (Wikipedia) | 2011 WC is ODI: not in this DB. 90.50 average is in the script only |

Cross-cutting problems:
- **`big` and `count` are typed twice** (`"big": "11,167"` and `"count": 11167`); a typo in one would not be caught.
- **No retrieval date** on any Wikipedia number, so staleness (Amla ranking, Mulder's 367\* breaking the 311 record) depends on someone remembering.
- **Spoken claims can reach the screen** (Tilak). Only a human caught the wrong strike rate.
- **Coverage vs this app (my reading of scripts, not DB queries):** about 4 of 10 reels (Albie, Marsh, Tambe, Tilak) have facts that sit in IPL / T20I ball-by-ball. The other 6 rest on first-class, Test or ODI numbers that this DB cannot give. The DB holds only T20 data per `CLAUDE.md`.

## 3. What the video side wants from the analytics app, ranked

| # | Item | Why it ranks here | Fits existing module | Gap |
|---|---|---|---|---|
| 1 | **Fact check / career card as JSON** (runs, avg, SR, 50s/100s, HS, wkts, econ, by competition) | It replaces the typed numbers that are today's weakest link, and fits the card/big blocks as-is | B1, B2 | Needs player-name resolution (Cricsheet uses "V Kohli" style names), a competition label (see data audit), and a hard "T20 only" caveat |
| 2 | **Story-angle finder for underrated players** ("high true SR / impact, few matches, no big profile") | The channel's whole topic. Today Opus picks players from memory | A1, I3, A5, B5 | Needs a "how famous" proxy; no fame data exists (guess: use matches played / team caps) |
| 3 | **Notable innings / best figures / season records** (top 5 scores, best bowling, one-over runs, hat-tricks, Orange Cap year) | Hook lines ("28 off one over", "616 runs in 2008") are this kind of fact | B1, B2, B5, I1 | Per-over and hat-trick queries are not modules yet; per-ball data supports them |
| 4 | **Season-by-season runs/wkts** (for a bar race or a rising bar row) | Natural fit to the `bars` block (needs a multi-bar variant) and to career-arc stories | B5, I4 | Output shape only |
| 5 | **Phase strike rates** (PP / middle / death) | "Finisher" stories (Albie, Tilak) | I1 | Phase SQL is copy-pasted and assumes 20 overs (known bug) |
| 6 | **Head-to-head** (batter v bowler, player v player) | Versus scenes (Goel v Venkataraghavan style, Kohli v Morkel) | B4, A4 | None beyond JSON output |
| 7 | Pace vs spin | Tilak's "struggles vs spin" claim | A2 | OK |
| 8 | **Wagon wheels / pitch maps / shot maps** | Visually the best, but data does not exist | none | Cricsheet CSV2 has no line, length, shot or direction field, and `deliveries.fielder` is NULL. **Not possible from current data; do not promise it** |
| 9 | Fielding / catches | Underrated fielders | none | `fielder` is NULL in all rows (JSON format has it, CSV2 does not) |
| 10 | Partnerships, form tracker, venue, team summary | Occasional supporting beats | I2, I4, B6, B3 | None |

Likely top value: items 1 and 3 together, then 2. Items 4 to 7 add polish later.

## 4. Proposed interface (20 lines)

1. **One-way, file-based contract.** B writes JSON; A reads JSON. No shared code, no imports in either direction. Reason: the repos use different Python environments (A: `.venv` for faster-whisper + Node/Hyperframes; B: Python 3.12 `.venv` + DuckDB) and a different release rhythm; a JSON schema is the only thing both need to agree on.
2. **B owns:** `cricket facts --player "Albie Morkel" --competition IPL [--season 2012] --out <path>` (CLI in `cricket.cli`, built on B1/B2/B5/I1/B4 modules; exact flag names are a proposal). It writes one `facts.json`. Read-only on the DB.
3. **A owns:** `reels/<slug>/data/facts.json` (a copy, committed with the reel so it is reproducible), and a small change in `tools/build.py`: a block value may be a token such as `"big": "{runs.IPL.career}"`; build.py fills `big`, `count` and the formatted string from one number and **fails if the token is missing**. This removes the double typing and lets a reel mix typed (Wikipedia) and app-sourced numbers.
4. **Fact record (every number):** `{ "id": "ipl.runs.career", "value": 6769, "display": "6,769", "label": "IPL runs", "unit": "runs", "scope": {"competition": "IPL", "season": null, "player_cricsheet": "AM Morkel"}, "provenance": { "source": "Cricsheet ball-by-ball", "db_file": "cricket_analytics.duckdb", "db_built": "2026-10-24", "data_through": "2025-06-03", "matches": 78, "module": "B1", "caveat": "T20 only, not first-class or Test" } }` (the numbers in the example are placeholders, not real stats).
5. **Name resolution is B's job.** If `--player` matches several people or none, B exits non-zero with candidates; it never guesses. A passes the display name from the script.
6. **Charts: ship data, not images.** The video engine draws its own cards, bars and plates in the theme palette, with seekable GSAP animation. Plotly PNG/SVG from B would clash with six themes and per-reel palettes, and would not animate. If a new visual is needed (multi-bar season race, sparkline), A adds a block to `templates/engine.js` that eats the same JSON. The one exception worth keeping open: a static SVG export, only if a wagon-wheel ever becomes possible (it is not with current data).
7. **Verify mode (phase 2, optional):** `cricket verify --claims claims.json` takes `{player, competition, metric, claimed_value}` and returns match / mismatch / not-in-scope. This would have caught the Tilak "SR 160" claim by machine. Only worth building after items 1 and 3 work.
8. **Freshness is part of the contract.** `data_through` and `db_built` come from the DB itself; A prints a warning at build time if `data_through` is older than 30 days (value is a guess; pick one). Ties to the freshness-table rule in B's `CLAUDE.md`.
9. **Schema file:** B keeps `docs/video_facts.schema.json` as the single definition; A copies it into `tools/` when it changes. Version field `"schema": 1` in each `facts.json`; A refuses unknown versions.
10. **Order of work (sizes are guesses):** B first finishes the data refresh and label fix (the numbers are wrong until then: IPL and T20I are mixed in today's data), then facts for 3 players (S-M); A adds token support in `build.py` (S); then redo one old reel (e.g. Marsh or Tilak) through the new path as the test, comparing against the hand-typed numbers (S).

## Surprises (not chased)
- Marsh and Tambe reels have no source record in the repo.
- The video side already planned this link in `PLAN.md` ("Waiting: user will give full access"), so the user expects an export, not a code integration.
- B's data is T20 only, but most reels are about first-class, Test and ODI careers. For those the app cannot help unless Cricsheet's Test and ODI files are ingested (guess: they exist on Cricsheet; not checked).
- Mojibake characters (`�`) show in my terminal for en-dashes in a couple of `scenes.json` strings (Tambe "2000-02", Fawad marquee). Could be a console-encoding artifact, not checked in the file bytes.
