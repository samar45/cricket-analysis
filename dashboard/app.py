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

import plotly.graph_objects as go


# ── IPL team colours ──────────────────────────────────────────────────────────

IPL_TEAM_COLORS: dict[str, str] = {
    "Mumbai Indians":                "#005DA0",
    "Chennai Super Kings":           "#F9CD05",
    "Royal Challengers Bengaluru":   "#EC1C24",
    "Royal Challengers Bangalore":   "#EC1C24",
    "Kolkata Knight Riders":         "#3A225D",
    "Delhi Capitals":                "#0078BC",
    "Delhi Daredevils":              "#0078BC",
    "Punjab Kings":                  "#ED1B24",
    "Kings XI Punjab":               "#ED1B24",
    "Rajasthan Royals":              "#254AA5",
    "Sunrisers Hyderabad":           "#F7A721",
    "Gujarat Titans":                "#1C1C1C",
    "Lucknow Super Giants":          "#A72056",
    "Deccan Chargers":               "#F7A721",
    "Kochi Tuskers Kerala":          "#6B2737",
    "Pune Warriors":                 "#1B4F8A",
    "Rising Pune Supergiants":       "#6F347A",
    "Rising Pune Supergiant":        "#6F347A",
    "Gujarat Lions":                 "#D4A017",
}

_DEFAULT_COLOR = "#4A90D9"


def _team_color(team: str, competition: str) -> str:
    if competition == "IPL":
        return IPL_TEAM_COLORS.get(team, _DEFAULT_COLOR)
    return _DEFAULT_COLOR


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


# ── Competition overview (home screen data) ───────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _competition_overview(competition: str) -> dict:
    """Load all data needed for the overview home screen."""
    try:
        league_sql, league_vals = get_sql_filter(competition, "m")
        where_m = f"WHERE {league_sql}" if league_sql != "1=1" else "WHERE 1=1"
        vals = league_vals or []

        # Metrics
        matches_n = query(
            f"SELECT COUNT(*) AS n FROM matches m {where_m}", vals or None
        )["n"].iloc[0]
        balls_n = query(
            f"SELECT COUNT(*) AS n FROM deliveries d JOIN matches m ON d.match_id = m.match_id {where_m}",
            vals or None
        )["n"].iloc[0]
        players_n = query(
            f"SELECT COUNT(DISTINCT d.batter) AS n FROM deliveries d JOIN matches m ON d.match_id = m.match_id {where_m}",
            vals or None
        )["n"].iloc[0]
        seasons_n = query(
            f"SELECT COUNT(DISTINCT m.season) AS n FROM matches m {where_m}",
            vals or None
        )["n"].iloc[0]

        # Top 10 run scorers
        top_batters = query(f"""
            SELECT d.batter AS player, SUM(d.runs_batter) AS runs
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            {where_m}
            GROUP BY d.batter
            ORDER BY runs DESC
            LIMIT 10
        """, vals or None)

        # Top 10 wicket takers
        top_bowlers = query(f"""
            SELECT d.bowler AS player, COUNT(*) AS wickets
            FROM deliveries d
            JOIN matches m ON d.match_id = m.match_id
            {where_m}
            AND d.wicket_type IS NOT NULL
            AND d.wicket_type NOT IN ('run out', 'retired hurt', 'obstructing the field')
            GROUP BY d.bowler
            ORDER BY wickets DESC
            LIMIT 10
        """, vals or None)

        # Matches per season
        matches_per_season = query(f"""
            SELECT m.season, COUNT(*) AS matches
            FROM matches m {where_m}
            AND m.season IS NOT NULL
            GROUP BY m.season
            ORDER BY m.season
        """, vals or None)

        # Team win records
        team_wins = query(f"""
            SELECT winner AS team,
                   COUNT(*) AS wins
            FROM matches m {where_m}
            AND winner IS NOT NULL
            GROUP BY winner
        """, vals or None)

        team_played = query(f"""
            SELECT team, COUNT(*) AS played FROM (
                SELECT m.team1 AS team FROM matches m {where_m}
                UNION ALL
                SELECT m.team2 AS team FROM matches m {where_m}
            ) t
            GROUP BY team
        """, (vals + vals) if vals else None)

        team_perf = team_played.merge(team_wins, on="team", how="left").fillna(0)
        team_perf["wins"] = team_perf["wins"].astype(int)
        team_perf["win_pct"] = (team_perf["wins"] / team_perf["played"] * 100).round(1)
        team_perf = team_perf.sort_values("win_pct", ascending=False).head(15)

        # Most recent season highlight
        latest_season = None
        top_scorer_latest = None
        top_bowler_latest = None

        if not matches_per_season.empty:
            latest_season = str(matches_per_season["season"].iloc[-1])
            season_where = where_m + f" AND m.season = '{latest_season}'"

            ts = query(f"""
                SELECT d.batter AS player, SUM(d.runs_batter) AS runs
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                {season_where}
                GROUP BY d.batter ORDER BY runs DESC LIMIT 1
            """, vals or None)
            if not ts.empty:
                top_scorer_latest = ts.iloc[0]

            tb = query(f"""
                SELECT d.bowler AS player, COUNT(*) AS wickets
                FROM deliveries d
                JOIN matches m ON d.match_id = m.match_id
                {season_where}
                AND d.wicket_type IS NOT NULL
                AND d.wicket_type NOT IN ('run out', 'retired hurt', 'obstructing the field')
                GROUP BY d.bowler ORDER BY wickets DESC LIMIT 1
            """, vals or None)
            if not tb.empty:
                top_bowler_latest = tb.iloc[0]

        return {
            "matches": int(matches_n),
            "balls": int(balls_n),
            "players": int(players_n),
            "seasons": int(seasons_n),
            "top_batters": top_batters,
            "top_bowlers": top_bowlers,
            "matches_per_season": matches_per_season,
            "team_perf": team_perf,
            "latest_season": latest_season,
            "top_scorer_latest": top_scorer_latest,
            "top_bowler_latest": top_bowler_latest,
        }
    except Exception as e:
        return {
            "matches": 0, "balls": 0, "players": 0, "seasons": 0,
            "top_batters": None, "top_bowlers": None,
            "matches_per_season": None, "team_perf": None,
            "latest_season": None, "top_scorer_latest": None,
            "top_bowler_latest": None,
            "error": str(e),
        }


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> tuple[str, str | None, ModuleParams, bool]:
    """Render full sidebar. Returns (competition, module_id_or_None, params, run_clicked)."""

    st.sidebar.markdown("## 🏏 Cricket Analytics")
    st.sidebar.divider()

    # ── Competition selector ──────────────────────────────────────────────────
    st.sidebar.markdown("**Competition**")
    comp_labels = [c.label for c in COMPETITIONS]
    comp_emojis = {c.label: c.emoji for c in COMPETITIONS}

    selected_comp = st.sidebar.radio(
        "Competition",
        comp_labels,
        format_func=lambda x: f"{comp_emojis[x]}  {x}",
        key="competition",
        label_visibility="collapsed",
    )

    st.sidebar.divider()

    # ── Module navigation ─────────────────────────────────────────────────────
    all_mods = list_modules()
    cat_order   = ["basic", "intermediate"]
    cat_emoji   = {"basic": "📊", "intermediate": "⚡", "advanced": "🤖"}
    cat_heading = {"basic": "Basic Analysis", "intermediate": "Advanced Analysis"}

    # Build per-category radio widgets; track which module is selected
    selected_module_id = st.session_state.get("selected_module_id", None)

    # Overview option always at top
    st.sidebar.markdown("**Overview**")
    show_overview = st.sidebar.radio(
        "overview_nav",
        ["🏠  Overview"],
        key="overview_nav",
        label_visibility="collapsed",
    )

    new_module_id = None  # None means Overview

    for cat in cat_order:
        mods = [m for m in all_mods if m["category"] == cat]
        if not mods:
            continue
        emoji = cat_emoji.get(cat, "")
        heading = cat_heading.get(cat, cat.title())
        st.sidebar.markdown(f"**{emoji} {heading}**")

        mod_labels = [f"{m['id']} — {m['name']}" for m in mods]
        mod_ids    = [m["id"] for m in mods]

        # Default: no selection (None → first empty option)
        cat_key = f"nav_{cat}"

        # Determine if a module from this category is currently selected
        current_cat_selection = None
        if selected_module_id in mod_ids:
            current_cat_selection = mod_labels[mod_ids.index(selected_module_id)]

        options_with_none = ["— Select —"] + mod_labels
        default_idx = 0
        if current_cat_selection in options_with_none:
            default_idx = options_with_none.index(current_cat_selection)

        sel = st.sidebar.radio(
            heading,
            options_with_none,
            index=default_idx,
            key=cat_key,
            label_visibility="collapsed",
        )
        if sel != "— Select —":
            label_idx = mod_labels.index(sel)
            new_module_id = mod_ids[label_idx]

    # If a module radio was clicked, update session state and clear overview
    if new_module_id is not None:
        if st.session_state.get("selected_module_id") != new_module_id:
            st.session_state["selected_module_id"] = new_module_id
            # Reset the other category radios to "— Select —" by clearing their keys
            # (Streamlit doesn't easily allow resetting radios, but we track via session state)
        selected_module_id = new_module_id
    else:
        # Overview is active — clear any module selection
        if show_overview == "🏠  Overview":
            selected_module_id = None
            st.session_state["selected_module_id"] = None

    st.sidebar.divider()

    # ── Filters (only shown when a module is selected) ─────────────────────
    run_btn = False
    params = ModuleParams(format=selected_comp)

    if selected_module_id is not None:
        try:
            mod = get_module(selected_module_id)
            supported = mod.supported_filters
        except Exception:
            supported = set()

        player = player2 = team = season = venue = phase = None
        extra: dict = {}

        all_players = _players_for(selected_comp) if any(
            f in supported for f in ("player", "player2")) else []
        all_venues  = _venues_for(selected_comp)  if "venue"  in supported else []
        all_teams   = _teams_for(selected_comp)   if "team"   in supported else []
        all_seasons = _seasons_for(selected_comp) if "season" in supported else []

        has_filters = bool(supported - {"format"})

        if has_filters:
            st.sidebar.markdown("**Filters**")

        if "player" in supported:
            label = "Batter" if selected_module_id == "B4" else "Player"
            player = _search_select(label, all_players, key="player",
                                    all_label="— All Players —")

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

        if selected_module_id == "B5":
            cap_map = {
                "🟠 Orange Cap (Runs)":    "orange",
                "🟣 Purple Cap (Wickets)": "purple",
                "⚡ Strike Rate Leaders":  "sr",
                "💰 Economy Leaders":      "economy",
            }
            sel_cap = st.sidebar.selectbox("Leaderboard", list(cap_map), key="cap")
            extra["cap"] = cap_map[sel_cap]

        if has_filters:
            st.sidebar.divider()
            run_btn = st.sidebar.button(
                "▶  Run Analysis", type="primary",
                use_container_width=True, key="run_btn"
            )

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

    return selected_comp, selected_module_id, params, run_btn


def _search_select(label: str, options: list[str], key: str,
                   all_label: str = "— All —", max_shown: int = 150) -> str | None:
    """Search text_input above a selectbox for clean filtered selection."""
    search = st.sidebar.text_input(f"🔍 Search {label.lower()}…", key=f"search_{key}")
    filtered = [o for o in options if search.lower() in o.lower()] if search else options
    shown = filtered[:max_shown]
    suffix = f" ({max_shown}/{len(filtered)})" if len(filtered) > max_shown else ""
    display_opts = [all_label] + shown
    sel = st.sidebar.selectbox(
        f"{label}{suffix}",
        display_opts,
        key=f"sel_{key}",
    )
    return None if sel == all_label else sel


# ── Overview home screen ──────────────────────────────────────────────────────

def _render_overview(competition: str):
    comp_obj = next((c for c in COMPETITIONS if c.label == competition), None)
    emoji = comp_obj.emoji if comp_obj else "🏏"

    st.markdown(
        f"<h1 style='margin-bottom:0'>{emoji} {competition} Analytics</h1>",
        unsafe_allow_html=True,
    )

    with st.spinner("Loading overview…"):
        ov = _competition_overview(competition)

    if ov.get("error") and ov["matches"] == 0:
        st.error(f"Could not load data: {ov['error']}")
        return

    # ── Metric cards ─────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matches",  f"{ov['matches']:,}")
    c2.metric("Balls",    f"{ov['balls']:,}")
    c3.metric("Players",  f"{ov['players']:,}")
    c4.metric("Seasons",  f"{ov['seasons']:,}")

    if ov["matches"] == 0:
        st.info("No data loaded for this competition yet. Use the CLI to ingest data.")
        return

    # ── This season at a glance (IPL only — or any competition) ──────────────
    if ov["latest_season"] and (ov["top_scorer_latest"] is not None or ov["top_bowler_latest"] is not None):
        with st.container(border=True):
            st.markdown(f"#### ✨ {ov['latest_season']} Season at a Glance")
            g1, g2 = st.columns(2)
            if ov["top_scorer_latest"] is not None:
                ts = ov["top_scorer_latest"]
                g1.metric(f"🏏 Top Run Scorer", ts["player"], f"{int(ts['runs'])} runs")
            if ov["top_bowler_latest"] is not None:
                tb = ov["top_bowler_latest"]
                g2.metric(f"🎯 Top Wicket Taker", tb["player"], f"{int(tb['wickets'])} wickets")

    # ── Top batters & bowlers ─────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        with st.container(border=True):
            st.markdown("#### 🏏 Top 10 Run Scorers")
            tb_df = ov["top_batters"]
            if tb_df is not None and not tb_df.empty:
                colors = [_team_color("", competition)] * len(tb_df)
                # For IPL, we can't easily match batter→team here, use default palette
                fig = go.Figure(go.Bar(
                    x=tb_df["runs"].tolist(),
                    y=tb_df["player"].tolist(),
                    orientation="h",
                    marker_color=_DEFAULT_COLOR,
                    text=tb_df["runs"].tolist(),
                    textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=380,
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Runs",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

    with col_right:
        with st.container(border=True):
            st.markdown("#### 🎯 Top 10 Wicket Takers")
            bw_df = ov["top_bowlers"]
            if bw_df is not None and not bw_df.empty:
                fig = go.Figure(go.Bar(
                    x=bw_df["wickets"].tolist(),
                    y=bw_df["player"].tolist(),
                    orientation="h",
                    marker_color="#E45E3E",
                    text=bw_df["wickets"].tolist(),
                    textposition="outside",
                ))
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    height=380,
                    yaxis=dict(autorange="reversed"),
                    xaxis_title="Wickets",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True)

    # ── Matches per season ────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 📅 Matches per Season")
        ms_df = ov["matches_per_season"]
        if ms_df is not None and not ms_df.empty:
            fig = go.Figure(go.Bar(
                x=[str(s) for s in ms_df["season"].tolist()],
                y=ms_df["matches"].tolist(),
                marker_color=_DEFAULT_COLOR,
                text=ms_df["matches"].tolist(),
                textposition="outside",
            ))
            fig.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
                xaxis_title="Season",
                yaxis_title="Matches",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Team win percentage ───────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 🏆 Team Win % (all-time)")
        tp_df = ov["team_perf"]
        if tp_df is not None and not tp_df.empty:
            teams_list = tp_df["team"].tolist()
            win_pcts   = tp_df["win_pct"].tolist()
            bar_colors = [_team_color(t, competition) for t in teams_list]
            fig = go.Figure(go.Bar(
                x=win_pcts,
                y=teams_list,
                orientation="h",
                marker_color=bar_colors,
                text=[f"{p}%" for p in win_pcts],
                textposition="outside",
            ))
            fig.update_layout(
                margin=dict(l=10, r=10, t=10, b=10),
                height=max(300, len(teams_list) * 28),
                yaxis=dict(autorange="reversed"),
                xaxis_title="Win %",
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Module results ─────────────────────────────────────────────────────────────

def _render_module(module_id: str, params: ModuleParams, competition: str):
    try:
        mod = get_module(module_id)
    except KeyError as e:
        st.error(str(e))
        return

    comp_obj = next((c for c in COMPETITIONS if c.label == competition), None)
    emoji = comp_obj.emoji if comp_obj else "🏏"

    st.markdown(
        f"<h1 style='margin-bottom:0'>{emoji} {competition} — {mod.module_name}</h1>",
        unsafe_allow_html=True,
    )

    with st.spinner(f"Running {mod.module_id}: {mod.module_name}…"):
        df        = mod.run(params)
        tabs_data = mod.run_tabs(params)

    if df is None or df.empty:
        st.warning("No data for the selected filters — try a broader competition or fewer filters.")
        return

    with st.container(border=True):
        if tabs_data:
            tab_labels  = ["📊 Overview"] + list(tabs_data.keys())
            tab_objects = st.tabs(tab_labels)
            with tab_objects[0]:
                _show_df_and_plot(df, mod, params, competition, key="main")
            for i, (name, tdf) in enumerate(tabs_data.items(), 1):
                with tab_objects[i]:
                    if tdf is not None and not tdf.empty:
                        st.dataframe(tdf, use_container_width=True, hide_index=True)
                        _dl_btn(tdf, f"{module_id}_{name}.csv")
                    else:
                        st.info("No data for this view with the current filters.")
        else:
            _show_df_and_plot(df, mod, params, competition, key="main")


def _show_df_and_plot(df, mod, params, competition: str, key: str = ""):
    st.dataframe(df, use_container_width=True, hide_index=True)
    _dl_btn(df, f"{mod.module_id}_results.csv")
    try:
        fig = mod.plot(df, params)
        if fig is not None:
            # Inject team colors for IPL bar charts where applicable
            if competition == "IPL" and hasattr(fig, "data"):
                _apply_ipl_colors(fig)
            st.plotly_chart(fig, use_container_width=True, key=f"plot_{key}")
    except NotImplementedError:
        pass
    except Exception as e:
        st.caption(f"Chart unavailable: {e}")


def _apply_ipl_colors(fig):
    """Attempt to color bars by team name when x or y axis contains team names."""
    try:
        for trace in fig.data:
            if trace.type == "bar":
                # Try y-axis (horizontal bars) then x-axis (vertical)
                names = list(trace.y) if trace.orientation == "h" else list(trace.x)
                if names and all(isinstance(n, str) for n in names):
                    colors = [IPL_TEAM_COLORS.get(n, _DEFAULT_COLOR) for n in names]
                    if any(c != _DEFAULT_COLOR for c in colors):
                        trace.marker.color = colors
    except Exception:
        pass


def _dl_btn(df, filename: str):
    st.download_button("⬇ Download CSV", df.to_csv(index=False),
                       file_name=filename, mime="text/csv")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    all_mods = list_modules()
    if not all_mods:
        st.error("No modules registered. Check module imports.")
        return

    competition, module_id, params, run_clicked = _render_sidebar()

    # Decide what to show in the main area
    if module_id is None:
        # Overview / home screen
        _render_overview(competition)
        return

    # A module is selected
    has_filters = False
    try:
        mod_obj  = get_module(module_id)
        supported = mod_obj.supported_filters
        has_filters = bool(supported - {"format"})
    except Exception:
        pass

    if not has_filters:
        # Auto-run modules with no meaningful filters (e.g. B5 leaderboards need cap type)
        _render_module(module_id, params, competition)
    elif run_clicked or st.session_state.get(f"ran_{module_id}_{competition}"):
        if run_clicked:
            st.session_state[f"ran_{module_id}_{competition}"] = True
        _render_module(module_id, params, competition)
    else:
        # Show a prompt to run
        comp_obj = next((c for c in COMPETITIONS if c.label == competition), None)
        emoji = comp_obj.emoji if comp_obj else "🏏"
        st.markdown(
            f"<h1 style='margin-bottom:0'>{emoji} {competition} — {module_id}</h1>",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            st.info("👈 Set your filters in the sidebar, then click **▶ Run Analysis**.")


if __name__ == "__main__":
    main()
