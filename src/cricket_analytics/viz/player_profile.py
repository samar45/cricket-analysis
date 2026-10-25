"""Figure for the `player_profile` module.

One player: a card of fixed facts (role, keeper, bats, bowls; unknown unless on the reviewed list), then two usage mixes that follow
the filters (batting-order buckets as % of innings; balls faced / bowled by phase as %), each titled with its "usually ..." hint,
then runs and wickets per competition.
No player (a list): the busiest players as bars of career matches (or of the usage count when sorted by one), coloured by role,
with keeper / hand / bowling type as text when known."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .. import competitions
from ..analysis.player_profile import BOWLED, COUNTS, FACED, POS_BUCKETS, usage_of
from . import PALETTE, bars_height, empty, style

_ROLE_COLOR = {
    "batter": PALETTE["primary"],
    "bowler": PALETTE["bad"],
    "all-rounder": PALETTE["secondary"],
    "unknown": PALETTE["neutral"],
}
_OVERS = {"powerplay": "0-5", "middle": "6-14", "death": "15-19"}


def _v(r, k) -> str | None:
    x = r.get(k)
    return None if x is None or pd.isna(x) else str(x)


def _label(competition: str, gender: str) -> str:
    for c in competitions.COMPETITIONS.values():
        if (c.competition, c.gender) == (competition, gender):
            return c.label
    return f"{competition} ({gender})"


def figure(result) -> go.Figure:
    d = result.data
    if d.empty:
        return empty("No player for these filters")
    return _card(d, result) if "competition" in d.columns else _list(d, result)


def _tiles(r) -> list[tuple[str, str | None, str | None]]:
    """(label, value, how sure) for each tile; value None = unknown. Keeper, bowling type and hand come only from the reviewed
    list (the module returns 'unknown' otherwise); how he is used is in the two mix charts below, not in a tile."""
    known = lambda k: None if _v(r, k) in (None, "unknown") else _v(r, k)  # noqa: E731
    return [
        ("Role", known("role"), _v(r, "role_confidence")),
        ("Keeper", known("keeper"), _v(r, "keeper_confidence")),
        ("Bats", known("bat_hand"), _v(r, "bat_hand_confidence")),
        ("Bowls", known("bowl_type"), _v(r, "bowl_type_confidence")),
    ]


def _usually(hint: str | None) -> str | None:
    return hint.removeprefix("usually ") if hint else None


def _card(d, result):
    r = d.iloc[0].to_dict()
    tot = d[COUNTS].sum()  # one mix over every competition row in the result
    u = usage_of(tot)
    d = (
        d.assign(label=[_label(c, g) for c, g in zip(d.competition, d.match_gender)])
        .sort_values("matches", ascending=False)
        .head(10)
    )
    panels: list[tuple[str, str]] = []
    if tot.bat_innings:
        panels.append(
            (
                "pos",
                f"Batting order: usually {_usually(u['usually_bats_at'])} of {int(tot.bat_innings)} innings",
            )
        )
    lines = [
        f"{k}: usually {_usually(u[h])}"
        for k, h in (("Faced", "usually_faces_in"), ("Bowled", "usually_bowls_in"))
        if u[h]
    ]
    if lines:
        panels.append(("phase", "Share of balls by phase | " + " | ".join(lines)))
    panels += [
        (col, f"{t} per competition")
        for col, t in (("runs", "Runs"), ("wickets", "Wickets"))
        if d[col].sum() > 0
    ]
    if not any(k in ("runs", "wickets") for k, _ in panels):
        panels.append(("runs", "Runs per competition"))
    heights = [0.9] + [1.5 if k in ("pos", "phase") else 0.5 + 0.1 * len(d) for k, _ in panels]
    fig = make_subplots(
        rows=len(panels) + 1,
        cols=1,
        vertical_spacing=0.09,
        row_heights=[h / sum(heights) for h in heights],
        subplot_titles=[""] + [t for _, t in panels],
    )
    for i, (kind, _) in enumerate(panels, 2):
        if kind == "pos":
            pct = [u[f"pct_{k}"] for k in POS_BUCKETS]
            fig.add_bar(
                x=list(POS_BUCKETS.values()),
                y=pct,
                row=i,
                col=1,
                marker_color=PALETTE["primary"],
                showlegend=False,
                text=[f"{p:.0f}%<br>({int(tot[k])})" for p, k in zip(pct, POS_BUCKETS)],
                textposition="outside",
                cliponaxis=False,
            )
            fig.update_yaxes(range=[0, max(pct) * 1.35], title_text="% of innings", row=i, col=1)
        elif kind == "phase":
            series = [
                (lab, g, c)
                for lab, g, c in (
                    ("Balls faced", FACED, PALETTE["secondary"]),
                    ("Balls bowled", BOWLED, PALETTE["bad"]),
                )
                if u[f"pct_{next(iter(g))}"] is not None
            ]
            for label, group, color in series:
                pct = [u[f"pct_{k}"] for k in group]
                fig.add_bar(
                    x=[p.capitalize() for p in _OVERS],
                    y=pct,
                    name=label,
                    row=i,
                    col=1,
                    marker_color=color,
                    showlegend=len(series) > 1,
                    text=[f"{p:.0f}%<br>({int(tot[k]):,})" for p, k in zip(pct, group)],
                    textposition="outside",
                    cliponaxis=False,
                )
            fig.update_yaxes(range=[0, 125], title_text="% of balls", row=i, col=1)
        else:
            c = PALETTE["primary"] if kind == "runs" else PALETTE["bad"]
            fig.add_bar(
                y=d.label,
                x=d[kind],
                orientation="h",
                row=i,
                col=1,
                marker_color=c,
                showlegend=False,
                cliponaxis=False,
                text=[f"{v:,}" for v in d[kind]],
                textposition="outside",
            )
            fig.update_yaxes(autorange="reversed", row=i, col=1)
            fig.update_xaxes(range=[0, d[kind].max() * 1.2], row=i, col=1)
    fig.update_layout(barmode="group")
    fig.update_xaxes(visible=False, row=1, col=1)
    fig.update_yaxes(visible=False, row=1, col=1)
    lo, hi = (
        fig.layout.yaxis.domain
    )  # the card sits in the first row; everything is placed in paper coordinates
    at = lambda f: lo + f * (hi - lo)  # noqa: E731
    tiles = _tiles(r)
    for i, (label, value, sure) in enumerate(tiles):
        x = (i + 0.5) / len(tiles)
        text = (value or "unknown").capitalize().replace("-arm ", "-arm<br>")
        fig.add_annotation(
            text=label.upper(),
            x=x,
            y=at(0.92),
            xref="paper",
            yref="paper",
            showarrow=False,
            yanchor="top",
            font=dict(size=11, color="#9AA4B2"),
        )
        fig.add_annotation(
            text=f"<b>{text}</b>",
            x=x,
            y=at(0.52),
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=16 if len(text) < 12 else 13, color="#E6EAF0" if value else "#9AA4B2"),
        )
        fig.add_annotation(
            text=f"({sure})" if sure else "",
            x=x,
            y=at(0.14),
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=10, color="#9AA4B2"),
        )
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="paper",
        x0=0,
        x1=1,
        y0=at(0),
        y1=at(1),
        layer="below",
        line=dict(color="rgba(255,255,255,0.18)"),
        fillcolor="rgba(255,255,255,0.04)",
    )
    gender = (
        " (name shared by a man and a woman: numbers mixed)"
        if _v(r, "player_gender") == "both"
        else ""
    )
    n_mix = sum(k in ("pos", "phase") for k, _ in panels)
    n_comp = sum(k in ("runs", "wickets") for k, _ in panels)
    return style(
        fig,
        str(r["player"]),
        result,
        note=f"{int(r['career_matches'])} T20 matches in the data{gender}; keeper / bowling type / hand: reviewed list only",
        height=240 + 260 * n_mix + (60 + 24 * len(d)) * n_comp,
    )


def _fact(r, key, word=""):
    v = getattr(r, key, None)
    return (
        None
        if v is None or pd.isna(v) or v == "unknown"
        else (f"{v} {word}".strip() if key != "keeper" else f"keeper: {v}")
    )


def _list(d, result):
    top = d.head(15).iloc[::-1]
    by = result.meta["params"].get("sort_by")
    col, what = "career_matches", "T20 matches in the data"
    if by and by != "matches" and "_" in by:
        phase, kind = by.split("_")
        col, what = f"{kind}_{phase}", f"balls {kind} in the {phase} (overs {_OVERS[phase]})"
    fig = go.Figure()
    for role, c in _ROLE_COLOR.items():
        s = top[top.role.fillna("unknown") == role]
        if s.empty:
            continue
        fig.add_bar(
            y=s.player,
            x=s[col],
            name=role,
            orientation="h",
            marker_color=c,
            cliponaxis=False,
            text=[
                " | ".join(
                    x
                    for x in (
                        _fact(r, "keeper"),
                        _fact(r, "bat_hand", "bats"),
                        _fact(r, "bowl_type"),
                    )
                    if x
                )
                for r in s.itertuples()
            ],
            textposition="outside",
            textfont=dict(size=11),
        )
    fig.update_xaxes(title_text=what, range=[0, top[col].max() * 1.5])
    fig.update_yaxes(
        categoryorder="array", categoryarray=list(top.player)
    )  # keep the sort order (traces are per role)
    return style(
        fig,
        f"Players: top {len(top)} by " + ("matches" if col == "career_matches" else what),
        result,
        note="text = keeper | batting hand | bowling type, only where on the reviewed list",
        height=bars_height(len(top), 28, 190),
    )
