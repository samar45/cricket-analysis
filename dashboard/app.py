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
    """The one error boundary: show the real exception message instead of an empty page."""
    def wrapper():
        try:
            page()
        except Exception as e:  # noqa: BLE001
            st.error(f"{type(e).__name__}: {e}")
    return wrapper


@guarded
def overview():
    info = ui.data_info()
    st.title("Cricket analytics")
    st.caption(f"Ball-by-ball data from {info['source']}. Database updated {info['db_modified']}.")
    cols = st.columns(3)   # plain text, not st.metric: metric values and labels are cut off in narrow cards
    for i, c in enumerate(info["competitions"]):
        with cols[i % 3], st.container(border=True):
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
        st.info("No rows for these filters. Loosen a filter or lower a minimum.")
    else:
        chart_tab, table_tab = st.tabs(["Chart", "Table"])
        with chart_tab:
            fig = _figure(mod.id, result)
            if fig is None:
                st.caption("This module has no chart yet.")
            else:
                st.plotly_chart(fig, width="stretch")
        with table_tab:
            st.dataframe(result.data, hide_index=True, width="stretch")
        c1, c2, _ = st.columns([1, 1, 4])
        c1.download_button("Download CSV", result.data.to_csv(index=False), f"{mod.id}.csv", "text/csv")
        c2.download_button("Download JSON", result.to_json(indent=2), f"{mod.id}.json", "application/json")
    with st.expander("About this result"):
        st.json({k: meta[k] for k in ("params", "data_through", "source", "db_modified")})
        for c in meta["caveats"]:
            st.markdown(f"- {c}")


with st.sidebar:
    st.header("🏏 Cricket analytics")
    page = st.radio("Page", ["Overview", "Explore"], key="page", label_visibility="collapsed")
{"Overview": overview, "Explore": explore}[page]()
