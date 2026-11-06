# Keepers for the 2027 IPL squads (2026-11-07)

Rule: keeper / hand come only from `player_overrides.csv`. Each new keeper value below has a web source (Wikipedia infobox role unless noted). `yes` = listed wicket-keeper; `sometimes` = source says occasional / secondary keeper. Cricsheet stumpings were used only to find candidates. Hands were filled only where the same source states them (Kartik Sharma: no hand found, left blank).

| Team | Keepers in reviewed list | New / changed this pass |
|---|---|---|
| CSK | MS Dhoni, SV Samson (yes, already) | Urvil Patel yes, left (en.wikipedia.org/wiki/Urvil_Patel); Kartik Sharma yes (indiatvnews.com, URL in file note) |
| DC | RR Pant (yes, already) | KL Rahul yes (wiki/KL_Rahul); Abishek Porel yes, left (wiki/Abishek_Porel) |
| GT | JC Buttler, T Banton (yes, already) | GD Phillips sometimes (wiki/Glenn_Phillips_(cricketer): "occasionally" keeper); Anuj Rawat yes, left (wiki/Anuj_Rawat); Kumar Kushagra yes, right (wiki/Kumar_Kushagra) |
| KKR | none before | TL Seifert yes (wiki/Tim_Seifert); FH Allen sometimes (wiki/Finn_Allen: "can also keep wicket"); A Raghuvanshi sometimes (wiki/Angkrish_Raghuvanshi: "occasional wicket-keeper") |
| LSG | N Pooran (yes, already) | JP Inglis yes (wiki/Josh_Inglis) |
| MI | RD Rickelton, Q de Kock (yes, already) | none |
| PBKS | none before | P Simran Singh yes (wiki/Prabhsimran_Singh); Vishnu Vinod yes (wiki/Vishnu_Vinod) |
| RCB | JM Cox, JM Sharma (yes, already) | PD Salt yes (wiki/Phil_Salt; lead says he mainly opens, sometimes keeps, infobox role wicket-keeper-batter) |
| RR | D Ferreira (sometimes, already) | Dhruv Jurel yes (wiki/Dhruv_Jurel); LG Pretorius yes, left (wiki/Lhuan-dre_Pretorius) |
| SRH | Ishan Kishan, H Klaasen (yes, already) | Salil Arora yes, right (crictracker.com "Who is Salil Arora? Punjab wicketkeeper", URL in file note) |

Rows: 12 new rows (source `web-verified`, hand confidence high), 5 existing rows got a keeper value (TL Seifert, KL Rahul, JP Inglis, PD Salt, GD Phillips); no keeper value overwritten, no hand conflicts.

## Not added (no source, or source says no)
- T Stubbs (DC): Wikipedia infobox says batsman; only a World Cup squad template tags him wk. Not marked.
- BM Duckett (DC): no keeping mentioned. Mayank Rawat (MI): sources say batter/off-spinner. Krish Bhagat (MI): bowling all-rounder. Daksh Kamra (KKR): all-rounder.
- Luvnith Sisodia (KKR, wicket-keeper per Wikipedia): only Cricsheet name is "LUVNITH SISODIA" (4 matches 2022, no contract match), so not added.
- D Ferreira (RR) stays `sometimes`: Wikipedia is split (lead "can also play as a wicketkeeper", playing-style section "predominantly" keeper).

## Check
Trade tool (`api.run('trade', ...)` for KKR/PBKS and RR vs CSK): the "no keeper in the reviewed list" flag no longer appears; the keeper rule applies. `player_attributes.csv` was regenerated from the current DB, so it also picked up other data added since (SMAT: 8047 players vs 7222).
