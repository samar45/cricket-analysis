"""Build player_attributes.csv from deliveries/matches (read-only). Everything here is DERIVED from Cricsheet data.

Only `role` (+ its confidence/source) is used as a fact. Every column starting `hint_` is a career-majority GUESS kept for
internal gap-finding (who is missing from player_overrides.csv) and as a "usually ..." hint; it is never shown as a fact.
Keeper, bowling type, pace/spin and batting hand are facts only when they are in player_overrides.csv. The real usage
(batting position, phase) is computed per query in analysis/player_profile.py so it follows the filters.

    python -m cricket_analytics.reference.build_attributes --out src/cricket_analytics/reference/player_attributes.csv

Rules (thresholds are module constants so they can be tuned in one place; docs/WORK_phase3_5.md explains each):
  role        batter / bowler / all-rounder from the player's share of his team's balls faced and bowled.
  hint_keeper stumpings by the fielder (+ catch rate as a weaker, low-confidence signal). A guess, not a fact.
  hint_bat_slot  opener / top order / middle / finisher / tail from the median order of first appearance in the innings.
  hint_bowl_phase_role  powerplay / middle / death / all-phase from where his balls fall.
  hint_bowl_kind  pace / spin GUESS from over distribution, stumpings off his bowling, extras and byes rates.
Bowling type (leg spin, ...) and batting hand are NOT derivable from Cricsheet; they come from player_overrides.csv.
"""

import argparse
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ..sql.fragments import BALL_FACED, BOWLER_WICKET, LEGAL_BALL, phase_sql

# ---- thresholds -------------------------------------------------------------------------------------------------
MIN_ROWS_MATCHES = 3       # players with fewer matches are left out of the CSV (nothing useful to say, saves size)
MIN_MATCHES = 5            # fewer matches -> role/slot 'unknown'
BOWL_SHARE_MIN = 0.06      # >= 6% of team legal balls per match ~ 1.2 overs of 20: a real bowling contribution
BAT_SHARE_MIN = 0.045      # >= 4.5% of team balls faced per match ~ 5 balls of 120: a real batting contribution
MIN_BOWL_BALLS = 120       # fewer legal balls: bowl_phase_role / bowl_kind 'unknown'
KEEPER_STUMPINGS = 3       # >= 3 stumpings AND rate >= KEEPER_RATE per match -> keeper
KEEPER_RATE = 0.06         # a full-time keeper makes ~0.1-0.3 stumpings per match (stumpings / ALL his matches)
KEEPER_RATE_WITH_CATCHES = 0.04
KEEPER_RATE_SOMETIMES = 0.025
FINISHER_DEATH_SHARE = 0.35
PHASE_ROLE_MIN = {"powerplay": 0.45, "death": 0.40, "middle": 0.60}   # share of the bowler's balls


def features(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per player name with raw counts and shares. Super overs (innings 3+) are ignored."""
    ph = phase_sql()
    con.execute(f"""
    CREATE TEMP VIEW dd AS
    SELECT d.*, m.date, m.gender, m.competition, {ph} AS phase
    FROM deliveries d JOIN matches m ON d.match_id = m.match_id WHERE d.innings <= 2""")
    # team totals per match, to turn a player's balls into a share of what his team faced / bowled
    con.execute(f"""
    CREATE TEMP TABLE team_match AS
    SELECT match_id, batting_team AS team, COUNT(*) FILTER (WHERE {BALL_FACED}) AS team_faced, 0 AS team_bowled
    FROM dd d GROUP BY ALL
    UNION ALL
    SELECT match_id, bowling_team, 0, COUNT(*) FILTER (WHERE {LEGAL_BALL}) FROM dd d GROUP BY ALL""")
    con.execute("CREATE TEMP TABLE tm AS SELECT match_id, team, SUM(team_faced) AS team_faced, SUM(team_bowled) AS team_bowled FROM team_match GROUP BY ALL")
    # who played for whom: batter, non-striker, bowler or fielder in the match (fielding subs excluded)
    con.execute("""
    CREATE TEMP TABLE pm AS
    SELECT DISTINCT match_id, team, player FROM (
        SELECT match_id, batting_team AS team, batter AS player FROM dd
        UNION ALL SELECT match_id, batting_team, non_striker FROM dd
        UNION ALL SELECT match_id, bowling_team, bowler FROM dd
        UNION ALL SELECT match_id, bowling_team, fielder FROM dd WHERE fielder IS NOT NULL
    ) WHERE player NOT LIKE '%(sub)%'""")
    # batting order: rank of first appearance (as batter or non-striker) in each innings. The opening pair share ball 1:
    # the one on strike is No.1 (is_striker is taken AT the first appearance, not MAX over the innings, which tied them)
    con.execute("""
    CREATE TEMP TABLE order_ AS
    SELECT match_id, innings, player, ROW_NUMBER() OVER (PARTITION BY match_id, innings ORDER BY first_seq, is_striker DESC) AS pos
    FROM (SELECT match_id, innings, player, MIN(ball_seq) AS first_seq, FIRST(is_striker ORDER BY ball_seq, is_striker DESC) AS is_striker FROM (
              SELECT match_id, innings, ball_seq, batter AS player, 1 AS is_striker FROM dd
              UNION ALL SELECT match_id, innings, ball_seq, non_striker, 0 FROM dd) GROUP BY ALL)""")
    # keepers for the caught-behind count: anyone with >= 3 stumpings (the rate rule in classify() is stricter)
    con.execute("CREATE TEMP TABLE keepers AS SELECT fielder FROM dd WHERE wicket_type = 'stumped' GROUP BY 1 HAVING COUNT(*) >= 3")
    return con.execute(f"""
    WITH played AS (
        SELECT pm.player, COUNT(*) AS matches, SUM(tm.team_faced) AS team_faced, SUM(tm.team_bowled) AS team_bowled
        FROM pm JOIN tm USING (match_id, team) GROUP BY pm.player),
    gend AS (SELECT player, CASE WHEN COUNT(DISTINCT gender) > 1 THEN 'both' ELSE any_value(gender) END AS gender, MAX(date) AS last_date FROM
             (SELECT batter AS player, gender, date FROM dd UNION ALL SELECT bowler, gender, date FROM dd) GROUP BY player),
    bat AS (
        SELECT batter AS player,
               COUNT(*) FILTER (WHERE {BALL_FACED}) AS balls_faced,
               COUNT(*) FILTER (WHERE {BALL_FACED} AND phase = 'death') AS faced_death,
               COUNT(*) FILTER (WHERE {BALL_FACED} AND phase = 'powerplay') AS faced_pp
        FROM dd d GROUP BY batter),
    pos AS (SELECT player, COUNT(*) AS bat_innings, median(pos) AS bat_position FROM order_ GROUP BY player),
    bowl AS (
        SELECT bowler AS player,
               COUNT(*) FILTER (WHERE {LEGAL_BALL}) AS balls_bowled,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND phase = 'powerplay') AS pp_balls,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND phase = 'middle') AS mid_balls,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND phase = 'death') AS death_balls,
               COUNT(*) FILTER (WHERE {LEGAL_BALL} AND over_num = 0) AS first_over_balls,
               COUNT(*) FILTER (WHERE wides > 0) AS wides,
               COUNT(*) FILTER (WHERE noballs > 0) AS noballs,
               COUNT(*) FILTER (WHERE byes > 0) AS byes,
               COUNT(*) FILTER (WHERE wicket_type = 'stumped') AS stumped_off,
               COUNT(*) FILTER (WHERE wicket_type = 'caught' AND fielder IN (SELECT fielder FROM keepers)) AS caught_behind,
               COUNT(*) FILTER (WHERE {BOWLER_WICKET}) AS wickets
        FROM dd d GROUP BY bowler),
    fld AS (
        SELECT fielder AS player,
               COUNT(*) FILTER (WHERE wicket_type = 'stumped') AS stumpings,
               COUNT(*) FILTER (WHERE wicket_type = 'caught') AS catches
        FROM dd WHERE fielder IS NOT NULL GROUP BY fielder)
    SELECT p.player AS name, g.gender, g.last_date, p.matches, p.team_faced, p.team_bowled,
           COALESCE(b.balls_faced, 0) AS balls_faced, COALESCE(b.faced_death, 0) AS faced_death, COALESCE(b.faced_pp, 0) AS faced_pp,
           COALESCE(ps.bat_innings, 0) AS bat_innings, ps.bat_position,
           COALESCE(w.balls_bowled, 0) AS balls_bowled, COALESCE(w.pp_balls, 0) AS pp_balls, COALESCE(w.mid_balls, 0) AS mid_balls,
           COALESCE(w.death_balls, 0) AS death_balls, COALESCE(w.first_over_balls, 0) AS first_over_balls,
           COALESCE(w.wides, 0) AS wides, COALESCE(w.noballs, 0) AS noballs, COALESCE(w.byes, 0) AS byes,
           COALESCE(w.stumped_off, 0) AS stumped_off, COALESCE(w.caught_behind, 0) AS caught_behind, COALESCE(w.wickets, 0) AS wickets,
           COALESCE(f.stumpings, 0) AS stumpings, COALESCE(f.catches, 0) AS catches
    FROM played p LEFT JOIN gend g ON g.player = p.player LEFT JOIN bat b ON b.player = p.player
    LEFT JOIN pos ps ON ps.player = p.player LEFT JOIN bowl w ON w.player = p.player LEFT JOIN fld f ON f.player = p.player
    ORDER BY p.player""").fetchdf()


def _conf(matches: pd.Series) -> pd.Series:
    return pd.Series(np.select([matches >= 30, matches >= 10], ["high", "medium"], "low"), index=matches.index)


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add the derived columns to the output of features(). Pure function of the counts."""
    o = pd.DataFrame({"name": df.name, "gender": df.gender, "last_date": df.last_date.astype(str).str[:10],
                      "matches": df.matches.astype(int)})
    # 'both' = the same Cricsheet name is used by a man and a woman (21 names, e.g. 'RP Singh'); the numbers are then mixed
    o["balls_faced"] = df.balls_faced
    o["balls_bowled"] = df.balls_bowled
    o["bat_share"] = (df.balls_faced / df.team_faced.replace(0, np.nan)).round(3)      # share of team balls faced, over his matches
    o["bowl_share"] = (df.balls_bowled / df.team_bowled.replace(0, np.nan)).round(3)   # share of team legal balls bowled
    enough = df.matches >= MIN_MATCHES
    bats, bowls = o.bat_share.fillna(0) >= BAT_SHARE_MIN, o.bowl_share.fillna(0) >= BOWL_SHARE_MIN
    o["role"] = np.select([~enough, bats & bowls, bowls, bats], ["unknown", "all-rounder", "bowler", "batter"], "batter")
    o["role_confidence"] = _conf(df.matches)
    o["role_source"] = "derived"

    # keeper: only the keeper stumps, so stumpings are the clean signal. There is no break in the stumpings-per-match
    # rate (0.2-0.3 for full-time keepers, down to 0.04 for batters who keep sometimes), so there are 3 levels:
    #   yes       >= 3 stumpings and >= 0.06 per match; or >= 3 and >= 0.04 per match with a keeper-like catch rate
    #             (>= 0.5 catches per match; keepers average 0.53, other fielders 0.31, so catches only break ties)
    #   sometimes >= 2 stumpings and >= 0.025 per match (de Villiers, KL Rahul: kept for periods, not always)
    #   ''        no evidence. A part-timer with 1 stumping in 300 matches stays here.
    rate = df.stumpings / df.matches
    cpm = df.catches / df.matches
    yes = (df.stumpings >= KEEPER_STUMPINGS) & ((rate >= KEEPER_RATE) | ((rate >= KEEPER_RATE_WITH_CATCHES) & (cpm >= 0.5)))
    sometimes = ~yes & (df.stumpings >= 2) & (rate >= KEEPER_RATE_SOMETIMES)
    o["stumpings"], o["catches"] = df.stumpings, df.catches
    o["catches_per_match"] = cpm.round(2)
    o["hint_keeper"] = np.select([yes, sometimes], ["yes", "sometimes"], "")
    o["hint_keeper_confidence"] = np.select([yes & (df.stumpings >= 10) & (rate >= KEEPER_RATE), yes, sometimes], ["high", "medium", "low"], "")

    # batting position and slot
    o["bat_innings"] = df.bat_innings
    o["hint_bat_position"] = df.bat_position.round(1)
    death = (df.faced_death / df.balls_faced.replace(0, np.nan)).fillna(0)
    o["bat_death_share"] = death.round(3)
    has = (df.bat_innings >= MIN_MATCHES) & df.bat_position.notna()
    p = df.bat_position
    o["hint_bat_slot"] = np.select(
        [~has, p <= 2, p <= 4, (p <= 7) & (death >= FINISHER_DEATH_SHARE), p <= 6, p > 6],
        ["unknown", "opener", "top order", "finisher", "middle", "tail"], "unknown")
    o["hint_bat_slot_confidence"] = np.where(has, _conf(df.bat_innings), "")

    # bowling: phase role
    bb = df.balls_bowled.replace(0, np.nan)
    sp, sm, sd = df.pp_balls / bb, df.mid_balls / bb, df.death_balls / bb
    o["pp_share"], o["mid_share"], o["death_share"] = sp.round(3), sm.round(3), sd.round(3)
    ok = df.balls_bowled >= MIN_BOWL_BALLS
    cand = pd.DataFrame({k: v.fillna(0) for k, v in (("powerplay", sp), ("middle", sm), ("death", sd))})
    meets = pd.DataFrame({k: cand[k] >= t for k, t in PHASE_ROLE_MIN.items()})
    best = (cand.where(meets, -1)).idxmax(axis=1)
    o["hint_bowl_phase_role"] = np.where(~ok, "", np.where(meets.any(axis=1), best, "all-phase"))

    # bowling: pace/spin guess. See spin_score().
    o["stumped_off"] = df.stumped_off
    o["stumped_off_per_1000"] = (1000 * df.stumped_off / bb).round(2)
    o["noball_rate"] = (df.noballs / bb).round(4)
    o["wide_rate"] = (df.wides / bb).round(4)
    o["wickets"] = df.wickets
    o["caught_behind_share"] = np.where(df.wickets >= 20, df.caught_behind / df.wickets.replace(0, np.nan), np.nan).round(3)
    o["bye_rate"] = (df.byes / bb).round(4)
    o["first_over_share"] = (df.first_over_balls / bb).round(3)
    score = spin_score(o)
    o["hint_bowl_kind"] = np.select([~ok, score >= 2], ["", "spin"], "pace")
    unsure = score.between(1, 2) | (df.balls_bowled < 600)    # scores 1-2 were right only ~50% of the time on the seed
    o["hint_bowl_kind_confidence"] = np.where(~ok, "", np.select([unsure, df.balls_bowled >= 1200], ["low", "high"], "medium"))
    # bowl_type and bat_hand are not derivable; they come from player_overrides.csv, never from this script
    return o


def spin_score(o: pd.DataFrame) -> pd.Series:
    """Points towards 'spin' (>= 2 -> spin). Each clause is one cheap piece of evidence:
       +3  stumped off his bowling: >= 2 stumpings and >= 1 per 1000 balls (pace bowlers: max 0.3 per 1000, measured)
       +1 / -1  caught-behind share of his wickets < 10% / >= 14% (needs >= 20 wickets; pace 16% vs spin 8% on average)
       +1  >= 55% of balls in the middle overs     -1  >= 25% of balls at the death
       -1  >= 10% of balls in over 1               -1  no-ball rate >= 1%
    """
    s = pd.Series(0.0, index=o.index)
    s += np.where((o.stumped_off >= 2) & (o.stumped_off_per_1000.fillna(0) >= 1), 3, 0)
    cb = o.caught_behind_share
    s += np.where(cb < 0.10, 1, 0) - np.where(cb >= 0.14, 1, 0)
    s += np.where(o.mid_share.fillna(0) >= 0.55, 1, 0)
    s -= np.where(o.death_share.fillna(0) >= 0.25, 1, 0)
    s -= np.where(o.first_over_share.fillna(0) >= 0.10, 1, 0)
    s -= np.where(o.noball_rate.fillna(0) >= 0.01, 1, 0)
    return s


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", type=Path, default=None, help="DuckDB file (default: config database). Opened read-only.")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.db is None:
        from ..config import get_db_path
        a.db = get_db_path()
    con = duckdb.connect(str(a.db), read_only=True)
    out = classify(features(con))
    out = out[out.matches >= MIN_ROWS_MATCHES].reset_index(drop=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.out, index=False)
    print(f"wrote {len(out)} players to {a.out}")


if __name__ == "__main__":
    main()
