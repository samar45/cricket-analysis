"""Render every video figure (viz/video/*) into ONE HTML page: each at 9:16 (shown 360x640) and 1:1 (360x360) on a
dark checkerboard, so transparency is visible.

Run: .venv\\Scripts\\python experiments\\video_gallery.py [output.html]
"""

import sys
import warnings
from pathlib import Path

from cricket_analytics import api
from cricket_analytics.viz import video

warnings.filterwarnings("ignore")
IPL = dict(competition="ipl")
KOHLI, ROHIT, BUMRAH = "V Kohli", "RG Sharma", "JJ Bumrah"

# (label, module, params, focus)
CASES = [
    ("batting: one player", "batting", dict(IPL, player=KOHLI), None),
    ("batting: by season", "batting", dict(IPL, player=KOHLI, group_by="season"), None),
    ("batting: by phase", "batting", dict(IPL, player=KOHLI, group_by="phase"), None),
    ("batting: leaders", "batting", IPL, None),
    ("bowling: how wickets fell", "bowling", dict(IPL, player=BUMRAH), None),
    ("bowling: by phase", "bowling", dict(IPL, player=BUMRAH, group_by="phase"), None),
    ("bowling: by season", "bowling", dict(IPL, player=BUMRAH, group_by="season"), None),
    ("bowling: leaders", "bowling", IPL, "leaders"),
    ("teams: one team", "teams", dict(IPL, team="Mumbai Indians"), None),
    ("teams: who wins most", "teams", IPL, None),
    ("venues", "venues", dict(IPL, venue="Wankhede Stadium"), None),
    ("matchup", "matchup", dict(IPL, player=KOHLI, player2=BUMRAH), None),
    ("partnerships: pairs", "partnerships", IPL, None),
    ("partnerships: stands", "partnerships", dict(IPL, group_by="stand"), None),
    ("form: batter", "form", dict(IPL, player=KOHLI), None),
    ("form: bowler", "form", dict(IPL, player=BUMRAH, role="bowler"), None),
    ("impact", "impact", IPL, None),
    ("true_performance", "true_performance", dict(IPL, player=KOHLI), None),
    ("season_awards", "season_awards", dict(IPL, season=2024), "death"),
    ("compare: batters", "compare", dict(IPL, player=KOHLI, player2=ROHIT), None),
    ("compare: bowlers", "compare", dict(IPL, player=BUMRAH, player2="YS Chahal", role="bowling"), None),
    ("death_overs", "death_overs", dict(IPL, player=KOHLI), None),
    ("pace_vs_spin", "pace_vs_spin", dict(IPL, player=KOHLI), None),
    ("player_profile: batter", "player_profile", dict(player=KOHLI), None),
    ("player_profile: bowler", "player_profile", dict(IPL, player=BUMRAH), None),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Video chart gallery</title><style>
body{{background:#0b0d10;color:#e6eaf0;font-family:Segoe UI,sans-serif;margin:24px}}
h1{{font-size:22px}} .row{{display:flex;gap:24px;align-items:flex-start;margin:0 0 36px}}
h2{{font-size:14px;color:#9aa4b2;margin:0 0 6px;font-weight:600}}
.checker{{background-color:#1b1f26;background-image:linear-gradient(45deg,#272c35 25%,transparent 25%,transparent 75%,#272c35 75%),
linear-gradient(45deg,#272c35 25%,transparent 25%,transparent 75%,#272c35 75%);background-size:32px 32px;background-position:0 0,16px 16px;
overflow:hidden;position:relative;border:1px solid #333}}
.s{{transform:scale(.33333);transform-origin:0 0;width:1080px;position:absolute;left:0;top:0}}
</style></head><body><h1>Video chart gallery (9:16 and 1:1, transparent background on a checkerboard)</h1>{body}</body></html>"""


def shown(fig, h: int, first: bool) -> str:
    html = fig.to_html(full_html=False, include_plotlyjs=True if first else False,
                       config=dict(staticPlot=True, displayModeBar=False))
    return f"<div class='checker' style='width:360px;height:{h}px'><div class='s'>{html}</div></div>"


def main(out: str) -> None:
    rows, first = [], True
    for label, mod, params, focus in CASES:
        cells = []
        for aspect, h in (("9:16", 640), ("1:1", 360)):
            try:
                fig = video.video_figure(mod, api.run(mod, **params), aspect, focus)
                cells.append(f"<div><h2>{aspect}</h2>{shown(fig, h, first)}</div>")
                first = False
            except Exception as e:  # noqa: BLE001  (a gallery should show what broke, not stop)
                cells.append(f"<p style='color:#EF5350'>{type(e).__name__}: {e}</p>")
                print("FAILED", label, aspect, type(e).__name__, e)
        rows.append(f"<h2>{label}: {mod} {params} focus={focus}</h2><div class='row'>{''.join(cells)}</div>")
    Path(out).write_text(PAGE.format(body="\n".join(rows)), encoding="utf-8")
    print("wrote", out, f"({len(CASES)} cases)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "video_gallery.html")
