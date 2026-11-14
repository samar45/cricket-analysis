"""Match win-probability / projected-score curves for reels (request 2): `cricket match find`, `cricket facts --match`,
`cricket chart match_curve|score_curve`.

Numbers come from `ml.predict.predict_match_curve` (the same replay the dashboard and web API use): a prediction at the
start of every over. Hero / hero2 come from the ball-by-ball `wpa` module (our simple logistic win-probability model).
Fresh set #3 (`ml.evaluate.fresh3_mask`) is locked: no output at all.
"""

import datetime as dt
import json
from collections import Counter

import click
import pandas as pd

from . import api, competitions
from .db import query
from .facts import FACTS_VERSION, _flatten, _fmt
from .reference import team_short

LOCKED = "locked: fresh set #3 (men's matches from 2026-10-15 get no model output)"
HERO_TOP = 2
_KIND = [None]  # which chart `_chart_cmd` draws (set by chart_main)


class Locked(ValueError):
    pass


def _row(mid: str) -> dict:
    d = query("SELECT * FROM matches WHERE match_id = ?", [str(mid)])
    if d.empty:
        raise ValueError(f"match_id {mid} is not in the database (find ids with `cricket match find`)")
    return d.iloc[0].to_dict()


def guard(row: dict) -> None:
    """Raise Locked for any fresh-set-#3 match (same rule as web/app.py: fresh3_mask)."""
    from .ml import evaluate as ev

    df = pd.DataFrame([{"gender": row["gender"], "competition": row["competition"], "date": row["date"],
                        "batting_team": row["team1"], "bowling_team": row["team2"]}])
    if ev.fresh3_mask(df).any():
        raise Locked(LOCKED)


def _comp_key(row) -> str | None:
    return next((k for k, c in competitions.COMPETITIONS.items() if (c.competition, c.gender) == (row["competition"], row["gender"])), None)


def model_version() -> str:
    from .ml import predict as P

    cut = json.loads((P.MODEL_DIR / "production_meta.json").read_text())["cutoff"]
    return f"production refit, trained to {cut} (G1 direct score model + sim-B ball simulator, docs/ML_PREDICTION.md section 9)"


def _result_text(row, winner) -> str | None:
    res, mg = row.get("result"), row.get("result_margin")
    if res == "tie" or row.get("outcome_method") == "super over":
        return "Tie" + (f", {winner} won the super over" if winner else "")
    if not winner or res not in ("runs", "wickets") or pd.isna(mg):
        return f"{winner} won" if winner else None
    return f"{winner} won by {int(mg)} {res[:-1] if int(mg) == 1 else res}"


def _thru(info, key) -> str:
    return next((c["latest"] for c in info["competitions"] if c["competition"] == key), None) or max(c["latest"] for c in info["competitions"])


# ---------- the curve ----------
def compute(mid: str) -> dict:
    """Locked check, then the replay. Returns {row, meta, rows (series), chase, defend, bl, tie}."""
    from .ml import predict as P

    row = _row(mid)
    guard(row)
    c, meta = P.predict_match_curve(mid)
    bl = pd.read_parquet(P.BALLS_FILE, filters=[("match_id", "==", str(mid))])
    chase, defend = meta["team2"], meta["team1"]
    winner = meta["winner"] if isinstance(meta["winner"], str) else None
    tie = row.get("result") == "tie" or bool(row.get("outcome_method"))
    rows = []
    for r in c.itertuples():
        d = {"inn": int(r.innings), "over": int(r.over), "score": int(r.runs), "wkts": int(r.wickets)}
        if r.innings == 1:
            q = {"proj": r.ens_q50, "proj_p10": r.ens_q10, "proj_p90": r.ens_q90}
        else:
            q = {"win_pct": r.win_ens, "proj": r.sim_q50, "proj_p10": r.sim_q10, "proj_p90": r.sim_q90}
        d.update({k: round(float(v), 4 if k == "win_pct" else 1) for k, v in q.items() if pd.notna(v)})
        rows.append(d)
    for inn, final, wk in ((1, meta["score1"], meta["wk1"]), (2, meta["score2"], meta["wk2"])):  # the end of each innings
        over = int(bl[bl.innings == inn].over_n.max()) + 1
        d = {"inn": inn, "over": over, "score": int(final), "wkts": int(wk)}
        if inn == 2:
            end = 0.5 if tie else 1.0 if winner == chase else 0.0 if winner == defend else None
            if end is not None:
                d["win_pct"] = end
        rows.append(d)
    rows.sort(key=lambda r: (r["inn"], r["over"]))
    return {"row": row, "meta": meta, "rows": rows, "chase": chase, "defend": defend, "bl": bl, "winner": winner, "tie": tie}


def _chase(rows):
    return [r for r in rows if r["inn"] == 2 and "win_pct" in r]


def _curve_facts(x) -> dict:
    ch, winner, rows = _chase(x["rows"]), x["winner"], x["rows"]
    out = {}
    live = [r for r in ch[1:-1]] if len(ch) > 2 else []  # in-chase states: not ball 0, not the final result
    if winner in (x["chase"], x["defend"]) and live and not x["tie"]:
        side_win = (lambda r: r["win_pct"]) if winner == x["chase"] else (lambda r: 1 - r["win_pct"])
        lo = min(live, key=side_win)
        out["low"] = {"over": lo["over"], "win_pct": round(side_win(lo), 4), "pct": round(100 * side_win(lo)), "team": winner}
    steps = [(b, a) for a, b in zip(ch, ch[1:])]
    for key, first_over in (("swing", 1), ("swing_mid", 3)):  # swing_mid skips overs 1-2 (the start-of-chase adjustment)
        pool = [s for s in steps if s[0]["over"] >= first_over]
        if not pool:
            continue
        b, a = max(pool, key=lambda s: abs(s[0]["win_pct"] - s[1]["win_pct"]))
        n = b["over"]  # the over that ended at b (1-indexed)
        w = x["bl"][(x["bl"].innings == 2) & (x["bl"].over_n == n - 1)]
        faced = Counter(w[w.wides == 0].batter)
        d = round(b["win_pct"] - a["win_pct"], 4)
        out[key] = {"over": n, "delta": d, "delta_pct": round(100 * abs(d)), "from": a["win_pct"], "to": b["win_pct"],
                    "team": x["chase"], **({"inn": 2} if key == "swing_mid" else {}),
                    **({"bowler": Counter(w.bowler).most_common(1)[0][0]} if len(w) else {}),
                    **({"batter": faced.most_common(1)[0][0]} if faced else {})}
    return out


def _heroes(x) -> dict:
    """Top WPA in the chase (innings 2): batters (chasing side) and bowlers (defending side), from the ball-by-ball wpa model."""
    from .analysis.wpa import ball_wpa
    from .sql.filters import Filters

    row = x["row"]
    d = ball_wpa(Filters(competition=_comp_key(row), season=str(row["season"])))
    d = d[(d.match_id == str(row["match_id"])) & (d.innings == 2)]
    if d.empty:
        return {}
    bat = d.groupby("bat_who").bat_wpa.sum()
    bowl = d.groupby("bowler").bowl_wpa.sum()
    cand = [(v, p, "bat", x["chase"]) for p, v in bat.items()] + [(v, p, "bowl", x["defend"]) for p, v in bowl.items()]
    cand.sort(key=lambda t: -t[0])
    return {("hero" if i == 0 else f"hero{i + 1}"): {"player": p, "wpa": round(float(v), 4), "wpa_pct": round(100 * float(v), 1), "role": role, "team": team}
            for i, (v, p, role, team) in enumerate(cand[:HERO_TOP])}


def build_facts(mid: str) -> dict:
    x = compute(mid)
    row, meta = x["row"], x["meta"]
    info = api.data_info()
    key = _comp_key(row)
    thru = _thru(info, key)
    match = {"teams": [meta["team1"], meta["team2"]], "team1": meta["team1"], "team2": meta["team2"],
             "team1_short": team_short(meta["team1"]), "team2_short": team_short(meta["team2"]), "batting_first": meta["team1"],
             "chasing": meta["team2"], "date": meta["date"], "venue": meta["venue"], "competition": key or row["competition"],
             "score1": f"{meta['score1']}/{meta['wk1']}", "score2": f"{meta['score2']}/{meta['wk2']}"}
    if meta["target"] is not None:
        match["target"] = meta["target"]
    if x["winner"]:
        match["winner"] = x["winner"]
    if row.get("result_margin") is not None and not pd.isna(row["result_margin"]):
        match["margin"] = f"{int(row['result_margin'])} {row['result']}"
    if (res := _result_text(row, x["winner"])):
        match["result"] = res
    oos = not meta["in_sample"]
    pre = {"out_of_sample": oos, "model_version": model_version()}
    if oos:  # never reached today: fresh set #3 is locked and everything older is in-sample
        from .ml import prematch

        p = prematch.predict(key or row["competition"], meta["venue"], meta["team1"], meta["team2"], date=meta["date"])
        pre.update(win_pct=round(float(p["p_a_win"]), 4), team=meta["team1"])
    facts = {"match": match, "curve": _curve_facts(x), **_heroes(x), "pre_match": pre,
             "series": {"overs": x["rows"]}}
    raw: dict = {}
    _flatten({k: v for k, v in facts.items() if k != "series"}, "", raw)
    mv = model_version()
    return {
        "meta": {
            "facts_version": FACTS_VERSION, "kind": "match", "match_id": str(mid),
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "data_through": thru, "db_path": info["db_path"], "db_modified": info["db_modified"], "source": info["source"],
            "model_version": mv, "in_sample": bool(meta["in_sample"]),
            "wpa_definition": "WPA = sum, over the balls of the chase (innings 2), of the change in the chasing side's win probability: credited to the batter "
                              "(off the bat; a dismissal to the batter who left) with + for the chasing side, and to the bowler with the sign flipped. "
                              "Win probability for hero / hero2 is the ball-by-ball logistic model of the `wpa` module (not the over-by-over curve model).",
            "low_definition": "curve.low = the eventual winner's lowest win probability at an over boundary during the chase (not the 0-over start, not the final result).",
            "swing_definition": "curve.swing = the largest one-over change in the chasing side's win probability; delta = to - from; "
                                "bowler = who bowled most of that over; batter = who faced most of it.",
            "caveats": ["Win % at each over boundary comes from our models (G1 + ball simulator 50/50), not from any bookmaker or official source.",
                        "The models were trained on this match: the curve is in-sample and shows what the model would say, not a forecast." if meta["in_sample"]
                        else "This match is after the models' training cutoff (out of sample).",
                        "The model gives no confidence band for win %: p10/p90 are absent. proj/proj_p10/proj_p90 are the projected final score (median, 10th and 90th percentile)."],
            "calls": [{"function": "ml.predict.predict_match_curve", "params": {"match_id": str(mid)}}, {"module": "wpa", "params": {"view": "players"}}],
        },
        "facts": facts,
        "tokens": {k: _fmt(v) for k, v in raw.items()},
        "tokens_raw": raw,
    }


# ---------- find ----------
def find(team, season=None, opponent=None, player=None, competition=None) -> list[dict]:
    from .sql.filters import Filters

    comp = competitions.get(competition) if competition else None
    scope, p = ("m.competition = ? AND m.gender = ?", [comp.competition, comp.gender]) if comp else ("m.gender = ?", [competitions.DEFAULT_GENDER])
    names = query(f"SELECT team1 AS t FROM matches m WHERE {scope} UNION SELECT team2 FROM matches m WHERE {scope}", p + p).t.tolist()
    for label, n in (("team", team), ("opponent", opponent)):
        if n and n not in names:
            cands = api.resolve_team(n, competition)
            raise click.ClickException(f"No exact {label} {n!r}. Closest names:\n" + ("\n".join(f"  {c['name']}" for c in cands) or "  (none)"))
    sql, params = f"SELECT m.* FROM matches m WHERE {scope} AND (m.team1 = ? OR m.team2 = ?)", p + [team, team]
    if opponent:
        sql, params = sql + " AND (m.team1 = ? OR m.team2 = ?)", params + [opponent, opponent]
    if season:
        s, sp = Filters(competition=competition, season=season)._season_sql("m")
        sql, params = sql + (f" AND {s}" if s else ""), params + sp
    if player:
        sql, params = sql + " AND m.match_id IN (SELECT match_id FROM deliveries WHERE batter = ? OR bowler = ? OR non_striker = ?)", params + [player] * 3
    d = query(sql + " ORDER BY m.date DESC, m.match_id", params)
    return [{"match_id": r["match_id"], "date": str(pd.Timestamp(r["date"]).date()), "teams": [r["team1"], r["team2"]],
             "result": _result_text(r, r["winner"] if isinstance(r["winner"], str) else None), "venue": r["venue"],
             "competition": _comp_key(r) or r["competition"]} for r in d.to_dict("records")]


@click.group()
def match():
    """Find matches for the reels: cricket match find --team "Rajasthan Royals" --season 2026 --json."""


@match.command("find")
@click.option("--team", required=True, help="Exact Cricsheet team name")
@click.option("--season", default=None, help="Year or Cricsheet label")
@click.option("--opponent", default=None)
@click.option("--player", default=None, help="Exact name: matches he batted or bowled in")
@click.option("--competition", default=None, help="Competition key, e.g. ipl")
@click.option("--json", "as_json", is_flag=True)
def find_cmd(team, season, opponent, player, competition, as_json):
    rows = find(team, season, opponent, player, competition)
    if as_json:
        click.echo(json.dumps(rows, indent=2))
    else:
        for r in rows:
            click.echo(f"{r['match_id']}  {r['date']}  {' v '.join(r['teams'])}  {r['result'] or '-'}  ({r['venue']})")


def facts_cmd(mid, out):
    try:
        data = build_facts(mid)
    except ValueError as e:  # Locked, unknown id, not modelled
        raise click.ClickException(str(e))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(f"Wrote {out}: {len(data['facts'])} sections, {len(data['tokens'])} tokens, data through {data['meta']['data_through']}")


@click.command(add_help_option=False, context_settings={"ignore_unknown_options": True})
@click.argument("match_id")
@click.option("--png", "--out", "png", type=click.Path(dir_okay=False), required=True)
@click.option("--team", default=None, help="match_curve: whose win % to draw (default the chasing side)")
@click.option("--mark", default="", help="match_curve: swing,low")
@click.option("--inn", type=click.Choice(["1", "2"]), default="1", help="score_curve: innings")
@click.option("--upto", type=int, default=None, help="draw the series only up to this over; axes stay full-match")
@click.option("--size", default=None, help="WxH, e.g. 1080x1920")
@click.option("--width", type=int, default=960)
@click.option("--height", type=int, default=980)
@click.option("--palette", default=None, help='JSON {"bg","ink","a1","a2"}')
@click.option("--fonts", default=None, help="folder with the font TTFs")
def _chart_cmd(match_id, png, team, mark, inn, upto, size, width, height, palette, fonts):
    from .viz import match_reel

    if size:
        try:
            width, height = (int(v) for v in size.lower().split("x"))
        except ValueError:
            raise click.UsageError("--size must look like 1080x1920")
    try:
        pal = {**match_reel.DEFAULT_PALETTE, **(json.loads(palette) if palette else {})}
    except ValueError:
        raise click.UsageError("--palette must be JSON")
    try:
        x = compute(match_id)
        info = api.data_info()
        thru = _thru(info, _comp_key(x["row"]))
        fonts_ok = match_reel.draw(_KIND[0], x, png, width, height, pal, team=team, marks=[m for m in mark.split(",") if m], inn=int(inn), upto=upto,
                                   thru=thru, font_dir=fonts)
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"Wrote {png} ({width}x{height}, transparent). Fonts: {fonts_ok}")


def chart_main(kind, png, size, width, height, palette, args):
    """Called by `cricket chart match_curve|score_curve <id> ...` (args = the leftover command line)."""
    _KIND[0] = kind
    extra = list(args) + (["--png", str(png)] if png else [])
    for flag, v in (("--size", size), ("--width", width), ("--height", height), ("--palette", palette)):
        if v:
            extra += [flag, str(v)]
    _chart_cmd.main(extra, prog_name=f"cricket chart {kind}", standalone_mode=False)
