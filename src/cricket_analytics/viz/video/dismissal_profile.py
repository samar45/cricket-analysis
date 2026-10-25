"""Dismissal profile for video: donut "how X gets out" (caught merged, top 4 kinds + other). Many batters are pooled."""

import pandas as pd

from . import MUTE, SERIES, donut, message_card, scope_text, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty:
        return message_card(aspect, "How he gets out", "No dismissals for these filters", note)
    kind = df["kind"].where(
        ~df["kind"].str.startswith("caught ("), "caught"
    )  # keeper / fielder split is too fine for a reel
    k = (
        df.groupby(kind)["outs"].sum().sort_values(ascending=False)
    )  # phase / bowler_kind splits just add up
    if len(k) > 4:
        k = pd.concat([k.head(4), pd.Series({"other": k.iloc[4:].sum()})])
    who = df["batter"].iloc[0] if df["batter"].nunique() == 1 else "batters"
    return donut(
        list(k.index),
        [int(v) for v in k],
        f"How {who} gets out",
        aspect,
        scope_text(result, ("player",)),
        note,
        center=(f"{int(k.sum()):,}", "dismissals"),
        colors=(SERIES + [MUTE])[: len(k)],
    )
