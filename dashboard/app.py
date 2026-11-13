"""Cricket analytics dashboard. Pages and widgets are generated from the module registry:
a new file in src/cricket_analytics/analysis/ (plus optional viz/<id>.py) shows up here with no edits.

Run: .venv\\Scripts\\streamlit.exe run dashboard/app.py
"""

import auction_room
import health
import match_predictor
import module_view
import player_page
import streamlit as st
import ui

from cricket_analytics import applog, competitions, registry

st.set_page_config(page_title="Cricket Analytics", page_icon="🏏", layout="wide")


def guarded(page):
    """The one error boundary: ValueError = fix your input (info); anything else shows the real exception."""

    def wrapper():
        try:
            page()
        except (
            ValueError
        ) as e:  # bad or missing user input (e.g. matchup with no player): a hint, not a failure
            st.warning(f"Check your filters: {e}")
        except Exception as e:  # noqa: BLE001
            eid = applog.log_error(
                f"dashboard:{page.__name__}",
                e,
                module=st.session_state.get("module"),
                params={k: v for k, v in st.session_state.items() if k.startswith("p_")},
            )
            st.error(
                "This filter combination couldn't be run. Try removing one filter at a time; "
                f"if it keeps failing, it's a bug worth reporting (error id {eid})."
            )
            with st.expander("Technical details"):
                st.code(f"{type(e).__name__}: {e}")

    return wrapper


@guarded
def overview():
    info = ui.data_info()
    st.title("Cricket analytics")
    st.caption(f"Ball-by-ball data from {info['source']}. Database updated {info['db_modified']}.")
    comps = info["competitions"]
    for start in range(0, len(comps), 3):  # rows of 3 fixed-height cards, so the grid is even
        for col, c in zip(st.columns(3), comps[start : start + 3]):
            with (
                col,
                st.container(border=True, height=135),
            ):  # plain text, not st.metric: it cuts off in narrow cards
                st.markdown(f"**{ui.comp_label(c['competition'])}**")
                st.markdown(f"##### {c['matches']:,} matches")
                st.caption(f"{c['earliest']} to {c['latest']}")

    st.subheader("Leaders")
    keys = [
        c["competition"]
        for c in info["competitions"]
        if c["competition"] in competitions.COMPETITIONS
    ]
    a, b = st.columns(2)
    with a:
        comp = ui.select(
            "ov_comp",
            "Competition",
            keys,
            none_label=ui.comp_label(None),
            format_func=ui.comp_label,
            index=keys.index("ipl") + 1 if "ipl" in keys else 0,
        )
    with b:
        season = ui.select(
            "ov_season", "Season", ui.choices("season", comp, None), none_label="All seasons"
        )
    params = {"competition": comp, "season": season}
    params = ui.gate("overview", params, "Show leaders")
    if params is None:
        return
    with st.container(key="res_overview"):
        _leaders(params)


def _leaders(params):
    bat, bowl = ui.run("batting", params), ui.run("bowling", params)
    st.caption(f"Data through {bat.meta['data_through']}")
    left, right = st.columns(2)
    left.markdown("**Most runs**")
    left.dataframe(
        bat.data.nlargest(5, "total_runs")[["batter", "total_runs", "average", "strike_rate"]],
        hide_index=True,
        width="stretch",
    )
    right.markdown("**Most wickets**")
    right.dataframe(
        bowl.data.nlargest(5, "wickets")[["bowler", "wickets", "economy", "average"]],
        hide_index=True,
        width="stretch",
    )


@guarded
def explore():
    mods = [m for m in registry.all_modules() if m.id not in module_view.HIDDEN_FROM_EXPLORE]
    cats = [c for c in registry.CATEGORIES if any(m.category == c for m in mods)]
    q = st.text_input("Search modules", key="module_search", placeholder="e.g. death, matchup, venue").strip().lower()
    cat = st.radio("Category", cats, horizontal=True, key="category", format_func=str.capitalize)
    in_cat = {m.id: m for m in mods if (q in f"{m.title} {m.id}".lower() if q else m.category == cat)}
    if not in_cat:
        st.info("No module matches that search.")
        return
    short = lambda i: in_cat[i].title.split(" (")[0]  # noqa: E731  # dropdown label only; the description keeps the detail
    mod = in_cat[ui.select("module", "Module", list(in_cat), format_func=short)]
    st.subheader(mod.title)
    module_view.module_view(mod)


def ask_page():
    """Plain-English question -> local Ollama model picks a module -> the same table/chart as Explore."""
    from cricket_analytics import ask as A

    st.title("Ask your cricket data")
    st.caption(
        "A small local model (Ollama) only picks the module and fills its filters. Names are matched in Python and "
        "every number comes from the data. Slow on first use while the model loads."
    )
    if A.ollama_up():
        _ask_body(A)
    else:
        st.warning("Ollama is not running. Start it with `ollama serve`, then reload.")
    _ask_log_table()


def _feedback(out: dict):
    """Thumbs up/down on an answer; both are appended to logs/ask.jsonl next to the ask itself."""
    aid = out.get("id")
    if not aid:
        return
    up, _ = st.columns([1, 8])
    if up.button("👍", key=f"fb_up_{aid}", help="This answer was right"):
        applog.log_feedback(aid, "up")
        st.toast("Thanks, logged.")
    with st.expander("👎 Wrong answer? Tell me what was wrong"):
        with st.form(f"fb_form_{aid}", clear_on_submit=True):
            comment = st.text_input("What was wrong?")
            mods = [None] + [m.id for m in registry.all_modules()]
            exp = st.selectbox(
                "Which module should it have been?",
                mods,
                format_func=lambda m: "(not sure)" if m is None else m,
            )
            if st.form_submit_button("👎 Send"):
                applog.log_feedback(aid, "down", comment, exp)
                st.success("Logged. Thanks.")


def _ask_log_table():
    import pandas as pd

    with st.expander("Ask log (last 20)"):
        rows = applog.read_asks(20)
        if not rows:
            st.caption("No questions logged yet.")
            return
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "time": a["ts"],
                        "question": a["question"],
                        "module": (a.get("tool_call") or {}).get("name"),
                        "status": a["status"],
                        "rating": a["rating"],
                        "error id": a.get("error_id"),
                    }
                    for a in reversed(rows)
                ]
            ),
            hide_index=True,
            width="stretch",
        )


def _ask_body(A):
    q = st.text_input("Question", key="ask_q", placeholder="Kohli's IPL strike rate in 2024")
    if st.button("Ask", type="primary") and q.strip():
        with st.spinner("Thinking..."):
            try:
                st.session_state["ask_out"] = A.ask(q.strip())
            except A.AskError as e:
                st.session_state["ask_out"] = None
                st.error(f"{e} (error id {getattr(e, 'error_id', '-')})")
    out = st.session_state.get("ask_out")
    if not out:
        return
    if out["tool_call"]:
        st.markdown(f"**Module:** `{out['tool_call']['name']}`")
        st.json(out["resolved_params"] or out["tool_call"]["arguments"], expanded=False)
    for n in out["notes"]:
        st.caption(n)
    (st.warning if out["status"] != "ok" else st.success)(out["answer"])
    for c in out["clarify"]:  # ambiguous name: let the user pick, then run without the model
        pick = st.radio(
            f"Which {c['param']} did you mean by '{c['said']}'?",
            c["candidates"],
            key=f"ask_pick_{c['param']}",
        )
        if pick and st.button("Use this", key=f"ask_use_{c['param']}"):
            st.session_state["ask_out"] = {
                **A.execute(
                    out["question"],
                    out["tool_call"],
                    picks={c["param"]: pick},
                    timings=out["timings"],
                ),
                "id": out.get("id"),
            }
            st.rerun()
    if out["result"]:
        import pandas as pd
        from cricket_analytics.api import Result

        r = Result(pd.DataFrame(out["result"]["rows"]), out["result"]["meta"])
        chart_tab, table_tab = st.tabs(["Chart", "Table"])
        with chart_tab:
            fig = module_view.figure(r.meta["module"], r)
            if (
                fig is None
            ):  # a statement, not a one-line `a if c else b`: Streamlit would print that expression's value
                st.caption("This module has no chart yet.")
            else:
                st.plotly_chart(fig, width="stretch", theme=None)
        with table_tab:
            st.dataframe(r.data, hide_index=True, width="stretch")
    st.caption(
        f"Seconds: {out['timings']}"
        + (f" | error id {out['error_id']}" if out.get("error_id") else "")
    )
    _feedback(out)


with st.sidebar:
    st.header("🏏 Cricket analytics")
    page = st.radio(
        "Page",
        ["Overview", "Explore", "Ask", "Player", "IPL market", "Match predictor", "Data health"],
        key="page",
        label_visibility="collapsed",
    )
{
    "Overview": overview,
    "Explore": explore,
    "Ask": guarded(ask_page),
    "Player": guarded(player_page.page),
    "IPL market": guarded(auction_room.page),
    "Match predictor": guarded(match_predictor.page),
    "Data health": guarded(health.page),
}[page]()
