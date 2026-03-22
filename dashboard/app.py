"""Streamlit dashboard — Cricket Analytics Platform.

Run with:  streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of where streamlit is launched from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(
    page_title="Cricket Analytics",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Register all modules
import modules.basic           # noqa: F401
import modules.intermediate    # noqa: F401

from modules.base import list_modules, get_module, ModuleParams
from src.cricket_analytics.db import query


# ── Cached lookups ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _all_players() -> list[str]:
    try:
        df = query("""
            SELECT DISTINCT batter AS name FROM deliveries WHERE batter IS NOT NULL
            UNION
            SELECT DISTINCT bowler AS name FROM deliveries WHERE bowler IS NOT NULL
            ORDER BY name
        """)
        return df["name"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _all_venues() -> list[str]:
    try:
        df = query("SELECT DISTINCT venue FROM matches WHERE venue IS NOT NULL ORDER BY venue")
        return df["venue"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _all_teams() -> list[str]:
    try:
        df = query("""
            SELECT DISTINCT team1 AS team FROM matches WHERE team1 IS NOT NULL
            UNION
            SELECT DISTINCT team2 AS team FROM matches WHERE team2 IS NOT NULL
            ORDER BY team
        """)
        return df["team"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _all_seasons() -> list[str]:
    try:
        df = query("SELECT DISTINCT season FROM matches WHERE season IS NOT NULL ORDER BY season DESC")
        return df["season"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _db_overview() -> dict:
    try:
        matches   = query("SELECT COUNT(*) AS n FROM matches")["n"].iloc[0]
        delivs    = query("SELECT COUNT(*) AS n FROM deliveries")["n"].iloc[0]
        players   = query("SELECT COUNT(DISTINCT batter) AS n FROM deliveries")["n"].iloc[0]
        formats   = query("SELECT DISTINCT format FROM matches WHERE format IS NOT NULL ORDER BY format")
        return {
            "matches": int(matches),
            "deliveries": int(delivs),
            "players": int(players),
            "formats": formats["format"].tolist(),
        }
    except Exception:
        return {"matches": 0, "deliveries": 0, "players": 0, "formats": []}


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar(modules_by_cat: dict) -> tuple[str, ModuleParams, dict]:
    """Render sidebar and return (selected_module_id, params, extra_opts)."""

    st.sidebar.markdown("## 🏏 Cricket Analytics")
    st.sidebar.divider()

    # Module selector grouped by category
    category_labels = {"basic": "📊 Basic", "intermediate": "⚡ Intermediate", "advanced": "🤖 Advanced"}
    all_modules = list_modules()

    options = []
    for cat, label in category_labels.items():
        cat_modules = [m for m in all_modules if m["category"] == cat]
        if cat_modules:
            options.append(f"── {label} ──")
            for m in cat_modules:
                options.append(f"  {m['id']} — {m['name']}")

    # Default to first real module
    real_options = [o for o in options if not o.startswith("──")]

    selected_label = st.sidebar.selectbox(
        "Analysis Module",
        options,
        format_func=lambda x: x,
        index=options.index(real_options[0]) if real_options else 0,
    )

    # Skip separators
    if selected_label.startswith("──"):
        selected_label = real_options[0]

    module_id = selected_label.strip().split(" — ")[0].strip()

    try:
        mod = get_module(module_id)
        supported = mod.supported_filters
    except Exception:
        supported = set()

    st.sidebar.divider()
    st.sidebar.markdown("### Filters")

    players = _all_players()
    venues  = _all_venues()
    teams   = _all_teams()
    seasons = _all_seasons()

    player, player2, team, season, fmt, venue, phase = (None,) * 7
    extra = {}

    # Format (shown for most modules)
    if "format" in supported:
        overview = _db_overview()
        available_formats = ["All"] + overview.get("formats", ["T20", "IPL", "ODI", "Test"])
        fmt = st.sidebar.selectbox("Format", available_formats, index=0)
        if fmt == "All":
            fmt = None

    # Player autocomplete
    if "player" in supported:
        label = "Batter" if module_id == "B4" else "Player"
        player_opts = ["— All Players —"] + players
        sel = st.sidebar.selectbox(
            label,
            player_opts,
            index=0,
            help="Start typing to search",
        )
        player = None if sel == "— All Players —" else sel

    # Player 2 (Head-to-Head only)
    if "player2" in supported:
        player2_opts = ["— All Bowlers —"] + players
        sel2 = st.sidebar.selectbox(
            "Bowler",
            player2_opts,
            index=0,
            help="Start typing to search",
        )
        player2 = None if sel2 == "— All Bowlers —" else sel2

    # Team autocomplete
    if "team" in supported:
        team_opts = ["— All Teams —"] + teams
        sel_t = st.sidebar.selectbox("Team", team_opts, index=0)
        team = None if sel_t == "— All Teams —" else sel_t

    # Season
    if "season" in supported:
        season_opts = ["— All Seasons —"] + seasons
        sel_s = st.sidebar.selectbox("Season", season_opts, index=0)
        season = None if sel_s == "— All Seasons —" else sel_s

    # Venue autocomplete
    if "venue" in supported:
        venue_opts = ["— All Venues —"] + venues
        sel_v = st.sidebar.selectbox("Venue", venue_opts, index=0, help="Start typing to search")
        venue = None if sel_v == "— All Venues —" else sel_v

    # Phase (B2, I1)
    if "phase" in supported:
        phase_opts = {"None": None, "Powerplay (0–5)": "powerplay",
                      "Middle (6–14)": "middle", "Death (15–19)": "death"}
        sel_ph = st.sidebar.selectbox("Phase", list(phase_opts.keys()), index=0)
        phase = phase_opts[sel_ph]

    # Module-specific extra options
    if module_id == "B5":
        cap = st.sidebar.selectbox(
            "Leaderboard",
            {"🟠 Orange Cap (Runs)": "orange", "🟣 Purple Cap (Wickets)": "purple",
             "⚡ Strike Rate": "sr", "💰 Economy": "economy"},
        )
        extra["cap"] = {
            "🟠 Orange Cap (Runs)": "orange",
            "🟣 Purple Cap (Wickets)": "purple",
            "⚡ Strike Rate": "sr",
            "💰 Economy": "economy",
        }.get(cap, "orange")

    st.sidebar.divider()
    run_clicked = st.sidebar.button("▶  Run Analysis", type="primary", use_container_width=True)

    params = ModuleParams(
        player=player,
        player2=player2,
        team=team,
        season=season,
        format=fmt,
        venue=venue,
        phase=phase,
        extra=extra,
    )

    return module_id, params, run_clicked


# ── Results renderer ──────────────────────────────────────────────────────────

def _render_results(module_id: str, params: ModuleParams):
    mod = get_module(module_id)

    with st.spinner(f"Running {mod.module_id}: {mod.module_name}…"):
        df = mod.run(params)
        tabs_data = mod.run_tabs(params)  # may be None

    if df.empty:
        st.warning("No results found for the selected filters. Try broadening your search.")
        return

    # ── Main results ──────────────────────────────────────────────────────
    st.subheader(f"📋 {mod.module_name}")

    if tabs_data:
        # Multi-tab layout (e.g. B6 Venue Analysis)
        tab_labels = ["📊 Overview"] + list(tabs_data.keys())
        tab_objects = st.tabs(tab_labels)

        with tab_objects[0]:
            _show_df_and_plot(df, mod, params, key="main")

        for i, (tab_name, tab_df) in enumerate(tabs_data.items(), start=1):
            with tab_objects[i]:
                if tab_df is not None and not tab_df.empty:
                    st.dataframe(tab_df, use_container_width=True, hide_index=True)
                    _csv_download(tab_df, f"{module_id}_{tab_name}.csv")
                else:
                    st.info("No data for this view with the current filters.")
    else:
        _show_df_and_plot(df, mod, params, key="main")


def _show_df_and_plot(df, mod, params, key=""):
    st.dataframe(df, use_container_width=True, hide_index=True)
    _csv_download(df, f"{mod.module_id}_results.csv")

    try:
        fig = mod.plot(df, params)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key=f"plot_{key}")
    except NotImplementedError:
        pass
    except Exception as e:
        st.caption(f"Chart unavailable: {e}")


def _csv_download(df, filename: str):
    st.download_button(
        "⬇ Download CSV",
        df.to_csv(index=False),
        file_name=filename,
        mime="text/csv",
    )


# ── DB overview metrics ───────────────────────────────────────────────────────

def _render_overview():
    st.divider()
    ov = _db_overview()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Matches in DB",    f"{ov['matches']:,}")
    col2.metric("Balls (deliveries)", f"{ov['deliveries']:,}")
    col3.metric("Unique Players",   f"{ov['players']:,}")
    col4.metric("Formats loaded",   ", ".join(ov["formats"]) or "None")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Page header
    st.markdown(
        "<h1 style='margin-bottom:0'>🏏 Cricket Analytics Platform</h1>"
        "<p style='color:gray;margin-top:4px'>IPL · T20I · ODI · Test — powered by Cricsheet</p>",
        unsafe_allow_html=True,
    )

    all_mods = list_modules()
    if not all_mods:
        st.error("No modules registered. Check module imports.")
        return

    modules_by_cat = {}
    for m in all_mods:
        modules_by_cat.setdefault(m["category"], []).append(m)

    module_id, params, run_clicked = _render_sidebar(modules_by_cat)

    # Persist results across sidebar interactions
    if run_clicked:
        st.session_state["last_module_id"] = module_id
        st.session_state["last_params"] = params
        st.session_state["has_results"] = True

    if st.session_state.get("has_results"):
        _render_results(
            st.session_state["last_module_id"],
            st.session_state["last_params"],
        )
    else:
        # Welcome screen
        st.markdown("### Select a module from the sidebar and click **▶ Run Analysis**")
        with st.expander("📖 Available Modules", expanded=True):
            cols = st.columns(2)
            for i, (cat, mods) in enumerate(modules_by_cat.items()):
                cat_emoji = {"basic": "📊", "intermediate": "⚡", "advanced": "🤖"}.get(cat, "")
                with cols[i % 2]:
                    st.markdown(f"**{cat_emoji} {cat.title()}**")
                    for m in mods:
                        st.markdown(f"- `{m['id']}` {m['name']}")

    _render_overview()


if __name__ == "__main__":
    main()
