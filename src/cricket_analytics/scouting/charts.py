"""Reel PNGs for SMAT scouting: scout_innings (a player's innings in date order) and scout_rank (top 10 uncapped).
Transparent, 960x980 by default, drawn with matplotlib + the reel TTFs (viz/match_reel.Canvas). palette = {bg, ink, a1, a2}: ink text, a1 highlight, a2 second series, bg text on a1 bars."""
import json
from pathlib import Path

import matplotlib.colors as mc
import pandas as pd

from ..viz.match_reel import PX, Canvas
from ..viz.video import AMBER, INK, RED, num, short_name
from . import reels
from .smat2025 import ROOT

DEFAULT = dict(bg="#111111", ink=INK, a1=AMBER, a2=RED)
CHARTS = ("scout_innings", "scout_rank")


def parse_palette(s: str | None) -> dict:
    p = {**DEFAULT, **(json.loads(s) if s else {})}
    bad = set(p) - set(DEFAULT)
    if bad:
        raise ValueError(f"palette keys must be bg, ink, a1, a2 (got {sorted(bad)})")
    return p


def parse_size(s: str | None) -> tuple[int, int]:
    try:
        return tuple(int(x) for x in s.lower().split("x")) if s else (960, 980)  # type: ignore
    except ValueError:
        raise ValueError(f"--size must look like 1080x1920, not {s!r}")


def _rgba(c, a=0.55):
    return mc.to_rgba(c, a)


def _header(cv, title, sub, big, big_label, note):
    """Title, subtitle, one big number (top right) and the footnote; returns the top of the plot area in pixels."""
    k, w = cv.k, cv.w
    cv.text(40 * k, 24 * k, title.upper(), 54, "lab")
    cv.text(40 * k, 92 * k, sub, 26, "lab", cv.pal["a1"])
    if big:
        cv.text(w - 40 * k, 0, big, 170, "num", cv.pal["a1"], "right")
        cv.text(w - 40 * k, 176 * k, big_label, 24, "lab", alpha=0.55, ha="right")
    cv.text(40 * k, cv.h - 14 * k, note, 20, "lab", alpha=0.55, va="bottom")
    return 215 * k


def innings(cv, player: str):
    pal, k = cv.pal, cv.k
    c = reels.resolve(player)
    role = c["role"]
    d = pd.read_parquet(ROOT / (("batting" if role == "bat" else "bowling") + ".parquet"))
    d = d[d.cricbuzz_id == c["cricbuzz_id"]].merge(reels._games()[["match_id", "date", "team1", "team2"]], on="match_id").sort_values("date")
    t = reels.table(role).set_index("cricbuzz_id").loc[c["cricbuzz_id"]]
    opp = [b if a == tm else a for a, b, tm in zip(d.team1, d.team2, d.team)]
    y = d.runs if role == "bat" else d.wickets
    best = int(y.values.argmax())
    if role == "bat":  # most runs, ties by strike rate (same rule as the facts file)
        best = list(d.index).index(d.assign(s=d.runs / d.balls.clip(lower=1)).sort_values(["runs", "s"]).index[-1])
    big = f"{int(t.runs)}" if role == "bat" else f"{int(t.wkts)}"
    lab = f"RUNS | SR {t.sr}" if role == "bat" else f"WICKETS | ECON {t.econ}"
    note = f"Source: Cricbuzz SMAT 2025-26 | data to {str(reels._games().date.max())[:10]}"
    top = _header(cv, c["name"], f"{t.team} | {'EVERY INNINGS' if role == 'bat' else 'EVERY SPELL'}", big, lab, note)
    ymax = max(y.max(), 1) * 1.25
    lg = reels.league()["sr"] if role == "bat" else None
    if lg:
        ymax = max(ymax, max(lg * d.balls / 100) * 1.25)
        cv.text(40 * k, 150 * k, "- - average batter, same balls", 22, "lab", pal["a2"])
    ax = cv.axes(40 * k, top + 20 * k, cv.w - 40 * k, cv.h - 110 * k)
    ax.set_xlim(-0.6, len(d) - 0.4), ax.set_ylim(0, ymax), ax.axis("off")
    x = list(range(len(d)))
    ax.bar(x, y, width=0.7, color=[pal["a1"] if i == best else _rgba(pal["ink"]) for i in x])
    for i, v in enumerate(y):
        ax.text(i, v + ymax * 0.01, f"{int(v)}", ha="center", va="bottom", fontproperties=cv.num, fontsize=56 * k * PX, color=pal["ink"])
    for i, o in enumerate(opp):
        ax.text(i, -ymax * 0.03, short_name(o)[:3].upper(), ha="center", va="top", fontproperties=cv.lab, fontsize=22 * k * PX, color=_rgba(pal["ink"]))
    if lg:  # a league-average batter's runs off the same balls: dashed tick over each bar
        for i, b in enumerate(d.balls):
            ax.plot([i - 0.45, i + 0.45], [lg * b / 100] * 2, color=pal["a2"], lw=4 * k, ls=(0, (3, 2)))


def rank(cv, role: str, focus: str | None = None, n: int = 10):
    pal, k = cv.pal, cv.k
    t = reels.table(role)
    t = t[t.t20i == "uncapped"]
    rows = t.head(n)
    big, lab = "", "RUNS ABOVE AVERAGE" if role == "bat" else "RUNS SAVED vs AVERAGE"
    f = None
    if focus:
        f = reels.resolve(focus)
        fr = t[t.cricbuzz_id == f["cricbuzz_id"]]
        if fr.empty:
            raise ValueError(f"{f['name']} is not in the uncapped {role} list")
        if f["cricbuzz_id"] not in set(rows.cricbuzz_id):
            rows = pd.concat([rows.head(n - 1), fr])
        big = f"#{int(fr.rank_uncapped.iloc[0])}"
    top = _header(cv, "Uncapped " + ("batters" if role == "bat" else "bowlers"), "SMAT 2025-26 | RANKED BY SCORE", big,
                  f"OF {len(t)} UNCAPPED" if big else "", f"Source: Cricbuzz SMAT 2025-26 | {lab.lower()}")
    rows = rows.iloc[::-1]
    hl = [f is not None and i == f["cricbuzz_id"] for i in rows.cricbuzz_id]
    left = 40 * k + 370 * k
    ax = cv.axes(left, top + 20 * k, cv.w - 40 * k, cv.h - 60 * k)
    ax.axis("off")
    ys = list(range(len(rows)))
    xmax = rows.score.max() * 1.3
    ax.set_xlim(0, xmax), ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.barh(ys, rows.score, height=0.75, color=[pal["a1"] if x else _rgba(pal["ink"]) for x in hl])
    for i, (v, r_, nm) in enumerate(zip(rows.score, rows.rank_uncapped, rows["name"])):
        ax.text(v + xmax * 0.01, i, num(v, 1), ha="left", va="center", fontproperties=cv.num, fontsize=56 * k * PX, color=pal["ink"])
        ax.text(-xmax * 0.02, i, f"{int(r_)}. {short_name(nm)[:16]}", ha="right", va="center", fontproperties=cv.lab, fontsize=26 * k * PX, color=pal["ink"])


def render(chart: str, png: Path, size: str | None = None, palette: str | None = None, **kw):
    w, h = parse_size(size)
    cv = Canvas(w, h, parse_palette(palette), kw.get("fonts"))
    if chart == "scout_innings":
        if not kw.get("player"):
            raise ValueError("scout_innings needs --player")
        innings(cv, kw["player"])
    elif chart == "scout_rank":
        if kw.get("role") not in ("bat", "bowl"):
            raise ValueError("scout_rank needs --role bat|bowl")
        rank(cv, kw["role"], kw.get("focus"))
    else:
        raise ValueError(f"unknown scouting chart {chart!r}; use {' or '.join(CHARTS)}")
    return cv.save(png)
