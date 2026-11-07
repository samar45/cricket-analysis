"""Player worth: the short, data-chosen metric set for a batter or bowler, shrunk and ranked against peers."""

from dataclasses import replace

import pandas as pd

from ..models import worth as W
from ..registry import ParamSpec, module, std
from ..sql.filters import Filters, explain_empty


@module(
    id="player_worth",
    title="Player worth (the metrics that matter, shrunk, with percentiles)",
    category="advanced",
    description="A short metric set picked by the data (docs/VALUE_worth.md): each candidate was scored by how well it repeats from "
    "one season to the next and how much of per-ball win probability added it explains, and near-duplicates were dropped. "
    "mode=profile gives the player's value on each kept metric (pulled toward the league average by how few balls he has), "
    "his percentile among peers and the balls behind it. mode=highlights lists the best single-match performances measured "
    "against everyone else in the same match (a 50 off 25 when the rest scored at 7 an over).",
    params=[
        *std("player", "competition", "season", "team", "opposition", "venue", "phase"),
        ParamSpec("role", "choice", default="batting", choices=("batting", "bowling")),
        ParamSpec("mode", "choice", default="profile", choices=("profile", "highlights")),
        ParamSpec("min_balls", "int", help="Peers need at least this many balls (default 100; 30 for phase and bowling-type slices)"),
        ParamSpec("top", "int", default=25, help="Rows to return when no player is given (best average percentile / best match first)"),
    ],
    caveats=[
        "With no competition and no season given the module uses IPL 2023 onwards (the Impact Player era); name a competition or seasons to look elsewhere. Only 6-ball T20 matches with a trusted target and a result are used.",
        "Which metrics are kept was decided on IPL 2023-26 and checked on BBL and PSL (models/data/worth_selected.csv); the shrinkage constant k is re-estimated on the filtered data when it has 40+ player-seasons, otherwise the IPL value is used.",
        "value = his rate pulled toward the league mean: (balls x his rate + k x league rate) / (balls + k). A balls-per-event number is the reciprocal of that rate. own_share = balls / (balls + k), how much of the number is his own.",
        "pctile: 100 = best among peers (peers = everyone in the filtered scope with enough balls, batters or bowlers, not split by batting slot); direction is applied, so a low economy gives a high percentile.",
        "Bowling-type and hand splits use only the reviewed list in player_overrides.csv; players facing or bowling to someone without a label are left out of that split.",
        "Wicket-taking and runs added per ball were tested and dropped as season-level skill measures: they barely repeat (see the doc). Wickets are still shown in the highlights.",
        "highlights: runs_vs_match = runs scored above (batting) or saved below (bowling) what everyone else in the same match did per ball in the same phases, both sides. It is a one-match number, not shrunk.",
        "team / opposition / venue / phase filters narrow the highlights and the peer group is built from the whole scope of competition and seasons.",
    ],
)
def player_worth(
    f: Filters, role: str = "batting", mode: str = "profile", min_balls: int | None = None, top: int = 25
) -> pd.DataFrame:
    if f.competition is None and not f.values("season") and f.season_from is None and f.season_to is None and f.last_n_years is None:
        f = replace(f, competition="ipl", season_from=2023)
    r = "bat" if role == "batting" else "bowl"
    d = W.ball_frame(f)
    if d.empty:
        raise explain_empty(f, "player worth")
    if mode == "highlights":
        h = W.highlights(d, r)
        if f.player:
            h = h[h.player == f.player]
        if f.values("team"):
            h = h[h.team.isin(f.values("team"))]
        if f.values("opposition"):
            h = h[h.opposition.isin(f.values("opposition"))]
        if h.empty:
            raise explain_empty(f, "match highlights")
        return h.head(int(top)).rename(columns={"player": "batter" if r == "bat" else "bowler"})
    p = W.profile(d, r, min_balls)
    if f.player:
        p = p[p.player == f.player]
        if p.empty:
            raise explain_empty(f, "player worth (not enough balls for the peer minimum?)")
        p = p.assign(value=p.value.round(2), raw=p.raw.round(4), own_share=p.own_share.round(2))
        return p.drop(columns=["rate", "s1"]).reset_index(drop=True)
    w = p.pivot(index="player", columns="metric", values="pctile")
    w.insert(0, "avg_pctile", w.mean(axis=1).round(0))
    w.insert(0, "balls", p.groupby("player").n.max().reindex(w.index).astype(int))
    w = w[w.balls >= (min_balls or 100)]  # a leaderboard needs a full-size sample, not a 30-ball slice
    return w.sort_values(["avg_pctile", "balls"], ascending=False).head(int(top)).reset_index()
