# Phase 2 work log (core layer + module porting)

## How to write a module (contract, 2A)
Add ONE file `src/cricket_analytics/analysis/<name>.py`. Nothing else is edited: the registry, `api.run`, CLI, JSON schema and (Phase 3) dashboard all read the registry. Template = `analysis/batting.py`.
```python
@module(
    id="bowling",
    title="Bowling stats",
    category="basic",  # basic | intermediate | advanced
    description="...",
    caveats=["..."],
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("group_by", "choice", default="player", choices=("player", "season", "phase")),
    ],
)
def bowling(f: Filters, group_by="player") -> pd.DataFrame:
    where, params = f.where("bowl")  # always "1=1 AND ..."; params bound with ?
    return query(
        f"SELECT ... FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {where} ...",
        params,
    )
```
- **Signature:** `fn(f: Filters, **extra) -> DataFrame`. `extra` = declared params that are not Filters fields (`player2`, `group_by`, `min_balls`, ...), defaults already filled. Return data only, no plotly, no printing, no `except: return empty`.
- **Aliases:** `deliveries d`, `matches m` (fragments hard-code `d.`). Always JOIN matches (Filters needs `m.competition/gender/season/venue/balls_per_over`).
- **Fragments** (`cricket_analytics.sql.fragments`, never re-type the rule): `BALL_FACED` (not a wide), `LEGAL_BALL` (not wide/no-ball), `RUNS_CONCEDED` (bat + wides + no-balls), `BOWLER_WICKET`, `DISMISSAL` (`player_out` left, striker OR non-striker; group on `d.player_out`), `BATTER_OUT` (the striker was the one out), `MATCH_OUTCOME` CTE (real winner + bat_first), `sql/innings.py::batter_innings`, `IS_DOT` (no runs of any kind off a legal ball), `IS_FOUR`, `IS_SIX`, `phase_sql(d, m)` (powerplay/middle/death; Hundred = 5-ball sets 0-4/5-14/15-19). Economy = `runs_conceded * 6.0 / legal balls` always. Need a new rule? Add it to `fragments.py` with a docstring, once.
- **Filters** (`f.where(side)`): side `'bat'` (team = batting side, player = batter), `'bowl'` (team = bowling side, player = bowler), `'match'` (team/opposition = team1/team2, player and phase ignored; use it for match-level modules). All exact `=`. `competition=None` means all competitions, MEN'S ONLY; women's = key `t20i_women`. `season` = Cricsheet label (`'2007/08'`) or year (`2008` -> seasons whose first match is in 2008; IPL 2020 = `'2020/21'`). Unknown competition/phase raise ValueError. `phase` filter works for bat/bowl; for a per-phase breakdown use `phase_sql()` in SELECT/GROUP BY.
- **ParamSpec kinds:** `player, player2, team, opposition, competition, season, venue, phase, int, choice` (choice needs `choices=`). `std(...)` returns ready specs for the Filters fields. `competition`/`phase`/`choice` become enums in `registry.json_schema(id)`, so an LLM can only send valid values. `api.run` rejects unknown params and bad choices before your function runs.
- **Output column names:** snake_case, counts as INTEGER (cast `SUM(...)::INTEGER`), percentages rounded 1 dp, rates 2 dp. First columns = group keys (`batter`/`bowler`, then `competition, season` or `phase`).
- **Viz (Phase 3):** `src/cricket_analytics/viz/<module_id>.py` with `figure(result: Result) -> plotly Figure`. Only the dashboard imports `viz/`. Do not put plotly in `analysis/`.
- **Tests:** add a case in `tests/test_core.py` style (fixture DB, compare to pandas on the raw CSV) and one golden number in `tests/test_golden.py`. Run: `.venv/Scripts/python -m pytest -q`.
- **Call it:** `api.run("bowling", player="JJ Bumrah", competition="ipl")`, or `cricket run bowling --player "JJ Bumrah" --competition ipl --json`. `cricket resolve bumrah` finds exact names.

## Old B1 vs new `batting` (IPL, all seasons, re-run 2026-10-24 after the 2B fixes; old = `modules/basic/batting.py` on the same DB)
| player | column | old B1 | new | why |
|---|---|---|---|---|
| V Kohli | total_runs / balls / fours | 9,346 / 6,930 / 847 | 9,336 / 6,926 / 845 | new drops 2 super-over innings (5 runs, 2 balls, 1 four each: matches 598004, 1216547) |
| V Kohli | innings | 275 | 275 | same by coincidence: old merged the super over into its match (-2) and lacked nothing else; new has 277 innings minus the 2 super overs |
| V Kohli | not_outs / average | 46 / 40.81 | 44 / 40.42 | 2 non-striker run outs (matches 548367, 1304059) were "not out" in old; new = 9,336 / 231 outs |
| V Kohli | fifties | 69 | 68 | old merged innings 46 + super over 5 into one 51 |
| RG Sharma | total_runs / balls | 7,331 / 5,517 | 7,329 / 5,514 | 1 super-over innings dropped (match 1216517: 2 runs, 3 balls) |
| RG Sharma | innings | 275 | 276 | match 501269: run out at the non-striker's end without facing a ball = an innings of 0 (old had no row for him) |
| RG Sharma | not_outs / average | 31 / 30.05 | 31 / 29.91 | outs 245 (new) vs 244 (old): +2 non-striker run outs (matches 1254058, 501269), -1 retired hurt (match 1527693, not an out) |
| RG Sharma | ducks | 18 | 19 | the 0-ball run out in 501269 is a duck |
| JC Buttler | total_runs / balls | 4,647 / 3,105 | 4,646 / 3,103 | super-over innings dropped (match 1082625: 1 run, 2 balls) |
| JC Buttler | not_outs / average | 21 / 40.41 | 19 / 39.71 | 2 non-striker run outs (matches 1082614, 1175359) were "not out" in old; (the 3rd, 1082625, was already out in old because of his super-over dismissal) |
| all three | strike rate, dot%, boundary%, hundreds, highest | | | tiny SR/dot% shifts only from the dropped super-over balls |
Other differences by design: player filter is exact (`=`), old was `ILIKE '%name%'`; old columns `total_fours/total_sixes/total_balls/highest_score` are now `fours/sixes/balls/highest`; ordering of columns changed.
Decision (documented in the module caveats): an innings exists when the batter faced a ball OR was dismissed. A batter left not out at the non-striker's end without facing a ball has no innings (cannot be told apart from "did not bat" without joining `non_striker`).

## MILESTONE log
- MILESTONE: 2026-10-24 ingest moved to `cricket_analytics/ingest/`, pyproject switched to one real package under `src/` (editable re-install blocked, see below)
- MILESTONE: 2026-10-24 db.query cached read-only + raises; competitions, fragments, filters, registry, api, cli written
- MILESTONE: 2026-10-24 `analysis/batting.py` ported; comparison with old B1 done
- MILESTONE: 2026-10-24 43 tests green; AppTest on old dashboard 0 exceptions

## Known gaps / decisions for the lead
- ~~Non-striker run outs count for nobody~~ FIXED in 2B (DISMISSAL via player_out).
- ~~Super-over innings included~~ FIXED in 2B (`Filters.include_super_overs=False` default). Verified: every delivery with innings > 2 (861 balls) belongs to one of 74 tied matches, over_num 0 only.
- Deviation from the spec: `'retired not out'` (9 rows) is also excluded from `BOWLER_WICKET` and `DISMISSAL`; 2B also excludes 'hit the ball twice' (1 row) from `BOWLER_WICKET`.

## 2B -> 2C (read this, it changes core behaviour)
- MILESTONE: 18:17 `viz/__init__.py` has `PALETTE` (primary/secondary/good/bad/neutral/light/accent/phases) and `subtitle(result)`. Use them.
- **Super overs are off by default:** `Filters.where('bat'|'bowl')` now ends with `d.innings <= 2` (nothing is added when `include_super_overs=True`). Modules that read `deliveries` with side='match' add `f.innings_sql()` themselves. `tests/test_core.py::test_filters_empty_is_men_only` was updated (one line).
- **Dismissals:** `BATTER_OUT` is unchanged (the striker was out). New `DISMISSAL` = `player_out` left the crease (striker OR non-striker; not retired hurt / retired not out). For innings/average counts group on `d.player_out`, not `d.batter`. `sql/innings.py::batter_innings(f, groups)` does it: one row per batter x match x innings (runs, balls, fours, sixes, dots, out). Reuse it, do not re-write it.
- `BOWLER_WICKET` now also excludes 'hit the ball twice' (1 row in the DB).
- New `MATCH_OUTCOME` CTE (`WITH mo AS ({MATCH_OUTCOME})`): real winner + bat_first per match. `matches.winner` is NULL for all 74 super-over matches (ingest does not store the eliminator winner); `mo.winner` fills it from the last super-over pair (73 resolved, 1 level: match 729315, KKR v RR 2014, decided on boundaries).
- NOTE: an earlier append of this section was lost when I rewrote the "Old B1 vs new" block (I truncated the file tail). If 2C appended lines to this file between 18:17 and 18:26, please re-add them.

## 2B (bowling, teams, venues, matchup, partnerships, form)
- MILESTONE: 18:17 Part 1 done (super overs off by default; dismissals from player_out); 7 analysis modules + 7 viz files written
- MILESTONE: 18:24 tests/test_analysis_b.py written, `pytest -q` all green
### Decisions
- Innings = faced a ball OR was dismissed (see the B1 table above). Retired hurt / retired not out are not outs.
- Bowling: runs conceded = bat + wides + no-balls; economy per 6 LEGAL balls; dot% = dots / legal balls; boundary% = (4s+6s) / balls faced by batters (no-balls in, wides out); hauls per innings; best_figures "w/r" via max wickets then min runs.
- Teams: win% = won / (won+lost). Super-over matches are won/lost by the super-over winner (MATCH_OUTCOME); `tied` = tie with no winner. bat_first = batting_team of innings 1.
- Venues: lowest_total counts only COMPLETED innings (10 wickets or full overs/100 balls), otherwise rain-cut innings give 2 and 7 as "lowest" (seen at Chinnaswamy and Eden before the fix).
- Partnerships: a stand ends at any `player_out` event (incl. retired hurt); wicket_no counts real dismissals only. Phase filter not offered. Checked: sum of stand runs = innings total (fixture, and all IPL: `test_real_partnerships_add_up_to_innings_totals`).
- Form: `window` rows (innings/spells), `rolling_runs` = mean runs, `rolling_sr` = sum(runs)*100/sum(balls); matches pandas rolling on 275 Kohli IPL innings.
### Old B2 vs new `bowling` (IPL, all seasons, measured)
| player | column | old B2 | new | why |
|---|---|---|---|---|
| JJ Bumrah | wickets / runs_conceded | 190 / 4,469 | 187 / 4,441 | old included 3 super-over wickets and 28 runs (`include_super_overs=True` gives exactly 190 / 4,469) |
| JJ Bumrah | economy | 7.51 | 7.34 | old "legal balls" = `extra_type IS NULL`, which drops the 79 legal balls that had byes/leg-byes (old divisor too small); plus super over |
| YS Chahal | economy | 8.17 | 8.05 | same: 57 bye/leg-bye balls missing from old legal balls (runs 5,417 and wickets 233 identical) |
| R Ashwin | economy | 7.29 | 7.20 | same, 57 balls (runs 5,652, wickets 187 identical) |
| all three | bowling_strike_rate | 18.80 / 17.08 / 24.88 | 19.42 / 17.33 / 25.19 | same legal-ball difference |
| all three | dot_ball_pct -> dot_pct | 38.45 / 31.65 / 32.99 | 40.0 / 32.7 / 34.1 | old = dots / ALL balls incl. wides and no-balls; new = dots / legal balls |
| all three | boundary_pct | 15.1 / 14.8 / 11.9 | 14.7 / 14.5 / 11.8 | old denominator = `extra_type IS NULL` balls; new = balls faced (no-balls in, wides out) |
| all three | innings, 4s/6s conceded, wides, no-balls | same | same | (Bumrah: 405/136/119/41 old vs 403/135/118/40, super over) |
| all three | best_wickets_in_match -> best_figures | 5 / 5 / 4 | 5/10, 5/40, 4/34 | new gives the figures, not just wickets |
Column renames: total_wickets->wickets, total_runs_conceded->runs_conceded, bowling_average->average, bowling_strike_rate->strike_rate, total_fours_conceded->fours_conceded, total_sixes_conceded->sixes_conceded, total_wides/total_noballs->wides/no_balls. New: balls, dots, three_plus, five_plus, best_figures. The old pie's made-up dot estimate (F18) is gone: the viz uses real counts.
### Requests for the lead (files I may not touch)
- `registry.py`: add a `bool` ParamSpec kind so `include_super_overs` can be exposed in `json_schema` / CLI / dashboard. Today it is only reachable by calling a module's `fn` with `Filters(include_super_overs=True)` (see tests/test_golden.py). `api._FILTER_FIELDS` already picks the field up automatically.
- Ingest: store the super-over winner (`matches.winner` is NULL in all 74 super-over matches; `MATCH_OUTCOME` derives it meanwhile).

## 2C (impact, true_performance, season_awards, compare, death_overs, pace_vs_spin)
- MILESTONE: 18:20 `sql/extra.py` (ratio, bat_cols, bowl_cols), `analysis/{impact,true_performance,season_awards,compare,death_overs,pace_vs_spin}.py` written
- MILESTONE: 18:55 6 viz files, `tests/test_analysis_c.py` (32 tests, 4 on the real DB), old-vs-new comparison on the real DB done
- Replaced: I3 -> `impact`, A1 -> `true_performance`, A3 -> `season_awards`, A4 -> `compare`, A5 -> `death_overs` (renamed, F5), A2 -> `pace_vs_spin`.
- Params: weights of `impact` are integer percents/points (`bat_weight_pct=60, wicket_points=20, econ_par=8, econ_weight_pct=40`) because ParamSpec has no float kind. `pace_vs_spin` stays `category="advanced"`: the registry only accepts basic/intermediate/advanced, so "experimental" is in the title, the description (first word) and the first caveat. Needs a registry change if a real category is wanted.
- Dismissals: `compare` and `death_overs` (batting) use `sql.innings.batter_innings` (player_out based, same as `batting`), so their averages equal the batting module's. `pace_vs_spin` counts bowler-credited wickets only.
- Unclassified bowlers (< 120 legal balls in the competition) are `Unknown` in pace_vs_spin; the old module forced them to `Pace` (F6).

### Old vs new, IPL, all seasons, real DB (measured 2026-10-24; old modules run on the same new DB; old filter = ILIKE on the name)
Common causes: **SO** = old counts super-over balls (new drops innings 3+); **LB** = old "legal ball" is `extra_type IS NULL`, so balls with byes/leg-byes vanish from legal balls (new: `wides=0 and noballs=0`); **RC** = old runs conceded is `runs_total - byes/legbyes` (keeps penalty runs); new = bat + wides + no-balls; **PH** = old phase uses fixed over bounds (same as new for 6-ball cricket).

| module | player | column | old | new | why |
|---|---|---|---|---|---|
| impact | V Kohli | total_runs / batting_sr | 9346 / 134.9 | 9336 / 134.8 | SO (10 runs, 4 balls) |
| impact | V Kohli | economy / dot_pct | 8.9 / 21.0 | 8.8 / 20.7 | LB + RC |
| impact | V Kohli, RG Sharma | avg_impact, bowl_impact, total_impact | NaN | 29.63 / 90.7 / 8177.2 (Kohli) | F17: `NULLIF(legal_balls, 1)` made any match with one legal ball NaN, which poisons the whole SUM |
| impact | V Kohli | bat_impact | 8094.1 | 8086.5 | SO |
| impact | RG Sharma | total_runs / economy / dot_pct | 7331 / 8.16 / 26.4 | 7329 / 8.02 / 26.0 | SO, LB, RC |
| impact | JJ Bumrah | (row) | not in output | present: 187 wkts, bowl_impact 4068.5 | old with a player filter returns the *opponents* who batted against / bowled to him (ILIKE on both sides), then LIMIT 30 cut Bumrah off |
| true_performance | V Kohli | matches | 513 | 275 | old summed per-phase match counts |
| true_performance | V Kohli | raw_sr / total_balls / sr_powerplay / sr_death | 134.9 / 6930 / 129.7 / 188.4 | 134.8 / 6926 / 129.55 / 188.38 | SO only (phase SRs match to rounding) |
| true_performance | V Kohli | true_sr / sr_adjustment | 141.8 / -6.9 | 137.69 / +2.89 | baseline: old pooled all seasons and used the plain mean of three phase SRs as "league SR"; new = per (competition, season, phase) and ball-weighted. Old adjustment was raw - true although its chart said "+ = tougher"; new = true - raw |
| true_performance | RG Sharma | true_sr | 138.6 | 134.59 | same baseline change |
| true_performance | JJ Bumrah | wickets / runs_conceded / raw_economy | 190 / 4469 / 7.51 | 187 / 4441 / 7.34 | SO (checked: 3 wkts and 28 runs in his super overs, so wickets and runs reconcile exactly); economy also LB (3572 vs 3631 legal balls) |
| true_performance | JJ Bumrah | true_economy / econ_adjustment | 7.41 / +0.10 | 7.04 / -0.30 | baseline change + the above |
| true_performance | B Kumar | raw_economy / true_economy | 7.90 / 7.86 | 7.71 / 7.46 | LB + baseline |
| season_awards | IPL 2024 death batters, middle batters | top 3 | same players, same runs/balls | same | none |
| season_awards | IPL 2024 powerplay bowlers | Boult / Starc / B Kumar economy | 7.15 / 10.19 / 8.46 | 7.03 / 10.07 / 8.18 | LB (old legal balls 224 vs 228 for Boult); wickets and runs equal |
| season_awards | IPL 2024 debutants | batters / bowlers top 3 | same players and runs | same; bowler economy 10.71 -> 10.18 (Coetzee) | LB |
| compare | V Kohli vs RG Sharma | total_runs / average / ducks / SR | 9346 / 40.81 / 24 / 134.86 (Kohli) | 9336 / 40.42 / 12 / 134.8 | SO; average uses player_out dismissals (231 outs; non-striker run outs count); ducks |
| compare | V Kohli | highest / fifties / hundreds | 87 / 7 / 0 | 113 / 68 / 9 | **old bug (not in the audit):** these were computed on per-phase rows, not innings. New matches `batting` exactly (checked in tests) |
| compare | JJ Bumrah vs B Kumar | wickets / economy / best_wickets | 190 / 7.51 / 4 | 187 / 7.34 / 5 | SO (3 wkts), LB; best_wickets old = best single phase |
| compare | Bumrah | boundary_pct | 15.1 | 14.7 | old denominator was legal balls, new (like `bowling`) balls faced by batters |
| death_overs | V Kohli | overall_sr / death_sr / index | 134.9 / 188.4 / 139.7 | 134.8 / 188.38 / 139.8 | SO; death dismissals 57 -> 60 (old excluded run outs) |
| death_overs | JJ Bumrah | death_balls / death_economy / index | 1383 / 8.43 / 89.1 | 1423 / 8.19 / 89.6 | LB + RC (death wickets 102 = 102) |
| pace_vs_spin | V Kohli | vs pace / vs spin runs | 5996 / 3350 (+0 other) | 5777 / 3307 (+252 Unknown) | old forced unclassified bowlers to Pace (F6), SO, and the classifier counts legal balls now (e.g. Ashwin 4868 -> 4710 balls; labels unchanged: Ashwin/Chahal Spin, Bumrah/B Kumar Pace) |
| pace_vs_spin | Kohli | dismissals vs pace / spin | 162 / 60 | 160 / 58 | SO (2 + 2) |
| pace_vs_spin | team RCB | rows | old returned 30 rows for every team (team filter did not restrict the batting side) with RCB = 29,748 runs vs pace | RCB only: 1477 + 27,700 + 14,834 runs | F1 (innings 1 = team1 guess) fixed with `batting_team` |
No difference I cannot explain. Possible bugs found in the OLD modules beyond the audit: A4 highest/fifties/hundreds/ducks per-phase bug; I3 player filter returning opponents; A1 `matches` inflated.

### Findings / surprises for the lead
- `pace_vs_spin` heuristic is weak: in `bowler_classification` with `season=2024` YS Chahal is labelled Pace (24.1% of his 2024 balls at the death, limit is 20%); with all seasons he is Spin. Leg-spinners used at the death flip. Hence batter/team modes label from the whole competition career.
- `death_overs` batters' index is naturally above 100 for almost everyone (Kohli 139.8, league typical about 125-130, guess); use `true_performance` for a league-adjusted number.
- `death_overs` default floors (15 death balls batting / 30 bowling) still let tiny samples top the list (e.g. WG Jacks 25 death balls, index 183.8). Raise `min_balls` for rankings.
