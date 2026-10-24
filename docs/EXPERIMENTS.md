# cricket-analysis - experiments and ideas (newest at the bottom)

One entry per experiment: idea, how we test it, result (measured / guess), decision (keep / drop / later).
Blocked ideas stay here with the reason, so nobody retries them without a new reason.

| Date | Idea | Test | Result | Decision |
|---|---|---|---|---|
| 2026-10-24 | Length / line / shot / wagon wheel / dropped catches | Research worker searched Cricsheet, Kaggle, Hawk-Eye, ESPNcricinfo (`docs/RESEARCH_data_nlq.md` §2) | No free, legal bulk source found. ESPNcricinfo terms ban scraping (claimed by its terms page) | **Blocked** until a legal source exists |
| 2026-10-24 | Catches per fielder from CSV2 | Lead opened raw IPL file: `fielder_1` filled on caught rows | Measured: works for 1 file; worker says ~100% across comps | Keep → Phase 1 loader, Phase 7 fielding stats |
| 2026-10-24 | Switch to Cricsheet JSON | Research compared formats | JSON adds only DRS, replacements, powerplays, stage (claimed by Cricsheet docs) | Later (Phase 8), only if those extras are wanted |
| 2026-10-24 | Local NLQ with `nemotron-3.5-bolt:e4b` | `ollama list`: present, 7.9 GB, tools capability | Won't fit 4 GB VRAM; speed unknown (guess: slow) | Test in Phase 6 with a 50-question eval |
