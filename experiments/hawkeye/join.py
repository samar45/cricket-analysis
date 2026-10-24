"""Join HawkeyeStats IPL CSV to Cricsheet IPL deliveries (read-only DB).
Usage: python -I join.py <hawkeye.csv> <cricket_analytics.duckdb> <out.csv.gz>
Match level: per-innings per-over total-runs fingerprint (names differ: Cricsheet uses initials, Hawk-Eye full names).
Ball level: n-th delivery of the innings, accepted only if runs_total equal AND bowler surname agrees."""
import sys, re, pandas as pd, duckdb
from collections import defaultdict
hk = pd.read_csv(sys.argv[1])
con = duckdb.connect(sys.argv[2], read_only=True)
cs = con.sql("""select d.match_id, d.innings, d.over_num, d.ball_seq, d.batter, d.bowler, d.runs_total, d.runs_batter,
  d.wicket_type, d.player_out, m.date, m.season, m.team1, m.team2
  from deliveries d join matches m using(match_id) where m.competition='ipl' and d.innings<=2
  order by d.match_id, d.innings, d.ball_seq""").df()

p = hk["delivery"].str.split(".", expand=True).astype(int)
hk["inn"], hk["ov"], hk["k"] = p[0], p[1], p[2]
hk = hk.sort_values(["matchId", "inn", "ov", "k"]).reset_index(drop=True)
print("hawkeye innings values", hk.inn.value_counts().to_dict())
hk = hk[hk.inn <= 2].copy()

def fp(df, ov, rc, inn):  # {innings: tuple(runs per over)}
    out = {}
    for i, g in df.groupby(inn):
        out[i] = tuple(g.groupby(ov)[rc].sum().tolist())
    return tuple(sorted(out.items()))
cs_fp = defaultdict(list)
for mid, g in cs.groupby("match_id"): cs_fp[fp(g, "over_num", "runs_total", "innings")].append(mid)
hk_fp = {mid: fp(g, "ov", "runs", "inn") for mid, g in hk.groupby("matchId")}

sur = lambda s: re.sub(r"[^a-z]", "", str(s).split()[-1].lower())
mmap, ambiguous = {}, 0
for hid, f in hk_fp.items():
    c = cs_fp.get(f, [])
    if len(c) == 1: mmap[hid] = c[0]
    elif len(c) > 1: ambiguous += 1  # ponytail: ambiguous fingerprints dropped, tie-break by names if it matters
print(f"hawkeye matches {len(hk_fp)}; exact-fingerprint matched {len(mmap)} ({100*len(mmap)/len(hk_fp):.1f}%); ambiguous {ambiguous}")
# duplicates of the same Cricsheet match claimed by 2 Hawkeye ids?
print("cricsheet matches claimed twice:", len(mmap) - len(set(mmap.values())))

rows = []
for hid, cid in mmap.items():
    h = hk[hk.matchId == hid]; c = cs[cs.match_id == cid]
    for i in (1, 2):
        hh, cc = h[h.inn == i].reset_index(drop=True), c[c.innings == i].reset_index(drop=True)
        if len(hh) != len(cc): continue
        j = pd.concat([cc.add_prefix("cs_"), hh.drop(columns=["inn"]).add_prefix("hk_")], axis=1)
        rows.append(j)
j = pd.concat(rows, ignore_index=True)
j["name_ok"] = j.cs_bowler.map(sur) == j.hk_bowler.map(sur)  # strict check; fails on spelling variants (CV Varun vs Varun Chakaravarthy)
j["ok"] = j.cs_runs_total == j.hk_runs  # position alignment is already pinned by the exact per-over fingerprint
print("aligned balls", len(j), "| runs agree", j.ok.sum(), f"{100*j.ok.mean():.2f}%", "| runs AND bowler surname agree", (j.ok & j.name_ok).sum(), f"{100*(j.ok&j.name_ok).mean():.2f}%")
j[j.ok].to_csv(sys.argv[3], index=False)
# match-level and coverage report
print("hawkeye matches matched:", len(mmap), "/", len(hk_fp))
tot = cs.groupby("season").agg(matches=("match_id", "nunique"), balls=("ball_seq", "size"), first=("date", "min"))
cov = j[j.ok].groupby("cs_season").agg(mt=("cs_match_id", "nunique"), tracked_pitch=("hk_pitchX", lambda s: s.notna().sum()), tracked_field=("hk_fieldX", lambda s: s.notna().sum()), joined=("ok", "size"))
t = tot.join(cov).fillna(0).sort_values("first")
t["pitch_cov_%"] = (100 * t.tracked_pitch / t.balls).round(1); t["field_cov_%"] = (100 * t.tracked_field / t.balls).round(1)
print(t.drop(columns="first").to_string())
print("TOTAL cricsheet IPL balls (inn1-2)", len(cs), "joined", int(j.ok.sum()), "pitch tracked", int(j[j.ok].hk_pitchX.notna().sum()))
unm = [h for h in hk_fp if h not in mmap]
print("unmatched hawkeye ids (first 15)", unm[:15], "n", len(unm))
# diagnostics on the ~1% balls that were aligned by position but disagree
bad = j[~j.ok]
print("bad balls by match (top 8):", bad.groupby("cs_match_id").size().sort_values(ascending=False).head(8).to_dict(), "matches with any bad:", bad.cs_match_id.nunique())
print("bad: runs differ", (bad.cs_runs_total != bad.hk_runs).sum(), "bowler differs only", ((bad.cs_runs_total == bad.hk_runs) & ~bad.ok).sum())
print(hk[hk.matchId == 2439].groupby("inn").size().to_dict(), "| cricsheet 2014 ipl matches not matched:",
      sorted(set(cs[cs.season == "2014"].match_id) - set(mmap.values())))
bad = j[~j.name_ok]
print(bad.groupby(["cs_bowler", "hk_bowler"]).size().sort_values(ascending=False).head(12).to_string())
