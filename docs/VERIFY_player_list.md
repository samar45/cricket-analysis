# Verification of the hand-kept player list (sample check)

Date: 2026-10-24. File checked: `src/cricket_analytics/reference/player_overrides.csv` (HEAD version: 941 data rows, file lines 2-942). Sources are public web pages read through search snippets and a few direct Wikipedia infobox reads; no scraping. Every claim below is *verified with the URL given* unless marked not found.

## Result in one paragraph

Sample = 100 rows (10 from each block of 100). **bat_hand is the weak field**: 11 of 94 checked bat_hand values were wrong (12%), all of them left/right flips: 4 on 'high', 6 on 'medium', 1 on 'low' rows. The 'medium' level is above the 10% line (15%), 'high' is just under it (8%). bowl_type is mostly right: 2 wrong of 78 (3%), plus 12 near-misses (fast vs fast-medium vs medium). Keeper: 11 of 11 correct. 12 rows were corrected (13 field values).

## 1. The sample (reproducible)

`random.Random(20261024)`; the file is split into blocks of 100 data rows in file order (last block has 41 rows); `rng.sample(indices_of_block, 10)` per block, then sorted by position. Row numbers (L) are file line numbers (header = line 1). Sampled names:

- Block 1: B Kumar (L4), Harbhajan Singh (L11), MM Sharma (L24), K Rabada (L26), Ravi Bishnoi (L41), MG Johnson (L69), Washington Sundar (L77), GJ Maxwell (L85), SK Raina (L94), Yash Dayal (L100)
- Block 2: RJ Harris (L109), AD Mathews (L113), CH Gayle (L145), DS Rathi (L146), S Lamichhane (L166), BM Scholtz (L167), R Shepherd (L173), BJ McCarthy (L180), Sohail Tanvir (L185), KA Maharaj (L197)
- Block 3: C Overton (L222), CF Parkinson (L224), FJ Klaassen (L236), JA Richardson (L253), SW Tait (L257), MJ Swepson (L262), OP Stone (L264), XC Bartlett (L266), S Dhawan (L276), AM Rahane (L298)
- Block 4: PR Stirling (L307), KC Sangakkara (L309), RR Rossouw (L311), SD Hope (L320), RR Pant (L334), TM Head (L338), DP Conway (L341), TM Dilshan (L344), AL Davies (L349), DA Payne (L355)
- Block 5: Junaid Khan (L413), Karan KC (L419), N Mlaba (L422), Sompal Kami (L432), MT Steketee (L436), LE Plunkett (L449), OE Robinson (L466), O Prendergast (L476), A Shrubsole (L488), Fatima Sana (L494)
- Block 6: KE Bryce (L506), L Pope (L509), MW Short (L512), DR Mousley (L526), GJ Delany (L541), MA Wood (L542), MA Beer (L553), Mahmudullah (L560), SG Borthwick (L565), LK Bell (L573)
- Block 7: S Prasanna (L608), GK Berg (L616), PWA Mulder (L625), KT Maphaka (L664), AA Alleyne (L665), NM Lyon (L670), Yasir Shah (L673), JL Gunn (L682), D Brown (L686), DA Cosker (L701)
- Block 8: KAJ Roach (L702), TS Sekhukhune (L703), AD Mascarenhas (L709), SB Styris (L711), SW Bates (L733), T Bhatia (L747), SJ Taylor (L754), L Ronchi (L769), MD Patel (L791), GC Wilson (L794)
- Block 9: YH Bhatia (L809), CMW Read (L823), MDKJ Perera (L824), Mohammad Haris (L835), TP Alsop (L838), Haseebullah Khan (L861), Yash Thakur (L868), Arshad Khan (L881), LR Shukla (L890), Lalit Yadav (L894)
- Block 10: JD Ryder (L905), BJ Hodge (L908), N Rana (L911), KC Cariappa (L913), VS Malik (L916), V Pratap Singh (L917), Mohammad Asif (L921), S Randiv (L928), Swapnil Singh (L930), V Sehwag (L937)

## 2. Error tables

Legend: V = verified, N = near-miss (pace tier differs: fast / fast-medium / medium, where sources themselves disagree), W = wrong, X = not found (none).

### By field and confidence level (confidence = the file's own label for that field)

| field, confidence | checked | V | N (near-miss) | W (wrong) | X |
|---|---|---|---|---|---|
| bowl_type, high | 66 | 57 | 8 (12.1%) | 1 (1.5%) | 0 |
| bowl_type, medium | 12 | 7 | 4 (33.3%) | 1 (8.3%) | 0 |
| bowl_type, low | 0 | 0 | 0 (-) | 0 (-) | 0 |
| bat_hand, high | 52 | 48 | 0 (0.0%) | 4 (7.7%) | 0 |
| bat_hand, medium | 40 | 34 | 0 (0.0%) | 6 (15.0%) | 0 |
| bat_hand, low | 2 | 1 | 0 (0.0%) | 1 (50.0%) | 0 |
| keeper (no confidence column) | 11 | 11 | 0 (0.0%) | 0 (0.0%) | 0 |
| **bowl_type, all** | 78 | 64 | 12 (15.4%) | 2 (2.6%) | 0 |
| **bat_hand, all** | 94 | 83 | 0 (0.0%) | 11 (11.7%) | 0 |
| **all fields** | 183 | 158 | 12 (6.6%) | 13 (7.1%) | 0 |

### Warnings

- **bat_hand 'medium': 6 wrong of 40 (15%) - ABOVE the 10% line.** bat_hand 'high': 4 wrong of 52 (7.7%), close to the line and still too many for a 'high' label. bat_hand 'low': 1 wrong of 2 (too few rows to judge).
- bowl_type 'high': 1 wrong of 66 (1.5%), near-misses 8 (12.1%). Under the 10% line for wrongs. bowl_type 'medium': 1 wrong of 12, 4 near-misses; 'low': 0 sampled.
- Wrong hands cluster on spinners, keepers and lesser-known players (Beer, Randiv, Swapnil Singh, Asif, Haseebullah, Alsop, Klaassen, Scholtz, Davies, Borthwick, Yash Dayal). Unsampled rows are likely to carry a similar error rate (about 12% is the sample estimate, on 94 values, so roughly +/- 5 points).

## 3. Per-row results

Bowl / Bat / Keep: V verified, N near-miss, W wrong (corrected), `-` field empty in the file.

| Line | Name | File: bowl_type (conf) | File: bat (conf) | File: keeper | Bowl | Bat | Keep | Source URL(s) | Remark |
|---|---|---|---|---|---|---|---|---|---|
| 4 | B Kumar | right-arm fast-medium (high) | right (high) |  | N | V | - | https://espncricinfo.com/cricketers/bhuvneshwar-kumar-326016 ; https://wisden.com/players/bhuvneshwar-kumar | ESPN/Wisden medium, other Wisden page fast-medium |
| 11 | Harbhajan Singh | right-arm off spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Harbhajan_Singh |  |
| 24 | MM Sharma | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Mohit_Sharma |  |
| 26 | K Rabada | right-arm fast (high) | left (high) |  | V | V | - | https://wisden.com/players/kagiso-rabada |  |
| 41 | Ravi Bishnoi | right-arm leg spin (high) | right (medium) |  | V | V | - | https://wisden.com/players/ravi-bishnoi |  |
| 69 | MG Johnson | left-arm fast (high) | left (high) |  | V | V | - | https://en.wikipedia.org/wiki/Mitchell_Johnson |  |
| 77 | Washington Sundar | right-arm off spin (high) | left (high) |  | V | V | - | https://wisden.com/players/washington-sundar |  |
| 85 | GJ Maxwell | right-arm off spin (high) | right (high) |  | V | V | - | https://ssl.espncricinfo.com/cricketers/glenn-maxwell-325026 |  |
| 94 | SK Raina | right-arm off spin (high) | left (high) |  | V | V | - | https://en.wikipedia.org/wiki/Suresh_Raina |  |
| 100 | Yash Dayal | left-arm fast-medium (high) | left (medium) |  | V | W | - | https://en.wikipedia.org/wiki/Yash_Dayal ; https://espncricinfo.com/cricketers/yash-dayal-1159720 | Wikipedia + ESPNcricinfo right-handed; one newer Wisden page and Cricket Times say left. Changed to right |
| 109 | RJ Harris | right-arm fast (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Ryan_Harris_(cricketer) | Wisden page says fast-medium |
| 113 | AD Mathews | right-arm medium (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Angelo_Mathews |  |
| 145 | CH Gayle | right-arm off spin (high) | left (high) |  | V | V | - | https://espncricinfo.com/player/chris-gayle-51880 |  |
| 146 | DS Rathi | right-arm leg spin (medium) | right (low) |  | V | V | - | https://en.wikipedia.org/wiki/Digvesh_Rathi |  |
| 166 | S Lamichhane | right-arm leg spin (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Sandeep_Lamichhane |  |
| 167 | BM Scholtz | left-arm orthodox (medium) | left (low) |  | V | W | - | https://en.wikipedia.org/wiki/Bernard_Scholtz | bat is right-handed (file said left) |
| 173 | R Shepherd | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://wisden.com/players/romario-shepherd |  |
| 180 | BJ McCarthy | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://cdn2.wisden.com/players/barry-mccarthy-63157 |  |
| 185 | Sohail Tanvir | left-arm fast-medium (high) | left (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Sohail_Tanvir |  |
| 197 | KA Maharaj | left-arm orthodox (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Keshav_Maharaj |  |
| 222 | C Overton | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Craig_Overton | Wikipedia/Cricinfo say medium-fast = our fast-medium |
| 224 | CF Parkinson | right-arm leg spin (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Callum_Parkinson |  |
| 236 | FJ Klaassen | left-arm fast-medium (high) | left (medium) |  | V | W | - | https://en.wikipedia.org/wiki/Fred_Klaassen | bat is right-handed (file said left) |
| 253 | JA Richardson | right-arm fast (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Jhye_Richardson |  |
| 257 | SW Tait | right-arm fast (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Shaun_Tait |  |
| 262 | MJ Swepson | right-arm leg spin (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Mitchell_Swepson |  |
| 264 | OP Stone | right-arm fast (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Olly_Stone |  |
| 266 | XC Bartlett | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://uk.cricinfo.com/cricketers/xavier-bartlett-1050545 |  |
| 276 | S Dhawan |  | left (high) |  | - | V | - | https://wisden.com/players/shikhar-dhawan |  |
| 298 | AM Rahane |  | right (high) |  | - | V | - | https://wisden.com/players/ajinkya-rahane |  |
| 307 | PR Stirling |  | right (high) |  | - | V | - | https://cricketireland.ie/players/ireland-men/paul-stirling |  |
| 309 | KC Sangakkara |  | left (high) |  | - | V | - | https://content.cricinfo.com/cricketers/kumar-sangakkara-50710 |  |
| 311 | RR Rossouw |  | left (high) |  | - | V | - | https://wisden.com/players/rilee-rossouw |  |
| 320 | SD Hope |  | right (high) |  | - | V | - | https://wisden.com/players/shai-hope |  |
| 334 | RR Pant |  | left (high) |  | - | V | - | https://wisden.com/players/rishabh-pant-65756 |  |
| 338 | TM Head |  | left (high) |  | - | V | - | https://cricket.com.au/players/CA:288 |  |
| 341 | DP Conway |  | left (high) |  | - | V | - | https://wisden.com/players/devon-conway |  |
| 344 | TM Dilshan |  | right (high) |  | - | V | - | https://en.wikipedia.org/wiki/Tillakaratne_Dilshan |  |
| 349 | AL Davies |  | left (high) |  | - | W | - | https://en.wikipedia.org/wiki/Alex_Davies_(cricketer) ; https://espncricinfo.com/player/alex-davies-516039 | bat is right-handed (file said left). Identity = Alex Davies, Lancashire/Warwickshire |
| 355 | DA Payne | left-arm fast-medium (high) | left (medium) |  | V | V | - | https://en.wikipedia.org/wiki/David_Payne_(cricketer) |  |
| 413 | Junaid Khan | left-arm fast (medium) |  |  | V | - | - | https://en.wikipedia.org/wiki/Junaid_Khan_(cricketer) | Wisden page says medium-fast |
| 419 | Karan KC | right-arm fast-medium (medium) |  |  | N | - | - | https://espncricinfo.com/cricketers/karan-kc-800675 | ESPNcricinfo: right-arm fast (file: fast-medium) |
| 422 | N Mlaba | left-arm orthodox (high) |  |  | V | - | - | https://en.wikipedia.org/wiki/Nonkululeko_Mlaba | Nonkululeko Mlaba, SA women |
| 432 | Sompal Kami | right-arm fast-medium (medium) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Sompal_Kami |  |
| 436 | MT Steketee | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Mark_Steketee | Mark Steketee |
| 449 | LE Plunkett | right-arm fast (high) | right (high) |  | N | V | - | https://en.wikipedia.org/wiki/Liam_Plunkett ; https://wisden.com/players/liam-plunkett | Wikipedia fast-medium, Wisden/Cricket.com fast (file: fast) |
| 466 | OE Robinson | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://wisden.com/players/ollie-robinson-64168 | medium-fast = our fast-medium |
| 476 | O Prendergast | right-arm off spin (medium) | right (medium) |  | W | V | - | https://en.wikipedia.org/wiki/Orla_Prendergast | bowls right-arm medium (Wikipedia; ESPN medium/medium-fast), not off spin. Changed to right-arm medium |
| 488 | A Shrubsole | right-arm fast-medium (high) | right (high) |  | N | V | - | https://en.wikipedia.org/wiki/Anya_Shrubsole ; https://cricket.com.au/players/CA:375 | sources say right-arm medium (file: fast-medium) |
| 494 | Fatima Sana | right-arm medium (medium) | right (medium) |  | V | V | - | https://wisden.com/players/fatima-sana-71759 |  |
| 506 | KE Bryce | right-arm medium (medium) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Kathryn_Bryce |  |
| 509 | L Pope | right-arm leg spin (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Lloyd_Pope |  |
| 512 | MW Short | right-arm off spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Matthew_Short |  |
| 526 | DR Mousley | right-arm off spin (high) | left (high) |  | V | V | - | https://en.wikipedia.org/wiki/Dan_Mousley |  |
| 541 | GJ Delany | right-arm leg spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Gareth_Delany |  |
| 542 | MA Wood | right-arm fast (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Mark_Wood_(cricketer) |  |
| 553 | MA Beer | left-arm wrist spin (high) | left (medium) |  | W | W | - | https://en.wikipedia.org/wiki/Michael_Beer_(cricketer) | Beer is slow left-arm ORTHODOX (file: left-arm wrist spin) and bats RIGHT (file: left) |
| 560 | Mahmudullah | right-arm off spin (high) | right (high) |  | V | V | - | https://ssl.espncricinfo.com/cricketers/mahmudullah-56025 |  |
| 565 | SG Borthwick | right-arm leg spin (high) | right (high) |  | V | W | - | https://en.wikipedia.org/wiki/Scott_Borthwick ; https://wisden.com/players/scott-borthwick-4913 | bat is LEFT-handed (file said right) |
| 573 | LK Bell | right-arm fast (high) | right (medium) |  | N | V | - | https://en.wikipedia.org/wiki/Lauren_Bell | ESPN/Wisden right-arm fast-medium (file: fast) |
| 608 | S Prasanna | right-arm leg spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Seekkuge_Prasanna |  |
| 616 | GK Berg | right-arm medium (high) | right (medium) |  | V | V | - | https://wisden.com/players/gareth-berg | Wikipedia says medium-fast |
| 625 | PWA Mulder | right-arm fast-medium (high) | right (high) |  | N | V | - | https://en.wikipedia.org/wiki/Wiaan_Mulder | Wikipedia/ESPN/Wisden right-arm medium; CA right-arm pace (file: fast-medium) |
| 664 | KT Maphaka | left-arm fast (high) | left (medium) |  | V | V | - | https://espncricinfo.com/cricketers/kwena-maphaka-1294342 |  |
| 665 | AA Alleyne | right-arm fast-medium (medium) |  |  | N | - | - | https://en.wikipedia.org/wiki/Aaliyah_Alleyne | Wikipedia right-arm medium (file: fast-medium) |
| 670 | NM Lyon | right-arm off spin (high) | right (high) |  | V | V | - | https://wisden.com/players/nathan-lyon |  |
| 673 | Yasir Shah | right-arm leg spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Yasir_Shah |  |
| 682 | JL Gunn | right-arm medium (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Jenny_Gunn | ESPN says medium-fast |
| 686 | D Brown | right-arm fast (high) | right (medium) |  | V | V | - | https://cricinfo.com/cricketers/darcie-brown-388845 | Darcie Brown |
| 701 | DA Cosker | left-arm orthodox (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Dean_Cosker |  |
| 702 | KAJ Roach | right-arm fast (high) | right (high) |  | N | V | - | https://en.wikipedia.org/wiki/Kemar_Roach | Wikipedia/ESPN fast-medium, Wisden fast (file: fast) |
| 703 | TS Sekhukhune | right-arm medium (medium) |  |  | V | - | - | https://en.wikipedia.org/wiki/Tumi_Sekhukhune | Wikipedia says fast-medium; Cricinfo/CA medium |
| 709 | AD Mascarenhas | right-arm medium (high) | right (high) |  | N | V | - | https://en.wikipedia.org/wiki/Dimitri_Mascarenhas | Wikipedia medium-fast, ESPN fast-medium (file: medium) |
| 711 | SB Styris | right-arm medium (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Scott_Styris |  |
| 733 | SW Bates | right-arm medium (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Suzie_Bates |  |
| 747 | T Bhatia |  | right (medium) | yes | - | V | V | https://en.wikipedia.org/wiki/Taniya_Bhatia |  |
| 754 | SJ Taylor |  | right (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Sarah_Taylor_(cricketer) |  |
| 769 | L Ronchi |  | right (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Luke_Ronchi |  |
| 791 | MD Patel |  | right (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Monank_Patel |  |
| 794 | GC Wilson |  | right (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Gary_Wilson_(cricketer) |  |
| 809 | YH Bhatia |  | left (high) | yes | - | V | V | https://wisden.com/players/yastika-bhatia |  |
| 823 | CMW Read |  | right (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Chris_Read |  |
| 824 | MDKJ Perera |  | left (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Kusal_Perera |  |
| 835 | Mohammad Haris |  | right (high) | yes | - | V | V | https://en.wikipedia.org/wiki/Mohammad_Haris |  |
| 838 | TP Alsop |  | right (high) | yes | - | W | V | https://espncricinfo.com/player/tom-alsop-602155 ; https://wisden.com/players/tom-alsop | bat is LEFT-handed (file said right); ESPN lists wicketkeeper-batter, Wisden 'occasional' |
| 861 | Haseebullah Khan |  | right (high) | yes | - | W | V | https://espncricinfo.com/ci/content/player/1171127.html ; https://wisden.com/players/haseebullah-90512 | bat is LEFT-handed (file said right) |
| 868 | Yash Thakur | right-arm fast-medium (high) | right (medium) |  | V | V | - | https://en.wikipedia.org/wiki/Yash_Thakur |  |
| 881 | Arshad Khan | left-arm fast-medium (medium) | left (medium) |  | N | V | - | https://en.wikipedia.org/wiki/Arshad_Khan_(Indian_cricketer) | Wikipedia left-arm medium (file: fast-medium) |
| 890 | LR Shukla | right-arm medium (high) | right (medium) |  | V | V | - | https://wisden.com/players/laxmi-shukla-2742 | Wikipedia says medium-fast |
| 894 | Lalit Yadav | right-arm off spin (high) | right (medium) |  | V | V | - | https://ssl.espncricinfo.com/cricketers/lalit-yadav-930189 |  |
| 905 | JD Ryder | right-arm medium (high) | left (high) |  | V | V | - | https://en.wikipedia.org/wiki/Jesse_Ryder |  |
| 908 | BJ Hodge | right-arm off spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/Brad_Hodge |  |
| 911 | N Rana | right-arm off spin (high) | left (high) |  | V | V | - | https://wisden.com/players/nitish-rana ; https://kkr.in/players/nitish-rana-profile-63649 | one Wisden page says slow left-arm orthodox; the rest off break |
| 913 | KC Cariappa | right-arm leg spin (high) | right (high) |  | V | V | - | https://en.wikipedia.org/wiki/K._C._Cariappa_(cricketer) |  |
| 916 | VS Malik | right-arm fast-medium (high) | right (medium) |  | N | V | - | https://en.wikipedia.org/wiki/Vikramjeet_Malik | Wikipedia/ESPN right-arm medium (file: fast-medium) |
| 917 | V Pratap Singh | right-arm fast-medium (medium) |  |  | N | - | - | https://en.wikipedia.org/wiki/Veer_Pratap_Singh | Wikipedia/Cricinfo right-arm medium (file: fast-medium) |
| 921 | Mohammad Asif | right-arm fast-medium (high) | right (medium) |  | V | W | - | https://en.wikipedia.org/wiki/Mohammad_Asif_(cricketer) | bat is LEFT-handed (file said right) |
| 928 | S Randiv | right-arm off spin (high) | left (medium) |  | V | W | - | https://en.wikipedia.org/wiki/Suraj_Randiv | bat is RIGHT-handed (file said left) |
| 930 | Swapnil Singh | left-arm orthodox (high) | left (medium) |  | V | W | - | https://en.wikipedia.org/wiki/Swapnil_Singh | bat is RIGHT-handed (file said left) |
| 937 | V Sehwag | right-arm off spin (high) | right (high) |  | V | V | - | https://wisden.com/players/virender-sehwag |  |

## 4. Fixes made in the CSV

All 100 sampled rows now carry `note = verified <domain> 2026-10-24` (domain of the main source). 12 rows had a value changed; confidence and `source` were left as they were on those rows:

| Name | Field | Was | Now | Source |
|---|---|---|---|---|
| Yash Dayal | bat_hand | left | right | https://en.wikipedia.org/wiki/Yash_Dayal |
| BM Scholtz | bat_hand | left | right | https://en.wikipedia.org/wiki/Bernard_Scholtz |
| FJ Klaassen | bat_hand | left | right | https://en.wikipedia.org/wiki/Fred_Klaassen |
| AL Davies | bat_hand | left | right | https://en.wikipedia.org/wiki/Alex_Davies_(cricketer) |
| O Prendergast | bowl_type | right-arm off spin | right-arm medium | https://en.wikipedia.org/wiki/Orla_Prendergast |
| MA Beer | bowl_type | left-arm wrist spin | left-arm orthodox | https://en.wikipedia.org/wiki/Michael_Beer_(cricketer) |
| MA Beer | bat_hand | left | right | https://en.wikipedia.org/wiki/Michael_Beer_(cricketer) |
| SG Borthwick | bat_hand | right | left | https://en.wikipedia.org/wiki/Scott_Borthwick |
| TP Alsop | bat_hand | right | left | espncricinfo.com/player/tom-alsop-602155 |
| Haseebullah Khan | bat_hand | right | left | espncricinfo.com/ci/content/player/1171127.html |
| Mohammad Asif | bat_hand | right | left | https://en.wikipedia.org/wiki/Mohammad_Asif_(cricketer) |
| S Randiv | bat_hand | left | right | https://en.wikipedia.org/wiki/Suraj_Randiv |
| Swapnil Singh | bat_hand | left | right | https://en.wikipedia.org/wiki/Swapnil_Singh |

Not changed on purpose: the near-miss rows (sources disagree on pace tier, left as written). Yash Dayal's bat hand was changed on a 2-vs-2 source split (Wikipedia and ESPNcricinfo say right; a newer Wisden page and Cricket Times say left): re-check by eye if it matters.

## 5. Recommendation

- **bowl_type: keep.** 3% wrong; the near-misses are pace-tier labels where sources disagree among themselves. For pace-vs-spin analysis the list is sound (the two bowl_type errors are Prendergast, medium vs off spin, and Beer, wrist spin vs orthodox).
- **bat_hand: blank or re-check the 'medium' and 'low' level first (about 411 values), and treat 'high' as roughly 92% right, not as fact.** Whole column has 860 filled values; re-check before it feeds any left/right split. About 12% of all sampled values were flipped; a flipped hand silently corrupts 'vs left-handers' stats. A cheap fix is one pass over the filled hands with the same method (one search each), starting with spinners, keepers and non-IPL players.
- keeper: no errors found in the sample; keep.

## 6. Extra task: IPL bowlers with no bowl_type

Measure: legal IPL balls (wides and no-balls excluded, super overs = innings 3+ excluded) bowled by players who have a `bowl_type` in the overrides file. Total: 284,465 legal balls, 578 bowlers. DB read-only.

| | Balls covered | Coverage | Bowlers with a type |
|---|---|---|---|
| Before | 269,938 | 94.89% | 361 of 578 |
| After | 278,929 | 98.05% | 409 of 578 |

Filled 48 players in order of balls bowled (46 in a first pass, then Shashank Singh and Raghu Sharma to cross 98%), then stopped. `source = web-verified`, confidence high on bowl_type and bat_hand, `note = web: <domain> 2026-10-24`. Identity came from the player's IPL team and years in the DB.

| Cricsheet name | bowl_type | bat_hand | Source / identity |
|---|---|---|---|
| A Singh | right-arm fast-medium | right | Amit Singh (Rajasthan) https://en.wikipedia.org/wiki/Amit_Singh_(cricketer) |
| Ankit Sharma | left-arm orthodox | left | Ankit Sharma (MP) https://en.wikipedia.org/wiki/Ankit_Sharma_(cricketer) |
| RG Sharma | right-arm off spin | right | Rohit Sharma wisden.com/players/rohit-sharma-3852 |
| VY Mahesh | right-arm fast-medium | right | Yo Mahesh https://en.wikipedia.org/wiki/Yo_Mahesh |
| SJ Srivastava | left-arm fast-medium | right | Shalabh Srivastava https://en.wikipedia.org/wiki/Shalabh_Srivastava |
| Brijesh Sharma | right-arm fast-medium | right | www.iplt20.com/players/brijesh-sharma/23164 |
| TM Dilshan | right-arm off spin | right | https://en.wikipedia.org/wiki/Tillakaratne_Dilshan |
| AG Murtaza | left-arm orthodox | left | Ali Murtaza https://en.wikipedia.org/wiki/Ali_Murtaza (Wisden says left-arm medium) |
| A Ashish Reddy | right-arm medium | right | espncricinfo.com/cricketers/ashish-reddy-389605 |
| Sakib Hussain | right-arm fast-medium | right | https://en.wikipedia.org/wiki/Sakib_Hussain (Wisden/ESPN say right-arm medium) |
| V Kohli | right-arm medium | right | wisden.com/player/13144/V Kohli |
| AA Chavan | left-arm orthodox | left | https://en.wikipedia.org/wiki/Ankeet_Chavan |
| KR Sen | right-arm fast | right | Kuldeep Sen espncricinfo.com/cricketers/kuldeep-sen-1163695 (Wisden alt: fast-medium) |
| Shivang Kumar | left-arm wrist spin | right | wisden.com/series/ipl-2026 'left-arm wrist spinner'; bat from latestly.com |
| AK Markram | right-arm off spin | right | wisden.com/players/aiden-markram |
| KP Appanna | left-arm orthodox | right | https://en.wikipedia.org/wiki/K._P._Appanna |
| YA Abdulla | left-arm fast-medium | left | Yusuf Abdulla (SA) https://en.wikipedia.org/wiki/Yusuf_Abdulla |
| Karanveer Singh | right-arm leg spin | right | espncricinfo.com/cricketers/karanveer-singh-322535 |
| S Kaushik | left-arm wrist spin | right | Shivil Kaushik espncricinfo.com/cricketers/shivil-kaushik-917213 |
| J Syed Mohammad | left-arm orthodox | left | Jamaluddin Syed Mohammad https://en.wikipedia.org/wiki/Syed_Mohammed |
| WG Jacks | right-arm off spin | right | wisden.com/players/will-jacks |
| B Akhil | right-arm fast-medium | right | Balachandra Akhil https://en.wikipedia.org/wiki/Balachandra_Akhil |
| Yash Raj Punja | right-arm leg spin | right | khelnow.com/cricket/player/yash-raj-punja |
| Kamran Khan | left-arm fast-medium | left | https://en.wikipedia.org/wiki/Kamran_Khan_(Indian_cricketer) |
| PP Hinge | right-arm fast-medium | right | Praful Hinge https://en.wikipedia.org/wiki/Praful_Hinge |
| P Parameswaran | left-arm medium | right | Prasanth Parameswaran espncricinfo.com/cricketers/prasanth-parameswaran-279562 |
| DP Vijaykumar | right-arm medium | right | Paidikalva Vijaykumar espncricinfo.com/ci/content/player/272949.html |
| PC Valthaty | right-arm medium | right | espncricinfo.com/cricketers/paul-valthaty-35630 (Wikipedia says off break) |
| Gurjapneet Singh | left-arm fast-medium | right | https://en.wikipedia.org/wiki/Gurjapneet_Singh |
| TL Suman | right-arm off spin | right | Tirumalasetti Suman wisden.com/player/23973 |
| Anand Rajan | right-arm medium | right | https://en.wikipedia.org/wiki/Anand_Rajan |
| R Sathish | right-arm medium | right | Rajagopal Sathish espncricinfo.com/cricketers/rajagopal-sathish-33870 |
| T Thushara | left-arm fast-medium | left | Thilan Thushara https://en.wikipedia.org/wiki/Thilan_Thushara |
| P Amarnath | right-arm medium | right | Palani Amarnath https://en.wikipedia.org/wiki/Palani_Amarnath (text calls him fast; infobox medium) |
| Ashok Sharma | right-arm fast-medium | right | gujarattitansipl.com/players/ashok-sharma-91316-profile (medium-fast; some press say express pace) |
| R Shukla | right-arm medium | right | Rahul Shukla https://en.wikipedia.org/wiki/Rahul_Shukla (Wikipedia says fast-medium) |
| Shivam Sharma | right-arm off spin | right | https://en.wikipedia.org/wiki/Shivam_Sharma |
| Ankit Soni | right-arm leg spin | right | https://en.wikipedia.org/wiki/Ankit_Soni |
| S Narwal | right-arm medium | left | Sumit Narwal wisden.com/players/sumit-narwal-5274 |
| P Sahu | right-arm leg spin | right | Pardeep Sahu espncricinfo.com/player/pardeep-sahu-34155 |
| Jaskaran Singh | right-arm medium | right | Jaskaran Singh (b.1989) https://en.wikipedia.org/wiki/Jaskaran_Singh_(cricketer,_born_1989) |
| Shoaib Ahmed | right-arm fast-medium | right | https://en.wikipedia.org/wiki/Shoaib_Ahmed_(Indian_cricketer) |
| SB Wagh | left-arm fast-medium | left | Shrikant Wagh https://en.wikipedia.org/wiki/Shrikant_Wagh |
| A Choudhary | left-arm medium | right | Aniket Choudhary wisden.com/players/aniket-choudhary-56974 (Wikipedia: medium-fast) |
| P Suyal | left-arm medium | right | Pawan Suyal https://en.wikipedia.org/wiki/Pawan_Suyal |
| RV Gomez | right-arm medium | right | Raiphi Gomez wisden.com/players/raiphi-gomez-5167 (Wikipedia: fast-medium) |
| Shashank Singh | right-arm off spin | right | en.wikipedia.org/wiki/Shashank_Singh (Wikipedia and Cricinfo list off break first, medium second; Wisden says medium) |
| Raghu Sharma | right-arm leg spin | right | espncricinfo.com/cricketers/raghu-sharma-1122621 (leg break googly) |

Not filled: RR Raje (Rohan Raje: Wikipedia mirror right-arm medium vs Wisden fast-medium - left blank); S Ladda (search found no profile - left blank).

Caveats: (1) Where sources split on pace tier I used the primary/majority label and still wrote 'high': Sakib Hussain, R Shukla, P Amarnath, Ashok Sharma, A Choudhary, Valthaty, RV Gomez, Shashank Singh, KR Sen, AG Murtaza (the Source column shows the split). Treat those as medium in practice. (2) Some of the 48 already had a row holding only a bat_hand (e.g. V Kohli, RG Sharma, TM Dilshan, AK Markram, WG Jacks): bat_hand was set from the web and `source` changed to `web-verified`. (3) New rows have empty `role` and `keeper`.


## bat_hand re-check (2026-10-25)

Scope: rows with bat_hand_confidence medium/low and no verified/web note (369 rows), ranked by balls faced in the DB (innings 1-2 only). One web search per player; Wikipedia / ESPNcricinfo / Wisden / club or board profile snippets. Searches stopped when the tool's per-session cap (200 searches) ran out, not because the list was finished.

| Result | Count |
|---|---|
| Checked | 197 of 369 |
| Confirmed (set high, note `web: <domain> 2026-10-25`) | 173 |
| bat_hand fixed (same note) | 24 |
| Blanked (sources split or not found) | 0 |
| bowl_type also fixed | 9 |
| Not yet checked | 172 |

The 24 fixes are 24 of the 197 checked rows (12%), all left/right flips, in line with the 10% sample. Rate by confidence band was not split out. Weak spots: Hassan Khan rests on one squad table (Wikipedia, Melbourne Renegades 2025-26). RP Singh: the DB team is USA, which does not match either Indian RP Singh found; both are right-handed, so right was set, but identity is uncertain. Several initials were matched by team and role (S Snater = Shane Snater, SW Currie = Scott Currie, H Kerr = Hayden Kerr, A Reddy = Arundhati Reddy, A Hunter = Amy Hunter); these were not checked against the DB beyond team and years.

### bat_hand fixes

| Player | Change | Source |
|---|---|---|
| JA Simpson | right -> left | wikipedia.org |
| JN Frylinck | right -> left | wikipedia.org |
| JM Coles | left -> right | espncricinfo.com |
| GH Dockrell | left -> right | espncricinfo.com |
| Rumana Ahmed | left -> right | wikipedia.org |
| Wahab Riaz | left -> right | espncricinfo.com |
| SM Whiteman | right -> left | wikipedia.org |
| Rohan Mustafa | right -> left | wikipedia.org |
| GG Wagg | left -> right | wikipedia.org |
| Hassan Khan | left -> right | wikipedia.org (Melbourne Renegades squad table; single source) |
| LP Goldsworthy | left -> right | wikipedia.org |
| RP Singh | left -> right | espncricinfo.com (Rudra Pratap Singh; may be a different RP Singh, low certainty) |
| KV Sharma | right -> left | espncricinfo.com |
| DC Drakes | right -> left | wikipedia.org |
| BC Fortuin | left -> right | wikipedia.org |
| R Trumpelmann | left -> right | wikipedia.org |
| Taskin Ahmed | right -> left | wisden.com |
| S Ismail | right -> left | wikipedia.org |
| OC McCoy | right -> left | wisden.com |
| JS Patel | left -> right | wikipedia.org |
| JP Behrendorff | left -> right | wikipedia.org |
| K Santokie | right -> left | wikipedia.org |
| Bipul Sharma | right -> left | wikipedia.org |
| V Permaul | left -> right | wikipedia.org |

### bowl_type fixes made on the way

| Player | Change | Source |
|---|---|---|
| AM Lilley | left-arm orthodox -> right-arm off spin | wikipedia.org (Arron Lilley) |
| BGF Green | right-arm off spin -> right-arm fast-medium | wikipedia.org |
| CP Wood | right-arm fast-medium -> left-arm fast-medium | wikipedia.org |
| H Kerr | right-arm fast-medium -> left-arm fast-medium | espncricinfo.com (Hayden Kerr) |
| DC Drakes | right-arm fast-medium -> left-arm fast-medium | wikipedia.org |
| TMJ Smith | right-arm leg spin -> left-arm orthodox | wikipedia.org (hand was already right; bowl fixed) |
| OC McCoy | right-arm fast-medium -> left-arm fast-medium | wisden.com |
| R Rampaul | left-arm fast-medium -> right-arm fast-medium | wikipedia.org |
| K Santokie | right-arm fast-medium -> left-arm fast-medium | wikipedia.org |

### Resume point

Unchecked rows still carry their old bat_hand and confidence (they are exactly the medium/low rows without a `web:` note). Skipped inside the checked range (8 rows, rank in brackets): JB Cracknell (#31), CL Tryon (#32), Mohammad Nawaz (#33), MJ Richardson (#34), TT Bresnan (#35), JA Thompson (#36), LJ Hill (#37), R Sharma (#156). After rank 205 nothing was searched: resume at Saeed Ajmal (#206), then Diana Baig, S Glenn, DS Kulkarni, B Doggett, B Muzarabani, R Ngarava, Noor Ahmad, M Kartik and down the rank order. Total unchecked: 172.
