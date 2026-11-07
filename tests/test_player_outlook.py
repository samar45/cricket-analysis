from cricket_analytics.models import player_outlook as O


def test_evidence_labels():
    assert [O.evidence_label(b) for b in (0, 299, 300, 899, 900)] == ["thin", "thin", "some", "some", "solid"]


def test_outlook_ordered_range():
    o = O.outlook(["V Kohli", "Nobody At All"]).set_index("player")
    k = o.loc["V Kohli"]
    assert 0 <= k.m10 <= k.exp_matches <= 14 and k.m10 <= k.m90 <= 14 and k.evidence == "solid"
    assert o.loc["Nobody At All"].isna()["exp_matches"] and o.loc["Nobody At All"].evidence == "thin"
