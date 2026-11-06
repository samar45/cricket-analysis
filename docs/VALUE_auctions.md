# IPL auctions 2022-2026: checks and gaps (built 2026-11-06)

Files (UTF-8, built by Worker A2, not yet reviewed by the lead):
- `src/cricket_analytics/reference/ipl_auctions.csv` (1,317 rows: 615 sold + 702 unsold)
- `src/cricket_analytics/reference/ipl_retentions.csv` (252 rows)

Build scripts were run from the scratchpad (not saved in the repo). Fetched pages are public news/Wikipedia pages read once each on 2026-11-06 (`source_date`).

## What is in the file
Columns as requested, plus three extra: `presented_on_block`, `match_basis`, `notes`.

| Year | Auction date (day 1) | Sold | Unsold rows | of which "on the block" | Overseas sold |
|---|---|---|---|---|---|
| 2022 | 2022-02-12 (2 days, Bengaluru) | 204 | 96 | 96 | 67 |
| 2023 | 2022-12-23 (Kochi) | 80 | 71 | 71 | 29 |
| 2024 | 2023-12-19 (Dubai) | 72 | 62 | 62 | 30 |
| 2025 | 2024-11-24 (2 days, Jeddah) | 182 | 394 | 101 | 62 |
| 2026 | 2025-12-16 (Abu Dhabi) | 77 | 79 | 79 | 29 |

**Sold rows** come from the Wikipedia page "List of 20XX Indian Premier League personnel changes" (CC BY-SA), with documented corrections (below). **Unsold rows** come from news lists (not Wikipedia, which lists sold only): MyKhel + Wisden (2022, 2024), Wisden + Onmanorama (2023), CricTracker + CricketAddictor (2025), Wisden + Outlook India (2026), merged by name. Country/capped for 2026 unsold also from the Sports Digest 350-player pool.

**Important: what "unsold" means.** `presented_on_block=true` means a source lists the player as having gone under the hammer and drawn no bid. For 2022-2024 and 2026 the lists we found contain only such players. They are NOT the full registered pool (2022: 600 players, 2023: 405, 2024: 333, 2026: 350), because no free legal source gave the full pool with prices except ESPNcricinfo (not scraped by instruction). For 2025 we also include all 395 players ESPNcricinfo-style "unsold" per CricketAddictor; only 101 of them are on CricTracker's on-block list. The other 293 have `presented_on_block` blank = unknown, most likely never brought up (accelerated rounds only covered franchise requests; this is an inference). For training, filter to `presented_on_block=true`.

`capped` = true/false as listed; Associate-nation players are left blank. `role` for 2026 sold rows is derived from the auction set name (the Wikipedia table has no role column), role is blank for unsold rows (not in any source) and for 2 added 2025 rows. `set_no`: set number, `acc` = accelerated round (2022-24 sets are from the table's "Set No." column). `lot_no` = the player's sequence number in the Wikipedia table (sold rows only, 2022-24 numbers are not strictly in auction order). `auction_date` is the first day for two-day auctions.

## Checks

### Totals against official figures
All five sold totals match the officially reported number of players and spend exactly after the corrections below.

| Year | Sold | Total (cr) | Official | Purse per team | Source for purse |
|---|---|---|---|---|---|
| 2022 | 204 | 551.70 | 204 / 551.70 (exchange4media, Wisden) | 90 | Wikipedia |
| 2023 | 80 | 167.00 | 80 / about 167 (Outlook: Rs 167.00 cr; The Quint) | 95 | ESPNcricinfo (search summary) |
| 2024 | 72 | 230.45 | 72 / 230.45 | 100 | Wisden (search summary) |
| 2025 | 182 | 639.15 | 182 / 639.15 (CricketAddictor, Business Today) | 120 | Wikipedia |
| 2026 | 77 | 215.45 | 77 / 215.45 (Wisden, Outlook) | 125 | Wikipedia (the 120 in the brief is wrong for 2026) |

Purses 90/95/100/120/125 all confirmed. Official 2024 total 230.45 and 2026 215.45 were taken from the same search summaries and Wikipedia sums; the 2023 official figure is quoted as 167.00 by Outlook (not 167.05).

### Per-team auction spend (crore, [players bought]; for the two mega auctions plus retention salary)
No team exceeds its purse. For megas the retention salary is shown but the real purse deduction can differ (2022: DC Axar 9 salary / 12 deduction, KKR Russell 12 / 16 per a Wikipedia footnote), so the comparison is indicative.

| Team | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| CSK | 45.05 [21] +42.00 ret | 18.95 [7] | 30.40 [6] | 54.95 [20] +65.00 ret | 41.00 [9] |
| DC | 47.40 [20] +39.00 | 15.00 [5] | 19.05 [9] | 72.80 [19] +43.75 | 21.45 [8] |
| GT | 51.85 [20] +38.00 | 14.80 [7] | 30.30 [8] | 68.85 [20] +51.00 | 10.95 [5] |
| KKR | 47.55 [21] +34.00 | 5.40 [8] | 31.35 [10] | 50.95 [15] +57.00 | 63.85 [13] |
| LSG | 59.00 [18] +30.20 | 19.80 [10] | 12.20 [6] | 68.90 [19] +51.00 | 18.40 [6] |
| MI | 47.90 [21] +42.00 | 20.50 [8] | 16.70 [8] | 44.80 [18] +75.00 | 2.20 [5] |
| PBKS | 68.55 [23] +16.00 | 20.00 [6] | 24.95 [8] | 110.15 [23] +9.50 | 8.00 [4] |
| RR | 61.05 [21] +28.00 | 9.85 [9] | 14.30 [5] | 40.70 [14] +79.00 | 13.40 [9] |
| RCB | 55.45 [19] +33.00 | 7.00 [7] | 20.40 [6] | 82.25 [19] +37.00 | 16.15 [8] |
| SRH | 67.90 [20] +22.00 | 35.70 [13] | 30.80 [6] | 44.80 [15] +75.00 | 20.05 [10] |

Cross-check: SRH 2023 = 35.70 matches The Federal and Outlook. 2025 team player counts match the Wikipedia summary table (CSK 20, DC 19, GT 20, KKR 15, LSG 19, MI 18, PBKS 23, RR 14, RCB 19, SRH 15). Mini-auction teams started with their leftover purse, which we do not have, so for 2023, 2024 and 2026 the check is only "spend is below the full purse".

### Most expensive 5 per auction (all confirmed against a second source)
- 2022: Ishan Kishan 15.25 (MI), Deepak Chahar 14.00 (CSK), Shreyas Iyer 12.25 (KKR), Liam Livingstone 11.50 (PBKS), Harshal Patel 10.75 (RCB)
- 2023: Sam Curran 18.50 (PBKS), Cameron Green 17.50 (MI), Ben Stokes 16.25 (CSK), Nicholas Pooran 16.00 (LSG), Harry Brook 13.25 (SRH)
- 2024: Mitchell Starc 24.75 (KKR), Pat Cummins 20.50 (SRH), Daryl Mitchell 14.00 (CSK), Harshal Patel 11.75 (PBKS), Alzarri Joseph 11.50 (RCB)
- 2025: Rishabh Pant 27.00 (LSG), Shreyas Iyer 26.75 (PBKS), Venkatesh Iyer 23.75 (KKR), Arshdeep Singh 18.00 (PBKS, RTM), Yuzvendra Chahal 18.00 (PBKS)
- 2026: Cameron Green 25.20 (KKR), Matheesha Pathirana 18.00 (KKR), Kartik Sharma 14.20 (CSK), Prashant Veer 14.20 (CSK), Liam Livingstone 13.00 (SRH)

The four sanity prices in the brief (Kishan 15.25, Curran 18.50, Starc 24.75, Pant 27.00) are right.

### Corrections made to the Wikipedia sold tables (Wikipedia had wrong prices)
Found by comparing each year with a second full list and with the official total. In each case total then matches exactly.
| Year | Player | Wikipedia | Used | Second source |
|---|---|---|---|---|
| 2022 | Ashok Sharma | 0.50 | 0.55 | Wisden sold list |
| 2022 | Aneeshwar Gautam | 1.00 (also base 1.00) | 0.20 (base 0.20) | Wisden sold list |
| 2023 | Prerak Mankad | 1.80 | 0.20 | Wisden + Onmanorama |
| 2023 | Donavon Ferreira | 0.20 | 0.50 | Wisden + Onmanorama |
| 2023 | Rajan Kumar | 0.20 | 0.70 | Wisden + Onmanorama |
| 2024 | Kartik Tyagi | 5.00 | 0.60 | Outlook |
Also: 2025 table lacked two sold players (Moeen Ali KKR 2.00; Venkata Satyanarayana Penmetsa MI 0.30); added from CricketAddictor (flagged in `notes`). Matthew Breetzke's base was blank; 0.75 added from CricketAddictor.
Residual risk: two errors that cancel inside a year would not show in totals. Prices of rows in 2025 and 2026 were checked against only one extra list each (see below).

### Row-level double-source coverage (automatic: surname + price on the same line of a second list)
2022: 200 of 204 (Wisden) before corrections, 204 of 204 after. 2023: 77 of 80 vs the Wisden/Onmanorama lists (both partial, 72 and 78 players). 2024: 68 of 72 (Outlook). 2025: all 182 vs CricketAddictor's list. 2026: 77 players, total equals Wisden/Outlook 215.45; per-row check only for the part of the Wisden page that was readable (58 of 77).
Known open conflict: 2023 Upendra Yadav (SRH): Wikipedia 0.25 (kept, and needed for the 167.00 total); Wisden lists 0.30.

### 10 random rows (seed 5), checked in the original page and a second source
| Row | Value in file | Second source |
|---|---|---|
| 2023 Duan Jansen MI | 0.20 | Wisden 2023 sold list: INR 20 lakh |
| 2025 Mitchell Starc DC | 11.75 | CricketAddictor 2025 sold list: Rs 11.75 cr, base 2 cr |
| 2026 Liam Livingstone SRH | 13.00 | Wisden 2026 sold list: SRH, 13 cr |
| 2022 Shivam Mavi KKR | 7.25 | Wisden 2022 sold list: 7,25,00,000 |
| 2025 Manish Pandey KKR | 0.75 | CricketAddictor: Rs 75 lakh |
| 2023 Upendra Yadav SRH | 0.25 | NOT confirmed: Wisden 0.30 (see conflict) |
| 2022 Harpreet Brar PBKS | 3.80 | Wisden 2022: 3,80,00,000 |
| 2022 Ashwin Hebbar DC | 0.20 | Wisden 2022: 20,00,000 |
| 2022 Gerald Coetzee unsold, base 0.20 | on block | Wisden 2022 unsold list: base 20,00,000 |
| 2024 Mohammad Waqar Salamkheil unsold, base 0.50 | on block | MyKhel and Wisden 2024 unsold lists |
Nine of ten confirmed.

URLs: sold, all years: `https://en.wikipedia.org/wiki/List_of_<year>_Indian_Premier_League_personnel_changes`. Second sources: Wisden sold lists (`wisden.com/series/tata-ipl-2022/...full-list-of-sold-players...`, `.../indian-premier-league-2023/...complete-list-sold-players-during-mini-auction`, `.../ipl-2026/...full-list-of-players-sold-along-with-final-bid-price`), Outlook India 2024 list, Onmanorama 2023, CricketAddictor 2025 (`cricketaddictor.com/cricket-news/ipl-auction-2025-all-sold-players-list`). Unsold URLs are in each row's `source_url`.

### Other consistency checks
- Base price: every row's base is one of the standard slabs (0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1, 1.25, 1.5, 2 cr) and no sold price is below base.
- 2025 RTM: 8 rows flagged (Arshdeep Singh PBKS 18, Jake Fraser-McGurk DC 9, Mukesh Kumar DC 8, Naman Dhir MI 5.25, Rachin Ravindra CSK 4, Sai Kishore GT 2, Shamar Joseph LSG 0.75, Swapnil Singh RCB 0.5), taken from Wikipedia's dagger marks (it cites MyKhel's RTM list). Not independently re-checked. RTM did not exist in 2022-2024 and 2026, so those years are all false.
- One duplicate name in 2025 unsold (Himanshu Singh appears twice in CricketAddictor, probably two players); price model should key on row, not name.

## Retentions file
`ipl_retentions.csv`: cycles 2022 (33 rows), 2025 (46), 2026 (173). `price_cr` is the salary on Wikipedia's retention tables. Team totals for 2025 match the known figures (MI 75.00, RR 79.00, SRH 75.00, PBKS 9.50). 2026 totals equal the earlier contracts file (GT 112.10, MI 122.25, ...).
- 2022: the GT and LSG rows (Hardik, Rashid, Gill; Rahul, Stoinis, Bishnoi) were the new franchises' draft picks, not retentions; same table. Real purse deductions differ from salaries for some (see above).
- 2023 and 2024 have no formal retention event with a new price, so they are not included (squads simply carried over).
- `capped` is blank in all retention rows: the Wikipedia tables do not say. `overseas`/`country` come from the nationality column.
- RTM cards available per team were not collected.

## Cricsheet mapping (`cricsheet_name`, `match_basis`)
Method: reused `ipl_contracts.csv` matches (basis `contracts:<original basis>`), then exact name, then unique surname + first initial among Cricsheet men's names (IPL appearances first; `initials_nonIPL` = unique only among all men's data, weaker), with 10 manual `judgement` matches (Dinesh Karthik = KD Karthik, Dwayne Bravo = DJ Bravo, Bhanuka Rajapaksa, Kusal Mendis = BKG Mendis, Dushmanta Chameera, Wiaan Mulder, Junior Dala, Rassie van der Dussen = HE van der Dussen, Fabian Allen = FA Allen, Karn Sharma = KV Sharma). The `cricket resolve` command was not run name by name (1,300 calls); the same Cricsheet name list was used directly. Two candidates -> blank.

Sold rows mapped: 2022 185/204, 2023 74/80, 2024 63/72, 2025 169/182, 2026 62/77. Unsold mapped: 70/96, 47/71, 47/62, 233/394, 55/79. Sanity check: of sold players with a mapped name, about 60-90 percent (lowest for 2023 `initials`, 19 of 32) have an IPL match in the auction's season in Cricsheet; the rest are bench, injured or withdrawn players (the large-price misses, such as Jason Roy, Deepak Chahar and Jofra Archer in 2022, are known season misses, but the small-price misses were not individually checked).

Unmapped sold (no record or ambiguous, left blank):
- 2022 (19): Abhinav Manohar Sadarangani, Chama Milind, Aneeshwar Gautam, Aryan Juyal, Ashwin Hebbar, B. Sai Sudharshan, Baltej Singh, C. Hari Nishanth, K. Bhagath Varma, Karan Sharma (ambiguous), Luvnith Sisodia, Rahul Buddhi, Rasikh Salam Dar, Ravikumar Samarth, Saurabh Dubey (ambiguous), Shubham Garhwal, Subhranshu Senapati, Vicky Ostwal, Writtick Chatterjee
- 2023 (6): Litton Das, Harpreet Singh Bhatia, Akash Vasisht, Bhagath Varma, Samarth Vyas, Yudhvir Singh Charak
- 2024 (9): Shubham Dubey (ambiguous), Gus Atkinson, Abid Mushtaq, Avanish Rao Aravelly, Jhathavedh Subramanyan, Prince Choudary, Rasikh Dar, Swastik Chhikara, Tanay Thyagarajan
- 2025 (13): Rasikh Salam Dar, Shubham Dubey (ambiguous), Vansh Bedi, Andre Siddarth, Aryan Juyal, Digvesh Singh, Krishnan Shrijith, Luvnith Sisodia, Manvanth Kumar L, Pyla Avinash, Swastik Chikara, Venkata Satyanarayana Penmetsa, Yuvraj Chaudhary
- 2026 (15): Tejasvi Singh, Amit Kumar, Atharva Ankolekar, Daksh Kamra, Kanishk Chouhan, Krains Fuletra, Mohammad Izhar, Onkar Tarmale, Prithvi Raj, Sahil Parekh, Sarthak Ranjan, Satvik Deswal, Vicky Ostwal, Vihaan Malhotra, Vishal Nishad
- Ambiguous unsold: 2025 Abhishek Nair, Karteek Sharma, Saurabh Dubey, Vishwanath Pratap Singh; 2026 Jamie Smith. Retentions unmapped: Pyla Avinash, Harnoor Pannu, Shubham Dubey (2026).
Some of these are spelling differences (for example Sai Sudharshan = B Sai Sudharsan, Rasikh Dar = Rasikh Salam in the old data) that a person could resolve; they were not guessed. Weak spots to spot-check: all `initials_nonIPL` rows (98) and `contracts:initials_nonIPL` rows (for example Jack Edwards = J Edwards, Ben Duckett = BM Duckett).

## Gaps and risks
1. **Unsold coverage is partial** (see "what unsold means"). The full registered pools (600, 405, 333, 577, 350 players) are not in the file; the pool for 2025 appears via the 293 unconfirmed unsold rows only. Counts: 2022 on-block unsold 96 (MyKhel reported 95; Wisden list had 89, union 96), 2023 71 and 2024 62 (both from live-updated lists; a third list might add a few), 2025 101 on-block (CricTracker says 102, one entry not parsed), 2026 79 (Wisden says 79).
2. **Country/overseas missing for some unsold:** 2025 unsold 170 blank, 2023 unsold 26 blank (sources give names and base price only). Filled where the same player appears with a country in another year's list (marked in `notes`). `capped` is blank for all 2023 and 2024 unsold rows (not in sources); present for 2022, 2025, 2026.
3. **Role** is blank for unsold rows and 2 sold rows. No unsold role source was used.
4. **Wikipedia errors:** it had 6 wrong prices and 2 missing rows in the sold tables (corrected). Other rows rest on Wikipedia plus the total check, so a wrong pair of prices that offset each other inside one year would pass undetected.
5. **Base prices** for sold rows are Wikipedia's (not double-checked row by row apart from the slab check); for unsold rows the two sources agreed except Josh Inglis 2024 (Wisden typo 20 cr; MyKhel 2 cr used, flagged in `notes`).
6. **Source terms:** Wikipedia text is CC BY-SA 4.0 (credit it if redistributed). The unsold lists and cross-check pages are facts (names, prices) read from news sites; no site was bulk-scraped, ESPNcricinfo and Cricbuzz were not touched, no login. Kaggle datasets were NOT used: pages that surfaced in search list no licence and need login to download. The 2022 and 2025 official iplt20.com auction pages were not opened (dynamic pages).
7. 2022 names such as "Shubham Sharma"/"Tanmay Agarwal" (Wisden only) and 8 players in 2026 (Wisden only) rest on one source.
8. The lot numbers (`lot_no`) for 2022-2024 follow the Wikipedia table's "S.No." column, which is not in strict auction order.
