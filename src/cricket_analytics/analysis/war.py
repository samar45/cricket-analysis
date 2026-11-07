"""Wins Above Replacement (WAR) for IPL player-seasons, and projected WAR (pWAR) for IPL 2027."""

from functools import lru_cache

import pandas as pd

from ..db import current_db_path
from ..models import war as w
from ..registry import ParamSpec, module, std
from ..sql.filters import explain_empty

MIN_BALLS = 100
PROJ_SEASON = 2027
PROJ_CSV = w.DATA / f"pwar_ipl_{PROJ_SEASON}.csv"


@lru_cache(maxsize=2)
def _ipl_rows(db_path: str, db_mtime: float, version: str = "v2") -> pd.DataFrame:
    fld = w.load_params("v2")["fielding"] if version == "v2" else None
    return w.centre(w.season_table("ipl", db_path, fielding=fld)[0])


def _scoped(f, version: str = "v2") -> pd.DataFrame:
    """IPL player-season-team rows narrowed by season / team (the only filters WAR understands)."""
    if f.competition not in (None, "ipl"):
        raise ValueError("WAR is measured for the IPL only (competition=ipl)")
    for name in ("venue", "opposition", "phase"):
        if f.values(name):
            raise ValueError(f"WAR is a season total: the {name} filter is not supported")
    path = current_db_path()
    r = _ipl_rows(str(path), path.stat().st_mtime, version)
    items = [str(x).strip() for x in f.values("season")]
    if items:
        years = [int(x) for x in items if len(x) == 4 and x.isdigit()]
        r = r[r.sy.isin(years) | r.season.isin(items)]
    if f.season_from is not None:
        r = r[r.sy >= int(f.season_from)]
    if f.season_to is not None:
        r = r[r.sy <= int(f.season_to)]
    if f.last_n_years is not None:
        r = r[r.sy > r.sy.max() - int(f.last_n_years)]
    teams = f.values("team")
    return r[r.team.isin(teams)] if teams else r


def _projected(f, role: str, components: bool, top: int) -> pd.DataFrame:
    if f.competition not in (None, "ipl") or any(
        f.values(n) for n in ("season", "team", "venue", "opposition", "phase")
    ):
        raise ValueError(
            "view=projected is the fixed IPL 2027 table: only the player filter applies"
        )
    d = pd.read_csv(PROJ_CSV).rename(
        columns={"cricsheet_name": "player", "pwar": "pwar", "bat": "bat_pwar", "bowl": "bowl_pwar", "field": "field_pwar"}
    )
    if f.player:
        d = d[d.player == f.player]
    key = {"all": "pwar", "batting": "bat_pwar", "bowling": "bowl_pwar"}[role]
    keep = {
        "all": ["player", "pwar", "bat_pwar", "bowl_pwar", "field_pwar", "exp_balls_bat", "exp_balls_bowl"]
        + (["bat_rate", "bowl_rate"] if components else []),
        "batting": ["player", "bat_pwar", "exp_balls_bat", "bat_rate"],
        "bowling": ["player", "bowl_pwar", "exp_balls_bowl", "bowl_rate"],
    }[role]
    return (
        d.sort_values([key, "player"], ascending=[False, True])[keep + ["ipl_balls_2023_on"]]
        .head(int(top))
        .reset_index(drop=True)
    )


@module(
    id="war",
    title="Wins above replacement (WAR) and projected WAR for IPL 2027",
    category="advanced",
    description="WAR turns a player's runs added (see the runs_added module) into wins: runs added minus what a replacement-level "
    "player would have added in the same balls, divided by the runs one win costs in that IPL era (about 100 runs in 2023+). "
    "view=season lists player-seasons (rank by WAR; batting and bowling are added together for all-rounders). "
    "view=projected lists pWAR for IPL 2027: a prediction made only from earlier seasons (IPL 2023+, plus other T20 leagues at a "
    "lower weight), pulled hard toward the average because single-season runs added is mostly noise. 1.0 = one win.",
    params=[
        *std("player", "competition", "season", "team", super_overs=False),
        ParamSpec("role", "choice", default="all", choices=("all", "batting", "bowling")),
        ParamSpec(
            "view",
            "choice",
            default="season",
            choices=("season", "projected"),
            help="season = realised WAR per player-season; projected = pWAR for IPL 2027",
        ),
        ParamSpec(
            "components",
            "bool",
            default=False,
            help="Also show the scoring part and the wicket part of runs added",
        ),
        ParamSpec(
            "min_balls",
            "int",
            help="Hide player-seasons with fewer balls than this (default 100; 1 when you pick one player)",
        ),
        ParamSpec("top", "int", default=40, help="Rows to return"),
        ParamSpec(
            "version",
            "choice",
            default="v2",
            choices=("v1", "v2"),
            help="v2 (default) adds fielding credit and replacement -6 runs per 100 balls; v1 is the original (no fielding)"
        ),
    ],
    caveats=[
        "Runs per win and the replacement level are measured from IPL 2023-2026 only (the Impact Player era); older seasons use their own era numbers (about 91 runs per win, from IPL 2008-2022). Runs per win has a wide range: 81 to 125 for 2023+ (40 team-seasons).",
        "Replacement level is a convention: -6 runs per 100 balls for batters and bowlers (v1 measured it from players outside their team's usual XI the following season, which is biased toward good players; counting the same season gives much lower values).",
        "WAR is only as repeatable as runs added is: a season's runs added is mostly luck (talent explains roughly 5-10% of the spread between players). Do not read a 0.5 difference between two players as skill.",
        "pWAR is a prediction, not a rating. Out of sample (IPL 2024-2026) it ranks bowlers a bit better than last season's WAR and it does not beat the simple baselines for batters or for team win share. No age data is used.",
        "pWAR counts expected balls from the last three IPL seasons. A player with no IPL ball since 2023 has 0 expected balls and pWAR 0 (see the ipl_balls_2023_on column); his projected rate is still shown.",
        "bat_runs_added / bowl_runs_added here are re-centred (each league-season is shifted so an average player is 0 before replacement is subtracted), so they differ from the runs_added module for the same player-season (e.g. Kohli 2016: 162.2 here vs 153.4 there). WAR is exact against its own columns.",
        "version=v2 (default) moves 20% of each catch / stumping from the bowler to the fielder and gives run-outs to the fielders (a convention: no drop or chance data), and uses replacement -6 runs per 100 balls (a replacement-level team wins about 36%); version=v1 is the original (no fielding, higher replacement level). pWAR uses the same v2 conventions (fielding part = past fielding WAR shrunk by 0.75); see docs/VALUE_war_fix.md. Team changes inside a season are added together; only IPL is supported.",
    ],
)
def war(
    f,
    role: str = "all",
    view: str = "season",
    components: bool = False,
    min_balls: int | None = None,
    top: int = 40,
    version: str = "v2",
) -> pd.DataFrame:
    if view == "projected":
        return _projected(f, role, components, top)
    if min_balls is None:
        min_balls = 1 if f.player else MIN_BALLS
    r = _scoped(f, version)
    if r.empty:
        raise explain_empty(f, "WAR (IPL seasons 2008-2026)")
    prm = w.load_params(version)
    t = w.war_table(r, prm)
    fld = version == "v2"
    if f.player:
        t = t[t.player == f.player]
        if t.empty:
            raise explain_empty(f, "WAR")
    bb, wb = t.bat_balls, t.bowl_balls
    t = t.assign(season=t.sy)
    if role == "batting":
        t = t[bb >= min_balls]
        out = pd.DataFrame(
            {
                "player": t.player,
                "season": t.season,
                "balls": t.bat_balls,
                "runs": t.bat_runs,
                "runs_added": t.bat_ra.round(1),
                "replacement_runs": t.bat_repl_runs.round(1),
                "war": t.bat_war.round(2),
            }
        )
        if components:
            out["scoring_part"], out["wicket_part"] = t.bat_sc.round(1), t.bat_wk.round(1)
        key = "war"
    elif role == "bowling":
        t = t[wb >= min_balls]
        out = pd.DataFrame(
            {
                "player": t.player,
                "season": t.season,
                "legal_balls": t.bowl_balls,
                "runs_conceded": t.bowl_runs,
                "wickets": t.bowl_wkts.astype(int),
                "runs_added": t.bowl_ra.round(1),
                "replacement_runs": t.bowl_repl_runs.round(1),
                "war": t.bowl_war.round(2),
            }
        )
        if components:
            out["scoring_part"], out["wicket_part"] = t.bowl_sc.round(1), t.bowl_wk.round(1)
        key = "war"
    else:
        t = t[(bb >= min_balls) | (wb >= min_balls)]
        out = pd.DataFrame(
            {
                "player": t.player,
                "season": t.season,
                "bat_balls": t.bat_balls,
                "bowl_balls": t.bowl_balls,
                "bat_runs_added": t.bat_ra.round(1),
                "bowl_runs_added": t.bowl_ra.round(1),
                "bat_war": t.bat_war.round(2),
                "bowl_war": t.bowl_war.round(2),
                **({"field_war": t.field_war.round(2)} if fld else {}),
                "war": t.war.round(2),
            }
        )
        if components:
            for a, b in (
                ("bat_scoring", "bat_sc"),
                ("bat_wicket", "bat_wk"),
                ("bowl_scoring", "bowl_sc"),
                ("bowl_wicket", "bowl_wk"),
            ):
                out[a] = t[b].round(1)
        key = "war"
    return (
        out.sort_values([key, "player", "season"], ascending=[False, True, True])
        .head(int(top))
        .reset_index(drop=True)
    )
