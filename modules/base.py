"""Base module interface — every analysis module inherits from this.

Enforces a consistent interface so modules are composable,
callable from CLI, notebooks, and the dashboard interchangeably.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ModuleParams:
    """Standard filter parameters accepted by every module."""
    player: str | None = None       # batter / player 1 (H2H)
    player2: str | None = None      # bowler / player 2 (H2H)
    team: str | None = None
    season: int | list[int] | None = None
    format: str | None = None       # None/"All"=no filter | "IPL" | "T20" | "ODI" | "Test"
    venue: str | None = None
    opposition: str | None = None
    date_range: tuple[str, str] | None = None   # ("2023-01-01", "2023-12-31")
    phase: str | None = None        # powerplay | middle | death
    output: str = "dataframe"       # dataframe | plot | report
    extra: dict = field(default_factory=dict)


class BaseModule(ABC):
    """Abstract base class for all analysis modules."""

    # Subclasses must set these
    module_id: str = ""        # e.g. "B1", "I3"
    module_name: str = ""      # e.g. "Batting Scorecard & Career Stats"
    category: str = ""         # basic | intermediate | advanced

    # Declare which sidebar filters this module uses.
    # Dashboard renders only these, keeping UI clean per module.
    supported_filters: set[str] = frozenset({
        "format", "player", "team", "season", "venue", "phase"
    })

    @abstractmethod
    def run(self, params: ModuleParams) -> pd.DataFrame:
        """Execute the analysis and return a DataFrame of results."""
        ...

    def run_tabs(self, params: ModuleParams) -> dict[str, pd.DataFrame] | None:
        """Optional: return multiple named DataFrames rendered as dashboard tabs.

        Returns None if the module doesn't support tabbed views (most modules).
        Override in modules that produce multi-section results (e.g. B6 Venue).
        """
        return None

    def plot(self, df: pd.DataFrame, params: ModuleParams) -> Any:
        """Generate a visualisation from the results. Override in subclasses."""
        raise NotImplementedError(f"{self.module_id} does not implement plot()")

    def execute(self, params: ModuleParams) -> pd.DataFrame | Any:
        """Unified entry point: run analysis, optionally produce a plot."""
        df = self.run(params)
        if params.output == "plot":
            return self.plot(df, params)
        return df

    def _build_where_clauses(self, params: ModuleParams, table_prefix: str = "") -> tuple[str, list]:
        """Build SQL WHERE clauses from standard params. Returns (sql_fragment, bind_values)."""
        clauses = []
        values = []
        p = f"{table_prefix}." if table_prefix else ""

        fmt = params.format
        if fmt and fmt.lower() not in ("all", ""):
            clauses.append(f"{p}format = ?")
            values.append(fmt)

        if params.team:
            clauses.append(f"({p}team1 ILIKE ? OR {p}team2 ILIKE ?)")
            values.extend([f"%{params.team}%", f"%{params.team}%"])
        if params.season:
            if isinstance(params.season, list):
                placeholders = ", ".join("?" for _ in params.season)
                clauses.append(f"{p}season IN ({placeholders})")
                values.extend([str(s) for s in params.season])
            else:
                clauses.append(f"{p}season = ?")
                values.append(str(params.season))
        if params.venue:
            clauses.append(f"{p}venue ILIKE ?")
            values.append(f"%{params.venue}%")
        if params.date_range:
            clauses.append(f"{p}date BETWEEN ? AND ?")
            values.extend(list(params.date_range))

        where_sql = " AND ".join(clauses) if clauses else "1=1"
        return where_sql, values

    def _phase_clause(self, params: ModuleParams, table_prefix: str = "d") -> str:
        """Return a SQL AND clause for the phase filter, or empty string."""
        p = f"{table_prefix}." if table_prefix else ""
        if params.phase == "powerplay":
            return f"AND {p}over_num BETWEEN 0 AND 5"
        if params.phase == "middle":
            return f"AND {p}over_num BETWEEN 6 AND 14"
        if params.phase == "death":
            return f"AND {p}over_num BETWEEN 15 AND 19"
        return ""

    def __repr__(self):
        return f"<Module {self.module_id}: {self.module_name}>"


# --- Module Registry ---
_REGISTRY: dict[str, type[BaseModule]] = {}


def register_module(cls: type[BaseModule]) -> type[BaseModule]:
    """Decorator to register a module class in the global registry."""
    _REGISTRY[cls.module_id] = cls
    return cls


def get_module(module_id: str) -> BaseModule:
    """Instantiate and return a registered module by ID."""
    cls = _REGISTRY.get(module_id)
    if cls is None:
        raise KeyError(f"Module '{module_id}' not found. Available: {list(_REGISTRY.keys())}")
    return cls()


def list_modules() -> list[dict]:
    """List all registered modules."""
    return [
        {"id": mid, "name": cls.module_name, "category": cls.category}
        for mid, cls in sorted(_REGISTRY.items())
    ]
