from cricket_analytics.ingest.commentary import parse_item


def item(text, ov, runs=0, legal=0, event="NONE", fmt=None):
    d = dict(commText=text, overNumber=ov, ballNbr=int(ov * 10) // 10, timestamp=1, inningsId=1,
             event=event, totalRuns=runs, legalRuns=legal)
    if fmt:
        d["commentaryFormats"] = {"bold": fmt}
    return d


A = "Arshdeep Singh to Shivam Dube, "


def test_slower_ball_four():
    r = parse_item(item(A + "B0$, Dube finishes with a boundary. Slower ball, but it is in the slot. Dube delays his bat swing and connects it off the middle",
                        19.6, 4, 4, "over-break,FOUR", {"formatId": ["B0$"], "formatValue": ["FOUR"]}))
    assert (r["over"], r["ball"], r["bowler"], r["batter"], r["runs_total"]) == (19, 6, "Arshdeep Singh", "Shivam Dube", 4)
    assert r["delivery"] == "slower ball" and r["contact"] == "middle"


def test_low_full_toss_inside_edge():
    r = parse_item(item(A + "no run, 134.6ks low full toss around off, Dube throws everything behind the big shot, gets a thick inside-edge", 19.5))
    assert r["speed"] == 134.6 and r["length"] == "full toss" and r["line"] == "outside off" and r["contact"] == "inside edge"


def test_yorker():
    r = parse_item(item(A + "no run, 133.9ks yorker outside off, Dube bends down and squeezes it straight to backward point", 19.4))
    assert r["speed"] == 133.9 and r["length"] == "yorker" and r["line"] == "outside off"


def test_very_full_miss():
    r = parse_item(item(A + "no run, 134.5ks very full delivery outside off, Dube swings off his feet and does not make contact", 19.3))
    assert r["length"] == "full" and r["contact"] == "miss"


def test_short_byes():
    r = parse_item(item(A + "byes, 1 run, banged in short and at the left-hander - Dube swings and misses, they run through for a bye.", 19.1, 1, 0))
    assert r["extra"] == "byes" and r["length"] == "bouncer" and r["line"] == "body" and r["contact"] == "miss"


def test_non_ball_ignored():
    assert parse_item({"commText": "chat", "timestamp": 1, "event": "NONE"}) is None
