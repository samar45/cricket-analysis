# Cross-check: state league leaders vs outside sources (2026-11-15)

Ours = `scouting/leagues.py` (`league_batting`, `league_bowling`, `league_teams`, `league_summary`). Nothing was fixed; this is a report.

Access limits: the fetch tool refused every cricbuzz.com URL ("unable to fetch"), so the Cricbuzz series stats pages are **unchecked**. ESPNcricinfo was not reachable either. Used instead: Wikipedia, web search snippets, thesportstak, crictracker, cricketworld/Grokipedia (via search), crickettimes. Sources marked "mirror?" may be fed by the same Cricbuzz data, so agreement there is weaker proof than a truly independent source. Several searches returned pages for the 2026 season of a league instead of 2025; those were not used as 2025 evidence.

Series ids (ours, folder names in `data/external/cricbuzz/state_<key>/`): SPL 13073, UP T20 10735, TNPL 9866, Maharaja 10515, DPL 10581, T20 Mumbai 9875. TNPL "latest" in the data is 2026 (series 12620); 2025 was checked as asked.

## Verdicts

| league-season | item | ours | source | source URL | verdict |
|---|---|---|---|---|---|
| Sher-e-Punjab 2026 | top 5 runs | Dhir 655, Prabhsimran 575, Anmolpreet 497, Ramandeep 474, Sanvir 377 | identical list incl. high scores (173, 125*, 133, 91*, 74*) | https://thesportstak.com/cricket/series/sher-e-punjab-t20-2026-t20-12716/stats (mirror?) | match (5/5) |
| Sher-e-Punjab 2026 | top 5 wickets | Bhaskar 20 (6/16), Chadha 14 (4/9), Pandey 12, S Sharma 12, R Sharma 11 | identical list incl. best figures | same | match (5/5) |
| Sher-e-Punjab 2026 | Dhir 655 / Bhaskar 20 | same | Dhir 655, Bhaskar 20 (search snippets of several sites) | https://www.mrcricketuae.com/sher-e-punjab-t20/stats/ | match |
| Sher-e-Punjab 2026 | matches 27; team wins (AMS 6, MOK 5, LLN 5, FAF 4, JLD 4, BHT 3) | 27 | none found (champions Amritsar Soormas only; consistent) | https://www.latestly.com/sports/cricket/amritsar-soormas-vs-ludhiana-lions-live-streaming-online-and-free-telecast-sher-e-punjab-t20-league-2026-final-7602743.html | unchecked |
| UP T20 2025 | Karan Sharma 519 (Orange Cap) | 519, top of list | Orange Cap = Karan Sharma, no total given | https://crickettimes.com/2025/09/up-t20-league-2025-complete-list-of-award-winners-prize-money-who-won-orange-cap-purple-cap-and-emerging-player/ | name matches, number unchecked |
| UP T20 2025 | Shivam Mavi 22 wkts (Purple Cap) | 22, top of list | Purple Cap = Mavi; one snippet says "22 wickets" | same / https://en.wikipedia.org/wiki/Shivam_Mavi | name matches, number weakly supported |
| UP T20 2025 | rest of top 5 runs / wickets | Rizvi 491, A Yadav 407, Rinku 372, Chikara 370; Nigam 20, Rai 20, N Tiwari 19, Tyagi 18 | no 2025 table found (crictracker page shown is the 2026 season, Karan Sharma 361, so not comparable) | https://www.crictracker.com/uttar-pradesh-t20/ | unchecked |
| UP T20 2025 | champions / wins | Kashi Rudras 9 wins (top), final vs Meerut Mavericks (Meerut 7 wins, 2nd) | Kashi Rudras beat Meerut Mavericks in final (6 Sep 2025) | https://www.outlookindia.com/sports/cricket/meerut-mavericks-vs-kashi-rudras-up-t20-league-final-toss-playing-xis-match-report | consistent; counts unchecked |
| UP T20 2025 | matches | 34 | none | - | unchecked |
| TNPL 2025 | top 2 runs | Raheja 488 (9 inns), Baba Aparajith 412 | Raheja 488 in 9 matches; Aparajith B 412 | https://www.olympics.com/en/news/tamil-nadu-premier-league-tnpl-2025-most-runs-wickets-list (via search snippet) | match (2/2) |
| TNPL 2025 | top 3 wickets | Sonu Yadav 16 (7 inns), Esakkimuthu 14, Ashwin 13 | Sonu Yadav 16 in 7 matches; Esakkimuthu 14; Ashwin 13 | same | match (3/3) |
| TNPL 2025 | runs/wkts ranks 3-5 | Amit Sathvik 340, Shivam Singh 327, Ashwin 297; Tanwar 13, Sai Kishore 12 | not shown | - | unchecked |
| TNPL 2025 | top scorer / wickets names | Raheja, Sonu Yadav | Raheja most runs, Sonu Yadav most wickets | https://en.wikipedia.org/wiki/Tamil_Nadu_Premier_League | match (names) |
| TNPL 2025 | teams | Chepauk 7 and Tiruppur 7 wins, Dindigul 6 | final: Tiruppur beat Dindigul by 118; Wikipedia gives final positions only | same | consistent; counts unchecked |
| TNPL 2025 | matches | 32 | none | - | unchecked |
| Maharaja 2025 | Padikkal runs | 449 (12 inns, HS 99) | 449, 12 inns, HS 99 (cricketworld stats, via search) and Grokipedia 449; Wikipedia says 439 | https://www.cricketworld.com/cricket/series/maharaja-trophy-ksca-t20-2025/stats/batting-most-run50/129707 ; https://en.wikipedia.org/wiki/Maharaja_Trophy_KSCA_T20 | match (2 sources); differs by 10 from Wikipedia |
| Maharaja 2025 | Kranthi Kumar wkts | 26 (best 5/36) | Wikipedia 26; Grokipedia 26, best 5/36 | https://en.wikipedia.org/wiki/Maharaja_Trophy_KSCA_T20 | match |
| Maharaja 2025 | other top-5 runs/wkts | Smaran 415, Sharath 392, Lochan 360, Taha 342; Yash Raj Punja 23, Gopal 17, Hegde 16, Cariappa 16 | not shown (cricketworld pages returned 403) | - | unchecked |
| Maharaja 2025 | team wins | MNG 9, HUB 8, GUL 6, BLR 6, MYS 2, SHI 1 | Wikipedia: final Mangaluru beat Hubli by 14 runs (VJD); league finishing order Hubli, Mangaluru, Gulbarga, Bengaluru, Mysore, Shivamogga | same | consistent; win counts include playoffs, so not directly comparable: unchecked |
| Maharaja 2025 | matches | 34 recorded, 33 with innings (1 no-result without innings) | none | - | unchecked |
| Delhi PL 2025 | Arpit Rana 495 | 495 | Orange Cap Arpit Rana 495 | https://crickettimes.com/2025/09/dpl-2025-final-ceremony-complete-list-of-winners-who-won-orange-cap-purple-cap-mvp-and-emerging-player/ | match |
| Delhi PL 2025 | wickets | Money Grewal 20 (11 inns, 5/23), Simarjeet 20 (5/23), Dadar 19 | Grewal 20, Simarjeet 20 same best 5/23, Dadar 19 (crictracker snippet; Cricket Times gives Grewal 20 Purple Cap) | https://www.crictracker.com/delhi-premier-league-t20/stats/bowling-top-wicket-takers/ (the page I could open now shows the 2026 season) | match (snippet only, not re-opened) |
| Delhi PL 2025 | other top-5 | Sarthak Ranjan 449, Yash Dhull 435, Nitish Rana 393, Krish Yadav 390 | none; Wikipedia infobox names Priyansh Arya / Simardeep Singh with no numbers and unclear season | https://en.wikipedia.org/wiki/Delhi_Premier_League_T20 | unchecked |
| Delhi PL 2025 | matches | 44 recorded, 40 with innings | Wikipedia: "40 matches" | same | match on 40 played; 4 recorded matches have no innings (abandoned / no ball bowled, guess) |
| Delhi PL 2025 | team wins / finish | CDK 8, WDL 7, EDR 6 ... | Wikipedia: West Delhi Lions champions, Central Delhi Kings runner-up | same | consistent; counts unchecked |
| T20 Mumbai 2025 | top 5 runs / wickets | Sutar 271, Lad 242, Patil 233, Mulchandani 219, Parkar 212; Attarde 11, Mishra 10, Raut 9 | no numbers found. Wikipedia: Sutar was POM in the final, Sairaj Patil was Player of the Tournament | https://en.wikipedia.org/wiki/T20_Mumbai_League | unchecked |
| T20 Mumbai 2025 | teams | MSC Maratha Royals 5 and SoBo Falcons 5 wins (top 2) | Final: MSC Maratha Royals beat SoBo Falcons by 5 wkts | same | consistent; counts unchecked |
| T20 Mumbai 2025 | matches | 23 | none | - | unchecked |

## Verdict counts per league-season

| league-season | match | differs | consistent only | unchecked |
|---|---|---|---|---|
| Sher-e-Punjab 2026 | 3 | 0 | 0 | 1 |
| UP T20 2025 | 0 | 0 | 3 (names, champion) | 3 |
| TNPL 2025 | 3 | 0 | 1 | 3 |
| Maharaja 2025 | 2 | 0 (1 vs Wikipedia only) | 1 | 3 |
| Delhi PL 2025 | 3 | 0 | 1 | 2 |
| T20 Mumbai 2025 | 0 | 0 | 1 | 3 |

Every Cricbuzz-specific check is unchecked because cricbuzz.com could not be fetched.

## Differences

| item | size | likely cause |
|---|---|---|
| Padikkal 449 (ours) vs 439 (Wikipedia) | 10 runs | Probably Wikipedia is wrong or older: cricketworld and Grokipedia both say 449 (guess, not proven) |
| DPL 2025: 44 matches recorded, 40 with innings | 4 | Matches abandoned with no ball bowled still sit in `matches`; Wikipedia says 40 played. `league_summary()["matches"]` counts 44 |
| DPL 2025 `nr` column sums to 14 team-slots = 7 matches, but only 4 matches lack innings | 3 matches | Likely tie / no-result after play without a stored winner (guess, not checked per match) |

## Internal checks (ours, `innings.parquet`, batting rows, bowling rows)

| league-season | innings | batting runs + extras = total | bowler wkts <= wickets fallen | bowler runs = total - byes - leg byes - penalty | bowler balls = innings balls |
|---|---|---|---|---|---|
| Sher-e-Punjab 2026 | 54 | 54/54 | 54/54 | 54/54 | 54/54 |
| UP T20 2025 | 68 | 68/68 | 68/68 | 68/68 | 68/68 |
| TNPL 2025 | 64 | 64/64 | 64/64 | 63/64 (match 119171, Salem Spartans: bowlers 158 vs expected 159, 1 run) | 62/64 (2 innings) |
| Maharaja 2025 | 65 (33 matches) | 65/65 | 65/65 | 65/65 | 62/65 (3 innings) |
| Delhi PL 2025 | 78 (40 matches) | 78/78 | 78/78 | 78/78 | 77/78 (1 innings) |
| T20 Mumbai 2025 | 45 | 45/45 | 45/45 | 43/45 (match 119333 inn 2: bowlers 150 vs 151 expected, -1; match 119351 inn 1: bowlers 162 vs 161, +1) | 45/45 |

Ball-count mismatches (6 innings) were not chased; a rain-shortened or retired-bowler card is the usual reason (guess). The 1-run bowler gaps are likely wide/no-ball or penalty-run attribution on the scorecard (guess). Across all 1,337 state-league innings in the data, batting runs + extras = total in every one and exactly 1 innings has bowler wickets above wickets fallen (not in the six league-seasons above; not investigated).

Not done: per-team wins vs a points table (no source reachable), name-spelling split check (bowling and batting group on Cricbuzz player id, so a spelling split inside one id cannot happen; a split across two ids was not tested), super-over handling.
