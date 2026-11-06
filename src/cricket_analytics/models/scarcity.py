"""Supply and demand in IPL auctions (M6): which player types were scarce, and did scarcity raise prices?

Pipeline (every judgement call: docs/VALUE_m6.md):
  1. usage: per player-competition-year usage counts from the DB (positions batted, overs by phase, runs, wickets).
  2. roles: weights per player from his usage in the three calendar years BEFORE an auction (IPL first; other men's T20,
     including SMAT, if he has fewer than 5 IPL matches there), bowling type and keeper ONLY from the reviewed list.
  3. squads: each team's squad just before each auction (retentions, or the previous roster minus the players put up).
  4. demand: slots of a best XII that are empty or below the league median, capped by open squad places, weighted by purse.
  5. supply: players put on the block who can fill the role, and those at or above the league-median recent value.
  6. index = demand / (quality supply + 1); tests of price and of "sold".

Data (DB-free once built): models/data/scarcity_usage.csv (step 1) and scarcity_*.csv outputs.
Rebuild:  python -m cricket_analytics.models.scarcity          (reads the DB read-only, a few seconds)
Use:      scarcity_for({"death_pace": 1.0}, 2026)   -> relative scarcity (1.0 = the auction's average role)
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from ..reference import REFERENCE_DIR
from . import trade as T
from . import war as w

DATA = w.DATA
USAGE_CSV = DATA / "scarcity_usage.csv"
PLAYERS_CSV = DATA / "scarcity_players.csv"
DEMAND_CSV = DATA / "scarcity_demand.csv"
INDEX_CSV = DATA / "scarcity_index.csv"
TEAMS_CSV = DATA / "scarcity_teams.csv"
TESTS_CSV = DATA / "scarcity_tests.csv"
FWD_CSV = DATA / "scarcity_2027.csv"
FWD_TEAMS_CSV = DATA / "scarcity_2027_teams.csv"
CHECK_CSV = DATA / "scarcity_squad_check.csv"

AUCTION_CSV = REFERENCE_DIR / "ipl_auctions.csv"
RETENTION_CSV = REFERENCE_DIR / "ipl_retentions.csv"

YEARS = (2022, 2023, 2024, 2025, 2026)
MEGA = {2022, 2025}
PURSE = {2022: 90.0, 2023: 95.0, 2024: 100.0, 2025: 120.0, 2026: 125.0, 2027: T.PURSE_CAP}  # cr
SQUAD_MAX, OVERSEAS_MAX = 25, 8

# thresholds (all documented in docs/VALUE_m6.md)
WINDOW = 3  # calendar years before the auction
MIN_MATCHES = 5  # to use a source at all (IPL first, else other T20)
MIN_INNS, MIN_BAT_BALLS_PER_MATCH = 5, 10.0
MIN_BOWL_BALLS, MIN_OVERS_PER_MATCH = 60, 2.0
CAN_FILL = 0.25  # role weight at which a player "can fill" the role
WK_COST = 20.0  # runs a wicket is worth (as in league_translation.py)
SHRINK_K = 300.0  # balls of average evidence added to each player's rate
YEAR_W = {1: 3.0, 2: 2.0, 3: 1.0}  # years before the auction -> weight

ROLES = (
    "keeper",
    "opener",
    "top_order",
    "middle",
    "finisher",
    "pp_pace",
    "mid_pace",
    "death_pace",
    "spin",
)
DIM = {r: "bat" for r in ROLES[:5]} | {r: "bowl" for r in ROLES[5:]}
SLOTS = (  # (slot, role): the best XII asked for, same idea as trade.SLOTS but by data-driven role
    ("keeper", "keeper"),
    ("opener 1", "opener"),
    ("opener 2", "opener"),
    ("top order", "top_order"),
    ("middle 1", "middle"),
    ("middle 2", "middle"),
    ("finisher", "finisher"),
    ("pp pace", "pp_pace"),
    ("mid pace", "mid_pace"),
    ("death pace", "death_pace"),
    ("spin 1", "spin"),
    ("spin 2", "spin"),
)
SLOT_K = {"opener 2": 1, "middle 2": 1, "spin 2": 1}  # k-th best for repeated roles; others 0
SMOOTH = 0.05


# ── step 1: usage from the DB ────────────────────────────────────────────────────────────────────────────────
USAGE_SQL = """
WITH base AS (
  SELECT d.*, year(m.date) AS yr, m.competition AS comp
  FROM deliveries d JOIN matches m USING (match_id)
  WHERE m.gender = 'male' AND m.competition <> 'hundred' AND d.innings <= 2),
bat AS (
  SELECT batter AS player, comp, yr,
    SUM(CASE WHEN COALESCE(wides,0)=0 THEN 1 ELSE 0 END) AS bat_balls, SUM(runs_batter) AS bat_runs,
    SUM(CASE WHEN player_out=batter AND wicket_type NOT IN ('retired hurt','retired not out','retired out') THEN 1 ELSE 0 END) AS bat_outs
  FROM base GROUP BY ALL),
bowl AS (
  SELECT bowler AS player, comp, yr,
    SUM(CASE WHEN COALESCE(wides,0)=0 AND COALESCE(noballs,0)=0 THEN 1 ELSE 0 END) AS bowl_balls,
    SUM(runs_batter+COALESCE(wides,0)+COALESCE(noballs,0)) AS bowl_runs,
    SUM(CASE WHEN wicket_type IN ('bowled','caught','caught and bowled','lbw','stumped','hit wicket') THEN 1 ELSE 0 END) AS bowl_wkts,
    SUM(CASE WHEN COALESCE(wides,0)=0 AND COALESCE(noballs,0)=0 AND over_num<6 THEN 1 ELSE 0 END) AS pp_balls,
    SUM(CASE WHEN COALESCE(wides,0)=0 AND COALESCE(noballs,0)=0 AND over_num>=15 THEN 1 ELSE 0 END) AS death_balls
  FROM base GROUP BY ALL),
x AS (SELECT match_id, innings, ball_seq*2 AS s, batter AS p, comp, yr FROM base
      UNION ALL SELECT match_id, innings, ball_seq*2+1, non_striker, comp, yr FROM base),
f AS (SELECT match_id, innings, p, comp, yr, min(s) AS s FROM x GROUP BY ALL),
pos AS (SELECT p AS player, comp, yr, COUNT(*) AS bat_inns,
    SUM(CASE WHEN r<=2 THEN 1 ELSE 0 END) AS pos_open, SUM(CASE WHEN r IN (3,4) THEN 1 ELSE 0 END) AS pos_top,
    SUM(CASE WHEN r IN (5,6) THEN 1 ELSE 0 END) AS pos_mid, SUM(CASE WHEN r IN (7,8) THEN 1 ELSE 0 END) AS pos_fin,
    SUM(r) AS pos_sum
  FROM (SELECT *, row_number() OVER (PARTITION BY match_id, innings ORDER BY s) AS r FROM f) GROUP BY ALL),
app AS (SELECT p AS player, comp, yr, COUNT(DISTINCT match_id) AS matches
  FROM (SELECT match_id, p, comp, yr FROM x UNION SELECT match_id, bowler, comp, yr FROM base) GROUP BY ALL)
SELECT a.player, a.comp, a.yr, a.matches,
  COALESCE(bat_balls,0) bat_balls, COALESCE(bat_runs,0) bat_runs, COALESCE(bat_outs,0) bat_outs,
  COALESCE(bat_inns,0) bat_inns, COALESCE(pos_open,0) pos_open, COALESCE(pos_top,0) pos_top,
  COALESCE(pos_mid,0) pos_mid, COALESCE(pos_fin,0) pos_fin, COALESCE(pos_sum,0) pos_sum,
  COALESCE(bowl_balls,0) bowl_balls, COALESCE(bowl_runs,0) bowl_runs, COALESCE(bowl_wkts,0) bowl_wkts,
  COALESCE(pp_balls,0) pp_balls, COALESCE(death_balls,0) death_balls
FROM app a LEFT JOIN bat USING (player,comp,yr) LEFT JOIN bowl USING (player,comp,yr) LEFT JOIN pos USING (player,comp,yr)
"""


def build_usage(db_path=None) -> pd.DataFrame:
    from ..db import query

    u = query(USAGE_SQL, [], db_path=db_path).fillna(0)
    for c in u.columns[3:]:
        u[c] = u[c].astype(int)
    u = u.sort_values(["comp", "yr", "player"])
    u.to_csv(USAGE_CSV, index=False)
    return u


@lru_cache(maxsize=1)
def usage() -> pd.DataFrame:
    if not USAGE_CSV.exists():
        raise FileNotFoundError(
            f"{USAGE_CSV.name} missing: run  python -m cricket_analytics.models.scarcity"
        )
    return pd.read_csv(USAGE_CSV)


# ── step 2: role weights and recent value, as of an auction year ─────────────────────────────────────────────
def _baselines(u: pd.DataFrame) -> pd.DataFrame:
    g = u.groupby(["comp", "yr"])[
        ["bat_balls", "bat_runs", "bat_outs", "bowl_balls", "bowl_runs", "bowl_wkts"]
    ].sum()
    return pd.DataFrame(
        {
            "base_bat": (g.bat_runs - WK_COST * g.bat_outs) / g.bat_balls.clip(lower=1),
            "base_bowl": (g.bowl_runs - WK_COST * g.bowl_wkts) / g.bowl_balls.clip(lower=1),
        }
    )


def bowl_style(bowl_type) -> str | None:
    """'pace', 'finger' or 'wrist' from the reviewed list's bowling type (None = not on the list)."""
    if bowl_type is None or pd.isna(bowl_type):
        return None
    t = str(bowl_type)
    if "spin" in t or "orthodox" in t:
        return "wrist" if ("leg spin" in t or "wrist" in t) else "finger"
    return "pace"


def features(year: int, u: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per player with enough matches in the WINDOW years before `year`: role weights (w_<role>), the split of spin
    into finger / wrist, recent value rates (runs above average per 100 balls, shrunk) and season volume. Index = Cricsheet name."""
    u = usage() if u is None else u
    base = _baselines(u)
    win = u[(u.yr >= year - WINDOW) & (u.yr < year)].copy()
    ipl_m = win[win.comp == "ipl"].groupby("player").matches.sum()
    use_ipl = set(ipl_m[ipl_m >= MIN_MATCHES].index)
    is_ipl = win.player.isin(use_ipl)
    win = win[(is_ipl & (win.comp == "ipl")) | (~is_ipl & (win.comp != "ipl"))].copy()
    win["source"] = np.where(win.comp == "ipl", "ipl", "other")
    win = win.join(base, on=["comp", "yr"])
    win["wt"] = (year - win.yr).map(YEAR_W) / sum(YEAR_W.values())
    win["bat_val"] = win.wt * (win.bat_runs - WK_COST * win.bat_outs - win.base_bat * win.bat_balls)
    win["bowl_val"] = win.wt * (
        win.base_bowl * win.bowl_balls - (win.bowl_runs - WK_COST * win.bowl_wkts)
    )
    win["bat_bw"], win["bowl_bw"] = win.wt * win.bat_balls, win.wt * win.bowl_balls
    cols = ["matches", "bat_balls", "bat_inns", "pos_open", "pos_top", "pos_mid", "pos_fin", "pos_sum", "bowl_balls",
            "pp_balls", "death_balls", "bat_val", "bowl_val", "bat_bw", "bowl_bw"]  # fmt: skip
    p = win.groupby("player")[cols].sum()
    p["source"] = win.groupby("player").source.first()
    yrs = win.drop_duplicates(["player", "yr"]).groupby("player").wt.sum()
    p = p[p.matches >= MIN_MATCHES]
    yrs = yrs.reindex(p.index)
    at = T.attributes()
    style = at.bowl_type.reindex(p.index).map(bowl_style)
    ni = p.bat_inns.clip(lower=1)
    f_bat = np.where(
        p.bat_inns >= MIN_INNS,
        np.minimum(1.0, p.bat_balls / p.matches / MIN_BAT_BALLS_PER_MATCH),
        0.0,
    )
    f_bowl = np.where(
        p.bowl_balls >= MIN_BOWL_BALLS, np.minimum(1.0, p.bowl_balls / 6 / p.matches / MIN_OVERS_PER_MATCH), 0.0
    )  # fmt: skip
    bb = p.bowl_balls.clip(lower=1)
    pp, de = p.pp_balls / bb, p.death_balls / bb
    pace, spin = (style == "pace").values, style.isin(["finger", "wrist"]).values
    out = pd.DataFrame(index=p.index)
    out["source"], out["matches"] = p.source, p.matches
    out["w_keeper"] = at.keeper.reindex(p.index).map({"yes": 1.0, "sometimes": 0.5}).fillna(0.0)
    out["w_opener"] = f_bat * p.pos_open / ni
    out["w_top_order"] = f_bat * p.pos_top / ni
    out["w_middle"] = f_bat * p.pos_mid / ni
    out["w_finisher"] = f_bat * p.pos_fin / ni
    out["w_pp_pace"] = f_bowl * pace * pp
    out["w_mid_pace"] = f_bowl * pace * (1 - pp - de).clip(lower=0)
    out["w_death_pace"] = f_bowl * pace * de
    out["w_spin"] = f_bowl * spin
    out["w_spin_finger"] = out.w_spin * (style == "finger").values
    out["w_spin_wrist"] = out.w_spin * (style == "wrist").values
    out["w_bowl_untyped"] = (
        f_bowl * style.isna().values
    )  # bowls, but the reviewed list has no bowling type: no role
    out["bat_pos"] = p.pos_sum / ni
    out["rate_bat"] = 100 * p.bat_val / (p.bat_bw + SHRINK_K)
    out["rate_bowl"] = 100 * p.bowl_val / (p.bowl_bw + SHRINK_K)
    out["value_bat"] = (
        out.rate_bat / 100 * p.bat_bw / yrs
    )  # runs above average per season (the slot ranking measure)
    out["value_bowl"] = out.rate_bowl / 100 * p.bowl_bw / yrs
    out["bowl_style"] = style
    return out


def role_medians(feat: pd.DataFrame) -> dict:
    """League median recent-value rate per role: among IPL-sourced players who can fill it (all-source if fewer than 10)."""
    out = {}
    for r in ROLES:
        can = feat[feat[f"w_{r}"] >= CAN_FILL]
        pool = can[can.source == "ipl"]
        pool = pool if len(pool) >= 10 else can
        out[r] = float(pool[f"rate_{DIM[r]}"].median()) if len(pool) else 0.0
    return out


# ── step 3: squads before each auction ───────────────────────────────────────────────────────────────────────
def _auctions() -> pd.DataFrame:
    a = pd.read_csv(AUCTION_CSV)
    a["key"] = a.cricsheet_name.fillna(a.player)
    ov = a.overseas.astype(str).str.lower().map({"true": 1.0, "false": 0.0})
    a["overseas"] = (
        ov.fillna(a.country.map(lambda c: np.nan if pd.isna(c) else float(c != "IND")))
        .fillna(0.0)
        .astype(bool)
    )
    for c in ("sold", "presented_on_block", "rtm"):
        a[c] = a[c].astype(str).str.lower().eq("true")
    a["capped"] = a.capped.astype(str).str.lower().map({"true": True, "false": False})
    return a


def _retentions() -> pd.DataFrame:
    r = pd.read_csv(RETENTION_CSV)
    r["key"] = r.cricsheet_name.fillna(r.player)
    r["overseas"] = r.overseas.astype(str).str.lower().eq("true")
    return r


SQ_COLS = ["team", "key", "player", "price_cr", "overseas"]


def _roster(pre: pd.DataFrame, sold: pd.DataFrame) -> pd.DataFrame:
    return (
        pd.concat([pre[SQ_COLS], sold[SQ_COLS]])
        .drop_duplicates(["team", "key"], keep="last")
        .reset_index(drop=True)
    )


def _derive(prev_roster: pd.DataFrame, presented_keys: set) -> pd.DataFrame:
    """Pre-auction squad when no retention list exists: last roster minus everybody who is put up again (released)."""
    return prev_roster[~prev_roster.key.isin(presented_keys)].reset_index(drop=True)


@lru_cache(maxsize=1)
def squads_before() -> dict:
    """year -> DataFrame(team, key, player, price_cr, overseas): each squad just before that auction. 2022, 2025, 2026 use the
    real retention lists; 2023 and 2024 are rolled forward (documented gap). 'derived_2026' = the roll-forward method applied
    to 2026, kept only to check it against the real list."""
    a, r = _auctions(), _retentions()
    pre = {y: r[r.cycle_year == y][SQ_COLS].reset_index(drop=True) for y in (2022, 2025, 2026)}
    sold = {y: a[(a.auction_year == y) & a.sold] for y in YEARS}
    pres = {y: set(a[(a.auction_year == y) & a.presented_on_block].key) for y in YEARS}
    roster = {2022: _roster(pre[2022], sold[2022])}
    pre[2023] = _derive(roster[2022], pres[2023])
    roster[2023] = _roster(pre[2023], sold[2023])
    pre[2024] = _derive(roster[2023], pres[2024])
    roster[2025] = _roster(pre[2025], sold[2025])
    out = {y: pre[y] for y in YEARS}
    out["derived_2026"] = _derive(roster[2025], pres[2026])
    return out


def squad_check() -> pd.DataFrame:
    """How good is the roll-forward? The derived 2026 squads against the real 2026 retention list, per team."""
    s = squads_before()
    d, real = s["derived_2026"], s[2026]
    rows = []
    for t in sorted(real.team.unique()):
        dk, rk = set(d[d.team == t].key), set(real[real.team == t].key)
        rows.append({"team": t, "real_n": len(rk), "derived_n": len(dk), "in_both": len(dk & rk)})
    c = pd.DataFrame(rows)
    c.loc[len(c)] = ["ALL", *c[["real_n", "derived_n", "in_both"]].sum()]
    c["recall"] = (c.in_both / c.real_n).round(3)
    c["precision"] = (c.in_both / c.derived_n).round(3)
    return c


# ── step 4: demand ───────────────────────────────────────────────────────────────────────────────────────────
def _slot_values(sq_feat: pd.DataFrame) -> dict:
    out = {}
    for slot, r in SLOTS:
        m = sq_feat[sq_feat[f"w_{r}"] >= CAN_FILL][f"value_{DIM[r]}"].sort_values(ascending=False)
        k = SLOT_K.get(slot, 0)
        out[slot] = float(m.iloc[k]) if len(m) > k else None
    return out


def team_needs(
    squads: pd.DataFrame, feat: pd.DataFrame, year: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(team x role need table, per-team summary). need = best-XII slots that are empty or below the league median slot value
    (median over teams, empty counted as 0, as in trade.league_slot_means), scaled down if more than the open squad places;
    demand = need x purse weight (purse left / median purse left, clipped 0.1-3)."""
    per = {
        t: _slot_values(feat.reindex(g.key.values).dropna(subset=["matches"]))
        for t, g in squads.groupby("team")
    }
    med = {
        s: float(np.median([p[s] if p[s] is not None else 0.0 for p in per.values()]))
        for s, _ in SLOTS
    }
    left = {t: PURSE[year] - float(g.price_cr.sum()) for t, g in squads.groupby("team")}
    pmed = float(np.median(list(left.values())))
    rows, summ = [], []
    for t, g in squads.groupby("team"):
        holes = [s for s, _ in SLOTS if per[t][s] is None or per[t][s] < med[s]]
        need = {r: float(sum(1 for s, r2 in SLOTS if s in holes and r2 == r)) for r in ROLES}
        open_spots = max(0, SQUAD_MAX - len(g))
        os_open = max(0, OVERSEAS_MAX - int(g.overseas.sum()))
        tot = sum(need.values())
        scale = min(1.0, open_spots / tot) if tot else 1.0
        pw = float(np.clip(left[t] / pmed, 0.1, 3.0)) if pmed > 0 else 1.0
        frac_os = min(1.0, os_open / max(open_spots, 1))
        for r in ROLES:
            rows.append({"year": year, "team": t, "role": r, "need_raw": need[r], "need": need[r] * scale,
                         "purse_weight": pw, "demand": need[r] * scale * pw, "frac_overseas": frac_os})  # fmt: skip
        summ.append({"year": year, "team": t, "squad_n": len(g), "open_spots": open_spots, "overseas_n": int(g.overseas.sum()),
                     "overseas_open": os_open, "squad_cost_cr": round(float(g.price_cr.sum()), 2),
                     "purse_left_cr": round(left[t], 2), "purse_weight": round(pw, 3), "need_total_raw": tot,
                     "need_scale": round(scale, 3), "holes": ", ".join(holes)})  # fmt: skip
    return pd.DataFrame(rows), pd.DataFrame(summ)


# ── step 5/6: supply and index ───────────────────────────────────────────────────────────────────────────────
def _index_table(year: int, dem: pd.DataFrame, pool: pd.DataFrame, med: dict) -> pd.DataFrame:
    """pool: players on the block with w_<role> columns, rate_bat / rate_bowl, overseas. One row per role."""
    d = dem.assign(d_os=dem.demand * dem.frac_overseas, d_in=dem.demand * (1 - dem.frac_overseas))
    d = d.groupby("role")[["need", "demand", "d_os", "d_in"]].sum()
    rows = []
    for r in ROLES:
        can = pool[pool[f"w_{r}"] >= CAN_FILL]
        q = can[can[f"rate_{DIM[r]}"] >= med[r]]
        qo = int(q.overseas.sum())
        rows.append({"year": year, "role": r, "teams_needing": int(((dem.role == r) & (dem.need > 0)).sum()),
                     "need_slots": d.need[r], "demand": d.demand[r], "supply_all": len(can), "supply_quality": len(q),
                     "supply_all_overseas": int(can.overseas.sum()), "supply_quality_overseas": qo,
                     "index": d.demand[r] / (len(q) + 1), "index_overseas": d.d_os[r] / (qo + 1),
                     "index_indian": d.d_in[r] / (len(q) - qo + 1)})  # fmt: skip
    t = pd.DataFrame(rows)
    lg = np.log(t["index"] + SMOOTH)
    t["log_rel_index"] = lg - lg.mean()
    t["rel_index"] = np.exp(t.log_rel_index)
    return t


def _main_role(row: pd.Series) -> str | None:
    ws = {r: row[f"w_{r}"] for r in ROLES}
    r = max(ws, key=ws.get)
    return r if ws[r] >= CAN_FILL else None


def build_year(year: int, squads: pd.DataFrame, players: pd.DataFrame) -> dict:
    """Everything for one auction year. players = the auction rows put on the block."""
    feat = features(year)
    med = role_medians(feat)
    dem, summ = team_needs(squads, feat, year)
    pl = players.join(feat, on="key", how="left")
    pl["classified"] = pl.matches.notna()
    wc = [c for c in pl.columns if c.startswith("w_")]
    pl[wc] = pl[wc].fillna(0.0)
    pl["main_role"] = pl.apply(_main_role, axis=1)
    return {
        "feat": feat,
        "dem": dem,
        "summ": summ,
        "pl": pl,
        "idx": _index_table(year, dem, pl, med),
    }


def forward_2027(index: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """PROVISIONAL: need per team and role from today's 2027 squads (before the 17 Nov 2026 retention deadline, so trades and
    releases will change it). Squads are full (about 25), so the open-places cap is ignored: need = weak or empty best-XII slots,
    which a team can only fill by releasing someone. Supply is unknown until the pool is announced: the median quality supply of the mini auctions
    2023, 2024 and 2026 stands in for it."""
    c = T.squads()
    sq = pd.DataFrame(
        {
            "team": c.team,
            "key": c.key,
            "player": c.player,
            "price_cr": c.price_cr.astype(float),
            "overseas": c.overseas,
        }
    ).reset_index(drop=True)
    dem, summ = team_needs(sq, features(2027), 2027)
    sup = (
        index[index.year.isin([2023, 2024, 2026])]
        .groupby("role")[["supply_all", "supply_quality"]]
        .median()
        .reindex(list(ROLES))
    )
    dem = dem.assign(
        need=dem.need_raw, demand=dem.need_raw * dem.purse_weight
    )  # squads are full: ignore the places cap
    d = dem.groupby("role")[["need", "demand"]].sum().reindex(list(ROLES))
    f = pd.DataFrame({"year": 2027, "role": list(ROLES),
                      "teams_needing": [int(((dem.role == r) & (dem.need > 0)).sum()) for r in ROLES],
                      "need_slots": d.need.values, "demand": d.demand.values,
                      "supply_all_assumed": sup.supply_all.values, "supply_quality_assumed": sup.supply_quality.values})  # fmt: skip
    f["index"] = f.demand / (f.supply_quality_assumed + 1)
    lg = np.log(f["index"] + SMOOTH)
    f["rel_index"] = np.exp(lg - lg.mean())
    f["status"] = (
        "PROVISIONAL until retentions (17 Nov 2026); supply assumed from earlier mini auctions"
    )
    return f, summ.assign(status="PROVISIONAL")


# ── step 7: tests (price and P(sold)) ────────────────────────────────────────────────────────────────────────
def design(
    players: pd.DataFrame, index: pd.DataFrame, fe: bool = True, scar: bool = True
) -> tuple[pd.DataFrame, list]:
    """Regression frame. exposure = weighted mean of the log relative index over the roles the player can fill
    (weights = role weights >= CAN_FILL); players with no role get 0 and the dummy no_role."""
    li = index.pivot(index="year", columns="role", values="log_rel_index")
    p = players.copy()
    ws = np.column_stack([p[f"w_{r}"].where(p[f"w_{r}"] >= CAN_FILL, 0.0).values for r in ROLES])
    lv = li.loc[p.auction_year.values, list(ROLES)].values
    tot = ws.sum(1)
    p["exposure"] = np.where(tot > 0, (ws * lv).sum(1) / np.where(tot > 0, tot, 1), 0.0)
    p["no_role"] = (tot == 0).astype(float)
    p["log_base"] = np.log(p.base_price_cr.astype(float))
    p["capped_f"] = p.capped.map({True: 1.0, False: 0.0}).fillna(0.0)
    p["capped_unknown"] = p.capped.isna().astype(float)
    p["overseas_f"] = p.overseas.astype(float)
    dim = p.main_role.map(DIM)
    p["value_main"] = np.where(dim == "bat", p.rate_bat, np.where(dim == "bowl", p.rate_bowl, 0.0))
    p["value_main"] = pd.Series(p.value_main, index=p.index).fillna(0.0)
    p["mega"] = p.auction_year.isin(MEGA).astype(float)
    cols = ["log_base", "capped_f", "capped_unknown", "overseas_f", "value_main", "no_role"]
    if scar:
        cols = ["exposure", *cols]
    if fe:
        for yy in YEARS[1:]:
            p[f"fe_{yy}"] = (p.auction_year == yy).astype(float)
        cols += [f"fe_{yy}" for yy in YEARS[1:]]
    else:
        cols += ["mega"]
    return p, cols


def _ols(X, y):
    b, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(X)), X]), y, rcond=None)
    return b


def _pr(b, X):
    return 1 / (1 + np.exp(-np.clip(np.column_stack([np.ones(len(X)), X]) @ b, -30, 30)))


def _logit(X, y, iters=40, ridge=1e-4):
    Xc = np.column_stack([np.ones(len(X)), X])
    b = np.zeros(Xc.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Xc @ b, -30, 30)))
        wgt = np.clip(p * (1 - p), 1e-6, None)
        step = np.linalg.solve(
            Xc.T @ (Xc * wgt[:, None]) + ridge * np.eye(len(b)), Xc.T @ (y - p) - ridge * b
        )
        b = b + step
        if np.abs(step).max() < 1e-8:
            break
    return b


BOOT, SEED = 1000, 20261106


def run_tests(players: pd.DataFrame, index: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows = []

    def add(test, term, est, lo, hi, n, note=""):
        rows.append(
            {
                "test": test,
                "term": term,
                "estimate": est,
                "lo90": lo,
                "hi90": hi,
                "n": n,
                "note": note,
            }
        )

    def boot(n, k):
        return (rng.integers(0, n, n) for _ in range(k))

    p, cols = design(players, index)
    sd = float(p.exposure.std())
    j = 1 + cols.index("exposure")
    s = p[p.sold & p.price_cr.notna()]
    X, y = s[cols].values, np.log(s.price_cr.astype(float).values)
    b = _ols(X, y)
    bs = np.array([_ols(X[i], y[i]) for i in boot(len(s), BOOT)])
    note = f"1 SD of exposure = {sd:.2f}; estimate = change in log price (0.10 = +10.5%)"
    add(
        "A price (log), auction FE",
        "exposure per +1 SD",
        float(b[j] * sd),
        *np.percentile(bs[:, j] * sd, [5, 95]),
        len(s),
        note,
    )
    for c in ("log_base", "capped_f", "overseas_f", "value_main"):
        k = 1 + cols.index(c)
        add("A price (log), auction FE", c, float(b[k]), *np.percentile(bs[:, k], [5, 95]), len(s))
    p2, c2 = design(players, index, fe=False)
    s2 = p2[p2.sold & p2.price_cr.notna()]
    X2, y2 = s2[c2].values, np.log(s2.price_cr.astype(float).values)
    b2 = _ols(X2, y2)
    bs2 = np.array([_ols(X2[i], y2[i]) for i in boot(len(s2), BOOT)])
    add(
        "A2 price (log), no FE (mega dummy)",
        "exposure per +1 SD",
        float(b2[1] * sd),
        *np.percentile(bs2[:, 1] * sd, [5, 95]),
        len(s2),
        note,
    )
    X, y = p[cols].values, p.sold.astype(float).values

    def ame(bb, XX):
        q = _pr(bb, XX)
        return float(np.mean(q * (1 - q)) * bb[j] * sd * 100)

    bsl = [ame(_logit(X[i], y[i]), X[i]) for i in boot(len(p), 300)]
    add("B P(sold), auction FE", "exposure per +1 SD (points)", ame(_logit(X, y), X), *np.percentile(bsl, [5, 95]), len(p),
        f"{int(y.sum())} sold of {len(p)} on the block; average marginal effect in percentage points; 300 bootstrap draws")  # fmt: skip
    pa, ca = design(players, index, fe=False, scar=True)
    pb, cb = design(players, index, fe=False, scar=False)
    ly = np.log(pa.price_cr.astype(float))
    ok = pa.sold & pa.price_cr.notna()
    for t in (2024, 2025, 2026):
        tr, te = ok & (pa.auction_year < t), ok & (pa.auction_year == t)

        def pred(pp, cc):
            X = np.column_stack([np.ones(te.sum()), pp.loc[te, cc].values])
            return X @ _ols(pp.loc[tr, cc].values, ly[tr].values)

        ea, eb = (ly[te].values - pred(pa, ca)) ** 2, (ly[te].values - pred(pb, cb)) ** 2
        gain = lambda i: np.sqrt(eb[i].mean()) - np.sqrt(ea[i].mean())  # noqa: E731
        bd = [gain(i) for i in boot(int(te.sum()), BOOT)]
        add(f"C out of sample {t} (trained on earlier auctions)", "RMSE gain from scarcity (log price)", float(gain(slice(None))),
            *np.percentile(bd, [5, 95]), int(te.sum()), f"RMSE without {np.sqrt(eb.mean()):.3f}, with {np.sqrt(ea.mean()):.3f}; train n={int(tr.sum())}")  # fmt: skip
    return pd.DataFrame(rows)


# ── build ────────────────────────────────────────────────────────────────────────────────────────────────────
PLAYER_COLS = ["auction_year", "player", "key", "country", "overseas", "capped", "base_price_cr", "sold", "price_cr", "team",
               "classified", "source", "matches", "main_role", *[f"w_{r}" for r in ROLES], "w_spin_finger", "w_spin_wrist",
               "w_bowl_untyped", "bat_pos", "rate_bat", "rate_bowl", "bowl_style"]  # fmt: skip


def build(write: bool = True) -> dict:
    a, s = _auctions(), squads_before()
    res = {
        y: build_year(y, s[y], a[(a.auction_year == y) & a.presented_on_block].copy())
        for y in YEARS
    }
    players = pd.concat([r["pl"] for r in res.values()], ignore_index=True)
    index = pd.concat([r["idx"] for r in res.values()], ignore_index=True)
    sold = players[players.sold & players.price_cr.notna()]
    g = sold.groupby(["auction_year", "main_role"]).price_cr
    index["avg_price_cr"] = [g.mean().get((y, r), np.nan) for y, r in zip(index.year, index.role)]
    index["n_sold_main"] = [int(g.size().get((y, r), 0)) for y, r in zip(index.year, index.role)]
    index["rank_scarcity"] = (
        index.groupby("year")["index"].rank(ascending=False, method="min").astype(int)
    )
    index["kind"] = np.where(index.year.isin(MEGA), "mega", "mini")
    out = {
        "players": players,
        "demand": pd.concat([r["dem"] for r in res.values()], ignore_index=True),
        "teams": pd.concat([r["summ"] for r in res.values()], ignore_index=True),
        "index": index,
        "check": squad_check(),
        "tests": run_tests(players, index),
    }
    out["fwd"], out["fwd_teams"] = forward_2027(index)
    if write:
        players[PLAYER_COLS].round(4).to_csv(PLAYERS_CSV, index=False)
        out["demand"].round(4).to_csv(DEMAND_CSV, index=False)
        index.round(4).to_csv(INDEX_CSV, index=False)
        out["teams"].to_csv(TEAMS_CSV, index=False)
        out["check"].to_csv(CHECK_CSV, index=False)
        out["tests"].round(4).to_csv(TESTS_CSV, index=False)
        out["fwd"].round(4).to_csv(FWD_CSV, index=False)
        out["fwd_teams"].to_csv(FWD_TEAMS_CSV, index=False)
        index_table.cache_clear()
    return out


# ── public helpers ───────────────────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def index_table() -> pd.DataFrame:
    if not INDEX_CSV.exists():
        raise FileNotFoundError(
            f"{INDEX_CSV.name} missing: run  python -m cricket_analytics.models.scarcity"
        )
    return pd.read_csv(INDEX_CSV)


def scarcity_for(player_roles, auction_year: int, kind: str = "relative") -> float:
    """Scarcity of a player's role(s) at an auction.

    player_roles: {role: weight} or a list of roles (equal weights); roles are in ROLES. Weights below CAN_FILL are ignored.
    kind: 'relative' (1.0 = the auction's average role; default), 'log' (log relative, 0 = average) or 'raw' (demand weighted
    by purse, per quality player on the block + 1). Weighted mean over the roles. auction_year 2027 gives the PROVISIONAL
    forward view. Returns NaN when the player has no role."""
    pr = (
        dict.fromkeys(player_roles, 1.0)
        if not isinstance(player_roles, dict)
        else dict(player_roles)
    )
    bad = set(pr) - set(ROLES)
    if bad:
        raise ValueError(f"Unknown role(s) {sorted(bad)}. Valid: {', '.join(ROLES)}")
    if kind not in ("relative", "log", "raw"):
        raise ValueError("kind must be 'relative', 'log' or 'raw'")
    pr = {r: float(x) for r, x in pr.items() if x >= CAN_FILL}
    if not pr:
        return float("nan")
    if int(auction_year) == 2027:
        t = pd.read_csv(FWD_CSV).set_index("role")
        t["log_rel_index"] = np.log(t.rel_index)
    else:
        i = index_table()
        if int(auction_year) not in set(i.year):
            raise ValueError(
                f"No auction {auction_year}. Valid: {sorted(set(i.year))} and 2027 (provisional)"
            )
        t = i[i.year == int(auction_year)].set_index("role")
    col = {"relative": "rel_index", "log": "log_rel_index", "raw": "index"}[kind]
    return float(sum(x * t.loc[r, col] for r, x in pr.items()) / sum(pr.values()))


def main() -> None:
    import sys

    if "--no-db" not in sys.argv:
        args = [x for x in sys.argv[1:] if not x.startswith("-")]
        print(f"usage rows: {len(build_usage(args[0] if args else None))}")
        usage.cache_clear()
    o = build()
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(o["check"])
    print(
        o["teams"].groupby("year")[["squad_n", "purse_left_cr", "need_total_raw"]].mean().round(1)
    )
    print(
        o["index"][
            [
                "year",
                "role",
                "need_slots",
                "demand",
                "supply_all",
                "supply_quality",
                "index",
                "rel_index",
                "avg_price_cr",
            ]
        ]
        .round(2)
        .to_string()
    )
    print(o["tests"].round(3).to_string())


if __name__ == "__main__":
    main()
