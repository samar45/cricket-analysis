"""Streamlit dashboard — Cricket Analytics Platform.

Design:
  Sidebar  = Competition picker + Module navigation ONLY (clean, minimal)
  Main     = Module-specific inline filters + results + charts
  Filters are contextual — each module shows only the filters it needs,
  rendered IN the page above the results (not crammed into the sidebar).
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

import pandas as pd
import plotly.graph_objects as go

from modules.base import list_modules, get_module, ModuleParams
from src.cricket_analytics.db import query
from src.cricket_analytics.leagues import COMPETITIONS, get_sql_filter


# ── Constants ────────────────────────────────────────────────────────────────

IPL_TEAM_COLORS = {
    "Mumbai Indians": "#005DA0", "Chennai Super Kings": "#FCCA06",
    "Royal Challengers Bengaluru": "#EC1C24", "Kolkata Knight Riders": "#3A225D",
    "Delhi Capitals": "#004C93", "Punjab Kings": "#DD1F2D",
    "Rajasthan Royals": "#254AA5", "Sunrisers Hyderabad": "#FF822A",
    "Gujarat Titans": "#1C1C1C", "Lucknow Super Giants": "#A72056",
    "Deccan Chargers": "#F7A721", "Rising Pune Supergiants": "#6F347A",
    "Gujarat Lions": "#D4A017", "Kochi Tuskers Kerala": "#6B2737",
    "Pune Warriors": "#1B4F8A",
}

MODULE_NAV = [
    ("🏠  Overview",          None),
    ("🏏  Batting Stats",     "B1"),
    ("🎯  Bowling Stats",     "B2"),
    ("🏆  Team Performance",  "B3"),
    ("⚔️  Head to Head",     "B4"),
    ("👑  Leaderboards",      "B5"),
    ("🏟️  Venue Analysis",   "B6"),
    ("📊  Phase Breakdown",   "I1"),
    ("🤝  Partnerships",      "I2"),
    ("💥  Impact Score",      "I3"),
    ("📈  Form Tracker",      "I4"),
]

MODULE_DESC = {
    "B1": "Career batting stats — runs, average, strike rate, 50s, 100s, highest score",
    "B2": "Career bowling stats — wickets, economy, average, dot ball %",
    "B3": "Team win/loss records, toss advantage, performance trends",
    "B4": "Batter vs bowler head-to-head matchup: runs, dismissals, dots, strike rate",
    "B5": "Orange Cap, Purple Cap, Strike Rate and Economy leaderboards",
    "B6": "Venue deep-dive: avg scores, bat-first win %, best batters & bowlers at a ground",
    "I1": "Powerplay / Middle / Death overs breakdown for teams and players",
    "I2": "Top batting partnerships by total runs and partnership strike rate",
    "I3": "Combined batting + bowling impact score to find all-rounders",
    "I4": "Rolling average form tracker — see who's in/out of form",
}


# ── Cached data loaders ──────────────────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _players_for(comp: str) -> list[str]:
    """Players sorted by matches played (popular names first for easier search)."""
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else ""
        sql = f"""
            SELECT name, SUM(appearances) AS n FROM (
                SELECT d.batter AS name, COUNT(DISTINCT d.match_id) AS appearances
                FROM deliveries d JOIN matches m ON d.match_id = m.match_id
                {w} AND d.batter IS NOT NULL GROUP BY d.batter
                UNION ALL
                SELECT d.bowler, COUNT(DISTINCT d.match_id)
                FROM deliveries d JOIN matches m ON d.match_id = m.match_id
                {w} AND d.bowler IS NOT NULL GROUP BY d.bowler
            ) GROUP BY name ORDER BY n DESC
        """
        return query(sql, (vals + vals) if vals else None)["name"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _batters_for(comp: str) -> list[str]:
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else ""
        sql = f"""
            SELECT d.batter AS name, SUM(d.runs_batter) AS runs
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            {w} AND d.batter IS NOT NULL GROUP BY d.batter ORDER BY runs DESC
        """
        return query(sql, vals or None)["name"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _bowlers_for(comp: str) -> list[str]:
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else ""
        sql = f"""
            SELECT d.bowler AS name, COUNT(*) AS wkts
            FROM deliveries d JOIN matches m ON d.match_id = m.match_id
            {w} AND d.bowler IS NOT NULL AND d.wicket_type IS NOT NULL
            GROUP BY d.bowler ORDER BY wkts DESC
        """
        return query(sql, vals or None)["name"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _venues_for(comp: str) -> list[str]:
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else ""
        return query(
            f"SELECT DISTINCT venue FROM matches m {w} AND venue IS NOT NULL ORDER BY venue",
            vals or None
        )["venue"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _teams_for(comp: str) -> list[str]:
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else ""
        return query(
            f"SELECT DISTINCT team1 AS team FROM matches m {w} UNION "
            f"SELECT DISTINCT team2 FROM matches m {w} ORDER BY team",
            (vals + vals) if vals else None
        )["team"].dropna().tolist()
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _seasons_for(comp: str) -> list[str]:
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else ""
        return query(
            f"SELECT DISTINCT season FROM matches m {w} AND season IS NOT NULL ORDER BY season DESC",
            vals or None
        )["season"].dropna().tolist()
    except Exception:
        return []


# ── Overview data ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _overview_data(comp: str) -> dict:
    try:
        sql_f, vals = get_sql_filter(comp, "m")
        w = f"WHERE {sql_f}" if sql_f != "1=1" else "WHERE 1=1"
        v = vals or []

        matches = query(f"SELECT COUNT(*) n FROM matches m {w}", v or None)["n"].iloc[0]
        balls   = query(f"SELECT COUNT(*) n FROM deliveries d JOIN matches m ON d.match_id=m.match_id {w}", v or None)["n"].iloc[0]
        players = query(f"SELECT COUNT(DISTINCT d.batter) n FROM deliveries d JOIN matches m ON d.match_id=m.match_id {w}", v or None)["n"].iloc[0]
        seasons = query(f"SELECT COUNT(DISTINCT m.season) n FROM matches m {w}", v or None)["n"].iloc[0]

        top_bat = query(f"""
            SELECT d.batter AS player, SUM(d.runs_batter) AS runs
            FROM deliveries d JOIN matches m ON d.match_id=m.match_id {w}
            GROUP BY d.batter ORDER BY runs DESC LIMIT 10
        """, v or None)

        top_bowl = query(f"""
            SELECT d.bowler AS player, COUNT(*) AS wickets
            FROM deliveries d JOIN matches m ON d.match_id=m.match_id {w}
            AND d.wicket_type IS NOT NULL
            AND d.wicket_type NOT IN ('run out','retired hurt','obstructing the field')
            GROUP BY d.bowler ORDER BY wickets DESC LIMIT 10
        """, v or None)

        per_season = query(f"""
            SELECT m.season, COUNT(*) AS matches FROM matches m {w}
            AND m.season IS NOT NULL GROUP BY m.season ORDER BY m.season
        """, v or None)

        team_w = query(f"SELECT winner AS team, COUNT(*) wins FROM matches m {w} AND winner IS NOT NULL GROUP BY winner", v or None)
        team_p = query(f"""
            SELECT team, COUNT(*) played FROM (
                SELECT m.team1 AS team FROM matches m {w}
                UNION ALL SELECT m.team2 FROM matches m {w}
            ) t GROUP BY team
        """, (v + v) if v else None)

        tp = team_p.merge(team_w, on="team", how="left").fillna(0)
        tp["wins"] = tp["wins"].astype(int)
        tp["win_pct"] = (tp["wins"] / tp["played"] * 100).round(1)
        tp = tp.sort_values("win_pct", ascending=False).head(15)

        # Latest season highlight
        latest = ts = tb = None
        if not per_season.empty:
            latest = str(per_season["season"].iloc[-1])
            sw = w + f" AND m.season = '{latest}'"
            r = query(f"SELECT d.batter AS player, SUM(d.runs_batter) AS v FROM deliveries d JOIN matches m ON d.match_id=m.match_id {sw} GROUP BY d.batter ORDER BY v DESC LIMIT 1", v or None)
            if not r.empty:
                ts = {"player": r.iloc[0]["player"], "val": int(r.iloc[0]["v"])}
            r2 = query(f"SELECT d.bowler AS player, COUNT(*) AS v FROM deliveries d JOIN matches m ON d.match_id=m.match_id {sw} AND d.wicket_type IS NOT NULL AND d.wicket_type NOT IN ('run out','retired hurt','obstructing the field') GROUP BY d.bowler ORDER BY v DESC LIMIT 1", v or None)
            if not r2.empty:
                tb = {"player": r2.iloc[0]["player"], "val": int(r2.iloc[0]["v"])}

        return {"matches": int(matches), "balls": int(balls), "players": int(players),
                "seasons": int(seasons), "top_bat": top_bat, "top_bowl": top_bowl,
                "per_season": per_season, "team_perf": tp,
                "latest": latest, "ts": ts, "tb": tb}
    except Exception as e:
        return {"matches": 0, "balls": 0, "players": 0, "seasons": 0,
                "top_bat": None, "top_bowl": None, "per_season": None,
                "team_perf": None, "latest": None, "ts": None, "tb": None, "err": str(e)}


# ── Sidebar (navigation ONLY — no filters) ───────────────────────────────────

def _sidebar() -> tuple[str, str | None]:
    st.sidebar.markdown("### 🏏 Cricket Analytics")
    st.sidebar.divider()

    # Competition radio
    comp_labels = [c.label for c in COMPETITIONS]
    comp_emojis = {c.label: c.emoji for c in COMPETITIONS}
    comp = st.sidebar.radio(
        "Competition", comp_labels,
        format_func=lambda x: f"{comp_emojis[x]}  {x}",
        key="comp", label_visibility="collapsed",
    )

    st.sidebar.divider()

    # Module radio — single flat list, clean
    nav_labels = [lbl for lbl, _ in MODULE_NAV]
    sel = st.sidebar.radio(
        "Navigate", nav_labels,
        key="nav", label_visibility="collapsed",
    )
    module_id = dict(MODULE_NAV).get(sel)

    st.sidebar.divider()
    st.sidebar.caption("Data: [Cricsheet.org](https://cricsheet.org)")

    return comp, module_id


# ── Selectbox helper ──────────────────────────────────────────────────────────

def _pick(label: str, options: list[str], key: str, all_label: str = "All") -> str | None:
    """Single selectbox with 'All' default. Streamlit's built-in type-to-search works."""
    val = st.selectbox(label, [all_label] + options, key=key)
    return None if val == all_label else val


# ── Per-module filter panels (rendered in main area) ──────────────────────────

def _filters_B1(comp):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        player = _pick("Player", _players_for(comp), "f_player")
    with c2:
        season = _pick("Season", _seasons_for(comp), "f_season")
    with c3:
        venue = _pick("Venue", _venues_for(comp), "f_venue")
    return ModuleParams(format=comp, player=player, season=season, venue=venue)


def _filters_B2(comp):
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    with c1:
        player = _pick("Player", _players_for(comp), "f_player")
    with c2:
        season = _pick("Season", _seasons_for(comp), "f_season")
    with c3:
        venue = _pick("Venue", _venues_for(comp), "f_venue")
    with c4:
        ph_map = {"All Phases": None, "Powerplay (1-6)": "powerplay",
                   "Middle (7-15)": "middle", "Death (16-20)": "death"}
        phase = ph_map[st.selectbox("Phase", list(ph_map), key="f_phase")]
    return ModuleParams(format=comp, player=player, season=season, venue=venue, phase=phase)


def _filters_B3(comp):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        team = _pick("Team", _teams_for(comp), "f_team")
    with c2:
        season = _pick("Season", _seasons_for(comp), "f_season")
    with c3:
        venue = _pick("Venue", _venues_for(comp), "f_venue")
    return ModuleParams(format=comp, team=team, season=season, venue=venue)


def _filters_B4(comp):
    c1, c2 = st.columns(2)
    with c1:
        batter = _pick("🏏 Batter", _batters_for(comp), "f_batter", "All Batters")
    with c2:
        bowler = _pick("🎯 Bowler", _bowlers_for(comp), "f_bowler", "All Bowlers")
    c3, _ = st.columns([2, 3])
    with c3:
        season = _pick("Season", _seasons_for(comp), "f_season")
    return ModuleParams(format=comp, player=batter, player2=bowler, season=season)


def _filters_B5(comp):
    c1, c2 = st.columns([3, 2])
    with c1:
        cap_map = {"🟠 Orange Cap (Runs)": "orange", "🟣 Purple Cap (Wickets)": "purple",
                    "⚡ Strike Rate Leaders": "sr", "💰 Economy Leaders": "economy"}
        cap = cap_map[st.selectbox("Leaderboard", list(cap_map), key="f_cap")]
    with c2:
        season = _pick("Season", _seasons_for(comp), "f_season")
    return ModuleParams(format=comp, season=season, extra={"cap": cap})


def _filters_B6(comp):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        venue = _pick("Venue", _venues_for(comp), "f_venue")
    with c2:
        team = _pick("Team", _teams_for(comp), "f_team")
    with c3:
        season = _pick("Season", _seasons_for(comp), "f_season")
    return ModuleParams(format=comp, venue=venue, team=team, season=season)


def _filters_I1(comp):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        team = _pick("Team", _teams_for(comp), "f_team")
    with c2:
        player = _pick("Player", _players_for(comp), "f_player")
    with c3:
        season = _pick("Season", _seasons_for(comp), "f_season")
    return ModuleParams(format=comp, team=team, player=player, season=season)


def _filters_I2(comp):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        player = _pick("Player", _players_for(comp), "f_player")
    with c2:
        team = _pick("Team", _teams_for(comp), "f_team")
    with c3:
        season = _pick("Season", _seasons_for(comp), "f_season")
    return ModuleParams(format=comp, player=player, team=team, season=season)


def _filters_I3(comp):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        player = _pick("Player", _players_for(comp), "f_player")
    with c2:
        team = _pick("Team", _teams_for(comp), "f_team")
    with c3:
        season = _pick("Season", _seasons_for(comp), "f_season")
    return ModuleParams(format=comp, player=player, team=team, season=season)


def _filters_I4(comp):
    c1, c2, c3 = st.columns([2, 3, 2])
    with c1:
        role = st.radio("Role", ["batter", "bowler"], horizontal=True, key="f_role")
    with c2:
        plist = _batters_for(comp) if role == "batter" else _bowlers_for(comp)
        player = _pick("Player", plist, f"f_player_{role}")
    with c3:
        window = st.slider("Rolling window", 3, 15, 5, key="f_window")
    return ModuleParams(format=comp, player=player, extra={"role": role, "window": window})


FILTER_FNS = {
    "B1": _filters_B1, "B2": _filters_B2, "B3": _filters_B3,
    "B4": _filters_B4, "B5": _filters_B5, "B6": _filters_B6,
    "I1": _filters_I1, "I2": _filters_I2, "I3": _filters_I3,
    "I4": _filters_I4,
}


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _ipl_bar_color(teams: list[str], comp: str) -> list[str]:
    if comp == "IPL":
        return [IPL_TEAM_COLORS.get(t, "#4A90D9") for t in teams]
    return ["#4A90D9"] * len(teams)


def _apply_ipl_colors(fig, comp: str):
    if comp != "IPL":
        return
    try:
        for trace in fig.data:
            if trace.type == "bar":
                names = list(trace.y) if trace.orientation == "h" else list(trace.x)
                if names and all(isinstance(n, str) for n in names):
                    colors = [IPL_TEAM_COLORS.get(n, "#4A90D9") for n in names]
                    if any(c != "#4A90D9" for c in colors):
                        trace.marker.color = colors
    except Exception:
        pass


def _hbar(x_vals, y_vals, color="#4A90D9", colors=None, height=360):
    fig = go.Figure(go.Bar(
        x=x_vals, y=y_vals, orientation="h",
        marker_color=colors or color,
        text=x_vals, textposition="outside",
    ))
    fig.update_layout(
        margin=dict(l=0, r=40, t=0, b=0), height=height,
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── Overview page ─────────────────────────────────────────────────────────────

def _render_overview(comp: str):
    comp_obj = next((c for c in COMPETITIONS if c.label == comp), None)
    emoji = comp_obj.emoji if comp_obj else "🏏"
    st.markdown(f"# {emoji} {comp} Dashboard")

    with st.spinner("Loading..."):
        ov = _overview_data(comp)

    if ov["matches"] == 0:
        st.info(f"No data for **{comp}**. Run:  `python -m src.cricket_analytics.cli ingest --format {comp_obj.cricsheet_key if comp_obj else 'ipl'}`")
        return

    # ── Metrics row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Matches", f"{ov['matches']:,}")
    c2.metric("Balls Bowled", f"{ov['balls']:,}")
    c3.metric("Players", f"{ov['players']:,}")
    c4.metric("Seasons", f"{ov['seasons']}")

    # ── Latest season highlight
    if ov["latest"] and (ov["ts"] or ov["tb"]):
        with st.container(border=True):
            st.markdown(f"#### ✨ {ov['latest']} Season Highlights")
            g1, g2 = st.columns(2)
            if ov["ts"]:
                g1.metric("🏏 Top Scorer", ov["ts"]["player"], f"{ov['ts']['val']} runs")
            if ov["tb"]:
                g2.metric("🎯 Top Wicket Taker", ov["tb"]["player"], f"{ov['tb']['val']} wickets")

    # ── Top batters + bowlers
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("#### 🏏 Top 10 Run Scorers")
            df = ov["top_bat"]
            if df is not None and not df.empty:
                st.plotly_chart(
                    _hbar(df["runs"].tolist(), df["player"].tolist()),
                    use_container_width=True, key="ov_bat",
                )
    with right:
        with st.container(border=True):
            st.markdown("#### 🎯 Top 10 Wicket Takers")
            df = ov["top_bowl"]
            if df is not None and not df.empty:
                st.plotly_chart(
                    _hbar(df["wickets"].tolist(), df["player"].tolist(), "#E45E3E"),
                    use_container_width=True, key="ov_bowl",
                )

    # ── Matches per season
    with st.container(border=True):
        st.markdown("#### 📅 Matches per Season")
        df = ov["per_season"]
        if df is not None and not df.empty:
            fig = go.Figure(go.Bar(
                x=[str(s) for s in df["season"]], y=df["matches"].tolist(),
                marker_color="#4A90D9", text=df["matches"].tolist(), textposition="outside",
            ))
            fig.update_layout(
                margin=dict(l=0, r=0, t=0, b=0), height=280,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, key="ov_season")

    # ── Team win %
    with st.container(border=True):
        st.markdown("#### 🏆 Team Win %")
        df = ov["team_perf"]
        if df is not None and not df.empty:
            teams = df["team"].tolist()
            pcts = df["win_pct"].tolist()
            st.plotly_chart(
                _hbar(pcts, teams, colors=_ipl_bar_color(teams, comp),
                      height=max(280, len(teams) * 28)),
                use_container_width=True, key="ov_team",
            )


# ── Module page ───────────────────────────────────────────────────────────────

def _render_module(module_id: str, comp: str):
    try:
        mod = get_module(module_id)
    except KeyError:
        st.error(f"Module {module_id} not found.")
        return

    comp_obj = next((c for c in COMPETITIONS if c.label == comp), None)
    emoji = comp_obj.emoji if comp_obj else "🏏"

    st.markdown(f"# {emoji} {mod.module_name}")
    st.caption(MODULE_DESC.get(module_id, ""))

    # ── Inline filter panel
    filter_fn = FILTER_FNS.get(module_id)
    if not filter_fn:
        st.error(f"No filter config for {module_id}")
        return

    with st.container(border=True):
        params = filter_fn(comp)
        _, btn_col = st.columns([5, 1])
        with btn_col:
            run_clicked = st.button("▶ Analyse", type="primary",
                                    use_container_width=True, key=f"run_{module_id}")

    # ── State: remember last run params
    state_key = f"res_{module_id}"
    if run_clicked:
        st.session_state[state_key] = params

    stored = st.session_state.get(state_key)
    if stored is None:
        st.info("👆 Choose your filters and click **Analyse**")
        return

    # ── Run analysis
    with st.spinner("Analysing..."):
        try:
            df = mod.run(stored)
            tabs_data = mod.run_tabs(stored)
        except Exception as e:
            st.error(f"Error: {e}")
            return

    if df is None or df.empty:
        st.warning("No data for these filters. Try broader selections.")
        return

    # ── Render results
    with st.container(border=True):
        if tabs_data:
            tab_labels = ["📊 Overview"] + list(tabs_data.keys())
            tab_objs = st.tabs(tab_labels)
            with tab_objs[0]:
                _show_results(df, mod, stored, comp, "main")
            for i, (name, tdf) in enumerate(tabs_data.items(), 1):
                with tab_objs[i]:
                    if tdf is not None and not tdf.empty:
                        st.dataframe(tdf, use_container_width=True, hide_index=True)
                        st.download_button("⬇ CSV", tdf.to_csv(index=False),
                                           f"{module_id}_{name}.csv", "text/csv",
                                           key=f"dl_{module_id}_{name}")
                    else:
                        st.info("No data for this tab.")
        else:
            _show_results(df, mod, stored, comp, "main")


def _show_results(df, mod, params, comp, key=""):
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇ Download CSV", df.to_csv(index=False),
                       f"{mod.module_id}_results.csv", "text/csv",
                       key=f"dl_{mod.module_id}_{key}")
    try:
        fig = mod.plot(df, params)
        if fig is not None:
            _apply_ipl_colors(fig, comp)
            st.plotly_chart(fig, use_container_width=True, key=f"plot_{key}")
    except NotImplementedError:
        pass
    except Exception as e:
        st.caption(f"Chart unavailable: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    comp, module_id = _sidebar()

    # Clear stored results when competition changes
    prev = st.session_state.get("_prev_comp")
    if prev != comp:
        for k in [k for k in st.session_state if k.startswith("res_")]:
            del st.session_state[k]
        st.session_state["_prev_comp"] = comp

    if module_id is None:
        _render_overview(comp)
    else:
        _render_module(module_id, comp)


if __name__ == "__main__":
    main()
