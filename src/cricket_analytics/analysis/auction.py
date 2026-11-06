"""IPL auction price model (what a player is likely to get) and the moneyball market check (WAR per crore by player type)."""

import pandas as pd

from ..models import auction as A
from ..registry import ParamSpec, module, std

GROUPS = {
    "type": "type",
    "role": "role",
    "price_band": "band",
    "auction_kind": "kind",
    "type_and_band": ["type", "band"],
}


def _flag(x):
    return {1.0: "yes", 0.0: "no"}.get(A.tf(pd.Series([x])).iloc[0], "")


def _pool(year: int) -> pd.DataFrame:
    d = A.load_predictions()
    d = d[d.auction_year == year]
    if d.empty:
        raise ValueError(f"No auction data for {year}; years: {list(A.YEARS)}")
    return d


def _predict(year: int, top: int) -> pd.DataFrame:
    d = _pool(year).sort_values(["p50", "p_sold"], ascending=False).head(int(top))
    role = d.role_src.fillna("")
    return pd.DataFrame(
        {
            "player": d.player,
            "role": role.where(role != "", d.role_data),
            "base_cr": d.base_price_cr,
            "overseas": [_flag(x) for x in d.overseas],
            "capped": [_flag(x) for x in d.capped],
            "p_sold": d.p_sold.round(2),
            "p10_cr": d.p10.round(2),
            "p50_cr": d.p50.round(2),
            "p90_cr": d.p90.round(2),
            "sold": d.sold.map({True: "yes", False: "no"}),
            "paid_cr": d.price_cr,
            "team": d.team.fillna(""),
            "prediction": d.pred_kind,
        }
    ).reset_index(drop=True)


def _player(name: str) -> pd.DataFrame:
    d = A.load_predictions()
    low = name.lower()
    hit = d[(d.cricsheet_name.fillna("").str.lower() == low) | (d.player.str.lower() == low)]
    if hit.empty:
        hit = d[d.player.str.lower().str.contains(low, regex=False)]
    if hit.empty:
        raise ValueError(f"{name!r} was not on the block in any IPL auction 2022-2026")
    why = A.contributions_from_json(hit, A.load_model()["final_model"])
    return pd.DataFrame(
        {
            "player": hit.player,
            "auction": hit.auction_year,
            "base_cr": hit.base_price_cr,
            "overseas": [_flag(x) for x in hit.overseas],
            "capped": [_flag(x) for x in hit.capped],
            "last_price_cr": hit.prior_price,
            "recent_war_2y": hit.war2.round(2),
            "batting_value": hit.bat_val.round(3),
            "bowling_value": hit.bowl_val.round(3),
            "t20_balls_before": hit.t20_balls.astype(int),
            "p_sold": hit.p_sold.round(2),
            "p10_cr": hit.p10.round(2),
            "p50_cr": hit.p50.round(2),
            "p90_cr": hit.p90.round(2),
            "sold": hit.sold.map({True: "yes", False: "no"}),
            "paid_cr": hit.price_cr,
            "model_leans_on": [A.lean_text(why.loc[i]) for i in hit.index],
            "prediction": hit.pred_kind,
        }
    ).reset_index(drop=True)


@module(
    id="auction",
    title="IPL auction: predicted price and moneyball market check",
    category="experimental",
    description="view=predict lists the players put on the block in one auction (2022-2026) with the model's chance of being sold and a "
    "10th / 50th / 90th percentile price in crore, next to what really happened. Every row is an out-of-sample prediction made with "
    "information dated before that auction (2025 from a 2022-24 fit, 2026 from a 2022-25 fit, 2022-24 by leaving one auction out). "
    "view=market asks which kinds of buy gave the most wins above replacement (WAR) per 10 crore in the season after the auction, "
    "with bootstrap ranges. view=player shows one player's features and estimates in each auction he was on the block.",
    params=[
        *std("player", "competition", super_overs=False),
        ParamSpec(
            "view",
            "choice",
            default="predict",
            choices=("predict", "market", "player"),
            help="predict = one auction's pool; market = WAR per crore by buy type; player = one player (needs the player filter)",
        ),
        ParamSpec("auction_year", "int", default=2026, help="view=predict: auction year 2022-2026"),
        ParamSpec(
            "top",
            "int",
            default=60,
            help="view=predict: rows to return (highest median price first)",
        ),
        ParamSpec(
            "group_by",
            "choice",
            default="type",
            choices=tuple(GROUPS),
            help="view=market: type = overseas / capped Indian / uncapped Indian",
        ),
        ParamSpec(
            "include_2026",
            "bool",
            default=False,
            help="view=market: also count the 2026 auction",
        ),
    ],
    caveats=[
        "Weak predictor. On the 2026 test the median price is no closer to the real price than 'price = base price' (mean error about 1.9 crore both), and the sold / unsold part has no skill (AUC about 0.5). Read the 10-90 range, not the median.",
        "Only players who were put on the block are modelled; the unsold lists are partial (2025: 293 further rows of unknown status are left out), and a mini auction's real purse left is unknown. No age data. Prices are paid prices, not bids.",
        "Value inputs use our WAR (IPL 2023+ only), other T20 leagues and the domestic SMAT trophy; players without any such data (many uncapped) look like average players with no history.",
        "view=market: WAR is one season of mostly luck (talent explains about 5-10% of the spread); bench players count as 0 WAR for their full price; names that could not be matched to Cricsheet count as 0 WAR. Small groups are flagged.",
        "The 2022 'retained' rows exclude the two new teams' draft picks; retained players have no role listed. Price bands use nominal crore, so a 2025 'over 8 cr' deal is a smaller share of the purse than a 2022 one.",
    ],
)
def auction(
    f,
    view: str = "predict",
    auction_year: int = 2026,
    top: int = 60,
    group_by: str = "type",
    include_2026: bool = False,
) -> pd.DataFrame:
    if f.competition not in (None, "ipl"):
        raise ValueError("The auction model covers the IPL only (competition=ipl)")
    if view == "market":
        yrs = (2022, 2023, 2024, 2025) + ((2026,) if include_2026 else ())
        t = A.market_table(A.load_market(), GROUPS[group_by], years=yrs)
        return t.rename(columns={"group": group_by})
    if view == "player":
        if not f.player:
            raise ValueError("view=player needs the player filter")
        return _player(f.player)
    return _predict(int(auction_year), top)
