"""Public API: the one place the CLI, the dashboard, the video pipeline and an LLM agent call.

    from cricket_analytics.api import run, resolve_player
    r = run("batting", player="V Kohli", competition="ipl", group_by="season")
    r.data (DataFrame), r.meta (dict), r.to_records(), r.to_json()
"""

import datetime as dt
import functools
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import competitions, registry
from .db import current_db_path, query, use_db
from .sql.filters import Filters
from .sql.fragments import PHASES

SOURCE = "Cricsheet (ODC-BY)"
_FILTER_FIELDS = set(Filters.__dataclass_fields__)
_TRUE, _FALSE = {"true", "1", "yes", "y", "on"}, {"false", "0", "no", "n", "off"}


@dataclass
class Result:
    data: pd.DataFrame
    meta: dict

    def to_records(self) -> list[dict]:
        """Rows as plain dicts (NaN -> None, dates -> ISO strings)."""
        return json.loads(self.data.to_json(orient="records", date_format="iso"))

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps({"meta": self.meta, "data": self.to_records()}, indent=indent)


def _coerce(spec: registry.ParamSpec, value):
    k = spec.kind
    if k == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{spec.name} must be an integer, got {value!r}") from None
    if k == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{spec.name} must be a number, got {value!r}") from None
    if k == "bool":
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE
        if isinstance(value, (bool, int)) and value in (0, 1):
            return bool(value)
        raise ValueError(f"{spec.name} must be true or false, got {value!r}")
    if k == "competition":
        competitions.get(value)
    elif k == "phase" and value not in PHASES:
        raise ValueError(f"phase must be one of {', '.join(PHASES)}, got {value!r}")
    elif k == "choice" and value not in spec.choices:
        raise ValueError(f"{spec.name} must be one of {', '.join(map(str, spec.choices))}, got {value!r}")
    elif k == "season":
        return value if isinstance(value, int) else str(value)
    return value


def run(module_id: str, *, db_path: Path | None = None, **params) -> Result:
    """Run one analysis module. Unknown params, bad choices or missing required params raise ValueError."""
    mod = registry.get(module_id)
    params = {k: v for k, v in params.items() if v is not None}
    unknown = set(params) - {p.name for p in mod.params}
    if unknown:
        raise ValueError(f"Module {module_id!r} has no param(s) {sorted(unknown)}. "
                         f"Allowed: {[p.name for p in mod.params]}")
    used = {}
    for p in mod.params:
        if p.name in params:
            used[p.name] = _coerce(p, params[p.name])
        elif p.required:
            raise ValueError(f"Module {module_id!r} needs param {p.name!r}")
        elif p.default is not None:
            used[p.name] = p.default
    f = Filters(**{k: v for k, v in used.items() if k in _FILTER_FIELDS})
    extra = {k: v for k, v in used.items() if k not in _FILTER_FIELDS}
    with use_db(db_path):
        df = mod.fn(f, **extra)
        where, p = f.where("match")
        through = query(f"SELECT max(m.date) AS d FROM matches m WHERE {where}", p)["d"].iloc[0]
        path = current_db_path()
    meta = {
        "module": mod.id,
        "title": mod.title,
        "params": used,
        "data_through": None if pd.isna(through) else str(pd.Timestamp(through).date()),
        "db_path": str(path),
        "db_modified": dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "row_count": len(df),
        "caveats": mod.caveats,
        "source": SOURCE,
    }
    return Result(df, meta)


def list_modules() -> list[dict]:
    return [{"id": m.id, "title": m.title, "category": m.category, "description": m.description,
             "params": [p.name for p in m.params]} for m in registry.all_modules()]


def schema() -> list[dict]:
    """Tool definitions for every module: {name, description, parameters: JSON Schema}."""
    return [{"name": m.id, "description": m.description, "parameters": registry.json_schema(m.id)}
            for m in registry.all_modules()]


def _rank(names_sql: str, params: list, name: str, limit: int) -> list[dict]:
    """Rank candidate names: exact, then case-insensitive, then a heuristic similarity score.

    Score = 0.9 * jaro_winkler_similarity on lower-cased names, +0.09 if the query is a substring
    (so 'kohli' finds 'V Kohli' ahead of unrelated names). The weights are a heuristic, not a standard.
    """
    sql = f"""
    WITH c AS ({names_sql})
    SELECT name,
           CASE WHEN name = ? THEN 1.0
                WHEN lower(name) = lower(?) THEN 0.99
                ELSE 0.9 * jaro_winkler_similarity(lower(name), lower(?))
                     + CASE WHEN lower(name) LIKE '%' || lower(?) || '%' THEN 0.09 ELSE 0 END
           END AS score
    FROM c ORDER BY score DESC, name LIMIT ?
    """
    df = query(sql, params + [name, name, name, name, limit])
    return [{"name": r.name, "score": round(float(r.score), 3)} for r in df.itertuples()]


def resolve_player(name: str, competition: str | None = None, limit: int = 5) -> list[dict]:
    """Candidate player names for a loose spelling, best first: [{name, score, matches, last_match}].

    Searches everyone who batted or bowled (in `competition` if given, else every competition incl. women's).
    """
    cond, p = "1=1", []
    if competition:
        c = competitions.get(competition)
        cond, p = "m.competition = ? AND m.gender = ?", [c.competition, c.gender]
    base = (f"SELECT d.match_id, m.date, d.batter, d.bowler FROM deliveries d "
            f"JOIN matches m ON d.match_id = m.match_id WHERE {cond}")
    names = f"SELECT DISTINCT batter AS name FROM ({base}) UNION SELECT DISTINCT bowler FROM ({base})"
    out = _rank(names, p + p, name, limit * 4)
    for r in out:
        s = query(f"SELECT count(DISTINCT match_id) AS n, max(date) AS last FROM ({base}) "
                  "WHERE batter = ? OR bowler = ?", p + [r["name"], r["name"]])
        r["matches"] = int(s["n"].iloc[0])
        r["last_match"] = None if pd.isna(s["last"].iloc[0]) else str(pd.Timestamp(s["last"].iloc[0]).date())
    out.sort(key=lambda r: (-r["score"], -r["matches"]))  # same score (A Kohli / V Kohli): more matches first
    return out[:limit]


def resolve_team(name: str, competition: str | None = None, limit: int = 5) -> list[dict]:
    """Candidate team names for a loose spelling, best first: [{name, score}]."""
    cond, p = "1=1", []
    if competition:
        c = competitions.get(competition)
        cond, p = "competition = ? AND gender = ?", [c.competition, c.gender]
    names = (f"SELECT team1 AS name FROM matches WHERE {cond} UNION "
             f"SELECT team2 FROM matches WHERE {cond}")
    return _rank(names, p + p, name, limit)


def data_info() -> dict:
    """What is in the DB: per-competition match count, earliest and latest match date."""
    df = query("SELECT competition, gender, count(*) AS matches, min(date) AS earliest, max(date) AS latest "
               "FROM matches GROUP BY ALL ORDER BY 1, 2")
    keys = {(c.competition, c.gender): k for k, c in competitions.COMPETITIONS.items()}
    rows = [{"competition": keys.get((r.competition, r.gender), f"{r.competition}/{r.gender}"),
             "matches": int(r.matches), "earliest": str(r.earliest)[:10], "latest": str(r.latest)[:10]}
            for r in df.itertuples()]
    path = current_db_path()
    return {"db_path": str(path),
            "db_modified": dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            "source": SOURCE, "competitions": rows}


@functools.lru_cache(maxsize=256)
def _choices(db: str, mtime: float, kind: str, competition: str | None, season: str | None) -> tuple[str, ...]:
    # db and mtime are only cache keys: a rebuilt DB file gets fresh lists
    where, p = Filters(competition=competition, season=season).where("match")
    if kind == "season":   # every season of the competition, newest first (a season filter would hide the others)
        where, p = Filters(competition=competition).where("match")
        sql = (f"SELECT m.season AS name FROM matches m WHERE {where} AND m.season IS NOT NULL "
               "GROUP BY 1 ORDER BY min(m.date) DESC")
    elif kind == "team":
        sql = (f"SELECT name FROM (SELECT m.team1 AS name FROM matches m WHERE {where} UNION ALL "
               f"SELECT m.team2 FROM matches m WHERE {where}) WHERE name IS NOT NULL GROUP BY 1 ORDER BY 1")
        p = p + p
    elif kind == "venue":
        sql = (f"SELECT m.venue AS name FROM matches m WHERE {where} AND m.venue IS NOT NULL "
               "GROUP BY 1 ORDER BY count(*) DESC, 1")
    else:   # player: most matches first, so familiar names lead the dropdown
        sql = (f"SELECT name FROM (SELECT d.match_id, d.batter AS name FROM deliveries d JOIN matches m USING (match_id) "
               f"WHERE {where} UNION SELECT d.match_id, d.bowler FROM deliveries d JOIN matches m USING (match_id) "
               f"WHERE {where}) WHERE name IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC, 1")
        p = p + p
    return tuple(query(sql, p)["name"].tolist())


_CHOICE_KINDS = {"player": "player", "player2": "player", "team": "team", "opposition": "team",
                 "venue": "venue", "season": "season"}


def choices(kind: str, competition: str | None = None, season: str | int | None = None) -> list[str]:
    """Values for a dropdown: kind = player | player2 | team | opposition | venue | season.

    Limited to `competition` (None = all men's) and `season`. Players: most matches first; seasons: newest first;
    venues: most matches first; teams: A-Z. Cached per DB file version.
    """
    if kind not in _CHOICE_KINDS:
        raise ValueError(f"choices kind must be one of {', '.join(_CHOICE_KINDS)}, got {kind!r}")
    if competition:
        competitions.get(competition)
    path = current_db_path()
    return list(_choices(str(path), path.stat().st_mtime, _CHOICE_KINDS[kind], competition or None,
                         None if season in (None, "") else str(season)))
