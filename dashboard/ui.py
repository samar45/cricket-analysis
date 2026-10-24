"""Dashboard helpers: cached API calls and the widgets generated from a module's ParamSpecs."""

import importlib.util

import streamlit as st
import streamlit.components.v1 as components

from cricket_analytics import api, competitions
from cricket_analytics.registry import Module, ParamSpec
from cricket_analytics.sql.fragments import PHASES
from cricket_analytics.viz import video

# Filter-like params keep one session key across modules, so choosing "ipl" survives a module switch.
SHARED = {"competition", "season", "team", "opposition", "venue", "player", "player2", "phase",
          "season_from", "season_to", "last_n_years"}
ORDER = ("competition", "season")   # drawn first: the player/team/venue lists depend on them
SEASON_EXTRAS = ("season_from", "season_to", "last_n_years")   # drawn by the season control, not one by one
SEASON_MODES = ("Single seasons", "Year range", "Last N seasons")


@st.cache_data(ttl=3600, show_spinner="Running...")
def run(module_id: str, params: dict) -> api.Result:
    return api.run(module_id, **params)


@st.cache_data(ttl=3600, show_spinner=False)
def choices(kind: str, competition: str | None, season: list | None) -> list[str]:
    return api.choices(kind, competition, season)


@st.cache_data(ttl=3600, show_spinner=False)
def data_info() -> dict:
    return api.data_info()


def comp_label(key: str | None) -> str:
    if key is None:
        return "All competitions (men's)"
    return competitions.COMPETITIONS[key].label if key in competitions.COMPETITIONS else key


def select(key: str, label: str, options: list, *, none_label: str | None = None, help: str | None = None,
           format_func=str, index: int = 0):
    """selectbox that forgets a stored value no longer in `options` (e.g. a player who is not in the new competition)."""
    if none_label:
        options = [None] + list(options)
        fmt = lambda o: none_label if o is None else format_func(o)  # noqa: E731
    else:
        fmt = format_func
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    return st.selectbox(label, options, index=min(index, len(options) - 1), key=key, help=help or None,
                        format_func=fmt)


def multiselect(key: str, label: str, options: list, *, help: str | None = None, placeholder: str = "All"):
    """multiselect that drops stored values no longer in `options`; nothing selected = no filter."""
    if key in st.session_state:
        st.session_state[key] = [v for v in st.session_state[key] if v in options]
    return st.multiselect(label, options, key=key, help=help or None, placeholder=placeholder)


def season_control(mod: Module, ctx: dict) -> dict:
    """Season mode (single seasons / year range / last N seasons) -> the season, season_from, season_to, last_n_years params."""
    mode = st.radio("Seasons", SEASON_MODES, horizontal=True, key="p_season_mode",
                    help="One season tells a story, several show a pattern. Last N counts seasons of each competition.")
    if mode == SEASON_MODES[0]:
        opts = choices("season", ctx.get("competition"), None)
        return {"season": multiselect("p_season", "Season", opts, help=mod.spec("season").help, placeholder="Any season")}
    if mode == SEASON_MODES[1]:
        years = sorted({int(s[:4]) for s in choices("season", ctx.get("competition"), None)})
        a, b = st.columns(2)
        with a:
            lo = select("p_season_from", "From year", years, none_label="Earliest", help=mod.spec("season_from").help)
        with b:
            hi = select("p_season_to", "To year", years, none_label="Latest", help=mod.spec("season_to").help)
        return {"season_from": lo, "season_to": hi}
    n = st.number_input("Last N seasons", min_value=1, value=5, step=1, key="p_last_n_years", help=mod.spec("last_n_years").help)
    return {"last_n_years": int(n)}


def _widget(mod: Module, p: ParamSpec, ctx: dict):
    key = f"p_{p.name}" if p.name in SHARED else f"{mod.id}_{p.name}"
    label, help = p.name.replace("_", " ").capitalize(), p.help
    k = p.kind
    if k == "competition":
        return select(key, label, list(competitions.COMPETITIONS), none_label=comp_label(None), help=help,
                      format_func=comp_label)
    if k in ("team", "opposition", "venue"):
        return multiselect(key, label, choices(k, ctx.get("competition"), None), help=help, placeholder=f"Any {k}")
    if k in ("player", "player2"):
        opts = choices(k, ctx.get("competition"), ctx.get("season"))
        return select(key, label, opts, none_label=None if p.required else "Any player", help=help)
    if k == "phase":
        return select(key, label, list(PHASES), none_label="All phases", help=help)
    if k == "choice":
        return select(key, label, list(p.choices), help=help, index=list(p.choices).index(p.default) if p.default in p.choices else 0)
    if k == "bool":
        return st.toggle(label, value=bool(p.default), key=key, help=help or None)
    if k == "float":
        return st.number_input(label, value=p.default, min_value=0.0, step=0.1, format="%g", key=key, help=help or None)
    return st.number_input(label, value=p.default, min_value=0, step=1, key=key, help=help or None)


def param_form(mod: Module) -> dict:
    """One widget per ParamSpec; returns only the params the user set (unset / off ones are left out)."""
    has_season = mod.spec("season") is not None and all(mod.spec(n) for n in SEASON_EXTRAS)
    shown = [p for p in mod.params if not (has_season and p.name in SEASON_EXTRAS)]
    ordered = sorted(shown, key=lambda p: ORDER.index(p.name) if p.name in ORDER else len(ORDER))
    cols, values = st.columns(3), {}
    for i, p in enumerate(ordered):
        with cols[i % 3]:
            if p.name == "season" and has_season:
                values.update(season_control(mod, values))
            else:
                values[p.name] = _widget(mod, p, values)
    return {k: v for k, v in values.items() if v is not None and v is not False and v != []}


VIDEO_ASPECTS = {"9:16": 640, "1:1": 360}   # preview height in px; every preview is 360 px wide, like a phone screen
_CHECKER = ("background-color:#1b1f26;background-image:linear-gradient(45deg,#272c35 25%,transparent 25%,transparent 75%,#272c35 75%),"
            "linear-gradient(45deg,#272c35 25%,transparent 25%,transparent 75%,#272c35 75%);background-size:32px 32px;"
            "background-position:0 0,16px 16px;")


def has_video(module_id: str) -> bool:
    return module_id in video.module_ids()


def video_preview_html(fig, aspect: str) -> str:
    """The 1080 px wide figure shrunk to 360 px wide on a checkerboard (so the transparency shows). Needs internet for plotly.js."""
    inner = fig.to_html(full_html=False, include_plotlyjs="cdn", config=dict(staticPlot=True, displayModeBar=False))
    return (f"<body style='margin:0'><div style='width:360px;height:{VIDEO_ASPECTS[aspect]}px;overflow:hidden;position:relative;{_CHECKER}'>"
            f"<div style='transform:scale(.33333);transform-origin:0 0;width:1080px;position:absolute;left:0;top:0'>{inner}</div></div></body>")


def video_tab(module_id: str, result) -> None:
    """Preview of the module's video figure (viz/video/<id>.py) at phone width, plus downloads."""
    a, b = st.columns([1, 2])
    aspect = a.radio("Shape", list(VIDEO_ASPECTS), horizontal=True, key="video_aspect")
    focus = b.text_input("Focus (optional)", key=f"video_focus_{module_id}", help="Picks one view in modules that have several: a player name, a phase, 'leaders'... Empty = the default view.")
    fig = video.video_figure(module_id, result, aspect, focus or None)
    components.html(video_preview_html(fig, aspect), width=380, height=VIDEO_ASPECTS[aspect] + 8)
    name = f"{module_id}_{aspect.replace(':', 'x')}"
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("Download HTML", fig.to_html(include_plotlyjs="cdn"), f"{name}.html", "text/html", key="video_html")
    if importlib.util.find_spec("kaleido"):
        if c2.button("Make PNG", key="video_png_make"):   # exports at 1080 px wide (the figure's own size)
            c2.download_button("Download PNG", fig.to_image(format="png"), f"{name}.png", "image/png", key="video_png")
    else:
        c2.caption("PNG needs kaleido: `pip install kaleido` (not installed).")
