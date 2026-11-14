"""SMAT 2025-26 domestic scouting tables, from the Cricbuzz scorecards (not ball-by-ball, which covers only 36 matches).

Run: python -m cricket_analytics.scouting.smat2025   (writes the two CSVs next to the parquet files)
Players are grouped by cricbuzz_id. IPL / T20I / earlier-SMAT history comes from the read-only DB via the scraper's
`cricsheet_name` (exact match only; no match = status "unknown", never a guess).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3] / "data" / "external" / "cricbuzz" / "smat2025"
UNKNOWN = "unknown (name not matched)"


def _short(name: str) -> str:
    from cricket_analytics.ingest.cricbuzz_series import _short as f
    return f(name)


def _mode(s: pd.Series) -> str:
    s = s[s != ""]
    return s.mode().iloc[0] if len(s) else ""


def _plate_players(df: pd.DataFrame) -> set:
    m = pd.read_parquet(ROOT / "matches.parquet")[["match_id", "stage"]]
    p = df.merge(m, on="match_id")
    return set(p[p.stage == "Plate"].cricbuzz_id)


def _who(g):
    return pd.Series(dict(name=_mode(g["name"]), cricsheet_name=_mode(g["cricsheet_name"]), team=g["team"].mode().iloc[0]))


def batter_table(min_balls: int = 100) -> pd.DataFrame:
    b = pd.read_parquet(ROOT / "batting.parquet")
    g = b.groupby("cricbuzz_id")
    t = g.agg(inns=("match_id", "size"), runs=("runs", "sum"), balls=("balls", "sum"), outs=("is_out", "sum"),
              fours=("fours", "sum"), sixes=("sixes", "sum"), med_pos=("pos", "median")).join(g[["name", "cricsheet_name", "team"]].apply(_who)[["name", "cricsheet_name", "team"]])
    t["fifties"] = g.runs.apply(lambda r: int(((r >= 50) & (r < 100)).sum()))
    t["hundreds"] = g.runs.apply(lambda r: int((r >= 100).sum()))
    t = t[t.balls >= min_balls].copy()
    lg = b.runs.sum() / b.balls.sum() * 100
    t["avg"] = (t.runs / t.outs.replace(0, float("nan"))).round(1)
    t["sr"] = (t.runs / t.balls * 100).round(1)
    t["boundary_pct"] = ((t.fours + t.sixes) / t.balls * 100).round(1)
    t["band"] = pd.cut(t.med_pos, [0, 3, 5, 12], labels=["top 3", "middle", "finisher"]).astype(str)
    t["plate"] = t.index.isin(_plate_players(b))
    t["score"] = (t.runs - lg * t.balls / 100).round(1)  # runs above league-average SR over the player's own balls
    return t.reset_index().sort_values("score", ascending=False, ignore_index=True)


def bowler_table(min_overs: float = 12) -> pd.DataFrame:
    b = pd.read_parquet(ROOT / "bowling.parquet")
    g = b.groupby("cricbuzz_id")
    t = g.agg(runs=("runs", "sum"), balls=("balls", "sum"), wkts=("wickets", "sum"), inns=("match_id", "size")).join(
        g[["name", "cricsheet_name", "team"]].apply(_who)[["name", "cricsheet_name", "team"]])
    t = t[t.balls >= min_overs * 6].copy()
    lg = b.runs.sum() / b.balls.sum() * 6
    t["overs"] = (t.balls // 6 + t.balls % 6 / 10).round(1)
    t["econ"] = (t.runs / t.balls * 6).round(2)
    t["avg"] = (t.runs / t.wkts.replace(0, float("nan"))).round(1)
    t["sr"] = (t.balls / t.wkts.replace(0, float("nan"))).round(1)
    t["plate"] = t.index.isin(_plate_players(b))
    t["score"] = (lg * t.balls / 6 - t.runs).round(1)  # runs saved vs league-average economy over the player's own overs
    return t.reset_index().sort_values("score", ascending=False, ignore_index=True)


HIST_SQL = """
WITH p AS (SELECT match_id, batter AS n FROM deliveries WHERE batter IN (SELECT unnest(?))
           UNION SELECT match_id, bowler FROM deliveries WHERE bowler IN (SELECT unnest(?))
           UNION SELECT match_id, non_striker FROM deliveries WHERE non_striker IN (SELECT unnest(?)))
SELECT p.n AS cricsheet_name, m.competition AS comp, COUNT(*) AS matches, MAX(year(m.date)) AS last_year,
       string_agg(DISTINCT CAST(year(m.date) AS VARCHAR), ',') AS years
FROM p JOIN matches m USING (match_id)
WHERE m.gender = 'male' AND m.competition IN ('ipl', 't20i', 'smat') GROUP BY ALL
"""


def history(names: list[str]) -> pd.DataFrame:
    """One row per cricsheet_name: ipl_matches, ipl_last, t20i_matches, smat_seasons (earlier, from the DB)."""
    from cricket_analytics.db import query
    h = query(HIST_SQL, [names] * 3)
    out = pd.DataFrame(index=pd.Index(names, name="cricsheet_name"))
    for c, k in (("ipl", "ipl_matches"), ("t20i", "t20i_matches")):
        out[k] = h[h.comp == c].set_index("cricsheet_name").matches
    out["ipl_last"] = h[h.comp == "ipl"].set_index("cricsheet_name").last_year
    s = h[h.comp == "smat"].set_index("cricsheet_name")
    out["smat_earlier"] = s.years.map(lambda y: " ".join(sorted(y.split(","))))
    out[["ipl_matches", "t20i_matches"]] = out[["ipl_matches", "t20i_matches"]].fillna(0).astype(int)
    return out.reset_index()


def _pool() -> set:
    from cricket_analytics.db import query
    q = query("SELECT DISTINCT batter AS n FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender = 'male' "
              "UNION SELECT DISTINCT bowler FROM deliveries d JOIN matches m USING (match_id) WHERE m.gender = 'male'")
    return set(q.n)


def second_pass(t: pd.DataFrame) -> pd.DataFrame:
    """Names the scraper left blank: try all men's Cricsheet names, any team. Only a UNIQUE hit counts.
    Level 1 = same derived name ('Ishan Kishan' -> 'I Kishan') or full name; level 2 = same surname and Cricsheet initials
    start with ours ('Ajinkya Rahane' -> 'AM Rahane'). Ambiguous or no hit = stays blank (status unknown)."""
    pool = _pool()
    low = {}
    for n in pool:
        low.setdefault(n.lower(), []).append(n)
    t = t.copy()
    t["match"] = ["team" if c else "" for c in t.cricsheet_name]
    for i, r in t[t.cricsheet_name == ""].iterrows():
        parts = r["name"].split()
        hits = {x for k in (r["name"].lower(), _short(r["name"]).lower()) for x in low.get(k, [])}
        kind = "name"
        if not hits and len(parts) > 1:
            ini, sur = "".join(w[0] for w in parts[:-1]).upper(), parts[-1].lower()
            hits = {n for n in pool if n.lower().endswith(" " + sur) and n.split(" ")[0].isupper() and n.split(" ")[0].startswith(ini)}
            kind = "initials"
        if len(hits) == 1:
            t.loc[i, ["cricsheet_name", "match"]] = [hits.pop(), kind]
    return t


def enrich(t: pd.DataFrame) -> pd.DataFrame:
    t = second_pass(t)
    names = sorted(set(t.cricsheet_name) - {""})
    h = history(names)
    t = t.merge(h, on="cricsheet_name", how="left")
    un = t.cricsheet_name == ""
    t["matched"] = ~un
    t["ipl_status"] = [UNKNOWN if u else (f"{int(n)} IPL matches, last {int(y)}" if n else "no IPL record")
                       for u, n, y in zip(un, t.ipl_matches.fillna(0), t.ipl_last.fillna(0))]
    t["t20i"] = ["unknown" if u else ("capped (T20I)" if n else "uncapped") for u, n in zip(un, t.t20i_matches.fillna(0))]
    t["smat_earlier"] = t.smat_earlier.fillna("").where(~un, "unknown")
    return t


# SMAT -> IPL factors: src/cricket_analytics/models/data/league_translation.csv (smat rows; measured on players with >=200 balls in
# both; 57 batters / 59 bowlers). bat runs_per_ball 0.981 (95% 0.960-1.004), bowl runs_per_ball 1.205 (1.172-1.243).
BAT_F, BOWL_F = 0.981, 1.205


def _md(df: pd.DataFrame) -> str:
    df = df.fillna("-").astype(str)
    return chr(10).join(["| " + " | ".join(df.columns) + " |", "|" + "---|" * df.shape[1]] + ["| " + " | ".join(r) + " |" for r in df.values])


def _view(t: pd.DataFrame, kind: str) -> pd.DataFrame:
    t = t.copy()
    t["player"] = t.name + t.plate.map({True: " *", False: ""}) + t.match.map({"name": " (n)", "initials": " (n)"}).fillna("")
    t["ipl"] = t.ipl_status.str.replace(UNKNOWN, "unknown").str.replace(" IPL matches, last ", " m, last ")
    t["smat_hist"] = t.smat_earlier.replace("", "none")
    cols = ["player", "team", "t20i", "ipl", "smat_hist"]
    stat = (["inns", "runs", "balls", "avg", "sr", "boundary_pct", "fifties", "hundreds", "band", "ipl_sr_est", "score"] if kind == "bat"
            else ["inns", "overs", "wkts", "econ", "avg", "sr", "ipl_econ_est", "score"])
    return t[["player", "team"] + stat + cols[2:]]


def write_report(path: Path = ROOT.parents[3] / "docs" / "REPORT_smat2025_domestic.md"):
    b, w = (pd.read_csv(ROOT / f"scouting_{k}.csv", keep_default_na=False, na_values=[""]) for k in ("batters", "bowlers"))
    raw = pd.read_parquet(ROOT / "batting.parquet"), pd.read_parquet(ROOT / "bowling.parquet")
    lg_sr = raw[0].runs.sum() / raw[0].balls.sum() * 100
    lg_ec = raw[1].runs.sum() / raw[1].balls.sum() * 6
    nm = pd.read_parquet(ROOT / "matches.parquet")
    ub, uw = b[b.t20i == "uncapped"], w[w.t20i == "uncapped"]
    bb = ub[(ub.ipl_matches == 0) & (ub.score >= 25)]
    bw = uw[(uw.ipl_matches == 0) & (uw.score >= 15)]
    unk_b, unk_w = b[b.t20i == "unknown"].head(10), w[w.t20i == "unknown"].head(10)
    n = lambda t: int((t.match.isna()).sum())
    out = f"""# SMAT 2025-26 domestic scouting report (IPL auction lens)

Source: Cricbuzz scorecards, all {len(nm)} matches ({(nm.stage != 'Plate').sum()} Elite, {(nm.stage == 'Plate').sum()} Plate), 26 Nov - 18 Dec 2025.
Tables built by `src/cricket_analytics/scouting/smat2025.py`; CSVs: `data/external/cricbuzz/smat2025/scouting_batters.csv`, `scouting_bowlers.csv`.
Not used: ball-by-ball (only 36 of 141 matches have it), so no dot-ball % is shown. VJD matches are in the scorecards as played.

## How to read this
- **Score (batters)** = runs minus what an average SMAT batter would score off the same balls (league SR {lg_sr:.1f}). +50 means 50 runs more than average from those balls.
- **Score (bowlers)** = runs saved against the league economy ({lg_ec:.2f}) over the player's own overs. Wickets are not in the score; they are shown next to it.
- **Position band** (batters): median batting position, 1-3 top 3, 4-5 middle, 6+ finisher.
- **IPL status / T20I** come from our database (Cricsheet). T20I "uncapped" means no men's T20I match in the DB; ODI or Test caps are not covered. "unknown" = the name could not be matched, so nothing is guessed.
- `*` after a name = Plate group player (weaker opposition). `(n)` = matched to a Cricsheet player by name only (not by team history), so a wrong match is possible.
- **IPL estimate columns** (`ipl_sr_est`, `ipl_econ_est`): SMAT figure times a factor from `src/cricket_analytics/models/data/league_translation.csv` (measured in this project: players with 200+ balls in both SMAT and the IPL, 57 batters / 59 bowlers). Batter runs-per-ball factor 0.981 (95% range 0.960-1.004, so close to no change); bowler runs-per-ball factor 1.205 (1.172-1.243, IPL economy is about 20% worse). Those players already made the IPL, so the factors are a rough guide, and they are not applied to the ranking scores, which are raw.

## Counts
| | Batters (100+ balls) | Bowlers (12+ overs) |
|---|---|---|
| In table | {len(b)} | {len(w)} |
| Uncapped (matched, no T20I) | {len(ub)} | {len(uw)} |
| Capped (T20I in DB) | {(b.t20i == 'capped (T20I)').sum()} | {(w.t20i == 'capped (T20I)').sum()} |
| Name not matched (status unknown) | {n(b)} | {n(w)} |
| Plate players | {int(b.plate.sum())} | {int(w.plate.sum())} |

## Top 15 uncapped batters (by score)
{_md(_view(ub.head(15), 'bat'))}

## Top 15 uncapped bowlers (by score)
{_md(_view(uw.head(15), 'bowl'))}

## Breakouts: uncapped, no IPL record, strong numbers
Batters with score of 25 or more ({len(bb)}):

{_md(_view(bb, 'bat'))}

Bowlers with 15 or more runs saved ({len(bw)}):

{_md(_view(bw, 'bowl'))}

## Strong numbers but status unknown (name not matched, top 10 each)
These could be capped or have IPL history; check by hand before acting.

{_md(_view(unk_b, 'bat'))}

{_md(_view(unk_w, 'bowl'))}

## Full tables
### Batters, 100+ balls
{_md(_view(b, 'bat'))}

### Bowlers, 12+ overs
{_md(_view(w, 'bowl'))}

## Caveats
- **Small samples.** Each player has at most 10-11 innings. One big innings moves the score a lot; treat the lists as a shortlist to watch, not a verdict.
- **SMAT is not IPL.** Pitches, opposition depth and the lack of a proper pace mix make SMAT easier on batters and gentler on bowlers. The factors above are averages; for an individual they are only a guide.
- **Plate group** ({int(b.plate.sum())} batters, {int(w.plate.sum())} bowlers in the tables) plays much weaker teams (Meghalaya, Nagaland, Sikkim and similar). Their numbers are inflated relative to Elite; read them with a large discount.
- **Name matching.** The scraper matched {int((b.match == 'team').sum())} batters and {int((w.match == 'team').sum())} bowlers by team history. A second pass matched {int(b.match.isin(['name', 'initials']).sum())} batters and {int(w.match.isin(['name', 'initials']).sum())} bowlers by name only (marked `(n)`; common names are the risk). {n(b)} batters and {n(w)} bowlers stay unmatched and are shown as unknown, not as uncapped.
- **Uncapped means no T20I only.** Players capped in ODIs or Tests could still show as uncapped; a player appearing only as a fielder or non-playing squad member is not detected as a T20I player.
- **Earlier SMAT history** in the DB covers 2016 to 2024 only (competition `smat`); it is not complete for every season.
- No VJD or super-over adjustment was made; super overs are not in the scorecards.
"""
    path.write_text(out, encoding="utf-8")


def main():
    for name, t in (("batters", batter_table()), ("bowlers", bowler_table())):
        t = enrich(t)
        if name == "batters":
            t["ipl_sr_est"] = (t.sr * BAT_F).round(1)
        else:
            t["ipl_econ_est"] = (t.econ * BOWL_F).round(2)
        t.to_csv(ROOT / f"scouting_{name}.csv", index=False)
        print(name, len(t), "rows,", int((~t.matched).sum()), "name-unmatched")
    write_report()


if __name__ == "__main__":
    main()
