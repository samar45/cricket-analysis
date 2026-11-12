"""Leak-free features for the direct ML models (S3/S4).

Everything here is PRIOR-ONLY: a feature for a match on date D is computed from matches with date < D
(matches on the same date do not see each other). So the same table is valid for every rolling test year;
no per-year refit is needed and deleting later matches never changes an earlier row (tested).

Pieces
  innings_features(inn)  scoring level (drift), shrunk venue / team effects -> one row per (match, innings)
  player_priors(states, inn) shrunk career runs-per-ball of the striker / non-striker before each match
  build_features(states, inn) -> state table with the frozen FEATURES columns (men's rows only)
  tune_k(inn, year)      pick the shrinkage strengths on last train season (prior-only, no GBM needed)
Shrinkage: effect = sum_of_residuals / (n + k)  (partial pooling toward 0 = the competition level).
k = 0 gives the raw, unshrunk per-venue / per-team mean (the "overfit" variant for S4).
"""

import numpy as np
import pandas as pd

COMPS = ["bbl", "blast", "bpl", "cpl", "hundred", "ilt20", "ipl", "lpl", "mlc", "psl", "sa20", "smat", "t20i"]

STATE = ["balls_left", "wickets", "runs", "crr", "runs_l30", "wk_l30", "innings", "target", "runs_needed", "rrr",
         "rr_diff", "comp_code", "impact_era", "season_year"]
LEVEL = ["lvl_ew", "lvl_season"]
EFFECTS = ["venue_eff", "venue_n", "bat_team_eff", "bowl_team_eff"]
PLAYER = ["striker_rpb", "ns_rpb", "striker_balls_prior", "ns_balls_prior", "striker_faced", "ns_faced"]
FEATURES = STATE + LEVEL + EFFECTS + PLAYER  # FROZEN: tests/test_ml_features.py pins this list
FEATURE_SETS = {
    "none": STATE + LEVEL,  # no venue / team / player effects
    "full": FEATURES,
    "no_level": [c for c in FEATURES if c not in LEVEL],  # ablation: no drift-aware level
}

PRIOR_MEAN, PRIOR_W = 150.0, 3.0  # level prior (runs, pseudo-matches) for a competition's first matches
HL_LEVEL, HL_TEAM = 60.0, 12.0  # half-lives: matches (competition level), first innings (team form)
K_PLAYER = 60.0  # pseudo-balls for a batter's shrunk runs-per-ball
K_SEASON = 5.0  # pseudo-matches pulling the season-to-date mean toward the EW level


def _decay(h):
    return 0.5 ** (1.0 / h)


def innings_features(inn, k_venue=15.0, k_team=10.0, hl_level=HL_LEVEL, hl_team=HL_TEAM):
    """One row per (match_id, innings): lvl_ew, lvl_season, venue_eff, venue_n, bat_team_eff, bowl_team_eff.

    Level / effects are learned from non-reduced FIRST innings only (second innings are cut short by the chase).
    Effects are in runs per 120 balls: venue vs competition level; team vs level + venue.
    """
    inn = inn.sort_values(["date", "match_id", "innings"], kind="stable")
    dl, dt = _decay(hl_level), _decay(hl_team)
    lvl, season, ven, bat, bowl = {}, {}, {}, {}, {}
    rows = []
    for _, day in inn.groupby("date", sort=True):
        upd = []
        for r in day.itertuples(index=False):
            ck = (r.competition, r.gender)
            s, w = lvl.get(ck, (0.0, 0.0))
            ew = (s + PRIOR_W * PRIOR_MEAN) / (w + PRIOR_W)
            ss, sn = season.get((ck, r.season_year), (0.0, 0.0))
            sea = (ss + K_SEASON * ew) / (sn + K_SEASON)
            vk = (r.gender, r.venue)
            vs, vn = ven.get(vk, (0.0, 0))
            veff = vs / (vn + k_venue) if vn + k_venue > 0 else 0.0
            bs, bw = bat.get((r.gender, r.batting_team), (0.0, 0.0))
            ws_, ww = bowl.get((r.gender, r.bowling_team), (0.0, 0.0))
            rows.append((r.match_id, r.innings, ew, sea, veff, vn,
                         bs / (bw + k_team) if bw + k_team > 0 else 0.0,
                         ws_ / (ww + k_team) if ww + k_team > 0 else 0.0))
            if r.innings == 1 and not r.reduced:
                upd.append((ck, r, ew, veff, vk))
        for ck, r, ew, veff, vk in upd:  # update AFTER the whole day was read
            x = float(r.final_total)
            s, w = lvl.get(ck, (0.0, 0.0))
            lvl[ck] = (s * dl + x, w * dl + 1.0)
            ss, sn = season.get((ck, r.season_year), (0.0, 0.0))
            season[(ck, r.season_year)] = (ss + x, sn + 1)
            vs, vn = ven.get(vk, (0.0, 0))
            ven[vk] = (vs + x - ew, vn + 1)
            res = x - ew - veff
            for d, key in ((bat, (r.gender, r.batting_team)), (bowl, (r.gender, r.bowling_team))):
                a, b = d.get(key, (0.0, 0.0))
                d[key] = (a * dt + res, b * dt + 1.0)
    cols = ["match_id", "innings", "lvl_ew", "lvl_season", "venue_eff", "venue_n", "bat_team_eff", "bowl_team_eff"]
    return pd.DataFrame(rows, columns=cols)


def player_priors(states, inn, lvl_by_match, k_player=K_PLAYER):
    """Shrunk career runs-per-ball (and balls) of every batter BEFORE each match; key (match_id, gender, batter).

    Runs of a ball are the change in team runs after it, credited to the striker (extras included: approximate).
    Career pooled over all competitions of the same gender. Shrunk toward the match's competition level / 120.
    """
    g = states.groupby(["match_id", "innings"], sort=False)
    d = (g.runs.shift(-1) - states.runs)
    ok = d.notna() & (states.striker.fillna("") != "")
    b = pd.DataFrame({"match_id": states.match_id[ok], "batter": states.striker[ok], "runs": d[ok], "balls": 1})
    b = b.groupby(["match_id", "batter"], as_index=False).sum()
    meta = inn.drop_duplicates("match_id").set_index("match_id")[["date", "gender"]]
    b = b.join(meta, on="match_id").sort_values("date", kind="stable")
    mu = lvl_by_match / 120.0
    tot, out = {}, []
    for _, day in b.groupby("date", sort=True):
        for r in day.itertuples(index=False):
            R, B = tot.get((r.gender, r.batter), (0.0, 0.0))
            m = mu.get(r.match_id, 1.25)
            out.append((r.match_id, r.gender, r.batter, (R + k_player * m) / (B + k_player) if B + k_player > 0 else m, B))
        for r in day.itertuples(index=False):
            R, B = tot.get((r.gender, r.batter), (0.0, 0.0))
            tot[(r.gender, r.batter)] = (R + r.runs, B + r.balls)
    return pd.DataFrame(out, columns=["match_id", "gender", "batter", "rpb", "balls_prior"])


def _faced(s):
    """Balls the striker / non-striker had faced earlier in the innings (vectorised)."""
    sk = s.striker.fillna("")
    sf = s.groupby(["match_id", "innings", sk], sort=False).cumcount().to_numpy()
    pos = np.arange(len(s))
    kS = s.match_id.astype(str) + "|" + s.innings.astype(str) + "|" + sk
    kN = s.match_id.astype(str) + "|" + s.innings.astype(str) + "|" + s.non_striker.fillna("")
    codes, _ = pd.factorize(pd.concat([kS, kN], ignore_index=True))
    left = pd.DataFrame({"pos": pos, "k": codes[len(s):]})
    right = pd.DataFrame({"pos": pos, "k": codes[: len(s)], "f": sf + 1})
    m = pd.merge_asof(left, right, on="pos", by="k", allow_exact_matches=False)
    return sf, m.f.fillna(0).to_numpy()


def build_features(states, inn, k_venue=15.0, k_team=10.0, k_player=K_PLAYER, hl_level=HL_LEVEL):
    """State table (men's rows only) with FEATURES columns added. Use k_*=0 for the raw / unshrunk variant."""
    s = states[states.gender == "male"].reset_index(drop=True)
    ifeat = innings_features(inn, k_venue, k_team, hl_level)
    lvl = ifeat.drop_duplicates("match_id").set_index("match_id").lvl_ew
    pri = player_priors(s, inn, lvl, k_player)
    s = s.merge(ifeat, on=["match_id", "innings"], how="left")
    for side, col in (("striker", "striker"), ("ns", "non_striker")):
        p = pri.rename(columns={"batter": col, "rpb": f"{side}_rpb", "balls_prior": f"{side}_balls_prior"})
        s = s.merge(p[["match_id", col, f"{side}_rpb", f"{side}_balls_prior"]], on=["match_id", col], how="left")
        s[f"{side}_rpb"] = s[f"{side}_rpb"].fillna(s.lvl_ew / 120.0)
        s[f"{side}_balls_prior"] = s[f"{side}_balls_prior"].fillna(0)
    s["striker_faced"], s["ns_faced"] = _faced(s)
    bb = s.balls_bowled.clip(lower=1)
    s["crr"] = np.where(s.balls_bowled > 0, s.runs / bb * 6, s.lvl_ew / 20)
    g = s.groupby(["match_id", "innings"], sort=False)
    s["runs_l30"] = s.runs - g.runs.shift(30).fillna(0)
    s["wk_l30"] = s.wickets - g.wickets.shift(30).fillna(0)
    rrr = (s.runs_needed / s.balls_left.clip(lower=1) * 6).clip(0, 36)  # capped: 1 ball left makes it explode
    s["rrr"] = np.where((s.innings == 2) & (s.balls_left > 0), rrr, np.nan)
    s["rr_diff"] = s.crr - s.rrr
    s["comp_code"] = s.competition.map({c: i for i, c in enumerate(COMPS)}).astype(int)
    s["impact_era"] = s.impact_era.astype(int)
    return s


def tune_k(inn, year, k_venue_grid=(10, 30, 100, 300, 1000), k_team_grid=(3, 10, 30)):
    """Choose (k_venue, k_team) for a test `year`: lowest squared error of level+venue+team prediction of men's
    first-innings totals in season year-1. Features at year-1 use only earlier matches, so no test data is touched."""
    val = inn[(inn.innings == 1) & (inn.gender == "male") & ~inn.reduced & (inn.season_year == year - 1)]
    best = None
    for kv in k_venue_grid:
        for kt in k_team_grid:
            f = innings_features(inn[inn.season_year < year], kv, kt).merge(val[["match_id", "innings", "final_total"]])
            mse = ((f.final_total - f.lvl_ew - f.venue_eff - f.bat_team_eff - f.bowl_team_eff) ** 2).mean()
            if best is None or mse < best[0]:
                best = (mse, kv, kt)
    return best[1], best[2], best[0]
