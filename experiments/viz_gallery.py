"""Render every module's figure into ONE self-contained dark HTML page, to eyeball the charts.

Run: .venv\\Scripts\\python experiments\\viz_gallery.py [output.html]
The first 13 figures are one per module; the rest are the other branches (single player, by phase, ...).
"""

import importlib
import sys
import warnings
from pathlib import Path

from cricket_analytics import api

warnings.filterwarnings("ignore")
IPL = dict(competition="ipl")
KOHLI, ROHIT, BUMRAH = "V Kohli", "RG Sharma", "JJ Bumrah"

MAIN = [  # (label, module, params)
    ("batting", "batting", IPL),
    ("bowling", "bowling", IPL),
    ("teams", "teams", IPL),
    ("venues", "venues", IPL),
    ("matchup", "matchup", dict(IPL, player=KOHLI)),
    ("partnerships", "partnerships", IPL),
    ("form", "form", dict(IPL, player=KOHLI)),
    ("impact", "impact", IPL),
    ("true_performance", "true_performance", IPL),
    ("season_awards", "season_awards", dict(IPL, season=2024)),
    ("compare", "compare", dict(IPL, player=KOHLI, player2=ROHIT)),
    ("death_overs", "death_overs", IPL),
    ("pace_vs_spin", "pace_vs_spin", IPL),
]
EXTRA = [
    ("batting, no competition filter", "batting", {}),
    ("batting, one player", "batting", dict(IPL, player=KOHLI)),
    ("batting by phase (many)", "batting", dict(IPL, group_by="phase")),
    ("batting by phase (one)", "batting", dict(IPL, group_by="phase", player=KOHLI)),
    ("batting by season (many)", "batting", dict(IPL, group_by="season")),
    (
        "batting by season (one)",
        "batting",
        dict(IPL, group_by="season", player=KOHLI, include_super_overs=True),
    ),
    ("bowling, one player", "bowling", dict(IPL, player=BUMRAH)),
    ("bowling by phase (many)", "bowling", dict(IPL, group_by="phase")),
    ("bowling by season (one)", "bowling", dict(IPL, group_by="season", player=BUMRAH)),
    ("teams by season (many)", "teams", dict(IPL, group_by="season")),
    ("teams by season (one)", "teams", dict(IPL, group_by="season", team="Mumbai Indians")),
    ("venues by season", "venues", dict(IPL, group_by="season")),
    ("matchup duel", "matchup", dict(IPL, player=KOHLI, player2=BUMRAH)),
    ("partnerships by stand", "partnerships", dict(IPL, group_by="stand")),
    ("partnerships by wicket", "partnerships", dict(IPL, group_by="wicket")),
    ("form, bowler", "form", dict(IPL, player=BUMRAH, role="bowler")),
    ("true_performance, bowling", "true_performance", dict(IPL, role="bowling")),
    ("season_awards, bowling", "season_awards", dict(IPL, role="bowling")),
    ("compare, bowling", "compare", dict(IPL, player=BUMRAH, player2="YS Chahal", role="bowling")),
    ("death_overs, bowling", "death_overs", dict(IPL, role="bowling")),
    ("pace_vs_spin, team", "pace_vs_spin", dict(IPL, mode="team_vs_type")),
    ("pace_vs_spin, classification", "pace_vs_spin", dict(IPL, mode="bowler_classification")),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Cricket viz gallery</title><style>
body{{background:#0F131A;color:#E6EAF0;font-family:'Source Sans Pro',Segoe UI,sans-serif;margin:24px}}
.card{{width:700px;margin:0 0 28px;background:#0F131A;border:1px solid #232b38;border-radius:8px;padding:8px}}
h1{{font-size:22px}} h2{{font-size:14px;color:#9AA4B2;margin:0 0 4px}}
</style></head><body><h1>Cricket viz gallery</h1>{body}</body></html>"""


def main(out: str) -> None:
    cards, first = [], True
    for label, mod, params in MAIN + EXTRA:
        try:
            fig = importlib.import_module(f"cricket_analytics.viz.{mod}").figure(
                api.run(mod, **params)
            )
            html = fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False)
            first = False
        except Exception as e:  # noqa: BLE001  (a gallery should show what broke, not stop)
            html = f"<p style='color:#EF5350'>{type(e).__name__}: {e}</p>"
            print("FAILED", label, type(e).__name__, e)
        cards.append(f"<div class='card'><h2>{label}: {mod} {params}</h2>{html}</div>")
    Path(out).write_text(PAGE.format(body="\n".join(cards)), encoding="utf-8")
    print("wrote", out, f"({len(cards)} figures)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "viz_gallery.html")
