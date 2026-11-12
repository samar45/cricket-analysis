"""Features from parsed Cricbuzz commentary (IPL 2017+), joined to Cricsheet deliveries (docs/EDA_commentary.md).

fill(d)        flagged fills (speed from bowler medians, wide => line); never imputes length / delivery statistically
ball_features  per-ball flags (false shot, edge boundary, short / yorker / ...)
player_season  bat / bowl tables per (player, season) -> data/external/commentary/features_{bat,bowl}.csv
Missing commentary values mean "not mentioned", so rates are shares of ALL balls for contact / delivery flags and
shares of balls with a known length / line for mixes.
"""

import numpy as np
import pandas as pd

OUT = "data/external/commentary"
FALSE_CONTACT = {"miss", "edge", "inside edge", "top edge", "leading edge", "bottom edge", "mistimed"}
EDGE = {"edge", "inside edge", "top edge", "leading edge", "bottom edge"}
SHORT = {"short", "bouncer", "short of length"}
GOOD = {"length", "back of a length"}
FULL = {"full", "full toss"}
SPEED_OK = (50.0, 160.0)  # quoted values outside are parse errors (EDA: 10, 943 kph exist), never used or filled from
MIN_Q = 10  # quoted balls a bowler needs before his median is used to fill


def load_frame(season_from: int = 2017) -> pd.DataFrame:
    """Cricsheet ball frame (runs added, WPA, bowl_kind from the reviewed list) inner-joined with parsed commentary."""
    from ..ingest.commentary import load_parsed
    from ..sql.filters import Filters
    from . import worth

    d = worth.ball_frame(Filters(competition="ipl", season_from=season_from))
    p = load_parsed().rename(columns={"event": "cb_event", "extra": "cb_extra"})
    keep = ["match_id", "innings", "ball_seq", "speed", "length", "line", "delivery", "contact", "shot", "lapse",
            "cb_event", "cb_extra", "bat_id", "bowl_id", "bat_mins", "bat_dots"]
    p = p[keep].drop_duplicates(["match_id", "innings", "ball_seq"])
    d["year"] = d.year.astype(int)
    return d.merge(p, on=["match_id", "innings", "ball_seq"], how="inner")


def fill(d: pd.DataFrame) -> pd.DataFrame:
    """Add speed_f / length_f / line_f with *_src in {text, filled_bowler, filled_rule, NA}. Needs speed, length, line,
    wides, bowler, year, bowl_kind. Speed fill: bowler-season median of valid quoted speeds if >= MIN_Q such balls, else
    bowler overall median if >= MIN_Q; only for bowlers of known kind and only when the median fits the kind
    (pace >= 100, spin <= 110) so a pace median is never written onto a spinner. Length / line: text, plus the rule
    Cricsheet wide => line 'wide'. No statistical imputation; delivery is not touched."""
    d = d.copy()
    sp = d.speed.where(d.speed.between(*SPEED_OK))
    d["speed_f"], d["speed_src"] = sp, np.where(sp.notna(), "text", None)
    g = pd.DataFrame({"b": d.bowler, "y": d.year, "s": sp})
    by = g.groupby(["b", "y"]).s.agg(["median", "count"])
    bo = g.groupby("b").s.agg(["median", "count"])
    m_by = pd.Series(list(zip(g.b, g.y))).map(by["median"].where(by["count"] >= MIN_Q)).to_numpy()
    m_bo = g.b.map(bo["median"].where(bo["count"] >= MIN_Q)).to_numpy()
    med = np.where(np.isnan(m_by), m_bo, m_by)
    fits = np.where(d.bowl_kind == "pace", med >= 100, np.where(d.bowl_kind == "spin", med <= 110, False))
    use = sp.isna() & ~np.isnan(med) & fits
    d.loc[use, "speed_f"] = med[use]
    d.loc[use, "speed_src"] = "filled_bowler"
    d["length_f"], d["length_src"] = d.length, np.where(d.length.notna(), "text", None)
    d["line_f"], d["line_src"] = d.line, np.where(d.line.notna(), "text", None)
    w = d.line.isna() & (d.wides > 0)
    d.loc[w, "line_f"], d.loc[w, "line_src"] = "wide", "filled_rule"
    return d


def ball_features(d: pd.DataFrame) -> pd.DataFrame:
    """Per-ball 0/1 flags (float columns f_*). Uses length_f / line_f when fill() has run, else the raw columns."""
    d = d.copy()
    ln = d["length_f"] if "length_f" in d else d.length
    li = d["line_f"] if "line_f" in d else d.line
    legal = (d.wides == 0) & (d.noballs == 0)
    faced = d.wides == 0
    b = d.runs_batter.isin([4, 6])
    d["faced"], d["legal"] = faced.astype(float), legal.astype(float)
    d["f_false"] = (faced & d.contact.isin(FALSE_CONTACT)).astype(float)
    d["f_miss"] = (faced & (d.contact == "miss")).astype(float)
    d["f_edge"] = (faced & d.contact.isin(EDGE)).astype(float)
    d["f_mistime"] = (faced & (d.contact == "mistimed")).astype(float)
    d["f_edge_bnd"] = (b & d.contact.isin(EDGE)).astype(float)
    d["f_clean_bnd"] = (b & ~d.contact.isin(FALSE_CONTACT)).astype(float)
    d["f_bnd"] = b.astype(float)
    d["f_yorker"] = (ln == "yorker").astype(float)
    d["f_fulltoss"] = (ln == "full toss").astype(float)
    d["f_short"] = ln.isin(SHORT).astype(float)
    d["f_slower"] = (d.delivery == "slower ball").astype(float)
    d["known_len"], d["known_line"] = ln.notna().astype(float), li.notna().astype(float)
    d["len_c"] = np.where(ln.isin(SHORT), "short", np.where(ln.isin(GOOD), "good", np.where(ln.isin(FULL), "full", np.where(ln == "yorker", "yorker", None))))
    d["line_c"] = li
    # drop: Cricbuzz DROPPED event or text lapse; runs the batter added after it until the end of his innings
    drop = d.cb_event.fillna("").str.contains("DROPPED") | (d.lapse == "drop")
    d["f_drop"] = drop.astype(float)
    d["f_runout_miss"] = d.cb_event.fillna("").str.contains("RUNOUT_MISS").astype(float)
    d = d.sort_values(["match_id", "innings", "ball_seq"])
    after = d.groupby(["match_id", "innings", "batter"]).runs_batter.transform(lambda s: s[::-1].cumsum()[::-1] - s)
    d["runs_after_drop"] = np.where(drop.reindex(d.index), after, np.nan)
    return d


def _mix_entropy(g: pd.Series) -> float:
    p = g.dropna().value_counts(normalize=True)
    return float(-(p * np.log(p)).sum()) if len(p) else np.nan


def player_season(d: pd.DataFrame, role: str, min_balls: int = 30) -> pd.DataFrame:
    """One row per (player, year) for role 'bat' or 'bowl'. Columns n (balls) + features; slice features need
    >= min_balls known balls in the slice, else NaN."""
    key = "batter" if role == "bat" else "bowler"
    d = d[d.faced == 1] if role == "bat" else d
    rows = []
    for (p, y), g in d.groupby([key, "year"]):
        n = len(g)
        r = {"player": p, "year": y, "n": n}
        r["false_pct"], r["miss_pct"], r["edge_pct"], r["mistime_pct"] = (g[c].mean() for c in ("f_false", "f_miss", "f_edge", "f_mistime"))
        r["edge_bnd_pct"], r["clean_bnd_pct"] = g.f_edge_bnd.mean(), g.f_clean_bnd.mean()
        r["edge_bnd_share"] = g.f_edge_bnd.sum() / g.f_bnd.sum() if g.f_bnd.sum() >= 10 else np.nan
        r["drop_n"] = g.f_drop.sum()
        r["runs_after_drop"] = g.runs_after_drop.sum()
        if role == "bat":
            r["sr"], r["bnd_pct"], r["out_pct"] = g.runs_batter.mean() * 100, g.f_bnd.mean(), (g.player_out == g.batter).mean()
            for s, name in (("short", "short"), ("full", "full"), ("good", "good")):
                h = g[g.len_c == s]
                ok = len(h) >= min_balls
                r[f"sr_vs_{name}"] = h.runs_batter.mean() * 100 if ok else np.nan
                r[f"out_vs_{name}"] = (h.player_out == h.batter).mean() if ok else np.nan
            h = g[g.line_c == "outside off"]
            ok = len(h) >= min_balls
            r["sr_vs_outside_off"] = h.runs_batter.mean() * 100 if ok else np.nan
            r["out_vs_outside_off"] = (h.player_out == h.batter).mean() if ok else np.nan
            r["ra"], r["wpa"] = g.bat_ra.mean(), g.bat_wpa.where(g.bat_who == g.batter, 0).mean()
        else:
            lg = g[g.legal == 1]
            r["econ_ball"] = (g.runs_batter + g.wides + g.noballs).mean()
            r["bnd_pct"], r["wk_pct"] = g.f_bnd.mean(), g.wicket_type.notna().mean()
            r["yorker_pct"] = lg.f_yorker.sum() / lg.known_len.sum() if lg.known_len.sum() >= min_balls else np.nan
            r["short_pct"] = lg.f_short.sum() / lg.known_len.sum() if lg.known_len.sum() >= min_balls else np.nan
            dg = lg[lg.phase == "death"]
            kd = dg.known_len.sum()
            r["death_fulltoss_pct"] = dg.f_fulltoss.sum() / kd if kd >= min_balls else np.nan
            r["death_yorker_pct"] = dg.f_yorker.sum() / kd if kd >= min_balls else np.nan
            r["len_entropy"] = _mix_entropy(lg.len_c) if lg.known_len.sum() >= min_balls else np.nan
            r["slower_pct"] = lg.f_slower.mean()
            r["ra"], r["wpa"] = g.bowl_ra.mean(), g.bowl_wpa.mean()
        rows.append(r)
    return pd.DataFrame(rows)


_CNT: dict = {}
PLUS_FEATS = ("death_yorker", "slower", "false")  # worth_plus extras: (numerator col, denominator col) in bowler_counts
K_CLAMP = (30.0, 3000.0)  # balls of evidence a rate needs to be trusted half-way; clamp for the fitted k


def bowler_counts() -> pd.DataFrame:
    """Per (bowler, year) counts behind the three worth_plus features: death yorkers / death balls with a known length,
    slower balls / legal balls, false shots / balls (any contact mention counts as 'known' only for the false-shot share
    of ALL balls: contact and delivery mentions are missing-not-at-random, length is close to random). Cached."""
    if "c" not in _CNT:
        d = ball_features(fill(load_frame(2017)))
        lg = d[d.legal == 1]
        dg = lg[lg.phase == "death"]
        c = pd.DataFrame({
            "death_yorker_n": dg.groupby(["bowler", "year"]).f_yorker.sum(), "death_yorker_d": dg.groupby(["bowler", "year"]).known_len.sum(),
            "slower_n": lg.groupby(["bowler", "year"]).f_slower.sum(), "slower_d": lg.groupby(["bowler", "year"]).size(),
            "false_n": d.groupby(["bowler", "year"]).f_false.sum(), "false_d": d.groupby(["bowler", "year"]).faced.sum()}).fillna(0.0)
        _CNT["c"] = c
    return _CNT["c"]


def _k(n: pd.Series, d: pd.Series) -> float:
    """Reliability k (balls of average evidence) of a rate by method of moments on bowler totals; mu = pooled rate."""
    m = d > 0
    n, d = n[m], d[m]
    mu = n.sum() / d.sum()
    between = ((d * (n / d - mu) ** 2).sum() - (len(d) - 1) * mu * (1 - mu)) / (d.sum() - (d**2).sum() / d.sum())
    return float(np.clip(mu * (1 - mu) / between, *K_CLAMP)) if between > 1e-12 else K_CLAMP[1]


def bowl_plus_feats(Xc: int, which=PLUS_FEATS) -> pd.DataFrame:
    """Per bowler, commentary data of years <= Xc only: shrunk rate minus the pooled rate, one column per feature in `which`
    (0 = no evidence or average). k is refitted from the same years, so nothing from later years leaks in."""
    c = bowler_counts()
    c = c[c.index.get_level_values("year") <= Xc].groupby(level="bowler").sum()
    out = pd.DataFrame(index=c.index)
    for f in which:
        n, d = c[f"{f}_n"], c[f"{f}_d"]
        if d.sum() == 0:
            out[f"cm_{f}"] = 0.0
            continue
        mu, k = n.sum() / d.sum(), _k(n, d)
        out[f"cm_{f}"] = (n + k * mu) / (d + k) - mu
    return out


def team_season_fielding(d: pd.DataFrame) -> pd.DataFrame:
    """Dropped catches and missed run-out chances per fielding team-season, with runs conceded after the drop."""
    t = d.groupby(["bowling_team", "year"]).agg(balls=("legal", "size"), drops=("f_drop", "sum"), runout_miss=("f_runout_miss", "sum"),
                                                runs_after_drop=("runs_after_drop", "sum")).reset_index()
    t["drops_per_1000"] = t.drops / t.balls * 1000
    return t


def build(season_from: int = 2017, save: bool = True):
    d = ball_features(fill(load_frame(season_from)))
    bat, bowl, team = player_season(d, "bat"), player_season(d, "bowl"), team_season_fielding(d)
    if save:
        bat.to_csv(f"{OUT}/features_bat.csv", index=False)
        bowl.to_csv(f"{OUT}/features_bowl.csv", index=False)
        team.to_csv(f"{OUT}/features_team_fielding.csv", index=False)
    return d, bat, bowl, team


if __name__ == "__main__":
    d, *_ = build()
    print(d.shape)
