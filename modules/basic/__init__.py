"""Basic analysis modules (B1-B6)."""

# Import all so they auto-register via @register_module
from modules.basic import (  # noqa: F401
    batting,
    bowling,
    team_performance,
    head_to_head,
    leaderboards,
    venue,
)
