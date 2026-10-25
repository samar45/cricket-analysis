"""Story finder: ranked "hooks" for one player, each a sentence built from numbers of the other modules."""

import math

import pandas as pd

from .. import api
from ..db import current_db_path
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters

# filter fields that are passed on to every module call (player is added per call)
_BASE_KEYS = (
    "competition",
    "season",
    "season_from",
    "season_to",
    "last_n_years",
    "team",
    "opposition",
    "venue",
    "include_super_overs",
)


def _run(module_id, **params):
    """api.run on the DB the outer call is using (a nested api.run would otherwise fall back to the default DB)."""
    return api.run(module_id, db_path=current_db_path(), **params)


COLUMNS = [
    "rank",
    "theme",
    "kind",
    "metric",
    "sentence",
    "label_a",
    "value_a",
    "n_a",
    "label_b",
    "value_b",
    "n_b",
    "n_unit",
    "rel_gap",
    "confidence",
    "score",
    "source",
]
OUTS_MIN, OUTS_FULL = (
    10,
    40,
)  # dismissals (or wickets) needed for an average to count / to count fully
RECORD_SCORE = (
    0.15  # a record has no second number to compare with: it only ranks if nothing else is strong
)
SELECTION_PENALTY = 0.5  # "best of K seasons" is picked after looking at the data


def _num(x) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def _row(r, bat: bool) -> dict:
    """One module row -> the common keys: sr / econ, avg, balls, outs (dismissals when batting, wickets when bowling)."""
    g = lambda k: _num(r[k]) if k in r.index else None  # noqa: E731
    if bat:
        outs = g("dismissals")
        if outs is None and g("innings") is not None:
            outs = g("innings") - (g("not_outs") or 0)
        return {"rate": g("strike_rate"), "avg": g("average"), "balls": g("balls"), "outs": outs}
    return {"rate": g("economy"), "avg": g("average"), "balls": g("balls"), "outs": g("wickets")}


def _hook(
    theme, metric, a, b, nunit, *, min_n, full_n, lower_better, src, dec=2, penalty=1.0, text=None
):
    """One comparison. a / b = (label, value, sample size). None when a number is missing or a sample is too small."""
    (la, va, na), (lb, vb, nb) = a, b
    if None in (va, vb, na, nb) or va <= 0 or vb <= 0 or min(na, nb) < min_n:
        return None
    rel = abs(va - vb) / max(va, vb)
    conf = min(1.0, math.sqrt(min(na, nb) / full_n))
    better = a if (va < vb) == lower_better else b
    worse = b if better is a else a
    fmt = lambda t: f"{t[0]} {t[1]:,.{dec}f} ({int(t[2]):,} {nunit})"  # noqa: E731
    sentence = text or f"{metric}: {fmt(better)} vs {fmt(worse)}, {rel:.0%} gap"
    return {
        "theme": theme,
        "kind": "gap",
        "metric": metric,
        "sentence": sentence,
        "label_a": la,
        "value_a": va,
        "n_a": int(na),
        "label_b": lb,
        "value_b": vb,
        "n_b": int(nb),
        "n_unit": nunit,
        "rel_gap": round(rel, 3),
        "confidence": round(conf, 3),
        "score": round(rel * conf * penalty, 3),
        "source": src,
    }


@module(
    id="stories",
    title="Story finder",
    category="advanced",
    description="Candidate reel hooks for one player, ranked. Each hook compares two of his own numbers taken from other "
    "modules (vs pace vs spin, home vs away, setting vs chasing, under pressure vs calm, death overs, powerplay vs "
    "middle, best season vs career, last N seasons vs career, a dismissal pattern vs all batters) and is a plain sentence "
    "with both numbers, both sample sizes and the module calls it came from. score = relative gap x sample confidence; "
    "comparisons on thin samples are dropped. A batter gets batting hooks, a bowler bowling hooks.",
    params=[
        ParamSpec("player", "player", required=True, help="Exact player name (use resolve first)"),
        *std("competition", "season", "team", "opposition", "venue"),
        ParamSpec(
            "role",
            "choice",
            default="auto",
            choices=("auto", "batting", "bowling"),
            help="auto = whichever he does more of (balls faced vs balls bowled)",
        ),
        ParamSpec(
            "min_balls",
            "int",
            help="Balls needed on each side of a comparison (default 150 batting, 120 bowling); averages need "
            f"{OUTS_MIN}+ dismissals/wickets on each side",
        ),
        ParamSpec(
            "recent_years", "int", default=3, help="Seasons in the 'recent form vs career' hook"
        ),
        ParamSpec("top", "int", default=10, help="Hooks to return, best first"),
    ],
    caveats=[
        "A heuristic, not a statistical test: score = relative gap (|a-b| / larger of the two) x sqrt(smaller sample / full sample), "
        "capped at 1. Full sample = 4 x min_balls for rates, 40 dismissals/wickets for averages. Nothing here is a significance test.",
        "One hook per theme (the stronger of strike rate / average, or economy / bowling average). Records have no second number and score a flat 0.15.",
        "'Best season' is the best of several seasons picked after looking, so its score is halved. Compare a season with the career, not with luck.",
        "Pace/spin, dismissal kind, home/away and pressure use those modules' own rules (see their caveats); unknown bowling types are not a side.",
        "Death-overs and 'recent' hooks compare a slice with the whole career, so the two sides overlap and the gap is understated.",
        "The powerplay vs middle hook ignores the death overs on purpose (the death-overs hook covers them).",
        "The recent-form hook is skipped when a season filter is set, or when the recent seasons are his whole record.",
    ],
)
def stories(
    f: Filters,
    role: str = "auto",
    min_balls: int | None = None,
    recent_years: int = 3,
    top: int = 10,
) -> pd.DataFrame:
    base = {k: getattr(f, k) for k in _BASE_KEYS if getattr(f, k) not in (None, [], (), False)}
    who = {"player": f.player, **base}

    def run(mod, **extra):
        r = _run(mod, **who, **extra)
        return r, [{"module": mod, "params": r.meta["params"]}]

    bat_r, bat_s = run("batting")
    bowl_r, bowl_s = run("bowling")
    nb = int(bat_r.data["balls"].iloc[0]) if len(bat_r.data) else 0
    nw = int(bowl_r.data["balls"].iloc[0]) if len(bowl_r.data) else 0
    if role == "auto":
        role = "bowling" if nw > nb else "batting"
    bat = role == "batting"
    career_r, career_s = (bat_r, bat_s) if bat else (bowl_r, bowl_s)
    if career_r.data.empty:
        return pd.DataFrame(columns=COLUMNS)
    career = _row(career_r.data.iloc[0], bat)
    mb = float(min_balls if min_balls is not None else (150 if bat else 120))
    # (name shown, lower is better): the rate (strike rate / economy) and the average
    metrics = (
        [("strike rate", False), ("batting average", False)]
        if bat
        else [("economy", True), ("bowling average", True)]
    )

    def compare(theme, ra, la, rb, lb, src, **kw):
        """Best hook over the role's two metrics for two common-key rows (ra / rb) - one hook per theme."""
        out = []
        for name, lower in metrics:
            rate = name in ("strike rate", "economy")
            key = "rate" if rate else "avg"
            nkey = "balls" if rate else "outs"
            unit = "balls" if rate else ("dismissals" if bat else "wickets")
            h = _hook(
                theme,
                name,
                (la, ra[key], ra[nkey]),
                (lb, rb[key], rb[nkey]),
                unit,
                min_n=mb if rate else OUTS_MIN,
                full_n=4 * mb if rate else OUTS_FULL,
                lower_better=lower,
                src=src,
                **kw,
            )
            if h:
                out.append(h)
        return max(out, key=lambda h: h["score"]) if out else None

    def pair(theme, df, col, va, la, vb, lb, r_src, **kw):
        """Compare two rows of a module result picked by `col` == va / vb."""
        ra, rb = df[df[col] == va], df[df[col] == vb]
        if ra.empty or rb.empty:
            return None
        return compare(theme, _row(ra.iloc[0], bat), la, _row(rb.iloc[0], bat), lb, r_src, **kw)

    hooks = []

    def add(h):
        if h:
            hooks.append(h)

    def safe(fn):  # one broken module must not sink the whole list
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass

    if bat:

        def pvs():
            r, s = run("pace_vs_spin")
            d = r.data[r.data["level"] == "kind"].assign(k=lambda x: x["bowler_type"].str.lower())
            add(pair("pace_vs_spin", d, "k", "pace", "against pace", "spin", "against spin", s))

        safe(pvs)

        def dism():
            r, s = run("dismissal_profile")
            lg_r = _run("dismissal_profile", **base)  # all batters, same filters
            lg = lg_r.data.groupby("kind")["outs"].sum()
            lg_total, total = int(lg.sum()), int(r.data["outs"].sum())
            lsrc = [{"module": "dismissal_profile", "params": lg_r.meta["params"]}]
            best = None
            for _, x in r.data.iterrows():
                if x["outs"] < 8 or total < 30 or x["kind"] not in lg.index:
                    continue
                p, q = 100 * x["outs"] / total, 100 * lg[x["kind"]] / lg_total
                if p <= q:
                    continue
                txt = (
                    f"{x['kind']} is {p:.1f}% of {f.player}'s dismissals ({int(x['outs'])} of {total}) "
                    f"vs {q:.1f}% for all batters ({lg_total:,} dismissals), {abs(p - q) / max(p, q):.0%} gap"
                )
                h = _hook(
                    "dismissal",
                    "dismissal share",
                    (f"{x['kind']} (him)", p, total),
                    ("all batters", q, lg_total),
                    "dismissals",
                    min_n=30,
                    full_n=100,
                    lower_better=True,
                    src=s + lsrc,
                    dec=1,
                    text=txt,
                )
                if h and (best is None or h["score"] > best["score"]):
                    best = h
            add(best)

        safe(dism)

    def home():
        r, s = run("home_away", role=role)
        add(pair("home_away", r.data, "location", "home", "at home", "away", "away", s))

    def chase():
        r, s = run("chase_vs_set", role=role)
        add(pair("chase_vs_set", r.data, "setting", "setting", "setting", "chasing", "chasing", s))

    def pressure():
        r, s = run("pressure", role=role)
        x = r.data.iloc[0]
        if bat:
            pa = {
                "rate": x["pressure_sr"],
                "avg": x["pressure_avg"],
                "balls": x["pressure_balls"],
                "outs": x["pressure_outs"],
            }
            ca = {
                "rate": x["calm_sr"],
                "avg": x["calm_avg"],
                "balls": x["calm_balls"],
                "outs": x["calm_outs"],
            }
        else:
            pw, cw = x["pressure_wickets"], x["calm_wickets"]
            pa = {
                "rate": x["pressure_economy"],
                "balls": x["pressure_legal_balls"],
                "outs": pw,
                "avg": x["pressure_runs_conceded"] / pw if pw else None,
            }
            ca = {
                "rate": x["calm_economy"],
                "balls": x["calm_legal_balls"],
                "outs": cw,
                "avg": x["calm_runs_conceded"] / cw if cw else None,
            }
        pa, ca = ({k: _num(v) for k, v in d.items()} for d in (pa, ca))
        add(compare("pressure", pa, "under pressure", ca, "calm", s))

    def death():
        r, s = run("death_overs", role=role)
        x = r.data.iloc[0]
        if bat:
            da = {
                "rate": x["death_sr"],
                "avg": x["death_avg"],
                "balls": x["death_balls"],
                "outs": x["death_dismissals"],
            }
        else:
            dw = x["death_wickets"]
            da = {
                "rate": x["death_economy"],
                "balls": x["death_balls"],
                "outs": dw,
                "avg": x["death_runs"] / dw if dw else None,
            }
        da = {k: _num(v) for k, v in da.items()}
        add(compare("death_overs", da, "in the death overs", career, "overall", s + career_s))

    def phases():
        r, s = run(role, group_by="phase")
        add(
            pair(
                "phase",
                r.data,
                "phase",
                "powerplay",
                "in the powerplay",
                "middle",
                "in the middle overs",
                s,
            )
        )

    def season_and_recent():
        r, s = run(role, group_by="season")
        d = r.data
        ok = d[(d["balls"] >= mb) & (d["innings"] >= 8)]
        if not ok.empty:
            col = "average" if bat else "economy"
            i = ok[col].idxmax() if bat else ok[col].idxmin()
            x = _row(d.loc[i], bat)
            label = f"in {d.loc[i, 'season']}"
            h = compare(
                "best_season", x, label, career, "career", s + career_s, penalty=SELECTION_PENALTY
            )
            if h:
                h["sentence"] = h["sentence"] + f" (best of {len(ok)} seasons)"
            add(h)
        if not f.values("season") and not f.season_from and not f.season_to and not f.last_n_years:
            rr, rs = run(role, last_n_years=int(recent_years))
            if len(rr.data):
                x = _row(rr.data.iloc[0], bat)
                if x["balls"] and x["balls"] < career["balls"]:
                    add(
                        compare(
                            "recent",
                            x,
                            f"last {recent_years} seasons",
                            career,
                            "career",
                            rs + career_s,
                        )
                    )

    def record():
        x = career_r.data.iloc[0]
        if bat:
            n = int(x["innings"])
            add(
                _record(
                    "highest score",
                    "runs",
                    float(x["highest"]),
                    str(int(x["highest"])),
                    n,
                    "innings",
                    career_s,
                    f"highest score {int(x['highest'])} in {n} innings ({int(x['hundreds'])} hundreds, {int(x['fifties'])} fifties)",
                )
            )
        else:
            w, rn = (int(v) for v in str(x["best_figures"]).split("/"))
            n = int(x["innings"])
            add(
                _record(
                    "best figures",
                    "wickets",
                    float(w),
                    x["best_figures"],
                    n,
                    "innings",
                    career_s,
                    f"best figures {x['best_figures']} in {n} innings ({int(x['five_plus'])} five-wicket hauls)",
                    float(rn),
                )
            )

    for fn in (home, chase, pressure, death, phases, season_and_recent, record):
        safe(fn)

    if not hooks:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(hooks).sort_values(["score", "theme"], ascending=[False, True]).head(int(top))
    df.insert(0, "rank", range(1, len(df) + 1))
    df[["n_a", "n_b"]] = df[["n_a", "n_b"]].astype("Int64")
    return df[COLUMNS].reset_index(drop=True)


def _record(label, unit, value, shown, n, nunit, src, sentence, value_b=None):
    conf = min(1.0, math.sqrt(n / 50))
    return {
        "theme": "record",
        "kind": "record",
        "metric": label,
        "sentence": sentence,
        "label_a": label,
        "value_a": value,
        "n_a": n,
        "label_b": "runs conceded" if value_b is not None else None,
        "value_b": value_b,
        "n_b": None,
        "n_unit": nunit,
        "rel_gap": None,
        "confidence": round(conf, 3),
        "score": round(RECORD_SCORE * conf, 3),
        "source": src,
    }
