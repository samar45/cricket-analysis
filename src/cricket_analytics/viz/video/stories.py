"""Stories for video: the hook's two numbers as big numbers, the metric as the title. `focus` = hook rank (default 1)."""

from . import big_number_card, message_card, num, scope_text, short_name, source_note


def video_figure(result, aspect="9:16", focus=None):
    df, note = result.data, source_note(result)
    who = short_name(result.meta["params"]["player"])
    if df.empty:
        return message_card(aspect, who, "No strong story in these filters", note)
    rank = int(focus) if str(focus or "").isdigit() else 1
    row = df[df["rank"] == rank]
    h = (row if len(row) else df).iloc[0]
    stats = [(num(h["value_a"]), f"{h['label_a']} ({h['n_a']:,} {h['n_unit']})")]
    if h["value_b"] == h["value_b"] and h["value_b"] is not None and h["kind"] == "gap":
        stats.append((num(h["value_b"]), f"{h['label_b']} ({h['n_b']:,} {h['n_unit']})"))
    return big_number_card(stats, f"{who}: {h['metric']}", aspect, scope_text(result), note)
