"""IPL trade tool: what a swap of players between two teams does to each side's best XII (on recent value, with honest ranges)."""

import pandas as pd

from ..models import trade as T
from ..registry import ParamSpec, module, std

TEAM_NAMES = tuple(T.TEAMS.values())


def _one(x):
    return x[0] if isinstance(x, (list, tuple)) and x else x


def _label(pt: pd.DataFrame, keys) -> str:
    return ", ".join(f"{pt.loc[k, 'player']} ({pt.loc[k, 'salary']:g} cr)" for k in keys) or "-"


def _trade_frame(r: dict) -> pd.DataFrame:
    rows = []
    for ab in r["order"]:
        x = r["teams"][ab]
        b, a = x["before"], x["after"]
        size = [f"squad of {a['n_squad']} is outside 18-25"] if not 18 <= a["n_squad"] <= 25 else []
        unknown = [
            f"{a['table'].loc[k, 'player']}: no IPL evidence since 2023 (value 0)"
            for k in x["got"]
            if not a["table"].loc[k, "has_evidence"]
        ]
        rows.append(
            {
                "team": T.TEAMS[ab],
                "gives": _label(b["table"], x["lost"]),
                "gets": _label(a["table"], x["got"]),
                "xii_before": round(b["value"], 2),
                "before_lo": round(b["lo"], 2),
                "before_hi": round(b["hi"], 2),
                "xii_after": round(a["value"], 2),
                "after_lo": round(a["lo"], 2),
                "after_hi": round(a["hi"], 2),
                "change": round(x["delta"], 2),
                "change_lo": round(x["delta_lo"], 2),
                "change_hi": round(x["delta_hi"], 2),
                "p_better": round(x["p_better"], 2),
                "verdict": x["verdict"],
                "squad_salary_before": round(b["squad_salary"], 2),
                "squad_salary_after": round(a["squad_salary"], 2),
                "purse_freed_cr": round(x["purse_change"], 2),
                "net_value_cr": round(x["net_value_cr"], 1),
                "value_per_cr_before": round(b["value_per_cr"], 4),
                "value_per_cr_after": round(a["value_per_cr"], 4),
                "holes_before": ", ".join(b["holes"]),
                "holes_after": ", ".join(a["holes"]),
                "holes_created": ", ".join(x["holes_created"]),
                "holes_filled": ", ".join(x["holes_filled"]),
                "squad_size_after": a["n_squad"],
                "notes": "; ".join(a["pick"]["flags"] + size + unknown),
            }
        )
    return pd.DataFrame(rows)


@module(
    id="trade",
    title="IPL trade tool: best XII before and after a player swap",
    category="experimental",
    description="Evaluates a swap of players between two IPL teams on RECENT value (wins above replacement per season, IPL 2023-26, "
    "recent seasons weighted 4/3/2/1), not on a forecast. For each team it picks the best legal XI plus impact player from the 2027 "
    "squad (max 4 overseas, a reviewed-list keeper, 5+ bowling options, 6+ top-seven batters), then shows XII value before and after "
    "with a range from bootstrapping each player's own matches, salary change, value per crore, and the slots (keeper, openers, ...) "
    "that become weak or strong. The verdict says 'too close to call' when the ranges overlap. view=squad lists one team's players "
    "with recent value, range, value per crore and surplus (value in rupees minus salary).",
    params=[
        *std("competition", super_overs=False),
        ParamSpec("team", "choice", default=TEAM_NAMES[5], choices=TEAM_NAMES, help="Team A"),
        ParamSpec("team2", "choice", default=TEAM_NAMES[8], choices=TEAM_NAMES, help="Team B"),
        ParamSpec(
            "give",
            "player",
            multi=True,
            help="Players Team A gives (contract name or Cricsheet name; must be in Team A's squad)",
        ),
        ParamSpec(
            "get",
            "player",
            multi=True,
            help="Players Team A gets from Team B (must be in Team B's squad)",
        ),
        ParamSpec(
            "view",
            "choice",
            default="trade",
            choices=("trade", "squad"),
            help="trade = before/after for both teams; squad = Team A's players",
        ),
        ParamSpec(
            "baseline",
            "choice",
            default="current",
            choices=("current", "before_trades"),
            help="current = squads after the announced 2027 trades; before_trades = undo the announced trades of the named players first",
        ),
    ],
    caveats=[
        "Value is RECENT, not predicted: batters' projections showed no out-of-sample skill (r 0.06) and team win share is mostly luck, so no playoff or title odds are shown.",
        "Recent value only weakly carries into the next season (IPL 2025-26 targets: r 0.13, slope 0.17 over 218 player-seasons): most of a season's value is luck, so a gap between two players is rarely skill.",
        "A trade only changes the XII when a player is good enough (by recent value) to be in it or to push someone out; the XII ignores reputation, so a poor-recent-form star can sit outside it and a swap then reads 'no change'.",
        "Ranges (10th-90th percentile) come from resampling each player's own matches; they do not include role changes, injuries, age, or fielding. A 'likely' verdict means most resamples agree, not that the future is known.",
        "Players with no IPL evidence since 2023 (new signings, uncapped) count as 0 (replacement) with the spread of past debutants; nothing is invented for them.",
        "Salaries are 2026 prices from Wikipedia; retained totals of CSK, DC, KKR and RR do not reconcile with the official figures, and no retention or release lists exist yet (re-run after 17 Nov 2026).",
        "Keepers, bowling type and hand come only from the reviewed list, which does not yet cover every keeper (KKR, PBKS and RR squads have none listed, so the keeper rule is skipped for them).",
        "The best XII is found by a simple swap search with documented rules (docs/VALUE_step5.md); it is not a captain's choice.",
    ],
)
def trade(
    f,
    team: str = TEAM_NAMES[5],
    team2: str = TEAM_NAMES[8],
    give=None,
    get=None,
    view: str = "trade",
    baseline: str = "current",
) -> pd.DataFrame:
    if f.competition not in (None, "ipl"):
        raise ValueError("The trade tool covers the IPL only (competition=ipl)")
    # "team" is also a Filters field, so api.run routes it into f, not into this kwarg.
    team, team2 = _one(f.team or team), _one(team2)
    if view == "squad":
        return T.squad_view(team)
    r = T.evaluate(team, team2, give or [], get or [], baseline)
    return _trade_frame(r)
