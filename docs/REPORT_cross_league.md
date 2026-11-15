# Cross-league scouting board (state T20 leagues + SMAT 2025 + IPL)

Built by `src/cricket_analytics/scouting/profile.py` (`cricket scouting board`, `cricket scouting profile "<name or id>"`). Data: Cricbuzz scorecards for
14 state leagues (all editions we scraped) and SMAT 2025-26; IPL, earlier SMAT and T20I from the Cricsheet DB. Nothing dated 2026-10-15 or later is used.
Board = 874 players with 100+ balls faced or bowled in the state leagues.

## How to read this
- **bat_score** = state-league runs minus what an average state-league batter scores off the same balls. **bowl_score** = runs saved against the average economy over the bowler's own overs. Both are in runs; state leagues are pooled (no per-league adjustment).
- **ipl_capped**: `yes` = linked Cricsheet player has an IPL match; `no` = linked with no IPL match, or no Cricsheet record at all (our DB holds every IPL match, so no record = never played IPL); `unknown` = a possible IPL match was found but its identity is doubtful (withheld, never guessed). "Capped" means played an IPL match in our DB (squad-only or impact-sub-unused players are not seen).
- **level**: highest level reached in our data: `IPL` > `T20I` > `SMAT` (Cricsheet SMAT 2016-24 or Cricbuzz SMAT 2025) > `state league only`; `unclear (doubtful link)` for doubtful links. A player with both T20I and SMAT is shown as T20I; one with IPL as IPL.
- **ipl_link**: how the Cricbuzz player was tied to a Cricsheet player (see below).

## Players on the board by level
| level | players |
|---|---|
| state league only | 476 |
| SMAT | 149 |
| unclear (doubtful link) | 129 |
| IPL | 112 |
| T20I | 8 |

| level | no | unknown | yes |
|---|---|---|---|
| IPL | 0 | 0 | 112 |
| SMAT | 149 | 0 | 0 |
| T20I | 8 | 0 | 0 |
| state league only | 476 | 0 | 0 |
| unclear (doubtful link) | 0 | 129 | 0 |

## Top 15 uncapped batters (ipl_capped = no, by bat_score)
| name | team | state_inns | state_runs | state_balls | state_avg | state_sr | bat_score | smat_runs | smat_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|---|---|
| Tushar Raheja | IDream Tiruppur Tamizhans | 33 | 1429 | 869 | 47.6 | 164.4 | 217.9 | 151 | 92 |  |
| Abhishek Pathak | Bundelkhand Bulls | 14 | 509 | 216 | 36.4 | 235.6 | 208.0 | 13 | 9 |  |
| Ajay Rohera | Jabalpur Royal Lions | 23 | 1122 | 667 | 53.4 | 168.2 | 192.4 | 66 | 45 | name_only |
| Luvnith Sisodia | Shivamogga Yodhas | 45 | 1327 | 831 | 30.9 | 159.7 | 168.9 | 0 | 0 | name_only |
| Parth Chaudhary | Gwalior Cheetahs | 14 | 675 | 370 | 48.2 | 182.4 | 159.4 | 0 | 0 |  |
| LR Chethan | Mysore Warriors | 44 | 1362 | 866 | 33.2 | 157.3 | 155.1 | 0 | 0 | name_only |
| Suraj Ahuja | Coastal Kings Mangaluru | 44 | 1045 | 643 | 34.8 | 162.5 | 148.9 | 106 | 78 | team_checked |
| Siddharth Joon | Central Delhi Kings | 20 | 477 | 242 | 25.1 | 197.1 | 139.7 | 0 | 0 |  |
| Ritik Tada | Jabalpur Royal Lions | 15 | 436 | 224 | 43.6 | 194.6 | 123.8 | 0 | 0 |  |
| Vansh Bedi | Central Delhi Kings | 22 | 393 | 200 | 23.1 | 196.5 | 114.3 | 0 | 0 |  |
| R Rajkumar | Trichy Grand Cholas | 31 | 571 | 332 | 26.0 | 172.0 | 108.3 | 167 | 104 |  |
| Uday Saharan | Bathinda Royals | 6 | 351 | 182 | 70.2 | 192.9 | 97.4 | 0 | 0 |  |
| Ankit Rajesh Kumar | West Delhi Lions | 18 | 381 | 206 | 21.2 | 185.0 | 93.9 | 448 | 260 | team_checked |
| Samson | Kerala | 6 | 368 | 197 | 73.6 | 186.8 | 93.5 | 233 | 169 |  |
| Salil Arora | Ludhiana Lions | 10 | 366 | 197 | 52.3 | 185.8 | 91.5 | 358 | 180 |  |

## Top 15 uncapped bowlers (ipl_capped = no, by bowl_score)
| name | team | state_bowl_balls | state_wkts | state_econ | bowl_score | smat_wkts | smat_bowl_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|
| Shubhang Hegde | Kalyani Bengaluru Blasters | 994 | 56 | 7.04 | 275.9 | 6 | 96 | team_checked |
| Jhathavedh Subramanyan | Vida Kovai Kings | 714 | 37 | 6.87 | 218.7 | 0 | 0 |  |
| M Silambarasan | Chepauk Super Gillies | 569 | 30 | 6.72 | 188.4 | 0 | 0 |  |
| Shreesha Achar | Shivamogga Yodhas | 666 | 37 | 7.27 | 159.1 | 0 | 0 |  |
| Vasuki Koushik | Coastal Kings Mangaluru | 787 | 37 | 7.69 | 132.6 | 10 | 144 | name_only |
| Prithviraj Shekhawat | Coastal Kings Mangaluru | 480 | 20 | 7.3 | 112.3 | 0 | 0 |  |
| Satvik Deswal | Ossudu Accord Warriors | 240 | 14 | 5.9 | 112.2 | 0 | 0 |  |
| Manan Bhardwaj | West Delhi Lions | 399 | 25 | 7.05 | 109.8 | 0 | 0 |  |
| S Ajith Ram | SKM Salem Spartans | 455 | 21 | 7.42 | 97.0 | 0 | 0 |  |
| Shikhar Shetty | Hubli Tigers | 324 | 15 | 6.96 | 94.0 | 0 | 0 |  |
| Macneil Noronha | Gulbarga Mystics | 517 | 26 | 7.61 | 94.0 | 1 | 24 |  |
| Paras Gurbax Arya | Gulbarga Mystics | 591 | 22 | 7.77 | 92.3 | 0 | 0 |  |
| Himanshu Sahani | Villianur Mohit Kings | 241 | 17 | 6.45 | 90.6 | 0 | 0 |  |
| Shashank Attarde | Aakash Tigers MWS | 264 | 21 | 6.7 | 88.0 | 0 | 0 |  |
| Kartik Chadha | Ludhiana Lions | 234 | 14 | 6.46 | 87.4 | 0 | 0 |  |

## Strong numbers but IPL status unknown (could be capped; check by hand), top 10 each
| name | team | state_inns | state_runs | state_balls | state_avg | state_sr | bat_score | smat_runs | smat_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|---|---|
| Mohammed Taha | Hubli Tigers | 44 | 1288 | 793 | 31.4 | 162.4 | 182.8 | 0 | 0 | doubtful |
| Ankush Singh | Chambal Ghariyals | 17 | 514 | 286 | 34.3 | 179.7 | 115.4 | 101 | 68 | doubtful |
| Sarthak Ranjan | North Delhi Strikers | 18 | 942 | 600 | 55.4 | 157.0 | 105.8 | 0 | 0 | doubtful |
| Jonty Sidhu | Central Delhi Kings | 22 | 611 | 370 | 35.9 | 165.1 | 95.4 | 0 | 0 | doubtful |
| Yajas Sharma | Outer Delhi Warriors | 16 | 412 | 230 | 27.5 | 179.1 | 91.5 | 0 | 0 | doubtful |
| V Manoharan | Kochi Blue Tigers | 12 | 414 | 240 | 34.5 | 172.5 | 79.5 | 0 | 0 | doubtful |
| Sagar Solanki | Rewa Jaguars | 15 | 369 | 218 | 36.9 | 169.3 | 65.2 | 0 | 0 | doubtful |
| Anmol Sharma | South Delhi Superstarz | 21 | 765 | 506 | 42.5 | 151.2 | 59.8 | 0 | 0 | doubtful |
| Kuldeep Gehi | Gwalior Cheetahs | 8 | 265 | 158 | 33.1 | 167.7 | 44.8 | 0 | 0 | doubtful |
| Adarsh Singh | Kanpur Superstars | 10 | 352 | 225 | 50.3 | 156.4 | 38.4 | 0 | 0 | doubtful |

| name | team | state_bowl_balls | state_wkts | state_econ | bowl_score | smat_wkts | smat_bowl_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|
| Ritesh Bhatkal | Mysore Warriors | 450 | 24 | 7.43 | 95.8 | 0 | 0 | doubtful |
| Ajay B Mishra | ARCS Andheri | 246 | 13 | 6.46 | 91.9 | 0 | 0 | doubtful |
| Kartik Yadav | South Delhi Superstarz | 204 | 14 | 6.29 | 81.9 | 0 | 0 | doubtful |
| Sachin Shinde | Mangalore Dragons | 186 | 13 | 6.35 | 72.8 | 0 | 0 | doubtful |
| Naman Sharma | Ruby White Town Legends | 226 | 12 | 6.93 | 66.8 | 0 | 0 | doubtful |
| Saurabh Kumar | Tungabhadra Warriors | 186 | 9 | 6.61 | 64.8 | 0 | 0 | doubtful |
| Shubham Sharma | Jodhpur Sunrisers | 185 | 9 | 6.65 | 63.4 | 0 | 0 | doubtful |
| Ramesh Kumar | Villianur Mohit Kings | 204 | 10 | 6.88 | 61.9 | 0 | 0 | doubtful |
| Satyajeet Bachhav | Ratnagiri Jets | 142 | 9 | 6.34 | 56.0 | 0 | 0 | doubtful |
| Shubham Mishra | Kanpur Superstars | 198 | 12 | 7.21 | 49.2 | 0 | 0 | doubtful |

## Link quality
| Link | Meaning | All 2261 Cricbuzz players | On the board (874) |
|---|---|---|---|
| strong | same cricbuzz_id in state leagues and SMAT 2025 | 250 players appear in both | 199 |
| reviewed | hand-checked override in `reference/cricbuzz_player_links.csv` (spelling differs); never flagged doubtful | 6 | 6 |
| team_checked | Cricsheet name taken from the SMAT 2025 team-scoped link | 244 | 82 |
| name_only | Cricsheet name from the scraper or a unique-name guess, passed the checks | 232 | 126 |
| doubtful | name-only link that failed a check; Cricsheet rows withheld, ipl_capped = unknown | 306 | 129 |
| none | no Cricsheet candidate | 1473 | 531 |

Checks on name-only links: (1) another Cricbuzz player claims the same Cricsheet name; (2) initials disagree; (3) Cricbuzz profile is new (id of 1,000,000 or more) but the Cricsheet player debuted before 2022; (4) the Cricsheet player's last match is 3+ years before the Cricbuzz player's first. Example: state-league "Sahaj Dhawan" was tied to "S Dhawan" (Shikhar Dhawan); check 3 flags it.
The checks are heuristics, so a flagged link can still be right and an unflagged name-only link can still be wrong; `(n)`-style caution applies to every name_only row.

## Caveats
- Name-only links are guesses by name; use `cricket scouting profile` and look at the Cricsheet rows before acting. Doubtful rows are hidden by default (`--doubtful` shows them).
- Cricbuzz scorecards are used, so the 55 matches without ball-by-ball do not matter here. Scorecards have no balls-faced for some tailenders (balls 0) and no super overs.
- A player with two Cricbuzz ids (spelling variants) appears twice on the board; ids are not merged by name.
- State-league strength differs a lot (for example Delhi / Tamil Nadu versus Pondicherry / Chhattisgarh). Scores are pooled and not league-adjusted. Samples are small (one season each for most leagues).
- Only IPL, SMAT (2016-2024 in the DB) and men's T20I come from Cricsheet; other leagues in the DB (PSL, BBL, ...) are not in the profile.
- Bengal Pro T20 and UP T20 2026 are not on Cricbuzz, so they are absent.
- **SMAT 2026 (the live test) is excluded**: its folder and `fresh3` data were never read.
