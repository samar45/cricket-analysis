"""Underrated finder: strong numbers, small fame. A transparent heuristic built from other modules."""

import pandas as pd

from .. import api
from ..db import current_db_path
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters


def _run(module_id, **params):
    """api.run on the DB the outer call is using (a nested api.run would otherwise fall back to the default DB)."""
    return api.run(module_id, db_path=current_db_path(), **params)


COLUMNS = [
    "rank",
    "player",
    "matches",
    "balls",
    "true_rate",
    "average",
    "avg_impact",
    "fame_matches",
    "q_true",
    "q_avg",
    "q_impact",
    "quality",
    "o_scope",
    "o_career",
    "obscurity",
    "underrated_score",
]
_PASS = (
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


def _pct(s: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Rank as 0 (worst) .. 1 (best) among the rows; ties share the average rank; NaN counts as worst."""
    s = s if higher_is_better else -s
    s = s.fillna(s.min() - 1 if s.notna().any() else 0)
    n = len(s)
    return s.rank(method="average").sub(1).div(max(n - 1, 1)) if n > 1 else pd.Series(0.5, s.index)


@module(
    id="underrated",
    title="Underrated finder",
    category="experimental",
    description="Players who are strong by the numbers but little known. HEURISTIC, not a fact. In the chosen scope "
    "(competition / seasons), every player with enough balls gets a quality score and an obscurity score, "
    "each a weighted mean of percentile ranks (0 = worst, 1 = best of the candidates). Quality = true strike rate "
    "(batting) or true economy (bowling) + batting / bowling average + average impact per match. Obscurity = "
    "fewer matches in the chosen scope + fewer career matches in the fame competition (default IPL: the league "
    "most fans watch). underrated_score = 100 x quality x obscurity, so a player must be both good and unknown. "
    "Every component is a column; every weight is a parameter.",
    params=[
        *std("competition", "season", "team", "opposition", "venue"),
        ParamSpec(
            "role", "choice", default="batting", choices=("batting", "bowling"), help="Who to rank"
        ),
        ParamSpec(
            "fame_competition",
            "competition",
            default="ipl",
            help="League whose career match count measures fame (all seasons, ignoring the season filters)",
        ),
        ParamSpec(
            "min_balls",
            "int",
            help="Candidates need this many balls in scope (default 100 faced when batting, 120 bowled)",
        ),
        ParamSpec("top", "int", default=20, help="Rows to return (highest score first)"),
        ParamSpec(
            "w_true", "float", default=0.4, help="Quality weight: true strike rate / economy"
        ),
        ParamSpec("w_avg", "float", default=0.3, help="Quality weight: batting / bowling average"),
        ParamSpec(
            "w_impact", "float", default=0.3, help="Quality weight: average impact per match"
        ),
        ParamSpec(
            "w_scope",
            "float",
            default=0.4,
            help="Obscurity weight: few matches in the chosen scope",
        ),
        ParamSpec(
            "w_career",
            "float",
            default=0.6,
            help="Obscurity weight: few career matches in the fame competition",
        ),
    ],
    caveats=[
        "A heuristic: 'fame' is only match counts in our data, not followers, media or awards. A player with few IPL matches can be famous elsewhere (e.g. a national-team regular).",
        "Percentiles are among the candidates that pass min_balls, so the same player scores differently in another scope; weights are invented (defaults 0.4/0.3/0.3 and 0.4/0.6).",
        "True strike rate / economy: see true_performance (phase- and season-adjusted). Average impact: see impact (our own blend; a bowler's value includes his batting points).",
        "A batter with no dismissals has no average and ranks last on that part; a bowler with no wickets likewise.",
        "Batting position is not used (no per-player position list in the data); fame_matches is 0 when the player never played the fame competition.",
        "Women's data is reached only with competition=t20i_women and fame_competition=t20i_women.",
    ],
)
def underrated(
    f: Filters,
    role: str = "batting",
    fame_competition: str = "ipl",
    min_balls: int | None = None,
    top: int = 20,
    w_true: float = 0.4,
    w_avg: float = 0.3,
    w_impact: float = 0.3,
    w_scope: float = 0.4,
    w_career: float = 0.6,
) -> pd.DataFrame:
    bat = role == "batting"
    scope = {k: getattr(f, k) for k in _PASS if getattr(f, k) not in (None, [], (), False)}
    mb = int(min_balls if min_balls is not None else (100 if bat else 120))
    who, mod = ("batter", "batting") if bat else ("bowler", "bowling")
    tp = _run("true_performance", role=role, min_balls=mb, top=100000, **scope).data
    if tp.empty:
        return pd.DataFrame(columns=COLUMNS)
    avg = _run(mod, **scope).data.set_index(who)["average"]
    imp = _run("impact", min_matches=1, top=100000, **scope).data.set_index("player")["avg_impact"]
    fame = _run("impact", competition=fame_competition, min_matches=1, top=100000).data.set_index(
        "player"
    )["matches"]
    d = pd.DataFrame(
        {
            "player": tp[who],
            "matches": tp["matches"],
            "balls": tp["total_balls"] if bat else tp["balls"],
            "true_rate": tp["true_sr"] if bat else tp["true_economy"],
        }
    )
    d["average"] = d["player"].map(avg)
    d["avg_impact"] = d["player"].map(imp)
    d["fame_matches"] = d["player"].map(fame).fillna(0).astype(int)
    d["q_true"] = _pct(d["true_rate"], bat)
    d["q_avg"] = _pct(d["average"], bat)
    d["q_impact"] = _pct(d["avg_impact"])
    d["o_scope"] = 1 - _pct(d["matches"])
    d["o_career"] = 1 - _pct(d["fame_matches"])
    d["quality"] = (w_true * d["q_true"] + w_avg * d["q_avg"] + w_impact * d["q_impact"]) / (
        (w_true + w_avg + w_impact) or 1
    )
    d["obscurity"] = (w_scope * d["o_scope"] + w_career * d["o_career"]) / (
        (w_scope + w_career) or 1
    )
    d["underrated_score"] = 100 * d["quality"] * d["obscurity"]
    d = d.sort_values(["underrated_score", "player"], ascending=[False, True]).head(int(top))
    d.insert(0, "rank", range(1, len(d) + 1))
    num = [c for c in COLUMNS if c.startswith(("q_", "o_")) or c in ("quality", "obscurity")]
    d[num] = d[num].round(3)
    d[["true_rate", "average", "avg_impact", "underrated_score"]] = d[
        ["true_rate", "average", "avg_impact", "underrated_score"]
    ].round(2)
    return d[COLUMNS].reset_index(drop=True)
