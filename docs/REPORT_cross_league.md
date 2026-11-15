# Cross-league scouting board (state T20 leagues + SMAT 2025 + IPL)

Built by `src/cricket_analytics/scouting/profile.py` (`cricket scouting board`, `cricket scouting profile "<name or id>"`). Data: Cricbuzz scorecards for
14 state leagues (all editions we scraped) and SMAT 2025-26; IPL, earlier SMAT and T20I from the Cricsheet DB. Nothing dated 2026-10-15 or later is used.
Board = 874 players with 100+ balls faced or bowled in the state leagues.

## How to read this
- **bat_score** = state-league runs minus what an average state-league batter scores off the same balls. **bowl_score** = runs saved against the average economy over the bowler's own overs. Both are in runs; state leagues are pooled (no per-league adjustment).
- **ipl_capped**: `yes` = linked Cricsheet player has an IPL match; `no` = linked and no IPL match; `unknown` = no usable link (never guessed). "Capped" means played an IPL match in our DB (squad-only or impact-sub-unused players are not seen).
- **ipl_link**: how the Cricbuzz player was tied to a Cricsheet player (see below).

## Top 15 uncapped batters (ipl_capped = no, by bat_score)
| name | team | state_inns | state_runs | state_balls | state_avg | state_sr | bat_score | smat_runs | smat_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|---|---|
| Ajay Rohera | Jabalpur Royal Lions | 23 | 1122 | 667 | 53.4 | 168.2 | 192.4 | 66 | 45 | name_only |
| Luvnith Sisodia | Shivamogga Yodhas | 45 | 1327 | 831 | 30.9 | 159.7 | 168.9 | 0 | 0 | name_only |
| LR Chethan | Mysore Warriors | 44 | 1362 | 866 | 33.2 | 157.3 | 155.1 | 0 | 0 | name_only |
| Suraj Ahuja | Coastal Kings Mangaluru | 44 | 1045 | 643 | 34.8 | 162.5 | 148.9 | 106 | 78 | team_checked |
| Ankit Rajesh Kumar | West Delhi Lions | 18 | 381 | 206 | 21.2 | 185.0 | 93.9 | 448 | 260 | team_checked |
| Salman Nizar | Kerala | 6 | 296 | 153 | 98.7 | 193.5 | 82.8 | 52 | 64 | team_checked |
| Dev Lakra | Purani Dilli 6 | 20 | 512 | 310 | 26.9 | 165.2 | 80.0 | 0 | 0 | name_only |
| Tripuresh Singh | Chambal Ghariyals | 17 | 330 | 180 | 30.0 | 183.3 | 79.1 | 39 | 16 | team_checked |
| Kunnummal | Kerala | 11 | 337 | 186 | 30.6 | 181.2 | 77.8 | 247 | 169 | team_checked |
| Aman Bhadoriya | Chambal Ghariyals | 17 | 256 | 128 | 36.6 | 200.0 | 77.6 | 0 | 0 | name_only |
| Rohan Patil | Kalyani Bengaluru Blasters | 43 | 1092 | 730 | 28.7 | 149.6 | 74.6 | 0 | 0 | name_only |
| Ashwin Hebbar | Andhra | 7 | 315 | 179 | 45.0 | 176.0 | 65.5 | 251 | 179 | team_checked |
| Ajay Jadav Mandal | Chhattisgarh | 6 | 295 | 169 | 73.8 | 174.6 | 59.5 | 40 | 37 | team_checked |
| Aditya Garhwal | Puducherry | 19 | 472 | 298 | 24.8 | 158.4 | 56.7 | 50 | 31 | name_only |
| Krishna Pandey | Puducherry | 10 | 319 | 191 | 39.9 | 167.0 | 52.8 | 22 | 25 | name_only |

## Top 15 uncapped bowlers (ipl_capped = no, by bowl_score)
| name | team | state_bowl_balls | state_wkts | state_econ | bowl_score | smat_wkts | smat_bowl_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|
| Shubhang Hegde | Kalyani Bengaluru Blasters | 994 | 56 | 7.04 | 275.9 | 6 | 96 | team_checked |
| Vasuki Koushik | Coastal Kings Mangaluru | 787 | 37 | 7.69 | 132.6 | 10 | 144 | name_only |
| Sagar Udeshi | Puducherry | 300 | 12 | 7.18 | 76.2 | 0 | 12 | team_checked |
| Aparajith | Chepauk Super Gillies | 234 | 9 | 6.77 | 75.4 | 0 | 0 | name_only |
| Rahil Shah | SKM Salem Spartans | 527 | 29 | 7.89 | 71.5 | 0 | 0 | name_only |
| Sonu Yadav | Nellai Royal Kings | 658 | 42 | 8.19 | 56.5 | 7 | 126 | team_checked |
| Shiva Singh | Kashi Rudras | 240 | 6 | 7.33 | 55.2 | 0 | 0 | name_only |
| Ajay Jadav Mandal | Chhattisgarh | 102 | 11 | 5.47 | 55.0 | 8 | 132 | team_checked |
| Yuvraj Chudasama | Saurashtra | 114 | 5 | 6.0 | 51.4 | 0 | 17 | team_checked |
| Aman Bhadoriya | Chambal Ghariyals | 330 | 20 | 7.85 | 46.7 | 0 | 0 | name_only |
| Suboth Bhati | Dindigul Dragons | 337 | 23 | 7.92 | 43.9 | 0 | 0 | name_only |
| Lalith Mohan | Vijayawada Sunshiners | 132 | 4 | 6.82 | 41.5 | 0 | 0 | name_only |
| Dharmendrasinh Jadeja | Saurashtra | 114 | 6 | 6.53 | 41.4 | 4 | 75 | team_checked |
| Atharva Ankolekar | Eagle Thane Strikers | 222 | 10 | 7.59 | 41.0 | 9 | 193 | team_checked |
| Shivam Shukla | Indore Pink Panthers | 337 | 26 | 7.99 | 39.9 | 17 | 205 | team_checked |

## Strong numbers but IPL status unknown (could be capped; check by hand), top 10 each
| name | team | state_inns | state_runs | state_balls | state_avg | state_sr | bat_score | smat_runs | smat_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|---|---|
| Tushar Raheja | IDream Tiruppur Tamizhans | 33 | 1429 | 869 | 47.6 | 164.4 | 217.9 | 151 | 92 |  |
| Abhishek Pathak | Bundelkhand Bulls | 14 | 509 | 216 | 36.4 | 235.6 | 208.0 | 13 | 9 |  |
| Mohammed Taha | Hubli Tigers | 44 | 1288 | 793 | 31.4 | 162.4 | 182.8 | 0 | 0 | doubtful |
| Prabhsimran Singh | Jalandhar Warriors | 9 | 575 | 286 | 82.1 | 201.0 | 176.4 | 233 | 147 |  |
| Shahrukh Khan | Vida Kovai Kings | 34 | 788 | 448 | 31.5 | 175.9 | 163.7 | 18 | 24 |  |
| Parth Chaudhary | Gwalior Cheetahs | 14 | 675 | 370 | 48.2 | 182.4 | 159.4 | 0 | 0 |  |
| Siddharth Joon | Central Delhi Kings | 20 | 477 | 242 | 25.1 | 197.1 | 139.7 | 0 | 0 |  |
| Sharath BR | Gulbarga Mystics | 34 | 850 | 513 | 26.6 | 165.7 | 135.1 | 103 | 50 |  |
| Ritik Tada | Jabalpur Royal Lions | 15 | 436 | 224 | 43.6 | 194.6 | 123.8 | 0 | 0 |  |
| Ankush Singh | Chambal Ghariyals | 17 | 514 | 286 | 34.3 | 179.7 | 115.4 | 101 | 68 | doubtful |

| name | team | state_bowl_balls | state_wkts | state_econ | bowl_score | smat_wkts | smat_bowl_balls | ipl_link |
|---|---|---|---|---|---|---|---|---|
| Jhathavedh Subramanyan | Vida Kovai Kings | 714 | 37 | 6.87 | 218.7 | 0 | 0 |  |
| Varun Chakaravarthy | Dindigul Dragons | 690 | 36 | 6.91 | 205.9 | 2 | 96 |  |
| M Silambarasan | Chepauk Super Gillies | 569 | 30 | 6.72 | 188.4 | 0 | 0 |  |
| Ravisrinivasan Sai Kishore | IDream Tiruppur Tamizhans | 564 | 30 | 6.84 | 175.2 | 1 | 102 |  |
| Shreesha Achar | Shivamogga Yodhas | 666 | 37 | 7.27 | 159.1 | 0 | 0 |  |
| Tejas Baroka | Central Delhi Kings | 450 | 23 | 7.07 | 122.8 | 0 | 0 | doubtful |
| Prithviraj Shekhawat | Coastal Kings Mangaluru | 480 | 20 | 7.3 | 112.3 | 0 | 0 |  |
| Satvik Deswal | Ossudu Accord Warriors | 240 | 14 | 5.9 | 112.2 | 0 | 0 |  |
| Manan Bhardwaj | West Delhi Lions | 399 | 25 | 7.05 | 109.8 | 0 | 0 |  |
| S Ajith Ram | SKM Salem Spartans | 455 | 21 | 7.42 | 97.0 | 0 | 0 |  |

## Link quality
| Link | Meaning | All 2261 Cricbuzz players | On the board (874) |
|---|---|---|---|
| strong | same cricbuzz_id in state leagues and SMAT 2025 | 250 players appear in both | 199 |
| team_checked | Cricsheet name taken from the SMAT 2025 team-scoped link | 244 | 82 |
| name_only | Cricsheet name from the scraper or a unique-name guess, passed the checks | 232 | 126 |
| doubtful | name-only link that failed a check; Cricsheet rows withheld, ipl_capped = unknown | 307 | 130 |
| none | no Cricsheet candidate | 1478 | 536 |

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
