"""IPL XI win odds: pick 11 players (+ an impact player) and see the XII value, the rules check, the win chance against an
average IPL 2027 XII, and the playoff / title odds from the trade tool's season simulation, next to the tool's own best XII."""

import numpy as np
import pandas as pd

from ..models import trade as T
from ..registry import ParamSpec, module, std

TEAM_NAMES = tuple(T.TEAMS.values())


def _one(x):
    return x[0] if isinstance(x, (list, tuple)) and x else x


def _ci(x):
    return float(np.mean(x)), float(np.percentile(x, 10)), float(np.percentile(x, 90))


def rules(pt: pd.DataFrame, xi: list, imp) -> list[dict]:
    """Rule checks of an XI (+ impact player): pass / fail with the count. Same definitions as the best-XII search."""
    x, both = pt.loc[xi], pt.loc[xi + ([imp] if imp else [])]
    bat7 = int(((x.bat_pos.fillna(99) <= 7.0) & (x.bat_matches.fillna(0) >= 5)).sum())
    kp = int((x.keeper | x.keeper_some).sum())
    bw = int(x.is_bowler.sum())
    os_n, os_all = int(x.overseas.sum()), int(both.overseas.sum())
    return [
        {"rule": "Overseas, max 4 (XI + impact)", "value": f"{os_n} + {os_all - os_n}", "ok": os_all <= T.MAX_OS_XI},
        {"rule": "Wicketkeeper", "value": kp, "ok": kp >= 1},
        {"rule": "Bowling options, min 5", "value": bw, "ok": bw >= T.MIN_BOWLERS},
        {"rule": "Top-seven batters, min 6", "value": bat7, "ok": bat7 >= 6},
    ]


def evaluate_xi(team: str, players=(), impact=(), basis: str = T.DEFAULT_BASIS) -> dict:
    """Numbers for one XI of `team` (no players given = the tool's own best XII), next to the tool's best XII."""
    v, ab = T.values(), T.team_abbr(team)
    tab = T.player_table(T.squads(), v, basis)
    D = T.draws_for(tab, v)
    pos = {k: i for i, k in enumerate(tab.index)}
    role = dict(zip(tab.index, T.roles(tab)))
    best = T.pick_xii(tab[tab.team == ab])
    if players:
        xi = T.resolve(tab, players, "league")
        if len(xi) != 11:
            raise ValueError(f"Pick exactly 11 players for the XI, got {len(xi)}")
        imp = T.resolve(tab, impact, "league") if impact else []
        if len(imp) > 1 or set(imp) & set(xi):
            raise ValueError("The impact player is one player who is not in the XI")
        imp = imp[0] if imp else None
        counted = imp is not None and tab.loc[imp, "value"] > 0
        val = tab.loc[xi, "value"].sum() + (T.IMPACT_WEIGHT * tab.loc[imp, "value"] if counted else 0.0)
        you = {"xi": xi, "impact": imp, "impact_counted": bool(counted), "value": float(val)}
    else:
        you = best
    strength = {t: T.pick_xii(tab[tab.team == t])["value"] for t in T.TEAMS}
    avg = float(np.mean(list(strength.values())))
    bt = T.beta(basis)
    sims = {k: T.simulate({**strength, ab: x["value"]}, bt["draws"]) for k, x in (("best", best), ("you", you))}
    odds = T.odds_summary(sims["best"], sims["you"])
    res = {}
    for k, x, tag in (("best", best, "before"), ("you", you, "after")):
        d = T.xii_draws(x, tab, D)
        win = 1 / (1 + np.exp(-np.asarray(bt["draws"])[:, None] * (d[None, :] - avg)))  # beta draws x value draws
        who = [(q, "XI") for q in x["xi"]] + ([(x["impact"], "IMP")] if x["impact"] else [])
        res[k] = {
            "value": float(x["value"]),
            "range": T.rng_text(d),
            "win": _ci(win),
            "playoff": odds[(ab, "playoff")][tag],
            "title": odds[(ab, "title")][tag],
            "rules": rules(tab, x["xi"], x["impact"]),
            "rows": sorted(
                (
                    {"name": tab.loc[q, "player"], "role": role[q], "os": bool(tab.loc[q, "overseas"]),
                     "war": float(tab.loc[q, "value"]), "slot": s, "outside": tab.loc[q, "team"] != ab}
                    for q, s in who
                ),
                key=lambda r: (r["slot"] != "XI", -r["war"]),
            ),
        }  # fmt: skip
    return {"team": T.TEAMS[ab], "abbr": ab, "you": res["you"], "best": res["best"], "avg": avg, "beta": bt,
            "custom": bool(players), "basis": basis, "seasons": T.SIM_BETAS * T.SIM_SEASONS}  # fmt: skip


@module(
    id="xi_odds",
    title="IPL XI win odds: your XI against an average 2027 XII",
    category="experimental",
    description="Pick a team and 11 players (plus an optional impact player) from the 2027 squads. Returns the XII value (wins above "
    "replacement a season, default basis = expected next season) with a range, a pass / fail check of the XI rules, the expected "
    "win % against an average IPL 2027 best XII, and playoff and title % from the simulated season, next to the same numbers for the "
    "tool's own best XII. No players given = the tool's best XII. Players from another squad are allowed and flagged.",
    params=[
        *std("competition", super_overs=False),
        ParamSpec("team", "choice", default=TEAM_NAMES[5], choices=TEAM_NAMES, help="Team"),
        ParamSpec("players", "player", multi=True, help="The 11 players of the XI (contract or Cricsheet name); empty = the tool's best XII"),
        ParamSpec("impact", "player", multi=True, help="Optional impact player (one name)"),
        ParamSpec("value_basis", "choice", default=T.DEFAULT_BASIS, choices=T.BASES, help="recent = WAR 2023-26 weighted 4/3/2/1 (default), worth = expected next-season WAR"),
    ],
    caveats=[
        "Value is a player-level estimate with weak skill: IPL 2024-26 team XII values correlate only about 0.2 with a team's wins (n = 30), so win, playoff and title percentages are ranges, not forecasts.",
        "Win % is the logistic of (fitted slope x gap to the average of the ten best XIIs); the slope is fitted on about 215 IPL 2024-26 matches and is uncertain, and the range shows that.",
        "Playoff and title % come from 40,000 simulated seasons in which the other nine teams play their own best XII.",
        "Players with no IPL evidence since 2023 count as replacement level. Players from another team's squad keep their current price and value and are flagged.",
        "Keeper, bowler and top-seven definitions come from the reviewed list and 2023-26 usage; the check mirrors the best-XII search, not the official playing conditions.",
    ],
)
def xi_odds(f, team: str = TEAM_NAMES[5], players=None, impact=None, value_basis: str = T.DEFAULT_BASIS) -> pd.DataFrame:
    if f.competition not in (None, "ipl"):
        raise ValueError("The XI odds tool covers the IPL only (competition=ipl)")
    r = evaluate_xi(_one(f.team or team), players or [], impact or [], value_basis)
    rows = []
    for k, label in (("you", "Your XI" if r["custom"] else "Best XII"), ("best", "Tool's best XII")):
        x = r[k]
        rows.append({
            "xi": label, "team": r["team"], "xii_value": round(x["value"], 2), "value_lo": round(x["range"][0], 2),
            "value_hi": round(x["range"][1], 2),
            **{f"{m}_pct": round(100 * x[m][0], 1) for m in ("win", "playoff", "title")},
            **{f"{m}_pct_{e}": round(100 * x[m][i], 1) for m in ("win", "playoff", "title") for i, e in ((1, "lo"), (2, "hi"))},
            "rules_passed": sum(q["ok"] for q in x["rules"]),
            "players": ", ".join(q["name"] for q in x["rows"]),
        })  # fmt: skip
    df = pd.DataFrame(rows)
    df.attrs["card"] = r
    return df
