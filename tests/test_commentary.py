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


def test_wide_fielder_not_line():
    r = parse_item(item("Blessing Muzarabani to Heinrich Klaasen, 1 run, attempted yorker ends up as a low full toss. Klaasen toe ends the drive to wide long-on", 5.1, 1, 1))
    assert r["line"] is None and r["length"] == "full toss" and r["contact"] == "mistimed"


def test_wide_of_off_and_down_leg():
    r = parse_item(item(A + "SIX, back of a length and well wide of off, Dube carts the drive", 5.1, 6, 6))
    assert r["line"] == "outside off" and r["length"] == "back of a length"
    r = parse_item(item(A + "wide, sprays it down leg, Dube does not make contact", 5.2, 1, 0))
    assert r["line"] == "leg" and r["contact"] == "miss"


def test_inside_edging_and_leg_lined():
    r = parse_item(item(A + "no run, fraction shorter and Dube ends up inside-edging it onto his pad", 5.3))
    assert r["contact"] == "inside edge" and r["length"] == "short"
    assert parse_item(item(A + "1 run, 127.9ks leg-lined delivery, Dube tucks it", 5.4, 1, 1))["line"] == "leg"


def test_truncated_fragment_kept_as_ball():
    r = parse_item(item("even Dube is playing the reverse. He premeditated the shot and Arshdeep", 5.5, 1, 1))
    assert r is not None and r["runs_total"] == 1 and r["length"] is None
