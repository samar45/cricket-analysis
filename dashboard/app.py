"""Streamlit dashboard — Cricket Analytics Platform.

Run with: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of where streamlit is launched from
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(page_title="Cricket Analytics", page_icon="🏏", layout="wide")

# Ensure modules are registered
import modules.basic  # noqa: F401
from modules.base import list_modules, get_module, ModuleParams
from src.cricket_analytics.db import query


def main():
    st.title("Cricket Analytics Platform")
    st.caption("Modular cricket analysis — IPL / T20I / ODI / Test")

    # Sidebar: filters
    st.sidebar.header("Filters")

    available = list_modules()
    module_options = {f"{m['id']} — {m['name']}": m["id"] for m in available}

    if not module_options:
        st.error("No modules registered. Check module imports.")
        return

    selected_label = st.sidebar.selectbox("Module", list(module_options.keys()))
    selected_id = module_options[selected_label]

    fmt = st.sidebar.selectbox("Format", ["T20", "ODI", "Test"], index=0)
    player = st.sidebar.text_input("Player (name or partial)")
    team = st.sidebar.text_input("Team")
    season = st.sidebar.text_input("Season (year)")
    venue = st.sidebar.text_input("Venue")
    phase = st.sidebar.selectbox("Phase", [None, "powerplay", "middle", "death"], index=0)

    # Parse season
    season_val = None
    if season:
        try:
            season_val = int(season)
        except ValueError:
            st.sidebar.warning("Season must be a number.")

    params = ModuleParams(
        player=player or None,
        team=team or None,
        season=season_val,
        format=fmt,
        venue=venue or None,
        phase=phase,
    )

    # Run module
    if st.sidebar.button("Run Analysis", type="primary"):
        module = get_module(selected_id)
        with st.spinner(f"Running {module.module_id}: {module.module_name}..."):
            df = module.run(params)

        if df.empty:
            st.warning("No results found for the given filters.")
        else:
            st.subheader(f"Results: {module.module_name}")
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Show plot
            try:
                fig = module.plot(df, params)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            except NotImplementedError:
                pass

            # Download
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", csv, f"{selected_id}_results.csv", "text/csv")

    # Quick stats section
    st.divider()
    st.subheader("Database Overview")
    col1, col2, col3 = st.columns(3)

    try:
        matches_count = query("SELECT COUNT(*) AS n FROM matches")["n"].iloc[0]
        deliveries_count = query("SELECT COUNT(*) AS n FROM deliveries")["n"].iloc[0]
        players_count = query("SELECT COUNT(DISTINCT batter) AS n FROM deliveries")["n"].iloc[0]
    except Exception:
        matches_count = deliveries_count = players_count = 0

    col1.metric("Matches", f"{matches_count:,}")
    col2.metric("Deliveries (balls)", f"{deliveries_count:,}")
    col3.metric("Unique Players", f"{players_count:,}")


if __name__ == "__main__":
    main()
