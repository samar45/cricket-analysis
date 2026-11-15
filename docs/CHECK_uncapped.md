# Hand check of the "uncapped" board names (2026-11-15)

Input: `docs/REPORT_cross_league.md` (top 15 uncapped batters and bowlers, plus the "IPL unknown" lists). Method: web search per name (Wikipedia, ESPNcricinfo, iplt20.com, Cricbuzz-type profiles, news), then a read-only DB search for the surname in IPL matches. Web search snippets are second-hand; "no match found" means no source showed an IPL appearance, not that one was ruled out on the official scorecard list. Squad-only = signed, never played.

DB searched: `competition='ipl'`, batter or bowler ilike surname. Result for all 28 uncapped names (30 rows, Ajay Jadav Mandal and Aman Bhadoriya appear twice): no IPL row under any plausible Cricsheet name. So no linking miss among the uncapped names.

## Uncapped batters
| name | our status | real IPL status | source | Cricsheet name | verdict |
|---|---|---|---|---|---|
| Ajay Rohera | no IPL | none found; went unsold at auction | https://en.wikipedia.org/wiki/Ajay_Rohera | none | correct |
| Luvnith Sisodia | no IPL | squad only: RCB 2022 (injured, released), KKR 2025 (bought), KKR 2026 (replacement signed 24 May 2026). Sources say "yet to debut"; nothing seen showing a match | https://en.wikipedia.org/wiki/Luvnith_Sisodia ; https://www.iplt20.com/news/article/kkr-pick-luvnith-sisodia-as-replacement-for-injured-matheesha-pathirana | none | unclear (probably correct; no post-26 May source seen) |
| LR Chethan | no IPL | none found; IPL target only | https://www.cricket.com/news/on-ipl-radar-for-a-long-time-lr-chethan-hopes-to-finally-break-through-11122024-1731414349817 | none | correct (sources end 2024; 2025/26 auctions not checked) |
| Suraj Ahuja | no IPL | none found. Identity note: Wikipedia/ESPNcricinfo profile is the Rajasthan/Railways wicketkeeper (ex India U19 captain); the Maharaja Trophy "Coastal Kings Mangaluru" Suraj Ahuja is either the same man on a Karnataka side (one Aaj Tak profile lists Bengaluru Blasters) or a different one. Not resolved | https://en.wikipedia.org/wiki/Suraj_Ahuja | none | correct on IPL; identity unclear |
| Ankit Rajesh Kumar | no IPL | probably Ankit Kumar, Delhi (West Delhi Lions, DPL 2025 96 off 46). No IPL found; no source gives "Rajesh" | https://www.aajtak.in/live-score/cricket/ankit-kumar-profile-98946 | none | correct (identity unconfirmed) |
| Salman Nizar | no IPL | none; unsold in 2025 mega auction, CSK trial 2025 only. 2026 auction outcome not found | https://www.espncricinfo.com/cricketers/salman-nizar-826349 | none | correct (2026 not checked) |
| Dev Lakra | no IPL | none found | https://www.espncricinfo.com/cricketers/dev-lakra-1299881 | none | correct |
| Tripuresh Singh | no IPL | none; only named as a scout watch-list player | https://www.espncricinfo.com/cricketers/tripuresh-singh-1460345 | none | correct |
| Kunnummal | no IPL | Rohan Kunnummal (Kerala). No IPL found; 2026 auction outcome not found | https://cricxtasy.com/?p=134859 | none | correct (2026 not checked) |
| Aman Bhadoriya | no IPL | none found (Madhya Pradesh, Chambal Ghariyals) | https://www.espncricinfo.com/cricketers/aman-bhadoriya-1292716 | none | correct |
| Rohan Patil | no IPL | none found (Karnataka) | https://espncricinfo.com/cricketers/rohan-patil-1327710 | `DT Patil` is a different man (Dhawal/Dattatray style initials, not this Patil) | correct |
| Ashwin Hebbar | no IPL | squad only: Delhi Capitals 2022 (bought at 20 lakh); no match found | https://en.wikipedia.org/wiki/Ashwin_Hebbar | none | correct |
| Ajay Jadav Mandal | no IPL | squad only: CSK 2023-24, Delhi Capitals 2025 (no game), reportedly retained for 2026; 2026 appearances not confirmed | https://en.wikipedia.org/wiki/Ajay_Mandal ; https://www.fancode.com/sport/players/ajay-mandal/15325 | none | unclear (2026) |
| Aditya Garhwal | no IPL | none found | https://en.wikipedia.org/wiki/Aditya_Garhwal | none | correct |
| Krishna Pandey | no IPL | none found (`IC Pandey`/`MK Pandey` in DB are other people) | https://www.espncricinfo.com/cricketers/krishna-pandey-1324975 | none | correct |

## Uncapped bowlers
| name | our status | real IPL status | source | Cricsheet name | verdict |
|---|---|---|---|---|---|
| Shubhang Hegde | no IPL | none found; RCB net bowler; IPL 2026 auction outcome not found | https://en.wikipedia.org/wiki/Shubhang_Hegde | none | correct (2026 not checked) |
| Vasuki Koushik | no IPL | none found (now Goa per CricketArchive) | https://en.wikipedia.org/wiki/Vasuki_Koushik | none | correct |
| Sagar Udeshi | no IPL | none found | https://en.wikipedia.org/wiki/Sagar_Udeshi | none | correct |
| Aparajith | no IPL | Baba Aparajith (Tamil Nadu): CSK squad five seasons, no appearance | https://en.wikipedia.org/wiki/Baba_Aparajith | none | correct (identity: assumed Baba Aparajith, Chepauk Super Gillies captain) |
| Rahil Shah | no IPL | none; unsold 2017, Gujarat Lions trial only | https://en.wikipedia.org/wiki/Rahil_Shah | none (`PR Shah`, `OA Shah` are others) | correct |
| Sonu Yadav | no IPL | squad only: RCB 2023 (bought 20 lakh, no game) | https://en.wikipedia.org/wiki/Sonu_Yadav | none (`Prince Yadav`, `K Yadav` etc. are others) | correct |
| Shiva Singh | no IPL | none found (UP T20 league; Kashi Rudras then Noida Kings 2026) | https://usa.cricinfo.com/cricketers/shiva-singh-1070194 | none (DB has other Singhs only) | correct |
| Ajay Jadav Mandal | no IPL | see batter row | see above | none | unclear (2026) |
| Yuvraj Chudasama | no IPL | none; net bowler for franchises (2025 article) | https://en.wikipedia.org/wiki/Yuvraj_Chudasama | none | correct |
| Aman Bhadoriya | no IPL | see batter row | see above | none | correct |
| Suboth Bhati | no IPL | none found; unsold ~2016-17 | https://en.wikipedia.org/wiki/Suboth_Bhati | none (`R Bhatia` is a different man) | correct |
| Lalith Mohan | no IPL | none found | https://en.wikipedia.org/wiki/Lalith_Mohan | none | correct |
| Dharmendrasinh Jadeja | no IPL | none; Punjab Kings net bowler 2022 only | https://www.espncricinfo.com/cricketers/dharmendrasinh-jadeja-598935 | none (`RA Jadeja` is a different man) | correct |
| Atharva Ankolekar | no IPL | squad only: Mumbai Indians 2026 (30 lakh), knee injury, replaced by Krish Bhagat on 16 Apr 2026, 0 matches | https://www.iplt20.com/news/4295/mumbai-indians-sign-krish-bhagat-as-a-replacement-for-atharva-ankolekar | none | correct |
| Shivam Shukla | no IPL | squad only: KKR 2025 replacement for Rovman Powell; IPL squad page showed 0 matches; 2026 not checked | https://testcf.iplt20.com/teams/kolkata-knight-riders/squad-details/22386 | none (`LR Shukla`, `R Shukla` are others) | unclear (2026 not checked; likely correct) |

## "IPL unknown" lists (extra)
Those with a DB IPL record are real IPL players our link missed. Cricsheet names found by DB search; "played" is from the DB, not re-verified on the web (they are well known IPL players).

| name | our status | real IPL status | Cricsheet name (IPL matches) | verdict |
|---|---|---|---|---|
| Varun Chakaravarthy | unknown | played, 94 DB matches 2019-2026 | `CV Varun` | linking miss |
| Shahrukh Khan | unknown | played, 53 DB matches 2021-2026 | `M Shahrukh Khan` | linking miss |
| Prabhsimran Singh | unknown | played, 65 DB matches 2019-2026 | `P Simran Singh` | linking miss |
| Ravisrinivasan Sai Kishore | unknown | played, 27 DB matches 2022-2026 | `R Sai Kishore` | linking miss |
| Sharath BR | unknown | in DB IPL | `BR Sharath` | linking miss (not web-checked) |
| Tejas Baroka | unknown/doubtful | in DB IPL | `Tejas Baroka` | linking miss (exact name present; link withheld as doubtful) |
| Tushar Raheja | unknown | none found; IPL trials, 2026 auction not found | none | unclear-to-correct (no match found) |
| Siddharth Joon | unknown | none found (Delhi U19-level; M Siddharth of LSG is a different man) | none | no match found |
| Mohammed Taha | doubtful | none found as of 2025 coverage | none | no match found (2026 not checked) |
| Jhathavedh Subramanyan | unknown | SRH 2024 bought (20 lakh); no match record seen; status conflicting | none | unclear |
| S Ajith Ram | unknown | none found | none | no match found |
| Prithviraj Shekhawat | unknown | none found | none | no match found |
| Satvik Deswal | unknown | squad only: RCB 2026 (30 lakh), IPL page lists 0 matches; Puducherry (not Delhi) | none | no match found |
| Manan Bhardwaj | unknown | none found | none | no match found |
| Abhishek Pathak, Parth Chaudhary, Ritik Tada, Ankush Singh, Silambarasan, Shreesha Achar | unknown | not searched (no time per name) | none in DB | unchecked |

## Summary
- 28 distinct uncapped names (30 rows): 25 correct, 3 unclear (Luvnith Sisodia, Ajay Jadav Mandal, Shivam Shukla), 0 linking misses. Several are squad-only (Sisodia, Hebbar, Mandal, Sonu Yadav, Ankolekar, Shukla, Aparajith), which our DB cannot see by design.
- Extra: 6 linking misses among the "unknown" names (all capped).
- Not checked: 2026 auction results for Nizar, Kunnummal, Hegde, Raheja, Taha; whether Sisodia, Mandal, Shukla played in late IPL 2026.
- Identity issues: Suraj Ahuja (two possible people), Ankit Rajesh Kumar (probably Ankit Kumar of Delhi), Aparajith (assumed Baba Aparajith).
