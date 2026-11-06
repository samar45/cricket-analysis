"""Supply and demand in IPL auctions: which roles were scarce, per auction, per team, and the provisional 2027 view."""

import pandas as pd

from ..models import scarcity as S
from ..models import trade as T
from ..registry import ParamSpec, module, std

VIEWS = ("auction", "team_needs", "2027")


def _first(x):
    return x[0] if isinstance(x, (list, tuple)) and x else x


def _auction(year: int) -> pd.DataFrame:
    i = S.index_table()
    if year not in set(i.year):
        raise ValueError(
            f"No auction {year}. Valid: {', '.join(map(str, sorted(set(i.year))))} (2027 = view 2027)"
        )
    d = i[i.year == year].sort_values("index", ascending=False)
    return pd.DataFrame(
        {
            "role": d.role,
            "teams_needing": d.teams_needing,
            "need_slots": d.need_slots.round(1),
            "demand": d.demand.round(2),
            "supply_all": d.supply_all,
            "supply_quality": d.supply_quality,
            "scarcity_index": d["index"].round(2),
            "relative": d.rel_index.round(2),
            "avg_price_cr": d.avg_price_cr.round(2),
            "n_sold": d.n_sold_main,
        }
    ).reset_index(drop=True)


def _team_needs(year: int, team: str | None) -> pd.DataFrame:
    if year == 2027:
        t = pd.read_csv(S.FWD_TEAMS_CSV)
    else:
        t = pd.read_csv(S.TEAMS_CSV)
        t = t[t.year == year]
        if t.empty:
            raise ValueError(f"No auction {year}")
    if team:
        t = t[t.team == T.team_abbr(team)]
    return t.reset_index(drop=True)


@module(
    id="scarcity",
    title="IPL auction supply and demand: scarcity index per role",
    category="experimental",
    description="For each IPL auction 2022-2026: the roles a team needs (open or weak slots in its best XII before the auction, "
    "weighted by purse left) against the players put on the block who can fill them at league-median recent value or better. "
    "Roles come from how a player was used in the three years before (batting position, bowling phase) plus the reviewed list "
    "(bowling type, keeper). view=auction (year) lists the roles with demand, supply, index and the average price paid; "
    "view=team_needs lists each team's open places, purse and weak slots; view=2027 is the PROVISIONAL forward view from today's "
    "squads (retentions are due 17 Nov 2026).",
    params=[
        *std("competition", "team", super_overs=False),
        ParamSpec(
            "year",
            "int",
            default=2026,
            help="Auction year 2022-2026 (2027 = provisional forward view)",
        ),
        ParamSpec(
            "view", "choice", default="auction", choices=VIEWS, help="auction / team_needs / 2027"
        ),
    ],
    caveats=[
        "PROVISIONAL for 2027: squads are full and nothing is released yet; supply is assumed from the 2023, 2024 and 2026 mini auctions.",
        "Squads before the 2023 and 2024 auctions are rolled forward from the previous roster minus players put up again (check on 2026: 86% of the real list found, 79% of the derived list correct); trades and retirements are not tracked.",
        "Only about half of the players put on the block have enough recent matches to get a role (the rest are mostly unknown uncapped players); they count in no supply.",
        "Keepers come only from the reviewed list, which is incomplete, so keeper scarcity is overstated. Bowlers without a bowling type on the list get no role.",
        "Test result (docs/VALUE_m6.md): scarcity did NOT raise prices detectably; do not read the index as a price predictor.",
        "Recent value here is a simple shrunk runs-above-average rate, not pWAR, so it works for all years and leagues (a domestic or foreign league rate is not translated to IPL level).",
    ],
)
def scarcity(f, year: int = 2026, view: str = "auction") -> pd.DataFrame:
    if f.competition not in (None, "ipl"):
        raise ValueError("Auction scarcity covers the IPL only (competition=ipl)")
    year = int(year)
    if view == "2027" or (view == "auction" and year == 2027):
        d = pd.read_csv(S.FWD_CSV)
        return (
            d.drop(columns=["year"])
            .round(2)
            .sort_values("index", ascending=False)
            .reset_index(drop=True)
        )
    if view == "team_needs":
        return _team_needs(year, _first(f.team))
    return _auction(year)
