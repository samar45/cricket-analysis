"""Real playing XIs from Cricsheet `_info.csv` files (`info,player,<team>,<name>` lines) -> data/external/ml/xi.parquet.

Columns: match_id, team, player, n_listed (players listed for that side: 11 normally, 12 in the IPL impact era, 13 with concussion subs).
Names match the ball-by-ball `batter`/`bowler` columns. Run: `python -m cricket_analytics.ingest.xi`.
"""

import csv
from pathlib import Path

import pandas as pd

from ..config import get_path

OUT = Path(__file__).resolve().parents[3] / "data" / "external" / "ml" / "xi.parquet"


def parse_info(path: Path) -> tuple[list[tuple[str, str]], str | None]:
    """([(team, player), ...], gender) from one info file."""
    out, gender = [], None
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.reader(f):
            if len(r) >= 4 and r[0] == "info" and r[1] == "player":
                out.append((r[2].strip(), r[3].strip()))
            elif len(r) >= 3 and r[0] == "info" and r[1] == "gender":
                gender = r[2].strip()
    return out, gender


def build(raw_root: Path | None = None, write: bool = True) -> pd.DataFrame:
    raw_root = Path(raw_root) if raw_root else get_path("raw") / "cricsheet"
    rows = []
    for p in sorted(raw_root.glob("*/*_info.csv")):
        pl, gender = parse_info(p)
        comp = p.parent.name
        comp = {"t20s": "t20i"}.get(comp, comp)
        if comp == "t20i" and gender == "female":
            comp = "t20i_women"
        mid = p.name.removesuffix("_info.csv")
        rows += [(mid, t, n, comp) for t, n in pl]
    df = pd.DataFrame(rows, columns=["match_id", "team", "player", "competition"]).drop_duplicates(["match_id", "team", "player"])
    df["n_listed"] = df.groupby(["match_id", "team"]).player.transform("size")
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        df.drop(columns="competition").to_parquet(OUT, index=False)
    return df


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per competition: number of sides with 11 / 12 / other players listed, and matches with no list at all is not visible here (see matches_without)."""
    s = df.drop_duplicates(["match_id", "team"])
    s = s.assign(size=s.n_listed.map(lambda n: n if n in (11, 12) else "other"))
    return s.pivot_table(index="competition", columns="size", values="match_id", aggfunc="count", fill_value=0)


if __name__ == "__main__":
    d = build()
    print(len(d), "rows,", d.match_id.nunique(), "matches")
    print(coverage(d).to_string())
