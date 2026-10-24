"""Dashboard helpers: cached API calls and the widgets generated from a module's ParamSpecs."""

import streamlit as st

from cricket_analytics import api, competitions
from cricket_analytics.registry import Module, ParamSpec
from cricket_analytics.sql.fragments import PHASES

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
