"""Resources left: who is still to bat, and which bowling overs are left (G3 features; the simulator can import the pure functions).

Everything is PRIOR-ONLY and uses only what is known at ball t:
  * the playing XI per side (announced at the toss, so legitimate) - reconstructed from the deliveries (no XI table in the DB);
  * player strengths from matches strictly BEFORE the match date, shrunk toward "average";
  * which batters have come in / which bowlers have bowled completed overs so far in this innings.
The batting order is NOT used: "left to bat" = XI minus everyone who has batted or is at the crease.

Pure functions (no DB): xi_from_deliveries, Strengths, bat_features, bowl_features, innings_resources.
DB / batch: load_deliveries, build_resources (writes nothing).  CLI: python -m cricket_analytics.ml.resources [stats|build]

Units (era-neutral, so 2012 and 2025 are comparable; the model's own level columns carry the era):
  bat ratio   = runs scored / runs an average team batter would score off the same balls (1.0 = average), shrunk
  bat exp     = ratio * balls faced per innings (shrunk): "average-batter balls" a batter is expected to add
  bowl econ   = runs conceded / runs an average bowler concedes over the same balls (below 1 = good), shrunk
  bowl wk     = wickets / wickets an average bowler takes from the same balls (above 1 = good), shrunk
  bowl death  = like econ but only for overs 17-20, shrunk
"""

from collections import defaultdict

import numpy as np
import pandas as pd

# shrinkage / defaults (pseudo-observations pulling toward average)
K_WAR, RPB_REF = 120.0, 1.3  # S2: pseudo-balls toward the league average; average runs per ball (to turn runs added into a ratio)
K_BAT_RUNS = 80.0  # pseudo expected-runs for the batting ratio
BPI_PRIOR, K_BPI = 9.0, 4.0  # balls per innings prior (innings)
POS_PRIOR, K_POS = 7.0, 3.0  # typical batting position prior (innings)
K_ECON, K_WK, K_DEATH = 150.0, 3.0, 80.0
P_BOWL_PRIOR, K_P = 0.35, 3.0
HL_S3 = 548.0  # days (about 1.5 seasons)
TOP_POS = 7  # "top/middle order" = typical position <= 7
PAD_BAT = (0.5, 0.8, 9.0)  # unknown XI member: exp, ratio, position ~ tail
PAD_BOWL = (1.15, 0.8, 1.15)  # unfilled overs: part-timer econ, wk, death
MAX_OVERS = 4.0
CREDITED = ("bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket")
NOT_DISMISSAL = ("retired hurt", "retired not out")
FIELDS = ["bat_left_n", "bat_left_str", "best_bat_left", "bat_left_top", "bat_out_str", "bowl_left_econ", "bowl_left_wk", "death_top_left"]
BAT_COLS = FIELDS[:5]  # bat_out_str = summed exp of the batters already out (used and no longer at the crease)
BOWL_COLS = FIELDS[5:]


# ---------- playing XI ----------
def xi_from_deliveries(d):
    """d: deliveries (match_id, innings, batting_team, bowling_team, batter, non_striker, bowler, fielder, fielder_2, fielder_3).
    Returns DataFrame (match_id, team, player, batted, bowled). Players who neither batted, bowled nor fielded a catch/run-out are missing
    (typically a 12th-man type); impact-era sides can list 12+ (everyone who appears is counted)."""
    parts = []
    for cols, side, flag in ((["batter", "non_striker"], "batting_team", "batted"), (["bowler"], "bowling_team", "bowled"),
                             (["fielder", "fielder_2", "fielder_3"], "bowling_team", None)):
        for c in cols:
            x = d[["match_id", side, c]].rename(columns={side: "team", c: "player"}).dropna().drop_duplicates()
            x["batted"], x["bowled"] = flag == "batted", flag == "bowled"
            parts.append(x)
    xi = pd.concat(parts, ignore_index=True)
    return xi.groupby(["match_id", "team", "player"], as_index=False).agg(batted=("batted", "max"), bowled=("bowled", "max"))


def xi_coverage(xi):
    """Distribution of side sizes: Series size -> number of (match, side)."""
    return xi.groupby(["match_id", "team"]).size().value_counts().sort_index()


# ---------- prior-only strengths ----------
def _days(s):
    return pd.to_datetime(s).to_numpy().astype("datetime64[D]").astype("int64")


class _Cum:
    """Per-key cumulative sums sorted by date; lookup of the totals over records with date < D."""

    def __init__(self, keys, dates, vals, hl=None):
        o = np.lexsort((dates, keys))
        keys, dates, vals = np.asarray(keys)[o], np.asarray(dates)[o], np.asarray(vals, dtype=float)[o]
        self.hl = hl  # half-life in days: a record of age a counts 0.5 ** (a / hl)  (S3)
        if hl:
            vals = vals * (2.0 ** (dates / hl))[:, None]
        self.t = {}
        starts = np.r_[0, np.flatnonzero(keys[1:] != keys[:-1]) + 1, len(keys)]
        for a, b in zip(starts[:-1], starts[1:]):
            self.t[keys[a]] = (dates[a:b], np.vstack([np.zeros(vals.shape[1]), np.cumsum(vals[a:b], axis=0)]))
        self.w = vals.shape[1]

    def before(self, key, day):
        if key not in self.t:
            return np.zeros(self.w)
        dt, cs = self.t[key]
        v = cs[np.searchsorted(dt, day, side="left")]
        return v * 2.0 ** (-day / self.hl) if self.hl else v


class Strengths:
    """Prior-only player strengths. bat(player, date) -> (exp, ratio, pos); bowl(player, date) -> (econ, wk, death, p_bowl).
    `date` = the match date; only records with a strictly earlier date are used. Unknown players get the average values."""

    def __init__(self, bat_cum, bowl_cum, app_cum, war=None):
        self.b, self.w, self.a, self.war = bat_cum, bowl_cum, app_cum, war

    @classmethod
    def build(cls, d, dates, hl_days=None, war=None):
        """d: deliveries of innings 1-2 (needs runs_batter, runs_total, wides, noballs, byes, legbyes, penalty, wicket_type, player_out,
        over_num, ball_seq, gender); dates: Series match_id -> date. Keys are 'name|gender'.
        hl_days: recency half-life in days (S3, form); None = every prior record counts the same (S1).
        war: _Cum from war_cum() (S2): batting ratio / bowling econ come from prior-season WAR runs added instead of own records."""
        d = d.copy()
        d["gender"] = d["gender"].astype(str)
        legal = (d.wides == 0) & (d.noballs == 0)
        d["legal"], d["faced"] = legal.astype(int), (d.wides == 0).astype(int)
        d["death"] = (d.over_num >= 16).astype(int)
        d["cred"] = (d.player_out.notna() & d.wicket_type.isin(CREDITED)).astype(int)
        d["conc"] = d.runs_total - d.byes.fillna(0) - d.legbyes.fillna(0) - d.penalty.fillna(0)
        d["druns"], d["dlegal"] = d.runs_total * d.death, d.legal * d.death
        ik = ["match_id", "innings"]
        t = d.groupby(ik).agg(tr=("runs_total", "sum"), tl=("legal", "sum"), tc=("cred", "sum"), dr=("druns", "sum"), dl=("dlegal", "sum")).reset_index()
        t["rpb"] = t.tr / t.tl.clip(lower=1)
        t["wpb"] = t.tc / t.tl.clip(lower=1)
        t["drpb"] = np.where(t.dl > 0, t.dr / t.dl.clip(lower=1), t.rpb)
        d = d.merge(t[ik + ["rpb", "wpb", "drpb"]], on=ik)
        day = d.match_id.map(dates)
        d["day"] = _days(day)
        # batting: runs, faced, outs, appearance order
        a = pd.concat([d[ik + ["batter", "ball_seq", "gender", "day"]].rename(columns={"batter": "p"}).assign(s=0),
                       d[ik + ["non_striker", "ball_seq", "gender", "day"]].rename(columns={"non_striker": "p"}).assign(s=1)])
        a = a.dropna(subset=["p"]).groupby(ik + ["p"], as_index=False).agg(fs=("ball_seq", "min"), s=("s", "min"), gender=("gender", "first"), day=("day", "first"))
        a["pos"] = a.sort_values(ik + ["fs", "s"]).groupby(ik).cumcount() + 1
        bt = d.groupby(ik + ["batter"]).agg(runs=("runs_batter", "sum"), balls=("faced", "sum"), rpb=("rpb", "first")).reset_index().rename(columns={"batter": "p"})
        out = d[d.player_out.notna() & ~d.wicket_type.isin(NOT_DISMISSAL)].groupby(ik + ["player_out"]).size().rename("out").reset_index().rename(columns={"player_out": "p"})
        a = a.merge(bt, on=ik + ["p"], how="left").merge(out, on=ik + ["p"], how="left").fillna({"runs": 0, "balls": 0, "out": 0, "rpb": 0})
        a["key"] = a.p + "|" + a.gender
        bat = _Cum(a.key.to_numpy(), a.day.to_numpy(), np.c_[a.runs, a.balls * a.rpb, a.balls, a.pos, np.ones(len(a))], hl_days)
        # bowling
        bw = d.groupby(ik + ["bowler"]).agg(balls=("legal", "sum"), runs=("conc", "sum"), wk=("cred", "sum"), dl=("dlegal", "sum"), dr=("druns", "sum"),
                                            rpb=("rpb", "first"), wpb=("wpb", "first"), drpb=("drpb", "first"), gender=("gender", "first"), day=("day", "first")).reset_index()
        bw["key"] = bw.bowler + "|" + bw.gender
        bowl = _Cum(bw.key.to_numpy(), bw.day.to_numpy(), np.c_[bw.runs, bw.balls * bw.rpb, bw.wk, bw.balls * bw.wpb, bw.dr, bw.dl * bw.drpb], hl_days)
        # appearances (for the chance a player bowls)
        xi = xi_from_deliveries(d)
        g = d.groupby("match_id").gender.first()
        xi["key"] = xi.player + "|" + xi.match_id.map(g)
        xi["day"] = _days(xi.match_id.map(dates))
        app = _Cum(xi.key.to_numpy(), xi.day.to_numpy(), np.c_[xi.bowled.astype(float), np.ones(len(xi))], hl_days)
        return cls(bat, bowl, app, war)

    def bat(self, key, day):
        runs, exp, balls, possum, n = self.b.before(key, day)
        ratio = (runs + K_BAT_RUNS) / (exp + K_BAT_RUNS)
        if self.war is not None:  # S2: ratio from prior-season runs added per ball (bat); unknown / women -> own-record ratio
            ra, wb = self.war.before(key.replace("|male", "") + "|bat", day)
            if wb > 0:
                ratio = 1.0 + ra / (wb + K_WAR) / RPB_REF
        bpi = (balls + K_BPI * BPI_PRIOR) / (n + K_BPI)
        pos = (possum + K_POS * POS_PRIOR) / (n + K_POS)
        return ratio * bpi, ratio, pos

    def bowl(self, key, day):
        runs, exp, wk, ewk, dr, dexp = self.w.before(key, day)
        bowled, apps = self.a.before(key, day)
        econ = (runs + K_ECON) / (exp + K_ECON)
        if self.war is not None:
            ra, wb = self.war.before(key.replace("|male", "") + "|bowl", day)
            if wb > 0:
                econ = 1.0 - ra / (wb + K_WAR) / RPB_REF  # runs added are positive for the bowling side when good
        return (econ, (wk + K_WK) / (ewk + K_WK), (dr + K_DEATH) / (dexp + K_DEATH),
                (bowled + K_P * P_BOWL_PRIOR) / (apps + K_P))


def war_cum():
    """S2 source: runs added per (player, role) from models/war.py (v3, centred, match-adjusted), eight men's leagues pooled.
    A record for season-year sy (calendar year the season ended) is dated 31 Dec of sy, so a match in year Y sees only sy < Y:
    never its own season (which contains the match). Keys 'name|bat' / 'name|bowl'; values (runs added, balls)."""
    from ..models import war

    rows, _ = war.all_tables()
    r = pd.concat(rows.values())
    r = r[r.role.isin(["bat", "bowl"])]
    g = r.groupby(["player", "role", "sy"], as_index=False).agg(ra=("sc", "sum"), wk=("wk", "sum"), balls=("balls", "sum"))
    g["ra"] += g.wk
    day = (pd.to_datetime(g.sy.astype(int).astype(str) + "-12-31")).to_numpy().astype("datetime64[D]").astype("int64")
    return _Cum((g.player + "|" + g.role).to_numpy(), day, np.c_[g.ra, g.balls])


# ---------- pure feature functions ----------
def bat_features(left, n_pad=0):
    """left: list of (exp, ratio, pos) for the XI members still to bat; n_pad: unknown members (XI < 11) added with tail values.
    -> dict bat_left_n, bat_left_str (sum of exp), best_bat_left (max exp), bat_left_top (typical position <= 7)."""
    left = list(left) + [PAD_BAT] * max(0, n_pad)
    if not left:
        return {"bat_left_n": 0.0, "bat_left_str": 0.0, "best_bat_left": 0.0, "bat_left_top": 0.0}
    e = [x[0] for x in left]
    return {"bat_left_n": float(len(left)), "bat_left_str": float(sum(e)), "best_bat_left": float(max(e)),
            "bat_left_top": float(sum(x[2] <= TOP_POS for x in left))}


def bowl_features(bowlers, overs_left):
    """bowlers: list of (cap_left_overs, econ, wk, death) for the bowling XI (cap_left >= 0; 0 = cannot bowl any more);
    overs_left: whole overs still to be bowled. Best allocation: the cheapest bowlers (lowest econ) fill the overs; unfilled overs get PAD_BOWL.
    -> bowl_left_econ / bowl_left_wk (over-weighted means of the filling bowlers), death_top_left (overs left of the 3 best death bowlers)."""
    need, w, e, k = float(max(overs_left, 0)), 0.0, 0.0, 0.0
    for cap, econ, wk, _ in sorted((b for b in bowlers if b[0] > 0), key=lambda b: b[1]):
        take = min(cap, need - w)
        if take <= 0:
            break
        w, e, k = w + take, e + take * econ, k + take * wk
    if need > w:
        e, k, w = e + (need - w) * PAD_BOWL[0], k + (need - w) * PAD_BOWL[1], need
    top = sorted((b for b in bowlers if b[0] > 0), key=lambda b: b[3])[:3]
    return {"bowl_left_econ": e / w if w else np.nan, "bowl_left_wk": k / w if w else np.nan, "death_top_left": float(sum(b[0] for b in top))}


def innings_resources(rows, bat_xi, bowl_xi, overs=20):
    """One innings. rows: iterable of (balls_bowled, striker, non_striker, bowler) in ball order (the state AFTER balls_bowled legal balls;
    striker / non_striker / bowler are those of the next delivery, as in states.parquet).
    bat_xi: {player: (exp, ratio, pos)} of the batting XI; bowl_xi: {player: (econ, wk, death, p_bowl)} of the bowling XI.
    -> list of dicts (FIELDS), one per row. Row t uses only rows <= t: batters seen so far, completed overs of each bowler so far."""
    used, balls, out, held, bowl, prev_bowler = set(), defaultdict(int), [], None, None, None
    for k, st, ns, bw in rows:
        if k > 0 and prev_bowler is not None:
            balls[prev_bowler] += 1  # legal ball k was bowled by the bowler listed one row earlier
        prev_bowler = bw if isinstance(bw, str) else prev_bowler
        n0 = len(used)
        used.update(x for x in (st, ns) if isinstance(x, str))
        if held is None or len(used) != n0:  # batting side changes only when a new batter appears
            left = [v for p, v in bat_xi.items() if p not in used]
            held = bat_features(left, n_pad=11 - len(used) - len(left))
        if bowl is None or k % 6 == 0:  # bowling side changes only at over boundaries
            bl = []
            for p, (econ, wk, dth, pb) in bowl_xi.items():
                cap = MAX_OVERS - balls[p] // 6 if balls[p] > 0 else MAX_OVERS * pb
                bl.append((max(0.0, cap), econ, wk, dth))
            bowl = bowl_features(bl, overs - k // 6)
        at = {x for x in (st, ns) if isinstance(x, str)}
        out.append({**held, "bat_out_str": float(sum(bat_xi[p][0] for p in used - at if p in bat_xi)), **bowl})
    return out


# ---------- batch (DB) ----------
_COLS = ("match_id, innings, over_num, ball_seq, batter, non_striker, bowler, runs_batter, runs_total, wides, noballs, byes, legbyes, penalty, "
         "wicket_type, player_out, batting_team, bowling_team, fielder, fielder_2, fielder_3")


def load_deliveries():
    """(deliveries innings 1-2 with gender, match dates Series). Read-only."""
    from ..db import query

    d = query(f"SELECT d.*, m.gender FROM (SELECT {_COLS} FROM deliveries WHERE innings <= 2) d JOIN matches m USING (match_id) WHERE m.gender IN ('male','female')")
    dates = query("SELECT match_id, date FROM matches").set_index("match_id").date
    return d, dates


def build_resources(states, d, dates, S=None):
    """states: states.parquet rows (match_id, innings, balls_bowled, striker, non_striker, bowler, batting_team, bowling_team, date).
    Returns the states keys + FIELDS columns (float32). Matches not in `d` are skipped."""
    S = S or Strengths.build(d, dates)
    xi = xi_from_deliveries(d)
    g = d.groupby("match_id").gender.first()
    xi["key"] = xi.player + "|" + xi.match_id.map(g)
    side = {k: v for k, v in xi.groupby(["match_id", "team"])}
    states = states.sort_values(["match_id", "innings", "balls_bowled"], kind="stable")
    out = []
    for (mid, inn), s in states.groupby(["match_id", "innings"], sort=False):
        day = int(_days(pd.Series([s.date.iloc[0]]))[0])
        bt, bw = s.batting_team.iloc[0], s.bowling_team.iloc[0]
        if (mid, bt) not in side:
            continue
        gx = str(g[mid])
        bat_xi = {r.player: S.bat(r.key, day) for r in side[(mid, bt)].itertuples()}
        bowl_xi = {r.player: S.bowl(r.key, day) for r in side.get((mid, bw), pd.DataFrame(columns=["player", "key"])).itertuples()}
        res = innings_resources(zip(s.balls_bowled, s.striker, s.non_striker, s.bowler), bat_xi, bowl_xi)
        out.append(pd.DataFrame(res, index=s.index).assign(match_id=s.match_id.to_numpy(), innings=s.innings.to_numpy(), balls_bowled=s.balls_bowled.to_numpy()))
    r = pd.concat(out)
    for c in FIELDS:
        r[c] = r[c].astype("float32")
    return r.reset_index(drop=True)


if __name__ == "__main__":
    import sys

    from .dataset import OUT_DIR, load

    d, dates = load_deliveries()
    if sys.argv[1:] == ["stats"]:
        xi = xi_from_deliveries(d)
        print(xi_coverage(xi).to_string())
    else:
        st, _ = load()
        src = sys.argv[2] if len(sys.argv) > 2 else "s1"  # s1 default; s2 = prior-season WAR; s3 = recency-weighted (half-life 1.5 seasons)
        S = Strengths.build(d, dates, hl_days=HL_S3 if src == "s3" else None, war=war_cum() if src == "s2" else None)
        r = build_resources(st, d, dates, S)
        r.to_parquet(OUT_DIR / ("resources.parquet" if src == "s1" else f"resources_{src}.parquet"))
        print(r.shape)
