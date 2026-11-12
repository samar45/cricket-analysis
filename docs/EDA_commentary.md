# EDA of parsed Cricbuzz commentary (IPL 2017-2026)

Data: 156,367 balls (the 158,923 parsed balls that join to a Cricsheet ball in a trusted-result match), 10 seasons. All numbers measured 2026-11-13 by `experiments/eda_commentary.py` and `experiments/feature_repeatability.py` on `models/commentary_features.py`. Charts: `docs/img/eda_coverage_speed.png`, `eda_outcome.png`, `eda_mnar.png`. Bowler type (pace/spin) comes only from the reviewed list (`reference/player_overrides.csv`); 2,407 balls have no reviewed type.

Commentator era: there is no commentator field in the Cricbuzz JSON, so "era" is a season-group proxy (2017-19, 2020-22, 2023-26). Coverage of length and line climbs steadily with season (44% to 72%), so this is likely the style of whoever writes the text, not what happened on the pitch.

## Key findings
1. **Length and line coverage depends on season, pace/spin and phase; contact, shot and delivery coverage is flat.** Length 44% (2017) to 72% (2025), pace 74% vs spin 34% (spinners rarely get a length word), middle overs 50% vs 66-67% powerplay/death. Contact stays 17-21% in every season, shot 60-67%, delivery 11-18%, quoted speed 3-13% (6% in 2025).
2. **Missing is not at random for contact, delivery, line and shot, but nearly at random for length.** Contact is present 2.3x the average on wickets and 1.6x on dots, but 0.5x on sixes and 1-3 run balls. Delivery type is 1.7x on wickets. Line is 0.72x and shot 0.83x on sixes (commentators write "SIX!" and skip the description). Length is 0.97-1.11x on every outcome. So any contact / delivery rate is "how often it was worth mentioning", not a pure ball rate; treat as a style/skill signal, never as a probability.
3. **Outcomes match cricket sense, which is a check on the parser.** Yorker: 1.15 runs/ball (lowest), 3.8% sixes vs 6.5% overall; full toss 1.95 runs/ball; short 1.83 and bouncer 1.72 runs/ball with 9.4% wickets on the bouncer. Edges score 1.01 runs/ball vs 1.40 overall (15% wickets); `middle` contact 3.23 runs/ball; `miss` 0.37.
4. **Speed**: pace median 135.5 kph (5-95%: 112-147), spin 93.5 (83-104). Slower balls drag pace tails below 120.
5. **Death overs**: yorker 13.5% and full toss 14.8% of known lengths (vs 2-3% powerplay); powerplay is length/back-of-a-length. Pace vs spin barely differ in boundary rate (21.0% vs 15.0%) but pace goes for more per ball (1.45 vs 1.31).

## Sanity-check violations (counts, see section 5 table)
- Yorker went for six 191/4,985 (3.8%, below the 6.5% base rate: fine). Inside edge for six: 2/4,441.
- Quoted speed outside 50-160: 5 of 14,125 (parse errors such as 10 and 943 kph, ignored by the fill). Pacers under 100 kph: 43 (0.4%). Spinners above 110: 53 (1.5%). My soft bands (spin 70-100, pace 120-155) flag 14% and 12.5%, but these are flighted fast spinners (95th pct 104) and slower balls / medium pacers (5th pct 112), not errors.
- Parser vs Cricsheet: Cricbuzz FOUR vs runs_batter != 4: 313/18,936 (1.7%, byes and overthrows); SIX: 17/9,758; WICKET without a Cricsheet wicket 16/7,783; Cricsheet non-run-out wicket without Cricbuzz WICKET 20/7,308 (0.3%). Join is sound.
- **Real problem: reviewed-spin bowlers are credited with "bouncer" on 535/6,375 (8.4%) and "yorker" 226 (4.3%), swing delivery 146/2,801 (5.2%).** The bouncer regex catches "short ball"/"short and rising", which for a spinner is just a short ball. Bowl-style labels are 0.7% wrong for spin-type deliveries on pacers (44/6,401), which is fine. Fix in the parser: do not map "short ball" to bouncer for reviewed spinners. Not changed here.
- `line = wide` means "wide of off stump", not a Cricsheet wide: only 1,280 of 5,561 Cricsheet wides that have a line carry the label `wide` (the rest say "outside off"), and 5,311 of 6,591 `line=wide` balls are legal. So the wide=>line rule fills only the 71 wides with no line text.
- `shot=leave` with runs off the bat: 55/1,890 (2.9%).

## Fills (flag columns `speed_src`, `length_src`, `line_src`)
| field | text | filled_bowler | filled_rule | NA |
|---|---|---|---|---|
| speed (kph) | 14,120 | 130,578 | 0 | 11,669 |
| length | 92,335 | 0 | 0 | 64,032 |
| line | 85,848 | 0 | 71 | 70,448 |
| delivery | untouched | | | |
Speed: a bowler-season median (>=10 valid quoted balls, else bowler overall) written on every other ball of that bowler, only for reviewed pace (median >= 100) or spin (<= 110). NA remains for 5,512 pace balls, 3,978 spin and 2,407 unreviewed-type balls. **A filled speed is a bowler constant: it adds no ball-level information, so use it only to describe bowlers, never as a ball-level predictor.** Length has no deterministic rule from the other parsed fields, so none is filled; fills are deliberately tiny.

## Features and repeatability
Files (gitignored): `data/external/commentary/features_bat.csv`, `features_bowl.csv`, `features_team_fielding.csv`, `repeatability_{bat,bowl}.csv`. Season-to-season r = Pearson r of the season-demeaned feature in year t and t+1, same player, at least 60 balls faced/bowled in both seasons (batters 462 pairs, bowlers 418). `r_ra` and `r_wpa` are correlations with that player's mean runs added / WPA per ball (positive = good for the player), same season and next season. The comparison baselines are `bnd_pct`, `sr`, `out_pct` (batters) and `econ_ball`, `bnd_pct`, `wk_pct` (bowlers) on the same sample. Compare to `docs/VALUE_worth.md` (balls per boundary 0.49 IPL, bowler boundary 0.60; the 2017+ sample here gives 0.40 and 0.50). Worth / WAR defaults are not changed.


## Which features repeat (section 7 summary)
**Batters** (462 pairs): boundary % 0.40 (baseline), **false-shot % 0.39 (CI 0.31-0.46)**, clean-boundary % 0.35, strike rate 0.27, SR vs full 0.26, SR vs outside off 0.26, edge % 0.25, dismissal % 0.23, miss % 0.23. Everything vs short/good length or dismissal-by-length is 0.15 or lower with wide CIs (200-235 pairs, noise).
**Bowlers** (418 pairs): slower-ball % 0.71, length entropy 0.70, yorker % 0.64, **induced false-shot % 0.57**, short-ball % 0.51, boundary % 0.50 (baseline), induced miss % 0.38, **economy 0.32**, induced edge % 0.31, **wicket % 0.13**.
- Beats the existing metrics on repeatability: batter false-shot % beats strike rate (0.39 vs 0.27) and dismissal rate (0.23), and ties boundary %. Bowler induced false-shot % beats economy (0.57 vs 0.32) and wicket % (0.13), and beats boundary % (0.50) a little (CIs overlap).
- But repeatability is not value. Batter false-shot % has r -0.08 with runs added (same season) and -0.07 next season: it is mostly attacking intent plus luck of mention, not a quality measure. Bowler false-shot % has r +0.08 / +0.11 with runs added / WPA (same season), about 0 next season. The bowler mix features (slower ball, yorker, entropy) are stable style markers (r 0.6-0.7) with |r| <= 0.11 to runs added: they describe how a bowler bowls, not how well.
- Same-season value links remain with the existing stats (strike rate r 0.66, boundary % 0.53 with batter runs added; economy -0.73 and boundary % -0.57 for bowlers). Death-over yorker % (136 pairs) has +0.16 / +0.18 with next-season runs added / WPA: the only feature with a positive forward link, but the sample is small and the CI wide; leads, not findings.
- Fielding: 1,739 balls with a drop (event DROPPED or text), mean 19.6 further runs by that batter in the innings; 428 missed run-out balls. The commentary has no fielder name, so drops are counted per fielding team-season (`features_team_fielding.csv`) and per bowler / batter in the player tables, not per fielder.
- DRS per team-season is not built: the review counts (`udrs`) exist only for 2023+ and carry Cricbuzz team ids with no mapping to team names in the files; only ball-level UDRS event flags are available. Left as a follow-up.
- Caveat: false-shot and contact flags are mentioned on 17-21% of balls and 2.3x more on wickets, so they are mention rates; the player means may partly reflect which commentators covered his matches.

# Appendix: full tables

### 1 Coverage (% of balls with the field)

**by year**

```
      length  line  shot  contact  delivery  sp_ok  balls
year                                                     
2017    43.7  41.0  60.0     17.8      11.2    2.7  13654
2018    50.4  47.5  60.1     18.3      16.8    4.1  13758
2019    48.8  47.3  60.4     16.8      15.7    7.8  14241
2020    53.4  45.5  62.0     17.2      13.1   11.4  14510
2021    54.9  50.3  63.7     19.0      15.7   12.2  14413
2022    58.8  55.1  66.9     20.3      14.4   10.0  17912
2023    63.4  58.7  66.7     19.6      15.6    9.8  17307
2024    69.4  66.0  67.3     20.0      15.7   11.3  16902
2025    71.6  67.5  66.6     20.4      15.2    6.7  16555
2026    68.6  62.7  66.3     20.9      13.6   12.7  17115
```

**by era**

```
         length  line  shot  contact  delivery  sp_ok  balls
era                                                         
2017-19    47.6  45.3  60.1     17.6      14.6    4.9  41653
2020-22    55.9  50.7  64.4     18.9      14.4   11.1  46835
2023-26    68.2  63.7  66.7     20.2      15.0   10.1  67879
```

**by phase**

```
           length  line  shot  contact  delivery  sp_ok  balls
phase                                                         
death        67.0  54.6  58.0     23.1      18.5    8.1  36102
middle       50.4  54.0  66.3     16.1      15.0    8.9  71780
powerplay    65.9  56.4  66.0     20.6      11.5    9.9  48485
```

**by bowl_kind**

```
           length  line  shot  contact  delivery  sp_ok  balls
bowl_kind                                                     
pace         73.6  56.8  62.8     21.4      15.0   10.5  98123
spin         33.6  51.4  66.8     15.1      14.4    6.4  55837
```

### 2 Distributions

speed (kph) by bowler type

```
             count     mean     std   min     5%    50%     95%    max
bowl_kind                                                             
pace       10333.0  133.429  10.341  75.5  112.5  135.5  147.00  157.3
spin        3559.0   93.523   6.685  68.5   83.0   93.5  103.91  132.9
```

length mix by phase (% of known)

```
length     back of a length  bouncer    full  full toss  length   short  short of length  yorker
phase                                                                                           
death                 6.428    8.076  25.804     14.759  13.020  11.981            6.467  13.465
middle                9.641    6.527  28.427      4.944  19.151  19.027            8.850   3.434
powerplay            13.224    5.135  24.838      2.663  25.821  12.494           13.736   2.087
```

line mix by phase (% of known)

```
line        body     leg  middle  outside off   wide
phase                                               
death      1.226  11.138  16.772       61.819  9.044
middle     0.841  13.425  19.244       60.300  6.190
powerplay  1.062  12.881  17.830       62.689  5.538
```

shot mix (% of known) by bowler type

```
shot        block     cut   drive   flick  glance   hook  leave   loft    pull  punch  reverse sweep  scoop   slog   steer   sweep
bowl_kind                                                                                                                         
pace       11.854   8.161  15.590  10.198   1.656  0.503  2.459  3.578  15.686  5.880          0.198  3.750  3.969  12.671   3.846
spin       14.617  10.824  12.704   7.785   0.951  0.008  0.914  3.676   7.852  9.353          1.696  1.305  3.153  12.107  13.055
```

### 3 Outcome by category (balls faced)

by length

```
                  balls  runs_ball  bnd_pct  six_pct  wk_pct  ra_bat
length                                                              
back of a length   9024      1.111   13.087    3.502   3.546  -0.085
bouncer            5780      1.723   27.976   10.813   9.377  -0.022
full              23774      1.629   23.740    8.282   5.329   0.196
full toss          5998      1.951   28.560    9.937   5.702   0.389
length            17844      1.243   16.342    6.013   5.066  -0.107
short             13396      1.827   28.971    8.622   6.091   0.285
short of length    8914      1.192   15.044    4.297   3.590  -0.037
yorker             4985      1.148   13.801    3.831   5.717  -0.316
```

by line

```
             balls  runs_ball  bnd_pct  six_pct  wk_pct  ra_bat
line                                                           
body           801      1.753   25.468   10.487   7.865   0.065
leg          10230      1.498   20.772    5.865   4.154   0.123
middle       14644      1.222   13.227    5.613   7.204  -0.188
outside off  49301      1.268   17.478    4.552   4.365  -0.033
wide          5311      1.891   29.373    3.220   3.615   0.460
```

by contact

```
              balls  runs_ball  bnd_pct  six_pct  wk_pct  ra_bat
contact                                                         
bottom edge     204      0.686    8.824    0.000   9.804  -0.795
edge           5610      1.038   19.822    0.873  15.437  -0.974
inside edge    4441      0.748    7.228    0.045   8.737  -0.789
leading edge   1229      0.724    4.963    0.895  16.843  -1.309
middle         1621      3.231   62.184   25.725   8.822   1.293
miss           9312      0.372    5.939    2.685   8.011  -0.965
mistimed       4362      0.916    6.488    2.132  11.027  -0.688
top edge       1897      1.752   29.151    9.594  30.522  -1.186
```

by delivery

```
                  balls  runs_ball  bnd_pct  six_pct   wk_pct  ra_bat
delivery                                                             
arm ball            102      0.863    6.863    1.961    1.961  -0.333
back of the hand     19      1.842   36.842   10.526   15.789  -0.519
carrom              492      1.061   11.179    6.301   11.382  -0.674
cutter             1223      1.142   14.800    4.579   11.611  -0.447
doosra                2      0.000    0.000    0.000  100.000  -5.423
flipper              36      0.917   11.111    5.556   13.889  -0.317
googly             3907      1.049   12.106    5.529   10.136  -0.559
inswinger          2009      1.084   13.987    4.032    6.471  -0.335
knuckle ball        270      1.463   23.333    9.630   23.704  -0.860
leg break          1285      1.045   12.607    5.058   12.607  -0.567
off break           448      1.174   14.286    7.143   14.286  -0.702
outswinger          706      0.802   13.739    0.992    6.374  -0.577
slower ball       11399      1.443   19.379    8.053    8.036  -0.072
topspinner           42      0.833    9.524    4.762   21.429  -0.508
```

by bowl_kind

```
           balls  runs_ball  bnd_pct  six_pct  wk_pct  ra_bat
bowl_kind                                                    
pace       93781      1.451   20.991    6.446   5.497   0.037
spin       54670      1.310   15.048    6.398   4.602   0.013
```

### 4 Missing-not-at-random: P(field present) by outcome class

```
          length    line    shot  contact  delivery   sp_ok  balls
outcome                                                           
1-3 runs  57.089  53.102  64.959   10.647    13.239   9.336  67934
dot       58.269  55.538  67.324   30.264    15.758  10.138  46606
four      67.866  56.352  66.351   15.553    11.606   7.337  18672
six       64.647  40.180  53.639   10.291    14.750   6.652   9756
wicket    61.748  50.045  65.881   44.161    25.698   7.957   7767
```

relative coverage by outcome (1.00 = season-phase average)

```
          r_length  r_line  r_contact  r_shot  r_delivery
outcome                                                  
dot          0.968   1.046      1.596   1.026       1.116
1-3 runs     0.982   1.003      0.564   1.000       0.893
four         1.114   1.044      0.800   1.016       0.821
six          1.048   0.724      0.521   0.826       0.967
wicket       1.013   0.943      2.317   1.028       1.708
```

### 5 Sanity checks

```
                                                     check  flagged     of      %                                        note
0                                            yorker -> six      191   4985   3.83                        all balls 6.5% sixes
1                                           yorker -> four      497   4985   9.97                             all balls 12.4%
2                             spinner speed outside 70-100      497   3559  13.96                                            
3                              pacer speed outside 120-155     1293  10333  12.51                                            
4                quoted speed outside 50-160 (parse error)        5  14125   0.04                                            
5                                 pacer quoted speed < 100       43  10333   0.42                                            
6                                         edge -> boundary     2065  13381  15.43  overall 18.9%; runs/ball edge 1.01 vs 1.40
7                                       inside edge -> six        2   4441   0.05                                            
8                        miss (beaten) -> runs off bat > 0     1169   9312  12.55             text can say miss then edge-run
9                 Cricsheet wide with line other than wide     4281   5561  76.98            line missing on 71 of 5632 wides
10                      line=wide but not a Cricsheet wide     5311   6591  80.58             wide of off but played is legal
11               Cricbuzz FOUR, Cricsheet runs_batter != 4      313  18936   1.65                 byes / overthrow boundaries
12                          Cricbuzz SIX, runs_batter != 6       17   9758   0.17                                            
13                    Cricbuzz WICKET, no Cricsheet wicket       16   7783   0.21                                            
14  Cricsheet wicket (not run out) without Cricbuzz WICKET       20   7308   0.27                                            
15                            shot=leave, runs off bat > 0       55   1890   2.91                                            
16                spin-type delivery, reviewed-pace bowler       44   6401   0.69                                            
17                    swing delivery, reviewed-spin bowler      146   2801   5.21                                            
18                           bouncer, reviewed-spin bowler      535   6375   8.39                                            
19                            yorker, reviewed-spin bowler      226   5227   4.32                                            
```


### 7 Repeatability tables
```
BATTERS (min 60 balls both seasons)
            feature  baseline  pairs  r_repeat  ci_lo  ci_hi  r_ra_same  r_wpa_same  r_ra_next  r_wpa_next
           bnd_pct      True    462      0.40   0.32   0.47       0.53        0.47       0.05        0.06
         false_pct     False    462      0.39   0.31   0.46      -0.08       -0.02      -0.07       -0.06
     clean_bnd_pct     False    462      0.35   0.27   0.43       0.53        0.45       0.06        0.09
                sr      True    462      0.27   0.18   0.35       0.66        0.56       0.08        0.05
        sr_vs_full     False    235      0.26   0.14   0.38       0.46        0.43       0.13        0.12
 sr_vs_outside_off     False    368      0.26   0.16   0.35       0.46        0.36       0.10        0.10
          edge_pct     False    462      0.25   0.16   0.33      -0.12       -0.04      -0.03       -0.05
           out_pct      True    462      0.23   0.14   0.31      -0.50       -0.52       0.02       -0.02
          miss_pct     False    462      0.23   0.14   0.31      -0.00        0.01      -0.00       -0.03
      edge_bnd_pct     False    462      0.20   0.11   0.28       0.08        0.15      -0.02       -0.10
       sr_vs_short     False    215      0.15   0.02   0.28       0.31        0.27       0.07        0.07
       mistime_pct     False    462      0.14   0.05   0.23       0.01       -0.00      -0.11       -0.02
        sr_vs_good     False    200      0.13  -0.00   0.27       0.37        0.32       0.10        0.06
      out_vs_short     False    215      0.10  -0.03   0.23      -0.13       -0.16       0.07        0.08
    edge_bnd_share     False    430      0.09  -0.00   0.19      -0.11       -0.01      -0.02       -0.10
       out_vs_good     False    200      0.07  -0.07   0.20      -0.25       -0.21      -0.08       -0.13
out_vs_outside_off     False    368      0.01  -0.09   0.11      -0.17       -0.09       0.09        0.04
       out_vs_full     False    235     -0.15  -0.27  -0.02      -0.11       -0.06       0.10        0.10

BOWLERS
            feature  baseline  pairs  r_repeat  ci_lo  ci_hi  r_ra_same  r_wpa_same  r_ra_next  r_wpa_next
        slower_pct     False    418      0.71   0.66   0.76      -0.11       -0.04      -0.05       -0.11
       len_entropy     False    385      0.70   0.64   0.74      -0.11       -0.04      -0.07       -0.10
        yorker_pct     False    385      0.64   0.58   0.70      -0.05       -0.02      -0.04       -0.02
         false_pct     False    418      0.57   0.50   0.63       0.08        0.11      -0.04        0.00
         short_pct     False    385      0.51   0.43   0.58       0.04        0.02      -0.04        0.00
           bnd_pct      True    418      0.50   0.42   0.57      -0.57       -0.49      -0.17       -0.20
death_fulltoss_pct     False    136      0.48   0.33   0.60      -0.09       -0.09       0.01        0.00
  death_yorker_pct     False    136      0.43   0.28   0.55      -0.00        0.00       0.16        0.18
          miss_pct     False    418      0.38   0.30   0.46       0.05        0.05       0.00        0.03
         econ_ball      True    418      0.32   0.23   0.40      -0.73       -0.61      -0.18       -0.21
          edge_pct     False    418      0.31   0.22   0.39       0.15        0.15       0.01        0.03
       mistime_pct     False    418      0.23   0.14   0.32      -0.10       -0.02      -0.13       -0.11
            wk_pct      True    418      0.13   0.04   0.22       0.50        0.48       0.01       -0.05
```
