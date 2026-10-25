"""Bowling for video. Default -> donut of HOW the wickets fell (caught / bowled / lbw / other; a second query on
the same filters, because the module result has no dismissal kinds). By phase -> economy bars. By season -> wickets
bars. focus='leaders' (or a column name) with many bowlers -> top-5 leaderboard."""

from pathlib import Path

from ...db import query
from ...sql.filters import Filters
from ...sql.fragments import BOWLER_WICKET
from . import (
    AMBER,
    INK,
    RED,
    SKY,
    columns,
    donut,
    hbars,
    message_card,
    num,
    scope_text,
    season_label,
    source_note,
)

PHASES = ["powerplay", "middle", "death"]
KINDS = [("Caught", AMBER), ("Bowled", RED), ("LBW", INK), ("Other", SKY)]


def wicket_kinds(result) -> dict[str, int]:
    """Wickets by kind for the filters the result ran with: caught (incl. caught and bowled), bowled, lbw, other."""
    p = result.meta["params"]
    f = Filters(**{k: v for k, v in p.items() if k in Filters.__dataclass_fields__})
    where, params = f.where("bowl")
    sql = (
        f"SELECT d.wicket_type AS kind, COUNT(*) AS n FROM deliveries d JOIN matches m ON d.match_id = m.match_id "
        f"WHERE {where} AND {BOWLER_WICKET} GROUP BY 1"
    )
    got = query(sql, params, db_path=Path(result.meta["db_path"]))
    out = {"Caught": 0, "Bowled": 0, "LBW": 0, "Other": 0}
    names = {"caught": "Caught", "caught and bowled": "Caught", "bowled": "Bowled", "lbw": "LBW"}
    for kind, n in zip(got["kind"], got["n"]):
        out[names.get(kind, "Other")] += int(n)
    return out


def video_figure(result, aspect="9:16", focus=None):
    df, note, sub = result.data, source_note(result), scope_text(result)
    if df.empty:
        return message_card(aspect, "Bowling", "No bowling data for these filters", note)
    if "season" in df.columns:
        who = df.groupby("bowler")["wickets"].sum().idxmax()
        d = df[df["bowler"] == who].tail(10)
        return columns(
            [season_label(s) for s in d["season"]],
            d["wickets"],
            f"{who}: wickets per season",
            aspect,
            f"last {len(d)} seasons | {sub}",
            note,
        )
    if "phase" in df.columns:
        g = df.groupby("phase")[["runs_conceded", "balls"]].sum().reindex(PHASES).dropna()
        who = df["bowler"].iloc[0] if df["bowler"].nunique() == 1 else "all bowlers"
        return columns(
            list(g.index),
            g["runs_conceded"] * 6 / g["balls"],
            f"{who}: economy by phase",
            aspect,
            f"runs per over (lower is better) | {sub}",
            note,
            highlight="min",
            fmt=lambda v: num(v, 1),
        )
    if len(df) > 1 and (focus == "leaders" or focus in df.columns):
        m = focus if focus in df.columns else "wickets"
        d = df.sort_values(m, ascending=(m == "economy")).head(5)
        return hbars(
            d["bowler"],
            d[m],
            f"Top 5 bowlers: {m.replace('_', ' ')}",
            aspect,
            sub,
            note,
            fmt=lambda v: num(v, 0 if m == "wickets" else 1),
        )
    kinds = wicket_kinds(result)
    if sum(kinds.values()) == 0:
        return message_card(aspect, "How wickets fell", "No wickets for these filters", note)
    items = [(k, kinds[k], c) for (k, c) in KINDS if kinds[k] > 0]
    who = df["bowler"].iloc[0] if len(df) == 1 else None
    return donut(
        [i[0] for i in items],
        [i[1] for i in items],
        f"{who}: how the wickets fell" if who else "How wickets fall",
        aspect,
        sub,
        note,
        center=(num(sum(kinds.values())), "wickets"),
        colors=[i[2] for i in items],
    )
