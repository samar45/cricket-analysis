"""Matchup predictor for video: the big numbers (expected runs an over, chance of a wicket per ball, balls per dismissal).
With view=grid it shows the five bowling types with the most balls, ranked by expected runs an over (all phases). focus = phase."""

from ...sql.fragments import PHASES
from . import (
    AMBER,
    INK,
    RED,
    big_number_card,
    hbars,
    message_card,
    num,
    scope_text,
    short_names,
    source_note,
)


def _vs(r) -> str:
    return r["bowler"] or (
        r["bowl_type"] if r["bowl_type_source"] != "none" else "a typical bowler"
    )


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "Matchup", "No prediction for these filters", note)
    sub = scope_text(result) + " | prediction, not a record"
    if len(df) > 1:
        want = focus if focus in PHASES else "all"
        d = (
            df[df.phase == want]
            .sort_values("batter_type_balls", ascending=False)
            .head(5)
            .sort_values("exp_runs_per_6", ascending=False)
        )
        return hbars(
            short_names(d.bowl_type),
            d.exp_runs_per_6,
            f"{d.batter.iloc[0]}: expected runs an over",
            aspect,
            f"by bowling type, {want if want != 'all' else 'all phases'} | {sub}",
            note,
            fmt=lambda v: num(v, 1),
        )
    r = df.iloc[0]
    when = f"{r.phase} overs" if r.phase != "all" else "all phases"
    stats = [
        (num(r.exp_runs_per_6, 1), "runs an over expected"),
        (f"{r.out_pct:.1f}%", "chance of a wicket each ball"),
        (num(r.balls_per_dismissal, 0), "balls per dismissal"),
    ]
    return big_number_card(
        stats,
        f"{r.batter} v {_vs(r)}, {when}",
        aspect,
        f"{sub} | {r.confidence} evidence",
        note,
        colors=[AMBER, RED, INK],
    )
