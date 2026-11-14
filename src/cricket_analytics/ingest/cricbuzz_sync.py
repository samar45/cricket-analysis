"""`cricket cricbuzz sync`: discover ongoing men's T20 series on Cricbuzz, save finished matches, verify against Cricsheet.

Data only. Matches dated >= 2026-10-15 (fresh set #3, SMAT 2026) are saved like any other; nothing here scores a model.
The DB is only read (read-only), Cricsheet stays the only source for the main DB. Raw layout:
  data/external/cricbuzz/<comp>/<series_id>/<match_id>/{scorecard.html.gz, comm1.json, comm2.json, meta.json}
  data/external/cricbuzz/<comp>/<series_id>/{matches,innings,batting,bowling,deliveries}.parquet
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import time
from pathlib import Path

import pandas as pd

from . import commentary as cm
from . import cricbuzz_series as cb

BASE = Path("data/external/cricbuzz")
LOCK = BASE / ".sync.lock"
LOG = BASE / "sync.log"
DB = "data/cricket_analytics.duckdb"
TEAM_MAP = Path(__file__).resolve().parent.parent / "reference" / "cricbuzz_team_map.csv"
DOC = Path("docs/VERIFY_cricbuzz_cricsheet.md")

# explicit name patterns -> our competition key (men's only; women's / youth are dropped first)
PATTERNS = [
    (r"indian premier league", "ipl"), (r"big bash league", "bbl"), (r"pakistan super league", "psl"),
    (r"caribbean premier league", "cpl"), (r"\bsa20\b", "sa20"), (r"vitality blast|t20 blast", "blast"),
    (r"the hundred", "hundred"), (r"international league t20", "ilt20"), (r"major league cricket", "mlc"),
    (r"bangladesh premier league", "bpl"), (r"lanka premier league", "lpl"), (r"syed mushtaq ali", "smat"),
]
DROP = re.compile(r"\bwomen|\bwbbl\b|\bwpl\b|\bu-?(19|23)\b|under-?(19|23)|\bwomen'?s", re.I)


class Locked(RuntimeError):
    pass


# ------------------------------------------------------------------ discover
def parse_series_list(page: str) -> list[dict]:
    """Schedule page -> [{id, slug, name, section, descs}] (section = INTERNATIONAL/LEAGUE/DOMESTIC/WOMEN; descs = match titles)."""
    toks = re.finditer(r'text-\[#00deaa\] text-sm font-bold">([^<]*)<|href="/cricket-series/(\d+)/([^"/]+)" class="block[^"]*">([^<]*)<'
                       r'|href="/live-cricket-scores/\d+/[^"]*" class="block mb-3" title="([^"]*)"', page)
    out, section = {}, ""
    cur = None
    for m in toks:
        if m[1]:
            section = m[1].strip().upper()
        elif m[2]:
            cur = out.setdefault(m[2], dict(id=int(m[2]), slug=m[3], name=html.unescape(m[4]), section=section, descs=[]))
        elif m[5] and cur:
            cur["descs"].append(html.unescape(m[5]))
    return list(out.values())


def classify(s: dict) -> str | None:
    """Competition key from the explicit name table, or None (women's, youth, not in the table)."""
    if s["section"] == "WOMEN" or DROP.search(s["name"]):
        return None
    return next((key for pat, key in PATTERNS if re.search(pat, s["name"], re.I)), None)


def discover(page: str) -> tuple[list[dict], list[dict], list[str]]:
    """-> (kept = name-table series with 'comp', candidates = other INTERNATIONAL series whose match list must be
    checked for men's T20Is, names of skipped non-women series that look like T20 but are unmapped)."""
    kept, cands, unmapped = [], [], []
    for s in parse_series_list(page):
        k = classify(s)
        if k:
            kept.append(dict(s, comp=k))
        elif s["section"] == "WOMEN" or DROP.search(s["name"]):
            continue
        elif s["section"] == "INTERNATIONAL":
            cands.append(s)
        elif re.search(r"t20|t10|league|smash|cup|trophy|challenge", s["name"], re.I)                 and not re.search(r"test|ranji|shield|four.day|three.day|one.day|ford trophy|vijay hazare|plunket|first.class", s["name"], re.I):
            unmapped.append(s["name"])
    return kept, cands, unmapped


def is_t20i(m: dict) -> bool:
    return m.get("matchFormat") == "T20" and bool(re.search(r"T20I", m.get("matchDesc", "")))


def series_matches(page: str, sid: int) -> list[dict]:
    """Series /matches page -> matchInfo dicts of that series (state, matchDesc, matchFormat, startDate, team names)."""
    t = page.replace('\\"', '"')
    dec, out = json.JSONDecoder(), {}
    for m in re.finditer(r'"matchInfo":', t):
        try:
            d, _ = dec.raw_decode(t, m.end())
        except ValueError:
            continue
        if isinstance(d, dict) and int(d.get("seriesId", -1)) == int(sid):
            out[str(d["matchId"])] = d
    return sorted(out.values(), key=lambda d: (int(d["startDate"]), d["matchId"]))


def wanted(matches: list[dict], comp: str) -> list[dict]:
    """Finished T20 matches only (T20I series also hold Tests/ODIs; T20I rows must say T20I)."""
    return [m for m in matches if m.get("state") == "Complete" and m.get("matchFormat") == "T20"
            and (comp != "t20i" or re.search(r"\bT20I\b", m.get("matchDesc", "")))]


# ------------------------------------------------------------------ scrape
def match_dir(comp: str, sid, mid, base: Path = BASE) -> Path:
    return base / comp / str(sid) / str(mid)


def to_fetch(matches: list[dict], comp: str, base: Path = BASE) -> list[dict]:
    """Finished matches whose scorecard is not saved yet."""
    return [m for m in wanted(matches, comp) if not (match_dir(comp, m["seriesId"], m["matchId"], base) / "scorecard.html.gz").exists()]


def scrape_match(m: dict, comp: str, base: Path = BASE, fetch=cb.fetch_match) -> None:
    d = match_dir(comp, m["seriesId"], m["matchId"], base)
    fetch(str(m["matchId"]), root=d.parent)
    (d / "meta.json").write_text(json.dumps(m), encoding="utf-8")


def parse_series(comp: str, sid, base: Path = BASE) -> int:
    """Raw -> parquet for one series (all saved matches, rebuilt each time; no DB needed, names mapped later in verify)."""
    root = base / comp / str(sid)
    out = {k: [] for k in ("match", "batting", "bowling", "innings", "deliveries")}
    for d in sorted(root.iterdir()):
        if not (d / "scorecard.html.gz").exists():
            continue
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
        try:
            r = cb.parse_match(d.name, dict(desc=meta.get("matchDesc", "")), {}, root)
        except Exception as e:  # report, don't chase
            log(f"parse failed {comp}/{sid}/{d.name}: {e!r}")
            continue
        for k in out:
            out[k] += [r[k]] if k == "match" else r[k]
    for k, name in dict(match="matches", batting="batting", bowling="bowling", innings="innings", deliveries="deliveries").items():
        pd.DataFrame(out[k]).to_parquet(root / f"{name}.parquet", index=False)
    return len(out["match"])


# ------------------------------------------------------------------ lock + log
def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}\n")


def acquire(lock: Path = LOCK, stale_s: int = 3 * 3600) -> None:
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and time.time() - lock.stat().st_mtime > stale_s:
        lock.unlink()  # a crashed run left it; sync is stopped after 2 h by the scheduler
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        raise Locked(f"another sync is running ({lock})") from None


def release(lock: Path = LOCK) -> None:
    lock.unlink(missing_ok=True)


# ------------------------------------------------------------------ verify
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def team_map() -> dict[tuple[str, str], str]:
    """(comp, normalised Cricbuzz name) -> Cricsheet name from the reference csv; comp '' = any."""
    m = {}
    if TEAM_MAP.exists():
        for r in pd.read_csv(TEAM_MAP, dtype=str).fillna("").itertuples():
            m[(r.competition, _norm(r.cricbuzz_name))] = r.cricsheet_name
    return m


def to_cs_team(name: str, comp: str, tmap: dict, cs_names: set[str]) -> str | None:
    """Map by the reference table, else exact (normalised) Cricsheet name; None = unmapped (logged, never guessed)."""
    n = _norm(name)
    for k in ((comp, n), ("", n)):
        if k in tmap:
            return tmap[k]
    hit = [c for c in cs_names if _norm(c) == n]
    return hit[0] if len(hit) == 1 else None


def _cs_innings(con, mid: str) -> dict[int, dict]:
    rows = con.execute(
        "select innings, any_value(batting_team), sum(runs_total), "
        "sum(case when player_out is not null and wicket_type not in ('retired hurt','retired not out') then 1 else 0 end), "
        "sum(case when coalesce(wides,0)=0 and coalesce(noballs,0)=0 then 1 else 0 end) "
        "from deliveries where match_id=? and innings<=2 group by 1 order by 1", [mid]).fetchall()
    return {r[0]: dict(team=r[1], runs=int(r[2]), wickets=int(r[3]), balls=int(r[4])) for r in rows}


def cs_player(name: str, team: str, tp: dict) -> str:
    """Cricsheet name: the exact rule from the SMAT scraper, else same surname + the first name's initial among the
    team's initials (Cricsheet 'PHKD Mendis' for 'Kamindu Mendis'), only when that is unique."""
    n = cb.cs_name(name, team, tp)
    if n or " " not in name.strip():
        return n
    first, last = name.split()[0], name.split()[-1]
    hits = {c for c in tp.get(team.lower(), set()) if c.lower().endswith(" " + last.lower()) and first[0].upper() in c.split()[0].upper()
            and c.split()[0].isupper()}
    return hits.pop() if len(hits) == 1 else ""


def _balls(overs) -> int:
    o = float(overs)
    return int(o) * 6 + round((o - int(o)) * 10)


def verify_one(m: dict, innings: pd.DataFrame, batting: pd.DataFrame, con, comp: str, tmap: dict, tp: dict, cs_names: set[str]) -> dict:
    """One Cricbuzz match (dict from matches.parquet) -> status row. Status: equal / different / waiting / unmapped_team / no_result."""
    row = dict(cb_match_id=m["match_id"], comp=comp, date=m["date"], team1=m["team1"], team2=m["team2"], status="", cricsheet_match_id="", diffs="",
               batters_compared=0, batters_unmapped=0)
    t1, t2 = (to_cs_team(m[k], comp, tmap, cs_names) for k in ("team1", "team2"))
    if not t1 or not t2:
        row["status"] = "unmapped_team"
        row["diffs"] = "unmapped: " + ", ".join(m[k] for k, t in (("team1", t1), ("team2", t2)) if not t)
        return row
    d = pd.Timestamp(m["date"]).date()
    cand = con.execute("select match_id, team1, team2, winner, result from matches where competition=? and date between ? and ?",
                       [comp, d - dt.timedelta(days=1), d + dt.timedelta(days=1)]).fetchall()
    cand = [c for c in cand if {c[1], c[2]} == {t1, t2}]
    if not cand:
        row["status"] = "waiting"
        return row
    mid, _, _, cs_winner, _ = cand[0]
    row["cricsheet_match_id"] = mid
    csi, diffs = _cs_innings(con, mid), []
    for r in innings.itertuples():
        c = csi.get(int(r.innings))
        if not c:
            diffs.append(f"inn{r.innings}: missing at Cricsheet")
            continue
        for f, a, b in (("runs", int(r.runs), c["runs"]), ("wickets", int(r.wickets), c["wickets"]), ("balls", _balls(r.overs), c["balls"])):
            if a != b:
                diffs.append(f"inn{r.innings} {f}: cricbuzz {a} vs cricsheet {b}")
    if m.get("winner"):
        w = to_cs_team(m["winner"], comp, tmap, cs_names)
        if cs_winner and w != cs_winner:
            diffs.append(f"winner: cricbuzz {m['winner']} vs cricsheet {cs_winner}")
    cs_bat = con.execute("select innings, batter, sum(runs_batter) from deliveries where match_id=? and innings<=2 group by 1,2", [mid]).fetchall()
    cs_runs = {(i, b): int(r) for i, b, r in cs_bat}
    for r in batting.itertuples():
        team = to_cs_team(r.team, comp, tmap, cs_names)
        n = cs_player(r.name, team, tp) if team else ""
        if not n or (int(r.innings), n) not in cs_runs:
            row["batters_unmapped"] += 1
            continue
        row["batters_compared"] += 1
        if cs_runs[(int(r.innings), n)] != int(r.runs):
            diffs.append(f"{r.name} inn{r.innings} runs: cricbuzz {r.runs} vs cricsheet {cs_runs[(int(r.innings), n)]}")
    row["status"] = "different" if diffs else "equal"
    row["diffs"] = "; ".join(diffs)
    return row


def load_saved(base: Path = BASE) -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("matches", "innings", "batting"):
        fs = sorted(base.glob(f"*/*/{name}.parquet"))
        parts = []
        for f in fs:
            df = pd.read_parquet(f)
            if len(df):
                parts.append(df.assign(comp=f.parent.parent.name))
        out[name] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return out


def verify(base: Path = BASE, db: str = DB, doc: Path | None = DOC) -> pd.DataFrame:
    """Compare every saved Cricbuzz match with Cricsheet (DB opened read-only). Writes verify.parquet and the markdown doc."""
    import duckdb

    saved = load_saved(base)
    if saved["matches"].empty:
        return pd.DataFrame()
    con = duckdb.connect(db, read_only=True)
    try:
        tmap = team_map()
        rows, tps = [], {}
        for comp, mm in saved["matches"].groupby("comp"):
            cs_names = {r[0] for r in con.execute("select team1 from matches where competition=? union select team2 from matches where competition=?", [comp, comp]).fetchall()}
            if comp not in tps:
                tps[comp] = _team_players(con, comp)
            for m in mm.to_dict("records"):
                if not m.get("complete") and m.get("result_type") is None:
                    continue
                ii = saved["innings"][saved["innings"].match_id == m["match_id"]]
                bb = saved["batting"][saved["batting"].match_id == m["match_id"]]
                rows.append(verify_one(m, ii, bb, con, comp, tmap, tps[comp], cs_names))
        res = pd.DataFrame(rows)
        cs_only = _cs_only(con, res, saved["matches"]) if len(res) else []
    finally:
        con.close()
    res = res.sort_values("date", ascending=False).reset_index(drop=True)
    res.to_parquet(base / "verify.parquet", index=False)
    if doc:
        write_doc(res, cs_only, doc)
    return res


def _team_players(con, comp: str) -> dict[str, set[str]]:
    rows = con.execute("select d.batting_team, d.batter from deliveries d join matches m using(match_id) where m.competition=? "
                       "union select d.bowling_team, d.bowler from deliveries d join matches m using(match_id) where m.competition=?", [comp, comp]).fetchall()
    out: dict[str, set[str]] = {}
    for t, n in rows:
        out.setdefault(t.lower(), set()).add(n)
    return out


def _cs_only(con, res: pd.DataFrame, saved_matches: pd.DataFrame) -> list[tuple]:
    """Cricsheet matches inside a Cricbuzz series' date span, with a team from that series, that no Cricbuzz match paired to."""
    paired = set(res.cricsheet_match_id) - {""}
    out = []
    for (comp, sid), g in saved_matches.assign(sid=saved_matches.get("series")).groupby(["comp", "series"]):
        g = g.merge(res[["cb_match_id", "status"]], left_on="match_id", right_on="cb_match_id")
        teams = {t for r in g.itertuples() for t in (r.team1, r.team2)}
        d0, d1 = pd.Timestamp(g.date.min()).date(), pd.Timestamp(g.date.max()).date()
        tn = {_norm(t) for t in teams}
        for mid, d, a, b in con.execute("select match_id, date, team1, team2 from matches where competition=? and date between ? and ?",
                                        [comp, d0 - dt.timedelta(days=1), d1 + dt.timedelta(days=1)]).fetchall():
            if mid not in paired and (_norm(a) in tn or _norm(b) in tn):
                out.append((comp, str(d), a, b, mid))
    return out


def write_doc(res: pd.DataFrame, cs_only: list[tuple], doc: Path) -> None:
    c = res.status.value_counts().to_dict()
    L = ["# Cricbuzz vs Cricsheet verification", "",
         f"Written by `cricket cricbuzz sync` on {dt.datetime.now():%Y-%m-%d %H:%M}; overwritten each run. Data check only, no model output.", "",
         "| Status | Matches |", "|---|---|"]
    for k, label in (("equal", "matched and equal"), ("different", "matched and different"), ("waiting", "waiting for Cricsheet"), ("unmapped_team", "team name not mapped")):
        L.append(f"| {label} | {c.get(k, 0)} |")
    L += [f"| Cricsheet only (no Cricbuzz copy) | {len(cs_only)} |", ""]
    diff = res[res.status == "different"]
    if len(diff):
        L += ["## Different (newest first)", ""]
        for r in diff.itertuples():
            L.append(f"- {r.date} {r.comp} {r.team1} v {r.team2} (cricbuzz {r.cb_match_id}, cricsheet {r.cricsheet_match_id}): {r.diffs}")
        L.append("")
    um = res[res.status == "unmapped_team"]
    if len(um):
        L += ["## Team names not mapped (add to reference/cricbuzz_team_map.csv)", ""]
        L += [f"- {r.comp}: {r.diffs}" for r in um.itertuples()] + [""]
    L += ["## All matches (newest first)", "", "| Date | Comp | Match | Status | Cricsheet id | Batters compared |", "|---|---|---|---|---|---|"]
    for r in res.itertuples():
        L.append(f"| {r.date} | {r.comp} | {r.team1} v {r.team2} | {r.status} | {r.cricsheet_match_id} | {r.batters_compared} |")
    if cs_only:
        L += ["", "## Cricsheet only", ""] + [f"- {d} {comp} {a} v {b} ({mid})" for comp, d, a, b, mid in sorted(cs_only, reverse=True)]
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ the command
def sync(dry_run: bool = False, do_verify: bool = True, max_matches: int | None = None, echo=print) -> int:
    """discover -> scrape -> verify. Returns exit code: 0 ok, 2 blocked (partial work kept)."""
    acquire()
    blocked, saved, kept, unmapped = False, 0, [], []
    try:
        try:
            kept, cands, unmapped = discover(cb.get("/cricket-schedule/series/all"))
            todo = []
            for s in kept + cands:
                ms = series_matches(cb.get(f"/cricket-series/{s['id']}/{s['slug']}/matches"), s["id"])
                if "comp" not in s:  # international: kept only if it holds men's T20Is
                    if not any(is_t20i(m) for m in ms):
                        continue
                    s = dict(s, comp="t20i")
                    kept.append(s)
                todo += [(s, m) for m in to_fetch(ms, s["comp"])]
            for s in unmapped:
                log(f"unmapped T20-looking series, skipped: {s}")
            if max_matches is not None:
                todo = todo[:max_matches]
            if not dry_run:
                touched = set()
                for s, m in todo:
                    scrape_match(m, s["comp"])
                    saved += 1
                    touched.add((s["comp"], s["id"]))
                    if saved % 10 == 0:
                        log(f"MILESTONE: {saved}/{len(todo)} matches saved")
                for comp, sid in touched:
                    parse_series(comp, sid)
            else:
                saved = len(todo)
        except cm.Blocked as e:
            blocked = True
            log(f"BLOCKED, stopped (partial work kept): {e}")
            if not dry_run:
                for comp, sid in {(s["comp"], s["id"]) for s in kept if (BASE / s["comp"] / str(s["id"])).exists()}:
                    parse_series(comp, sid)
        counts = {}
        if do_verify and not dry_run:
            res = verify()
            counts = res.status.value_counts().to_dict() if len(res) else {}
    finally:
        release()
    line = (f"series kept {len(kept)} ({', '.join(sorted({s['comp'] for s in kept}))}); new matches {'would save' if dry_run else 'saved'} {saved}; "
            f"verified equal {counts.get('equal', 0)}, mismatched {counts.get('different', 0)}, waiting {counts.get('waiting', 0)}; "
            f"unmapped T20 series {len(unmapped)}{'; BLOCKED' if blocked else ''}")
    echo(line)
    log(line)
    return 2 if blocked else 0
