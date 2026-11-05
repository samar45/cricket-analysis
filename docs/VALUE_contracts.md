# IPL contracts reference: checks and gaps (built 2026-11-05)

File: `src/cricket_analytics/reference/ipl_contracts.csv` (278 rows, UTF-8). Worker C, not yet reviewed by the lead.

## What the file is
- One row per player per team for the squad at the end of IPL 2026 (RCB champions), including players who withdrew and were replaced (`withdrawn_2026=true`). Four extra rows (`status_2027=traded_in`) show the 2027 trades from the new team's side.
- `price_cr` is the 2026 salary from each team's Wikipedia season page (CC BY-SA). For the four 2027-traded players the OLD team row keeps the 2026 price and the `traded_in` row carries the new price.
- `how_acquired`: `retained` (kept in the Nov 2025 retention), `auction_2026` (mini-auction held 16 Dec 2025 in Abu Dhabi, for the 2026 season), `trade` (Nov 2025 pre-season trades, or 2027 trade on traded_in rows), `replacement` (in-season injury/withdrawal cover, bought in 2026). `year_acquired` is the calendar year of the transaction (retention, auction and Nov trades = 2025). The original 2025 mega-auction price/year of retained players is NOT in the file.
- `capped` filled only where the source stated it (RCB page, LSG/MI uncapped auction buys); blank otherwise. `role_listed` is blank for every row: the Wikipedia squad tables do not carry a role column in the form we could read.
- `cricsheet_name` + `match_basis`: exact (full name equal), initials (unique surname + first initial in our IPL data), initials_nonIPL (same, from all men's T20 data), judgement (manual, listed below), ambiguous / none (blank).

## Checks

Spend columns in crore. Official purse is **125 cr** for 2026 (Wikipedia and iplt20.com), not 120. "Purse spend" = retained + trades + auction buys (replacements are paid outside the purse). "Active" excludes withdrawn players.

| Team | Active rows | Withdrawn rows | Active salary | Purse spend (retained+trade+auction) | Overseas (active) |
|---|---|---|---|---|---|
| CSK | 25 | 5 | 114.85 | 120.60 | 8 |
| DC | 25 | 1 | 120.15 | 121.40 | 8 |
| GT | 25 | 2 | 121.80 | 123.05 | 7 |
| KKR | 25 | 4 | 88.45 | 118.55 | 7 |
| LSG | 24 | 2 | 116.05 | 120.45 | 6 |
| MI | 25 | 4 | 122.70 | 124.45 | 7 |
| PBKS | 25 | 0 | 121.50 | 121.50 | 8 |
| RR | 25 | 2 | 117.30 | 118.35 | 8 |
| RCB | 23 | 3 | 117.15 | 124.75 | 7 |
| SRH | 25 | 4 | 118.00 | 119.55 | 8 |

- Squad size: all ten active squads are 23-25 (inside 18-25). Including withdrawn rows CSK has 30; that is an artefact of keeping withdrawn players, not an oversized squad.
- Purse: no team is over 125 cr. Seven teams are over 120 cr (CSK, DC, GT, LSG, MI, PBKS, RCB); that is fine under the real 125 cr purse. MI (124.45) and RCB (124.75) are within 0.6 cr of the cap.
- Overseas: nobody above 8. Five teams are at exactly 8 (CSK, DC, PBKS, RR, SRH).
- KKR active salary (88.45) is low because Pathirana (18) and Mustafizur (9.2) withdrew and their replacements cost 0.75 each.

### Reconciliation with the official retention totals (iplt20.com, 15 Nov 2025)
Retained+trade rows in the file vs the official "total spent": GT 112.10, LSG 102.05, MI 122.25, PBKS 113.50, RCB 108.60, SRH 99.50 match exactly. Four do NOT match:

| Team | File | iplt20.com | Gap |
|---|---|---|---|
| CSK | 79.60 | 81.60 | 2.00 |
| DC | 99.95 | 103.20 | 3.25 |
| KKR | 54.70 | 60.70 | 6.00 |
| RR | 104.95 | 108.95 | 4.00 |

All four are teams with trades or traded-away players, so a likely cause is how the official total counts traded players, but this is a guess and not checked. Player counts match for CSK (16), DC (17), KKR (12), RR (16), so one or more individual prices on those pages may differ from what iplt20.com used. Treat retained prices of CSK, DC, KKR and RR as less certain until checked. Auction prices are confirmed separately (below).

### 10 random rows re-verified against a second source
Seed 7, `in_squad` rows. Second sources: Wisden full sold list https://www.wisden.com/series/ipl-2026/cricket-news/ipl-2026-auction-full-list-of-players-sold-along-with-final-bid-price ; iplt20.com retention page https://www.iplt20.com/news/4247/tata-ipl-2026-player-retentions-announced (team totals only, no player prices).

| Row | Result |
|---|---|
| DC Auqib Nabi 8.4 | Confirmed by Wisden (listed as Auqib Dar Nabi) |
| PBKS Ben Dwarshuis 4.4 | Confirmed (Accelerated Round 2) |
| CSK Sarfaraz Khan 0.75 | Confirmed (Accelerated Round 2). Some early reports list him unsold; he was sold in the accelerated round |
| KKR Mustafizur Rahman 9.2 | Confirmed (Accelerated Round 1) |
| SRH Onkar Tarmale 0.30 | Confirmed (Accelerated Round 1) |
| PBKS Yuzvendra Chahal 18 | Indirect only: PBKS retained total matches iplt20.com exactly; no player price shown |
| GT Nishant Sindhu 0.30 | Indirect only: GT retained total matches exactly |
| RR Dhruv Jurel 14 | NOT verified: RR total is 4.00 off |
| DC Tristan Stubbs 10 | NOT verified: DC total is 3.25 off |
| CSK Jamie Overton 1.5 | NOT verified: CSK total is 2.00 off |

So 5 of 10 are directly confirmed, 2 indirectly, 3 not independently confirmed. Extra auction spot check from the same Wisden page: Connolly 3, Sahil Parakh 0.3, Livingstone 13, Kartik Sharma 14.2, Prashant Veer 14.2 all match. Prithvi Shaw (DC, 0.75, auction) is not on that Wisden page, so unconfirmed.

## 2027 trades and releases found (as of 2026-11-05)
| Date | Move | Fees | Source |
|---|---|---|---|
| 2026-06-23 | Rishabh Pant LSG to DC, Kuldeep Yadav DC to LSG | Pant 15 cr (down from 27); Kuldeep keeps his existing contract (13.25 cr per Wikipedia, 13.5 per Business Today/Outlook summaries) | Official DC news https://www.delhicapitals.in/news/rishabh-pant-returns-to-delhi-capitals-as-kuldeep-yadav-moves-to-lucknow-super-giants (date only, no fees); fees from https://www.businesstoday.in/sports/story/ipls-costliest-player-rishabh-pant-takes-44-pay-cut-returns-to-delhi-capitals-538707-2026-06-23 and Outlook (search summary, Outlook page not opened) |
| 2026-10-14 (article date) | T Natarajan DC to SRH, Zeeshan Ansari SRH to DC | Natarajan 5 cr (down from 10.75); Ansari keeps 0.40 | https://www.crictracker.com/cricket-news/t-natarajan-reunites-with-srh-as-zeeshan-ansari-moves-to-dc-in-player-trade/ |

- No releases or retention lists exist yet. The retention/release deadline was moved from 15 to 17 Nov 2026 (newkerala, dated 2 Nov); the mini-auction is 16 Dec 2026 in Goa; the trade window closes about 9 Dec 2026 (one week before the auction; from a search summary, not read in full). Rerun this build after 17 Nov to capture retentions and releases. Until then `status_2027` is `in_squad` only meaning "no change announced", not "confirmed retained".

## Unresolved Cricsheet names (`cricsheet_name` blank)
- No record found (likely new or uncapped, or spelled differently in Cricsheet): Macneil Noronha, Prithvi Raj, Sarthak Ranjan, Tejasvi Singh, Daksh Kamra, Luvnith Sisodia, Mohammad Izhar, Atharva Ankolekar, Vishal Nishad, Pyla Avinash, Emanjot Chahal, Kanishk Chouhan, Satvik Deswal, Vihaan Malhotra, Vicky Ostwal, Krains Fuletra, Amit Kumar, Onkar Tarmale, RS Ambrish. Some may exist under a different spelling that the surname search missed.
- Ambiguous, deliberately left blank (do not guess):
  - Saurabh Dubey (KKR) and Shubham Dubey (RR): the two candidates are `SR Dubey` (4 matches, last 2026-05-24) and `SB Dubey` (17 matches, last 2026-05-24); cannot tell which is which.
  - Kuldip Yadav (CSK): only `K Yadav` (3 matches, 2023), probably a different person from the Kuldeep Yadav entry.
  - Harnoor Singh (PBKS): only `H Singh`, too generic.
  - Mangesh Yadav (RCB): only `MP Yadav`, which is Mayank Yadav.

## Manual (judgement) matches, please spot-check
Cameron Green = C Green (vs CJ Green, 1 match in 2020); Finn Allen = FH Allen (vs FA Allen, 2022); Rinku Singh = RK Singh; Rohit Sharma = RG Sharma; Sai Kishore = R Sai Kishore; Sai Sudharsan = B Sai Sudharsan; Prasidh Krishna = M Prasidh Krishna; Varun Chakravarthy = CV Varun; Vaibhav Sooryavanshi = V Suryavanshi; Wanindu Hasaranga = PWH de Silva; Dasun Shanaka = MD Shanaka; Dushmantha Chameera = PVD Chameera; Kamindu Mendis = PHKD Mendis; Shahrukh Khan = M Shahrukh Khan. Other `initials` matches (about 160) are unique surname + first-initial matches and were not individually verified. Mukul Choudhary = MD Choudhary and Mayank Rawat = M Rawat are of that weaker kind (no other candidate, but could be someone else). Spelling variants accepted: Abhishek Porel = Abishek Porel, Nitish Kumar Reddy = Nithish Kumar Reddy.

## Other gaps and uncertainties
- Source conflicts: Wikipedia lists Mitchell Marsh (LSG) as withdrawn although stats show him playing; Cameron Green is 25.2 or 25.25 cr on different Wikipedia pages (25.2 used); Kuldeep Yadav 13.25 vs 13.5.
- Wikipedia season pages were read through a summarising fetch tool, not parsed from raw HTML; an extraction slip is possible, which is partly why the team-total reconciliation matters. Only the first ~100k characters of each page were read (squad tables sit early).
- Trade salaries: for Nov 2025 trades the price equals the player's salary at the old team (Wikipedia lists the same figure). Pant and Natarajan show that 2027 trades can reset the fee, so do not assume trade price = old price.
- Replacement-player fees are as listed on Wikipedia and are outside the purse.
- No ESPNcricinfo or Cricbuzz pages were fetched. Role and original 2025 mega-auction price are not collected.
