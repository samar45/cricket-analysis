# Handover: cricket-analysis → Edit Pipeline (Reels)

For the Claude session working in `D:\Claude projects\Edit Pipeline`. Read this first, then `docs/HANDSHAKE_video.md` (the exact contract) in this repo.
Written 2026-10-25. Repo: `D:\Claude projects\cricket-analysis` (GitHub samar45/cricket-analysis, branch `main`; new work on `dev`).

## What this app is
A local cricket stats engine built on Cricsheet ball-by-ball data (ODC-BY licence, credit "Cricsheet").
- **Data:** 10,418 T20 matches through 2026-10-14. Covers IPL, men's and women's T20I, BBL, PSL, CPL, SA20, The Hundred and the T20 Blast. **T20 only:** no Test, ODI or first-class data yet.
- **About 20 analysis modules,** including batting, bowling, compare, matchup, pace_vs_spin, home_away, chase_vs_set, pressure, dismissal_profile, innings_list (debut / last N / best), player_profile and fielding. A "stories" module that writes ranked reel hooks is being built.
- **Every number comes with provenance:** source, data-through date, DB date and caveats.
- **Checked against known records,** for example Kohli 8,661 IPL runs to 2025, Buttler 863 in IPL 2022 and Bumrah's best IPL figures of 5/10.

## How Edit Pipeline uses it (no shared code: call the CLI)
Use the full path, so it works from the Edit Pipeline folder with its own venv:
```
"D:\Claude projects\cricket-analysis\.venv\Scripts\cricket.exe" <command>
```

| Need | Command |
|---|---|
| Exact player name (Cricsheet uses initials: "RG Sharma") | `cricket resolve "RG Sharma"` or `cricket resolve "Sharma"`. Careful: a full name can match a different player ("rohit sharma" finds an associate player named Rohit Sharma, not RG Sharma), so check the matches count and last date |
| Everything for one player's reel, as one JSON file | `cricket facts --player "V Kohli" --competition ipl --out reels/<slug>/data/facts.json` |
| One stat table | `cricket run <module> --player "V Kohli" --competition ipl [--last_n_years 5] --json --out file.json` |
| Reel chart as PNG (1080×1920 or 1080×1080, transparent background) | `cricket chart <module> --player "V Kohli" --competition ipl --aspect 9:16 --png reels/<slug>/assets/kohli.png` |
| List modules / parameters | `cricket modules`, `cricket schema --json` |
| How fresh is the data | `cricket info` |

## facts.json: the part `scenes.json` should read
- `meta`: player, competition, `data_through`, source, the module calls made, and the sections skipped.
- `facts`: sections such as `career`, `best_season`, `by_phase`, `vs_pace_spin`, `home_away`, `chase_vs_set`, `pressure`, `dismissals` and `profile`. Bowlers get bowling keys instead.
- `tokens`: display-ready strings for direct substitution, e.g. `{career.runs}` → `"9,336"`, `{career.average}` → `"40.42"`, `{profile.bat_hand}`.
- `tokens_raw`: the same keys as plain numbers, for count-up animations.

### Suggested change on the Edit Pipeline side
`build.py` replaces `{token}` placeholders in `scenes.json` with values from `facts.json`, and **fails if a token is missing**. That ends hand-typed stats and the double typing of `big` and `count`.

## Rules
- **Never hand-type a stat.** Take it from `facts.json` or `cricket run`, and print `meta.source` + `meta.data_through` in the reel's source line.
- **Resolve names first.** A vague name such as "Kohli" makes `facts` exit with an error and list candidates.
- **T20 only.** Reels about first-class, Test or ODI careers still need another source.
- **Bowling type and batting hand** come from a reviewed list of about 990 players, mostly web-checked; others show "unknown". Batting hands marked low confidence are not yet verified.
- **Super overs are excluded,** matching official records.
- **Never use the Hawk-Eye trial data in a reel:** it is local only and has no licence.

## Where things are (in the cricket-analysis repo)
- `docs/HANDSHAKE_video.md`: the contract, versioned; read its changelog for any changes.
- `docs/RUNBOOK.md`: how to set up, update the data (`cricket update`) and check health (`cricket health`), without Claude.
- The dashboard: `.venv\Scripts\streamlit.exe run dashboard/app.py`, with Explore, Ask, Data health and a Video tab with PNG download.
- The data must be kept fresh: run `cricket update` with the dashboard stopped. It pulls only new matches and checks them.
