"""State leagues page: auction shortlist board and one-player cross-league profile (Cricbuzz state leagues + SMAT 2025 + IPL/T20I).

All numbers come from `scouting.profile` (cached here); this file only lays them out. Column meanings: docs/REPORT_cross_league.md.
"""

import streamlit as st

from cricket_analytics.scouting import profile as P
from cricket_analytics.scouting.reels import NotExact

LEVELS = ["IPL", "T20I", "SMAT", "state league only", "unclear (doubtful link)"]
BOARD_COLS = {
    "bat": ["name", "team", "state_inns", "state_runs", "state_balls", "state_avg", "state_sr", "bat_score", "smat_runs", "smat_balls", "ipl_capped", "level", "ipl_link"],
    "bowl": ["name", "team", "state_bowl_balls", "state_wkts", "state_econ", "bowl_score", "smat_wkts", "smat_bowl_balls", "ipl_capped", "level", "ipl_link"],
}


@st.cache_data(show_spinner="Building the board (first time takes a while)...")
def _board():
    return P.board(100)


@st.cache_data(show_spinner="Looking up the player...")
def _profile(q: str, doubtful: bool):
    df = P.profile(q, include_doubtful=doubtful)
    return df, df.attrs.get("withheld", [])  # attrs are not reliably kept by the cache, so return them explicitly


def _board_tab():
    a, b, c = st.columns(3)
    role = a.radio("Rank", ["Batters", "Bowlers"], horizontal=True, key="sl_role")
    capped = b.selectbox("IPL capped", ["no", "yes", "unknown", "any"], key="sl_capped")
    min_balls = c.slider("Min balls (faced / bowled)", 100, 600, 100, step=50, key="sl_min_balls")
    lv = st.multiselect("Level", LEVELS, default=LEVELS, key="sl_level")
    kind, balls, score = ("bat", "state_balls", "bat_score") if role == "Batters" else ("bowl", "state_bowl_balls", "bowl_score")
    t = _board()
    t = t[t[balls] >= min_balls]
    t = t[t.level.isin(lv)]
    if capped != "any":
        t = t[t.ipl_capped == capped]
    st.dataframe(t.sort_values(score, ascending=False)[BOARD_COLS[kind]], hide_index=True, width="stretch")
    st.caption(
        f"{len(t)} players. ipl_link: strong = same Cricbuzz id across files; team_checked = Cricsheet name from the SMAT 2025 team-scoped link; "
        "name_only = matched by name, passed checks; doubtful = failed a check. ipl_capped: unknown = a possible IPL match was found but its identity is doubtful; no = no IPL match or no Cricsheet record at all. level = highest level reached in our data."
    )


def _player_tab():
    q = st.text_input("Player (name or Cricbuzz id)", key="sl_player", placeholder="Naman Dhir").strip()
    doubtful = st.checkbox("Show doubtful links", key="sl_doubtful", help="Cricsheet rows tied to this player by a name match that failed a check.")
    if not q:
        return
    try:
        df, withheld = _profile(q, doubtful)
    except NotExact as e:
        st.info(str(e).split(". candidates")[0])
        pick = st.radio("Which one?", e.candidates, key="sl_pick", format_func=lambda c: f"{c['name']} ({c['team']}, id {c['cricbuzz_id']})")
        if pick:
            df, withheld = _profile(str(pick["cricbuzz_id"]), doubtful)
        else:
            return
    st.dataframe(df, hide_index=True, width="stretch")
    if withheld and not doubtful:
        st.caption("Withheld (doubtful link): " + "; ".join(withheld))


def page():
    st.title("State leagues")
    if not P.available():
        st.warning("Cricbuzz scouting data is not on this machine.")
        return
    st.caption(
        "Cricbuzz scorecards (state T20 leagues and SMAT 2025) plus Cricsheet IPL / earlier SMAT / T20I. Name-only links can be wrong. "
        "SMAT 2026 is excluded until the live test ends (7 Dec 2026)."
    )
    board, player = st.tabs(["Board", "Player"])
    with board:
        _board_tab()
    with player:
        _player_tab()
