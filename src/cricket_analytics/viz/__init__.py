"""Plotly figures, one file per module: `viz/<module_id>.py` has `figure(result) -> go.Figure`.

Only the dashboard imports this package. Colours come from PALETTE so charts look alike.
"""

PALETTE = {
    "primary": "#2196F3",   # main series (runs, wickets)
    "secondary": "#FF9800",  # rolling average / second series
    "good": "#4CAF50",      # not out, wins, fours
    "bad": "#EF5350",       # out, losses, sixes
    "neutral": "#9E9E9E",   # dots, no result
    "light": "#90CAF9",
    "accent": "#E91E63",
    "phases": ["#2196F3", "#FF9800", "#F44336"],  # powerplay, middle, death
}


def subtitle(result) -> str:
    """'ipl, 2024, V Kohli' from the params the module ran with (group_by/min_balls/window left out)."""
    skip = {"group_by", "min_balls", "window", "role", "min_stands", "top", "include_super_overs"}
    return ", ".join(str(v) for k, v in result.meta["params"].items() if k not in skip)
