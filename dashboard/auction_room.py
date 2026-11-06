"""Auction Room page: the IPL auction work (needs, scarcity, price ranges, scouting, market check) on one page.

Everything comes from the `scarcity`, `auction` and `war` modules through `ui.run` (so it is cached and has provenance);
this file only lays it out. Each section shows a plain caveat line.
"""

import pandas as pd
import streamlit as st
import ui

from cricket_analytics.models import auction as A
from cricket_analytics.models.war import DATA

SMAT_CSV = DATA / "scouting_preview_smat.csv"


def _show(df: pd.DataFrame) -> None:
    st.dataframe(df, hide_index=True, width="stretch")


def _needs() -> None:
    st.subheader("2027 needs")
    st.warning(
        "PROVISIONAL until the retentions (17 Nov 2026): squads are full today and nothing is released yet. "
        "Supply is assumed from the earlier mini auctions."
    )
    t = ui.run("scarcity", {"view": "team_needs", "year": 2027}).data
    _show(
        t[
            [
                "team",
                "squad_n",
                "open_spots",
                "overseas_open",
                "purse_left_cr",
                "need_total_raw",
                "holes",
            ]
        ]
        .sort_values("need_total_raw", ascending=False)
        .rename(columns={"need_total_raw": "need_score", "holes": "weak or open slots"})
    )
    st.caption(
        "Need = open or weak slots in a team's best XII, weighted by purse left. Roles are guessed from how a player "
        "was used in the last three years, keepers only from the reviewed list."
    )


def _scarce() -> None:
    st.subheader("Scarce roles")
    year = st.radio(
        "Auction", [2027, 2026, 2025, 2024, 2023, 2022], horizontal=True, key="ar_scarce"
    )
    d = ui.run("scarcity", {"view": "auction", "year": year}).data
    _show(d)
    st.info(
        "Honest note: when we tested it, scarcity did NOT raise prices in the 2022-26 auctions "
        "(docs/VALUE_m6.md). Read the index as a description of the room, not as a price forecast."
        + (" 2027 is provisional." if year == 2027 else "")
    )


def _estimator() -> None:
    st.subheader("Price estimator")
    names = sorted(A.load_predictions().player.unique())
    default = names.index("Cameron Green") if "Cameron Green" in names else 0
    who = st.selectbox(
        "Player who has been on the block (2022-2026)", names, index=default, key="ar_player"
    )
    try:
        d = ui.run("auction", {"view": "player", "player": who}).data
    except ValueError as e:
        st.info(str(e))
        return
    show = d[["auction", "base_cr", "overseas", "capped", "last_price_cr", "recent_war_2y", "p_sold", "p10_cr", "p50_cr", "p90_cr", "sold", "paid_cr"]]  # fmt: skip
    _show(show)
    with st.expander("Features the model leans on"):
        _show(
            d[
                [
                    "auction",
                    "batting_value",
                    "bowling_value",
                    "t20_balls_before",
                    "model_leans_on",
                    "prediction",
                ]
            ]
        )
    st.caption(
        "Honest note: the median barely beats 'price = base price' (about 1.9 crore average error both, 2026 test), and "
        "the chance of being sold has almost no skill. Read the 10-90% range. Each row was predicted using only what was "
        "known before that auction. A 2027 pool estimate waits for the retentions."
    )


def _scouting() -> None:
    st.subheader("Uncapped scouting")
    st.warning(
        "Translated estimate, noisy: 150-500 domestic balls per player. A shortlist to look at, not a ranking."
    )
    smat = pd.read_csv(SMAT_CSV)
    smat = smat.assign(
        ipl_squad_2027=smat.ipl_squad_2027.fillna("-"), value_per_100=smat.value_per_100.round(1)
    )[["player", "role", "smat_balls", "value_per_100", "ipl_balls_all", "t20i_balls_all", "ipl_squad_2027"]]  # fmt: skip
    st.markdown(
        "**SMAT (domestic T20) players with under 100 IPL balls**, value in runs above the IPL average per 100 balls"
    )
    _show(smat)
    pool = A.load_predictions()
    pool = pool[
        (pool.auction_year == 2026)
        & (A.tf(pool.overseas).fillna(0) == 0)
        & (A.tf(pool.capped).fillna(0) == 0)
    ]
    pool = pool[pool.ipl_balls < 500].assign(
        value=lambda d: d[["bat_val", "bowl_val"]].max(axis=1).round(3)
    )
    top = pool.sort_values("value", ascending=False).head(15)
    st.markdown(
        "**IPL-light uncapped Indians in the 2026 auction pool** (under 500 IPL balls), shrunk value in wins per standard season"
    )
    _show(
        top[
            [
                "player",
                "ipl_balls",
                "t20_balls",
                "bat_val",
                "bowl_val",
                "value",
                "base_price_cr",
                "price_cr",
                "team",
            ]
        ]
        .round(3)
        .rename(columns={"price_cr": "paid_cr", "t20_balls": "all_t20_balls"})
    )
    st.caption(
        "Both lists are translated or shrunk estimates from small samples. The market check below found no sign that "
        "uncapped Indians as a type were under-priced; the hope is to find individuals, and one season of data is mostly luck."
    )


def _market() -> None:
    st.subheader("Market check")
    st.markdown(
        "**WAR per 10 crore by buy type, auctions 2022-25** (95% range from resampling players)"
    )
    t = ui.run("auction", {"view": "market", "group_by": "type"}).data
    _show(
        t[["type", "players", "crore_spent", "war_total", "war_per_10cr", "lo", "hi", "played_%"]]
    )
    st.markdown(
        "**Against the cheapest alternative** (a base-price buy filling the same roster slot)"
    )
    c = ui.run("auction", {"view": "cheapest"}).data
    _show(c)
    st.markdown("**Share of buys with any IPL ball**, by price band (players in brackets)")
    _show(ui.run("auction", {"view": "played"}).data)
    st.caption(
        "Honest note: no group of buys other than retained and capped Indians is clearly above 0, and uncapped Indians are "
        "not clearly better than the cheapest alternative. One season of WAR per buy is mostly luck; bench players count 0."
    )


def page() -> None:
    st.title("Auction room")
    st.caption(
        "IPL auction work built on our own models. Every section says how far to trust it (docs/VALUE_m4.md, VALUE_m6.md)."
    )
    _needs()
    _scarce()
    _estimator()
    _scouting()
    _market()
