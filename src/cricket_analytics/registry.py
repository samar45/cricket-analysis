"""Module registry: one `@module(...)` decorated function per analysis, discovered by import."""

from dataclasses import dataclass, field
from typing import Callable

from .sql.fragments import PHASES

CATEGORIES = ("basic", "intermediate", "advanced", "experimental")
KINDS = (
    "player",
    "player2",
    "team",
    "opposition",
    "competition",
    "season",
    "venue",
    "phase",
    "int",
    "float",
    "bool",
    "choice",
)
MULTI_KINDS = ("team", "opposition", "season", "venue")


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str
    required: bool = False
    default: object = None
    choices: tuple | None = None
    help: str = ""
    multi: bool = False  # accepts one value or a list (JSON schema: an array)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"ParamSpec {self.name}: kind {self.kind!r} not in {KINDS}")
        if self.kind == "choice" and not self.choices:
            raise ValueError(f"ParamSpec {self.name}: kind 'choice' needs choices")
        if self.multi and self.kind not in MULTI_KINDS:
            raise ValueError(f"ParamSpec {self.name}: multi is only for {MULTI_KINDS}")
        if self.choices is not None:
            object.__setattr__(self, "choices", tuple(self.choices))


# The standard Filters fields as ready-made specs: params=[*std("player", "competition"), ...]
# "season" brings its range and last-N siblings with it, so a module that takes seasons takes all three ways.
_STD = {
    "player": ParamSpec(
        "player",
        "player",
        help="Exact player name as in the data, e.g. 'V Kohli' (use resolve first)",
    ),
    "player2": ParamSpec("player2", "player2", help="Second player (e.g. the bowler in a matchup)"),
    "competition": ParamSpec(
        "competition", "competition", help="Competition key; omit for all (men's)"
    ),
    "season": ParamSpec(
        "season",
        "season",
        multi=True,
        help="Cricsheet season label or a year, e.g. 2024; several allowed",
    ),
    "team": ParamSpec("team", "team", multi=True, help="Exact team name; several allowed"),
    "opposition": ParamSpec(
        "opposition", "opposition", multi=True, help="Exact opposition team name; several allowed"
    ),
    "venue": ParamSpec(
        "venue",
        "venue",
        multi=True,
        help="Exact venue name; several allowed (names contain commas, so pass a list)",
    ),
    "phase": ParamSpec("phase", "phase", help="powerplay | middle | death"),
}


_SEASON_RANGE = [
    ParamSpec(
        "season_from",
        "int",
        help="First year, inclusive (a season's year = year of its first match)",
    ),
    ParamSpec("season_to", "int", help="Last year, inclusive"),
    ParamSpec(
        "last_n_years",
        "int",
        help="The N most recent seasons of each competition (seasons, not calendar years)",
    ),
]

_SUPER_OVERS = ParamSpec(
    "include_super_overs",
    "bool",
    help="Count super-over innings (innings 3+); off by default, as in official records",
)


def std(*names: str, super_overs: bool = True) -> list[ParamSpec]:
    """Ready-made specs for Filters fields, plus `include_super_overs` (pass super_overs=False for modules
    that never read deliveries)."""
    out = [s for n in names for s in ([_STD[n], *_SEASON_RANGE] if n == "season" else [_STD[n]])]
    return out + ([_SUPER_OVERS] if super_overs else [])


@dataclass
class Module:
    id: str
    title: str
    category: str
    description: str
    params: list[ParamSpec]
    caveats: list[str]
    fn: Callable = field(repr=False)

    def spec(self, name: str) -> ParamSpec | None:
        return next((p for p in self.params if p.name == name), None)


_REGISTRY: dict[str, Module] = {}


def module(
    *,
    id: str,
    title: str,
    category: str,
    description: str,
    params: list[ParamSpec],
    caveats: list[str] | None = None,
):
    """Register `fn(f: Filters, **extra) -> DataFrame` as an analysis module."""
    if category not in CATEGORIES:
        raise ValueError(f"module {id}: bad category {category!r}")

    def deco(fn):
        if id in _REGISTRY:
            raise ValueError(f"Duplicate module id {id!r}")
        _REGISTRY[id] = Module(
            id, title, category, description, list(params), list(caveats or []), fn
        )
        return fn

    return deco


def _load() -> None:
    from . import analysis  # noqa: F401  (importing it imports every file in analysis/)


def get(module_id: str) -> Module:
    _load()
    if module_id not in _REGISTRY:
        raise ValueError(f"Unknown module {module_id!r}. Available: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[module_id]


def all_modules() -> list[Module]:
    _load()
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def _prop(p: ParamSpec) -> dict:
    from .competitions import COMPETITIONS

    t = dict(
        {
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "season": {"type": ["string", "integer"]},
        }.get(p.kind, {"type": "string"})
    )
    if p.kind == "competition":
        t["enum"] = list(COMPETITIONS)
    elif p.kind == "phase":
        t["enum"] = list(PHASES)
    elif p.kind == "choice":
        t["enum"] = list(p.choices)
    if p.multi:
        t = {"type": "array", "items": t}
    if p.help:
        t["description"] = p.help
    if p.default is not None:
        t["default"] = p.default
    return t


def json_schema(module_id: str) -> dict:
    """JSON Schema (draft 2020-12) of one module's params; usable as an LLM tool `input_schema`."""
    m = get(module_id)
    return {
        "type": "object",
        "title": m.id,
        "description": m.description,
        "properties": {p.name: _prop(p) for p in m.params},
        "required": [p.name for p in m.params if p.required],
        "additionalProperties": False,
    }
