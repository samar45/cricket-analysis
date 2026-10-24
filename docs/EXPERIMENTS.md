# cricket-analysis - experiments and ideas (newest at the bottom)

One entry per experiment: idea, how we test it, result (measured / guess), decision (keep / drop / later).
Blocked ideas stay here with the reason, so nobody retries them without a new reason.

| Date | Idea | Test | Result | Decision |
|---|---|---|---|---|
| 2026-10-24 | Length / line / shot / wagon wheel / dropped catches | Research worker searched Cricsheet, Kaggle, Hawk-Eye, ESPNcricinfo (`docs/RESEARCH_data_nlq.md` §2) | No free, legal bulk source found. ESPNcricinfo terms ban scraping (claimed by its terms page) | **Blocked** until a legal source exists |
| 2026-10-24 | Catches per fielder from CSV2 | Lead opened raw IPL file: `fielder_1` filled on caught rows | Measured: works for 1 file; worker says ~100% across comps | Keep → Phase 1 loader, Phase 7 fielding stats |
| 2026-10-24 | Switch to Cricsheet JSON | Research compared formats | JSON adds only DRS, replacements, powerplays, stage (claimed by Cricsheet docs) | Later (Phase 8), only if those extras are wanted |
| 2026-10-24 | Local NLQ with `nemotron-3.5-bolt:e4b` | `ollama list`: present, 7.9 GB, tools capability | Won't fit 4 GB VRAM; speed unknown (guess: slow) | Test in Phase 6 with a 50-question eval |
| 2026-10-24 | Where analysts get line/length/shot/drops: official sites (BCCI/IPL, ICC), vendors (CricViz, Opta, Sportradar…), forums, DIY video/commentary | Research worker → `docs/RESEARCH_ball_tracking.md` (9 options ranked) | Official sites: no reuse allowed. Vendors with line/shot (Sportradar, CricViz, Opta) are enterprise-only. Cheap APIs (€29/mo+) have no line/length. ESPNcricinfo keeps drop logs but doesn't publish them | See the two experiments below |
| 2026-10-24 | HawkeyeStats GitHub CSVs (`github.com/alittlefitness/HawkeyeStats`): speed, pitch x/y (length/line), stumps x/y, field x/y (where the ball went) for IPL, ODI, Test, men and women | Lead verified the repo and file list | No licence; README says it's tidied from the ICC's pulselive feed; seasons unknown; partial coverage | **Samar to decide** (medium-high legal risk). If yes: read the schema only, keep data out of git |
| 2026-10-24 | Hand-tag one IPL match from highlights (~25–40 balls: wickets, 4s, 6s, drops) and join to `deliveries` | Time the effort, check the join on match_id + innings + over.ball | Not run | Proposed, cheap and legal |
