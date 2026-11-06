# End-to-end QA of the "value" chain (2026-11-06)

Scope: runs_added, wpa, war, matchup_predict, trade, from DB to models to modules to CLI to dashboard to reel PNG. All results **measured by us**, real DB (data to 2026-10-14, IPL to 2026-05-31). Source code was not edited. `src/cricket_analytics/models/data/` is unchanged at the end (`git diff --stat` on it is empty; other modified files in the tree, `config.yaml`, `competitions.py`, `reference/ipl_auctions.csv`, `ipl_retentions.csv`, are another worker's, not mine).
Tests: `tests/test_e2e_value.py`, 45 tests, all green (about 2 min, needs the real DB).

## Result table

| # | Check | Result |
|---|---|---|
| 1a | run_expectancy rebuild (to temp dir): run_expectancy.csv, adjust.csv, venue_factor.csv | PASS, byte-identical |
| 1b | win_prob `--write` | PASS, JSON equal at 1e-9 (file is 10 bytes longer: float repr only) |
| 1c | war (war_params.json, pwar_ipl_2027.csv) | PASS (params differ in last float digit only; pwar byte-identical) |
| 1d | trade (trade_match_ra.csv 7,932 rows) and `trade beta` (215 matches, beta 0.094, -0.028 to 0.237) | PASS, byte-identical |
| 1e | matchup_model (about 4 min) | PASS, matchup_k.json equal at 1e-9 (reformatted last digits) |
| 1f | models/data restored with `git checkout`, `git status` clean there | PASS |
| 2 | CLI `--json` for runs_added (bat/bowl), wpa (players, match 981019), war (season, projected), matchup_predict (card, grid), trade (trade, squad, must_play, before_trades): 11 runs | 11/11 PASS (exit 0, valid JSON) |
| 2b | `cricket chart --aspect 9:16 --png` for 9 variants | 9/9 PASS, all 1080x1920; opened trade, wpa match, matchup card (and on a dark background war projected, trade squad) |
| 3a | Kohli 2016 = 973 runs, Buttler 2022 = 863, Bumrah 2024 = 311 balls / 20 wkts | PASS |
| 3b | WAR = (runs added - replacement x balls) / rpw for Kohli 2016, Buttler 2022, Bumrah 2024 (rpw 90.97 / 99.30) | PASS (within 0.01) |
| 3c | trade `war_2023..26` equal war module seasons; `recent_value` = 4/3/2/1 weighted (Narine 0.68, Bumrah 0.86, Kohli 0.40) | PASS |
| 3d | WPA: sum of per-ball swing = result - start WP, 3 matches (981019, 981017, 1473511) | PASS (diff 0.0) |
| 4 | Edge cases (24 inputs) | 20 PASS, see bugs F1-F5 for the rest |
| 5 | Dashboard AppTest: 5 modules default and one non-default param set, trade card HTML (default and MI/RR Hardik must-play), squad view | PASS, 0 exceptions, 0 st.error |
| 6 | `cricket ask`, 3 questions | routing mostly misses (see F7) |

## Bugs and findings (severity order; none needs a data fix)

**F1 (medium). Empty results give no explanation.** `runs_added`, `wpa`, `war` return 0 rows silently for an unknown player, a season with no data, a bad `match_id`, and for any WPA on a rain-affected match (the 2023 final 1370353 gives 0 rows). `matchup_predict` by contrast errors with "check the spelling with resolve".
Repro: `.venv\Scripts\cricket.exe run runs_added --player "Zzz Nobody" --competition ipl` prints the caveat notes and "No rows for these filters." with exit 0; `cricket run wpa --view match --match_id 1` likewise; `cricket run wpa --view match --match_id 1370353` (D/L final) likewise. The wpa caveats do say D/L is excluded, but the user is not told that this is why.

**F2 (low). War projected chart subtitle mislabels scope.** `cricket chart war --view projected --aspect 9:16 --png x.png` shows title "PROJECTED WINS, IPL 2027" with subtitle "...| ALL MEN'S T20". WAR is IPL-only (`cricket run war --competition hundred` correctly errors "WAR is measured for the IPL only"), and with no competition given it silently uses the IPL.

**F3 (low). Same-player-both-sides gives a misleading error.** `api.run("trade", team=MI, team2=RR, give="Hardik Pandya", get="Hardik Pandya")` raises "'Hardik Pandya' is not in the RR squad. Valid names: ..." (correct to refuse, but the message does not say the issue is the same player on both sides). Wrong-squad and same-team ("Pick two different teams") errors are clear.

**F4 (low). `must_play` with an unknown name says "not in the league squad"** (it lists all 250 names). Clear enough, very long.

**F5 (low). Empty give and get is accepted** and returns "no change to the best XII" for both teams (p_better 0, gives/gets "-"), not an error. Harmless; arguably a prompt would be better. With get only (no give) the squad goes to 26 and is flagged "outside 18-25", good.

**F6 (low, consistency). WAR re-centres runs added.** The `bat_runs_added` column of `war` differs from `runs_added` module for the same player-season (Kohli 2016: 162.2 vs 153.4; Bumrah 2024 bowling: 175.2 vs 179.2; Buttler 2022: 157.9 vs 147.1). Documented in VALUE_step3 ("each league-season is centred"), but neither module's caveat says the two will not match, and the column names are the same. WAR arithmetic itself is exact against its own columns.

**F7 (info, as expected). `cricket ask` and the new modules.** (default model, local Ollama, 3 questions, one run each)
| question | routed to | verdict |
|---|---|---|
| "who added the most wins in IPL 2025" | none; model said IPL 2025 "has not happened yet" | miss, and the reason is false (data exists to May 2026) |
| "Kohli v Bumrah prediction" | none; "can't answer predictions about future matches" | miss (matchup_predict exists) |
| "which IPL player has the highest WAR in 2024" | `war`, season 2024, ipl | hit; Bumrah 1.92 first, matches the module |
So `war` is found when named by its name; "wins added" and "prediction" are not mapped, and the model refuses with an invented reason. Not fixed (as instructed).

## Not bugs (checked)
- Reel PNGs have a transparent background by design (batting chart, the pre-existing module, is the same); text looks invisible on white but is correct on dark.
- `wpa` returns 0 rows for `competition=hundred` (documented: no 100-ball model); `runs_added` works for the Hundred (Buttler 799 balls, 143.1 runs added) and for Blast and women's T20I.
- Trade on bbl, t20i, hundred errors clearly ("The trade tool covers the IPL only"), also via CLI (exit 1).
- KKR has no reviewed keeper: squad view and a KKR trade run fine (rule skipped, documented).
- Competition key is `hundred`, not `the_hundred`; the wrong key errors with the valid list.
- Model rebuilds show last-digit float noise only; no real drift. Rebuild times: win_prob 12 s, war 16 s, trade 3 s, beta 2 s, matchup about 4 min.

## Not covered
No browser pass on port 8503 (AppTest only); `cricket ask` run once per question (LLM output varies); the WPA player-level view was not reconciled to match-level totals; trade odds (simulation) were compared only to the numbers in VALUE_step5 (MI 2.30 to 2.69 matches).
