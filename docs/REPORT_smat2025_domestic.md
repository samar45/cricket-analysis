# SMAT 2025-26 domestic scouting report (IPL auction lens)

Source: Cricbuzz scorecards, all 141 matches (126 Elite, 15 Plate), 26 Nov - 18 Dec 2025.
Tables built by `src/cricket_analytics/scouting/smat2025.py`; CSVs: `data/external/cricbuzz/smat2025/scouting_batters.csv`, `scouting_bowlers.csv`.
Not used: ball-by-ball (only 36 of 141 matches have it), so no dot-ball % is shown. VJD matches are in the scorecards as played.

## How to read this
- **Score (batters)** = runs minus what an average SMAT batter would score off the same balls (league SR 136.1). +50 means 50 runs more than average from those balls.
- **Score (bowlers)** = runs saved against the league economy (8.46) over the player's own overs. Wickets are not in the score; they are shown next to it.
- **Position band** (batters): median batting position, 1-3 top 3, 4-5 middle, 6+ finisher.
- **IPL status / T20I** come from our database (Cricsheet). T20I "uncapped" means no men's T20I match in the DB; ODI or Test caps are not covered. "unknown" = the name could not be matched, so nothing is guessed.
- `*` after a name = Plate group player (weaker opposition). `(n)` = matched to a Cricsheet player by name only (not by team history), so a wrong match is possible.
- **IPL estimate columns** (`ipl_sr_est`, `ipl_econ_est`): SMAT figure times a factor from `src/cricket_analytics/models/data/league_translation.csv` (measured in this project: players with 200+ balls in both SMAT and the IPL, 57 batters / 59 bowlers). Batter runs-per-ball factor 0.981 (95% range 0.960-1.004, so close to no change); bowler runs-per-ball factor 1.205 (1.172-1.243, IPL economy is about 20% worse). Those players already made the IPL, so the factors are a rough guide, and they are not applied to the ranking scores, which are raw.

## Counts
| | Batters (100+ balls) | Bowlers (12+ overs) |
|---|---|---|
| In table | 115 | 196 |
| Uncapped (matched, no T20I) | 60 | 113 |
| Capped (T20I in DB) | 17 | 24 |
| Name not matched (status unknown) | 38 | 59 |
| Plate players | 11 | 25 |

## Top 15 uncapped batters (by score)
| player | team | inns | runs | balls | avg | sr | boundary_pct | fifties | hundreds | band | ipl_sr_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ankit Kumar | Haryana | 11 | 448 | 260 | 44.8 | 172.3 | 27.3 | 5 | 0 | top 3 | 169.0 | 94.1 | uncapped | no IPL record | 2019 2023 |
| Anmolpreet Singh | Punjab | 10 | 349 | 199 | 34.9 | 175.4 | 25.6 | 2 | 0 | top 3 | 172.1 | 78.1 | uncapped | 9 m, last 2024 | 2018 2019 2021 2022 2023 |
| Virat Singh | Jharkhand | 11 | 382 | 225 | 42.4 | 169.8 | 23.1 | 4 | 0 | top 3 | 166.6 | 75.8 | uncapped | 2 m, last 2021 | 2016 2018 2019 2021 |
| Kumar Kushagra | Jharkhand | 10 | 422 | 261 | 60.3 | 161.7 | 21.5 | 4 | 0 | top 3 | 158.6 | 66.8 | uncapped | 4 m, last 2026 | 2021 |
| Tanmay Agarwal (n) | Hyderabad | 10 | 320 | 186 | 35.6 | 172.0 | 27.4 | 3 | 0 | top 3 | 168.7 | 66.8 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Karan Lal | Bengal | 7 | 219 | 112 | 31.3 | 195.5 | 31.2 | 0 | 1 | top 3 | 191.8 | 66.6 | uncapped | no IPL record | 2021 2023 2024 |
| Ayush Mhatre (n) | Mumbai | 6 | 325 | 195 | 108.3 | 166.7 | 23.1 | 1 | 2 | top 3 | 163.5 | 59.6 | uncapped | 13 m, last 2026 | - |
| M Murasingh | Tripura | 7 | 277 | 161 | 46.2 | 172.0 | 19.9 | 2 | 0 | finisher | 168.7 | 57.9 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Nishant Sindhu | Haryana | 11 | 303 | 182 | 33.7 | 166.5 | 23.6 | 2 | 0 | top 3 | 163.3 | 55.3 | uncapped | 5 m, last 2026 | 2022 2023 |
| Abishek Porel | Bengal | 7 | 225 | 128 | 32.1 | 175.8 | 29.7 | 2 | 0 | top 3 | 172.5 | 50.8 | uncapped | 33 m, last 2026 | 2023 2024 |
| Ravi Singh (n) | Railways | 7 | 218 | 126 | 36.3 | 173.0 | 26.2 | 1 | 0 | finisher | 169.7 | 46.5 | uncapped | 1 m, last 2026 | - |
| Anukul Roy (n) | Jharkhand | 11 | 303 | 189 | 60.6 | 160.3 | 20.1 | 1 | 0 | middle | 157.3 | 45.8 | uncapped | 24 m, last 2026 | 2019 2021 |
| Lalit Yadav (n) | Goa | 7 | 275 | 175 | 137.5 | 157.1 | 20.0 | 2 | 0 | middle | 154.1 | 36.8 | uncapped | 25 m, last 2024 | 2018 2019 2021 2022 2023 |
| Prerak Mankad (n) | Saurashtra | 7 | 175 | 102 | 25.0 | 171.6 | 28.4 | 2 | 0 | top 3 | 168.3 | 36.2 | uncapped | 6 m, last 2023 | 2016 2018 2019 2021 2022 2024 |
| Kunal Chandela | Uttarakhand | 7 | 350 | 232 | 50.0 | 150.9 | 21.6 | 4 | 0 | top 3 | 148.0 | 34.2 | uncapped | no IPL record | 2021 2022 |

## Top 15 uncapped bowlers (by score)
| player | team | inns | overs | wkts | econ | avg | sr | ipl_econ_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Kumar Kartikeya | Madhya Pradesh | 9 | 34.0 | 5 | 6.38 | 43.4 | 40.8 | 7.69 | 70.6 | uncapped | 16 m, last 2025 | 2019 2021 2022 2023 2024 |
| Palzor Tamang * | Sikkim | 6 | 23.0 | 9 | 5.65 | 14.4 | 15.3 | 6.81 | 64.5 | uncapped | no IPL record | 2019 2021 |
| Kranthi Kumar * | Sikkim | 6 | 21.5 | 10 | 5.63 | 12.3 | 13.1 | 6.78 | 61.7 | uncapped | no IPL record | 2021 |
| Avinov Choudhury (n) | Assam | 7 | 27.0 | 10 | 6.19 | 16.7 | 16.2 | 7.46 | 61.4 | uncapped | no IPL record | 2022 2023 |
| Harsh Dubey | Vidarbha | 7 | 26.0 | 8 | 6.35 | 20.6 | 19.5 | 7.65 | 54.9 | uncapped | 11 m, last 2026 | 2021 2022 2024 |
| Ravi Kiran | Chhattisgarh | 7 | 25.0 | 9 | 6.4 | 17.8 | 16.7 | 7.71 | 51.5 | uncapped | no IPL record | 2016 2018 2019 2021 2022 |
| Manav Suthar (n) | Rajasthan | 10 | 35.0 | 13 | 7.0 | 18.8 | 16.2 | 8.44 | 51.0 | uncapped | 4 m, last 2026 | 2022 |
| Bishworjit Konthoujam * | Manipur | 5 | 18.4 | 8 | 5.95 | 13.9 | 14.0 | 7.17 | 46.9 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Murugan Ashwin (n) | Jammu and Kashmir | 7 | 24.0 | 7 | 6.54 | 22.4 | 20.6 | 7.88 | 46.0 | uncapped | 44 m, last 2023 | 2016 2018 2019 2021 |
| Prashant Veer (n) | Uttar Pradesh | 7 | 25.0 | 9 | 6.76 | 18.8 | 16.7 | 8.15 | 42.5 | uncapped | 6 m, last 2026 | 2023 |
| Swarajeet Das * | Meghalaya | 5 | 17.4 | 8 | 6.11 | 13.5 | 13.2 | 7.36 | 41.4 | uncapped | no IPL record | 2019 |
| Shivam Shukla | Madhya Pradesh | 10 | 34.1 | 17 | 7.26 | 14.6 | 12.1 | 8.75 | 41.0 | uncapped | no IPL record | 2024 |
| Mukhtar Hussain | Assam | 7 | 27.0 | 15 | 6.96 | 12.5 | 10.8 | 8.39 | 40.4 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Suraj Kashyap | Bihar | 7 | 27.0 | 8 | 7.0 | 23.6 | 20.2 | 8.44 | 39.4 | uncapped | no IPL record | 2021 |
| Arshad Khan | Madhya Pradesh | 5 | 17.0 | 10 | 6.18 | 10.5 | 10.2 | 7.45 | 38.8 | uncapped | 24 m, last 2026 | 2023 |

## Breakouts: uncapped, no IPL record, strong numbers
Batters with score of 25 or more (11):

| player | team | inns | runs | balls | avg | sr | boundary_pct | fifties | hundreds | band | ipl_sr_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ankit Kumar | Haryana | 11 | 448 | 260 | 44.8 | 172.3 | 27.3 | 5 | 0 | top 3 | 169.0 | 94.1 | uncapped | no IPL record | 2019 2023 |
| Tanmay Agarwal (n) | Hyderabad | 10 | 320 | 186 | 35.6 | 172.0 | 27.4 | 3 | 0 | top 3 | 168.7 | 66.8 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Karan Lal | Bengal | 7 | 219 | 112 | 31.3 | 195.5 | 31.2 | 0 | 1 | top 3 | 191.8 | 66.6 | uncapped | no IPL record | 2021 2023 2024 |
| M Murasingh | Tripura | 7 | 277 | 161 | 46.2 | 172.0 | 19.9 | 2 | 0 | finisher | 168.7 | 57.9 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Kunal Chandela | Uttarakhand | 7 | 350 | 232 | 50.0 | 150.9 | 21.6 | 4 | 0 | top 3 | 148.0 | 34.2 | uncapped | no IPL record | 2021 2022 |
| Mohit Ahlawat | Services | 7 | 174 | 104 | 29.0 | 167.3 | 26.9 | 0 | 0 | top 3 | 164.1 | 32.4 | uncapped | no IPL record | 2019 2021 |
| Pragnay Reddy (n) | Hyderabad | 10 | 244 | 156 | 34.9 | 156.4 | 23.7 | 1 | 0 | top 3 | 153.4 | 31.7 | uncapped | no IPL record | 2021 2022 |
| Kranthi Kumar * | Sikkim | 6 | 185 | 114 | 61.7 | 162.3 | 21.9 | 2 | 0 | middle | 159.2 | 29.8 | uncapped | no IPL record | 2021 |
| Ekant Sen (n) | Himachal Pradesh | 7 | 283 | 187 | 40.4 | 151.3 | 21.9 | 2 | 0 | top 3 | 148.4 | 28.5 | uncapped | no IPL record | 2019 2021 2022 |
| Abhimanyu Easwaran (n) | Bengal | 7 | 266 | 175 | 44.3 | 152.0 | 21.1 | 1 | 1 | top 3 | 149.1 | 27.8 | uncapped | no IPL record | 2019 2021 2023 |
| Aman Mokhade (n) | Vidarbha | 7 | 206 | 131 | 34.3 | 157.3 | 22.1 | 3 | 0 | top 3 | 154.3 | 27.7 | uncapped | no IPL record | 2022 |

Bowlers with 15 or more runs saved (23):

| player | team | inns | overs | wkts | econ | avg | sr | ipl_econ_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Palzor Tamang * | Sikkim | 6 | 23.0 | 9 | 5.65 | 14.4 | 15.3 | 6.81 | 64.5 | uncapped | no IPL record | 2019 2021 |
| Kranthi Kumar * | Sikkim | 6 | 21.5 | 10 | 5.63 | 12.3 | 13.1 | 6.78 | 61.7 | uncapped | no IPL record | 2021 |
| Avinov Choudhury (n) | Assam | 7 | 27.0 | 10 | 6.19 | 16.7 | 16.2 | 7.46 | 61.4 | uncapped | no IPL record | 2022 2023 |
| Ravi Kiran | Chhattisgarh | 7 | 25.0 | 9 | 6.4 | 17.8 | 16.7 | 7.71 | 51.5 | uncapped | no IPL record | 2016 2018 2019 2021 2022 |
| Bishworjit Konthoujam * | Manipur | 5 | 18.4 | 8 | 5.95 | 13.9 | 14.0 | 7.17 | 46.9 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Swarajeet Das * | Meghalaya | 5 | 17.4 | 8 | 6.11 | 13.5 | 13.2 | 7.36 | 41.4 | uncapped | no IPL record | 2019 |
| Shivam Shukla | Madhya Pradesh | 10 | 34.1 | 17 | 7.26 | 14.6 | 12.1 | 8.75 | 41.0 | uncapped | no IPL record | 2024 |
| Mukhtar Hussain | Assam | 7 | 27.0 | 15 | 6.96 | 12.5 | 10.8 | 8.39 | 40.4 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Suraj Kashyap | Bihar | 7 | 27.0 | 8 | 7.0 | 23.6 | 20.2 | 8.44 | 39.4 | uncapped | no IPL record | 2021 |
| B Lalnunfela * | Mizoram | 6 | 19.0 | 11 | 6.47 | 11.2 | 10.4 | 7.8 | 37.7 | uncapped | no IPL record | 2021 |
| Codanda Ajit Karthik * (n) | Mizoram | 6 | 22.0 | 5 | 6.77 | 29.8 | 26.4 | 8.16 | 37.1 | uncapped | no IPL record | 2021 |
| Akash Choudhary * | Meghalaya | 5 | 20.0 | 6 | 6.7 | 22.3 | 20.0 | 8.07 | 35.2 | uncapped | no IPL record | 2019 2021 2023 |
| Abid Mushtaq (n) | Jammu and Kashmir | 6 | 21.1 | 2 | 6.85 | 72.5 | 63.5 | 8.25 | 34.0 | uncapped | no IPL record | 2019 2021 2023 |
| Nagwaswalla | Gujarat | 7 | 25.5 | 11 | 7.35 | 17.3 | 14.1 | 8.86 | 28.5 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Rajesh Mohanty | Odisha | 7 | 25.0 | 12 | 7.4 | 15.4 | 12.5 | 8.92 | 26.5 | uncapped | no IPL record | 2019 2021 |
| Darshan Misal | Goa | 7 | 25.0 | 5 | 7.44 | 37.2 | 30.0 | 8.97 | 25.5 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Deepraj Gaonkar | Goa | 7 | 24.0 | 10 | 7.46 | 17.9 | 14.4 | 8.99 | 24.0 | uncapped | no IPL record | 2016 2019 2021 2022 2023 |
| Manisankar Murasingh | Tripura | 7 | 26.5 | 6 | 7.6 | 34.0 | 26.8 | 9.16 | 23.0 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Avneesh Sudha | Uttarakhand | 4 | 15.0 | 4 | 6.93 | 26.0 | 22.5 | 8.35 | 22.9 | uncapped | no IPL record | 2019 2021 2022 |
| MD Nidheesh | Kerala | 7 | 24.2 | 7 | 7.56 | 26.3 | 20.9 | 9.11 | 21.8 | uncapped | no IPL record | 2019 2021 |
| Rongsen Jonathan * | Nagaland | 5 | 17.5 | 8 | 7.35 | 16.4 | 13.4 | 8.86 | 19.8 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Ram Gurung * | Meghalaya | 5 | 17.0 | 2 | 7.53 | 64.0 | 51.0 | 9.07 | 15.8 | uncapped | no IPL record | 2021 2023 |
| Lee Yong Lepcha * | Sikkim | 6 | 16.0 | 2 | 7.5 | 60.0 | 48.0 | 9.04 | 15.3 | uncapped | no IPL record | 2019 2021 |

## Strong numbers but status unknown (name not matched, top 10 each)
These could be capped or have IPL history; check by hand before acting.

| player | team | inns | runs | balls | avg | sr | boundary_pct | fifties | hundreds | band | ipl_sr_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Salil Arora | Punjab | 8 | 358 | 180 | 71.6 | 198.9 | 28.3 | 1 | 1 | middle | 195.1 | 113.0 | unknown | unknown | unknown |
| Sarfaraz Khan | Mumbai | 7 | 329 | 162 | 65.8 | 203.1 | 34.6 | 3 | 1 | top 3 | 199.2 | 108.5 | unknown | unknown | unknown |
| K Priyojit Singh * | Manipur | 5 | 239 | 117 | 59.8 | 204.3 | 29.1 | 2 | 1 | middle | 200.4 | 79.8 | unknown | unknown | unknown |
| Samant Jakhar | Haryana | 11 | 198 | 111 | 24.8 | 178.4 | 26.1 | 1 | 0 | finisher | 175.0 | 46.9 | unknown | unknown | unknown |
| Nischal * | Nagaland | 4 | 181 | 103 | 45.2 | 175.7 | 26.2 | 0 | 1 | top 3 | 172.4 | 40.8 | unknown | unknown | unknown |
| Mridul Surroch | Himachal Pradesh | 7 | 204 | 125 | 40.8 | 163.2 | 20.8 | 2 | 0 | finisher | 160.1 | 33.9 | unknown | unknown | unknown |
| Yashvardhan Dalal | Haryana | 11 | 398 | 268 | 49.8 | 148.5 | 19.0 | 5 | 0 | middle | 145.7 | 33.2 | unknown | unknown | unknown |
| Prabhsimran | Punjab | 10 | 233 | 147 | 23.3 | 158.5 | 26.5 | 2 | 0 | top 3 | 155.5 | 32.9 | unknown | unknown | unknown |
| Arsh Ranga | Haryana | 11 | 284 | 186 | 25.8 | 152.7 | 23.7 | 1 | 0 | top 3 | 149.8 | 30.8 | unknown | unknown | unknown |
| R Rajkumar | Tamil Nadu | 7 | 167 | 104 | 33.4 | 160.6 | 23.1 | 1 | 0 | finisher | 157.5 | 25.4 | unknown | unknown | unknown |

| player | team | inns | overs | wkts | econ | avg | sr | ipl_econ_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gurinder Singh * | Sikkim | 6 | 23.0 | 11 | 5.09 | 10.6 | 12.5 | 6.13 | 77.5 | unknown | unknown | unknown |
| Vicky Ostwal | Maharashtra | 7 | 27.0 | 7 | 6.44 | 24.9 | 23.1 | 7.76 | 54.4 | unknown | unknown | unknown |
| T Thyagarajan | Hyderabad | 10 | 40.0 | 16 | 7.2 | 18.0 | 15.0 | 8.68 | 50.3 | unknown | unknown | unknown |
| Jalaj Saxena | Maharashtra | 6 | 24.0 | 9 | 6.38 | 17.0 | 16.0 | 7.69 | 50.0 | unknown | unknown | unknown |
| Raj Choudhary | Railways | 7 | 26.3 | 3 | 6.68 | 59.0 | 53.0 | 8.05 | 47.1 | unknown | unknown | unknown |
| Siraj | Hyderabad | 4 | 15.5 | 7 | 5.87 | 13.3 | 13.6 | 7.07 | 40.9 | unknown | unknown | unknown |
| Bailapudi Yeswanth | Andhra | 6 | 21.3 | 4 | 6.6 | 35.5 | 32.2 | 7.95 | 39.9 | unknown | unknown | unknown |
| V Koushik | Goa | 7 | 24.0 | 10 | 6.92 | 16.6 | 14.4 | 8.34 | 37.0 | unknown | unknown | unknown |
| Prithvi Raj Yarra | Andhra | 9 | 34.0 | 12 | 7.47 | 21.2 | 17.0 | 9.0 | 33.6 | unknown | unknown | unknown |
| Milind | Hyderabad | 9 | 34.4 | 17 | 7.5 | 15.3 | 12.2 | 9.04 | 33.2 | unknown | unknown | unknown |

## Full tables
### Batters, 100+ balls
| player | team | inns | runs | balls | avg | sr | boundary_pct | fifties | hundreds | band | ipl_sr_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Ishan Kishan | Jharkhand | 10 | 517 | 262 | 57.4 | 197.3 | 32.1 | 2 | 2 | top 3 | 193.6 | 160.4 | capped (T20I) | 127 m, last 2026 | 2018 2019 2021 |
| Abhishek Sharma | Punjab | 6 | 304 | 122 | 50.7 | 249.2 | 43.4 | 2 | 1 | top 3 | 244.5 | 137.9 | capped (T20I) | 92 m, last 2026 | 2018 2019 2021 2022 2023 |
| Salil Arora | Punjab | 8 | 358 | 180 | 71.6 | 198.9 | 28.3 | 1 | 1 | middle | 195.1 | 113.0 | unknown | unknown | unknown |
| Sarfaraz Khan | Mumbai | 7 | 329 | 162 | 65.8 | 203.1 | 34.6 | 3 | 1 | top 3 | 199.2 | 108.5 | unknown | unknown | unknown |
| Ankit Kumar | Haryana | 11 | 448 | 260 | 44.8 | 172.3 | 27.3 | 5 | 0 | top 3 | 169.0 | 94.1 | uncapped | no IPL record | 2019 2023 |
| K Priyojit Singh * | Manipur | 5 | 239 | 117 | 59.8 | 204.3 | 29.1 | 2 | 1 | middle | 200.4 | 79.8 | unknown | unknown | unknown |
| Anmolpreet Singh | Punjab | 10 | 349 | 199 | 34.9 | 175.4 | 25.6 | 2 | 0 | top 3 | 172.1 | 78.1 | uncapped | 9 m, last 2024 | 2018 2019 2021 2022 2023 |
| Virat Singh | Jharkhand | 11 | 382 | 225 | 42.4 | 169.8 | 23.1 | 4 | 0 | top 3 | 166.6 | 75.8 | uncapped | 2 m, last 2021 | 2016 2018 2019 2021 |
| Kumar Kushagra | Jharkhand | 10 | 422 | 261 | 60.3 | 161.7 | 21.5 | 4 | 0 | top 3 | 158.6 | 66.8 | uncapped | 4 m, last 2026 | 2021 |
| Tanmay Agarwal (n) | Hyderabad | 10 | 320 | 186 | 35.6 | 172.0 | 27.4 | 3 | 0 | top 3 | 168.7 | 66.8 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Karan Lal | Bengal | 7 | 219 | 112 | 31.3 | 195.5 | 31.2 | 0 | 1 | top 3 | 191.8 | 66.6 | uncapped | no IPL record | 2021 2023 2024 |
| Ramandeep Singh | Punjab | 10 | 209 | 107 | 29.9 | 195.3 | 28.0 | 0 | 0 | finisher | 191.6 | 63.4 | capped (T20I) | 27 m, last 2026 | 2021 2022 2023 |
| Ajinkya Rahane (n) | Mumbai | 10 | 391 | 241 | 48.9 | 162.2 | 22.0 | 3 | 0 | top 3 | 159.1 | 63.0 | capped (T20I) | 197 m, last 2026 | 2019 2021 2022 2023 2024 |
| Ayush Mhatre (n) | Mumbai | 6 | 325 | 195 | 108.3 | 166.7 | 23.1 | 1 | 2 | top 3 | 163.5 | 59.6 | uncapped | 13 m, last 2026 | - |
| M Murasingh | Tripura | 7 | 277 | 161 | 46.2 | 172.0 | 19.9 | 2 | 0 | finisher | 168.7 | 57.9 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Devdutt Padikkal | Karnataka | 6 | 309 | 185 | 61.8 | 167.0 | 25.9 | 2 | 1 | top 3 | 163.8 | 57.2 | capped (T20I) | 89 m, last 2026 | 2019 2021 2023 |
| Nishant Sindhu | Haryana | 11 | 303 | 182 | 33.7 | 166.5 | 23.6 | 2 | 0 | top 3 | 163.3 | 55.3 | uncapped | 5 m, last 2026 | 2022 2023 |
| Deepak Hooda (n) | Rajasthan | 10 | 305 | 186 | 38.1 | 164.0 | 23.7 | 3 | 0 | top 3 | 160.9 | 51.8 | capped (T20I) | 107 m, last 2025 | 2016 2018 2019 2021 |
| Abishek Porel | Bengal | 7 | 225 | 128 | 32.1 | 175.8 | 29.7 | 2 | 0 | top 3 | 172.5 | 50.8 | uncapped | 33 m, last 2026 | 2023 2024 |
| Samant Jakhar | Haryana | 11 | 198 | 111 | 24.8 | 178.4 | 26.1 | 1 | 0 | finisher | 175.0 | 46.9 | unknown | unknown | unknown |
| Ravi Singh (n) | Railways | 7 | 218 | 126 | 36.3 | 173.0 | 26.2 | 1 | 0 | finisher | 169.7 | 46.5 | uncapped | 1 m, last 2026 | - |
| Anukul Roy (n) | Jharkhand | 11 | 303 | 189 | 60.6 | 160.3 | 20.1 | 1 | 0 | middle | 157.3 | 45.8 | uncapped | 24 m, last 2026 | 2019 2021 |
| Smaran Ravichandran (n) | Karnataka | 7 | 319 | 201 | 63.8 | 158.7 | 18.4 | 2 | 0 | middle | 155.7 | 45.4 | capped (T20I) | no IPL record | - |
| Nischal * | Nagaland | 4 | 181 | 103 | 45.2 | 175.7 | 26.2 | 0 | 1 | top 3 | 172.4 | 40.8 | unknown | unknown | unknown |
| Vaibhav Suryavanshi (n) | Bihar | 6 | 197 | 117 | 39.4 | 168.4 | 24.8 | 0 | 1 | top 3 | 165.2 | 37.8 | capped (T20I) | 23 m, last 2026 | - |
| Lalit Yadav (n) | Goa | 7 | 275 | 175 | 137.5 | 157.1 | 20.0 | 2 | 0 | middle | 154.1 | 36.8 | uncapped | 25 m, last 2024 | 2018 2019 2021 2022 2023 |
| Prerak Mankad (n) | Saurashtra | 7 | 175 | 102 | 25.0 | 171.6 | 28.4 | 2 | 0 | top 3 | 168.3 | 36.2 | uncapped | 6 m, last 2023 | 2016 2018 2019 2021 2022 2024 |
| Aman Khan (n) | Puducherry | 7 | 236 | 147 | 33.7 | 160.5 | 23.1 | 2 | 0 | middle | 157.5 | 35.9 | capped (T20I) | no IPL record | - |
| Kunal Chandela | Uttarakhand | 7 | 350 | 232 | 50.0 | 150.9 | 21.6 | 4 | 0 | top 3 | 148.0 | 34.2 | uncapped | no IPL record | 2021 2022 |
| Mridul Surroch | Himachal Pradesh | 7 | 204 | 125 | 40.8 | 163.2 | 20.8 | 2 | 0 | finisher | 160.1 | 33.9 | unknown | unknown | unknown |
| Yashvardhan Dalal | Haryana | 11 | 398 | 268 | 49.8 | 148.5 | 19.0 | 5 | 0 | middle | 145.7 | 33.2 | unknown | unknown | unknown |
| Prabhsimran | Punjab | 10 | 233 | 147 | 23.3 | 158.5 | 26.5 | 2 | 0 | top 3 | 155.5 | 32.9 | unknown | unknown | unknown |
| Mohit Ahlawat | Services | 7 | 174 | 104 | 29.0 | 167.3 | 26.9 | 0 | 0 | top 3 | 164.1 | 32.4 | uncapped | no IPL record | 2019 2021 |
| Pragnay Reddy (n) | Hyderabad | 10 | 244 | 156 | 34.9 | 156.4 | 23.7 | 1 | 0 | top 3 | 153.4 | 31.7 | uncapped | no IPL record | 2021 2022 |
| Arsh Ranga | Haryana | 11 | 284 | 186 | 25.8 | 152.7 | 23.7 | 1 | 0 | top 3 | 149.8 | 30.8 | unknown | unknown | unknown |
| Jehu Anderson * | Mizoram | 6 | 175 | 106 | 35.0 | 165.1 | 25.5 | 1 | 0 | top 3 | 162.0 | 30.7 | capped (T20I) | no IPL record | 2023 |
| Kranthi Kumar * | Sikkim | 6 | 185 | 114 | 61.7 | 162.3 | 21.9 | 2 | 0 | middle | 159.2 | 29.8 | uncapped | no IPL record | 2021 |
| Ekant Sen (n) | Himachal Pradesh | 7 | 283 | 187 | 40.4 | 151.3 | 21.9 | 2 | 0 | top 3 | 148.4 | 28.5 | uncapped | no IPL record | 2019 2021 2022 |
| Prithvi Shaw (n) | Maharashtra | 7 | 183 | 114 | 26.1 | 160.5 | 28.1 | 2 | 0 | top 3 | 157.5 | 27.8 | capped (T20I) | 79 m, last 2024 | 2019 2021 2022 2024 |
| Abhimanyu Easwaran (n) | Bengal | 7 | 266 | 175 | 44.3 | 152.0 | 21.1 | 1 | 1 | top 3 | 149.1 | 27.8 | uncapped | no IPL record | 2019 2021 2023 |
| Aman Mokhade (n) | Vidarbha | 7 | 206 | 131 | 34.3 | 157.3 | 22.1 | 3 | 0 | top 3 | 154.3 | 27.7 | uncapped | no IPL record | 2022 |
| Robin Minz (n) | Jharkhand | 11 | 166 | 102 | 27.7 | 162.7 | 19.6 | 1 | 0 | middle | 159.6 | 27.2 | uncapped | 4 m, last 2026 | - |
| R Rajkumar | Tamil Nadu | 7 | 167 | 104 | 33.4 | 160.6 | 23.1 | 1 | 0 | finisher | 157.5 | 25.4 | unknown | unknown | unknown |
| Naman Dhir | Punjab | 8 | 235 | 154 | 33.6 | 152.6 | 18.2 | 2 | 0 | middle | 149.7 | 25.4 | capped (T20I) | 33 m, last 2026 | 2023 |
| Ruchit Ahir | Saurashtra | 7 | 163 | 102 | 40.8 | 159.8 | 18.6 | 0 | 0 | finisher | 156.8 | 24.2 | uncapped | no IPL record | 2024 |
| Priyansh Arya | Delhi | 7 | 197 | 127 | 28.1 | 155.1 | 22.0 | 1 | 0 | top 3 | 152.2 | 24.1 | uncapped | 31 m, last 2026 | 2021 2023 2024 |
| Nitish Rana | Delhi | 7 | 274 | 184 | 45.7 | 148.9 | 19.6 | 2 | 0 | top 3 | 146.1 | 23.6 | capped (T20I) | 123 m, last 2026 | 2016 2018 2019 2021 2022 2023 2024 |
| Pukhraj Mann (n) | Himachal Pradesh | 7 | 170 | 108 | 24.3 | 157.4 | 21.3 | 1 | 0 | middle | 154.4 | 23.0 | uncapped | no IPL record | 2022 |
| Vishvaraj Jadeja | Saurashtra | 7 | 235 | 157 | 33.6 | 149.7 | 21.7 | 2 | 0 | top 3 | 146.9 | 21.3 | uncapped | no IPL record | 2018 2021 2022 2023 2024 |
| Sai Sudharsan | Tamil Nadu | 6 | 192 | 126 | 38.4 | 152.4 | 19.0 | 1 | 1 | top 3 | 149.5 | 20.5 | unknown | unknown | unknown |
| Shubham Garhwal | Rajasthan | 8 | 168 | 109 | 21.0 | 154.1 | 25.7 | 1 | 0 | top 3 | 151.2 | 19.6 | unknown | unknown | unknown |
| Abhinav Tejrana | Goa | 7 | 179 | 118 | 25.6 | 151.7 | 21.2 | 2 | 0 | top 3 | 148.8 | 18.4 | unknown | unknown | unknown |
| Kunnummal | Kerala | 7 | 247 | 169 | 41.2 | 146.2 | 20.7 | 1 | 1 | top 3 | 143.4 | 17.0 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Yash Dhull (n) | Delhi | 7 | 261 | 180 | 37.3 | 145.0 | 20.0 | 2 | 0 | top 3 | 142.2 | 16.0 | uncapped | 3 m, last 2023 | 2022 2023 2024 |
| N Jagadeesan | Tamil Nadu | 7 | 191 | 129 | 31.8 | 148.1 | 17.1 | 1 | 0 | middle | 145.3 | 15.4 | uncapped | 10 m, last 2023 | 2018 2019 2021 2023 |
| Dhruv Shorey (n) | Vidarbha | 6 | 206 | 141 | 51.5 | 146.1 | 18.4 | 2 | 0 | middle | 143.3 | 14.1 | uncapped | 2 m, last 2019 | 2016 2018 2019 2021 |
| Kishan Lyngdoh * | Meghalaya | 5 | 214 | 149 | 53.5 | 143.6 | 21.5 | 1 | 1 | top 3 | 140.9 | 11.2 | uncapped | no IPL record | 2021 |
| Suyash Prabhudessai (n) | Goa | 7 | 211 | 148 | 52.8 | 142.6 | 14.9 | 3 | 0 | middle | 139.9 | 9.6 | uncapped | 10 m, last 2024 | 2019 2021 2022 2023 |
| Atharva Taide | Vidarbha | 7 | 180 | 126 | 25.7 | 142.9 | 23.0 | 2 | 0 | top 3 | 140.2 | 8.5 | uncapped | 10 m, last 2025 | 2019 2021 2022 2024 |
| Aanjaneya Suryavanshi | Uttarakhand | 5 | 158 | 110 | 39.5 | 143.6 | 18.2 | 2 | 0 | middle | 140.9 | 8.3 | unknown | unknown | unknown |
| Ashwin Hebbar | Andhra | 10 | 251 | 179 | 25.1 | 140.2 | 18.4 | 2 | 0 | top 3 | 137.5 | 7.4 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Vineet Dhankhar | Services | 7 | 157 | 110 | 26.2 | 142.7 | 18.2 | 0 | 0 | middle | 140.0 | 7.3 | unknown | unknown | unknown |
| Harpreet Singh | Madhya Pradesh | 10 | 334 | 240 | 41.8 | 139.2 | 18.8 | 2 | 0 | middle | 136.6 | 7.3 | capped (T20I) | 8 m, last 2024 | 2016 2018 2019 2021 2022 2023 2024 |
| Tripathi | Maharashtra | 5 | 163 | 115 | 54.3 | 141.7 | 17.4 | 1 | 0 | middle | 139.0 | 6.5 | unknown | unknown | unknown |
| Srikar Bharat | Andhra | 10 | 239 | 171 | 23.9 | 139.8 | 21.1 | 1 | 0 | top 3 | 137.1 | 6.3 | unknown | unknown | unknown |
| Suryakumar Yadav | Mumbai | 5 | 165 | 118 | 41.2 | 139.8 | 18.6 | 0 | 0 | middle | 137.1 | 4.4 | unknown | unknown | unknown |
| Amit Rajera * | Sikkim | 6 | 154 | 110 | 30.8 | 140.0 | 20.9 | 0 | 0 | top 3 | 137.3 | 4.3 | unknown | unknown | unknown |
| Yawer Hassan | Jammu and Kashmir | 5 | 157 | 113 | 31.4 | 138.9 | 19.5 | 1 | 0 | top 3 | 136.3 | 3.2 | unknown | unknown | unknown |
| Samson | Kerala | 6 | 233 | 169 | 58.2 | 137.9 | 21.9 | 2 | 0 | top 3 | 135.3 | 3.0 | unknown | unknown | unknown |
| Shivalik Sharma (n) | Baroda | 7 | 177 | 128 | 29.5 | 138.3 | 18.8 | 1 | 0 | top 3 | 135.7 | 2.8 | capped (T20I) | no IPL record | - |
| Nihar Deka | Assam | 7 | 139 | 101 | 23.2 | 137.6 | 13.9 | 1 | 0 | middle | 135.0 | 1.5 | unknown | unknown | unknown |
| Joseph Lalthankhuma * | Mizoram | 6 | 193 | 141 | 64.3 | 136.9 | 12.8 | 0 | 0 | middle | 134.3 | 1.1 | uncapped | no IPL record | 2021 2022 2023 |
| SDNV Prasad | Andhra | 8 | 152 | 111 | 50.7 | 136.9 | 16.2 | 1 | 0 | finisher | 134.3 | 0.9 | unknown | unknown | unknown |
| Rinku Singh | Uttar Pradesh | 7 | 172 | 127 | 24.6 | 135.4 | 17.3 | 1 | 0 | middle | 132.8 | -0.9 | unknown | unknown | unknown |
| Sameer Rizvi | Uttar Pradesh | 7 | 191 | 141 | 27.3 | 135.5 | 18.4 | 1 | 0 | middle | 132.9 | -0.9 | uncapped | 18 m, last 2026 | 2022 2023 2024 |
| Ayush Badoni | Delhi | 7 | 206 | 152 | 29.4 | 135.5 | 15.1 | 1 | 0 | middle | 132.9 | -0.9 | uncapped | 58 m, last 2026 | 2021 2022 2023 2024 |
| Manan Vohra | Chandigarh | 7 | 278 | 205 | 46.3 | 135.6 | 18.0 | 4 | 0 | top 3 | 133.0 | -1.0 | uncapped | 51 m, last 2023 | 2016 2018 2019 2021 2024 |
| Sumit Ghadigaonkar | Assam | 7 | 144 | 107 | 20.6 | 134.6 | 15.9 | 1 | 0 | top 3 | 132.0 | -1.6 | uncapped | no IPL record | 2023 |
| Aryan Juyal | Uttar Pradesh | 7 | 201 | 149 | 33.5 | 134.9 | 19.5 | 2 | 0 | top 3 | 132.3 | -1.8 | uncapped | no IPL record | 2019 2021 2022 2024 |
| Samantray | Odisha | 7 | 177 | 133 | 29.5 | 133.1 | 16.5 | 2 | 0 | middle | 130.6 | -4.0 | unknown | unknown | unknown |
| Aasirwad Swain | Odisha | 4 | 138 | 105 | 69.0 | 131.4 | 13.3 | 1 | 0 | finisher | 128.9 | -4.9 | unknown | unknown | unknown |
| Tanay Thyagarajan (n) | Hyderabad | 10 | 150 | 114 | 25.0 | 131.6 | 16.7 | 1 | 0 | finisher | 129.1 | -5.2 | uncapped | no IPL record | 2018 2021 2022 2023 |
| Aarya Desai | Gujarat | 7 | 188 | 143 | 31.3 | 131.5 | 18.9 | 2 | 0 | top 3 | 129.0 | -6.6 | uncapped | no IPL record | 2023 |
| Shubham Khajuria (n) | Jammu and Kashmir | 6 | 163 | 125 | 27.2 | 130.4 | 16.8 | 0 | 0 | top 3 | 127.9 | -7.1 | uncapped | no IPL record | 2016 2018 2019 2021 2023 |
| Kunal Singh Rathore | Rajasthan | 9 | 141 | 109 | 23.5 | 129.4 | 16.5 | 0 | 0 | finisher | 126.9 | -7.4 | uncapped | 1 m, last 2025 | 2022 |
| Shashwat Rawat | Baroda | 7 | 160 | 123 | 32.0 | 130.1 | 18.7 | 0 | 0 | top 3 | 127.6 | -7.4 | uncapped | no IPL record | 2021 2024 |
| Nakul Sharma | Services | 7 | 162 | 125 | 27.0 | 129.6 | 12.8 | 1 | 0 | finisher | 127.1 | -8.1 | uncapped | no IPL record | 2018 2019 2021 |
| Arjun Azad | Chandigarh | 7 | 142 | 111 | 20.3 | 127.9 | 18.9 | 1 | 0 | top 3 | 125.5 | -9.1 | unknown | unknown | unknown |
| Amandeep Khare | Chhattisgarh | 7 | 261 | 199 | 43.5 | 131.2 | 17.1 | 1 | 0 | top 3 | 128.7 | -9.9 | uncapped | no IPL record | 2018 2019 2021 2022 2023 |
| S Gani | Bihar | 7 | 134 | 106 | 22.3 | 126.4 | 17.9 | 1 | 0 | top 3 | 124.0 | -10.3 | uncapped | no IPL record | 2021 2022 |
| Parth Vats | Haryana | 11 | 151 | 119 | 25.2 | 126.9 | 15.1 | 0 | 0 | finisher | 124.5 | -11.0 | unknown | unknown | unknown |
| Akshat Pandey | Railways | 6 | 130 | 104 | 32.5 | 125.0 | 17.3 | 1 | 0 | finisher | 122.6 | -11.6 | uncapped | no IPL record | 2016 2021 2022 2023 |
| Arshin Kulkarni (n) | Maharashtra | 7 | 225 | 174 | 37.5 | 129.3 | 18.4 | 1 | 0 | top 3 | 126.8 | -11.8 | uncapped | 4 m, last 2026 | - |
| Arpit Subash Bhatewara * | Meghalaya | 5 | 125 | 101 | 25.0 | 123.8 | 17.8 | 1 | 0 | top 3 | 121.4 | -12.5 | unknown | unknown | unknown |
| Innesh Mahajan | Himachal Pradesh | 7 | 154 | 123 | 22.0 | 125.2 | 19.5 | 1 | 0 | top 3 | 122.8 | -13.4 | unknown | unknown | unknown |
| Hanuma Vihari | Tripura | 7 | 151 | 122 | 21.6 | 123.8 | 18.9 | 0 | 0 | top 3 | 121.4 | -15.1 | unknown | unknown | unknown |
| Saurav Chauhan | Gujarat | 7 | 167 | 134 | 41.8 | 124.6 | 14.2 | 1 | 0 | middle | 122.2 | -15.4 | uncapped | 3 m, last 2024 | 2021 2022 2023 |
| Mayank Agarwal (n) | Karnataka | 7 | 135 | 111 | 19.3 | 121.6 | 14.4 | 0 | 0 | top 3 | 119.3 | -16.1 | uncapped | 125 m, last 2025 | 2016 2018 2019 2021 2022 2023 |
| Rahul Buddhi (n) | Hyderabad | 10 | 244 | 192 | 34.9 | 127.1 | 15.6 | 2 | 0 | middle | 124.7 | -17.3 | uncapped | no IPL record | 2021 2022 2023 |
| Sanjeet Desai | Chhattisgarh | 5 | 126 | 106 | 25.2 | 118.9 | 16.0 | 0 | 0 | middle | 116.6 | -18.3 | uncapped | no IPL record | 2021 2022 2023 |
| Ayush Loharuka | Bihar | 7 | 132 | 112 | 22.0 | 117.9 | 13.4 | 0 | 0 | middle | 115.7 | -20.4 | unknown | unknown | unknown |
| Pyla Avinash | Andhra | 8 | 117 | 101 | 16.7 | 115.8 | 14.9 | 0 | 0 | finisher | 113.6 | -20.5 | unknown | unknown | unknown |
| Lomror | Rajasthan | 10 | 270 | 215 | 33.8 | 125.6 | 13.0 | 0 | 0 | middle | 123.2 | -22.6 | unknown | unknown | unknown |
| Sambit S Baral | Odisha | 6 | 135 | 118 | 27.0 | 114.4 | 12.7 | 0 | 0 | middle | 112.2 | -25.6 | unknown | unknown | unknown |
| Qamran Iqbal (n) | Jammu and Kashmir | 6 | 134 | 119 | 22.3 | 112.6 | 16.0 | 1 | 0 | top 3 | 110.5 | -28.0 | uncapped | no IPL record | 2021 2023 |
| K Sai Satwik * | Sikkim | 6 | 201 | 169 | 50.2 | 118.9 | 15.4 | 1 | 0 | top 3 | 116.6 | -29.0 | unknown | unknown | unknown |
| Ricky Bhui (n) | Andhra | 10 | 237 | 196 | 29.6 | 120.9 | 13.3 | 0 | 0 | middle | 118.6 | -29.8 | uncapped | 4 m, last 2024 | 2018 2019 2021 2022 2023 |
| Venkatesh Iyer (n) | Madhya Pradesh | 10 | 211 | 177 | 26.4 | 119.2 | 13.0 | 2 | 0 | finisher | 116.9 | -29.9 | capped (T20I) | 62 m, last 2026 | 2016 2018 2019 2021 2022 2023 2024 |
| Johnson Singh * | Manipur | 5 | 126 | 117 | 31.5 | 107.7 | 11.1 | 1 | 0 | top 3 | 105.7 | -33.2 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Vijay Shankar (n) | Tripura | 7 | 129 | 121 | 18.4 | 106.6 | 12.4 | 1 | 0 | middle | 104.6 | -35.7 | capped (T20I) | 69 m, last 2025 | 2016 2018 2019 2021 2023 |
| Piyush Singh | Bihar | 4 | 115 | 114 | 28.8 | 100.9 | 8.8 | 1 | 0 | top 3 | 99.0 | -40.2 | uncapped | no IPL record | 2019 2022 |
| Harsh Gawali | Madhya Pradesh | 10 | 302 | 253 | 33.6 | 119.4 | 13.8 | 3 | 0 | top 3 | 117.1 | -42.4 | unknown | unknown | unknown |
| Pradyun Saikia | Assam | 6 | 130 | 127 | 32.5 | 102.4 | 12.6 | 0 | 0 | top 3 | 100.5 | -42.9 | unknown | unknown | unknown |
| Akash Raj | Bihar | 5 | 110 | 115 | 22.0 | 95.7 | 10.4 | 0 | 0 | middle | 93.9 | -46.5 | uncapped | no IPL record | 2021 |
| Techi Neri * | Arunachal Pradesh | 4 | 87 | 107 | 21.8 | 81.3 | 6.5 | 0 | 0 | top 3 | 79.8 | -58.6 | uncapped | no IPL record | 2019 2021 2023 |

### Bowlers, 12+ overs
| player | team | inns | overs | wkts | econ | avg | sr | ipl_econ_est | score | t20i | ipl | smat_hist |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Gurinder Singh * | Sikkim | 6 | 23.0 | 11 | 5.09 | 10.6 | 12.5 | 6.13 | 77.5 | unknown | unknown | unknown |
| Saurabh Kumar (n) | Andhra | 9 | 35.0 | 9 | 6.34 | 24.7 | 23.3 | 7.64 | 74.0 | capped (T20I) | no IPL record | 2016 2018 2019 2021 |
| Kumar Kartikeya | Madhya Pradesh | 9 | 34.0 | 5 | 6.38 | 43.4 | 40.8 | 7.69 | 70.6 | uncapped | 16 m, last 2025 | 2019 2021 2022 2023 2024 |
| Palzor Tamang * | Sikkim | 6 | 23.0 | 9 | 5.65 | 14.4 | 15.3 | 6.81 | 64.5 | uncapped | no IPL record | 2019 2021 |
| Kranthi Kumar * | Sikkim | 6 | 21.5 | 10 | 5.63 | 12.3 | 13.1 | 6.78 | 61.7 | uncapped | no IPL record | 2021 |
| Avinov Choudhury (n) | Assam | 7 | 27.0 | 10 | 6.19 | 16.7 | 16.2 | 7.46 | 61.4 | uncapped | no IPL record | 2022 2023 |
| Harsh Dubey | Vidarbha | 7 | 26.0 | 8 | 6.35 | 20.6 | 19.5 | 7.65 | 54.9 | uncapped | 11 m, last 2026 | 2021 2022 2024 |
| Vicky Ostwal | Maharashtra | 7 | 27.0 | 7 | 6.44 | 24.9 | 23.1 | 7.76 | 54.4 | unknown | unknown | unknown |
| Ravi Kiran | Chhattisgarh | 7 | 25.0 | 9 | 6.4 | 17.8 | 16.7 | 7.71 | 51.5 | uncapped | no IPL record | 2016 2018 2019 2021 2022 |
| Manav Suthar (n) | Rajasthan | 10 | 35.0 | 13 | 7.0 | 18.8 | 16.2 | 8.44 | 51.0 | uncapped | 4 m, last 2026 | 2022 |
| T Thyagarajan | Hyderabad | 10 | 40.0 | 16 | 7.2 | 18.0 | 15.0 | 8.68 | 50.3 | unknown | unknown | unknown |
| Jalaj Saxena | Maharashtra | 6 | 24.0 | 9 | 6.38 | 17.0 | 16.0 | 7.69 | 50.0 | unknown | unknown | unknown |
| Sidak Singh (n) | Puducherry | 6 | 21.0 | 9 | 6.1 | 14.2 | 14.0 | 7.35 | 49.6 | capped (T20I) | no IPL record | - |
| Jaydev Unadkat (n) | Saurashtra | 7 | 28.0 | 12 | 6.71 | 15.7 | 14.0 | 8.09 | 48.8 | capped (T20I) | 115 m, last 2026 | 2016 2018 2019 2021 2022 2023 2024 |
| Raj Choudhary | Railways | 7 | 26.3 | 3 | 6.68 | 59.0 | 53.0 | 8.05 | 47.1 | unknown | unknown | unknown |
| Bishworjit Konthoujam * | Manipur | 5 | 18.4 | 8 | 5.95 | 13.9 | 14.0 | 7.17 | 46.9 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Murugan Ashwin (n) | Jammu and Kashmir | 7 | 24.0 | 7 | 6.54 | 22.4 | 20.6 | 7.88 | 46.0 | uncapped | 44 m, last 2023 | 2016 2018 2019 2021 |
| Yash Thakur | Vidarbha | 7 | 26.1 | 18 | 6.8 | 9.9 | 8.7 | 8.19 | 43.3 | capped (T20I) | 22 m, last 2026 | 2019 2021 2022 2024 |
| Prashant Veer (n) | Uttar Pradesh | 7 | 25.0 | 9 | 6.76 | 18.8 | 16.7 | 8.15 | 42.5 | uncapped | 6 m, last 2026 | 2023 |
| Swarajeet Das * | Meghalaya | 5 | 17.4 | 8 | 6.11 | 13.5 | 13.2 | 7.36 | 41.4 | uncapped | no IPL record | 2019 |
| Shivam Shukla | Madhya Pradesh | 10 | 34.1 | 17 | 7.26 | 14.6 | 12.1 | 8.75 | 41.0 | uncapped | no IPL record | 2024 |
| Siraj | Hyderabad | 4 | 15.5 | 7 | 5.87 | 13.3 | 13.6 | 7.07 | 40.9 | unknown | unknown | unknown |
| Mukhtar Hussain | Assam | 7 | 27.0 | 15 | 6.96 | 12.5 | 10.8 | 8.39 | 40.4 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Bailapudi Yeswanth | Andhra | 6 | 21.3 | 4 | 6.6 | 35.5 | 32.2 | 7.95 | 39.9 | unknown | unknown | unknown |
| Suraj Kashyap | Bihar | 7 | 27.0 | 8 | 7.0 | 23.6 | 20.2 | 8.44 | 39.4 | uncapped | no IPL record | 2021 |
| Arshad Khan | Madhya Pradesh | 5 | 17.0 | 10 | 6.18 | 10.5 | 10.2 | 7.45 | 38.8 | uncapped | 24 m, last 2026 | 2023 |
| Anukul Roy (n) | Jharkhand | 11 | 37.2 | 18 | 7.42 | 15.4 | 12.4 | 8.94 | 38.8 | uncapped | 24 m, last 2026 | 2019 2021 |
| B Lalnunfela * | Mizoram | 6 | 19.0 | 11 | 6.47 | 11.2 | 10.4 | 7.8 | 37.7 | uncapped | no IPL record | 2021 |
| Codanda Ajit Karthik * (n) | Mizoram | 6 | 22.0 | 5 | 6.77 | 29.8 | 26.4 | 8.16 | 37.1 | uncapped | no IPL record | 2021 |
| V Koushik | Goa | 7 | 24.0 | 10 | 6.92 | 16.6 | 14.4 | 8.34 | 37.0 | unknown | unknown | unknown |
| Suyash Sharma | Delhi | 7 | 27.0 | 11 | 7.11 | 17.5 | 14.7 | 8.57 | 36.4 | uncapped | 39 m, last 2026 | 2023 2024 |
| KM Asif | Kerala | 6 | 20.3 | 15 | 6.73 | 9.2 | 8.2 | 8.11 | 35.4 | uncapped | 7 m, last 2023 | 2018 2019 2021 2022 2023 |
| Akash Choudhary * | Meghalaya | 5 | 20.0 | 6 | 6.7 | 22.3 | 20.0 | 8.07 | 35.2 | uncapped | no IPL record | 2019 2021 2023 |
| Shams Mulani (n) | Mumbai | 8 | 28.0 | 5 | 7.21 | 40.4 | 33.6 | 8.69 | 34.8 | uncapped | 2 m, last 2024 | 2018 2019 2021 2022 2023 |
| Abid Mushtaq (n) | Jammu and Kashmir | 6 | 21.1 | 2 | 6.85 | 72.5 | 63.5 | 8.25 | 34.0 | uncapped | no IPL record | 2019 2021 2023 |
| Prithvi Raj Yarra | Andhra | 9 | 34.0 | 12 | 7.47 | 21.2 | 17.0 | 9.0 | 33.6 | unknown | unknown | unknown |
| KC Cariappa * | Mizoram | 6 | 23.2 | 8 | 7.03 | 20.5 | 17.5 | 8.47 | 33.4 | uncapped | 11 m, last 2019 | 2016 2019 2021 2023 |
| Milind | Hyderabad | 9 | 34.4 | 17 | 7.5 | 15.3 | 12.2 | 9.04 | 33.2 | unknown | unknown | unknown |
| Jayant Yadav (n) | Puducherry | 7 | 25.0 | 9 | 7.16 | 19.9 | 16.7 | 8.63 | 32.5 | uncapped | 20 m, last 2023 | 2016 2018 2019 2021 2022 2023 |
| Bhuvneshwar Kumar | Uttar Pradesh | 7 | 22.0 | 8 | 7.0 | 19.2 | 16.5 | 8.44 | 32.1 | capped (T20I) | 206 m, last 2026 | 2019 2021 2023 2024 |
| Sandeep Sharma | Chandigarh | 7 | 27.0 | 13 | 7.3 | 15.2 | 12.5 | 8.8 | 31.4 | capped (T20I) | 142 m, last 2026 | 2018 2019 2021 2024 |
| Aaron Nongrum * | Meghalaya | 5 | 13.0 | 2 | 6.08 | 39.5 | 39.0 | 7.33 | 31.0 | unknown | unknown | unknown |
| Vipraj Nigam | Uttar Pradesh | 7 | 28.0 | 13 | 7.36 | 15.8 | 12.9 | 8.87 | 30.8 | uncapped | 19 m, last 2026 | 2024 |
| Shubham Agarwal (n) | Chhattisgarh | 7 | 23.0 | 9 | 7.17 | 18.3 | 15.3 | 8.64 | 29.5 | uncapped | 1 m, last 2017 | 2021 2023 |
| RS Hangargekar | Maharashtra | 7 | 26.4 | 11 | 7.39 | 17.9 | 14.5 | 8.9 | 28.6 | uncapped | 2 m, last 2023 | 2021 |
| Nagwaswalla | Gujarat | 7 | 25.5 | 11 | 7.35 | 17.3 | 14.1 | 8.86 | 28.5 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Rajesh Mohanty | Odisha | 7 | 25.0 | 12 | 7.4 | 15.4 | 12.5 | 8.92 | 26.5 | uncapped | no IPL record | 2019 2021 |
| Mohammed Salahuddin Izhar | Bihar | 5 | 19.4 | 9 | 7.12 | 15.6 | 13.1 | 8.58 | 26.3 | unknown | unknown | unknown |
| Chiragvir Dhindsa | Chandigarh | 7 | 19.0 | 4 | 7.11 | 33.8 | 28.5 | 8.57 | 25.7 | unknown | unknown | unknown |
| Darshan Misal | Goa | 7 | 25.0 | 5 | 7.44 | 37.2 | 30.0 | 8.97 | 25.5 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Deepraj Gaonkar | Goa | 7 | 24.0 | 10 | 7.46 | 17.9 | 14.4 | 8.99 | 24.0 | uncapped | no IPL record | 2016 2019 2021 2022 2023 |
| Auqib Nabi Dar | Jammu and Kashmir | 7 | 25.5 | 15 | 7.55 | 13.0 | 10.3 | 9.1 | 23.5 | unknown | unknown | unknown |
| Manisankar Murasingh | Tripura | 7 | 26.5 | 6 | 7.6 | 34.0 | 26.8 | 9.16 | 23.0 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Avneesh Sudha | Uttarakhand | 4 | 15.0 | 4 | 6.93 | 26.0 | 22.5 | 8.35 | 22.9 | uncapped | no IPL record | 2019 2021 2022 |
| Badal Biswal | Odisha | 5 | 17.0 | 4 | 7.12 | 30.2 | 25.5 | 8.58 | 22.8 | unknown | unknown | unknown |
| Karn Sharma | Railways | 7 | 26.0 | 7 | 7.62 | 28.3 | 22.3 | 9.18 | 21.9 | unknown | unknown | unknown |
| MD Nidheesh | Kerala | 7 | 24.2 | 7 | 7.56 | 26.3 | 20.9 | 9.11 | 21.8 | uncapped | no IPL record | 2019 2021 |
| Abdul Basith | Kerala | 7 | 18.0 | 5 | 7.28 | 26.2 | 21.6 | 8.77 | 21.2 | uncapped | 1 m, last 2023 | 2022 2023 |
| Ankur Malik * | Sikkim | 6 | 19.0 | 7 | 7.37 | 20.0 | 16.3 | 8.88 | 20.7 | unknown | unknown | unknown |
| Nitin Sai Yadav | Hyderabad | 7 | 25.0 | 5 | 7.64 | 38.2 | 30.0 | 9.21 | 20.5 | unknown | unknown | unknown |
| Rongsen Jonathan * | Nagaland | 5 | 17.5 | 8 | 7.35 | 16.4 | 13.4 | 8.86 | 19.8 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Biplab Samantray (n) | Odisha | 7 | 18.0 | 9 | 7.39 | 14.8 | 12.0 | 8.9 | 19.2 | uncapped | 8 m, last 2013 | 2016 2018 2019 2021 |
| Digvesh Singh Rathi (n) | Delhi | 5 | 20.0 | 7 | 7.5 | 21.4 | 17.1 | 9.04 | 19.2 | uncapped | 23 m, last 2026 | - |
| Chingakham Bidash * | Manipur | 3 | 12.0 | 6 | 6.92 | 13.8 | 12.0 | 8.34 | 18.5 | unknown | unknown | unknown |
| Mohammad Arfaz Ahmed | Hyderabad | 7 | 12.0 | 4 | 6.92 | 20.8 | 18.0 | 8.34 | 18.5 | unknown | unknown | unknown |
| Atal Bihari Rai | Railways | 7 | 25.2 | 9 | 7.74 | 21.8 | 16.9 | 9.33 | 18.3 | unknown | unknown | unknown |
| Praveen Dubey | Karnataka | 6 | 16.2 | 8 | 7.35 | 15.0 | 12.2 | 8.86 | 18.2 | uncapped | 5 m, last 2025 | 2018 2019 2021 |
| Abdul Ajij Kuraishi | Assam | 5 | 17.0 | 6 | 7.41 | 21.0 | 17.0 | 8.93 | 17.8 | unknown | unknown | unknown |
| Ram Gurung * | Meghalaya | 5 | 17.0 | 2 | 7.53 | 64.0 | 51.0 | 9.07 | 15.8 | uncapped | no IPL record | 2021 2023 |
| Lee Yong Lepcha * | Sikkim | 6 | 16.0 | 2 | 7.5 | 60.0 | 48.0 | 9.04 | 15.3 | uncapped | no IPL record | 2019 2021 |
| Yuvraj Chaudhary (n) | Uttarakhand | 6 | 19.0 | 5 | 7.68 | 29.2 | 22.8 | 9.25 | 14.7 | uncapped | no IPL record | 2021 |
| Imliwati Lemtur * | Nagaland | 5 | 16.0 | 9 | 7.56 | 13.4 | 10.7 | 9.11 | 14.3 | uncapped | no IPL record | 2019 2021 2022 2023 |
| Swapnil Singh | Tripura | 7 | 22.0 | 10 | 7.82 | 17.2 | 13.2 | 9.42 | 14.1 | unknown | unknown | unknown |
| Anuj Thakral | Haryana | 4 | 14.0 | 6 | 7.5 | 17.5 | 14.0 | 9.04 | 13.4 | unknown | unknown | unknown |
| Mayank Markande | Punjab | 5 | 16.0 | 2 | 7.62 | 61.0 | 48.0 | 9.18 | 13.3 | capped (T20I) | 40 m, last 2026 | 2018 2019 2021 2022 2023 |
| L Kishan Singha * | Manipur | 5 | 20.0 | 3 | 7.8 | 52.0 | 40.0 | 9.4 | 13.2 | uncapped | no IPL record | 2021 2022 2023 |
| Ankit Sharma | Kerala | 4 | 13.0 | 3 | 7.46 | 32.3 | 26.0 | 8.99 | 13.0 | unknown | unknown | unknown |
| Arpit Rana | Haryana | 5 | 15.0 | 3 | 7.6 | 38.0 | 30.0 | 9.16 | 12.9 | unknown | unknown | unknown |
| Nishant Sindhu | Haryana | 6 | 17.0 | 4 | 7.71 | 32.8 | 25.5 | 9.29 | 12.8 | uncapped | 5 m, last 2026 | 2022 2023 |
| Vishal Jayswal | Gujarat | 6 | 17.0 | 5 | 7.76 | 26.4 | 20.4 | 9.35 | 11.8 | uncapped | no IPL record | 2022 2023 |
| Arjun Tendulkar | Goa | 5 | 16.2 | 8 | 7.78 | 15.9 | 12.2 | 9.37 | 11.2 | uncapped | 6 m, last 2026 | 2021 2022 2023 |
| Japagnya Bhatt (n) | Gujarat | 4 | 13.0 | 7 | 7.62 | 14.1 | 11.1 | 9.18 | 11.0 | capped (T20I) | no IPL record | - |
| Yudhvir Singh Charak | Jammu and Kashmir | 7 | 26.0 | 11 | 8.04 | 19.0 | 14.2 | 9.69 | 10.9 | unknown | unknown | unknown |
| Prince Yadav | Delhi | 8 | 30.2 | 11 | 8.14 | 22.5 | 16.5 | 9.81 | 9.6 | capped (T20I) | 20 m, last 2026 | 2024 |
| Sunil Kumar | Uttar Pradesh | 6 | 20.3 | 8 | 8.0 | 20.5 | 15.4 | 9.64 | 9.4 | unknown | unknown | unknown |
| Chirag Jani | Saurashtra | 5 | 16.0 | 6 | 7.88 | 21.0 | 16.0 | 9.5 | 9.3 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 2024 |
| Harpreet Brar | Punjab | 9 | 29.0 | 15 | 8.14 | 15.7 | 11.6 | 9.81 | 9.3 | uncapped | 48 m, last 2026 | 2019 2021 2022 2023 |
| Sharafuddeen | Kerala | 6 | 16.0 | 6 | 7.88 | 21.0 | 16.0 | 9.5 | 9.3 | uncapped | no IPL record | 2021 |
| T Natarajan | Tamil Nadu | 6 | 23.0 | 8 | 8.09 | 23.2 | 17.2 | 9.75 | 8.5 | capped (T20I) | 73 m, last 2026 | 2019 2021 2023 |
| Khalid Alam | Bihar | 5 | 14.0 | 2 | 7.86 | 55.0 | 42.0 | 9.47 | 8.4 | unknown | unknown | unknown |
| Rahul Sharma | Railways | 4 | 15.5 | 6 | 7.96 | 21.0 | 15.8 | 9.59 | 7.9 | unknown | unknown | unknown |
| Ninad Rathva | Baroda | 6 | 18.0 | 4 | 8.06 | 36.2 | 27.0 | 9.71 | 7.2 | uncapped | no IPL record | 2018 2019 2021 2022 2023 |
| Sakibul Gani | Bihar | 7 | 23.5 | 6 | 8.18 | 32.5 | 23.8 | 9.86 | 6.6 | uncapped | no IPL record | 2021 2022 |
| TC Vanlalremruata * | Mizoram | 6 | 23.0 | 8 | 8.22 | 23.6 | 17.2 | 9.91 | 5.5 | uncapped | no IPL record | 2023 |
| Rasikh Salam (n) | Baroda | 6 | 20.0 | 5 | 8.2 | 32.8 | 24.0 | 9.88 | 5.2 | uncapped | 25 m, last 2026 | 2019 2023 |
| Shivang Kumar (n) | Madhya Pradesh | 4 | 12.1 | 4 | 8.05 | 24.5 | 18.2 | 9.7 | 4.9 | uncapped | 13 m, last 2026 | - |
| Venkatesh Iyer (n) | Madhya Pradesh | 9 | 19.0 | 6 | 8.26 | 26.2 | 19.0 | 9.95 | 3.7 | capped (T20I) | 62 m, last 2026 | 2016 2018 2019 2021 2022 2023 2024 |
| Satyanarayana Raju | Andhra | 10 | 36.0 | 16 | 8.36 | 18.8 | 13.5 | 10.07 | 3.5 | unknown | unknown | unknown |
| Rahul Singh (n) | Chandigarh | 7 | 27.0 | 4 | 8.33 | 56.2 | 40.5 | 10.04 | 3.4 | uncapped | no IPL record | 2018 2019 2021 2023 |
| Shahbaz Ahmed | Bengal | 5 | 16.0 | 4 | 8.25 | 33.0 | 24.0 | 9.94 | 3.3 | capped (T20I) | 58 m, last 2026 | 2019 2021 2023 2024 |
| Prayash Singh | Odisha | 6 | 14.4 | 5 | 8.25 | 24.2 | 17.6 | 9.94 | 3.1 | unknown | unknown | unknown |
| Tripuresh Singh | Madhya Pradesh | 10 | 37.0 | 16 | 8.38 | 19.4 | 13.9 | 10.1 | 3.0 | uncapped | no IPL record | 2024 |
| Rajan Kumar | Uttarakhand | 7 | 26.0 | 13 | 8.35 | 16.7 | 12.0 | 10.06 | 2.9 | uncapped | no IPL record | 2022 |
| Thakur | Mumbai | 10 | 30.0 | 13 | 8.37 | 19.3 | 13.8 | 10.09 | 2.7 | unknown | unknown | unknown |
| Rahul Batham | Madhya Pradesh | 10 | 32.4 | 10 | 8.39 | 27.4 | 19.6 | 10.11 | 2.3 | uncapped | no IPL record | 2019 2021 2023 2024 |
| Pulkit Narang | Services | 7 | 22.0 | 4 | 8.41 | 46.2 | 33.0 | 10.13 | 1.1 | uncapped | no IPL record | 2019 2021 |
| Prashant Solanki (n) | Maharashtra | 7 | 23.0 | 6 | 8.43 | 32.3 | 23.0 | 10.16 | 0.5 | uncapped | 2 m, last 2022 | 2021 2022 |
| Kiran Laishram * | Manipur | 5 | 17.0 | 3 | 8.47 | 48.0 | 34.0 | 10.21 | -0.2 | unknown | unknown | unknown |
| KV Sasikanth (n) | Andhra | 8 | 29.2 | 9 | 8.49 | 27.7 | 19.6 | 10.23 | -0.9 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 |
| Sonu Yadav | Tamil Nadu | 6 | 21.0 | 7 | 8.52 | 25.6 | 18.0 | 10.27 | -1.4 | uncapped | no IPL record | 2021 |
| Agreas Sangma * (n) | Meghalaya | 4 | 13.0 | 2 | 8.62 | 56.0 | 39.0 | 10.39 | -2.0 | uncapped | no IPL record | 2023 |
| Hemang Patel | Gujarat | 5 | 16.0 | 7 | 8.62 | 19.7 | 13.7 | 10.39 | -2.7 | uncapped | no IPL record | 2019 2022 2023 |
| Raj Limbani | Baroda | 7 | 25.1 | 15 | 8.58 | 14.4 | 10.1 | 10.34 | -3.1 | unknown | unknown | unknown |
| Vikas Yadav | Services | 5 | 16.0 | 2 | 8.69 | 69.5 | 48.0 | 10.47 | -3.7 | uncapped | no IPL record | 2019 2021 |
| Tadakamalla Mohith * | Arunachal Pradesh | 5 | 17.0 | 6 | 8.71 | 24.7 | 17.0 | 10.5 | -4.2 | unknown | unknown | unknown |
| Sairaj Patil | Mumbai | 9 | 29.0 | 14 | 8.62 | 17.9 | 12.4 | 10.39 | -4.7 | uncapped | no IPL record | 2021 2022 |
| Mridul Surroch | Himachal Pradesh | 7 | 21.0 | 8 | 8.71 | 22.9 | 15.8 | 10.5 | -5.4 | unknown | unknown | unknown |
| Vignesh Puthur (n) | Kerala | 4 | 14.0 | 6 | 8.86 | 20.7 | 14.0 | 10.68 | -5.6 | uncapped | 5 m, last 2025 | - |
| Aryaman Singh (n) | Himachal Pradesh | 6 | 18.0 | 3 | 8.78 | 52.7 | 36.0 | 10.58 | -5.8 | uncapped | 23 m, last 2012 | - |
| Anshul Kamboj | Haryana | 11 | 43.1 | 21 | 8.59 | 17.7 | 12.3 | 10.35 | -5.9 | uncapped | 25 m, last 2026 | 2022 2023 |
| Sourabh Majumdar | Chhattisgarh | 6 | 19.5 | 7 | 8.77 | 24.9 | 17.0 | 10.57 | -6.2 | uncapped | no IPL record | 2021 2022 2023 |
| Pheiroijam Jotin * | Manipur | 5 | 19.0 | 6 | 8.79 | 27.8 | 19.0 | 10.59 | -6.3 | unknown | unknown | unknown |
| Ravi Bishnoi | Gujarat | 7 | 23.5 | 9 | 8.73 | 23.1 | 15.9 | 10.52 | -6.4 | capped (T20I) | 85 m, last 2026 | 2019 2021 2022 2023 |
| Adil Ayub Tunda | Puducherry | 6 | 20.5 | 11 | 8.78 | 16.6 | 11.4 | 10.58 | -6.8 | unknown | unknown | unknown |
| Viki Saha (n) | Tripura | 5 | 18.0 | 5 | 8.83 | 31.8 | 21.6 | 10.64 | -6.8 | uncapped | no IPL record | 2016 2018 2023 |
| Ajay Jadav Mandal | Chhattisgarh | 6 | 22.0 | 8 | 8.77 | 24.1 | 16.5 | 10.57 | -6.9 | uncapped | no IPL record | 2018 2019 2021 2022 2023 |
| Shivam Mavi | Uttar Pradesh | 7 | 21.1 | 6 | 8.79 | 31.0 | 21.2 | 10.59 | -7.0 | capped (T20I) | 32 m, last 2022 | 2021 2022 2024 |
| Nabam Tempol * | Arunachal Pradesh | 4 | 12.0 | 2 | 9.08 | 54.5 | 36.0 | 10.94 | -7.5 | uncapped | no IPL record | 2019 2021 |
| Nachiket Bhute (n) | Vidarbha | 4 | 14.0 | 4 | 9.0 | 31.5 | 21.0 | 10.84 | -7.6 | uncapped | no IPL record | 2021 |
| Abhishek Sharma | Punjab | 6 | 16.0 | 7 | 8.94 | 20.4 | 13.7 | 10.77 | -7.7 | capped (T20I) | 92 m, last 2026 | 2018 2019 2021 2022 2023 |
| J Suchith (n) | Uttarakhand | 7 | 19.1 | 7 | 8.87 | 24.3 | 16.4 | 10.69 | -7.9 | uncapped | 21 m, last 2022 | 2016 2018 2019 2021 2022 |
| Agrim Tiwari | Uttarakhand | 5 | 18.0 | 5 | 8.94 | 32.2 | 21.6 | 10.77 | -8.8 | uncapped | no IPL record | 2021 2022 |
| Saurav Kumar * | Nagaland | 5 | 12.1 | 2 | 9.21 | 56.0 | 36.5 | 11.1 | -9.1 | unknown | unknown | unknown |
| Vijaykumar Vyshak | Karnataka | 6 | 22.0 | 9 | 8.91 | 21.8 | 14.7 | 10.74 | -9.9 | uncapped | 25 m, last 2026 | 2021 2022 2023 |
| Arshin Kulkarni (n) | Maharashtra | 6 | 14.4 | 2 | 9.2 | 67.5 | 44.0 | 11.09 | -10.9 | uncapped | 4 m, last 2026 | - |
| Khiangte Vanrotlinga * | Mizoram | 6 | 19.0 | 3 | 9.05 | 57.3 | 38.0 | 10.91 | -11.3 | unknown | unknown | unknown |
| Amit Rana | Haryana | 4 | 12.0 | 5 | 9.42 | 22.6 | 14.4 | 11.35 | -11.5 | unknown | unknown | unknown |
| Shubhang Hegde | Karnataka | 5 | 16.0 | 6 | 9.19 | 24.5 | 16.0 | 11.07 | -11.7 | uncapped | no IPL record | 2023 |
| Krunal Pandya (n) | Baroda | 6 | 20.0 | 3 | 9.05 | 60.3 | 40.0 | 10.91 | -11.8 | capped (T20I) | 158 m, last 2026 | 2018 2019 2021 2022 2023 2024 |
| Shami | Bengal | 7 | 26.5 | 16 | 8.91 | 14.9 | 10.1 | 10.74 | -12.0 | unknown | unknown | unknown |
| Ankolekar | Mumbai | 10 | 32.1 | 9 | 8.89 | 31.8 | 21.4 | 10.71 | -13.9 | uncapped | no IPL record | 2021 2023 2024 |
| K Nagarkoti (n) | Rajasthan | 8 | 29.3 | 13 | 8.95 | 20.3 | 13.6 | 10.78 | -14.5 | uncapped | 12 m, last 2022 | 2021 2022 |
| Ajay Dev Goud (n) | Hyderabad | 7 | 25.0 | 7 | 9.04 | 32.3 | 21.4 | 10.89 | -14.5 | uncapped | no IPL record | 2019 2021 |
| Sahil Dhiwan | Rajasthan | 4 | 12.2 | 2 | 9.65 | 59.5 | 37.0 | 11.63 | -14.7 | unknown | unknown | unknown |
| Saurabh Shekhar | Jharkhand | 6 | 20.0 | 5 | 9.25 | 37.0 | 24.0 | 11.15 | -15.8 | unknown | unknown | unknown |
| DA Jadeja | Saurashtra | 4 | 12.3 | 4 | 9.76 | 30.5 | 18.8 | 11.76 | -16.3 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 2024 |
| Akash Deep | Bengal | 5 | 18.0 | 7 | 9.39 | 24.1 | 15.4 | 11.31 | -16.8 | uncapped | 14 m, last 2025 | 2019 2021 2023 |
| A Sheth | Baroda | 6 | 20.0 | 9 | 9.35 | 20.8 | 13.3 | 11.27 | -17.8 | uncapped | no IPL record | 2016 2018 2019 2021 2022 2023 2024 |
| Aman Khan (n) | Puducherry | 6 | 13.5 | 6 | 9.76 | 22.5 | 13.8 | 11.76 | -18.0 | capped (T20I) | no IPL record | - |
| Ishant Bhardwaj | Haryana | 6 | 22.0 | 8 | 9.32 | 25.6 | 16.5 | 11.23 | -18.9 | unknown | unknown | unknown |
| Vikash Singh | Jharkhand | 16 | 48.0 | 15 | 8.85 | 28.3 | 19.2 | 10.66 | -19.0 | uncapped | no IPL record | 2016 2018 2019 2021 |
| Umran Malik (n) | Jammu and Kashmir | 5 | 17.0 | 6 | 9.59 | 27.2 | 17.0 | 11.56 | -19.2 | capped (T20I) | 26 m, last 2024 | 2021 2023 |
| Sakib Hussain | Bihar | 5 | 15.1 | 5 | 9.76 | 29.6 | 18.2 | 11.76 | -19.7 | uncapped | 11 m, last 2026 | 2022 |
| Sushant Mishra (n) | Jharkhand | 11 | 42.2 | 22 | 8.93 | 17.2 | 11.5 | 10.76 | -19.9 | uncapped | 2 m, last 2026 | - |
| Heramb Parab | Goa | 4 | 12.0 | 4 | 10.17 | 30.5 | 18.0 | 12.25 | -20.5 | uncapped | no IPL record | 2019 2021 |
| Varun Chakaravarthy | Tamil Nadu | 4 | 16.0 | 2 | 9.75 | 78.0 | 48.0 | 11.75 | -20.7 | unknown | unknown | unknown |
| Shreyas Gopal | Karnataka | 6 | 21.0 | 5 | 9.48 | 39.8 | 25.2 | 11.42 | -21.4 | uncapped | 51 m, last 2024 | 2016 2018 2019 2021 2023 |
| Akash Sengupta | Assam | 6 | 21.3 | 9 | 9.49 | 22.7 | 14.3 | 11.44 | -22.1 | uncapped | no IPL record | 2021 2023 |
| Chinntla Rakshan Readdi | Hyderabad | 9 | 32.4 | 13 | 9.15 | 23.0 | 15.1 | 11.03 | -22.7 | unknown | unknown | unknown |
| Mohit Rathee (n) | Services | 7 | 24.0 | 8 | 9.42 | 28.2 | 18.0 | 11.35 | -23.0 | uncapped | 1 m, last 2023 | - |
| Rajandeep Singh | Jharkhand | 7 | 21.0 | 5 | 9.57 | 40.2 | 25.2 | 11.53 | -23.4 | unknown | unknown | unknown |
| Soumya Ranjan Lenka | Odisha | 5 | 15.0 | 4 | 10.07 | 37.8 | 22.5 | 12.13 | -24.1 | unknown | unknown | unknown |
| Harshal Patel (n) | Gujarat | 5 | 19.3 | 8 | 9.69 | 23.6 | 14.6 | 11.68 | -24.1 | capped (T20I) | no IPL record | - |
| Mayank Dagar | Himachal Pradesh | 6 | 19.5 | 5 | 9.68 | 38.4 | 23.8 | 11.66 | -24.2 | uncapped | 8 m, last 2024 | 2018 2019 2021 2022 |
| Vaibhav Arora (n) | Himachal Pradesh | 7 | 23.4 | 9 | 9.51 | 25.0 | 15.8 | 11.46 | -24.8 | uncapped | 42 m, last 2026 | 2021 2022 |
| Akash Maharaj Singh | Rajasthan | 6 | 21.0 | 2 | 9.67 | 101.5 | 63.0 | 11.65 | -25.4 | unknown | unknown | unknown |
| Gurjapneet Singh | Tamil Nadu | 6 | 23.2 | 5 | 9.56 | 44.6 | 28.0 | 11.52 | -25.6 | unknown | unknown | unknown |
| Jagjit Singh | Chandigarh | 7 | 26.0 | 11 | 9.46 | 22.4 | 14.2 | 11.4 | -26.1 | uncapped | no IPL record | 2021 2024 |
| Akshat Pandey | Railways | 6 | 17.0 | 4 | 10.0 | 42.5 | 25.5 | 12.05 | -26.2 | uncapped | no IPL record | 2016 2021 2022 2023 |
| Prerak Mankad (n) | Saurashtra | 6 | 12.0 | 3 | 10.83 | 43.3 | 24.0 | 13.05 | -28.5 | uncapped | 6 m, last 2023 | 2016 2018 2019 2021 2022 2024 |
| Nikhil Sharma (n) | Chandigarh | 4 | 12.0 | 3 | 10.83 | 43.3 | 24.0 | 13.05 | -28.5 | uncapped | no IPL record | - |
| Saurabh Das | Tripura | 6 | 20.0 | 6 | 9.9 | 33.0 | 20.0 | 11.93 | -28.8 | uncapped | no IPL record | 2018 2019 2021 |
| Ashok Sharma | Rajasthan | 10 | 37.1 | 22 | 9.26 | 15.6 | 10.1 | 11.16 | -29.6 | unknown | unknown | unknown |
| Suryansh Shedge | Mumbai | 8 | 16.0 | 5 | 10.31 | 33.0 | 19.2 | 12.42 | -29.7 | capped (T20I) | 10 m, last 2026 | 2024 |
| Sanvir Singh | Punjab | 9 | 20.0 | 7 | 10.0 | 28.6 | 17.1 | 12.05 | -30.8 | uncapped | 5 m, last 2024 | 2021 2022 2023 |
| Rahul Chahar (n) | Rajasthan | 9 | 29.0 | 6 | 9.55 | 46.2 | 29.0 | 11.51 | -31.7 | capped (T20I) | 79 m, last 2026 | 2018 2019 2021 2022 |
| Ayush Badoni | Delhi | 6 | 17.0 | 6 | 10.35 | 29.3 | 17.0 | 12.47 | -32.2 | uncapped | 58 m, last 2026 | 2021 2022 2023 2024 |
| Pradipta Pramanik | Bengal | 6 | 17.0 | 4 | 10.35 | 44.0 | 25.5 | 12.47 | -32.2 | uncapped | no IPL record | 2018 2019 2021 2024 |
| Indrajit Debnath | Tripura | 6 | 16.3 | 3 | 10.55 | 58.0 | 33.0 | 12.71 | -34.4 | unknown | unknown | unknown |
| Gurnoor Brar (n) | Punjab | 6 | 23.1 | 10 | 9.97 | 23.1 | 13.9 | 12.01 | -35.0 | uncapped | 1 m, last 2023 | - |
| Abhishek Tiwari | Services | 4 | 13.3 | 5 | 11.11 | 30.0 | 16.2 | 13.39 | -35.8 | unknown | unknown | unknown |
| Ramandeep Singh | Punjab | 9 | 23.4 | 9 | 10.06 | 26.4 | 15.8 | 12.12 | -37.8 | capped (T20I) | 27 m, last 2026 | 2021 2022 2023 |
| Vishal Gaur | Services | 4 | 12.0 | 5 | 11.75 | 28.2 | 14.4 | 14.16 | -39.5 | unknown | unknown | unknown |
| Ayush Goyal | Punjab | 5 | 15.5 | 5 | 11.05 | 35.0 | 19.0 | 13.32 | -41.1 | unknown | unknown | unknown |
| Vidhwath Kaverappa | Karnataka | 6 | 20.4 | 3 | 10.5 | 72.3 | 41.3 | 12.65 | -42.2 | uncapped | 1 m, last 2024 | 2022 2023 |
| Samant Jakhar | Haryana | 10 | 29.3 | 14 | 9.9 | 20.9 | 12.6 | 11.93 | -42.5 | unknown | unknown | unknown |
| Darshan Nalkande (n) | Vidarbha | 6 | 22.1 | 8 | 10.42 | 28.9 | 16.6 | 12.56 | -43.5 | uncapped | 6 m, last 2024 | 2019 2021 2022 2024 |
| Ashwani Kumar | Punjab | 9 | 29.0 | 8 | 9.97 | 36.1 | 21.8 | 12.01 | -43.7 | uncapped | 10 m, last 2026 | 2022 |
| Chetan Sakariya | Saurashtra | 7 | 28.0 | 12 | 10.04 | 23.4 | 14.0 | 12.1 | -44.2 | capped (T20I) | 20 m, last 2025 | 2019 2021 2022 |
| Bal Krishna | Jharkhand | 11 | 36.3 | 14 | 9.7 | 25.3 | 15.6 | 11.69 | -45.3 | uncapped | no IPL record | 2021 |
| Vidyadhar Patil | Karnataka | 7 | 26.0 | 8 | 10.35 | 33.6 | 19.5 | 12.47 | -49.1 | uncapped | no IPL record | 2021 |
| Sumit Kumar | Haryana | 11 | 38.0 | 7 | 9.79 | 53.1 | 32.6 | 11.8 | -50.6 | uncapped | 3 m, last 2024 | 2016 2019 2021 2022 2023 |
| Akash Madhwal | Uttarakhand | 6 | 18.0 | 3 | 11.44 | 68.7 | 36.0 | 13.79 | -53.8 | uncapped | 17 m, last 2025 | 2019 2021 2022 |
| Tushar Deshpande (n) | Mumbai | 10 | 30.3 | 8 | 10.23 | 39.0 | 22.9 | 12.33 | -54.0 | capped (T20I) | 53 m, last 2026 | 2018 2019 2021 2022 2023 |
| Ravisrinivasan Sai Kishore | Tamil Nadu | 6 | 17.0 | 1 | 11.94 | 203.0 | 102.0 | 14.39 | -59.2 | unknown | unknown | unknown |
| Writtick Chatterjee | Bengal | 7 | 23.0 | 7 | 11.39 | 37.4 | 19.7 | 13.72 | -67.5 | uncapped | no IPL record | 2018 2019 2021 2024 |

## Caveats
- **Small samples.** Each player has at most 10-11 innings. One big innings moves the score a lot; treat the lists as a shortlist to watch, not a verdict.
- **SMAT is not IPL.** Pitches, opposition depth and the lack of a proper pace mix make SMAT easier on batters and gentler on bowlers. The factors above are averages; for an individual they are only a guide.
- **Plate group** (11 batters, 25 bowlers in the tables) plays much weaker teams (Meghalaya, Nagaland, Sikkim and similar). Their numbers are inflated relative to Elite; read them with a large discount.
- **Name matching.** The scraper matched 46 batters and 92 bowlers by team history. A second pass matched 31 batters and 45 bowlers by name only (marked `(n)`; common names are the risk). 38 batters and 59 bowlers stay unmatched and are shown as unknown, not as uncapped.
- **Uncapped means no T20I only.** Players capped in ODIs or Tests could still show as uncapped; a player appearing only as a fielder or non-playing squad member is not detected as a T20I player.
- **Earlier SMAT history** in the DB covers 2016 to 2024 only (competition `smat`); it is not complete for every season.
- No VJD or super-over adjustment was made; super overs are not in the scorecards.
