"""The one generic renderer for a registry module: title, filter form, Run gate, then chart / table / video / downloads.

Used by Explore, the IPL market page and (via `figure`) the Ask page. `HIDDEN_FROM_EXPLORE` is the single place that
decides which modules Explore skips because another page already hosts them (CLI / API / Ask still see every module).
"""

import importlib

import streamlit as st
import ui

# modules that live on a dedicated page; Explore does not list them
ON_MARKET_PAGE = {"trade", "xi_odds", "auction", "scarcity"}
ON_PLAYER_PAGE = {"player_card", "player_worth"}
HIDDEN_FROM_EXPLORE = ON_MARKET_PAGE | ON_PLAYER_PAGE
LEAN = {"trade", "xi_odds"}  # numbers only: no prose; caveats sit in one "Method" expander at the bottom


def figure(mod_id: str, result):
    name = f"cricket_analytics.viz.{mod_id}"
    try:
        viz = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        return None  # a module without a chart is fine
    return viz.figure(result)


def card_html(mod_id: str, result) -> str | None:
    try:
        viz = importlib.import_module(f"cricket_analytics.viz.{mod_id}")
    except ModuleNotFoundError:
        return None
    return viz.html(result) if hasattr(viz, "html") else None


def module_view(mod, *, scope: str | None = None, fixed: dict | None = None, skip: tuple = (), extra=None) -> None:
    """Form + Run gate + result for one module. `fixed` params are always sent and their widgets (plus `skip`) hidden;
    `scope` names the Run button / result container (default: the module id). `extra(params, result)` draws more under the result."""
    scope = scope or mod.id
    fixed = fixed or {}
    lean = mod.id in LEAN
    if not lean:
        st.write(mod.description)
    if mod.category == "experimental" and not lean:
        st.warning(
            "Experimental module: treat the numbers as rough. "
            + (mod.caveats[0] if mod.caveats else "")
        )
    params = ui.param_form(mod, skip=(*fixed, *skip))
    params = ui.gate(scope, {**params, **fixed})
    if params is None:
        return
    with st.container(key=f"res_{scope}"):
        _result(mod, params, lean, extra)


def _result(mod, params, lean, extra=None):
    result = ui.run(mod.id, params)
    meta = result.meta
    if not lean:
        st.caption(
            f"{meta['row_count']:,} rows | data through {meta['data_through']} | source: {meta['source']}"
        )
    if result.data.empty:
        chosen = ", ".join(
            f"{k} = {v}" for k, v in meta["params"].items() if v not in (None, [], False, 0, "")
        )
        st.warning(
            f"No data for this combination ({chosen}). For example, the player may not have played "
            "for that team, at that venue or in those seasons. Remove a filter or lower a minimum."
        )
    else:
        names = ["Chart", "Table"] + (["Video"] if ui.has_video(mod.id) else [])
        chart_tab, table_tab, *video_tab = st.tabs(names)
        with chart_tab:
            card = card_html(mod.id, result)  # a module's own HTML card, if its viz module has html()
            fig = None if card else figure(mod.id, result)  # the card replaces the plain chart
            if card:
                st.html(card)
                if lean:
                    viz = importlib.import_module(f"cricket_analytics.viz.{mod.id}")
                    for title, body in viz.details(result):
                        with st.expander(title):
                            st.html(body)
            elif fig is None:
                st.caption("This module has no chart yet.")
            else:
                st.plotly_chart(fig, width="stretch", theme=None)  # theme=None: keep our own template
        with table_tab:
            st.dataframe(result.data, hide_index=True, width="stretch")
        for tab in video_tab:
            with tab:
                ui.video_tab(mod.id, result)
        c1, c2, _ = st.columns([1, 1, 4])
        c1.download_button(
            "Download CSV", result.data.to_csv(index=False), f"{mod.id}.csv", "text/csv"
        )
        c2.download_button(
            "Download JSON", result.to_json(indent=2), f"{mod.id}.json", "application/json"
        )
    if extra and not result.data.empty:
        extra(params, result)
    with st.expander("Method" if lean else "About this result"):
        if lean:
            st.caption(importlib.import_module(f"cricket_analytics.viz.{mod.id}").method_note(result))
        else:
            st.json({k: meta[k] for k in ("params", "data_through", "source", "db_modified")})
        for c in meta["caveats"]:
            st.markdown(f"- {c}")
