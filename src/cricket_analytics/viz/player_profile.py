"""Figure for the `player_profile` module.

One player: a card of tiles (role, keeper, batting slot, bats, bowls) over bars of runs and wickets per competition.
No player (a list): the busiest players as bars of career matches, coloured by role, with slot and bowling type as text."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .. import competitions
from . import PALETTE, bars_height, empty, style

_ROLE_COLOR = {"batter": PALETTE["primary"], "bowler": PALETTE["bad"], "all-rounder": PALETTE["secondary"], "unknown": PALETTE["neutral"]}


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
    """(label, value, how sure) for each tile; value None = unknown."""
    role = _v(r, "role")
    bowls = _v(r, "bowl_type") or (_v(r, "bowl_kind") if role in ("bowler", "all-rounder") else None)
    return [("Role", role, _v(r, "role_confidence")),
            # keeper only when the hand-kept list says so; the stumping-rate guess (source 'derived') is not shown
            ("Keeper", _v(r, "keeper") if _v(r, "keeper_source") not in (None, "derived") else None, _v(r, "keeper_confidence")),
            ("Batting slot", _v(r, "bat_slot"), _v(r, "bat_slot_confidence")),
            ("Bats", _v(r, "bat_hand"), _v(r, "bat_hand_confidence")),
            ("Bowls", bowls, _v(r, "bowl_type_confidence") if _v(r, "bowl_type") else _v(r, "bowl_kind_confidence"))]


def _card(d, result):
    r = d.iloc[0].to_dict()
    d = d.assign(label=[_label(c, g) for c, g in zip(d.competition, d.match_gender)]).sort_values("matches", ascending=False).head(10)
    panels = [(col, title, c) for col, title, c in (("runs", "Runs", PALETTE["primary"]), ("wickets", "Wickets", PALETTE["bad"]))
              if d[col].sum() > 0] or [("runs", "Runs", PALETTE["primary"])]
    n = len(panels)
    fig = make_subplots(rows=n + 1, cols=1, vertical_spacing=0.12, row_heights=[0.34] + [0.66 / n] * n,
                        subplot_titles=[""] + [f"{t} per competition" for _, t, _ in panels])
    for i, (col, _, c) in enumerate(panels, 2):
        fig.add_bar(y=d.label, x=d[col], orientation="h", row=i, col=1, marker_color=c, showlegend=False, cliponaxis=False,
                    text=[f"{v:,}" for v in d[col]], textposition="outside")
        fig.update_yaxes(autorange="reversed", row=i, col=1)
        fig.update_xaxes(range=[0, d[col].max() * 1.2], row=i, col=1)
    fig.update_xaxes(visible=False, row=1, col=1)
    fig.update_yaxes(visible=False, row=1, col=1)
    lo, hi = fig.layout.yaxis.domain   # the card sits in the first row; everything is placed in paper coordinates
    at = lambda f: lo + f * (hi - lo)  # noqa: E731
    tiles = _tiles(r)
    for i, (label, value, sure) in enumerate(tiles):
        x = (i + 0.5) / len(tiles)
        text = (value or "unknown").capitalize().replace("-arm ", "-arm<br>")
        fig.add_annotation(text=label.upper(), x=x, y=at(0.92), xref="paper", yref="paper", showarrow=False, yanchor="top",
                           font=dict(size=11, color="#9AA4B2"))
        fig.add_annotation(text=f"<b>{text}</b>", x=x, y=at(0.52), xref="paper", yref="paper", showarrow=False,
                           font=dict(size=16 if len(text) < 12 else 13, color="#E6EAF0" if value else "#9AA4B2"))
        fig.add_annotation(text=f"({sure})" if sure else "", x=x, y=at(0.14), xref="paper", yref="paper", showarrow=False,
                           font=dict(size=10, color="#9AA4B2"))
    fig.add_shape(type="rect", xref="paper", yref="paper", x0=0, x1=1, y0=at(0), y1=at(1), layer="below",
                  line=dict(color="rgba(255,255,255,0.18)"), fillcolor="rgba(255,255,255,0.04)")
    gender = " (name shared by a man and a woman: numbers mixed)" if _v(r, "player_gender") == "both" else ""
    return style(fig, str(r["player"]), result, note=f"{int(r['career_matches'])} T20 matches in the data{gender}",
                 height=300 + 150 * n + 30 * len(d))


def _list(d, result):
    top = d.head(15).iloc[::-1]
    fig = go.Figure()
    for role, c in _ROLE_COLOR.items():
        s = top[top.role.fillna("unknown") == role]
        if s.empty:
            continue
        fig.add_bar(y=s.player, x=s.career_matches, name=role, orientation="h", marker_color=c, cliponaxis=False,
                    text=[" | ".join(x for x in (_v(r._asdict(), "bat_slot"), _v(r._asdict(), "bowl_type") or _v(r._asdict(), "bowl_kind")) if x)
                          for r in s.itertuples()],
                    textposition="outside", textfont=dict(size=11))
    fig.update_xaxes(title_text="T20 matches in the data", range=[0, top.career_matches.max() * 1.45])
    return style(fig, f"Players: top {len(top)} by matches", result, note="text = batting slot | bowling type (or pace / spin)",
                 height=bars_height(len(top), 28, 190))
