"""Dashboard helpers: cached API calls and the widgets generated from a module's ParamSpecs."""

import streamlit as st

from cricket_analytics import api, competitions
from cricket_analytics.registry import Module, ParamSpec
from cricket_analytics.sql.fragments import PHASES

# Filter-like params keep one session key across modules, so choosing "ipl" survives a module switch.
SHARED = {"competition", "season", "team", "opposition", "venue", "player", "player2", "phase"}
ORDER = ("competition", "season")   # drawn first: the player/team/venue lists depend on them


@st.cache_data(ttl=3600, show_spinner="Running...")
def run(module_id: str, params: dict) -> api.Result:
    return api.run(module_id, **params)


@st.cache_data(ttl=3600, show_spinner=False)
def choices(kind: str, competition: str | None, season: str | None) -> list[str]:
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


def _widget(mod: Module, p: ParamSpec, ctx: dict):
    key = f"p_{p.name}" if p.name in SHARED else f"{mod.id}_{p.name}"
    label, help = p.name.replace("_", " ").capitalize(), p.help
    k = p.kind
    if k == "competition":
        return select(key, label, list(competitions.COMPETITIONS), none_label=comp_label(None), help=help,
                      format_func=comp_label)
    if k == "season":
        return select(key, label, choices("season", ctx.get("competition"), None), none_label="Any season", help=help)
    if k in ("player", "player2", "team", "opposition", "venue"):
        opts = choices(k, ctx.get("competition"), ctx.get("season") if k in ("player", "player2") else None)
        return select(key, label, opts, none_label=None if p.required else f"Any {k.rstrip('2')}", help=help)
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
    ordered = sorted(mod.params, key=lambda p: ORDER.index(p.name) if p.name in ORDER else len(ORDER))
    cols, values = st.columns(3), {}
    for i, p in enumerate(ordered):
        with cols[i % 3]:
            values[p.name] = _widget(mod, p, values)
    return {k: v for k, v in values.items() if v is not None and v is not False}
