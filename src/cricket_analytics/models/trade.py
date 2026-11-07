"""IPL trade tool: recent value per player, best XII per squad, and a trade evaluation with honest ranges.

Built on RECENT value (what a player delivered in the Impact Player era, IPL 2023-26), not on predictions. Our tests
(docs/VALUE_step3.md) show batter projections have no out-of-sample skill, so batters carry "recent form" only.

    recent value (wins above replacement per season) = sum_s w_s * WAR_s / sum_s w_s, weights 4/3/2/1 for 2026..2023,
    over the seasons from the player's first Impact-era IPL season to 2026 (a season he missed counts 0 = replacement).
    Range: bootstrap over the player's own matches (10th to 90th percentile of 400 draws), batting and bowling together.

Data (all DB-free once built):  models/data/trade_match_ra.csv  (one row per player-match-role: runs added, balls, batting position)
Rebuild:  python -m cricket_analytics.models.trade           (about 40 s, reads the DB read-only)
Full method and every judgement call: docs/VALUE_step5.md.
"""

import difflib
import itertools
import re
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from ..reference import OVERRIDES_CSV, REFERENCE_DIR
from . import war as w

MATCH_CSV = w.DATA / "trade_match_ra.csv"
CONTRACTS_CSV = REFERENCE_DIR / "ipl_contracts.csv"
PWAR_CSV = w.DATA / "pwar_ipl_2027.csv"
WORTHVAL_CSV = w.DATA / "worth_value_2027.csv"  # expected next-season WAR per player (models/xii_basis.py)
BASES = ("recent", "worth", "blend")  # what the XII is picked on: see docs/VALUE_xii_basis.md
BLEND_A = 0.1  # weight on recent value in "blend" (the pooled-rho maximum of the backtest in xii_basis.pick_blend)
DEFAULT_BASIS = "worth"  # beat "recent" in the XII-level test (IPL 2024-26, n=30 team-seasons)

SEASONS = (
    2023,
    2024,
    2025,
    2026,
)  # Impact Player era (owner's rule: older IPL seasons are not used)
WEIGHTS = {2026: 4.0, 2025: 3.0, 2024: 2.0, 2023: 1.0}
DRAWS = 400
SEED = 20261106
REPL_SALARY = 0.30  # cr: the base price of an uncapped player = what a replacement costs
IMPACT_WEIGHT = 0.5  # the impact player plays about half a match
MAX_OS_XI, MAX_OS_XII = 4, 5
MIN_OVERS, MIN_BOWLERS = 20.0, 5

TEAMS = {  # contracts abbreviation -> name in the data
    "CSK": "Chennai Super Kings",
    "DC": "Delhi Capitals",
    "GT": "Gujarat Titans",
    "KKR": "Kolkata Knight Riders",
    "LSG": "Lucknow Super Giants",
    "MI": "Mumbai Indians",
    "PBKS": "Punjab Kings",
    "RR": "Rajasthan Royals",
    "RCB": "Royal Challengers Bengaluru",
    "SRH": "Sunrisers Hyderabad",
}
FULL_TO_ABBR = {v: k for k, v in TEAMS.items()}


# ── build (needs the DB) ─────────────────────────────────────────────────────────────────────────────────────
def build_match_table(db_path=None) -> pd.DataFrame:
    """Per player and match (IPL 2023+): runs added (league-centred, as in WAR), balls, batting position."""
    from ..db import query
    from .match_adjust import adjusted, match_rows

    # WAR v3: batting + bowling runs added (v1 definition: no fielding credit), adjusted for match conditions at w = war.MATCH_W
    r = adjusted(match_rows("ipl"), w.load_params()["match_w"])
    m = r.groupby(["match_id", "sy", "player", "role"], as_index=False)[["balls", "ra_adj"]].sum().rename(columns={"ra_adj": "ra"})

    m = m[m.sy >= SEASONS[0]]
    pos = query(
        """WITH x AS (SELECT d.match_id, d.innings, d.ball_seq, 0 AS src, d.batter AS p FROM deliveries d
                      JOIN matches m USING (match_id) WHERE m.competition = 'ipl' AND d.innings <= 2 AND m.date >= '2023-01-01'
                      UNION ALL
                      SELECT d.match_id, d.innings, d.ball_seq, 1, d.non_striker FROM deliveries d
                      JOIN matches m USING (match_id) WHERE m.competition = 'ipl' AND d.innings <= 2 AND m.date >= '2023-01-01'),
                f AS (SELECT match_id, innings, p, min(ball_seq * 2 + src) AS s FROM x GROUP BY ALL)
           SELECT match_id, p AS player, row_number() OVER (PARTITION BY match_id, innings ORDER BY s) AS pos FROM f""",
        [],
        db_path=db_path,
    )
    m = m.merge(pos, how="left", on=["match_id", "player"])
    m.loc[m.role == "bowl", "pos"] = np.nan
    return m[["match_id", "sy", "player", "role", "balls", "ra", "pos"]].round(5)


def build(db_path=None) -> pd.DataFrame:
    m = build_match_table(db_path)
    m.to_csv(MATCH_CSV, index=False)
    return m


# ── values ───────────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Values:
    """table: one row per player with IPL-era evidence (index = Cricsheet name). bat_draws / bowl_draws: (players, DRAWS)."""

    table: pd.DataFrame
    bat_draws: np.ndarray
    bowl_draws: np.ndarray
    debut_pool: (
        np.ndarray
    )  # zero-centred first-season WAR of debutants: the spread used for "no IPL evidence" players
    index: dict = field(default_factory=dict)

    def __post_init__(self):
        self.index = {p: i for i, p in enumerate(self.table.index)}


def _per_match(m: pd.DataFrame) -> pd.DataFrame:
    p = m.pivot_table(
        index=["player", "sy", "match_id"], columns="role", values=["balls", "ra"], fill_value=0.0
    )
    p.columns = [f"{r}_{k}" for k, r in p.columns]
    for c in ("bat_balls", "bat_ra", "bowl_balls", "bowl_ra"):
        if c not in p:
            p[c] = 0.0
    return p.reset_index()


def compute_values(m: pd.DataFrame, prm: dict, draws: int = DRAWS, seed: int = SEED) -> Values:
    """Recent value per player with a bootstrap over his own matches (the same resampled matches feed batting and bowling)."""
    era = prm["era"]["2023"]
    rpw, rb, rw = era["rpw"], era["repl"]["bat"] / 100.0, era["repl"]["bowl"] / 100.0
    pm = _per_match(m)
    rng = np.random.default_rng(seed)
    rows, bat_d, bowl_d, first_war = [], [], [], {}
    for player, g in pm.groupby("player"):
        first = int(g.sy.min())
        win = [s for s in SEASONS if s >= first]
        wsum = sum(WEIGHTS[s] for s in win)
        bat_pt = bowl_pt = 0.0
        bd, wd = np.zeros(draws), np.zeros(draws)
        per = {}
        for s, gs in g.groupby("sy"):
            n = len(gs)
            idx = rng.integers(0, n, (draws, n))
            bw = WEIGHTS[s] / wsum
            ba, bb = gs.bat_ra.values, gs.bat_balls.values
            wa, wb = gs.bowl_ra.values, gs.bowl_balls.values
            bat_s = (ba.sum() - rb * bb.sum()) / rpw
            bowl_s = (wa.sum() - rw * wb.sum()) / rpw
            bat_pt += bw * bat_s
            bowl_pt += bw * bowl_s
            bd += bw * ((ba[idx].sum(1) - rb * bb[idx].sum(1)) / rpw)
            wd += bw * ((wa[idx].sum(1) - rw * wb[idx].sum(1)) / rpw)
            per[s] = (bat_s, bowl_s, int(bb.sum()), int(wb.sum()), n)
        first_war[player] = (first, per[first][0] + per[first][1])
        rec = {"player": player, "first_season": first, "bat_value": bat_pt, "bowl_value": bowl_pt}
        for s in SEASONS:
            b, o, bbl, obl, n = per.get(s, (0.0, 0.0, 0, 0, 0))
            rec |= {f"bat_war_{s}": b, f"bowl_war_{s}": o, f"matches_{s}": n}
            rec[f"bat_balls_{s}"], rec[f"bowl_balls_{s}"] = bbl, obl
        rows.append(rec)
        bat_d.append(bd)
        bowl_d.append(wd)
    t = pd.DataFrame(rows).set_index("player")
    t["value"] = t.bat_value + t.bowl_value
    deb = np.array([v for p, (f, v) in first_war.items() if f > SEASONS[0]])
    return Values(t, np.array(bat_d), np.array(bowl_d), deb - deb.mean())


@lru_cache(maxsize=1)
def values() -> Values:
    if not MATCH_CSV.exists():
        raise FileNotFoundError(
            f"{MATCH_CSV.name} missing: run  python -m cricket_analytics.models.trade"
        )
    return compute_values(pd.read_csv(MATCH_CSV), w.load_params())


@lru_cache(maxsize=1)
def usage() -> pd.DataFrame:
    """Per player (IPL 2023+): matches, usual batting position, bat share of matches, overs per match when he bowls."""
    m = pd.read_csv(MATCH_CSV)
    bat = (
        m[(m.role == "bat") & m.pos.notna()]
        .groupby("player")
        .agg(bat_pos=("pos", "mean"), bat_matches=("match_id", "nunique"))
    )
    bw = (
        m[(m.role == "bowl") & (m.balls > 0)]
        .groupby("player")
        .agg(bowl_matches=("match_id", "nunique"), bowl_balls=("balls", "sum"))
    )
    bw["overs_when_bowling"] = bw.bowl_balls / 6 / bw.bowl_matches
    appear = m.groupby("player").match_id.nunique().rename("matches")
    u = pd.concat([appear, bat, bw[["bowl_matches", "overs_when_bowling"]]], axis=1)
    u["bowl_share"] = (u.bowl_matches.fillna(0) / u.matches).round(3)
    return u


# ── contracts and squads ─────────────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def attributes() -> pd.DataFrame:
    """Reviewed list only: keeper, bowl_type, bowl_kind (never the derived guesses)."""
    o = pd.read_csv(OVERRIDES_CSV).set_index("name")
    kind = o.bowl_type.map(
        lambda t: None if pd.isna(t) else ("spin" if re.search("spin|orthodox", t) else "pace")
    )
    return pd.DataFrame({"keeper": o.keeper, "bowl_type": o.bowl_type, "bowl_kind": kind})


def load_contracts() -> pd.DataFrame:
    c = pd.read_csv(CONTRACTS_CSV)
    c["overseas"] = c.overseas.astype(str).str.lower().eq("true")
    c["withdrawn_2026"] = c.withdrawn_2026.astype(str).str.lower().eq("true")
    c["key"] = c.cricsheet_name.fillna(
        c.player
    )  # the id a squad uses: Cricsheet name, else the contract name
    return c


def squads(
    contracts: pd.DataFrame | None = None, baseline: str = "current", only=None
) -> pd.DataFrame:
    """Rows of the squads. current = after the announced 2027 trades (traded_in rows, no traded_out rows).
    before_trades = the announced trades are undone (traded_out rows at their old price instead of traded_in rows), for all of
    them or, with `only` = names, just for those players (so one real trade can be evaluated with the others in place).
    Withdrawn players are out."""
    if baseline not in ("current", "before_trades"):
        raise ValueError("baseline must be 'current' or 'before_trades'")
    c = load_contracts() if contracts is None else contracts
    c = c[~c.withdrawn_2026]
    s = c.status_2027.astype(str)
    cur = c[(s == "in_squad") | (s == "traded_in")]
    if baseline == "current":
        return cur.copy()
    names = None if only is None else {str(x).strip().lower() for x in only}
    hit = (
        pd.Series(True, c.index)
        if names is None
        else c.key.str.lower().isin(names) | c.player.str.lower().isin(names)
    )
    undo = c.key.isin(c[hit & (s == "traded_in")].key)  # players whose announced trade is undone
    return c[
        ((s == "in_squad") & ~undo)
        | (undo & s.str.startswith("traded_out"))
        | ((s == "traded_in") & ~hit)
    ].copy()


def team_abbr(team: str) -> str:
    t = str(team).strip()
    if t.upper() in TEAMS:
        return t.upper()
    if t in FULL_TO_ABBR:
        return FULL_TO_ABBR[t]
    alt = {"royal challengers bangalore": "RCB"}.get(t.lower())
    if alt:
        return alt
    raise ValueError(f"Unknown IPL team {team!r}. Valid: {', '.join(TEAMS.values())}")


@lru_cache(maxsize=1)
def worth_values() -> pd.DataFrame:
    if not WORTHVAL_CSV.exists():
        raise FileNotFoundError(f"{WORTHVAL_CSV.name} missing: run  python -m cricket_analytics.models.xii_basis")
    return pd.read_csv(WORTHVAL_CSV).set_index("player")


def _check_basis(basis: str) -> str:
    if basis not in BASES:
        raise ValueError(f"value_basis must be one of {BASES}, got {basis!r}")
    return basis


def player_table(sq: pd.DataFrame, v: Values | None = None, basis: str = "recent") -> pd.DataFrame:
    """One row per squad player: contract + value + role information. Index = team + key.
    basis: recent = WAR 2023-26 weighted 4/3/2/1; worth = expected next-season WAR (player_worth ridge); blend = BLEND_A x recent +
    (1 - BLEND_A) x worth. `recent_value` always keeps the recent number (the bootstrap draws are centred on it, see draws_for)."""
    v = values() if v is None else v
    _check_basis(basis)
    u = usage()
    at = attributes()
    pw = pd.read_csv(PWAR_CSV).set_index("cricsheet_name")
    t = sq.set_index("key", drop=False)
    t["has_evidence"] = t.index.isin(v.table.index)
    vt = v.table.reindex(t.index)
    for c in ("bat_value", "bowl_value", "value"):
        t[c] = vt[c].fillna(0.0).values
    for s in SEASONS:
        t[f"war_{s}"] = (vt[f"bat_war_{s}"].fillna(0) + vt[f"bowl_war_{s}"].fillna(0)).values
    t["matches_ipl_2023_on"] = u.matches.reindex(t.index).fillna(0).astype(int).values
    t["bat_pos"] = u.bat_pos.reindex(t.index).values
    t["overs_when_bowling"] = u.overs_when_bowling.reindex(t.index).fillna(0).values
    t["bowl_share"] = u.bowl_share.reindex(t.index).fillna(0).values
    t["keeper"] = at.keeper.reindex(t.index).eq("yes").values
    t["keeper_some"] = at.keeper.reindex(t.index).eq("sometimes").values
    t["bat_matches"] = u.bat_matches.reindex(t.index).fillna(0).values
    t["bowl_kind"] = at.bowl_kind.reindex(t.index).values
    t["pwar_bowl"] = pw.bowl.reindex(t.index).fillna(0).values
    # a bowling option bowls in 30%+ of his matches and averages 1+ over when he does; his capacity is his usual spell rounded up
    # (a bowler who averages 3.2 overs can bowl 4), at most 4
    t["is_bowler"] = (t.overs_when_bowling >= 1.0) & (t.bowl_share >= 0.3)
    t["overs"] = np.where(t.is_bowler, np.minimum(4.0, np.ceil(t.overs_when_bowling)), 0.0)
    t["recent_value"] = t.value
    if basis != "recent":
        wv = worth_values().reindex(t.index).fillna(0.0)
        a = 0.0 if basis == "worth" else BLEND_A
        t["bat_value"] = a * t.bat_value + (1 - a) * wv.bat_war.values
        t["bowl_value"] = a * t.bowl_value + (1 - a) * wv.bowl_war.values
        t["value"] = t.bat_value + t.bowl_value
    t["salary"] = t.price_cr.astype(float)
    t["value_per_cr"] = t.value / t.salary
    return t


# ── market: rupees per win ───────────────────────────────────────────────────────────────────────────────────
def market_fit(pt: pd.DataFrame) -> dict:
    """Salary against recent value over players with IPL evidence. Two numbers, both reported:
    ols = slope of (salary - base price) on value; ratio = total (salary - base) of all squad players / total positive value."""
    e = pt[pt.has_evidence & (pt.matches_ipl_2023_on >= 5)]
    x, y = e.value.values, (e.salary - REPL_SALARY).values
    slope, icpt = np.polyfit(x, y, 1)
    r = np.corrcoef(x, y)[0, 1]
    pos = pt.value.clip(lower=0).sum()
    return {
        "n": int(len(e)),
        "cr_per_win_ols": float(slope),
        "intercept_cr": float(icpt),
        "r": float(r),
        "r2": float(r * r),
        "cr_per_win_ratio": float((pt.salary - REPL_SALARY).sum() / pos),
        "total_salary_cr": float(pt.salary.sum()),
        "total_positive_value": float(pos),
    }


# ── best XII ─────────────────────────────────────────────────────────────────────────────────────────────────
def draws_for(pt: pd.DataFrame, v: Values | None = None) -> np.ndarray:
    """(players, DRAWS) draws of recent value. Same player = same draws everywhere (so a trade's shared players cancel).
    A player with no IPL-era evidence gets value 0 and the spread of debutants' first seasons (zero-centred)."""
    import zlib

    v = values() if v is None else v
    out = np.zeros((len(pt), DRAWS))
    for i, (k, ev) in enumerate(zip(pt.index, pt.has_evidence)):
        if ev and k in v.index:
            j = v.index[k]
            out[i] = v.bat_draws[j] + v.bowl_draws[j]
        else:
            out[i] = np.random.default_rng(zlib.crc32(str(k).encode())).choice(v.debut_pool, DRAWS)
    if "recent_value" in pt:  # another basis: the same spread (own-match bootstrap), centred on that basis's value
        out = out + (pt.value.values - pt.recent_value.values)[:, None]
    return out


def _penalty(sel, a) -> float:
    """Rule breaks of an XI, in 'wins'; one break costs far more than any player is worth, so a legal XI always wins."""
    p = max(0, a["os"][sel].sum() - MAX_OS_XI) * 20.0
    if a["need_keeper"] and not a["keeper"][sel].any():
        p += 20.0
    p += max(0.0, MIN_OVERS - a["overs"][sel].sum()) * 2.0
    p += max(0, MIN_BOWLERS - a["bowler"][sel].sum()) * 20.0
    p += max(0, 6 - a["bat7"][sel].sum()) * 20.0
    return p


def _search(a, n: int, seed: int = 7) -> np.ndarray:
    val, m = a["val"], len(a["val"])
    force = a.get(
        "force", np.zeros(m, bool)
    )  # must-play players: in every start, never swapped out
    free = np.flatnonzero(~force)
    k = n - int(force.sum())
    rng = np.random.default_rng(seed)
    fixed = np.flatnonzero(force)
    starts = [np.r_[fixed, free[np.argsort(-val[free])][:k]]] + [
        np.r_[fixed, rng.permutation(free)[:k]] for _ in range(30)
    ]
    best, best_f = None, -1e18
    for st in starts:
        sel = np.zeros(m, bool)
        sel[st] = True
        f = val[sel].sum() - _penalty(sel, a)
        while True:
            move_to = None
            for i, o in itertools.product(np.flatnonzero(sel & ~force), np.flatnonzero(~sel)):
                s2 = sel.copy()
                s2[i], s2[o] = False, True
                f2 = val[s2].sum() - _penalty(s2, a)
                if f2 > f + 1e-9:
                    f, move_to = f2, s2
            if move_to is None:
                break
            sel = move_to
        if f > best_f + 1e-9:
            best, best_f = sel, f
    return best


def pick_xii(pt: pd.DataFrame, force=()) -> dict:
    """Best legal XI plus impact player from one squad (rows of player_table).

    Rules enforced (as penalties in a swap search that starts from the top-valued 11 and 30 random starts, so no ILP library):
    at most 4 overseas in the XI; a keeper from the REVIEWED list (a 'yes', else a 'sometimes'; if the squad has none the rule is
    dropped and flagged, never guessed); at least 5 bowling options with 20+ expected overs between them; at least 6 usual
    top-seven batters. The impact player is the best remaining player (an Indian if the XI already has 4 overseas), always named, counted at
    IMPACT_WEIGHT only if his value is above 0 (a below-replacement impact player adds 0). `force` = labels of players who must be in the XI (a captain or star in poor form).
    Returns {'xi': [index labels], 'impact': label or None, 'value': float, 'flags': [str], 'penalty': float}."""
    n = 11
    if len(pt) < n:
        raise ValueError(f"A squad needs at least {n} players, this one has {len(pt)}")
    fmask = pt.index.isin(list(force))
    if fmask.sum() > n:
        raise ValueError(f"must_play lists {int(fmask.sum())} players of one team; an XI has {n}")
    yes = pt.keeper.values.astype(bool)
    some = pt.keeper_some.values.astype(bool) & ~yes
    flags = []
    need = bool(yes.any() or some.any())
    if not need:
        flags.append("no keeper in the reviewed list for this squad: keeper rule not applied")
    a = {
        "val": pt.value.values.astype(float),
        "os": pt.overseas.values.astype(int),
        "keeper": yes if yes.any() else (yes | some),
        "need_keeper": need,
        "overs": pt.overs.values.astype(float),
        "bowler": pt.is_bowler.values.astype(int),
        "bat7": (
            (pt.bat_pos.fillna(99).values <= 7.0) & (pt.bat_matches.fillna(0).values >= 5)
        ).astype(int),
        "force": fmask,
    }
    sel = _search(a, n)
    pen = float(_penalty(sel, a))
    if pen > 0:
        flags.append("squad cannot meet every rule (not enough bowlers / batters / keepers)")
    rest = np.flatnonzero(~sel)
    os_xi = a["os"][sel].sum()
    cand = [i for i in rest if os_xi < MAX_OS_XI or not a["os"][i]]
    imp = max(cand, key=lambda i: a["val"][i]) if cand else None
    idx = pt.index
    return {
        "xi": [idx[i] for i in np.flatnonzero(sel)],
        "impact": None if imp is None else idx[imp],
        "value": float(
            a["val"][sel].sum() + (IMPACT_WEIGHT * a["val"][imp] if imp is not None and a["val"][imp] > 0 else 0.0)
        ),
        "impact_counted": imp is not None and a["val"][imp] > 0,
        "flags": flags,
        "penalty": pen,
    }


def xii_draws(pick: dict, pt: pd.DataFrame, D: np.ndarray) -> np.ndarray:
    pos = {k: i for i, k in enumerate(pt.index)}
    t = D[[pos[k] for k in pick["xi"]]].sum(0)
    return t + (IMPACT_WEIGHT * D[pos[pick["impact"]]] if pick.get("impact_counted") else 0.0)


def rng_text(d: np.ndarray) -> tuple[float, float]:
    return float(np.percentile(d, 10)), float(np.percentile(d, 90))


# ── holes ────────────────────────────────────────────────────────────────────────────────────────────────────
SLOTS = (  # (slot, category, which-best, measure)
    ("keeper", "keeper", 0, "value"),
    ("opener 1", "opener", 0, "bat_value"),
    ("opener 2", "opener", 1, "bat_value"),
    ("middle 1", "middle", 0, "bat_value"),
    ("middle 2", "middle", 1, "bat_value"),
    ("middle 3", "middle", 2, "bat_value"),
    ("finisher", "finisher", 0, "bat_value"),
    ("pace 1", "pace", 0, "bowl_value"),
    ("pace 2", "pace", 1, "bowl_value"),
    ("pace 3", "pace", 2, "bowl_value"),
    ("spin 1", "spin", 0, "bowl_value"),
    ("spin 2", "spin", 1, "bowl_value"),
)


def _members(pt: pd.DataFrame, cat: str) -> pd.DataFrame:
    bp, bm = pt.bat_pos.fillna(99), pt.bat_matches.fillna(0)
    if cat == "keeper":
        return pt[pt.keeper | pt.keeper_some]
    if cat == "opener":
        return pt[(bp <= 2.5) & (bm >= 5)]
    if cat == "middle":
        return pt[(bp > 2.5) & (bp <= 6.5) & (bm >= 5)]
    if cat == "finisher":
        return pt[(bp > 6.5) & (bp < 99) & (bm >= 5)]
    return pt[pt.is_bowler & (pt.bowl_kind == cat)]


def slot_values(pt: pd.DataFrame) -> dict:
    """Slot -> value of the best available player for it (None = nobody in the squad qualifies). A player may fill several slots."""
    out = {}
    for slot, cat, k, meas in SLOTS:
        m = _members(pt, cat)[meas].sort_values(ascending=False)
        out[slot] = float(m.iloc[k]) if len(m) > k else None
    return out


def league_slot_means(player_tab: pd.DataFrame) -> dict:
    per = [slot_values(g) for _, g in player_tab.groupby("team")]
    return {
        s: float(np.median([p[s] if p[s] is not None else 0.0 for p in per])) for s, *_ in SLOTS
    }


def holes(pt: pd.DataFrame, ref: dict) -> list[str]:
    """Slots where the best available player is below the league median for that slot (or nobody qualifies)."""
    sv = slot_values(pt)
    return [s for s, x in sv.items() if x is None or x < ref[s]]


# ── season simulation: playoff and title odds ────────────────────────────────────────────────────────────────
BETA_CSV = w.DATA / "trade_beta_matches.csv"
BETA_BOOT, BETA_SEED = 1000, 20261107
SIM_BETAS, SIM_SEASONS = 40, 1000  # 40 beta draws x 1000 seasons = 40,000 seasons per scenario
PURSE_CAP = 125.0  # cr: the 2026 purse rule; a guess for 2027 (not announced)
# 2022+ format: two groups of five; a team plays its group rivals twice, its "rival" in the other group twice, the other four once
GROUPS = (("MI", "KKR", "RR", "DC", "LSG"), ("CSK", "SRH", "RCB", "PBKS", "GT"))
RIVALS = (
    ("MI", "CSK"),
    ("KKR", "PBKS"),
    ("RR", "RCB"),
    ("DC", "SRH"),
    ("LSG", "GT"),
)  # 2022 pairing; 2027 groups unknown
ORDER = tuple(t for g in GROUPS for t in g)


def fixtures() -> list[tuple[int, int]]:
    """70 league games as pairs of ORDER indices (each team plays 14)."""
    ix, pairs = {t: i for i, t in enumerate(ORDER)}, []
    for a, b in itertools.combinations(ORDER, 2):
        same = any(a in g and b in g for g in GROUPS)
        rival = (a, b) in RIVALS or (b, a) in RIVALS
        pairs += [(ix[a], ix[b])] * (2 if same or rival else 1)
    return pairs


def prior_values(m: pd.DataFrame, season: int, prm: dict) -> pd.Series:
    """Recent value (point estimate) of every player using only seasons BEFORE `season`: weights 4,3,2,1 counted back from
    the season before, from the player's first season in the data (a missed season counts 0). Used only to fit beta."""
    e = prm["era"]["2023"]
    repl = m.role.map({"bat": e["repl"]["bat"] / 100.0, "bowl": e["repl"]["bowl"] / 100.0})
    g = m.assign(war=(m.ra - repl * m.balls) / e["rpw"])
    g = g[g.sy < season].groupby(["player", "sy"]).war.sum().unstack()
    out = {}
    for p, row in g.iterrows():
        first = row.dropna().index.min()
        ss = list(range(int(first), season))
        wt = np.array([max(1.0, 5.0 - (season - s)) for s in ss])
        out[p] = float((wt * row.reindex(ss).fillna(0.0).values).sum() / wt.sum())
    return pd.Series(out, dtype=float)


def build_beta_matches(db_path=None) -> pd.DataFrame:
    """One row per IPL 2024-26 match with a winner: both teams' most-used XI (that season) valued from PRIOR seasons only.
    x1 / x2 = recent value; x1w / x2w = worth basis; x1b / x2b = blend (columns the basis fits use)."""
    from . import xii_basis as XB

    from ..db import query

    m, prm = pd.read_csv(MATCH_CSV), w.load_params()
    mt = query(
        "SELECT match_id, date, team1, team2, winner FROM matches WHERE competition = 'ipl' AND date >= '2024-01-01' "
        "AND winner IS NOT NULL",
        [],
        db_path=db_path,
    )
    lu = query(
        """SELECT DISTINCT d.match_id, t.team, t.p AS player FROM deliveries d JOIN matches m USING (match_id),
           LATERAL (VALUES (d.batting_team, d.batter), (d.batting_team, d.non_striker), (d.bowling_team, d.bowler)) AS t(team, p)
           WHERE m.competition = 'ipl' AND m.date >= '2024-01-01' AND d.innings <= 2""",
        [],
        db_path=db_path,
    )
    mt["sy"] = pd.to_datetime(mt.date).dt.year
    lu = lu.merge(mt[["match_id", "sy"]], on="match_id")
    rows = []
    for sy, g in lu.groupby("sy"):
        pv = prior_values(m, int(sy), prm)
        pw = XB.prior_worth(int(sy))
        pvs = {"": pv, "w": pw, "b": (BLEND_A * pv.reindex(pv.index.union(pw.index)).fillna(0) + (1 - BLEND_A) * pw.reindex(pv.index.union(pw.index)).fillna(0))}
        cnt = g.groupby(["team", "player"]).size().reset_index(name="n")
        xi = (
            cnt.sort_values(["team", "n", "player"], ascending=[True, False, True])
            .groupby("team")
            .head(11)
        )
        xs = {k: xi.assign(v=xi.player.map(q).fillna(0.0)).groupby("team").v.sum() for k, q in pvs.items()}
        x = xs[""]
        for r in mt[mt.sy == sy].itertuples():
            if r.team1 in x.index and r.team2 in x.index:
                rows.append(
                    (r.match_id, sy, r.team1, r.team2, int(r.winner == r.team1))
                    + tuple(c for k in ("", "w", "b") for c in (xs[k][r.team1], xs[k][r.team2]))
                )
    out = pd.DataFrame(rows, columns=["match_id", "sy", "team1", "team2", "team1_won", "x1", "x2", "x1w", "x2w", "x1b", "x2b"])
    return out.round(5)


def fit_beta(d: pd.DataFrame, boot: int = BETA_BOOT, seed: int = BETA_SEED, basis: str = "recent") -> dict:
    """Logistic slope (no intercept: team1 is not a home side) of the match result on the difference in XI value
    (wins a season). Newton steps; the bootstrap resamples matches. Returns beta, its draws, 10-90 range and n."""
    sfx = {"recent": "", "worth": "w", "blend": "b"}[_check_basis(basis)]
    x, y = (d[f"x1{sfx}"] - d[f"x2{sfx}"]).values.astype(float), d.team1_won.values.astype(float)

    def one(x, y):
        b = 0.0
        for _ in range(25):
            p = 1 / (1 + np.exp(-b * x))
            g, h = ((y - p) * x).sum(), (p * (1 - p) * x * x).sum()
            if h < 1e-12:
                break
            b += g / h
        return b

    rng = np.random.default_rng(seed)
    draws = np.array(
        [one(x[i], y[i]) for i in (rng.integers(0, len(x), len(x)) for _ in range(boot))]
    )
    b = one(x, y)
    return {
        "beta": float(b),
        "draws": draws,
        "lo": float(np.percentile(draws, 10)),
        "hi": float(np.percentile(draws, 90)),
        "n": int(len(x)),
        "p_positive": float((draws > 0).mean()),
    }


@lru_cache(maxsize=3)
def beta(basis: str = "recent") -> dict:
    if not BETA_CSV.exists():
        raise FileNotFoundError(
            f"{BETA_CSV.name} missing: run  python -m cricket_analytics.models.trade beta"
        )
    return fit_beta(pd.read_csv(BETA_CSV), basis=basis)


def simulate(
    strength: dict, beta_draws, seed: int = 11, betas: int = SIM_BETAS, seasons: int = SIM_SEASONS
) -> dict:
    """Season simulation. strength = {abbr: XII value}. Each of `betas` beta draws runs `seasons` seasons: 70 league games
    (win chance = logistic(beta x value difference)), top 4 by wins (ties random) to Q1 / Eliminator / Q2 / Final.
    The same random numbers are used for every scenario (same seed), so a before/after difference is not simulation noise.
    Returns {'playoff': (betas, 10), 'title': (betas, 10)} shares in ORDER order."""
    rng = np.random.default_rng(seed)
    bt = rng.choice(np.asarray(beta_draws), betas)
    fx = fixtures()
    s = np.array([strength[t] for t in ORDER])
    u = rng.random((betas, seasons, len(fx)))
    tie = rng.random((betas, seasons, 10))
    po = rng.random((betas, seasons, 4))
    wins = np.zeros((betas, seasons, 10))
    for k, (i, j) in enumerate(fx):
        pw = 1 / (1 + np.exp(-bt * (s[i] - s[j])))[:, None]
        w_i = u[:, :, k] < pw
        wins[:, :, i] += w_i
        wins[:, :, j] += ~w_i
    top = np.argsort(-(wins + 0.5 * tie), axis=2)[
        :, :, :4
    ]  # wins are whole numbers: the 0.5 x tie term only breaks ties

    def win(a, b, r):  # team index arrays; a wins with chance logistic(beta x diff)
        p = 1 / (1 + np.exp(-bt[:, None] * (s[a] - s[b])))
        return np.where(r < p, a, b)

    t1, t2, t3, t4 = (top[:, :, i] for i in range(4))
    q1w, el = win(t1, t2, po[:, :, 0]), win(t3, t4, po[:, :, 1])
    q1l = np.where(q1w == t1, t2, t1)
    q2 = win(q1l, el, po[:, :, 2])
    champ = win(q1w, q2, po[:, :, 3])
    eye = np.arange(10)
    return {
        "playoff": (top[..., None] == eye).any(2).mean(1),
        "title": (champ[..., None] == eye).mean(1),
        "wins": wins.mean((0, 1)),
    }


def odds_summary(before: dict, after: dict, kinds=("playoff", "title")) -> dict:
    """{(team, kind): {'before'|'after'|'diff': (mean over all seasons, 10th, 90th percentile over beta draws)}}."""

    def f(d):
        return (float(d.mean()), float(np.percentile(d, 10)), float(np.percentile(d, 90)))

    out = {}
    for kind in kinds:
        for i, t in enumerate(ORDER):
            b, a = before[kind][:, i], after[kind][:, i]
            out[(t, kind)] = {"before": f(b), "after": f(a), "diff": f(a - b)}
    return out


# ── trade ────────────────────────────────────────────────────────────────────────────────────────────────────
def resolve(pt: pd.DataFrame, names, team: str) -> list[str]:
    """Squad labels for names given as contract name or Cricsheet name (case-insensitive). Unknown -> ValueError with valid names."""
    names = [names] if isinstance(names, str) else list(names or [])
    lut = {}
    for k, p in zip(pt.index, pt.player):
        lut[str(k).lower()] = k
        lut[str(p).lower()] = k
    out = []
    for n in names:
        k = lut.get(str(n).strip().lower())
        if k is None and team == "league":  # ~250 names: show the closest few, not all
            near = difflib.get_close_matches(str(n).strip().lower(), list(lut), n=5, cutoff=0.5)
            raise ValueError(
                f"{n!r} is not in the league squad. Closest: "
                + (
                    ", ".join(dict.fromkeys(str(lut[x]) for x in near))
                    or "none (check the spelling)"
                )
            )
        if k is None:
            raise ValueError(
                f"{n!r} is not in the {team} squad. Valid names: "
                + ", ".join(
                    sorted(f"{p} ({k})" if p != k else p for k, p in zip(pt.index, pt.player))
                )
            )
        out.append(k)
    if len(set(out)) != len(out):
        raise ValueError("A player is listed twice")
    return out


def moved_rows(
    pt_from: pd.DataFrame, keys: list[str], dest_abbr: str, contracts: pd.DataFrame
) -> pd.DataFrame:
    """The players as they join `dest_abbr`. A player takes the 2027 price on his traded_in row for that team if the contracts
    file has one (a real announced trade), else he keeps his current salary."""
    m = pt_from.loc[keys].copy()
    new = (
        contracts[(contracts.team == dest_abbr) & (contracts.status_2027 == "traded_in")]
        .set_index("key")
        .price_cr
    )
    for k in keys:
        if k in new.index:
            m.loc[k, "salary"] = float(new[k])
    m["team"] = dest_abbr
    m["value_per_cr"] = m.value / m.salary
    return m


def verdict(p_better: float, lo: float, hi: float) -> str:
    """Plain words from the share of bootstrap draws in which the XII is better. The range overlapping 0 is 'too close to call'."""
    if lo == hi == 0:
        return "no change to the best XII"
    if lo < 0 < hi and 0.3 < p_better < 0.7:
        return "too close to call"
    if p_better >= 0.8:
        return "likely better"
    if p_better <= 0.2:
        return "likely worse"
    return "leans better" if p_better > 0.5 else "leans worse"


def evaluate(
    team: str,
    team2: str,
    give=(),
    get=(),
    baseline: str = "current",
    contracts: pd.DataFrame | None = None,
    v: Values | None = None,
    must_play=(),
    odds: bool = True,
    value_basis: str = DEFAULT_BASIS,
) -> dict:
    """Trade evaluation. `give` leaves `team` for `team2`, `get` arrives from `team2`. `must_play` = names forced into their
    team's XI (before and after). odds=True adds a season simulation (playoff and title odds, see simulate()).
    Returns {'teams': {abbr: {...before/after numbers...}}, 'give': [...], 'get': [...], 'league': {...}}."""
    v = values() if v is None else v
    c = load_contracts() if contracts is None else contracts
    a, b = team_abbr(team), team_abbr(team2)
    if a == b:
        raise ValueError("Pick two different teams")
    gl, tl = (
        ([give] if isinstance(give, str) else list(give or [])),
        ([get] if isinstance(get, str) else list(get or [])),
    )
    # an empty give and get is valid on purpose: the dashboard default and must_play-only runs are a no-change baseline (F5)
    both = {str(x).strip().lower() for x in gl} & {str(x).strip().lower() for x in tl}
    if both:
        raise ValueError(
            f"{sorted(both)[0]!r} is on both sides of the trade: a player can only leave one team"
        )
    tab = player_table(squads(c, baseline, only=list(give or []) + list(get or [])), v, value_basis)
    A, B = tab[tab.team == a], tab[tab.team == b]
    gk, tk = resolve(A, give, a), resolve(B, get, b)
    ref = league_slot_means(tab)
    cpw = market_fit(tab)["cr_per_win_ratio"]
    force = resolve(tab, must_play, "league") if must_play else []
    A2 = pd.concat([A.drop(index=gk), moved_rows(B, tk, a, c)])
    B2 = pd.concat([B.drop(index=tk), moved_rows(A, gk, b, c)])
    out = {}
    for ab, before, after, got, lost in ((a, A, A2, tk, gk), (b, B, B2, gk, tk)):
        res = {"got": got, "lost": lost}
        for tag, pt in (("before", before), ("after", after)):
            pick = pick_xii(pt, force)
            D = draws_for(pt, v)
            d = xii_draws(pick, pt, D)
            lo, hi = rng_text(d)
            who = pick["xi"] + ([pick["impact"]] if pick["impact"] else [])
            sal = float(pt.loc[who, "salary"].sum())
            res[tag] = {
                "pick": pick,
                "value": pick["value"],
                "lo": lo,
                "hi": hi,
                "draws": d,
                "squad_salary": float(pt.salary.sum()),
                "xii_salary": sal,
                "value_per_cr": pick["value"] / sal if sal else 0.0,
                "holes": holes(pt, ref),
                "n_squad": len(pt),
                "table": pt,
                "assets_cr": pick["value"] * cpw,  # XII value at the market price per win
                "purse_left_cr": PURSE_CAP - float(pt.salary.sum()),
                "pdraws": D,
            }
        dd = res["after"]["draws"] - res["before"]["draws"]
        res["delta"] = float(res["after"]["value"] - res["before"]["value"])
        res["delta_lo"], res["delta_hi"] = rng_text(dd)
        res["p_better"] = float((dd > 0).mean())
        res["verdict"] = verdict(res["p_better"], res["delta_lo"], res["delta_hi"])
        res["purse_change"] = res["before"]["squad_salary"] - res["after"]["squad_salary"]

        # net value in rupees: surplus (value x market crore per win - salary above base) of who arrives minus who leaves
        def sur(t, ks):
            return float(
                sum(t.loc[k, "value"] * cpw - (t.loc[k, "salary"] - REPL_SALARY) for k in ks)
            )

        res["net_value_cr"] = sur(res["after"]["table"], got) - sur(res["before"]["table"], lost)
        res["holes_created"] = [h for h in res["after"]["holes"] if h not in res["before"]["holes"]]
        res["holes_filled"] = [h for h in res["before"]["holes"] if h not in res["after"]["holes"]]
        res["got_detail"] = player_cards(res["after"]["table"], res["after"]["pdraws"], got)
        out[ab] = res
    sim = None
    if odds:
        bt = beta(value_basis)
        strength = {}
        for t in TEAMS:
            strength[t] = (
                out[t]["before"]["value"]
                if t in out
                else pick_xii(tab[tab.team == t], force)["value"]
            )
        after = {**strength, a: out[a]["after"]["value"], b: out[b]["after"]["value"]}
        sim = {
            "beta": {k: bt[k] for k in ("beta", "lo", "hi", "n", "p_positive")},
            "odds": odds_summary(simulate(strength, bt["draws"]), simulate(after, bt["draws"])),
            "seasons": SIM_BETAS * SIM_SEASONS,
        }
    return {
        "sim": sim,
        "cr_per_win": cpw,
        "must_play": force,
        "teams": out,
        "give": gk,
        "get": tk,
        "league": ref,
        "baseline": baseline,
        "value_basis": value_basis,
        "order": (a, b),
    }


WORTH_CSV = w.DATA / "worth_headline.csv"
WORTH_IDS = {"bat": ("sr|middle|abs", "bnd|all|abs", "dot|all|abs"), "bowl": ("dot|all|abs", "bnd|all|abs", "econ|middle|abs")}


def build_worth_headline(db_path=None) -> pd.DataFrame:
    """Display-only: 3 headline player_worth metrics per role (shrunk value + percentile among IPL 2023+ peers with 100+ balls) and the
    expected matches next season (player_outlook), one row per player and metric. Does not feed the XII search."""
    from ..sql.filters import Filters
    from . import player_outlook as PO
    from . import worth

    d = worth.ball_frame(Filters(competition="ipl", season_from=SEASONS[0]))
    parts = []
    for role in ("bat", "bowl"):
        p = worth.profile(d, role)
        parts.append(p[p.id.isin(WORTH_IDS[role])].assign(role=role))
    t = pd.concat(parts)[["player", "role", "id", "metric", "value", "pctile", "n"]]
    o = PO.outlook(sorted(t.player.unique())).set_index("player")[["exp_matches", "m10", "m90"]]
    return t.join(o, on="player").round(2)


@lru_cache(maxsize=1)
def worth_headline() -> pd.DataFrame:
    return pd.read_csv(WORTH_CSV) if WORTH_CSV.exists() else pd.DataFrame(columns=["player", "role", "id"])


def _worth_of(key: str) -> dict | None:
    """Headline metrics of the role he has most balls in: [{label, value, pctile}], plus expected matches range (or None)."""
    h = worth_headline()
    h = h[h.player == key]
    if h.empty:
        return None
    role = h.groupby("role").n.max().idxmax()
    h = h[h.role == role]
    r0 = h.iloc[0]
    m = None if pd.isna(r0.exp_matches) else (float(r0.exp_matches), float(r0.m10), float(r0.m90))
    return {
        "role": role,
        "metrics": [dict(label=r.metric, value=float(r.value), pctile=int(r.pctile)) for r in h.itertuples()],
        "matches": m,
    }


def player_cards(pt: pd.DataFrame, D: np.ndarray, keys) -> list[dict]:
    """What a trade card shows for each player: price, recent value with its 10-90 range, bowler pWAR, headline worth metrics
    (display only), expected matches next season."""
    pos = {k: i for i, k in enumerate(pt.index)}
    out = []
    for k in keys:
        r, d = pt.loc[k], D[pos[k]]
        out.append(
            {
                "name": str(r.player),
                "price": float(r.salary),
                "value": float(r.value),
                "lo": float(np.percentile(d, 10)),
                "hi": float(np.percentile(d, 90)),
                "pwar_bowl": float(r.pwar_bowl) if r.is_bowler else None,
                "evidence": bool(r.has_evidence),
                "worth": _worth_of(k),
            }
        )
    return out


def squad_names(team: str) -> list[str]:
    """Contract names of one team's players, current and before announced trades (the dashboard's give / get lists)."""
    a = team_abbr(team)
    out = set()
    for b in ("current", "before_trades"):
        s = squads(baseline=b)
        out |= set(s[s.team == a].player)
    return sorted(out)


def roles(pt: pd.DataFrame):
    bats = (pt.bat_matches >= 5) & (pt.bat_pos <= 7.5)
    return np.select(
        [~pt.has_evidence, pt.keeper, bats & pt.is_bowler, pt.is_bowler],
        ["no IPL evidence", "wicketkeeper", "all-rounder", "bowler"],
        "batter",
    )


def squad_view(team: str, basis: str = DEFAULT_BASIS) -> pd.DataFrame:
    """One team's squad: salary, recent WAR by season, recent value with range, value per crore, surplus, XII membership."""
    v = values()
    tab = player_table(squads(), v, basis)
    a = team_abbr(team)
    cpw = market_fit(tab)["cr_per_win_ratio"]
    pt = tab[tab.team == a]
    pick = pick_xii(pt)
    D = draws_for(pt, v)
    lo, hi = np.percentile(D, 10, axis=1), np.percentile(D, 90, axis=1)
    role = roles(pt)
    out = pd.DataFrame(
        {
            "player": pt.player.values,
            "role": role,
            "overseas": pt.overseas.values,
            "salary_cr": pt.salary.values,
            **{f"war_{s}": pt[f"war_{s}"].round(2).values for s in SEASONS},
            "recent_value": pt.value.round(2).values,
            "range_lo": lo.round(2),
            "range_hi": hi.round(2),
            "bowl_pwar": pt.pwar_bowl.round(2).values,
            "value_per_cr": pt.value_per_cr.round(3).values,
            "surplus_cr": (pt.value * cpw - (pt.salary - REPL_SALARY)).round(1).values,
            "in_best_xii": np.where(
                pt.index.isin(pick["xi"]), "XI", np.where(pt.index == pick["impact"], "impact", "")
            ),
            "cr_per_win": round(cpw, 1),
        }
    )
    return out.sort_values(["recent_value", "player"], ascending=[False, True]).reset_index(
        drop=True
    )


def main() -> None:
    import sys

    if "beta" in sys.argv[1:]:
        d = build_beta_matches()
        d.to_csv(BETA_CSV, index=False)
        b = fit_beta(d)
        print(
            f"wrote {BETA_CSV.name}: {len(d)} matches; beta {b['beta']:.3f} (10-90: {b['lo']:.3f} to {b['hi']:.3f})"
        )
        return
    m = build()
    print(f"wrote {MATCH_CSV.name}: {len(m)} rows")
    h = build_worth_headline()
    h.to_csv(WORTH_CSV, index=False)
    print(f"wrote {WORTH_CSV.name}: {len(h)} rows")


if __name__ == "__main__":
    main()
