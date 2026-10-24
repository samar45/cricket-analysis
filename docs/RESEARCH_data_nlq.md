# Research: data format, ball-level data, local NLQ (2026-10-24)

Labels: **[V]** verified (read or ran it today), **[C]** claimed by a source, **[G]** guess.
No zips downloaded, nothing pulled or installed. Sizes below come from HTTP HEAD requests (headers only).

## 0. Surprise first: CSV2 already has fielders, gender, team type

CLAUDE.md says "CSV2 has no fielder field". That is wrong for the current files **[V]**.

- Ball files (`data/raw/cricsheet/<key>/<id>.csv`) have columns `fielder_1, fielder_2, fielder_3`, plus `wicket_type`, `player_dismissed`, `other_wicket_type`, `other_player_dismissed`. Version line in the info file: `version,2.3.0`.
- Measured in our raw folders: caught dismissals with `fielder_1` filled: IPL 4,813 of 4,813; BBL 4,064 of 4,064; Blast 5,839 of 5,839; T20I 16,876 of 16,880 **[V]** (simple awk count; Hundred not counted because quoted venue commas break awk).
- Root cause of NULL `deliveries.fielder`: `ingestion/cricsheet.py:172` reads `df.get("fielder", df.get("fielders"))`. Real column names are `fielder_1..3`, so it always gets None **[V]**. This is a one-line ingest bug, not a format limit.
- The `_info.csv` files also carry `info,gender`, `info,team_type` (club/international), `info,event`, `info,match_type`, `info,overs`, `info,balls_per_over`, `info,match_number`, and `info,registry,people,<name>,<id>` lines **[V]** (checked on BBL match 1023581). The IPL-vs-T20I mislabel and the "no gender column" problem therefore come from our `_parse_info` dropping these, not from CSV2 lacking them.
- `data/raw/cricsheet/blast/` has 3,143 files (about 1,571 matches) **[V]**; the 0-Blast-matches fact in CLAUDE.md is stale (JOURNEY.md says Blast now loads).

Implication: switching to JSON is **optional**. Fixing the ingest parser (fielder_1..3, gender, team_type, event, stage-less) gets most of what is wanted from the files already on disk.

---

## 1. Cricsheet JSON vs CSV2

### 1.1 What JSON has (page: https://cricsheet.org/format/json/, read today) **[V]**
| Wanted | In JSON? | Field |
|---|---|---|
| Fielders on wickets | Yes | `wickets[].fielders[].name` (substitute fielders are not flagged separately; the doc has no dedicated field) |
| Gender | Yes | `info.gender` |
| match_type | Yes | `info.match_type` (Test, ODI, T20, IT20, ODM, MDM) |
| Event name / stage | Yes | `info.event.name`, `.match_number`, `.group`, `.stage` |
| Club vs international | Yes | `info.team_type` |
| Player registry ids | Yes | `info.registry.people` (name to 8-char id); `registry.venues` since v1.3.0 |
| DRS reviews | Yes | `deliveries[].review` {by, batter, decision (struck down/upheld), umpire, umpires_call}; `info.missing.reviews` flags matches with no review data |
| Replacements / subs | Yes | `deliveries[].replacements.match` (supersub, concussion, covid, injury, tactical...) and `.role` (impact-style batter/bowler swaps) |
| Powerplays | Yes | `innings[].powerplays[]` {from, to, type: batting/fielding/mandatory} |
| balls_per_over | Yes | `info.balls_per_over` (6 normally; Hundred should be 5 with 100 balls, **[G]** not opened a Hundred file to confirm) |
| Extras detail, penalty runs, target, DLS | Yes | `extras`, `penalty_runs`, `target`, `outcome.method` |
| Officials | Yes | `officials.umpires/tv_umpires/match_referees/reserve_umpires` |

### 1.2 What CSV2 already has vs lacks
- CSV2 already has: fielders (`fielder_1..3`), gender, team_type, event, match_type, overs, balls_per_over, registry people ids, umpires, referee, toss, winner, player list **[V]** (seen in file).
- CSV2 likely lacks (not seen in the BBL file; **[G]** until checked on a match with DRS): DRS reviews, replacements/subs detail, powerplay definitions, event `stage`/`group`, venue ids, penalty-run pre/post split, per-wicket fielder substitute info. These are the real extras JSON adds.

### 1.3 JSON zip names and sizes (`https://cricsheet.org/downloads/<name>`; sizes from HEAD, Last-Modified shown) **[V]**
| Competition | Zip | Size |
|---|---|---|
| IPL (men) | `ipl_male_json.zip` (also `ipl_json.zip`) | 5.19 MB (07 Oct 2026) |
| T20I men | `t20s_male_json.zip` | 14.48 MB (14 Oct) |
| T20I women | `t20s_female_json.zip` | 8.59 MB (07 Oct) |
| BBL | `bbl_male_json.zip` | 2.71 MB |
| PSL | `psl_male_json.zip` | 1.50 MB |
| CPL | `cpl_male_json.zip` | 1.83 MB |
| SA20 | `sat_male_json.zip` | 0.53 MB |
| The Hundred | `hnd_male_json.zip` / `hnd_female_json.zip` (`hnd_json.zip` = both) | 0.76 MB / 0.72 MB / 1.47 MB |
| T20 Blast | `ntb_male_json.zip` | 6.20 MB |
| WBBL (if wanted) | `wbb_female_json.zip` | 2.06 MB |
| Recently added, 30 days | `recently_added_30_male_json.zip` (`..._json.zip` both genders 1.42 MB) | 1.23 MB |
| Recently added, 7 days | `recently_added_7_male_json.zip` | 0.28 MB |
| Recently added, 2 days | `recently_added_2_male_json.zip` | listed on page, size not fetched |
| Everything | `all_male_json.zip`, `all_json.zip` | listed, size not fetched (**[G]** about 100 MB+) |

Sum of the 8 men's league zips plus T20I men and women is about 40 MB **[V]** (arithmetic of the above). Match counts on the downloads page: IPL 1,243; T20I 5,810 (men 3,627 / women 2,183); BBL 662; PSL 357; CPL 445; SA20 130; Hundred 389; Blast 1,570 **[V]**. Page note: 380 Afghanistan/APL matches are withheld **[V]**.

Gotcha: the "recently added" window is time-based by when Cricsheet added the match, so use 30-day zip for a monthly refresh and dedupe by match_id.

### 1.4 Licence **[V]**
https://cricsheet.org/licensing/ : most match data is ODC-BY (Open Data Commons Attribution): attribute public use, keep the licence notice. No share-alike per that page. Local use is fine; if the dashboard is made public, add a "Data: Cricsheet (ODC-BY)" credit.

### Recommendation (section 1)
Do **not** switch format yet: fix the CSV2 parser (`fielder_1..3`, `gender`, `team_type`, `event`, `match_type`, registry ids) first, which is S/M effort and uses the data already on disk. Move to JSON only if DRS reviews, replacements or powerplay/stage fields are wanted, then use JSON as an additional table, not a rewrite.

---

## 2. Ball-level data Cricsheet does not have

Honest headline: **no free, legal, bulk, ball-by-ball line/length/shot dataset for IPL/T20 turned up** in my searches. Search results were thin, so absence is "not found", not "does not exist".

| Source | What it has | Coverage | Join to Cricsheet | Licence/ToS risk | Effort |
|---|---|---|---|---|---|
| ESPNcricinfo commentary pages (text) | Per-ball commentary; text often says "full", "short of a length", "outside off", shot names, "dropped", "put down" | Most pro matches **[C]** by community scrapers | Match by date + teams + over.ball; ESPN match id has no map to Cricsheet id (Cricsheet registry/`info.match_id` are Cricsheet's own) | **High.** Parent Disney terms (https://disneytermsofuse.com/english/ s.2.A, 2.B(viii), 2.B(x)) restrict use to "personal, noncommercial" and prohibit scraping/data-mining/dataset building by "robot, spider, script, or other automated means" **[V]** (read). That Cricinfo falls under these terms is **[G]**: its own ToS URL returned 403 and robots.txt returned 403 to me | M-L, plus fragile |
| ESPNcricinfo internal JSON (commentary API with structured fields) | **[G]** I recall structured fields for shot type, line, length and wagon coordinates in the site's commentary feed, but could not verify: no doc found, the scraper repo I read lists none | **[G]** only some matches | same as above | **High** (same terms; undocumented API) | L, fragile |
| GitHub `mudassirkhan19/cricinfo-ballwise-scraper` | Scrapes ball-by-ball CSV from commentary links you supply; README does not mention line/length/shot **[V]**; notes errors on penalty runs | Whatever links you give | You supply the links | High (scraper of ESPN pages); licence of repo unknown | M |
| Kaggle "IPL ball by ball 2008-2026" and similar (e.g. lyc0riz, jamiewelsh2) | Cricsheet-derived: batter, bowler, runs, extras, wickets; no pitch/shot fields visible **[C]** from search snippet; baselight mirror page now shut down so I could not read columns | 2008-2026 | Same as Cricsheet (no gain) | Low-med (derived from ODC-BY) | S, but no new info |
| Kaggle line/length/shot datasets | **Not found.** Kaggle search page returned no content to me **[V]**; web search found none | n/a | n/a | n/a | n/a |
| Hawk-Eye / ball tracking | Line, length, bounce, speed. Commercial feeds only (https://www.hawkeyeinnovations.com/data) **[C]**. A 2026 arXiv paper (https://arxiv.org/abs/2608.18020) says tracking exists for about 57% of IPL, 66% of BBL, about 75% of CPL/SA20 in its dataset **[C]** (source of that data not stated, not released that I could see) | Partial | n/a | High (commercial) | Not realistic |
| Academic: IEEE DataPort "Front pitch view shot extraction and ball tracking" (https://ieee-dataport.org/documents/front-pitch-view-shot-extraction-and-ball-tracking-cricket-using-deep-learning) | 300 annotated broadcast clips, full/good/short classification **[C]** | Tiny, not match-level | Cannot join | Low-med (research licence; check) | Not useful for stats |
| Own computer vision on broadcast video | Length/line from video | Your own clips | Manual | High (broadcast copyright), plus GPU 4 GB is weak **[G]** | XL |
| Dropped catches from commentary NLP | Regex/LLM over text for "dropped", "put down", "spilled", "grassed", "missed a chance" | Only where you already have commentary text | Fuzzy by match/over.ball | Same as commentary source (High) | M once text exists |

Notes
- Cricsheet itself has no length/line/shot/wagon fields in CSV2 or JSON **[V]** (field list above). Dropped catches are not recorded either (only actual dismissals).
- Dropped catches are the one item NLP can add even from small text samples, but only after you legally have text.
- Wagon wheel and pitch map visuals in tutorials are drawn from data the authors got elsewhere **[C]** (search snippet), not Cricsheet.

### Recommendation (section 2)
Treat length/line/shot/wagon/drops as **out of scope for bulk data**: every realistic source (Cricinfo, Hawk-Eye) is either ToS-restricted (non-commercial personal use, no scraping) or commercial, and no open Kaggle set was found. If you still want it, do a one-off, personal, tiny sample (a few matches) and ask Samar to decide the ToS risk himself; otherwise spend the effort on fielder-based stats (catches, catch partnerships) that Cricsheet already supports.

---

## 3. Local natural-language query (NLQ)

### 3.1 This machine **[V]**
- `ollama --version`: **0.40.10**.
- `ollama list`: `nemotron-3.5-bolt:e4b-q4_K_M` (7.9 GB, modified 17 hours ago) and `gemma2:9b` (5.4 GB).
- GPU: RTX 3050 Laptop, 4096 MiB total, 0 used (nvidia-smi).
- `nemotron-3.5-bolt:e4b-q4_K_M` **is present**. `ollama show`: architecture gemma4, 7.5B parameters (the "e4b" is "effective 4B"; the file is 7.9 GB because it carries a vision and audio projector plus embeddings **[G]**), Q4_K_M, context 131,072, capabilities: **completion, vision, audio, tools, thinking** (thinking on by default), default temperature 1, top_k 64, top_p 0.95. Licence OpenMDW-1.1.
- `gemma2:9b`: capability list shows **completion only** (no tools) **[V]**; context 8,192. So it cannot do native tool calling; it could only do schema-constrained JSON.
- Memory fit **[G]**: 7.9 GB model will not fit fully in 4 GB VRAM; Ollama will split layers between GPU and CPU RAM (14 GB RAM total). Expect a few tokens/s up to maybe 10-15 tok/s; untested. Not tested because that would load the model (kept read-only).

### 3.2 Ollama features **[V]** (docs read today)
- **Tool calling:** supported. `POST /api/chat` with `tools: [{type:"function", function:{name, description, parameters:<JSON Schema>}}]`; response has `message.tool_calls`. Python SDK can take plain functions and builds the schema from signature plus docstring (https://docs.ollama.com/capabilities/tool-calling). Docs examples use qwen3; the model must have the `tools` capability (visible in `ollama show`).
- **Structured output:** supported. `format` accepts `"json"` or a full JSON Schema object (Pydantic `model_json_schema()` works). Docs advise also putting the schema in the prompt and using temperature 0 (https://docs.ollama.com/capabilities/structured-outputs). Docs do not say whether `format` can be combined with `tools` in one request **[V: not stated]**; treat as untested.
- Ollama's cloud does not support structured outputs; local does **[V]** (doc line).

### 3.3 Small models good at tool calling
- Candidates visible in the Ollama "tools" filter today (https://ollama.com/search?c=tools) **[V]**: `nemotron-3.5-bolt` (e4b, already installed), `tev1` (0.8b, 4b), `bonsai-2` (2b, 4b). Most others listed are 9B to 400B+.
- Many of these names are newer than my training knowledge, so I cannot give a quality ranking **[G]**. Older, well-known small tool-callers (qwen3 4B/1.7B, llama3.2 3B) may also be on the Ollama library but I did not verify the current tags.
- Practical point: for "pick 1 of 16 functions and fill 4 params" a 4B model is usually enough **[G]**; the failures are in parameter values (names, seasons), not in picking the tool.

### 3.4 Recommended architecture (no raw SQL from the LLM)
```
question -> [LLM: 1 call, tool-calling or schema-constrained JSON]
         -> {tool: "player_batting_summary", player: "kohli", competition: "ipl", season: "2024"}
         -> [Python: validate + resolve names] -> existing module (SQL via db.query)
         -> table/chart in Streamlit  (+ optional 1-line LLM summary, or none)
```
1. **Tool catalogue from the registry.** The 16 modules already register via `@register_module` and have `ModuleParams`. Generate the tools list from that registry (name, one-line description, parameter schema) so adding a module adds a tool automatically. No second place to edit.
2. **One shared parameter schema**: `player`, `team`, `opponent`, `season`, `competition` (enum of the 8), `gender`, optional `top_n`. Competition and gender should be **enums** in the schema so the model cannot invent values.
3. **Constrain the output.** Use tool calling if it behaves; fallback is `format=<schema with enum of tool names>` at temperature 0. With the schema enforced, the output is always parseable; accuracy then is only about choosing right.
4. **Fuzzy name resolution in Python, not in the LLM.** Pull player names from the registry/`players` table (Cricsheet registry gives stable ids), normalise ("V Kohli" vs "Virat Kohli", "kohli", "AB de Villiers" vs "ABD"), match with a fuzzy library or DuckDB `jaro_winkler_similarity` / `levenshtein` (**no new dependency needed**: DuckDB has them built in **[G]**, verify before use). If top score is low or two candidates are close, ask the user "Did you mean V Kohli or Virat Kohli?" Same for teams and venues (alias maps already exist in `preprocessing/`).
5. **Defaults and clarifications.** Missing season means all seasons; missing competition means ask or default to all. If no tool fits, say so, never guess.
6. **Safety.** Read-only DuckDB connection already used by `db.query`. No LLM-written SQL means no injection or runaway queries.
7. **Latency.** Run only one LLM call per question; skip the "explain the result" call unless wanted (CPU-offloaded 7.5B model makes each call slow **[G]**). Consider turning thinking off for this task (it is on by default for this model) to cut time; supported by the `thinking` capability but flag name not verified.
8. **Model choice.** Start with the already-installed `nemotron-3.5-bolt:e4b-q4_K_M` (has tools). Also test a smaller `tools` model (e.g. a 2B-4B one) as a speed alternative, but that needs a pull, so ask Samar first.

### 3.5 Evaluation
- Fixed set of **~50 questions** in a YAML/JSON file: `question`, `expected_tool`, `expected_params`. Mix: 16 tools x ~2 phrasings, 8 with spelling or nickname problems ("Kohli", "Rohit", "MS Dhoni"), 6 with ambiguous or out-of-scope questions where the expected answer is "ask/refuse".
- Metrics, scored by exact match in Python (no LLM judge needed): (a) tool accuracy, (b) parameter accuracy after name resolution, (c) valid-JSON rate, (d) mean latency per question. Also (e) **end-to-end spot check** of 5 questions: the final number matches the dashboard module output and a known real stat (IPL career runs vs Cricsheet/ESPNcricinfo), per the project's Verification rule.
- Run each question 3 times at temperature 0 and 0.3 to see variance; report counts ("n=50, 3 runs"), since one run is not proof.
- Gate: ship only if tool accuracy is high enough that Samar trusts it (suggested bar 90% tool, 85% params **[G]**); below that, keep it as "suggest a module" rather than auto-run.
- Keep the question set in `tests/` as a script, outside the normal `pytest -q` run (it needs Ollama and is slow).

### Recommendation (section 3)
Build a thin router: one tool-call (or schema-constrained JSON) to pick 1 of the 16 registered modules plus parameters, with player/team/venue fuzzy matching done in Python/DuckDB and clarification when unsure. Start with the installed `nemotron-3.5-bolt:e4b-q4_K_M` (confirmed tool-capable), judge it on a 50-question exact-match set, and only consider pulling a smaller tools model if latency on the 4 GB GPU is too slow.

---

## Open items (not chased)
- Verify CSV2 against a DRS match for review/replacement info, and a Hundred file for `balls_per_over`/`overs` (decides whether JSON adds anything).
- Verify DuckDB version has `jaro_winkler_similarity` (requirements pin duckdb 1.5.0 **[V]** in `requirements.txt`).
- ESPNcricinfo ToS page and robots.txt returned 403 to the fetch tool; the Disney-wide terms were read instead.
- Update CLAUDE.md known facts ("CSV2 has no fielder field", "Blast has 0 matches") once the lead agrees.
