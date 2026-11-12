# What the cached Cricbuzz JSON contains (measured 2026-11-12, IPL 2023-26)

Source: 584 cached full-commentary JSON files (292 matches x 2 innings), 100,000 items, 69,700 of them real balls (the rest are over-break summaries, promos, interviews, milestones, announcements). 0 requests used. Coverage % = share of ball items (69,700) unless stated.

## Per ball item (`commentary[].commentaryList[]`)
| Field | Example | Coverage | Cricsheet lacks it? | Use |
|---|---|---|---|---|
| commText (+ commentaryFormats bold/italic) | "Siraj to Gill, FOUR, full and outside off..." | 100% | Yes (all of line/length/shot/contact/speed, already parsed) | parsed; raw text is not stored |
| timestamp | 1681746403338 (ms epoch) | 100% | Yes | when the commentator posted the line, NOT ball time. Median 41 s between balls (p99 220 s); over 6 first ball ~94 s vs ~75 s normal, so timeouts show faintly. Rough pace of play only |
| ballNbr, overNumber | 154, 19.6 | 100% / ball items only | partly | already used for join |
| batsmanStriker.batId / bowlerStriker.bowlId | 6692 | 99.99% | Yes: a stable Cricbuzz player id (312 batter ids, 237 bowler ids) | fix name mismatches (Sooryavanshi/Suryavanshi); map to our player ids once, then names stop mattering. Also lets us use Cricbuzz player pages for hand/style |
| batsmanStriker running stats: batRuns, batBalls, batFours, batSixes, batDots, batMins, batStrikeRate | batMins 21, batDots 5 | 100% (batDots, batMins on 86% of all items, ~99% of balls) | Dots and minutes at crease: partly (dots derivable); batMins is new | minutes-at-crease, cross-check of our innings tables |
| bowlerStriker running stats: bowlOvs, bowlRuns, bowlWkts, bowlMaidens, bowlEcon, bowlWides, bowlNoballs | | 100% | derivable | integrity check only |
| batTeamScore, batTeamName (short) | 226, CSK | batTeamScore>0 on 99.2% (0 on opening balls) | derivable | check; no new info. batTeamWkts absent per ball |
| totalRuns, legalRuns | 4, 4 | 100% / 94% (missing on over-break items) | no | used |
| event | NONE, FOUR, SIX, WICKET, DROPPED, UDRS, RUNOUT_MISS, FIFTY, TEAM_FIFTY, TEAM_HUNDRED, PARTNERSHIP, HIGHSCORING_OVER, MILESTONE, over-break | 100% (comma lists) | **Yes: DROPPED (409 balls + 124 with over-break/four), UDRS review (~900 incl. with wicket), RUNOUT_MISS (147)** | drop-catch / review / missed run-out flags, cleaner than text regex |
| overSeparator (on over-break items) | {score 226, wickets 6, runs 16, o_summary "1 N1 L1 Wd N1 6 Wd W 1 1", batStrikerIds/Names/Runs/Balls, batNonStriker*, bowlIds, bowlOvers/Maidens/Runs/Wickets, overNum, timestamp} | 10,996 items (every over, both innings) | **Non-striker id at end of each over (Cricsheet has non-striker per ball already); o_summary per-ball string** | free check of over runs/wickets; nothing essential |

## Match header (`matchDetails.matchHeader`), one per file
| Field | Example | Coverage | Cricsheet lacks? | Use |
|---|---|---|---|---|
| tossResults (winner, decision) | RR, Bowling | 584/584 | no (Cricsheet has toss) | cross-check |
| dayNight, matchStartTimestamp, matchCompleteTimestamp | false, ms epoch | 100% | **Yes: day vs night flag, real start and end times** | day/night split; match duration (incl. rain) |
| venue (id, name, city, country, timezone, latitude, longitude) | Sawai Mansingh, 26.89, 75.80 | 100% | **Yes: lat/long** | map view, venue_country already exists; weather/altitude joins |
| result (type, winningTeam, winningMargin, winByRuns) | win by 6 | 100% | no | cross-check |
| revisedTarget.reason | "" | 100% (empty unless DLS) | partly | rain-affected flag |
| playersOfTheMatch (id, name, teamId, captain, keeper, substitute) | Jos Buttler id 2258 | 100% | POTM in Cricsheet already | note: `teamName` is wrong-ish (Buttler shown as "Somerset"; this is his default team, do not use) |
| team1/team2 playerDetails | [] | 0% (always empty) | - | **no playing XI in this endpoint** |
| playersOfTheSeries[] (battingStyle RIGHT/LEFT, bowlingStyle "Right Arm off break", role, playingXIChange, isOverseas, captain, keeper, substitute) | | only 8 rows total in 584 files (one player per series-end match) | **Yes, but 8 players only** | hand/style/role for a handful of award winners; check against reference/player_overrides.csv. Not a source for 300 players |

## Miniscore (`matchDetails.miniscore`): state at fetch time = end of the match, same for every ball
Contains target, partnership (balls/runs), currentRunRate, requiredRunRate, lastWicket, ppData (powerplay overs and runs), matchUdrs (reviews remaining/successful/unsuccessful per team), recentOvsStats, latestPerformance, innings score list. It is a final snapshot, not ball-by-ball, so required rate / win probability per ball is NOT in the data. Per-ball required rate has to be computed ourselves (we have target + balls). ppData.runsScored: powerplay runs (derivable). matchUdrs: **review counts per team per match (Cricsheet has individual reviews only for some matches)**.

## Not present (checked)
- Playing XI / team sheets: no (playerDetails empty).
- Impact-player substitutions: **text only**. 761 items match "impact player/sub" in 281 of 292 matches (68 of them are balls, the rest are free-text announcements such as "Impact Sub: Suryakumar Yadav comes in for Bumrah"; some hits are interview quotes about the rule, so these are leads, not clean data). No structured field, no over of entry. Parse with a regex "(X) ... (replaces|comes in for|in for) (Y)" and verify against Cricsheet's `replacements`/player lists; Cricsheet already carries impact subs for 2023+ in some form (check `matches`/`players`, not verified here).
- Batting hand / bowling style per ball: no (only in the 8 playersOfTheSeries rows). bowling style appears in text ("leg-spinner") only sometimes.
- Win probability, wagon wheel, pitch map, shot/line/length as structured fields: no.
- commentarySnippetList: video promos (headline, url, videoId), no cricket data.

## Top 5 useful new things
1. Cricbuzz player ids on every ball (fixes the ~5-8% name mismatches; gateway to style/hand via player pages).
2. Structured `event` flags: DROPPED, UDRS, RUNOUT_MISS (cleaner than the text regex for drops and reviews).
3. Day/night flag, real match start/end times, venue lat/long, DLS reason.
4. Per-ball commentary timestamps (rough pace of play; strategic timeout bump visible, but it is the post time, not delivery time).
5. Impact-sub announcements (text, ~281 matches) as a cross-check or source if Cricsheet is incomplete.
