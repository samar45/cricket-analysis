"""Cricket analytics dashboard. Pages and widgets are generated from the module registry:
a new file in src/cricket_analytics/analysis/ (plus optional viz/<id>.py) shows up here with no edits.

Run: .venv\\Scripts\\streamlit.exe run dashboard/app.py
"""

import importlib

import streamlit as st
import ui

from cricket_analytics import competitions, registry

st.set_page_config(page_title="Cricket Analytics", page_icon="🏏", layout="wide")


def guarded(page):
    """The one error boundary: ValueError = fix your input (info); anything else shows the real exception."""
    def wrapper():
        try:
            page()
        except ValueError as e:   # bad or missing user input (e.g. matchup with no player): a hint, not a failure
            st.warning(f"Check your filters: {e}")
        except Exception as e:  # noqa: BLE001
            st.error("This filter combination couldn't be run. Try removing one filter at a time; "
                     "if it keeps failing, it's a bug worth reporting.")
            with st.expander("Technical details"):
                st.code(f"{type(e).__name__}: {e}")
    return wrapper


@guarded
def overview():
    info = ui.data_info()
    st.title("Cricket analytics")
    st.caption(f"Ball-by-ball data from {info['source']}. Database updated {info['db_modified']}.")
    comps = info["competitions"]
    for start in range(0, len(comps), 3):   # rows of 3 fixed-height cards, so the grid is even
        for col, c in zip(st.columns(3), comps[start:start + 3]):
            with col, st.container(border=True, height=135):   # plain text, not st.metric: it cuts off in narrow cards
                st.markdown(f"**{ui.comp_label(c['competition'])}**")
                st.markdown(f"##### {c['matches']:,} matches")
                st.caption(f"{c['earliest']} to {c['latest']}")

    st.subheader("Leaders")
    keys = [c["competition"] for c in info["competitions"] if c["competition"] in competitions.COMPETITIONS]
    a, b = st.columns(2)
    with a:
        comp = ui.select("ov_comp", "Competition", keys, none_label=ui.comp_label(None), format_func=ui.comp_label,
                         index=keys.index("ipl") + 1 if "ipl" in keys else 0)
    with b:
        season = ui.select("ov_season", "Season", ui.choices("season", comp, None), none_label="All seasons")
    params = {"competition": comp, "season": season}
    bat, bowl = ui.run("batting", params), ui.run("bowling", params)
    st.caption(f"Data through {bat.meta['data_through']}")
    left, right = st.columns(2)
    left.markdown("**Most runs**")
    left.dataframe(bat.data.nlargest(5, "total_runs")[["batter", "total_runs", "average", "strike_rate"]],
                   hide_index=True, width="stretch")
    right.markdown("**Most wickets**")
    right.dataframe(bowl.data.nlargest(5, "wickets")[["bowler", "wickets", "economy", "average"]],
                    hide_index=True, width="stretch")


def _figure(mod_id: str, result):
    name = f"cricket_analytics.viz.{mod_id}"
    try:
        viz = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        return None   # a module without a chart is fine
    return viz.figure(result)


@guarded
def explore():
    mods = registry.all_modules()
    cats = [c for c in registry.CATEGORIES if any(m.category == c for m in mods)]
    cat = st.radio("Category", cats, horizontal=True, key="category", format_func=str.capitalize)
    in_cat = {m.id: m for m in mods if m.category == cat}
    mod = in_cat[ui.select("module", "Module", list(in_cat), format_func=lambda i: in_cat[i].title)]

    st.subheader(mod.title)
    st.write(mod.description)
    if mod.category == "experimental":
        st.warning("Experimental module: treat the numbers as rough. " + (mod.caveats[0] if mod.caveats else ""))
    params = ui.param_form(mod)

    result = ui.run(mod.id, params)
    meta = result.meta
    st.caption(f"{meta['row_count']:,} rows | data through {meta['data_through']} | source: {meta['source']}")
    if result.data.empty:
        chosen = ", ".join(f"{k} = {v}" for k, v in meta["params"].items() if v not in (None, [], False, 0, ""))
        st.warning(f"No data for this combination ({chosen}). For example, the player may not have played "
                   "for that team, at that venue or in those seasons. Remove a filter or lower a minimum.")
    else:
        names = ["Chart", "Table"] + (["Video"] if ui.has_video(mod.id) else [])
        chart_tab, table_tab, *video_tab = st.tabs(names)
        with chart_tab:
            fig = _figure(mod.id, result)
            if fig is None:
                st.caption("This module has no chart yet.")
            else:
                st.plotly_chart(fig, width="stretch", theme=None)   # theme=None: keep our own template
        with table_tab:
            st.dataframe(result.data, hide_index=True, width="stretch")
        for tab in video_tab:
            with tab:
                ui.video_tab(mod.id, result)
        c1, c2, _ = st.columns([1, 1, 4])
        c1.download_button("Download CSV", result.data.to_csv(index=False), f"{mod.id}.csv", "text/csv")
        c2.download_button("Download JSON", result.to_json(indent=2), f"{mod.id}.json", "application/json")
    with st.expander("About this result"):
        st.json({k: meta[k] for k in ("params", "data_through", "source", "db_modified")})
        for c in meta["caveats"]:
            st.markdown(f"- {c}")


def ask_page():
    """Plain-English question -> local Ollama model picks a module -> the same table/chart as Explore."""
    from cricket_analytics import ask as A
    st.title("Ask your cricket data")
    st.caption("A small local model (Ollama) only picks the module and fills its filters. Names are matched in Python and "
               "every number comes from the data. Slow on first use while the model loads.")
    if not A.ollama_up():
        st.warning("Ollama is not running. Start it with `ollama serve`, then reload.")
        return
    q = st.text_input("Question", key="ask_q", placeholder="Kohli's IPL strike rate in 2024")
    if st.button("Ask", type="primary") and q.strip():
        with st.spinner("Thinking..."):
            try:
                st.session_state["ask_out"] = A.ask(q.strip())
            except A.AskError as e:
                st.session_state["ask_out"] = None
                st.error(str(e))
    out = st.session_state.get("ask_out")
    if not out:
        return
    if out["tool_call"]:
        st.markdown(f"**Module:** `{out['tool_call']['name']}`")
        st.json(out["resolved_params"] or out["tool_call"]["arguments"], expanded=False)
    for n in out["notes"]:
        st.caption(n)
    (st.warning if out["status"] != "ok" else st.success)(out["answer"])
    for c in out["clarify"]:   # ambiguous name: let the user pick, then run without the model
        pick = st.radio(f"Which {c['param']} did you mean by '{c['said']}'?", c["candidates"], key=f"ask_pick_{c['param']}")
        if pick and st.button("Use this", key=f"ask_use_{c['param']}"):
            st.session_state["ask_out"] = A.execute(out["question"], out["tool_call"], picks={c["param"]: pick},
                                                    timings=out["timings"])
            st.rerun()
    if out["result"]:
        import pandas as pd
        from cricket_analytics.api import Result
        r = Result(pd.DataFrame(out["result"]["rows"]), out["result"]["meta"])
        chart_tab, table_tab = st.tabs(["Chart", "Table"])
        with chart_tab:
            fig = _figure(r.meta["module"], r)
            st.plotly_chart(fig, width="stretch", theme=None) if fig is not None else st.caption("This module has no chart yet.")
        with table_tab:
            st.dataframe(r.data, hide_index=True, width="stretch")
    st.caption(f"Seconds: {out['timings']}")


with st.sidebar:
    st.header("🏏 Cricket analytics")
    page = st.radio("Page", ["Overview", "Explore", "Ask"], key="page", label_visibility="collapsed")
{"Overview": overview, "Explore": explore, "Ask": guarded(ask_page)}[page]()
