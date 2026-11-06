"""Build reference/player_dob.csv: Cricsheet people.csv (key_cricinfo) + Wikidata dump (P2697 -> P569).
Inputs in data/external/ (see docs/VALUE_age.md). Run: .venv/Scripts/python scripts/build_player_dob.py"""
import duckdb, pandas as pd
W = "data/external/wikidata/sparql_2026-11-07/dob.csv"
SRC = "https://www.wikidata.org/wiki/Special:EntityData/"
ppl = pd.read_csv("data/external/cricsheet/people.csv", dtype=str)
wd = pd.read_csv(W, dtype=str)
wd["qid"] = wd["item"].str.rsplit("/", n=1).str[-1]
wd["dob"] = wd["dob"].str[:10]
wd = wd[wd.dob.str.match(r"^\d{4}-\d\d-\d\d$")]
# ambiguous cricinfo ids (several different DOBs) are dropped
n = wd.groupby("id").dob.nunique()
wd = wd[wd.id.isin(n[n == 1].index)].drop_duplicates("id")
ci = pd.concat([ppl[["identifier", "key_cricinfo"]].rename(columns={"key_cricinfo": "id"}),
                ppl[["identifier", "key_cricinfo_2"]].rename(columns={"key_cricinfo_2": "id"}),
                ppl[["identifier", "key_cricinfo_3"]].rename(columns={"key_cricinfo_3": "id"})]).dropna()
c = duckdb.connect("data/cricket_analytics.duckdb", read_only=True)
pl = c.sql("select player_id as cricsheet_identifier, name as cricsheet_name from players").df()
out = pl.merge(ppl[["identifier", "key_cricinfo"]], left_on="cricsheet_identifier", right_on="identifier", how="left")
m = ci.merge(wd, on="id").drop_duplicates("identifier")
out = out.merge(m[["identifier", "qid", "dob"]], on="identifier", how="left").rename(columns={"qid": "wikidata_qid"})
out["source_url"] = SRC.rsplit("Special", 1)[0] + out.wikidata_qid.fillna("")
out.loc[out.wikidata_qid.isna(), "source_url"] = ""
out["source_date"] = "2026-11-07"
out[["cricsheet_name", "cricsheet_identifier", "key_cricinfo", "wikidata_qid", "dob", "source_url", "source_date"]] \
    .sort_values("cricsheet_name").to_csv("src/cricket_analytics/reference/player_dob.csv", index=False)
print(len(out), out.dob.notna().sum())
