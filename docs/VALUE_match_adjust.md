# Match-conditions adjustment of Runs Added (2026-11-07)

**Question.** Is 4-0-35-2 in a 260 match, or 50 off 25 when everyone else scored at 7, better judged against THAT match than against the league-season average?

**Method** (`models/match_adjust.py`). For every ball, a *match condition* c = average runs added per ball of **all other players** in the same match, same phase (powerplay / middle / death), same role, both innings. "Leave one out": the player's own balls are removed, so he never sets his own baseline. Adjusted = runs added - w x c x balls, then re-centred per league-season (average player stays 0, as in WAR). w = 0 is today's number; w = 1 fully judges against the match. Bowlers' credit already means "less conceded = more", so the same formula works for both. Use: `match_adjusted_runs_added(Filters(competition="ipl"), w)` gives per player-season bat/bowl balls, raw runs added and adjusted runs added.

**Measured by us**, all on the shipped v1 runs-added definition (no fielding credit). Small samples: IPL 2023-26 has only 135 batter and 155 bowler season-pairs, so the correlation noise is about +/-0.08. Treat every difference below as weak.

## The curve

| w | IPL 23-26 bat repeat. (consec / odd-even) | bowl repeat. | IPL 2008-26 bat | IPL 2008-26 bowl | Team-season fit r (2008-26) | (2023+) | Next-season rho ipl3, bat | bowl |
|---|---|---|---|---|---|---|---|---|
| 0 | .079 / .054 | .154 / .133 | .039 / .059 | .099 / .106 | .728 | .778 | .050 | .129 |
| 0.25 | .096 / .046 | .158 / .122 | .052 / .051 | .105 / .105 | .737 | .783 | .060 | .146 |
| 0.5 | .111 / .043 | .162 / .108 | .062 / .045 | .108 / .101 | .742 | .784 | .063 | .170 |
| **0.75** | .122 / .043 | .165 / .091 | .069 / .041 | .111 / .095 | **.742** | .784 | .072 | .191 |
| 1 | .129 / .046 | .167 / .074 | .073 / .039 | .112 / .088 | .740 | .780 | .074 | .207 |

Columns: *repeatability* = Pearson r of per-ball value between consecutive seasons (min 100 balls bat / 60 bowl) and between odd and even matches of the same season. *Team fit* = r of team-season summed runs added vs (win share - 0.5) x matches, IPL. *Next-season rho* = backtest idea (data up to X, predict IPL X+1, targets 2024-26 pooled, n about 200), predictor ipl3 = last three IPL seasons' per-ball value built from adjusted values, graded against the **raw** (unadjusted) truth so the test is not circular. Other predictor lw_all (all leagues): bat .031 -> .063, bowl .130 -> .126 (flat).

Other leagues (check): BBL bat consecutive .23 -> .25 (peak at 0.5) -> .22; BBL odd-even bat .08 -> .21 (rises); PSL is negative and noisy at every w (-0.2 .. 0, tiny pools), so it tells us nothing.

## Chosen w = 0.75

Rule: pick the w where the average of the four IPL 2008-26 repeatability numbers (bat/bowl x consecutive/odd-even) is highest, provided team-season fit does not get worse. That average is flat: .076, .078, .079, .079, .078, so 0.5 and 0.75 tie; 0.75 wins on the next-season test and ties on team fit (.742). Honest reading:

- Team fit **improves slightly** (r .728 -> .742), not worse. Expected: within a match the adjustment nets to about zero across the two teams.
- Consecutive-season repeatability and next-season prediction **rise with w**; odd-even repeatability for bowlers **falls** with w. The two repeatability tests disagree, so "more repeatable" is **not established**; every change is inside the noise except possibly the bowler next-season rho (.129 -> .191, same players in every row).
- Consistent with docs/VALUE_worth.md: match-relative rates are not clearly more repeatable. The case for w = 0.75 is mostly that it judges the performance the way Samar asked (against the match) at no cost to the team fit, not that it is a better skill estimate. It is a **suggestion for the lead**: fine to plug into the display value; do not claim it measures skill better.

## Sanity players (runs added per 100 balls; raw -> adjusted at w = 0.75)

| Player | Period | Bat balls | Bat | Bowl balls | Bowl |
|---|---|---|---|---|---|
| Bumrah | IPL 2023-26 | 20 | -43.1 -> -18.9 | 865 | 34.4 -> 36.6 |
| H Pandya | IPL 2023-26 | 690 | -14.4 -> -14.2 | 700 | -18.2 -> -19.5 |
| Klaasen | IPL 2023-26 | 1205 | 32.9 -> 33.5 | 0 | - |
| Narine | IPL 2023-26 | 469 | -13.2 -> -15.1 | 1194 | 19.7 -> 16.4 |
| Kohli | IPL 2023-26 | 1795 | 6.5 -> 7.0 | 0 | - |
| Kohli | IPL career | 6883 | 3.3 -> 0.8 | 251 | -33.0 -> -27.8 |
| Bumrah | IPL career | 86 | -31.3 -> -16.7 | 3607 | 25.0 -> 27.4 |
| Narine | IPL career | 1099 | -17.5 -> -21.2 | 4633 | 18.9 -> 17.9 |

Reads sensibly: bowlers who work in high-scoring grounds gain (Bumrah), Kohli's long career at high-scoring Bengaluru loses about 2.5 runs per 100 balls, Narine's batting slides because he bats when others also tear it up. Klaasen's 33 per 100 balls is untouched because his extra is against the match too.

## Three highest-scoring IPL matches: a bowler's 4 overs, raw -> adjusted (runs added, w = 0.75)

| Match | Bowler | Raw | Adjusted | Match average c per ball (bowling) |
|---|---|---|---|---|
| SRH v RCB 2024-04-15 (549 runs) | Topley | -30.7 | -18.4 | -0.7 |
| | Cummins | +13.2 | +28.0 | -0.8 |
| DC v PBKS 2026-04-25 (529) | Bartlett | -33.4 | -25.5 | -0.5 |
| | Arshdeep | +1.2 | +17.9 | -0.8 |
| SRH v RR 2025-03-23 (528) | Archer | -40.1 | -32.6 | -0.4 |
| | Patel | +8.3 | +21.1 | -0.7 |

Everyone in such a game is down 0.5-0.8 runs per ball; the adjustment hands back about 12-17 runs per 24 balls for the good spells and 8-12 for the worst, so a bowler who merely held his own in a slog gets credit and a bad spell is still a bad spell.

Not done: no change to `models/backtest.py` (the check lives in `match_adjust.predictive()` and reuses `backtest.run` with a swapped table); not plugged into WAR v2 (fielding rows and Worker B's files untouched); v1 definition only. Reproduce: `match_adjust.curve()`, `match_adjust.predictive()` (about 4 minutes).
