# Phase 2 work log (core layer + module porting)

## How to write a module (contract, 2A)
Add ONE file `src/cricket_analytics/analysis/<name>.py`. Nothing else is edited: the registry, `api.run`, CLI, JSON schema and (Phase 3) dashboard all read the registry. Template = `analysis/batting.py`.
```python
@module(id="bowling", title="Bowling stats", category="basic",          # basic | intermediate | advanced
        description="...", caveats=["..."],
        params=[*std("player", "competition", "season", "team", "opposition", "venue", "phase"),
                ParamSpec("group_by", "choice", default="player", choices=("player", "season", "phase"))])
def bowling(f: Filters, group_by="player") -> pd.DataFrame:
    where, params = f.where("bowl")                    # always "1=1 AND ..."; params bound with ?
    return query(f"SELECT ... FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE {where} ...", params)
```
- **Signature:** `fn(f: Filters, **extra) -> DataFrame`. `extra` = declared params that are not Filters fields (`player2`, `group_by`, `min_balls`, ...), defaults already filled. Return data only, no plotly, no printing, no `except: return empty`.
- **Aliases:** `deliveries d`, `matches m` (fragments hard-code `d.`). Always JOIN matches (Filters needs `m.competition/gender/season/venue/balls_per_over`).
- **Fragments** (`cricket_analytics.sql.fragments`, never re-type the rule): `BALL_FACED` (not a wide), `LEGAL_BALL` (not wide/no-ball), `RUNS_CONCEDED` (bat + wides + no-balls), `BOWLER_WICKET`, `BATTER_OUT` (striker out, not retired hurt), `IS_DOT` (no runs of any kind off a legal ball), `IS_FOUR`, `IS_SIX`, `phase_sql(d, m)` (powerplay/middle/death; Hundred = 5-ball sets 0-4/5-14/15-19). Economy = `runs_conceded * 6.0 / legal balls` always. Need a new rule? Add it to `fragments.py` with a docstring, once.
- **Filters** (`f.where(side)`): side `'bat'` (team = batting side, player = batter), `'bowl'` (team = bowling side, player = bowler), `'match'` (team/opposition = team1/team2, player and phase ignored; use it for match-level modules). All exact `=`. `competition=None` means all competitions, MEN'S ONLY; women's = key `t20i_women`. `season` = Cricsheet label (`'2007/08'`) or year (`2008` -> seasons whose first match is in 2008; IPL 2020 = `'2020/21'`). Unknown competition/phase raise ValueError. `phase` filter works for bat/bowl; for a per-phase breakdown use `phase_sql()` in SELECT/GROUP BY.
- **ParamSpec kinds:** `player, player2, team, opposition, competition, season, venue, phase, int, choice` (choice needs `choices=`). `std(...)` returns ready specs for the Filters fields. `competition`/`phase`/`choice` become enums in `registry.json_schema(id)`, so an LLM can only send valid values. `api.run` rejects unknown params and bad choices before your function runs.
- **Output column names:** snake_case, counts as INTEGER (cast `SUM(...)::INTEGER`), percentages rounded 1 dp, rates 2 dp. First columns = group keys (`batter`/`bowler`, then `competition, season` or `phase`).
- **Viz (Phase 3):** `src/cricket_analytics/viz/<module_id>.py` with `figure(result: Result) -> plotly Figure`. Only the dashboard imports `viz/`. Do not put plotly in `analysis/`.
- **Tests:** add a case in `tests/test_core.py` style (fixture DB, compare to pandas on the raw CSV) and one golden number in `tests/test_golden.py`. Run: `.venv/Scripts/python -m pytest -q`.
- **Call it:** `api.run("bowling", player="JJ Bumrah", competition="ipl")`, or `cricket run bowling --player "JJ Bumrah" --competition ipl --json`. `cricket resolve bumrah` finds exact names.

## Old B1 vs new `batting` (IPL, all seasons, measured 2026-10-24)
| player | column | old B1 | new | why |
|---|---|---|---|---|
| V Kohli | innings / not_outs | 275 / 46 | 277 / 48 | new counts a super-over innings (match 598004, 1216547) as its own innings; old merged it into the match |
| V Kohli | fifties | 69 | 68 | old merged 46 (innings 1) + 5 (super over) = 51 into one fifty; new keeps 46 |
| RG Sharma | innings / not_outs | 275 / 31 | 276 / 33 | +1 super-over innings (match 1216517); and his retired hurt (match 1527693) was an "out" in old, not in new |
| RG Sharma | average | 30.05 | 30.17 | 7331 runs / 243 outs (new) vs 244 outs (old, counted retired hurt) |
| JC Buttler | innings / not_outs | 136 / 21 | 137 / 22 | +1 super-over innings (match 1082625) |
| all three | runs, balls, SR, 4s, 6s, dot%, boundary%, hundreds, ducks, highest | same | same | - |
Other differences by design: player filter is exact (`=`), old was `ILIKE '%name%'` (so "Sharma" matched every Sharma); old column names `total_fours/total_sixes/total_balls/highest_score` are now `fours/sixes/balls/highest`; the ordering of columns changed. No bug found in the new code.

## MILESTONE log
- MILESTONE: 2026-10-24 ingest moved to `cricket_analytics/ingest/`, pyproject switched to one real package under `src/` (editable re-install blocked, see below)
- MILESTONE: 2026-10-24 db.query cached read-only + raises; competitions, fragments, filters, registry, api, cli written
- MILESTONE: 2026-10-24 `analysis/batting.py` ported; comparison with old B1 done
- MILESTONE: 2026-10-24 43 tests green; AppTest on old dashboard 0 exceptions

## Known gaps / decisions for the lead
- Non-striker run outs (5,453 balls in the DB have `player_out != batter`) count as nobody's dismissal in `BATTER_OUT` (spec as written). Kohli has 3 such in all competitions. A per-innings "dismissed" table would fix it; needs a design call.
- Super-over innings (innings 3-8, 861 balls) are included in every stat. Official records exclude them.
- Deviation from the spec: `'retired not out'` (9 rows) is also excluded from `BOWLER_WICKET` and `BATTER_OUT`.
