"""Cross-league player profile for auction scouting: Indian state T20 leagues + SMAT 2025 (Cricbuzz scorecards) + IPL / earlier
SMAT / T20I (Cricsheet, read-only DB), one row per (competition, season).

Same person across Cricbuzz files = same cricbuzz_id (link "strong"). Cricbuzz -> Cricsheet goes through the scraper's `cricsheet_name`:
SMAT 2025's is team-scoped ("team_checked"); a state-league one is name-only ("name_only") and gets sanity checks, failing = "doubtful".
Doubtful Cricsheet rows are withheld from profile() unless include_doubtful=True. SMAT 2026 and anything dated >= 2026-10-15 is never read.
"""
import functools
import glob
import re

import pandas as pd

from ..sql.fragments import BALL_FACED, BOWLER_WICKET, DISMISSAL, LEGAL_BALL, RUNS_CONCEDED
from .reels import NotExact
from .smat2025 import ROOT as SMAT

CB = SMAT.parent
CUTOFF = "2026-10-15"
DB_COMPS = {"ipl": "IPL", "smat": "SMAT", "t20i": "T20I"}
STATE = {"spl": "Sher-e-Punjab T20 League", "upt20": "UP T20 League", "tnpl": "Tamil Nadu Premier League", "dpl": "Delhi Premier League",
         "maharaja": "Maharaja Trophy KSCA T20", "mumbai": "T20 Mumbai League", "bengal": "Bengal Pro T20", "saurashtra": "Saurashtra Premier League",
         "rpl": "Rajasthan Premier League", "apl": "Andhra Premier League", "kcl": "Kerala Cricket League", "mppl": "Madhya Pradesh Premier League",
         "mpl": "Maharashtra Premier League", "cgpl": "Chhattisgarh Premier League", "ppl": "Pondicherry Premier League"}


def available() -> bool:
    return (SMAT / "batting.parquet").exists() and bool(glob.glob(str(CB / "state_*" / "*" / "batting.parquet")))


def _cb(kind: str) -> pd.DataFrame:
    """Per-innings Cricbuzz rows (state leagues + SMAT 2025) with competition, season, date."""
    parts = []
    files = [("SMAT", SMAT / f"{kind}.parquet", SMAT / "matches.parquet")]
    for f in glob.glob(str(CB / "state_*" / "*" / f"{kind}.parquet")):
        key = re.search(r"state_(\w+)", f.replace("\\", "/")).group(1)
        files.append((STATE.get(key, key), f, f.replace(kind, "matches")))
    for comp, f, mf in files:
        d = pd.read_parquet(f).merge(pd.read_parquet(mf)[["match_id", "date"]], on="match_id")
        parts.append(d.assign(competition=comp))
    d = pd.concat(parts, ignore_index=True)
    d["dt"] = pd.to_datetime(d.date)
    d = d[d.dt < CUTOFF]
    d["season"] = d.dt.dt.year.astype(str)
    return d


@functools.lru_cache(maxsize=1)
def _cbd():
    b, w = _cb("batting"), _cb("bowling")
    return b, w


def _names() -> pd.DataFrame:
    b, w = _cbd()
    return pd.concat([b[["cricbuzz_id", "name", "team", "dt"]], w[["cricbuzz_id", "name", "team", "dt"]]])


def _mode(s):
    s = s[s != ""]
    return s.mode().iloc[0] if len(s) else ""


def _cs_frames(names: list[str], comps=tuple(DB_COMPS)):
    """Per-innings Cricsheet batting / bowling for these names (men's, innings 1-2, before the cutoff)."""
    from ..db import query
    cl = ",".join(f"'{c}'" for c in comps)
    base = (f"FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender='male' AND m.competition IN ({cl}) "
            f"AND m.date < DATE '{CUTOFF}' AND d.innings <= 2 AND ")
    sel = "m.competition AS competition, CAST(year(m.date) AS VARCHAR) AS season, d.match_id, d.innings, any_value(m.date) AS dt"
    b = query(f"SELECT d.batter AS cricsheet_name, {sel}, sum(d.runs_batter) AS runs, sum(CASE WHEN {BALL_FACED} THEN 1 ELSE 0 END) AS balls "
              f"{base} d.batter IN (SELECT unnest(?)) GROUP BY ALL", [names])
    o = query(f"SELECT d.player_out AS cricsheet_name, d.match_id, d.innings, 1 AS is_out {base} {DISMISSAL} "
              f"AND d.player_out IN (SELECT unnest(?)) GROUP BY ALL", [names])
    b = b.merge(o, on=["cricsheet_name", "match_id", "innings"], how="left")
    b["is_out"] = b.is_out.fillna(0).astype(bool)
    w = query(f"SELECT d.bowler AS cricsheet_name, {sel}, sum(CASE WHEN {LEGAL_BALL} THEN 1 ELSE 0 END) AS balls, "
              f"sum({RUNS_CONCEDED}) AS runs, sum(CASE WHEN {BOWLER_WICKET} THEN 1 ELSE 0 END) AS wickets "
              f"{base} d.bowler IN (SELECT unnest(?)) GROUP BY ALL", [names])
    for t in (b, w):
        t["dt"] = pd.to_datetime(t.dt)
        t["competition"] = t.competition.map(DB_COMPS)
    return b, w


def _summ(b: pd.DataFrame, w: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per-innings batting / bowling -> one row per keys: inns, runs, balls, avg, sr, 50s, 100s, overs, wkts, econ, bowl avg."""
    b = b.assign(f50=(b.runs >= 50) & (b.runs < 100), f100=b.runs >= 100)
    bt = b.groupby(keys).agg(inns=("runs", "size"), runs=("runs", "sum"), balls=("balls", "sum"), outs=("is_out", "sum"),
                             fifties=("f50", "sum"), hundreds=("f100", "sum"), first_date=("dt", "min"), last_date=("dt", "max"))
    bw = w.groupby(keys).agg(bowl_balls=("balls", "sum"), runs_conceded=("runs", "sum"), wkts=("wickets", "sum"),
                             bfirst=("dt", "min"), blast=("dt", "max"))
    t = bt.join(bw, how="outer")
    t["first_date"], t["last_date"] = t[["first_date", "bfirst"]].min(axis=1), t[["last_date", "blast"]].max(axis=1)
    t = t.drop(columns=["bfirst", "blast"])
    n = [c for c in t.columns if c not in ("first_date", "last_date")]
    t[n] = t[n].fillna(0).astype(int)
    t["avg"] = (t.runs / t.outs.replace(0, float("nan"))).round(1)
    t["sr"] = (t.runs / t.balls.replace(0, float("nan")) * 100).round(1)
    t["overs"] = (t.bowl_balls // 6 + t.bowl_balls % 6 / 10).round(1)
    t["econ"] = (t.runs_conceded / t.bowl_balls.replace(0, float("nan")) * 6).round(2)
    t["bowl_avg"] = (t.runs_conceded / t.wkts.replace(0, float("nan"))).round(1)
    return t.drop(columns="outs").reset_index()


def _initials_ok(cs: str, cb: str) -> bool:
    """'RP Singh' vs 'Reavan Preet Singh'. A full-name Cricsheet entry (not initials) is not checked here."""
    tok = cs.split(" ")[0]
    if not (tok.isupper() and len(tok) <= 3 and len(cs.split()) > 1):
        return True
    ini = "".join(w[0].upper() for w in cb.split()[:-1])
    return ini.startswith(tok) or tok.startswith(ini)


@functools.lru_cache(maxsize=1)
def links() -> pd.DataFrame:
    """One row per cricbuzz_id: cricsheet_name, link (team_checked / name_only / doubtful / ''), link_note."""
    b, w = _cbd()
    ids = _names().groupby("cricbuzz_id").agg(name=("name", _mode), first=("dt", "min"))
    both = pd.concat([b, w])
    smat = both[both.competition == "SMAT"].groupby("cricbuzz_id").cricsheet_name.agg(_mode)
    state = both[both.competition != "SMAT"].groupby("cricbuzz_id").cricsheet_name.agg(_mode)
    ids["cricsheet_name"] = smat.reindex(ids.index).fillna("")
    ids["link"] = ["team_checked" if n else "" for n in ids.cricsheet_name]
    ids["link_note"] = ""
    for i in ids.index[ids.cricsheet_name == ""]:
        if state.get(i, ""):
            ids.loc[i, ["cricsheet_name", "link"]] = [state[i], "name_only"]
    # still blank: unique-name guess from the SMAT scouting helper (exact / derived short name / initials). Always name_only, same checks below.
    from .smat2025 import second_pass
    blank = ids[ids.cricsheet_name == ""].reset_index()
    g = second_pass(blank[["cricbuzz_id", "name", "cricsheet_name"]]).set_index("cricbuzz_id")
    g = g[g.cricsheet_name != ""]
    ids.loc[g.index, "cricsheet_name"] = g.cricsheet_name
    ids.loc[g.index, "link"] = "name_only"
    nm = sorted(set(ids.cricsheet_name) - {""})
    from ..db import query
    h = query(f"SELECT n, min(date) AS f, max(date) AS l FROM (SELECT match_id, batter n FROM deliveries UNION SELECT match_id, bowler FROM deliveries) p "
              f"JOIN matches USING (match_id) WHERE gender='male' AND date < DATE '{CUTOFF}' AND n IN (SELECT unnest(?)) GROUP BY n", [nm]).set_index("n")
    claims = ids[ids.cricsheet_name != ""].groupby("cricsheet_name").size()
    for i, r in ids[ids.link == "name_only"].iterrows():
        why = []
        if claims[r.cricsheet_name] > 1:
            why.append(f"{claims[r.cricsheet_name]} Cricbuzz players share this Cricsheet name")
        if not _initials_ok(r.cricsheet_name, r["name"]):
            why.append("initials disagree")
        if r.cricsheet_name in h.index:
            f, l = h.loc[r.cricsheet_name, ["f", "l"]]
            if i >= 1_000_000 and pd.Timestamp(f) < pd.Timestamp("2022-01-01"):
                why.append(f"new Cricbuzz profile (id {i}) but Cricsheet player debuted {pd.Timestamp(f):%Y-%m-%d}")
            if pd.Timestamp(l) < pd.Timestamp(r["first"]) - pd.DateOffset(years=3):
                why.append(f"Cricsheet player's last match {pd.Timestamp(l):%Y-%m-%d} is 3+ years before the Cricbuzz player's first")
        else:
            why.append("not found in Cricsheet DB")
        if why:
            ids.loc[i, ["link", "link_note"]] = ["doubtful", "; ".join(why)]
    return ids


def _resolve(query_: str) -> int:
    n = _names()
    if str(query_).strip().isdigit():
        i = int(query_)
        if i not in set(n.cricbuzz_id):
            raise ValueError(f"cricbuzz_id {i} not found")
        return i
    hit = n[n.name.str.lower() == str(query_).strip().lower()]
    ids = sorted(set(hit.cricbuzz_id))
    if len(ids) == 1:
        return ids[0]
    pool = hit if ids else n[n.name.str.lower().str.contains(str(query_).strip().lower(), regex=False)]
    cands = [dict(cricbuzz_id=int(i), name=g.name.iloc[0], team=g.sort_values("dt").team.iloc[-1], role="")
             for i, g in pool.groupby("cricbuzz_id")][:8]
    raise NotExact(f"{query_!r} is " + ("ambiguous" if ids else "not an exact name") + "; give the cricbuzz_id. candidates: "
                   + "; ".join(f"{c['name']} ({c['team']}, id {c['cricbuzz_id']})" for c in cands), cands)


COLS = ["cricbuzz_id", "name", "competition", "season", "source", "link", "link_note", "cricsheet_name", "inns", "runs", "balls", "avg", "sr",
        "fifties", "hundreds", "bowl_balls", "overs", "wkts", "runs_conceded", "econ", "bowl_avg", "first_date", "last_date"]


def _rows(ids, comps=tuple(DB_COMPS), include_doubtful=False) -> pd.DataFrame:
    b, w = _cbd()
    b, w = b[b.cricbuzz_id.isin(ids)], w[w.cricbuzz_id.isin(ids)]
    k = ["cricbuzz_id", "competition", "season"]
    cb = _summ(b, w, k).assign(source="cricbuzz_scorecard", link="strong", link_note="", cricsheet_name="")
    lk = links().loc[list(ids)]
    lk = lk[lk.cricsheet_name != ""]
    withheld = lk[lk.link == "doubtful"]
    if not include_doubtful:
        lk = lk[lk.link != "doubtful"]
    parts = [cb]
    if len(lk) and comps:
        cb_, cw_ = _cs_frames(sorted(set(lk.cricsheet_name)), comps)
        cs = _summ(cb_, cw_, ["cricsheet_name", "competition", "season"])
        cs = lk.reset_index()[["cricbuzz_id", "cricsheet_name", "link", "link_note"]].merge(cs, on="cricsheet_name")
        parts.append(cs.assign(source="cricsheet"))
    out = pd.concat(parts, ignore_index=True)
    out = out.merge(links()["name"].reset_index(), on="cricbuzz_id")
    out = out.sort_values(["cricbuzz_id", "last_date"], ignore_index=True)[COLS]
    out.attrs["withheld"] = [f"{r.cricsheet_name} ({r.link_note})" for r in withheld.itertuples()]
    return out


def profile(query: str, include_doubtful: bool = False) -> pd.DataFrame:
    """Rows per (competition, season) for one player (name or cricbuzz_id). Ambiguous name -> NotExact with candidates."""
    return _rows([_resolve(query)], include_doubtful=include_doubtful)


def board(min_balls: int = 100) -> pd.DataFrame:
    """Auction shortlist: every state-league player with >= min_balls faced or bowled, with state / SMAT 2025 / IPL totals and ipl_capped.
    score = runs above the state-league average strike rate over his balls + runs saved vs the average economy over his overs."""
    b, w = _cbd()
    sb, sw = b[b.competition != "SMAT"], w[w.competition != "SMAT"]
    lg_sr, lg_ec = sb.runs.sum() / sb.balls.sum() * 100, sw.runs.sum() / sw.balls.sum() * 6
    bt = sb.groupby("cricbuzz_id").agg(state_inns=("runs", "size"), state_runs=("runs", "sum"), state_balls=("balls", "sum"), state_outs=("is_out", "sum"))
    bw = sw.groupby("cricbuzz_id").agg(state_bowl_balls=("balls", "sum"), state_runs_conc=("runs", "sum"), state_wkts=("wickets", "sum"))
    t = bt.join(bw, how="outer").fillna(0)
    t = t[(t.state_balls >= min_balls) | (t.state_bowl_balls >= min_balls)].copy()
    t["state_sr"] = (t.state_runs / t.state_balls.replace(0, float("nan")) * 100).round(1)
    t["state_avg"] = (t.state_runs / t.state_outs.replace(0, float("nan"))).round(1)
    t["state_econ"] = (t.state_runs_conc / t.state_bowl_balls.replace(0, float("nan")) * 6).round(2)
    t["bat_score"] = (t.state_runs - lg_sr * t.state_balls / 100).round(1)
    t["bowl_score"] = (lg_ec * t.state_bowl_balls / 6 - t.state_runs_conc).round(1)
    t["score"] = (t.bat_score + t.bowl_score).round(1)
    r = _rows(list(t.index), comps=("ipl",))
    for pre, comp in (("smat", "SMAT"), ("ipl", "IPL")):
        s = r[r.competition == comp].groupby("cricbuzz_id")[["runs", "balls", "wkts", "bowl_balls"]].sum()
        t = t.join(s.add_prefix(pre + "_"))
    lk = links().reindex(t.index)
    t["ipl_link"] = lk.link.fillna("")
    from ..db import query
    names = sorted(set(lk.cricsheet_name[lk.link.isin(["team_checked", "name_only"])]))
    seen = set(query("SELECT DISTINCT n FROM (SELECT match_id, batter n FROM deliveries UNION SELECT match_id, bowler FROM deliveries "
                     "UNION SELECT match_id, non_striker FROM deliveries) p JOIN matches m USING (match_id) WHERE m.competition='ipl' "
                     f"AND m.date < DATE '{CUTOFF}' AND n IN (SELECT unnest(?))", [names]).n)
    t["ipl_capped"] = ["unknown" if l not in ("team_checked", "name_only") else ("yes" if n in seen else "no")
                       for l, n in zip(lk.link.fillna(""), lk.cricsheet_name.fillna(""))]
    t["smat_in_2025"] = t.index.isin(set(_cb("batting").query("competition == 'SMAT'").cricbuzz_id))
    n = _names().sort_values("dt").groupby("cricbuzz_id").agg(name=("name", "last"), team=("team", "last"))
    t = n.join(t, how="inner").fillna({c: 0 for c in t.columns if t[c].dtype != object and not c.startswith(("state_sr", "state_avg", "state_econ"))})
    t = t.drop(columns=["state_outs", "state_runs_conc"])
    ints = [c for c in t.columns if c.startswith(("state_inns", "state_runs", "state_balls", "state_bowl", "state_wkts", "smat_", "ipl_runs", "ipl_balls", "ipl_wkts", "ipl_bowl")) and t[c].dtype != object and c != "smat_in_2025"]
    t[ints] = t[ints].astype(int)
    return t.reset_index().sort_values("score", ascending=False, ignore_index=True)


def write_report(path="docs/REPORT_cross_league.md", min_balls: int = 100):
    """python -m cricket_analytics.scouting.profile : writes the shortlist report."""
    b = board(min_balls)
    lk = links()
    b_, w_ = _cbd()
    st = set(b_[b_.competition != "SMAT"].cricbuzz_id) | set(w_[w_.competition != "SMAT"].cricbuzz_id)
    sm = set(b_[b_.competition == "SMAT"].cricbuzz_id) | set(w_[w_.competition == "SMAT"].cricbuzz_id)
    md = lambda d: chr(10).join(["| " + " | ".join(d.columns) + " |", "|" + "---|" * d.shape[1]] + ["| " + " | ".join(map(str, r)) + " |" for r in d.fillna("-").values])
    bat = ["name", "team", "state_inns", "state_runs", "state_balls", "state_avg", "state_sr", "bat_score", "smat_runs", "smat_balls", "ipl_link"]
    bowl = ["name", "team", "state_bowl_balls", "state_wkts", "state_econ", "bowl_score", "smat_wkts", "smat_bowl_balls", "ipl_link"]
    top = lambda cap, col, cols, n=15: md(b[(b.ipl_capped == cap) & (b[col] > 0)].sort_values(col, ascending=False).head(n)[cols])
    out = f"""# Cross-league scouting board (state T20 leagues + SMAT 2025 + IPL)

Built by `src/cricket_analytics/scouting/profile.py` (`cricket scouting board`, `cricket scouting profile "<name or id>"`). Data: Cricbuzz scorecards for
{len(STATE) - 1} state leagues (all editions we scraped) and SMAT 2025-26; IPL, earlier SMAT and T20I from the Cricsheet DB. Nothing dated 2026-10-15 or later is used.
Board = {len(b)} players with {min_balls}+ balls faced or bowled in the state leagues.

## How to read this
- **bat_score** = state-league runs minus what an average state-league batter scores off the same balls. **bowl_score** = runs saved against the average economy over the bowler's own overs. Both are in runs; state leagues are pooled (no per-league adjustment).
- **ipl_capped**: `yes` = linked Cricsheet player has an IPL match; `no` = linked and no IPL match; `unknown` = no usable link (never guessed). "Capped" means played an IPL match in our DB (squad-only or impact-sub-unused players are not seen).
- **ipl_link**: how the Cricbuzz player was tied to a Cricsheet player (see below).

## Top 15 uncapped batters (ipl_capped = no, by bat_score)
{top("no", "bat_score", bat)}

## Top 15 uncapped bowlers (ipl_capped = no, by bowl_score)
{top("no", "bowl_score", bowl)}

## Strong numbers but IPL status unknown (could be capped; check by hand), top 10 each
{top("unknown", "bat_score", bat, 10)}

{top("unknown", "bowl_score", bowl, 10)}

## Link quality
| Link | Meaning | All {len(lk)} Cricbuzz players | On the board ({len(b)}) |
|---|---|---|---|
| strong | same cricbuzz_id in state leagues and SMAT 2025 | {len(st & sm)} players appear in both | {int(b.smat_in_2025.sum())} |
| team_checked | Cricsheet name taken from the SMAT 2025 team-scoped link | {(lk.link == "team_checked").sum()} | {(b.ipl_link == "team_checked").sum()} |
| name_only | Cricsheet name from the scraper or a unique-name guess, passed the checks | {(lk.link == "name_only").sum()} | {(b.ipl_link == "name_only").sum()} |
| doubtful | name-only link that failed a check; Cricsheet rows withheld, ipl_capped = unknown | {(lk.link == "doubtful").sum()} | {(b.ipl_link == "doubtful").sum()} |
| none | no Cricsheet candidate | {(lk.link == "").sum()} | {(b.ipl_link == "").sum()} |

Checks on name-only links: (1) another Cricbuzz player claims the same Cricsheet name; (2) initials disagree; (3) Cricbuzz profile is new (id of 1,000,000 or more) but the Cricsheet player debuted before 2022; (4) the Cricsheet player's last match is 3+ years before the Cricbuzz player's first. Example: state-league "Sahaj Dhawan" was tied to "S Dhawan" (Shikhar Dhawan); check 3 flags it.
The checks are heuristics, so a flagged link can still be right and an unflagged name-only link can still be wrong; `(n)`-style caution applies to every name_only row.

## Caveats
- Name-only links are guesses by name; use `cricket scouting profile` and look at the Cricsheet rows before acting. Doubtful rows are hidden by default (`--doubtful` shows them).
- Cricbuzz scorecards are used, so the 55 matches without ball-by-ball do not matter here. Scorecards have no balls-faced for some tailenders (balls 0) and no super overs.
- A player with two Cricbuzz ids (spelling variants) appears twice on the board; ids are not merged by name.
- State-league strength differs a lot (for example Delhi / Tamil Nadu versus Pondicherry / Chhattisgarh). Scores are pooled and not league-adjusted. Samples are small (one season each for most leagues).
- Only IPL, SMAT (2016-2024 in the DB) and men's T20I come from Cricsheet; other leagues in the DB (PSL, BBL, ...) are not in the profile.
- Bengal Pro T20 and UP T20 2026 are not on Cricbuzz, so they are absent.
- **SMAT 2026 (the live test) is excluded**: its folder and `fresh3` data were never read.
"""
    from pathlib import Path
    Path(path).write_text(out, encoding="utf-8")


if __name__ == "__main__":
    write_report()
