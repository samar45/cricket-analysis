"""One JSON of headline facts for a player, for a reel: `cricket facts --player "V Kohli" --competition ipl --out facts.json`.

    {"meta": {provenance, "facts_version": 1, "generated", "calls": [...], "skipped": [...]},
     "facts": {"career": {"source": [{"module", "params"}], "runs": 9336, ...}, "by_phase": {"death": {...}}, ...},
     "tokens": {"career.runs": "9,336", ...},        # display strings, for {career.runs} substitution
     "tokens_raw": {"career.runs": 9336, ...}}       # the same keys, raw numbers
Only sections that have data are present. Every section lists the module calls it came from.
"""

import datetime as dt
import math
import re

import pandas as pd

from . import api

FACTS_VERSION = 1
MIN_BALLS = 300     # a side of the game (bat or bowl) joins the career card at this many balls
PHASES = ("powerplay", "middle", "death")
ORDER = ("career", "best_season", "by_phase", "vs_pace_spin", "home_away", "chase_vs_set", "pressure", "dismissals",
         "profile")


class PlayerNotFound(ValueError):
    def __init__(self, name, candidates):
        self.candidates = candidates
        super().__init__(f"No data for player {name!r}")


def _clean(v):
    """numpy/pandas scalar -> plain Python; NaN/None/'unknown' -> None."""
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    return None if v in ("unknown", "Unknown", "") else v


def _pick(row, cols) -> dict:
    """{out_name: value} from a DataFrame row; cols maps out_name -> column (a list means same name)."""
    cols = cols if isinstance(cols, dict) else {c: c for c in cols}
    out = {k: _clean(row[c]) for k, c in cols.items() if c in row.index}
    return {k: v for k, v in out.items() if v is not None}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def _fmt(v) -> str:
    if isinstance(v, str):
        return v
    if float(v) == int(v):
        return f"{int(v):,}"
    return f"{v:,.1f}" if abs(v) >= 100 else f"{v:,.2f}"


def _flatten(d: dict, prefix: str, raw: dict) -> None:
    for k, v in d.items():
        if k == "source":
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten(v, key, raw)
        elif isinstance(v, (int, float, str)) and not isinstance(v, bool):
            raw[key] = v


def build(player: str, competition: str | None = None, last_n_years: int | None = None, db_path=None) -> dict:
    base = {"player": player, **({"competition": competition} if competition else {}),
            **({"last_n_years": last_n_years} if last_n_years else {})}
    calls, results, skipped = [], [], []

    def call(module, **extra):
        r = api.run(module, db_path=db_path, **base, **extra)
        src = {"module": module, "params": r.meta["params"]}
        calls.append(src)
        results.append(r)
        return r, src

    facts: dict = {}

    def section(name, fn):
        """fn() -> dict | None. None or an error is recorded in meta.skipped; one broken module must not sink the file."""
        try:
            out = fn()
        except Exception as e:
            skipped.append({"section": name, "reason": f"error: {e}"})
            return
        if out:
            facts[name] = out
        else:
            skipped.append({"section": name, "reason": "no data"})

    bat, s_bat = call("batting")
    bowl, s_bowl = call("bowling")
    bat_row = bat.data.iloc[0] if len(bat.data) else None
    bowl_row = bowl.data.iloc[0] if len(bowl.data) else None
    if bat_row is None and bowl_row is None:
        raise PlayerNotFound(player, api.resolve_player(player, competition, 5))
    bat_balls = int(bat_row["balls"]) if bat_row is not None else 0
    bowl_balls = int(bowl_row["balls"]) if bowl_row is not None else 0
    role = "bowling" if bowl_balls > bat_balls else "batting"
    bats = bat_row is not None and (bat_balls >= MIN_BALLS or role == "batting")
    bowls = bowl_row is not None and (bowl_balls >= MIN_BALLS or role == "bowling")

    career, src = {}, []
    if bats:
        career.update(_pick(bat_row, {"innings": "innings", "not_outs": "not_outs", "runs": "total_runs", "balls": "balls",
                                      "highest": "highest", "average": "average", "strike_rate": "strike_rate",
                                      "fifties": "fifties", "hundreds": "hundreds", "fours": "fours", "sixes": "sixes"}))
        src.append(s_bat)
    if bowls:
        career.update(_pick(bowl_row, {"bowl_innings": "innings", "wickets": "wickets", "runs_conceded": "runs_conceded",
                                       "balls_bowled": "balls", "economy": "economy", "bowl_average": "average",
                                       "bowl_strike_rate": "strike_rate", "best_figures": "best_figures",
                                       "three_plus": "three_plus", "five_plus": "five_plus"}))
        src.append(s_bowl)
    facts["career"] = {"source": src, **career}

    def best_season():
        bat_side = role == "batting"
        r, s = call(role, group_by="season")
        if r.data.empty:
            return None
        key = "total_runs" if bat_side else "wickets"
        row = r.data.loc[r.data[key].idxmax()]
        cols = ({"season": "season", "runs": "total_runs", "innings": "innings", "average": "average",
                 "strike_rate": "strike_rate", "highest": "highest"} if bat_side else
                {"season": "season", "wickets": "wickets", "innings": "innings", "economy": "economy",
                 "best_figures": "best_figures"})
        return {"source": [s], **_pick(row, cols)}

    def by_phase():
        r, s = call(role, group_by="phase")
        cols = ({"innings": "innings", "runs": "total_runs", "balls": "balls", "average": "average",
                 "strike_rate": "strike_rate", "boundary_pct": "boundary_pct"} if role == "batting" else
                {"innings": "innings", "balls": "balls", "wickets": "wickets", "economy": "economy", "dot_pct": "dot_pct"})
        out = {row["phase"]: _pick(row, cols) for _, row in r.data.iterrows() if row["phase"] in PHASES}
        return {"source": [s], **out} if out else None

    def vs_pace_spin():
        r, s = call("pace_vs_spin")
        kinds = {str(row["bowler_type"]).lower(): _pick(row, ["innings", "runs", "balls", "strike_rate", "average",
                                                              "dismissals", "dot_pct", "pct_of_balls"])
                 for _, row in r.data.iterrows() if row["level"] == "kind"}
        if "pace" not in kinds and "spin" not in kinds:
            return None
        unk = kinds.pop("unknown", {}).get("pct_of_balls")
        return {"source": [s], **kinds, **({"unknown_pct": unk} if unk is not None else {})}

    def home_away():
        r, s = call("home_away", role=role)
        cols = ({"matches": "matches", "runs": "total_runs", "average": "average", "strike_rate": "strike_rate"}
                if role == "batting" else {"matches": "matches", "wickets": "wickets", "economy": "economy"})
        out = {row["location"]: _pick(row, cols) for _, row in r.data.iterrows() if row["location"] != "unknown"}
        return {"source": [s], **out} if out else None

    def chase_vs_set():
        r, s = call("chase_vs_set", role=role)
        cols = (["innings", "runs", "average", "strike_rate", "big_games", "win_pct"] if role == "batting"
                else ["innings", "wickets", "economy", "big_games", "win_pct"])
        out = {row["setting"]: _pick(row, cols) for _, row in r.data.iterrows() if row["setting"] in ("setting", "chasing")}
        return {"source": [s], **out} if out else None

    def pressure():
        r, s = call("pressure", role=role)
        if r.data.empty:
            return None
        cols = ({"balls": "pressure_balls", "runs": "pressure_runs", "outs": "pressure_outs", "strike_rate": "pressure_sr",
                 "average": "pressure_avg", "calm_strike_rate": "calm_sr", "sr_change": "sr_change"} if role == "batting" else
                {"balls": "pressure_legal_balls", "wickets": "pressure_wickets", "economy": "pressure_economy",
                 "calm_economy": "calm_economy", "economy_change": "economy_change"})
        out = _pick(r.data.iloc[0], cols)
        return {"source": [s], **out} if out.get("balls") else None

    def dismissals():
        r, s = call("dismissal_profile")
        if r.data.empty:
            return None
        d = r.data.sort_values("outs", ascending=False)
        kinds = {_slug(row["kind"]): {"label": row["kind"], "outs": int(row["outs"]), "pct": float(row["pct"])}
                 for _, row in d.iterrows()}
        return {"source": [s], "total": int(d["outs"].sum()), "top_kind": d.iloc[0]["kind"],
                "top_pct": float(d.iloc[0]["pct"]), "kinds": kinds}

    def profile():
        r, s = call("player_profile", min_matches=1)
        if r.data.empty:
            return None
        return {"source": [s], **_pick(r.data.iloc[0], ["role", "bowl_kind", "bowl_type", "bat_hand", "keeper",
                                                         "usually_bats_at", "usually_faces_in", "usually_bowls_in"])}

    section("best_season", best_season)
    section("by_phase", by_phase)
    if role == "batting":   # these three are batter views; a bowler's tail-end numbers would mislead
        section("vs_pace_spin", vs_pace_spin)
    section("home_away", home_away)
    section("chase_vs_set", chase_vs_set)
    section("pressure", pressure)
    if role == "batting":
        section("dismissals", dismissals)
    section("profile", profile)
    facts = {k: facts[k] for k in ORDER if k in facts}

    raw: dict = {}
    _flatten(facts, "", raw)
    first = results[0].meta
    meta = {
        "facts_version": FACTS_VERSION, "player": player, "role": role, "params": base,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "data_through": max((r.meta["data_through"] for r in results if r.meta["data_through"]), default=None),
        "db_path": first["db_path"], "db_modified": first["db_modified"], "source": first["source"],
        "competition_note": None if competition else "No competition given: all men's T20 competitions combined.",
        "caveats": list(dict.fromkeys(c for r in results for c in r.meta["caveats"])),
        "calls": calls, "skipped": skipped,
    }
    return {"meta": meta, "facts": facts, "tokens": {k: _fmt(v) for k, v in raw.items()}, "tokens_raw": raw}
