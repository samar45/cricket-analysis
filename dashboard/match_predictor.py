"""Match predictor page: live state forecast, replay of a past match, pre-match forecast.

All numbers come from `cricket_analytics.ml.predict` (first-innings score range = G1 direct model alone; win probability = G1 and the sim-B ball simulator averaged 50/50; see docs/ML_PREDICTION.md section 9) and, for the
Pre-match tab, `cricket_analytics.ml.prematch`. Every computation sits behind a Run button.
"""

import importlib.util

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import ui

import cricket_analytics.viz  # noqa: F401  (registers the shared plotly template)
from cricket_analytics.ml import predict as P

OVERS_HELP = "Overs bowled, e.g. 10.0 or 10.3 (10 overs and 3 balls)."


@st.cache_resource(show_spinner="Loading models (first time only)...")
def _warm():
    P.warm()
    return True


@st.cache_data(ttl=3600, show_spinner=False)
def _lists(comp: str):
    return P.venues(comp), P.teams(comp)


@st.cache_data(ttl=3600, show_spinner=False)
def _players(comp: str, team: str, role: str):
    return P.players(comp, team, role)


@st.cache_data(show_spinner="Simulating...")
def _state(params: tuple):
    return P.predict_state(**dict(params))


@st.cache_data(show_spinner="Replaying every over (about 10 s)...")
def _curve(match_id: str, n_sims: int):
    return P.predict_match_curve(match_id, n_sims=n_sims)


def pct(x) -> str:
    return "-" if x is None or pd.isna(x) else f"{100 * x:.0f}%"


# ---------- tab 1: live state ----------
def live_tab():
    c1, c2, c3 = st.columns(3)
    with c1:
        comp = ui.select("mp_comp", "Competition", P.competitions(), format_func=ui.comp_label, index=P.competitions().index("ipl"))
    venues, teams = _lists(comp)
    with c2:
        venue = ui.select("mp_venue", "Venue", venues)
    with c3:
        innings = st.radio("Innings", [1, 2], format_func=lambda i: "1st innings (batting first)" if i == 1 else "2nd innings (chasing)", key="mp_innings", horizontal=True)
    a, b = st.columns(2)
    with a:
        bat = ui.select("mp_bat", "Batting team", teams)
    with b:
        bowl = ui.select("mp_bowl", "Bowling team", [t for t in teams if t != bat])
    r1, r2, r3, r4 = st.columns(4)
    runs = r1.number_input("Runs", 0, 400, 60, key="mp_runs")
    wk = r2.number_input("Wickets down", 0, 9, 2, key="mp_wk")
    overs = r3.number_input("Overs", 0.0, 19.5, 5.0, step=0.1, format="%.1f", help=OVERS_HELP, key="mp_overs")
    target = r4.number_input("Target", 1, 500, 180, key="mp_target", disabled=innings == 1)
    with st.expander("Players (optional; average players are used otherwise)"):
        p1, p2, p3 = st.columns(3)
        bats, bowls = _players(comp, bat, "bat"), _players(comp, bowl, "bowl")
        with p1:
            striker = ui.select("mp_striker", "Striker", bats, none_label="Average batter")
        with p2:
            non = ui.select("mp_non", "Non-striker", [x for x in bats if x != striker], none_label="Average batter")
        with p3:
            bowler = ui.select("mp_bowler", "Bowler", bowls, none_label="Average bowler")
    try:
        P.parse_overs(overs)
    except ValueError as e:
        st.warning(str(e))
        return
    params = {"competition": comp, "venue": venue, "batting_team": bat, "bowling_team": bowl, "innings": innings, "runs": int(runs),
              "wickets": int(wk), "overs": round(float(overs), 1), "target": int(target) if innings == 2 else None,
              "striker": striker, "non_striker": non, "bowler": bowler}
    run = ui.gate("mp_live", params, "Predict")
    if run is None:
        return
    _warm()
    with st.container(key="res_mp_live"):
        _live_result(_state(tuple(sorted(run.items()))), run)


def _live_result(r: dict, p: dict):
    chase = r["innings"] == 2
    q = r["score"]
    st.caption(f"{p['batting_team']} {r['runs']}/{r['wickets']} after {p['overs']:.1f} overs"
               + (f", chasing {r['target']}" if chase else "") + f" at {r['venue']}. Scoring level used: {r['level']:.0f} runs per 120 balls (matches before {r['date']}).")
    if r.get("finished"):
        st.info("The innings is already over: " + (f"{p['batting_team']} {'won' if r['win']['bat'] == 1 else 'lost' if r['win']['bat'] == 0 else 'tied'}." if chase else f"final score {r['runs']}."))
        return
    k = st.columns(3)
    k[0].metric("Predicted final score" if not chase else "Projected score (stops at target)", f"{q['q50']:.0f}")
    k[0].caption(f"80% range: {q['q10']:.0f} to {q['q90']:.0f}")
    k[1].metric(f"{p['batting_team']} win", pct(r["win"]["bat"]))
    k[2].metric(f"{p['bowling_team']} win", pct(r["win"]["bowl"]))
    g, s = r["g1"], r["sim"]
    rows = [{"model": "G1 (direct model)", "q10": g.get("q10"), "median": g.get("q50"), "q90": g.get("q90"), f"{p['batting_team']} win": g.get("win_bat")},
            {"model": "Simulator (sim-B)", "q10": s["q10"], "median": s["q50"], "q90": s["q90"], f"{p['batting_team']} win": s["win_bat"]},
            {"model": "Shown above (score: G1 in the first innings, simulator in a chase; win: blend)", "q10": q["q10"], "median": q["q50"], "q90": q["q90"], f"{p['batting_team']} win": r["win"]["bat"]}]
    t = pd.DataFrame(rows)
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        "q10": st.column_config.NumberColumn("10%", format="%.0f"), "median": st.column_config.NumberColumn("median", format="%.0f"),
        "q90": st.column_config.NumberColumn("90%", format="%.0f"), f"{p['batting_team']} win": st.column_config.NumberColumn(f"{p['batting_team']} win", format="percent")})
    if chase:
        st.caption("Chase: only the simulator projects a score (the direct score model is first-innings only), and a chase stops once the target is reached.")
    fig = go.Figure(go.Histogram(x=r["sims"], xbins=dict(size=4), marker_color="#4c9be8", name="simulated final scores"))
    for lab, x, col in (("10%", q["q10"], "#888"), ("median", q["q50"], "#e0a800"), ("90%", q["q90"], "#888")):
        fig.add_vline(x=x, line_dash="dot", line_color=col, annotation_text=lab, annotation_position="top")
    if chase:
        fig.add_vline(x=r["target"], line_color="#e5534b", annotation_text="target", annotation_position="top right")
    fig.update_layout(height=300, showlegend=False, xaxis_title="final score (simulator, 1,000 paths)", yaxis_title="paths", margin=dict(t=36))
    st.plotly_chart(fig, width="stretch", theme=None)
    kn = r["players_known"]
    if any(not kn[k] for k in kn if p.get(k)):
        st.caption("A chosen player has no earlier data, so an average player was used.")


# ---------- tab 2: replay ----------
def replay_tab():
    c1, c2 = st.columns(2)
    with c1:
        comp = ui.select("mp_rcomp", "Competition", P.competitions(), format_func=ui.comp_label, index=P.competitions().index("ipl"))
    allm = P.matches(comp)
    seasons = sorted(allm.season_year.unique(), reverse=True)
    with c2:
        season = ui.select("mp_rseason", "Season", seasons)
    m = allm[allm.season_year == season]
    pick = ui.select("mp_rmatch", "Match", m.match_id.tolist(), format_func=lambda i: m.set_index("match_id").label[i])
    run = ui.gate("mp_replay", {"match": pick}, "Replay")
    if run is None:
        return
    _warm()
    with st.container(key="res_mp_replay"):
        curve, meta = _curve(run["match"], 200)
        _replay_result(curve, meta)


def _replay_result(c: pd.DataFrame, meta: dict):
    t1, t2 = meta["team1"], meta["team2"]
    res = f"{meta['winner']} won" if meta["winner"] else meta.get("result") or "no result"
    st.markdown(f"**{t1} {meta['score1']}/{meta['wk1']}**, **{t2} {meta['score2']}/{meta['wk2']}** (target {meta['target']}). {res}. {meta['venue']}, {meta['date']}.")
    if meta["in_sample"]:
        st.caption("The models were trained on this match, so the curve is flattering. Use it to see the shape, not the accuracy.")
    w = c[c.innings == 2]
    fig = go.Figure()
    fig.add_hline(y=0.5, line_dash="dot", line_color="#888")
    for col, name, style in (("win_g1", "G1 (direct)", dict(width=1.5)), ("win_sim", "Simulator", dict(width=1.5)), ("win_ens", "Blend", dict(width=3.5, color="#e0a800"))):
        fig.add_scatter(x=w.over, y=w[col], mode="lines+markers", name=name, line=style, marker=dict(size=5))
    fig.update_layout(height=360, yaxis=dict(range=[0, 1], tickformat=".0%", title=f"P({t2} win)"), xaxis_title="overs bowled in the chase",
                      title=dict(text=f"{t2} chasing {meta['target']}: win probability after each over"))
    st.plotly_chart(fig, width="stretch", theme=None)
    f = c[c.innings == 1]
    fig2 = go.Figure()
    fig2.add_scatter(x=f.over, y=f.ens_q90, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig2.add_scatter(x=f.over, y=f.ens_q10, mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(76,155,232,0.25)", name="10-90% range")
    fig2.add_scatter(x=f.over, y=f.ens_q50, mode="lines+markers", line=dict(width=3, color="#e0a800"), marker=dict(size=5), name="predicted total (G1)")
    fig2.add_hline(y=meta["score1"], line_color="#e5534b", annotation_text=f"actual {meta['score1']}", annotation_position="bottom right")
    fig2.update_layout(height=330, yaxis_title=f"{t1} projected total", xaxis_title="overs bowled in the 1st innings",
                       title=dict(text=f"{t1} batting first: projected final score after each over"))
    st.plotly_chart(fig2, width="stretch", theme=None)
    with st.expander("Numbers per over"):
        show = c.drop(columns=["balls"]).round(2)
        st.dataframe(show, hide_index=True, width="stretch")


# ---------- tab 3: pre-match ----------
def prematch_tab():
    if importlib.util.find_spec("cricket_analytics.ml.prematch") is None:
        st.info("Pre-match forecast: coming soon.")
        return
    from cricket_analytics.ml import prematch

    c1, c2, c3 = st.columns(3)
    with c1:
        comp = ui.select("mp_pcomp", "Competition", P.competitions(), format_func=ui.comp_label, index=P.competitions().index("ipl"))
    venues, teams = _lists(comp)
    with c2:
        venue = ui.select("mp_pvenue", "Venue", venues)
    with c3:
        toss = ui.select("mp_ptoss", "Toss (optional)", ["a bats", "a fields", "b bats", "b fields"], none_label="Not known")
    a, b = st.columns(2)
    with a:
        ta = ui.select("mp_pa", "Team A", teams)
    with b:
        tb = ui.select("mp_pb", "Team B", [t for t in teams if t != ta])
    params = {"competition": comp, "venue": venue, "team_a": ta, "team_b": tb, "toss": toss}
    run = ui.gate("mp_pre", params, "Predict")
    if run is None:
        return
    kw = {"competition": comp, "venue": venue, "team_a": ta, "team_b": tb}
    if run["toss"]:
        side, dec = run["toss"].split()
        kw.update(toss_winner=ta if side == "a" else tb, toss_decision="bat" if dec == "bats" else "field")
    with st.container(key="res_mp_pre"):
        try:
            r = prematch.predict(**kw)
        except FileNotFoundError:
            st.info("Pre-match forecast: coming soon (model not trained yet).")
            return
        k = st.columns(3)
        k[0].metric(f"{ta} win", pct(r["p_a_win"]))
        k[1].metric(f"{tb} win", pct(1 - r["p_a_win"]))
        k[2].metric("Venue effect (runs)", f"{r['parts']['venue_effect']:+.1f}")
        st.dataframe(pd.DataFrame([
            {"team": ta, "if batting first": f"{r['score_a_q50']:.0f}", "range 10-90%": f"{r['score_a_q10']:.0f} to {r['score_a_q90']:.0f}"},
            {"team": tb, "if batting first": f"{r['score_b_q50']:.0f}", "range 10-90%": f"{r['score_b_q10']:.0f} to {r['score_b_q90']:.0f}"}]),
            hide_index=True, width="stretch")
        st.caption(r["parts"]["note"])


# ---------- tab 4: luck & surprises ----------
@st.cache_data(show_spinner="Reading the cached win-probability curves...")
def _luck(comp: str, season: int):
    from cricket_analytics.ml import luck

    tl = luck.team_luck(comp, season)
    tl["luck (chase-adjusted)"] = luck.team_luck(comp, season, adjust=True).set_index("team").luck.reindex(tl.team).to_numpy()
    return tl, luck.top_matches(comp, season, "surprise"), luck.top_matches(comp, season, "swing")


def _match_table(t: pd.DataFrame, cols: dict) -> pd.DataFrame:
    out = pd.DataFrame({"date": t.date.astype(str), "match": t.chaser + " chased " + t.setter, "winner": t.winner})
    for k, v in cols.items():
        out[v] = t[k]
    out["decisive over"] = [f"over {o + 1}: {w['runs']} runs, {w['wickets']} wkts" for o, w in zip(t.decisive_over, t.decisive_what)]
    return out


def luck_tab():
    from cricket_analytics.ml import luck

    c1, c2 = st.columns(2)
    with c1:
        comp = ui.select("mp_lcomp", "Competition", list(luck.COMPS), format_func=ui.comp_label)
    with c2:
        season = ui.select("mp_lseason", "Season", [2026, 2025, 2024, 2023, 2022])
    run = ui.gate("mp_luck", {"comp": comp, "season": season}, "Run")
    if run is None:
        return
    with st.container(key="res_mp_luck"):
        tl, sur, sw = _luck(run["comp"], run["season"])
        st.markdown("**Team luck:** actual wins minus the wins the model expected before each chase (+ = luckier).")
        st.dataframe(tl, hide_index=True, width="stretch", column_config={
            "expected": st.column_config.NumberColumn(format="%.1f"), "luck": st.column_config.NumberColumn(format="%+.1f"),
            "luck (chase-adjusted)": st.column_config.NumberColumn(format="%+.1f"), "z": st.column_config.NumberColumn("z (luck / noise)", format="%+.1f")})
        st.caption("Chase-adjusted removes the season's gap between how often chasers really won and how often the model expected. |z| under 2 is within normal noise.")
        st.markdown("**Most surprising results:** the winner's chance at the start of the chase was lowest.")
        st.dataframe(_match_table(sur, {"p_winner_start": "winner's chance at start", "comeback_low": "winner's worst moment"}), hide_index=True, width="stretch",
                     column_config={"winner's chance at start": st.column_config.NumberColumn(format="percent"), "winner's worst moment": st.column_config.NumberColumn(format="percent")})
        st.markdown("**Most swingy matches:** the most total movement in win probability.")
        st.dataframe(_match_table(sw, {"swing": "swing (sum of moves)", "lead_changes": "lead changes"}), hide_index=True, width="stretch",
                     column_config={"swing (sum of moves)": st.column_config.NumberColumn(format="%.2f")})
        st.caption("Probabilities are out-of-sample (the models had not seen the match). Decided chases only. Curve = direct model per over; start = blend with the simulator. Predicted total = G1 alone.")


def page():
    st.title("Match predictor")
    st.caption("First-innings score range: direct model (G1) alone (about 1.6 runs better than a level-scaled DLS-style table in other leagues; about a tie in the IPL); win probability: G1 and the ball-by-ball simulator (sim-B), averaged. Men's 20-over cricket only. Nothing runs until you click.")
    live, replay, pre, lk = st.tabs(["Live state", "Replay a match", "Pre-match", "Luck & surprises"])
    with live:
        live_tab()
    with replay:
        replay_tab()
    with pre:
        prematch_tab()
    with lk:
        luck_tab()
