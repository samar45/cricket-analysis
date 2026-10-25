# Research: fresh T20 data within hours or a day of a match

Date: 2026-10-25. Read-only desk research (page reads only). No sign-ups, keys, downloads or API calls.
Labels: **[V]** verified on the page (URL given). **[C]** claimed by a vendor/search snippet. **[G]** my guess. Not legal advice.
Extends `docs/RESEARCH_ball_tracking.md` section 2. I did not re-read `ingest/` code; the target is our existing `matches` + `deliveries` schema.

## 0. Surprises (read first)

1. **Cricsheet's own "recent matches" page lists only matches played 14 Oct 2026 as the newest** (Mongolia v Myanmar, Bahrain v Qatar, Thailand v Bhutan) **[V]** (https://cricsheet.org/matches/). So our DB (latest 2026-10-14) is not stale versus Cricsheet; Cricsheet itself has nothing newer at fetch time. India v NZ is not listed **[V]** (same page, plus a team-filtered fetch found none).
2. The downloads page returned numbers that look inconsistent with that (52 matches "added in the previous 2 days", 49 men's) **[V as fetched]** (https://cricsheet.org/downloads/). Possibly a cached copy, or a bulk catch-up. **Unresolved, not chased.** Do not rely on those counts.
3. **The India tour of NZ started 22 Oct**: T20Is on 22 and 24 Oct (Christchurch), 27 Oct (Wellington), 30 Oct (Auckland), 1 Nov (Hamilton) **[C]** (search summary of RevSportz/ESPN schedule; ESPN series page https://www.espn.com.au/cricket/scores/series/24469). So the 2nd T20I is 24 Oct, as Samar said; 3rd is 27 Oct, a usable test target.
4. **CricketData.org terms say commercial or business use is prohibited on the site/material and needs paid credits + own key** **[V]** (https://cricketdata.org/terms-of-use/). Instagram Reels from a monetised or brand account may count as business use **[G]**. Free tier is 100 hits/day and "a few minutes behind" **[V]** (https://cricketdata.org/pricing/).
5. I found **no stated Cricsheet cadence** anywhere (about, downloads, matches pages) **[V: not stated]**, and no RSS/e-mail alert. Only a Mastodon account, @cricsheet@deeden.co.uk **[V]** (https://cricsheet.org/about/).

## 1. Cricsheet itself

- Newest listed match: played 14 Oct 2026 **[V]**. Fetch date 25 Oct, so the visible lag is about 11 days for the newest match shown. This is one observation, not a measured lag. **[G]** Cricsheet is a one-person project, adds in batches, and lags days to weeks; the gap above fits that. Our own history can measure it: compare `matches.date` against the date Cricsheet first published each match (we do not store the publish date; `cricket update` runs could start logging it, effort S).
- Downloads: "recently added" bundles for 2, 7 and 30 days (`recently_added_2/7/30`, all/male/female, CSV and CSV2 variants), plus "recently played" bundles **[V]** (https://cricsheet.org/downloads/). We already use CSV2 zips. So `cricket update` can poll `recently_added_2_male_csv2.zip` cheaply **[G]**, instead of re-downloading everything.
- Withheld matches exist (Afghanistan; counts shown on page) **[V]**. Not relevant to India v NZ.
- Licence: Open Data Commons Attribution for most data, CC BY 4.0 for XML; commercial use not restricted, attribution required **[V]** (https://cricsheet.org/licensing/). Reel credit line: "Data: Cricsheet.org" is enough.
- Notification: no feed. Options: (a) poll the "recently added 2" bundle or the `/matches/` page daily by script (low load, polite); (b) follow the Mastodon account **[V exists]**; (c) e-mail the maintainer to ask for cadence (contact page exists) **[V]**. Note (a) costs nothing and is what Cricsheet's own bundles are for **[G]**.

Conclusion: Cricsheet will never be "within hours". For reels that need numbers the same day, a second, provisional source is needed.

## 2. APIs (free tier or cheap)

| Provider | Latency (claimed) | Scorecard / ball-by-ball | Free tier | Price | Social/reuse terms | IDs vs Cricsheet |
|---|---|---|---|---|---|---|
| CricketData.org (CricAPI) | "few minutes behind real time" **[V]** pricing page | Scorecards yes; BBB advertised **[V]** home page; which plan has it unclear **[V: not stated]** | 100 hits/day, lifetime **[V]** | S $5.99 (2k/day), M $12.99, L $29.99, U $64.99 **[V]** | Commercial/business use prohibited without paid credits **[V]**; sharing text/images on social with link-back allowed **[V]**; storing data not addressed **[V]** | Own IDs; names only **[G]** |
| Sportmonks Cricket | Live flag; refresh at your rate; no latency number **[V]** (https://www.sportmonks.com/cricket-api/) | Scorecard + BBB via `balls` include (over, bowler, batter, runs, wicket) **[V]** | Free token, no card, 14-day trial; free plan limited leagues (CSA T20 Challenge, T20 int., BBL) with 180 calls/h **[C]** api.market blog snippet | EUR 29 (26 leagues), 75, 125 **[V]** | Terms not read **[V: not read]** | Numeric player IDs (e.g. Latham 205) **[V]**; names via lineup; map by name **[G]** |
| EntitySport | "real-time" **[C]** | Commentary plans; BBB endpoint not documented on page **[V]** | No free plan; free dev token covers a few finished competitions **[V]** | from $150/mo (earlier doc) | Not stated **[V]** | Not stated |
| Cricbuzz via RapidAPI/Apify | Scrape of Cricbuzz, near-live **[C]** | Commentary text | trial-level only **[C]** | ~$1/1k requests to $20/mo **[C]** | Resold scrape; Cricbuzz has no official API **[C]** | names |
| Goalserve | live **[C]** | BBB **[C]** | none seen | from $125/mo cricket live score, $800 full **[C]** | not read | n/a |
| Sportradar / Roanuz / SportDataAPI / API-Cricket | not verified | | | | | I found no usable pricing pages **[V: not found]** |

Note: all of these give Cricsheet-like data (scorecard, per-ball runs/wicket) and nothing more.

## 3. Official and free sources

- ICC / BCCI (iplt20.com) / Cricket Australia: terms reserve content and data, personal use only; CA explicitly bans systematic retrieval without permission **[V in earlier doc]**. No ICC/NZC match-centre terms newly read (NZC not read, **[V: not read]**). Treat as no.
- ESPNcricinfo: returned 403 to my fetch of robots.txt and pages **[V]**; Disney terms bar scraping (earlier doc). No.
- Wikipedia: text is CC BY-SA 4.0; reusers must credit via link and indicate changes **[V]** (https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use). Bots must follow API etiquette and avoid undue load **[V]**. Scorecard facts (runs, wickets, overs) are not themselves copyrightable in most jurisdictions **[G]**, and a reel number needs no copied prose, so the legal exposure for hand-entered or API-fetched facts is **low [G]**. Wikipedia usually holds only a series summary, not full ball-by-ball, and T20I scorecard detail is thin **[G]**. Useful for result/score checks, not for per-ball analysis.
- Open-source scrapers on GitHub: they scrape Cricbuzz/Cricinfo, so they inherit those sites' terms. I did not review specific repos. Risk **high [G]**.
- Manual route (legal, free, slow): read the official scorecard yourself and type batting/bowling lines into a CSV. It is your own transcription of facts **[G]**. About 15-20 min per match for scorecard-level data **[G]**.

## 4. Ranked table

| # | Source | Latency | Ball-by-ball? | Free tier | Price | Social-media reuse terms | Legal risk | Effort |
|---|---|---|---|---|---|---|---|---|
| 1 | **Cricsheet** (existing), poll `recently_added_2` daily | days to weeks **[G]** (newest is 14 Oct on 25 Oct) | Yes | all free | $0 | ODC-By, attribution, commercial OK **[V]** | None | S (already built) |
| 2 | **Sportmonks free token / 14-day trial** | minutes **[C]** | Yes (`balls` include) **[V]** | free token, limited leagues; trial all **[V]** | EUR 29/mo after trial | Unknown, read ToS before use **[V: not read]** | Low if licensed **[G]** | M |
| 3 | **CricketData.org free** | minutes **[V]** | Unclear, scorecard yes | 100 hits/day **[V]** | $0 (S $5.99 for 2k/day) | Business use banned without paid plan **[V]** | Low-med (grey for reels) | S-M |
| 4 | **Manual scorecard CSV** (type from official scorecard) | hours | No (scorecard) | n/a | $0 | Facts, own transcription **[G]** | Low **[G]** | S per match, tedious |
| 5 | **Wikipedia** (result/score sanity check) | hours **[G]** | No | free | $0 | CC BY-SA, link back **[V]** | Low | S |
| 6 | Cricbuzz/Cricinfo scrapers, RapidAPI resellers | minutes | Commentary | trial | $1/1k or $20/mo **[C]** | Disney/Cricbuzz terms bar it **[V/C]** | High | M |

## 5. Recommendation

Top two: **Cricsheet as the permanent truth** (just automate the daily poll of the 2-day bundle) plus **Sportmonks as the provisional layer** (licensed, per-ball, cheap). CricketData free is a fallback for scorecard-only numbers but its terms are the riskiest fit for reels.

### Small legal experiment (needs Samar)

Goal: get the India v NZ 2nd or 3rd T20I into a `provisional_*` table within a day.
1. Samar signs up for a **Sportmonks free token** (no card; 14-day trial starts only when subscribing, so do not subscribe yet) and puts it in `.env` as `SPORTMONKS_TOKEN`. **Needs Samar: sign-up + key.**
2. Before any call, read Sportmonks' Terms of Service for caching and public-content use (I did not). If they ban storing or social reuse, stop and fall back to option 4.
3. Check the free token covers T20 internationals. If not, the trial (14 days, then EUR 29/mo) is needed. **Needs Samar's yes on any money.**
4. Fetch one finished fixture with `balls` included (a few calls, far below limits). Map to `provisional_matches` and `provisional_deliveries` with the same columns as our tables plus `source`, `fetched_at`, `provisional=true`. Player names matched to Cricsheet via `resolve_player`; unmatched names logged, not guessed. **Never insert into the real tables.**
5. `cricket update` drops provisional rows whose match appears in Cricsheet (match by date + teams) and compares the two as a free accuracy check (Cricsheet vs API totals).
6. Reel facts built from provisional rows carry a "provisional" tag in `cricket facts`.

Effort: ~1 day of a worker for the table, mapper and replace-on-publish logic; about 2 hours for the first fetch and name mapping. Cost: $0 on the free token, EUR 29/mo only if the free plan lacks T20Is and Samar chooses to continue.

Success = one match's batter and bowler totals match the official scorecard on every player, and unmatched player names under 5% **[G threshold]**.

Fallback with no money or sign-up: type one scorecard from the official site into `data/provisional/<match>.csv`; same table, scorecard-level only.

## Open items (not chased)
- Sportmonks ToS, EntitySport/Goalserve terms: not read.
- Cricsheet lag history: unmeasured (needs publish dates).
- The 52-match "previous 2 days" figure vs 14 Oct latest is unexplained.
- Whether free Sportmonks includes T20Is is a snippet claim only.
