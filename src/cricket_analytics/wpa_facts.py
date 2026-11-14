"""Player WPA for reels (request C): the `wpa` section of `cricket facts --player` and `cricket chart wpa --player X`.
Built on the ball-by-ball `wpa` module (analysis/wpa.py: ball_wpa). WPA = win probability added, 1.0 = one whole win.
A player's WPA in a match = what he added with the bat (batter's balls, a dismissal charged to the batter who left)
plus what he added with the ball (bowler's balls, sign flipped). Fresh-set-#3 matches (men's, 2026-10-15 on) are left out."""

import json
from functools import lru_cache

import click
from matplotlib.colors import to_rgba
import pandas as pd

from .reference import team_short


MIN_MATCHES = 20  # a player is ranked only with this many matches in scope
TOP = 3
DEFINITION = ("WPA = change in the batting side's win probability over each ball (our ball-by-ball logistic model, `wpa` module), "
              "credited to the batter off the bat (a dismissal to the batter who left) and, sign flipped, to the bowler. A player's "
              "match WPA is his batting plus bowling total; 1.0 = one whole win. Fresh set #3 matches (men's, from 2026-10-15) are excluded.")


@lru_cache(maxsize=8)
def _per_match(competition: str | None, last_n_years: int | None) -> pd.DataFrame:
    """One row per (player, match): wpa, date, opponent, match_id."""
    from .analysis.wpa import ball_wpa
    from .ml import evaluate as ev
    from .sql.filters import Filters

    d = ball_wpa(Filters(competition=competition, last_n_years=last_n_years))
    d = d[~ev.fresh3_mask(d)]
    bat = d.assign(player=d.bat_who, w=d.bat_wpa, opp=d.bowling_team)
    bowl = d.assign(player=d.bowler, w=d.bowl_wpa, opp=d.batting_team)
    x = pd.concat([bat[["player", "match_id", "date", "opp", "w"]], bowl[["player", "match_id", "date", "opp", "w"]]])
    return x.groupby(["player", "match_id"], as_index=False).agg(wpa=("w", "sum"), date=("date", "first"), opponent=("opp", "first")).sort_values("date")


def player_matches(player, competition=None, last_n_years=None) -> pd.DataFrame:
    x = _per_match(competition, last_n_years)
    return x[x.player == player].reset_index(drop=True)


def section(player, competition=None, last_n_years=None) -> dict | None:
    from .db import query
    from .matchreel import _result_text

    x = _per_match(competition, last_n_years)
    mine = x[x.player == player]
    if mine.empty:
        return None
    tot = x.groupby("player").agg(total=("wpa", "sum"), n=("match_id", "nunique"))
    out = {"source": [{"module": "wpa", "params": {"competition": competition, "last_n_years": last_n_years}}],
           "total": round(float(mine.wpa.sum()), 3), "matches": int(len(mine)), "per_match": round(float(mine.wpa.mean()), 4),
           "min_matches": MIN_MATCHES}
    ranked = tot[tot.n >= MIN_MATCHES].total.rank(ascending=False, method="min")
    if player in ranked.index:
        out.update(rank=int(ranked[player]), of=int(len(ranked)))
    top = mine.nlargest(TOP, "wpa")
    ms = query("SELECT * FROM matches WHERE match_id IN (SELECT UNNEST(?))", [list(top.match_id)]).set_index("match_id")
    out["top"] = {}
    for i, r in enumerate(top.itertuples(), 1):
        m = ms.loc[r.match_id]
        res = _result_text(m.to_dict(), m["winner"] if isinstance(m["winner"], str) else None)
        out["top"][str(i)] = {"match_id": r.match_id, "date": str(pd.Timestamp(r.date).date()), "opponent": r.opponent, "wpa": round(float(r.wpa), 3),
                              **({"result": res} if res else {})}
    return out


@click.command(add_help_option=False, context_settings={"ignore_unknown_options": True})
@click.option("--player", required=True)
@click.option("--competition", default=None)
@click.option("--last_n_years", type=int, default=None)
@click.option("--png", "--out", "png", type=click.Path(dir_okay=False), required=True)
@click.option("--size", default=None)
@click.option("--width", type=int, default=960)
@click.option("--height", type=int, default=980)
@click.option("--palette", default=None)
@click.option("--fonts", default=None)
def _chart_cmd(player, competition, last_n_years, png, size, width, height, palette, fonts):
    from .api import data_info
    from .viz import match_reel as mr

    if size:
        try:
            width, height = (int(v) for v in size.lower().split("x"))
        except ValueError:
            raise click.UsageError("--size must look like 1080x1920")
    mine = player_matches(player, competition, last_n_years)
    if mine.empty:
        raise click.ClickException(f"No WPA data for {player!r}. Check the name with `cricket resolve`.")
    try:
        pal = {**mr.DEFAULT_PALETTE, **(json.loads(palette) if palette else {})}
    except ValueError:
        raise click.UsageError("--palette must be JSON")
    info = data_info()
    thru = max(c["latest"] for c in info["competitions"] if not competition or c["competition"] == competition)
    click.echo(f"Wrote {png} ({width}x{height}, transparent). Fonts: " + draw(mine, player, competition, png, width, height, pal, thru, fonts))


def draw(mine, player, competition, png, w, h, pal, thru, fonts=None) -> str:
    from .viz import match_reel as mr

    cv = mr.Canvas(w, h, pal, fonts)
    k, ink, a1 = cv.k, pal["ink"], pal["a1"]
    cv.text(40 * k, 24 * k, f"{player.upper()} MATCH WPA", 54)
    cv.text(40 * k, 92 * k, f"{competition.upper() if competition else 'MEN\'S T20'} | EVERY MATCH, OLDEST TO NEWEST", 26, "lab", a1)
    tot = float(mine.wpa.sum())
    cv.text(w - 40 * k, 0, f"{tot:+.1f}", 170, "num", a1, "right")
    cv.text(w - 40 * k, 176 * k, "WINS ADDED (1.0 = ONE WIN)", 24, alpha=0.55, ha="right")
    ax = cv.axes(40 * k + 90 * k, 250 * k, w - 40 * k, h - 120 * k)
    n, best = len(mine), int(mine.wpa.values.argmax())
    ax.bar(range(n), mine.wpa, width=1.0, color=[a1 if i == best else to_rgba(ink, 0.5) for i in range(n)])
    ax.axhline(0, color=ink, lw=2 * k, alpha=0.6)
    ax.set_xlim(-1, n), ax.set_xticks([])
    ax.set_yticks([-0.5, 0, 0.5]) if mine.wpa.abs().max() > 0.5 else None
    for sp in ("left",):
        ax.spines[sp].set_visible(False)
    cv.style_ticks(ax, 26)
    b = mine.iloc[best]
    label = f"BEST +{b.wpa:.2f}\nv {team_short(b.opponent)}, {pd.Timestamp(b.date).year}"
    mr.DRAWN.append(label)
    ax.annotate(label, (best, b.wpa), xytext=(0, 14 * k * mr.PX), textcoords="offset points",
                ha="right" if best > n * 0.35 else "left", va="bottom", color=a1, fontproperties=cv.lab, fontsize=28 * k * mr.PX)
    ax.set_ylim(min(mine.wpa.min() * 1.1, -0.05), mine.wpa.max() * 1.35)
    years = pd.to_datetime(mine.date).dt.year
    cv.text(40 * k + 90 * k, h - 100 * k, f"{years.min()}", 26, ha="left")
    cv.text(w - 40 * k, h - 100 * k, f"{years.max()}", 26, ha="right")
    cv.text(40 * k, h - 14 * k, f"Source: Cricsheet | data to {thru} | win probability from our model", 20, alpha=0.55, va="bottom")
    return cv.save(png)
