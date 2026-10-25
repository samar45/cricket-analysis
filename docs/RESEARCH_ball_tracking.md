# Research: ball-level detail beyond Cricsheet (line, length, shot, wagon wheel, drops)

Date: 2026-10-24. Read-only desk research (web search plus page reads). Nothing downloaded, scraped, signed up for, or called via API.
Labels: **[V]** verified, I read it on the page (URL given). **[C]** claimed by a source (search snippet, vendor, paper) and not checked further. **[G]** my guess.
Extends `docs/RESEARCH_data_nlq.md` section 2. Caught-by-fielder is already in Cricsheet, so the gaps are drops, catch difficulty, line, length, shot, wagon wheel.

## 0. Surprises (read first)

1. **A public GitHub repo of Hawk-Eye tracking CSVs exists**: `alittlefitness/HawkeyeStats` has men's and women's IPL, ODI and Test files **[V]** (https://github.com/alittlefitness/HawkeyeStats). Fields: ball speed, pitch x/y (bounce point), stumps x/y, field x/y (where the ball went, i.e. wagon wheel). The README says it is a tidy version of JSON from an ICC endpoint (`cricketapi-icc.pulselive.com`) **[V]**. **No licence file, no seasons stated, match-id scheme not stated** **[V]**. A 2026 high-school-journal paper used it (~140,000 legal IPL deliveries, 24 columns incl. `match_id`, `pitch_x`, `pitch_y`, `field_x`, `field_y`) **[V]** (https://nhsjs.com/2026/does-good-length-outside-off-really-work-a-ball-tracking-study-of-wickets-in-the-ipl/). So the paper-reported IPL men's subset is not complete (about 140k of roughly 1.8M+ balls in our DB; **[G]** that is under 10% of IPL balls, but our DB mixes comps, so treat as rough). It gives length/line/wagon, but **not shot type, not drops**.
2. **ESPN reports dropped-catch counts per player, team and venue** from "ESPNcricinfo's logs" **[V]** (https://africa.espn.com/cricket/story/_/id/44796342/ipl-2025-dropping-catching-standards-repeat-offenders-biggest-beneficiaries: 103 of 431 chances dropped after 39 IPL 2025 games). So drops are recorded somewhere in Cricinfo's data; how it is recorded or exposed is **not stated** on that page. The same ESPN page gives no definition of a drop **[V]**.
3. The Sportradar v2 cricket feed lists "ball tracking for shot and delivery, type coding" and, at Advanced level, "shot and ball types, wagon wheel data" **[V]** (https://developer.sportradar.com/cricket/reference/cricket-overview and https://developer.sportradar.com/sportradar-updates/changelog/cricket-v2-1). The pages do not mention line, length, drops, trial access or price **[V]**.
4. My earlier doc cited arXiv 2608.18020 for "tracking exists for 57% of IPL...". I re-read its abstract page: it speaks of "ball-level primitives" and 2.7M legal deliveries, **nothing about tracking coverage** **[V]**. Treat the earlier 57/66/75% numbers as **unverified**; I could not reproduce them.
5. The `bounceR` R package, which reportedly reads Hawk-Eye data "available on the ICC and BCCI websites", is mentioned in the R `cricketdata` Cricsheet vignette, along with the remark that no public WBBL Hawk-Eye set exists **[V]** (https://cran.uni-muenster.de/web/packages/cricketdata/vignettes/cricsheet.html, passage read at offset 100000). I could not find the package itself **[V: not found by search]**. This is a hint that the official sites show Hawk-Eye data, **not** a licence to use it.

## 1. Official sources

Method: I could only fetch static text. Several official sites are JavaScript apps, so "what the page shows" below is limited to what the fetch returned. Do not read "not seen" as "not there".

| Site | Fields visible to me | Form | Terms on reuse / automated access |
|---|---|---|---|
| iplt20.com (BCCI) Matches page | Fixtures/results list, season filter 2008-2026, venue filter. Page loaded as "Loading..." so no match-centre fields were seen **[V]** (https://www.iplt20.com/matches/results) | JS app | Terms: content "intended solely for personal use"; no copying; reproduce/publish/exploit needs BCCI prior written authorisation. Scraping and data mining are **not named** **[V]** (https://www.iplt20.com/terms-and-conditions) |
| icc-cricket.com | Not inspected (JS). The HawkeyeStats README says ICC's pulselive endpoint serves JSON with Hawk-Eye fields **[V as a README claim]** | JSON behind the site **[C]** | ICC owns "data" on the site; personal-use extracts only; no commercial use without licence; no explicit scraping clause **[V]** (https://www.icc-cricket.com/about/the-icc/legal-notices/website-terms-of-use) |
| cricket.com.au (BBL) | Not inspected. | n/a | "Systematic retrieval of data or other content" to build a database needs Cricket Australia's prior written permission **[V]** (https://www.cricket.com.au/terms-and-conditions). This is the clearest anti-scraping line I found |
| ECB / thehundred.com | Not inspected | n/a | Terms page URLs I tried returned 404; **not read** **[V: not found]** |
| PSL, CPL, SA20 sites | Not checked (time) | n/a | Not read |
| ESPNcricinfo | Already covered in earlier doc: Disney terms bar scraping and dataset building **[V in earlier doc]**; its own pages returned 403 to me **[V]** | n/a | High risk |

Takeaway: none of the official sites I could read grants reuse. The ICC and BCCI terms do not name bots, but both reserve content and "data" rights and allow personal use only. Cricket Australia explicitly requires permission for systematic retrieval. All of this is my reading, not legal advice.

## 2. Commercial providers

Prices are as claimed on the vendor page unless noted.

| Provider | Line/length | Shot | Wagon | Fielding / drops | Price and access | Source |
|---|---|---|---|---|---|---|
| Hawk-Eye (Sony) | Yes in principle (it is the tracker) **[C]** | n/a | n/a | n/a | Data page lists feeds for "partners"; no cricket detail, no price, contact by email **[V]** (https://www.hawkeyeinnovations.com/data) | |
| CricViz | Centurion portal uses licensed third-party ball tracking for speeds, lines, lengths **[C]** (ellipsedata.com summary via search) | **[G]** likely | **[G]** likely | Own data collection for CA **[C]** | No public price. Sells to boards, teams (e.g. London Spirit, Cricket Australia), broadcasters **[C]** | search snippets |
| Stats Perform / Opta | Not stated | Not stated | Not stated | Says it covers "player performance in the field" **[C]** | Enterprise only; official data partner for ECB, CA, CSA, NZC, ICC **[C]** | statsperform.com snippet |
| Sportradar | Not stated | Yes: "shot and ball types" **[V]** | Yes at Advanced level **[V]** | "Unique fielding data points", none named **[V]** | Pricing not public, no free tier seen on the page **[V]**. v2 data is official for ICC, ECB, CPL **[V]** | link in surprises |
| Roanuz | Page returned an error ("app key invalid") **[V]**, so unread | | | | Unknown | |
| EntitySport | Not mentioned on pricing page **[V]** | no | no | Player stats list catches and stumpings only **[V]** | Starter $150/mo (international only), Pro $250/mo (adds domestic T20 leagues), Elite $450/mo. Free dev token with a few finished competitions and samples **[V]** (https://entitysport.com/cricket-api/) | |
| Sportmonks | Ball-by-ball with over, bowler, batter, runs, wicket flag. No line/length/shot/wagon/fielding mention **[V]** | no | no | no | EUR 29/mo (26 leagues), 75 (64), 125 (100+); free token plus 14-day trial; IPL and BBL pages exist, The Hundred not mentioned **[V]** (https://www.sportmonks.com/cricket-api/) | |
| CricketData (CricAPI) | no | no | no | no | Free signup; "paid from $5.99" claimed, ball-by-ball on paid plans **[V]** (https://cricketdata.org/), free limit of 100 hits/day **[C]** | |
| Cricbuzz via third-party API/Apify | Commentary text only **[C]** | | | | e.g. api.market $19.99/mo; Apify $1 per 1,000 requests **[C]**. No official Cricbuzz API **[C]**. Underlying content is scraped Cricbuzz, so risk is high **[G]** | |
| NV Play (scoring/analysis app) | Manual pitch-map coding with x/y click coordinates in CSV export **[V]** (https://support.nvplay.com/hc/en-gb/articles/32473170149273) | yes manual | yes manual | manual | Commercial product, price not seen | |

Takeaway: the cheap APIs (Sportmonks, CricketData, EntitySport) give Cricsheet-like data and nothing new. Only Sportradar, CricViz, Opta and Hawk-Eye carry the rich fields, and they are enterprise deals. **[G]** A hobbyist is unlikely to be sold a licence, and the licence would probably forbid keeping a local DB.

## 3. How public analysts get it

- **Use a free repo of scraped tracking JSON** (HawkeyeStats above). Example: the NHSJS 2026 paper **[V]**.
- **Use broadcaster-style or club tools**: NV Play, Pitch-Vision, Fulltrack AI. A University of Adelaide study found Fulltrack AI's line/length output agreed closely with motion capture (ICC > 0.96) **[C]** (search snippet; paper not opened). That is for your own nets bowling, not broadcast.
- **Work from Cricsheet only** and say so. A "fielding woes" page claims Cricsheet-only methodology **[C]** and a Univ. of Sunderland paper on 4,660 fielding outcomes (2016-2020, IPL included) exists (DOI 10.1080/24748668.2025.2455276) **[V: title and metadata only; the PDF body was unreadable, so its data source is unknown]**.
- **Substack writers** (e.g. Kohli and Kipling "Clues from the crease") discuss tracking sparsity **[C]**: public tracking data is thin.
- I did **not** find Reddit/r/datasets threads (search returned none) **[V: not found]**. No Kaggle set with line/length/shot found, same as the earlier doc.

Academic datasets (for building models, not for match stats):

| Dataset | What | Size/licence | Joins to matches? |
|---|---|---|---|
| IEEE DataPort "Front Pitch View shot extraction and ball tracking" | 5,000 FPV vs non-FPV frames, pitch/umpire boxes, 3,000 ball boxes, 300 delivery clips labelled full/good/short **[V]** | ~8 MB; needs IEEE DataPort subscription; no licence stated; GitHub copy (KumailAbb/FPVShotDetection) **[V]** (https://ieee-dataport.org/node/15628) | No: footage not identified |
| HF `rokmr/cricket-shot` | 1,750 clips, 10 shot classes (cover, defence, flick, hook, late cut, lofted, pull, square cut, straight, sweep), 2.89 GB, Apache-2.0 **[V]** (https://huggingface.co/datasets/rokmr/cricket-shot) | Clip source not stated; copyright of the clips is unclear **[G]** | No |
| CricShot10 / KUCricShot | 10-class and 4-class shot clip sets **[C]** (search snippets) | not checked | No |
| CVPRW 2024 "Cricket Excited Actions" | Classes include catches, sixes, fours, clean bowled **[C]**; repo Altaf-hucn/Cricket-Excited-Actions-Benchmark **[C]** | paper page returned 403; size/licence unknown | No |
| ASAP / LCric (arXiv 2301.06866) | ~1,000 hours of cricket video aligned to web commentary from ESPNCricinfo **[V]** (https://arxiv.org/abs/2301.06866, repo https://github.com/asap-benchmark/asap-pipeline) | README says cricket pipeline release is unfinished and the user supplies videos **[V]**; licence of data not stated | Aligned to Cricinfo commentary, not Cricsheet |

None of these has a dropped-catch label **[V for the ones I read; C for the rest]**.

## 4. Do-it-yourself options

**(a) Hand-tag from highlights.** Fields you could add: length (full / good / short, or yorker/full/good/short), line (wide off / off / middle-leg), shot name, rough wagon sector (8 or 12 slices), drop flag plus easy/hard. Effort per T20 innings (120 balls): **[G]** about 1.5-3 hours with a spreadsheet and the video paused per ball; highlights show only boundaries and wickets so bias toward fours, sixes and wickets (selection bias, not a full-ball sample). Dropped catches are visible in highlights, so drops are the best field to hand-tag. Legal: your own observations, stored as your own data, are low risk **[G]**. You must not copy or redistribute the video. Join: Cricsheet `match_id` + `innings` + `over.ball` (already in the schema), so the join is clean.

**(b) Computer vision on broadcast video.** Building blocks exist: TrackNet-style ball trackers (tennis origin; V4 has released code) **[C]**, YOLOv8 pitch and ball detection in a 2025 cricket paper **[C]**, the shot-clip datasets above, and the front-pitch-view data for length classes. No ready-made cricket length tool was found **[V: not found]**. On an RTX 3050 4 GB, inference with small YOLO models is fine and fine-tuning a small model is possible **[G]**, but training TrackNet-class video models on 4 GB is tight **[G]**. The blocker is not the GPU, it is getting broadcast video legally: broadcaster copyright and YouTube terms **[G]**. Effort: weeks. Not recommended.

**(c) NLP over commentary text.** The words "dropped", "put down", "full and wide", "short" live in ball-by-ball commentary, but the usable sources are: ESPNcricinfo (Disney terms ban it **[V earlier]**), Cricbuzz (no official API **[C]**), Sportradar "AI automated commentary" (paid, **[V]** that v2 has it). I found no commentary source with an open licence. **[G]** Guardian/BBC over-by-over text exists for some games but covers few T20 leagues and I did not check their terms. If commentary were available, regex on a short word list is trivial; the legal part is the problem. Drops via NLP: only where you already hold the text.

## 5. Ranked options

Legal risk is my reading of the terms I could read (not legal advice).

| # | Source | Fields (length / line / shot / wagon / drops / catch difficulty) | Coverage | Legal risk | Cost | Effort | Join to Cricsheet |
|---|---|---|---|---|---|---|---|
| 1 | Hand-tag your own sample (spreadsheet, optionally NV Play-style grid) | L yes / line yes / shot yes / wagon rough / drops yes / difficulty yes (subjective) | Only what you tag; start with drops from highlights | **Low**: own notes, no video copied | Free | High per match (G: 2-3 h/innings) | Clean: match_id + innings + over.ball |
| 2 | HawkeyeStats (GitHub CSVs from ICC feed) | L from pitch_y / line from pitch_x / no shot / wagon from field_x,y / no drops / no | Men's and women's IPL (partial, ~140k balls reported), ODI, Test; seasons not stated **[V]** | **Med-high**: no licence; derived from ICC endpoint whose site terms reserve "data" and allow personal use only | Free | Low to read, medium to join | Unknown: columns have `match_id` but scheme not stated; probably need date+teams+batter/bowler/runs match **[G]** |
| 3 | Sportradar v2 | L unclear / line unclear / shot yes / wagon yes / fielding "unique points" unknown / unknown | Official for ICC, ECB (so Hundred), CPL **[V]** | Low if licensed, but **not obtainable** for a hobbyist **[G]** | Not public; enterprise **[V: no price]** | Low once licensed | Via fixture ids; need mapping |
| 4 | CricViz / Opta / Hawk-Eye feeds | Everything incl. fielding events **[C]** | Pro comps | Low if licensed | Enterprise; no price found | n/a | Not realistic for hobby use |
| 5 | Mid-tier APIs (Sportmonks EUR 29/mo, EntitySport $150/mo) | Ball-by-ball only, no L/line/shot/wagon/drops seen **[V]** | IPL, BBL etc. depending on plan | Low (licensed) | EUR 29+ | Low | Date+teams (no gain over Cricsheet) |
| 6 | Cricinfo commentary + NLP for drops | Drops yes, length/line words yes, shot names yes; no coordinates | Most pro matches **[C]** | **High**: Disney terms | Free | Medium + fragile | date+teams+over.ball |
| 7 | Third-party commentary scrapers (Apify/api.market Cricbuzz) | Commentary text | Broad | **High**: resold scrape **[G]** | $1/1,000 req to $19.99/mo **[C]** | Low | date+teams |
| 8 | Academic video datasets (HF cricket-shot, IEEE FPV) | Train a shot or length classifier | Not match-level | Low-med (Apache-2.0 on HF; clip origin unclear) | Free (IEEE needs subscription) | High, needs video | None |
| 9 | CV on broadcast video | Everything in theory | Your clips | **High**: broadcast copyright **[G]** | GPU limited | XL | Manual |

### Top 3 for a solo hobbyist

1. **Hand-tag drops (plus length/line on wickets and boundaries) for a small sample.** Legal, free, clean join. Start with drops only; they are the rarest and most useful field and the easiest to see.
2. **Look at HawkeyeStats, with Samar's decision on legal risk.** Biggest data gain for the least effort, but there is no licence and it came from an ICC feed. Decision for Samar: use privately and never ship it in the repo or redistribute, or skip. My lean: read the header and schema only until he decides.
3. **Stay on Cricsheet and build fielding-chance proxies** (catch partnerships, catches per fielder, who bowls when catches arrive). No new data needed; zero legal risk.

### Experiment we could run this week (legal, small)

Pick one IPL match Samar already watches. In a CSV with columns `match_id, innings, over, ball, length, line, shot, drop(0/1), catch_difficulty(easy/medium/hard), notes`, tag **only the highlights package**: every wicket, four, six and every dropped catch (typically 25-40 balls). Time it. Then join it to `deliveries` on match_id + innings + over.ball in a test and check the batter/bowler match on every row. Success = the join has 100% key hits and the time per tagged ball is known, so we can decide whether to scale.

Optional pre-check (needs Samar's yes, read-only): open the HawkeyeStats `mensIPL` CSV in the GitHub web viewer, note the header and one match's rows, and see whether it carries a date, teams, or a match id we can map. Do not clone or download.

## Open items (not chased)
- Terms for The Hundred, PSL, CPL, SA20 sites were not read.
- Cricinfo's per-ball drop field (if exposed) is unconfirmed; I could not open Cricinfo pages (403).
- Roanuz page failed to load; its fields are unknown.
- Sunderland paper's data source and CVPRW dataset size/licence not read.
- I did not verify whether HawkeyeStats files are current or which IPL seasons are present.
