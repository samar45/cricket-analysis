"""Matchup predictor: expected runs and wicket chance per ball for a batter against a bowler or bowling type."""

import pandas as pd

from ..models import matchup_model as M
from ..registry import ParamSpec, module, std
from ..sql.attributes import BOWL_TYPES
from ..sql.filters import Filters
from ..sql.fragments import PHASES

TYPE_CHOICES = ("any", "pace", "spin", *BOWL_TYPES)


def _pct(x: float) -> float:
    return round(100 * float(x), 1)


def _card(fit, vocab, batter, bowler, bowl_type, phase, wd, inn, rr) -> dict:
    r = M.predict(fit, vocab, batter, bowler, bowl_type, phase, wd, inn, rr)
    P, L, T, ev = r["P"], r["P_league"], r["P_type"], r["evidence"]
    er, el, et = (float(fit.exp_runs(x[None])[0]) for x in (P, L, T))
    has_type = r["type"] >= 0 or r["kind"] >= 0
    if bowl_type:
        src, label = "asked", bowl_type
    elif bowler:
        src, label = (
            ("reviewed list", BOWL_TYPES[r["type"]]) if r["type"] >= 0 else ("unknown", "unknown")
        )
    else:
        src, label = "none", "typical bowler"
    return {
        "batter": batter,
        "bowler": bowler,
        "bowl_type": label,
        "bowl_type_source": src,
        "phase": phase or "all",
        "wickets_down": wd or "any",
        "innings": inn or "any",
        "required_rate": rr or "any",
        "exp_runs_per_ball": round(er, 3),
        "exp_runs_per_6": round(er * 6, 2),
        "strike_rate": round(er * 100, 1),
        "p_out": round(float(P[6]), 4),
        "balls_per_dismissal": round(1 / float(P[6]), 1),
        "p_dot": round(float(P[0]), 4),
        "p_1": round(float(P[1]), 4),
        "p_2": round(float(P[2]), 4),
        "p_3": round(float(P[3]), 4),
        "p_4": round(float(P[4]), 4),
        "p_6": round(float(P[5]), 4),
        "dot_pct": _pct(P[0]),
        "four_pct": _pct(P[4]),
        "six_pct": _pct(P[5]),
        "out_pct": _pct(P[6]),
        "league_exp_runs_per_6": round(el * 6, 2),
        "league_out_pct": _pct(L[6]),
        "vs_typical_runs_per_6": round((er - el) * 6, 2),
        "vs_typical_out_x": round(float(P[6] / L[6]), 2),
        "typical_vs_type_runs_per_6": round(et * 6, 2) if has_type else None,
        "league_dot_pct": _pct(L[0]),
        "league_four_pct": _pct(L[4]),
        "league_six_pct": _pct(L[5]),
        "league_balls": ev["league_balls"],
        "batter_balls": ev.get("bat", 0),
        "batter_phase_balls": ev.get("bat_phase"),
        "batter_kind_balls": ev.get("bat_kind", 0),
        "batter_type_balls": ev.get("bat_type", 0),
        "bowler_balls": ev.get("bowl", 0),
        "pair_balls": ev.get("pair", 0),
        "raw_level": ev.get("raw_level"),
        "raw_balls": ev.get("raw_balls"),
        "raw_runs_per_ball": round(ev["raw_runs_per_ball"], 3)
        if "raw_runs_per_ball" in ev
        else None,
        "raw_out_pct": round(ev["raw_out_pct"], 1) if "raw_out_pct" in ev else None,
        "confidence": M.confidence(ev, bowler, has_type),
    }


@module(
    id="matchup_predict",
    title="Matchup predictor (batter v bowler / bowling type)",
    category="experimental",
    description="What happens per ball when a batter faces a bowler (or a bowling type) in a phase and match state: expected "
    "runs, chance of a wicket, dot / 4 / 6 chances. Built in layers from the league (phase, wickets down, chase rate) down to "
    "the batter, the bowler, the batter against that bowling type and against that exact bowler; each layer is pulled toward "
    "the one before it, the less data the harder (weights fitted on past seasons). view=grid gives the batter against every "
    "bowling type in every phase. Bowling type and batting hand come only from the hand-kept list; an unlisted bowler has no type layer.",
    params=[
        ParamSpec(
            "player",
            "player",
            required=True,
            help="The batter, exact name as in the data (use resolve first)",
        ),
        ParamSpec(
            "player2",
            "player2",
            help="The bowler (his type comes from the hand-kept list). Do not combine with bowl_type",
        ),
        ParamSpec(
            "bowl_type",
            "choice",
            default="any",
            choices=TYPE_CHOICES,
            help="Face a bowling type instead of one bowler: pace, spin or a finer type",
        ),
        *std("phase", "competition", "season", super_overs=False),
        ParamSpec(
            "wickets_down",
            "choice",
            default="any",
            choices=("any", *M.WK_BANDS),
            help="Wickets down when the ball is bowled",
        ),
        ParamSpec(
            "innings",
            "choice",
            default="any",
            choices=("any", "first", "chase"),
            help="First innings, or the second innings (a chase)",
        ),
        ParamSpec(
            "required_rate",
            "choice",
            default="any",
            choices=("any", *M.RR_BANDS),
            help="Chase only: runs per over still needed (low <8, mid 8-11, high 11+)",
        ),
        ParamSpec(
            "view",
            "choice",
            default="card",
            choices=("card", "grid"),
            help="card = one matchup; grid = the batter against every bowling type in every phase",
        ),
    ],
    caveats=[
        "player = the batter, player2 = the bowler. A prediction, not a record: each number is the model's per-ball probability, shrunk toward the league when the batter, type or pair has few balls. The evidence columns say how many balls stand behind each layer; confidence is strong / medium / thin from those.",
        "Default competition is the IPL (competition=None means IPL here). The shrinkage weights were fitted on IPL balls up to 2024; other competitions reuse them with their own data, which is untested.",
        "Out-of-sample check (fit to 2024, test on IPL 2025-26): the gain over the league average is small (about 0.9% in log loss), most of it from the batter's own level and the match state. The bowling-type and head-to-head layers add very little. See docs/VALUE_step4.md.",
        "Bowling type and batting hand come only from the hand-kept list (player_overrides.csv). A bowler without a type gets no type layers (not guessed).",
        "p_out = the striker is dismissed (any way, run outs included). Dot = no runs off the bat and no wicket (a leg-bye ball counts as a dot for the batter). Wides are not balls faced. Super overs are left out.",
        "The raw_* columns are the plain counts of the most specific group with data (head-to-head, else batter v type, else v kind, else the batter), all phases and states pooled, so they will not match the prediction for a single phase.",
        "Phase = all weights the three phases by how this batter really faces them; wickets_down / innings = any weights by the league mix in the latest era. IPL 2023 onward is its own era (scoring jumped).",
        "No line, length or field data exists in the source, so there is no wagon-wheel or pitch-map part to this.",
    ],
)
def matchup_predict(
    f: Filters,
    player2: str | None = None,
    bowl_type: str = "any",
    wickets_down: str = "any",
    innings: str = "any",
    required_rate: str = "any",
    view: str = "card",
) -> pd.DataFrame:
    batter, bowler = f.player, player2
    if bowler and bowl_type != "any":
        raise ValueError("give a bowler or a bowl_type, not both")
    if required_rate != "any" and innings != "chase":
        raise ValueError("required_rate only applies with innings='chase'")
    fit, vocab = M.get_fit(f)
    for who, name in (("batter", batter), ("bowler", bowler)):
        if name and vocab.id(name) < 0:
            raise ValueError(
                f"{who} {name!r} has no balls in these filters (check the spelling with resolve)"
            )
    wd, inn, rr = (None if v == "any" else v for v in (wickets_down, innings, required_rate))
    bt = None if bowl_type == "any" else bowl_type
    if view == "grid":
        return pd.DataFrame(
            [
                _card(fit, vocab, batter, None, t, ph, wd, inn, rr)
                for t in BOWL_TYPES
                for ph in (*PHASES, None)
            ]
        )
    return pd.DataFrame([_card(fit, vocab, batter, bowler, bt, f.phase, wd, inn, rr)])
