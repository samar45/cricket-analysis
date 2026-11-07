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
def _ipl_data(db_path: str, db_mtime: float, version: str = "v3") -> tuple[pd.DataFrame, pd.DataFrame]:
    fld = w.load_params("v2")["fielding"] if version == "v2" else None
    rows, apps = w.season_table("ipl", db_path, fielding=fld)
    rows = w.centre(rows)
    mw = w.load_params(version).get("match_w", 0.0)
    return (w.match_adjust_rows(rows, mw) if mw else rows), apps


def _scoped(f, version: str = "v3") -> tuple[pd.DataFrame, pd.DataFrame]:
    """IPL player-season-team rows narrowed by season (team is applied later, on whole player-seasons, so the fielding
    group averages always come from every player)."""
    if f.competition not in (None, "ipl"):
        raise ValueError("WAR is measured for the IPL only (competition=ipl)")
    for name in ("venue", "opposition", "phase"):
        if f.values(name):
            raise ValueError(f"WAR is a season total: the {name} filter is not supported")
    path = current_db_path()
    r, apps = _ipl_data(str(path), path.stat().st_mtime, version)
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
    return r, apps


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
    if "field_pwar" not in d:
        d["field_pwar"] = 0.0
    if f.player:
        d = d[d.player == f.player]
    key = {"all": "pwar", "batting": "bat_pwar", "bowling": "bowl_pwar"}[role]
    keep = {
        "all": ["player", "pwar", "bat_pwar", "bowl_pwar", "exp_balls_bat", "exp_balls_bowl"]
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
    "view=season lists player-seasons ranked by main_war: the part of WAR from the player's main job (batting for batters, bowling for bowlers, both for all-rounders; main_role from the share of his balls spent bowling); war is batting + bowling (v3 has no fielding). "
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
            default="v3",
            choices=("v1", "v2", "v3"),
            help="v3 (default) = batting + bowling only, runs added 25% adjusted for match conditions, replacement -6 per 100 balls; v2 adds fielding credit; v1 is the original"
        ),
        ParamSpec(
            "fair_fielding",
            "bool",
            default=True,
            help="version=v2 only: fielding compared with the player's own group (keepers vs keepers, others vs others) and shrunk by its reliability; off = raw credit",
        ),
    ],
    caveats=[
        "WAR v3 (default) is batting + bowling only: the bowler keeps full credit for catches and stumpings and a run-out credits nobody (see the fielding module for fielding). Runs added is adjusted 25% for match conditions: each ball is also compared with what the other players did in the same match, phase and role (a weak or strong opponent, a flat pitch), at weight 0.25 because one match tells little about the opposition. The scoring part below includes this adjustment.",
        "Runs per win and the replacement level are measured from IPL 2023-2026 only (the Impact Player era); older seasons use their own era numbers (about 91 runs per win, from IPL 2008-2022). Runs per win has a wide range: 81 to 125 for 2023+ (40 team-seasons).",
        "Replacement level is a convention: -6 runs per 100 balls for batters and bowlers (v1 measured it from players outside their team's usual XI the following season, which is biased toward good players; counting the same season gives much lower values).",
        "WAR is only as repeatable as runs added is: a season's runs added is mostly luck (talent explains roughly 5-10% of the spread between players). Do not read a 0.5 difference between two players as skill.",
        "pWAR is a prediction, not a rating. Out of sample (IPL 2024-2026) it ranks bowlers a bit better than last season's WAR and it does not beat the simple baselines for batters or for team win share. No age data is used.",
        "pWAR counts expected balls from the last three IPL seasons. A player with no IPL ball since 2023 has 0 expected balls and pWAR 0 (see the ipl_balls_2023_on column); his projected rate is still shown.",
        "bat_runs_added / bowl_runs_added here are re-centred (each league-season is shifted so an average player is 0 before replacement is subtracted), so they differ from the runs_added module for the same player-season (e.g. Kohli 2016: 127.5 here vs 153.4 there, mostly the match adjustment). WAR is exact against its own columns.",
        "main_role: bowling share of (balls faced + balls bowled) under 20% = batter, over 80% = bowler, otherwise all-rounder. main_war = batting WAR for batters, bowling WAR for bowlers, bat + bowl for all-rounders, so a bowler is not judged by his batting, nor a batter by his bowling.",
        "version=v2 only. Fair fielding (default): a keeper's catches and stumpings are compared with the average keeper per match, a non-keeper's with the average non-keeper (keepers = yes / sometimes in the reviewed list), then shrunk toward 0 by season-to-season reliability (about 0.4 to 0.5 for catches at 13 matches, about 0.07 for run-outs). Fielding positions (slips, deep) and dropped catches are not in the data, so field_war is a rough guide; fair_fielding=false gives the raw credit. Matches = matches he batted or bowled in.",
        "version=v2 moves 20% of each catch / stumping from the bowler to the fielder and gives run-outs to the fielders (a convention: no drop or chance data), and uses replacement -6 runs per 100 balls (a replacement-level team wins about 36%); version=v1 is the original (no fielding, higher replacement level). pWAR (bat + bowl) is refit on the v3 adjusted rates; see docs/VALUE_war_v3.md. Team changes inside a season are added together; only IPL is supported.",
    ],
)
def war(
    f,
    role: str = "all",
    view: str = "season",
    components: bool = False,
    min_balls: int | None = None,
    top: int = 40,
    version: str = "v3",
    fair_fielding: bool = True,
) -> pd.DataFrame:
    if view == "projected":
        return _projected(f, role, components, top)
    if min_balls is None:
        min_balls = 1 if f.player else MIN_BALLS
    r, apps = _scoped(f, version)
    if r.empty:
        raise explain_empty(f, "WAR (IPL seasons 2008-2026)")
    prm = w.load_params(version)
    fld = version == "v2"
    t = w.war_table(r, prm, apps if fld and fair_fielding else None)
    if f.values("team"):  # players who played for the team that season, with their whole season (all teams added together)
        t = t.merge(r[r.team.isin(f.values("team"))][["player", "sy"]].drop_duplicates(), on=["player", "sy"])
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
        role_ = w.main_role(t.bat_balls, t.bowl_balls)
        main = t.bat_war.where(role_ == "batter", t.bowl_war.where(role_ == "bowler", t.bat_war + t.bowl_war))
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
                **({"field_war": t.field_war.round(2)} if fld else {}),  # v2 only
                "main_role": role_,
                "main_war": main.round(2),
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
        key = "main_war"
    return (
        out.sort_values([key, "player", "season"], ascending=[False, True, True])
        .head(int(top))
        .reset_index(drop=True)
    )
