"""Player profile for video: a profile card. Title = the player, subtitle = role / batting hand / bowling type, then
big numbers: matches, plus runs for batters, wickets for bowlers, both for all-rounders (summed over the rows in the
result, i.e. the competitions selected). Without `player` the module returns a list, which has no single-message chart."""

import pandas as pd

from . import big_number_card, message_card, num, scope_text, source_note


def _val(r, k):
    v = r.get(k)
    return None if v is None or pd.isna(v) else v


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    if df.empty or df["player"].nunique() != 1:
        return message_card(aspect, "Player profile", "Pick one player to get a profile card", note)
    r = df.iloc[0]
    role = str(_val(r, "role") or "player")
    bowl = _val(r, "bowl_type") or (f"{_val(r, 'bowl_kind')} bowler" if _val(r, "bowl_kind") and role != "batter" else None)
    sub = " | ".join(str(x) for x in (role, f"{_val(r, 'bat_hand')}-hand bat" if _val(r, "bat_hand") else None, bowl) if x)
    scope = scope_text(result)
    one = "competition" in df.columns and result.meta["params"].get("competition")
    matches = int(df["matches"].sum()) if one else int(r["career_matches"])
    stats = [(num(matches), f"{scope.split(' | ')[0]} matches" if one else "T20 matches")]
    runs, wkts = int(df["runs"].sum()), int(df["wickets"].sum())
    if role != "bowler":
        stats.append((num(runs), "runs"))
    if role in ("bowler", "all-rounder"):
        stats.append((num(wkts), "wickets"))
    return big_number_card(stats, r["player"], aspect, sub, note)
