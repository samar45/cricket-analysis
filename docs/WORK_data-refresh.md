# Work log: data refresh
MILESTONE: 00:25 branch overhaul created, CLAUDE.md committed (de8525a)
MILESTONE: 00:30 build done: 285.5s, 8 comps, 0 skipped, Blast 1571 matches loaded, teams migrated 884 cells
MILESTONE: 00:32 BUG: first build had doubled league deliveries (Kohli IPL 18692 vs old 8671). Cause: league zips contain all_matches.csv, ingest treated it as a match. Fixed (isdigit stem filter), first build moved to scratchpad, rebuilding from the already-downloaded raw files
MILESTONE: 00:35 stopped by Samar (going to sleep). Rebuild killed partway; new DB unverified. Resume: docs/JOURNEY.md section 6
MILESTONE: 17:51 phase-1 builder started; incomplete cricket_analytics.duckdb deleted (Samar approved)
MILESTONE: 17:56 raw zips downloaded to data/raw/_zips_2026-10-24 and unpacked; loader/schema/leagues/cli code done, fixture tests pass; starting build
MILESTONE: 17:56 build started (8 comps, new loader, from raw files dated 2026-10-24)
MILESTONE: 17:58 t20s loaded: 1,312,737 deliveries in 103s
MILESTONE: 17:58 ipl loaded: 295,732 deliveries in 22s
MILESTONE: 17:58 bbl loaded: 153,250 deliveries in 12s
MILESTONE: 17:58 psl loaded: 83,799 deliveries in 7s
MILESTONE: 17:58 cpl loaded: 103,717 deliveries in 9s
MILESTONE: 17:58 sa20 loaded: 29,020 deliveries in 3s
MILESTONE: 17:59 hundred loaded: 38,786 deliveries in 4s
MILESTONE: 17:59 blast loaded: 360,545 deliveries in 29s
MILESTONE: 17:59 build finished in 190s
MILESTONE: 18:00 verification run; results in section below

## Phase 1 verification (2026-10-24, new DB data/cricket_analytics.duckdb, 252.7 MB)

Build: 190 s, 8 competitions, 0 files skipped, 0 warnings. Raw zips kept in data/raw/_zips_2026-10-24 (42 MB). Slim DB untouched (mtime 2026-10-22 23:42). Queries ran with the slim DB opened read-only.

### a. Freshness: new DB vs slim DB, per competition

| competition | matches_new | earliest_new | latest_new | matches_old | earliest_old | latest_old | delta |
|---|---|---|---|---|---|---|---|
| bbl | 662 | 2011-12-16 | 2026-01-25 | 662.0 | 2011-12-16 | 2026-01-25 | 0.0 |
| blast | 1,570 | 2014-05-16 | 2026-07-18 |  |  |  | 1,570.0 |
| cpl | 445 | 2013-07-30 | 2026-09-20 | 407.0 | 2013-07-30 | 2025-09-21 | 38.0 |
| hundred | 201 | 2021-07-22 | 2026-08-16 | 167.0 | 2021-07-22 | 2025-08-31 | 34.0 |
| ipl | 1,243 | 2008-04-18 | 2026-05-31 | 1,169.0 | 2008-04-18 | 2025-06-03 | 74.0 |
| psl | 357 | 2016-02-04 | 2026-05-03 | 314.0 | 2016-02-04 | 2025-05-25 | 43.0 |
| sa20 | 130 | 2023-01-10 | 2026-01-25 | 130.0 | 2023-01-10 | 2026-01-25 | 0.0 |
| t20i | 5,810 | 2005-02-17 | 2026-10-14 | 5,086.0 | 2005-02-17 | 2026-03-20 | 724.0 |

New DB split by gender (slim DB has no gender column; its `t20i` row mixes men and women. Slim competition is derived as: format T20 + tournament 'Indian Premier' = ipl, other T20 = t20i, else lower(format)):

| competition | gender | matches | earliest | latest |
|---|---|---|---|---|
| bbl | male | 662 | 2011-12-16 | 2026-01-25 |
| blast | male | 1,570 | 2014-05-16 | 2026-07-18 |
| cpl | male | 445 | 2013-07-30 | 2026-09-20 |
| hundred | male | 201 | 2021-07-22 | 2026-08-16 |
| ipl | male | 1,243 | 2008-04-18 | 2026-05-31 |
| psl | male | 357 | 2016-02-04 | 2026-05-03 |
| sa20 | male | 130 | 2023-01-10 | 2026-01-25 |
| t20i | female | 2,183 | 2009-06-18 | 2026-10-07 |
| t20i | male | 3,627 | 2005-02-17 | 2026-10-14 |

Totals: new 10418 matches / 2377586 deliveries; slim 7935 / 1812213

### b. Every slim match_id in the new DB?

Slim match_ids missing from new DB: **0** of 7935.



Matches in new DB but not in slim: 2483.

### c. Integrity

| check | value |
|---|---|
| matches duplicate match_id | 0 |
| deliveries duplicate (match_id,innings,ball_seq) | 0 |
| matches with 0 deliveries | 0 |
| deliveries with no match | 0 |
| players rows | 10,103 |
| players duplicate player_id | 0 |

### d. Labels and fills

NULL team columns:

| batting_team_null | bowling_team_null | deliveries |
|---|---|---|
| 0 | 0 | 2,377,586 |

Fielder filled on `caught` wickets, per competition and gender:

| competition | gender | caught_wickets | fielder_filled | pct |
|---|---|---|---|---|
| bbl | male | 5,387 | 5,387 | 100.0 |
| blast | male | 12,855 | 12,775 | 99.38 |
| cpl | male | 3,393 | 3,393 | 100.0 |
| hundred | male | 1,568 | 1,568 | 100.0 |
| ipl | male | 9,321 | 9,321 | 100.0 |
| psl | male | 2,760 | 2,760 | 100.0 |
| sa20 | male | 1,016 | 1,016 | 100.0 |
| t20i | female | 10,365 | 10,356 | 99.91 |
| t20i | male | 26,371 | 26,356 | 99.94 |

Fielder filled by wicket kind:

| wicket_type | n | fielder_filled |
|---|---|---|
| caught | 73,036 | 72,932 |
| bowled | 27,258 | 1 |
| run out | 11,263 | 9,083 |
| lbw | 9,668 | 0 |
| stumped | 4,131 | 4,131 |
| caught and bowled | 4,118 | 0 |
| retired hurt | 177 | 0 |
| hit wicket | 140 | 0 |
| retired out | 74 | 1 |
| obstructing the field | 16 | 0 |
| retired not out | 9 | 0 |
| hit the ball twice | 1 | 0 |

balls_per_over by competition:

| competition | balls_per_over | matches |
|---|---|---|
| bbl | 6 | 662 |
| blast | 6 | 1,570 |
| cpl | 6 | 445 |
| hundred | 5 | 201 |
| ipl | 6 | 1,243 |
| psl | 6 | 357 |
| sa20 | 6 | 130 |
| t20i | 6 | 5,810 |

Hundred max over_num / ball_num: [{'max_over_num': 19, 'max_ball_num': 9}]

Gender counts:

| gender | matches |
|---|---|
| female | 2,183 |
| male | 8,235 |

Competition counts:

| competition | matches |
|---|---|
| t20i | 5,810 |
| blast | 1,570 |
| ipl | 1,243 |
| bbl | 662 |
| cpl | 445 |
| psl | 357 |
| hundred | 201 |
| sa20 | 130 |

team_type / match_type:

| team_type | match_type | matches |
|---|---|---|
| international | T20 | 5,810 |
| club | T20 | 4,608 |

result values (old DB had NULL for ties and no-results):

| result | matches |
|---|---|
| wickets | 5,073 |
| runs | 5,036 |
| no result | 199 |
| tie | 105 |
|  | 5 |

### e. Spot checks

Name check: batters like Kohli = ['T Kohli', 'V Kohli', 'A Kohli']; bowlers like Bumrah = ['JJ Bumrah']

Kohli IPL career runs, new DB:
```sql
SELECT sum(d.runs_batter) runs, count(*) balls FROM deliveries d JOIN matches m USING(match_id) WHERE m.competition='ipl' AND d.batter='V Kohli'
```
| runs | balls |
|---|---|
| 9,346.0 | 7,127 |

Same, slim DB (format T20 + tournament Indian Premier):
```sql
SELECT sum(d.runs_batter) runs FROM deliveries d JOIN matches m USING(match_id) WHERE m.format='T20' AND m.tournament ILIKE '%Indian Premier%' AND d.batter='V Kohli'
```
| runs |
|---|
| 8,671.0 |

Kohli runs in IPL matches dated 2026 (new DB):
```sql
SELECT sum(d.runs_batter) runs, count(DISTINCT m.match_id) matches FROM deliveries d JOIN matches m USING(match_id) WHERE m.competition='ipl' AND d.batter='V Kohli' AND m.date >= DATE '2026-01-01'
```
| runs | matches |
|---|---|
| 675.0 | 16 |

Bumrah IPL wickets (bowler-credited kinds), new DB:
```sql
SELECT count(*) wickets FROM deliveries d JOIN matches m USING(match_id) WHERE m.competition='ipl' AND d.bowler='JJ Bumrah' AND d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
```
| wickets |
|---|
| 190 |

Same, slim DB:
```sql
SELECT count(*) wickets FROM deliveries d JOIN matches m USING(match_id) WHERE m.format='T20' AND m.tournament ILIKE '%Indian Premier%' AND d.bowler='JJ Bumrah' AND d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','retired out','obstructing the field')
```
| wickets |
|---|
| 186 |

IPL 2025 match count, new DB:
```sql
SELECT count(*) matches, min(date)::VARCHAR first_date, max(date)::VARCHAR last_date FROM matches WHERE competition='ipl' AND season='2025'
```
| matches | first_date | last_date |
|---|---|---|
| 74 | 2025-03-22 | 2025-06-03 |

By result:

| result | n |
|---|---|
| wickets | 37 |
| runs | 33 |
| no result | 3 |
| tie | 1 |

Slim DB IPL 2025:

| matches |
|---|
| 74 |

IPL seasons >= 2025 in new DB:

| season | matches | first_date | last_date |
|---|---|---|---|
| 2025 | 74 | 2025-03-22 | 2025-06-03 |
| 2026 | 74 | 2026-03-28 | 2026-05-31 |



### c2. Extra check: slim vs new, per match (7,935 slim matches)

For every slim match_id, ball count, total runs and wicket count are identical in the new DB (0 mismatches each, 0 missing). So no doubled data (the earlier all_matches.csv bug) and no lost balls. The 1,134 old-style (match_id, innings, over_num, ball_num) collisions in the slim DB are 0 in the new DB because `ball` is now read as text ("4.10" used to be read as 4.1); `ball_seq` is the primary key anyway.

Other measured facts:
- matches.date type: slim DB = TIMESTAMP; new DB = DATE (as db.py always declared).
- 5 matches have result NULL: 1268191, 1273144, 1407719, 1544610 (small-nation T20Is) and 804705 (Blast 2015). They have a winner but no runs/wickets margin (probably bowl-out / unusual finish, guess). Ties (105) and no-results (199) are now filled; the old loader left them NULL because `_parse_info` skipped the `outcome` key.
- 66 matches have no `info,event`; their `tournament` falls back to the label ('T20I', 'Big Bash League', ...) and `event` is NULL.
- Team aliases (Delhi Daredevils etc.) are applied at ingest to team1, team2, toss_winner, winner, batting_team, bowling_team: 0 old names left.
- 0 tournament names contain U+FFFD (the "Men?s" garbling is console-only).
- Fielder: `caught and bowled` (4,118) has no fielder_1 (the bowler is the catcher); `lbw`/`bowled` have none by nature; run out 9,083 of 11,263 have one; stumped 100%.

### f. pytest, verbatim

```
FF..............                                                         [100%]
================================== FAILURES ===================================
_______________________ test_init_schema_creates_tables _______________________

temp_db = WindowsPath('C:/Users/SAMAR/AppData/Local/Temp/pytest-of-SAMAR/pytest-7/test_init_schema_creates_table0/test.duckdb')

    def test_init_schema_creates_tables(temp_db):
        init_schema(temp_db)
        con = get_connection(temp_db)
        tables = con.execute("SHOW TABLES").fetchdf()["name"].tolist()
        con.close()
    
        assert "matches" in tables
        assert "deliveries" in tables
        assert "players" in tables
>       assert "venues" in tables
E       AssertionError: assert 'venues' in ['deliveries', 'matches', 'players']

tests\test_db.py:28: AssertionError
_______________________ test_init_schema_is_idempotent ________________________

temp_db = WindowsPath('C:/Users/SAMAR/AppData/Local/Temp/pytest-of-SAMAR/pytest-7/test_init_schema_is_idempotent0/test.duckdb')

    def test_init_schema_is_idempotent(temp_db):
        init_schema(temp_db)
        init_schema(temp_db)  # Should not raise
        con = get_connection(temp_db)
        tables = con.execute("SHOW TABLES").fetchdf()["name"].tolist()
        con.close()
>       assert len(tables) >= 5
E       AssertionError: assert 3 >= 5
E        +  where 3 = len(['deliveries', 'matches', 'players'])

tests\test_db.py:39: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_db.py::test_init_schema_creates_tables - AssertionError: as...
FAILED tests/test_db.py::test_init_schema_is_idempotent - AssertionError: ass...
2 failed, 14 passed in 1.60s
```

The 2 failures are the old `tests/test_db.py` asserting that `venues`, `seasons`, `player_match` exist; they were deliberately dropped from the schema (audit section 7) and the tests dir is not mine to edit. The other worker's 10 `tests/test_ingest.py` tests pass against the new loader.

### g. Modules and dashboard against the new DB

Config was overridden in memory only (`load_config()["paths"]["database"] = ...`), config.yaml untouched.

| Module | Params | Rows |
|---|---|---|
| B1 batting | V Kohli, IPL | 1 (total_runs 9,346, 275 innings) |
| B2 bowling | JJ Bumrah, IPL | 1 |
| B5 leaderboards | IPL, 2025 | 25 |
| I1 phase analysis | IPL | 3 |
| I2 partnerships | V Kohli, IPL | 30 |
| A1 true performance | IPL | 40 |
| A3 season awards | IPL, 2025 | 5 |
| A4 player comparison | V Kohli vs RG Sharma, IPL | 2 |
| B1 | V Kohli, T20 International | 1 |

All 9 ran without exceptions. Competition filters now return: T20 International 3,627 (men), T20 International (Women) 2,183, IPL 1,243, BBL 662, PSL 357, CPL 445, SA20 130, The Hundred 201, T20 Blast 1,570.
`streamlit.testing.v1.AppTest` on dashboard/app.py (default Overview view): 0 exceptions, 0 st.error, 6 metrics rendered. Only the known `use_container_width` deprecation warnings.
Not tested: Hundred phase SQL (still assumes 20 overs / 6-ball overs; audit F2), clicking through each module tab in the dashboard.
