"""Streamlit dashboard — Cricket Analytics Platform.

Run with:  streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(
    page_title="Cricket Analytics",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Register all modules
import modules.basic        # noqa: F401
import modules.intermediate # noqa: F401

from modules.base import list_modules, get_module, ModuleParams
from src.cricket_analytics.db import query
from src.cricket_analytics.leagues import COMPETITIONS, get_sql_filter


# ── Competition-aware cached lookups ──────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _players_for(competition: str) -> list[str]:
    """All player names for the given competition (batter + bowler combined)."""
    try:
        league_sql, league_vals = get_sql_filter(competition, "m")
        where = f"WHERE {league_sql}" if league_sql != "1=1" else ""
        sql = f"""
            SELECT DISTINCT batter AS name
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            {where} AND d.batter IS NOT NULL
            UNION
            SELECT DISTINCT bowler AS name
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            {where} AND d.bowler IS NOT NULL
            ORDER BY name
        """
        # values used twice (batter + bowler union)
        df = query(sql, league_vals + league_vals if league_vals else None)
        return df["name"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _venues_for(competition: str) -> list[str]:
    try:
        league_sql, league_vals = get_sql_filter(competition, "m")
        where = f"WHERE {league_sql}" if league_sql != "1=1" else ""
        sql = f"""
            SELECT DISTINCT venue FROM matches m
            {where} AND venue IS NOT NULL
            ORDER BY venue
        """
        df = query(sql, league_vals or None)
        return df["venue"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _teams_for(competition: str) -> list[str]:
    try:
        league_sql, league_vals = get_sql_filter(competition, "m")
        where = f"WHERE {league_sql}" if league_sql != "1=1" else ""
        sql = f"""
            SELECT DISTINCT team1 AS team FROM matches m {where}
            UNION
            SELECT DISTINCT team2 AS team FROM matches m {where}
            ORDER BY team
        """
        df = query(sql, (league_vals + league_vals) if league_vals else None)
        return df["team"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _seasons_for(competition: str) -> list[str]:
    try:
        league_sql, league_vals = get_sql_filter(competition, "m")
        where = f"WHERE {league_sql}" if league_sql != "1=1" else ""
        sql = f"SELECT DISTINCT season FROM matches m {where} AND season IS NOT NULL ORDER BY season DESC"
        df = query(sql, league_vals or None)
        return df["season"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _db_overview() -> dict:
    try:
        matches  = query("SELECT COUNT(*) AS n FROM matches")["n"].iloc[0]
        delivs   = query("SELECT COUNT(*) AS n FROM deliveries")["n"].iloc[0]
        players  = query("SELECT COUNT(DISTINCT batter) AS n FROM deliveries")["n"].iloc[0]
        fmts_df  = query(
            "SELECT format, COUNT(*) AS n FROM matches WHERE format IS NOT NULL "
            "GROUP BY format ORDER BY n DESC"
        )
        return {
            "matches":    int(matches),
            "deliveries": int(delivs),
            "players":    int(players),
            "formats":    fmts_df.set_index("format")["n"].to_dict(),
        }
    except Exception:
        return {"matches": 0, "deliveries": 0, "players": 0, "formats": {}}


# ── Search-filtered selectbox helper ──────────────────────────────────────────

def _search_select(label: str, options: list[str], key: str,
                   all_label: str = "— All —", max_shown: int = 150) -> str | None:
    """Show a text-search box + selectbox combo.

    The search box narrows the dropdown to matching items so users never
    have to scroll through thousands of names.
    Returns the selected value, or None if '— All —' is chosen.
    """
    search = st.sidebar.text_input(f"🔍 Search {label.lower()}…", key=f"search_{key}")
    if search:
        filtered = [o for o in options if search.lower() in o.lower()]
    else:
        filtered = options

    shown = filtered[:max_shown]
    suffix = f" (showing {max_shown} of {len(filtered)})" if len(filtered) > max_shown else ""
    display_opts = [all_label] + shown

    sel = st.sidebar.selectbox(
        f"{label}{suffix}",
        display_opts,
        key=f"sel_{key}",
    )
    return None if sel == all_label else sel


# ── Sidebar renderer ──────────────────────────────────────────────────────────

def _render_sidebar() -> tuple[str, ModuleParams, bool]:
    st.sidebar.markdown("## 🏏 Cricket Analytics")
    st.sidebar.divider()

    # ── Competition (formerly Format) ─────────────────────────────────────────
    comp_labels = [c.label for c in COMPETITIONS]
    comp_emojis = {c.label: c.emoji for c in COMPETITIONS}
    comp_descs  = {c.label: c.description for c in COMPETITIONS}

    selected_comp = st.sidebar.selectbox(
        "Competition",
        comp_labels,
        format_func=lambda x: f"{comp_emojis[x]} {x}",
        key="competition",
    )
    st.sidebar.caption(comp_descs.get(selected_comp, ""))

    # ── Module selector ───────────────────────────────────────────────────────
    st.sidebar.divider()
    all_mods = list_modules()
    cat_order = ["basic", "intermediate", "advanced"]
    cat_emoji = {"basic": "📊", "intermediate": "⚡", "advanced": "🤖"}

    options: list[str] = []
    for cat in cat_order:
        mods = [m for m in all_mods if m["category"] == cat]
        if mods:
            options.append(f"── {cat_emoji[cat]} {cat.title()} ──")
            for m in mods:
                options.append(f"  {m['id']} — {m['name']}")

    real_opts = [o for o in options if not o.startswith("──")]
    default_idx = options.index(real_opts[0]) if real_opts else 0

    selected_label = st.sidebar.selectbox(
        "Analysis Module",
        options,
        index=default_idx,
        key="module_select",
    )
    if selected_label.startswith("──"):
        selected_label = real_opts[0]

    module_id = selected_label.strip().split(" — ")[0].strip()

    try:
        mod = get_module(module_id)
        supported = mod.supported_filters
    except Exception:
        supported = set()

    # ── Dynamic filters ───────────────────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.markdown("### Filters")

    player = player2 = team = season = venue = phase = None
    extra = {}

    # Load lists filtered to the selected competition (cached)
    all_players = _players_for(selected_comp) if any(
        f in supported for f in ("player", "player2")) else []
    all_venues  = _venues_for(selected_comp)  if "venue"  in supported else []
    all_teams   = _teams_for(selected_comp)   if "team"   in supported else []
    all_seasons = _seasons_for(selected_comp) if "season" in supported else []

    if "player" in supported:
        label = "Batter" if module_id == "B4" else "Player"
        player = _search_select(label, all_players, key="player", all_label="— All Players —")

    if "player2" in supported:
        player2 = _search_select("Bowler", all_players, key="player2",
                                 all_label="— All Bowlers —")

    if "team" in supported:
        team = _search_select("Team", all_teams, key="team",
                              all_label="— All Teams —")

    if "season" in supported and all_seasons:
        sel_s = st.sidebar.selectbox(
            "Season",
            ["— All Seasons —"] + all_seasons,
            key="season",
        )
        season = None if sel_s == "— All Seasons —" else sel_s

    if "venue" in supported:
        venue = _search_select("Venue", all_venues, key="venue",
                               all_label="— All Venues —")

    if "phase" in supported:
        phase_map = {
            "None": None,
            "Powerplay (0–5)": "powerplay",
            "Middle (6–14)":   "middle",
            "Death (15–19)":   "death",
        }
        sel_ph = st.sidebar.selectbox("Phase", list(phase_map), key="phase")
        phase = phase_map[sel_ph]

    # Module-specific extras
    if module_id == "B5":
        cap_map = {
            "🟠 Orange Cap (Runs)":    "orange",
            "🟣 Purple Cap (Wickets)": "purple",
            "⚡ Strike Rate Leaders":  "sr",
            "💰 Economy Leaders":      "economy",
        }
        sel_cap = st.sidebar.selectbox("Leaderboard", list(cap_map), key="cap")
        extra["cap"] = cap_map[sel_cap]

    st.sidebar.divider()
    run_btn = st.sidebar.button("▶  Run Analysis", type="primary",
                                use_container_width=True, key="run_btn")

    params = ModuleParams(
        format=selected_comp,
        player=player,
        player2=player2,
        team=team,
        season=season,
        venue=venue,
        phase=phase,
        extra=extra,
    )
    return module_id, params, run_btn


# ── Results renderer ──────────────────────────────────────────────────────────

def _render_results(module_id: str, params: ModuleParams):
    mod = get_module(module_id)

    with st.spinner(f"Running {mod.module_id}: {mod.module_name}…"):
        df       = mod.run(params)
        tabs_data = mod.run_tabs(params)

    if df.empty:
        st.warning("No data for the selected filters — try a different competition or broader filters.")
        return

    st.subheader(f"📋 {mod.module_name}")

    if tabs_data:
        tab_labels  = ["📊 Overview"] + list(tabs_data.keys())
        tab_objects = st.tabs(tab_labels)
        with tab_objects[0]:
            _show_df_and_plot(df, mod, params, key="main")
        for i, (name, tdf) in enumerate(tabs_data.items(), 1):
            with tab_objects[i]:
                if tdf is not None and not tdf.empty:
                    st.dataframe(tdf, use_container_width=True, hide_index=True)
                    _dl_btn(tdf, f"{module_id}_{name}.csv")
                else:
                    st.info("No data for this view with the current filters.")
    else:
        _show_df_and_plot(df, mod, params, key="main")


def _show_df_and_plot(df, mod, params, key=""):
    st.dataframe(df, use_container_width=True, hide_index=True)
    _dl_btn(df, f"{mod.module_id}_results.csv")
    try:
        fig = mod.plot(df, params)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key=f"plot_{key}")
    except NotImplementedError:
        pass
    except Exception as e:
        st.caption(f"Chart unavailable: {e}")


def _dl_btn(df, filename: str):
    st.download_button("⬇ Download CSV", df.to_csv(index=False),
                       file_name=filename, mime="text/csv")


# ── DB overview bar ───────────────────────────────────────────────────────────

def _render_overview():
    st.divider()
    ov = _db_overview()
    cols = st.columns(4)
    cols[0].metric("Matches",     f"{ov['matches']:,}")
    cols[1].metric("Balls (deliveries)", f"{ov['deliveries']:,}")
    cols[2].metric("Players",     f"{ov['players']:,}")
    fmt_str = "  ·  ".join(
        f"{fmt} ({n:,})" for fmt, n in list(ov["formats"].items())[:5]
    ) or "None loaded"
    cols[3].metric("Formats loaded", fmt_str)

    # Show ingest hint if franchise leagues are missing
    loaded_fmts = set(ov["formats"].keys())
    missing = [c.label for c in COMPETITIONS
               if c.label not in ("T20 International",) and
               c.label.upper() not in loaded_fmts and
               c.cricsheet_key.upper() not in loaded_fmts]
    if missing:
        with st.expander(f"📥 {len(missing)} competition(s) not yet loaded — click to see how"):
            st.markdown("Run these commands to download more data:")
            for c in COMPETITIONS:
                if c.label in missing:
                    st.code(
                        f"python -m src.cricket_analytics.cli ingest --format {c.cricsheet_key}",
                        language="bash",
                    )


# ── Welcome screen ────────────────────────────────────────────────────────────

def _render_welcome(modules_by_cat: dict):
    st.markdown("### 👈 Select a competition & module, then click **▶ Run Analysis**")
    with st.expander("📖 Available Modules", expanded=True):
        cols = st.columns(2)
        for i, (cat, mods) in enumerate(modules_by_cat.items()):
            emoji = {"basic": "📊", "intermediate": "⚡", "advanced": "🤖"}.get(cat, "")
            with cols[i % 2]:
                st.markdown(f"**{emoji} {cat.title()}**")
                for m in mods:
                    st.markdown(f"- `{m['id']}` {m['name']}")
    with st.expander("🏟️ Available Competitions"):
        for c in COMPETITIONS:
            st.markdown(f"**{c.emoji} {c.label}** — {c.description}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.markdown(
        "<h1 style='margin-bottom:0'>🏏 Cricket Analytics Platform</h1>"
        "<p style='color:gray;margin-top:4px'>T20 · IPL · BBL · PSL · CPL · SA20 · Hundred · Blast</p>",
        unsafe_allow_html=True,
    )

    all_mods = list_modules()
    if not all_mods:
        st.error("No modules registered. Check module imports.")
        return

    modules_by_cat: dict[str, list] = {}
    for m in all_mods:
        modules_by_cat.setdefault(m["category"], []).append(m)

    module_id, params, run_clicked = _render_sidebar()

    if run_clicked:
        st.session_state["last_module_id"] = module_id
        st.session_state["last_params"]    = params
        st.session_state["has_results"]    = True

    if st.session_state.get("has_results"):
        _render_results(
            st.session_state["last_module_id"],
            st.session_state["last_params"],
        )
    else:
        _render_welcome(modules_by_cat)

    _render_overview()


if __name__ == "__main__":
    main()
